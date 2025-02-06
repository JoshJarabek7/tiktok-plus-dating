from datetime import UTC, datetime
from uuid import UUID, uuid4

from neo4j import ManagedTransaction
from pydantic import UUID4, HttpUrl

from app.db import DatabaseManager
from app.models.dating import (
    DatingFilter,
    DatingMatch,
    DatingProfile,
    Gender,
    Sexuality,
)
from app.models.interaction import InteractionType
from app.services.interaction import InteractionService


class DatingError(Exception):
    """Base exception for dating-related errors."""

    pass


class MatchCreationError(DatingError):
    """Exception raised when match creation fails."""

    pass


class ActionRecordingError(DatingError):
    """Exception raised when recording a dating action fails."""

    pass


class DatingService:
    """Service for managing dating profiles and matches.

    This service handles creating and updating dating profiles,
    finding potential matches, and managing dating interactions.
    """

    # Constants for CPU-optimized settings
    EMBEDDING_DIM = 64  # Reduced from 256 for CPU efficiency
    BATCH_SIZE = 100
    CONCURRENCY = 4
    SAMPLE_RATE = 0.5
    MAX_ITERATIONS = 100
    SIMILARITY_CUTOFF = 0.1
    TOP_K = 10  # Limit similarity comparisons
    DEFAULT_LIMIT = 50  # Default number of matches to return

    def __init__(self):
        """Initialize the dating service with required dependencies."""
        self.interaction_service = InteractionService()
        self._setup_gds()

    def _setup_gds(self) -> None:
        """Set up Graph Data Science projections and algorithms.

        Creates node projections for dating recommendations with memory-efficient
        settings suitable for CPU-based servers.
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.run("CALL gds.graph.drop('dating-graph') YIELD graphName;")
            # Create graph projection with optimized settings
            session.run(
                """
                CALL gds.graph.project.cypher(
                    'dating-graph',
                    'MATCH (n) WHERE n:User OR n:DatingProfile 
                     RETURN id(n) AS id, labels(n) AS labels,
                     CASE 
                        WHEN n:User THEN [
                            n.interests,
                            apoc.date.diff(n.birth_date, date(), 'years'),
                            [x IN labels(n) WHERE x <> "User"],
                            n.gender
                        ]
                        WHEN n:DatingProfile THEN [
                            n.gender_preference,
                            n.bio,
                            n.photos
                        ]
                        ELSE []
                     END AS features',
                    'MATCH (s)-[r:HAS_DATING_PROFILE|DATING_ACTION|DATING_MATCH|INTERACTED_WITH]-(t)
                     RETURN id(s) AS source, id(t) AS target, type(r) AS type,
                     CASE type(r)
                        WHEN "DATING_MATCH" THEN 1.0
                        WHEN "DATING_ACTION" THEN 
                            CASE r.type
                                WHEN "SUPER_LIKE" THEN 0.8
                                WHEN "SWIPE_RIGHT" THEN 0.6
                                ELSE 0.0
                            END
                        WHEN "INTERACTED_WITH" THEN r.completion_rate * 
                            CASE WHEN r.unregretted THEN 1.5 ELSE 1.0 END
                        ELSE 0.5
                     END AS weight',
                    {
                        validateRelationships: false,
                        batchSize: $batch_size
                    }
                )
            """,
                batch_size=self.BATCH_SIZE,
            )

            # Configure FastRP with CPU-optimized settings
            session.run(
                """
                CALL gds.fastRP.write(
                    'dating-graph',
                    {
                        embeddingDimension: $dim,
                        iterationWeights: [1.0, 1.0],
                        featureProperties: ['features'],
                        relationshipWeightProperty: 'weight',
                        writeProperty: 'embedding',
                        randomSeed: 42,
                        concurrency: 1,  # Reduce concurrency for low-resource
                        sudo: false       # For community edition
                    }
                )
            """,
                dim=self.EMBEDDING_DIM,
            )

            # Create node similarity graph with efficient settings
            session.run(
                """
                CALL gds.nodeSimilarity.write(
                    'dating-graph',
                    {
                        writeRelationshipType: 'SIMILAR',
                        writeProperty: 'similarity',
                        similarityCutoff: $cutoff,
                        topK: $top_k,
                        sampleRate: $sample_rate,
                        deltaThreshold: 0.001,
                        maxIterations: $max_iter,
                        batchSize: $batch_size,
                        concurrency: $concurrency
                    }
                )
            """,
                cutoff=self.SIMILARITY_CUTOFF,
                top_k=self.TOP_K,
                sample_rate=self.SAMPLE_RATE,
                max_iter=self.MAX_ITERATIONS,
                batch_size=self.BATCH_SIZE,
                concurrency=self.CONCURRENCY,
            )

    def _create_dating_profile(
        self, tx: ManagedTransaction, profile: DatingProfile
    ) -> DatingProfile:
        """Create a new dating profile in the database.

        Args:
            tx: The database transaction
            profile: The profile to create

        Returns:
            The created profile

        Raises:
            ValueError: If profile creation fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        CREATE (profile:DatingProfile {
            user_id: $user_id,
            bio: $bio,
            birth_date: date($birth_date),
            gender: $gender,
            sexuality: $sexuality,
            photos: $photos,
            max_distance_miles: $max_distance_miles,
            min_age_preference: $min_age_preference,
            max_age_preference: $max_age_preference,
            gender_preference: $gender_preference,
            is_visible: $is_visible,
            created_at: $current_time,
            updated_at: $current_time
        })
        CREATE (user)-[:HAS_DATING_PROFILE]->(profile)
        RETURN profile
        """

        result = tx.run(
            query,
            user_id=str(profile.user_id),
            bio=profile.bio,
            birth_date=profile.birth_date.isoformat(),
            gender=profile.gender.value,
            sexuality=profile.sexuality.value,
            photos=[str(photo) for photo in profile.photos],
            max_distance_miles=profile.max_distance_miles,
            min_age_preference=profile.min_age_preference,
            max_age_preference=profile.max_age_preference,
            gender_preference=[g.value for g in profile.gender_preference],
            is_visible=profile.is_visible,
            current_time=datetime.now(UTC).isoformat(),
        )

        if not result.consume().counters.nodes_created:
            raise ValueError("Failed to create dating profile")

        return profile

    def create_dating_profile(self, profile: DatingProfile) -> DatingProfile:
        """Create a new dating profile.

        Public method that handles the database session for creating
        a new dating profile.

        Args:
            profile: The profile to create

        Returns:
            The created profile

        Raises:
            ValueError: If profile creation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(self._create_dating_profile, profile)

    def _get_potential_matches(
        self, tx: ManagedTransaction, user_id: UUID4, filters: DatingFilter
    ) -> list[DatingProfile]:
        """Find potential dating matches for a user.

        Uses CPU-optimized Graph Data Science algorithms:
        1. FastRP embeddings for efficient similarity calculation
        2. Pre-computed node similarities
        3. Optimized path-based metrics
        4. Smart filtering based on preferences

        Args:
            tx: The database transaction
            user_id: ID of the user seeking matches
            filters: Filtering criteria for matches

        Returns:
            List of potential matches ordered by compatibility

        Raises:
            ValueError: If match finding fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})-[:HAS_DATING_PROFILE]->(user_profile:DatingProfile)
        // Add index hint for performance
        USING INDEX user_id_index
        
        // Find potential matches using efficient filtering
        MATCH (target:User)-[:HAS_DATING_PROFILE]->(target_profile:DatingProfile)
        WHERE target <> user
        AND target_profile.is_visible = true
        AND NOT (user)-[:BLOCKS|BLOCKED_BY]->(target)
        AND NOT (target)-[:BLOCKS|BLOCKED_BY]->(user)
        
        // Apply basic filters
        WITH user, user_profile, target, target_profile,
             apoc.date.diff(
                 date(target_profile.birth_date), 
                 date(), 
                 'years'
             ) as target_age
        WHERE target_age >= $min_age
        AND target_age <= $max_age
        AND target_profile.gender IN $gender_preference
        
        // Calculate embedding similarity efficiently
        WITH user, user_profile, target, target_profile, target_age,
             gds.similarity.cosine(user.embedding, target.embedding) AS embedding_sim
        
        // Get pre-computed node similarity
        OPTIONAL MATCH (user)-[sim:SIMILAR]-(target)
        WITH user, user_profile, target, target_profile, target_age, embedding_sim,
             sim.similarity AS node_sim
        
        // Calculate location-based score if available
        WITH user, user_profile, target, target_profile, target_age, embedding_sim, node_sim,
             CASE 
                WHEN user.latitude IS NOT NULL 
                     AND user.longitude IS NOT NULL
                     AND target.latitude IS NOT NULL
                     AND target.longitude IS NOT NULL
                THEN point.distance(
                    point({latitude: user.latitude, longitude: user.longitude}),
                    point({latitude: target.latitude, longitude: target.longitude})
                ) * 0.000621371
                ELSE 10000  # Default max distance if location data missing
             END as distance_miles
        
        // Apply distance filter
        WHERE distance_miles IS NULL OR distance_miles <= $max_distance_miles
        
        // Get interaction history
        OPTIONAL MATCH (user)-[int:INTERACTED_WITH]->(post:Post)<-[:POSTED]-(target)
        WITH user, user_profile, target, target_profile, target_age,
             embedding_sim, node_sim, distance_miles,
             collect(int) as interactions
        
        // Calculate interaction score
        WITH user, user_profile, target, target_profile, target_age,
             embedding_sim, node_sim, distance_miles,
             CASE WHEN size(interactions) > 0
                  THEN avg(
                    [int in interactions | 
                     int.completion_rate * size(int.engagement_signals) *
                     CASE WHEN int.unregretted THEN 1.5 ELSE 1.0 END
                    ])
                  ELSE 0
             END as interaction_score
        
        // Calculate compatibility score
        WITH target_profile, target_age,
             (
                COALESCE(embedding_sim, 0.0) * 0.3 +
                COALESCE(node_sim, 0.0) * 0.2 +
                interaction_score * 0.2 +
                CASE 
                    WHEN distance_miles IS NOT NULL 
                    THEN (1 - (distance_miles / $max_distance_miles)) * 0.3
                    ELSE 0.15  // Half weight if location unknown
                END
             ) as compatibility_score
        
        // Return matches ordered by compatibility
        RETURN target_profile {
            .*,
            age: target_age,
            compatibility_score: compatibility_score
        } as profile
        ORDER BY compatibility_score DESC
        SKIP $offset
        LIMIT $limit
        """

        result = tx.run(
            query,
            user_id=str(user_id),
            min_age=filters.min_age,
            max_age=filters.max_age,
            gender_preference=[g.value for g in filters.gender_preference]
            if filters.gender_preference
            else [],
            max_distance_miles=filters.max_distance_miles,
            offset=0,  # We'll filter excluded matches in memory
            limit=1000,  # Get more to allow for filtering
        )

        matches = []
        seen_ids = set()

        for record in result:
            profile_data = record["profile"]

            # Skip if we should exclude seen/matched profiles
            if filters.exclude_seen and profile_data["user_id"] in seen_ids:
                continue

            if filters.exclude_matched and self._check_existing_match(
                tx, user_id, UUID(profile_data["user_id"])
            ):
                continue

            if profile_data["compatibility_score"] < filters.min_compatibility:
                continue

            # Convert data types
            profile_data["photos"] = [HttpUrl(p) for p in profile_data["photos"]]
            profile_data["gender"] = Gender(profile_data["gender"])
            profile_data["sexuality"] = Sexuality(profile_data["sexuality"])
            profile_data["gender_preference"] = [
                Gender(g) for g in profile_data["gender_preference"]
            ]

            matches.append(DatingProfile(**profile_data))

            if len(matches) >= filters.limit:
                break

        return matches[filters.offset :]

    def _check_existing_match(
        self, tx: ManagedTransaction, user_id: UUID4, target_id: UUID4
    ) -> bool:
        """Check if a match already exists between users.

        Args:
            tx: The database transaction
            user_id: First user's ID
            target_id: Second user's ID

        Returns:
            True if a match exists, False otherwise
        """
        query = """
        RETURN exists((:User {user_id: $user_id})-[:DATING_MATCH]-(:User {user_id: $target_id})) as has_match
        """
        result = tx.run(query, user_id=str(user_id), target_id=str(target_id))
        if record := result.single():
            return record["has_match"]
        return False

    def get_potential_matches(
        self, user_id: UUID4, filters: DatingFilter
    ) -> list[DatingProfile]:
        """Find potential dating matches for a user.

        Public method that handles the database session for finding
        potential matches based on filters and preferences.

        Args:
            user_id: ID of the user seeking matches
            filters: Filtering criteria for matches

        Returns:
            List of potential matches ordered by compatibility

        Raises:
            ValueError: If match finding fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._get_potential_matches, user_id, filters)

    def _record_dating_action(
        self,
        tx: ManagedTransaction,
        user_id: UUID4,
        target_id: UUID4,
        action: InteractionType,
    ) -> DatingMatch | None:
        """Record a dating action (like/pass/super) in the database.

        Creates or updates a match record and checks for mutual matches.

        Args:
            tx: The database transaction
            user_id: ID of the user taking action
            target_id: ID of the profile being acted on
            action: The action being taken

        Returns:
            DatingMatch if mutual match created, None otherwise

        Raises:
            ActionRecordingError: If action recording fails
            MatchCreationError: If match creation fails
        """
        try:
            # First verify both users exist
            check_query = """
            MATCH (user:User {user_id: $user_id})
            MATCH (target:User {user_id: $target_id})
            RETURN {
                user_exists: user IS NOT NULL,
                target_exists: target IS NOT NULL,
                is_blocked: exists((user)-[:BLOCKS]->(target)) OR exists((target)-[:BLOCKS]->(user))
            } as status
            """
            check = tx.run(
                check_query,
                user_id=str(user_id),
                target_id=str(target_id),
            ).single()

            if not check:
                raise ActionRecordingError("Failed to verify users")

            status = check["status"]
            if not status["user_exists"]:
                raise ActionRecordingError("User not found")
            if not status["target_exists"]:
                raise ActionRecordingError("Target user not found")
            if status["is_blocked"]:
                raise ActionRecordingError("Cannot interact with blocked user")

            # Record the action
            query = """
            MATCH (user:User {user_id: $user_id})
            MATCH (target:User {user_id: $target_id})
            
            // Create the action relationship
            MERGE (user)-[action:DATING_ACTION {type: $action}]->(target)
            SET action.updated_at = $current_time
            
            // Check for mutual match
            WITH user, target, action,
                 exists((target)-[:DATING_ACTION {type: 'SWIPE_RIGHT'}]->(user)) as they_like,
                 exists((target)-[:DATING_ACTION {type: 'SUPER_LIKE'}]->(user)) as they_super
            
            WHERE action.type IN ['SWIPE_RIGHT', 'SUPER_LIKE'] AND
                  (they_like OR they_super)
            
            // Create match if mutual
            MERGE (user)-[match:DATING_MATCH]-(target)
            ON CREATE SET
                match.match_id = $match_id,
                match.created_at = $current_time,
                match.updated_at = $current_time,
                match.compatibility_score = 0.0  // Will be calculated by background job
            
            RETURN {
                match_id: match.match_id,
                user_id_a: user.user_id,
                user_id_b: target.user_id,
                user_a_action: action.type,
                user_b_action: CASE 
                    WHEN they_super THEN 'SUPER_LIKE'
                    ELSE 'SWIPE_RIGHT'
                END,
                distance_miles: point.distance(
                    point({latitude: user.latitude, longitude: user.longitude}),
                    point({latitude: target.latitude, longitude: target.longitude})
                ) * 0.000621371,  // Convert meters to miles
                compatibility_score: 0.0,  // Will be updated by background job
                is_mutual: true,
                created_at: match.created_at,
                updated_at: match.updated_at
            } as match
            """

            result = tx.run(
                query,
                user_id=str(user_id),
                target_id=str(target_id),
                action=action.value,
                match_id=str(uuid4()),
                current_time=datetime.now(UTC).isoformat(),
            )

            if record := result.single():
                return DatingMatch(**record["match"])
            return None

        except Exception as e:
            if "match" in str(e).lower():
                raise MatchCreationError(f"Failed to create match: {str(e)}")
            raise ActionRecordingError(f"Failed to record action: {str(e)}")

    async def record_dating_action(
        self, user_id: UUID4, target_id: UUID4, action: InteractionType
    ) -> DatingMatch | None:
        """Record a dating action (like/pass/super).

        Public method that handles the database session for recording
        dating actions and checking for mutual matches.

        Args:
            user_id: ID of the user taking action
            target_id: ID of the profile being acted on
            action: The action being taken

        Returns:
            DatingMatch if mutual match created, None otherwise

        Raises:
            ActionRecordingError: If action recording fails
            MatchCreationError: If match creation fails
        """
        if user_id == target_id:
            raise ActionRecordingError("Cannot perform dating action on yourself")

        if action not in {
            InteractionType.SWIPE_RIGHT,
            InteractionType.SWIPE_LEFT,
            InteractionType.SUPER_LIKE,
        }:
            raise ActionRecordingError("Invalid dating action type")

        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._record_dating_action, user_id, target_id, action
            )

    def get_dating_profile(self, user_id: UUID4) -> DatingProfile:
        """Get a user's dating profile.

        Args:
            user_id: ID of the user whose profile to get

        Returns:
            The requested dating profile

        Raises:
            ValueError: If profile not found
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._get_dating_profile, user_id)

    def _get_dating_profile(
        self, tx: ManagedTransaction, user_id: UUID4
    ) -> DatingProfile:
        """Get a user's dating profile from the database.

        Args:
            tx: The database transaction
            user_id: ID of the user whose profile to get

        Returns:
            The requested dating profile

        Raises:
            ValueError: If profile not found
        """
        query = """
        MATCH (user:User {user_id: $user_id})-[:HAS_DATING_PROFILE]->(profile:DatingProfile)
        RETURN profile {.*}
        """

        result = tx.run(query, user_id=str(user_id))
        if record := result.single():
            profile_data = record["profile"]
            profile_data["photos"] = [HttpUrl(p) for p in profile_data["photos"]]
            profile_data["gender"] = Gender(profile_data["gender"])
            profile_data["sexuality"] = Sexuality(profile_data["sexuality"])
            profile_data["gender_preference"] = [
                Gender(g) for g in profile_data["gender_preference"]
            ]
            return DatingProfile(**profile_data)
        raise ValueError("Dating profile not found")

    def update_dating_profile(self, profile: DatingProfile) -> DatingProfile:
        """Update a user's dating profile.

        Args:
            profile: The updated profile data

        Returns:
            The updated dating profile

        Raises:
            ValueError: If update fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(self._update_dating_profile, profile)

    def _update_dating_profile(
        self, tx: ManagedTransaction, profile: DatingProfile
    ) -> DatingProfile:
        """Update a user's dating profile in the database.

        Args:
            tx: The database transaction
            profile: The updated profile data

        Returns:
            The updated dating profile

        Raises:
            ValueError: If update fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})-[:HAS_DATING_PROFILE]->(profile:DatingProfile)
        SET profile += {
            bio: $bio,
            birth_date: date($birth_date),
            gender: $gender,
            sexuality: $sexuality,
            photos: $photos,
            max_distance_miles: $max_distance_miles,
            min_age_preference: $min_age_preference,
            max_age_preference: $max_age_preference,
            gender_preference: $gender_preference,
            is_visible: $is_visible,
            updated_at: $current_time
        }
        RETURN profile {.*}
        """

        result = tx.run(
            query,
            user_id=str(profile.user_id),
            bio=profile.bio,
            birth_date=profile.birth_date.isoformat(),
            gender=profile.gender.value,
            sexuality=profile.sexuality.value,
            photos=[str(photo) for photo in profile.photos],
            max_distance_miles=profile.max_distance_miles,
            min_age_preference=profile.min_age_preference,
            max_age_preference=profile.max_age_preference,
            gender_preference=[g.value for g in profile.gender_preference],
            is_visible=profile.is_visible,
            current_time=datetime.now(UTC).isoformat(),
        )

        if record := result.single():
            profile_data = record["profile"]
            profile_data["photos"] = [HttpUrl(p) for p in profile_data["photos"]]
            profile_data["gender"] = Gender(profile_data["gender"])
            profile_data["sexuality"] = Sexuality(profile_data["sexuality"])
            profile_data["gender_preference"] = [
                Gender(g) for g in profile_data["gender_preference"]
            ]
            return DatingProfile(**profile_data)
        raise ValueError("Failed to update dating profile")

    def get_mutual_matches(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[DatingMatch]:
        """Get a user's mutual matches.

        Args:
            user_id: ID of the user whose matches to get
            limit: Maximum number of matches to return
            offset: Number of matches to skip

        Returns:
            List of mutual matches ordered by match date

        Raises:
            ValueError: If fetching matches fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(
                self._get_mutual_matches, user_id, limit, offset
            )

    def _get_mutual_matches(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[DatingMatch]:
        """Get a user's mutual matches from the database.

        Args:
            tx: The database transaction
            user_id: ID of the user whose matches to get
            limit: Maximum number of matches to return
            offset: Number of matches to skip

        Returns:
            List of mutual matches ordered by match date

        Raises:
            ValueError: If fetching matches fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})-[match:DATING_MATCH]-(other:User)
        WITH user, other, match
        ORDER BY match.created_at DESC
        SKIP $offset
        LIMIT $limit
        
        // Get the actions that led to the match
        MATCH (user)-[action_a:DATING_ACTION]->(other)
        MATCH (other)-[action_b:DATING_ACTION]->(user)
        WHERE action_a.type IN ['SWIPE_RIGHT', 'SUPER_LIKE']
        AND action_b.type IN ['SWIPE_RIGHT', 'SUPER_LIKE']
        
        // Calculate distance if location data exists
        WITH user, other, match, action_a, action_b,
             CASE 
                WHEN user.latitude IS NOT NULL 
                     AND user.longitude IS NOT NULL
                     AND other.latitude IS NOT NULL
                     AND other.longitude IS NOT NULL
                THEN point.distance(
                    point({latitude: user.latitude, longitude: user.longitude}),
                    point({latitude: other.latitude, longitude: other.longitude})
                ) * 0.000621371  // Convert meters to miles
                ELSE null
             END as distance_miles

        RETURN {
            match_id: match.match_id,
            user_id_a: user.user_id,
            user_id_b: other.user_id,
            user_a_action: action_a.type,
            user_b_action: action_b.type,
            distance_miles: distance_miles,
            compatibility_score: match.compatibility_score,
            is_mutual: true,
            created_at: match.created_at,
            updated_at: match.updated_at
        } as match
        ORDER BY match.created_at DESC
        """

        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )

        return [DatingMatch(**record["match"]) for record in result]

    def record_profile_view(self, viewer_id: UUID4, creator_id: UUID4) -> None:
        """Record a profile view interaction.

        Args:
            viewer_id: ID of the user viewing the profile
            creator_id: ID of the creator being viewed

        Raises:
            ValueError: If recording fails
        """
        # Record both dating profile view and creator interaction
        self.interaction_service.record_profile_view(viewer_id, creator_id)
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.execute_write(self._record_profile_view, viewer_id, creator_id)

    def _record_profile_view(
        self, tx: ManagedTransaction, viewer_id: UUID4, creator_id: UUID4
    ) -> None:
        """Record a profile view in the database.

        Args:
            tx: The database transaction
            viewer_id: ID of the user viewing the profile
            creator_id: ID of the creator being viewed

        Raises:
            ValueError: If recording fails
        """
        query = """
        MATCH (viewer:User {user_id: $viewer_id})
        MATCH (creator:User {user_id: $creator_id})
        WHERE viewer <> creator
        
        // Record dating profile view
        MERGE (viewer)-[view:DATING_PROFILE_VIEW]->(creator)
        ON CREATE SET
            view.view_count = 1,
            view.created_at = $current_time,
            view.updated_at = $current_time
        ON MATCH SET
            view.view_count = view.view_count + 1,
            view.updated_at = $current_time
        """

        result = tx.run(
            query,
            viewer_id=str(viewer_id),
            creator_id=str(creator_id),
            current_time=datetime.now(UTC).isoformat(),
        )

        if (
            not result.consume().counters.relationships_created
            and not result.consume().counters.properties_set
        ):
            raise ValueError("Failed to record profile view")
