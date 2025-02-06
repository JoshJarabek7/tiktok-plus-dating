from datetime import UTC, datetime

from neo4j import ManagedTransaction
from pydantic import UUID4, EmailStr

from app.db import DatabaseManager
from app.models.user import User


class ProfileError(Exception):
    """Base exception for profile-related errors."""

    pass


class ProfileNotFoundError(ProfileError):
    """Exception raised when a profile cannot be found."""

    pass


class ProfileUpdateError(ProfileError):
    """Exception raised when profile update fails."""

    pass


class ProfileAccessError(ProfileError):
    """Exception raised when profile access is denied."""

    pass


class ProfileService:
    """Service for managing user profiles.

    This service handles all profile-related operations including:
    - Updating profile information
    - Getting profile information
    - Managing profile privacy settings
    - Handling profile pictures

    All methods verify user permissions and handle blocked user relationships.
    """

    # Constants for CPU-optimized settings
    EMBEDDING_DIM = 64  # Reduced from 256 for CPU efficiency
    BATCH_SIZE = 100
    CONCURRENCY = 4
    SAMPLE_RATE = 0.5
    MAX_ITERATIONS = 100
    SIMILARITY_CUTOFF = 0.1
    TOP_K = 10  # Limit similarity comparisons

    def __init__(self) -> None:
        """Initialize the profile service.

        Sets up the Graph Data Science library with CPU-optimized settings.
        """
        self._setup_gds()

    def _setup_gds(self) -> None:
        """Set up Graph Data Science projections and algorithms.

        Creates node projections for profile analysis with memory-efficient
        settings suitable for CPU-based servers.
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            # Create graph projection with optimized settings
            session.run(
                """
                CALL gds.graph.project.cypher(
                    'profile-graph',
                    'MATCH (n) WHERE n:User 
                     RETURN id(n) AS id, labels(n) AS labels,
                     CASE 
                        WHEN n:User THEN [
                            n.interests,
                            [x IN labels(n) WHERE x <> "User"],
                            n.bio,
                            n.username,
                            n.display_name
                        ]
                        ELSE []
                     END AS features',
                    'MATCH (s)-[r:FOLLOWS|INTERACTED_WITH|COMMENTED|LIKED]-(t)
                     RETURN id(s) AS source, id(t) AS target, type(r) AS type,
                     CASE type(r)
                        WHEN "FOLLOWS" THEN 1.0
                        WHEN "INTERACTED_WITH" THEN r.completion_rate * 
                            CASE WHEN r.unregretted THEN 1.5 ELSE 1.0 END
                        WHEN "COMMENTED" THEN 0.8
                        WHEN "LIKED" THEN 0.6
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
                    'profile-graph',
                    {
                        embeddingDimension: $dim,
                        iterationWeights: [1.0, 1.0],
                        featureProperties: ['features'],
                        relationshipWeightProperty: 'weight',
                        writeProperty: 'embedding',
                        randomSeed: 42,
                        batchSize: $batch_size,
                        concurrency: $concurrency
                    }
                )
            """,
                dim=self.EMBEDDING_DIM,
                batch_size=self.BATCH_SIZE,
                concurrency=self.CONCURRENCY,
            )

            # Create node similarity graph with efficient settings
            session.run(
                """
                CALL gds.nodeSimilarity.write(
                    'profile-graph',
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

    def _get_profile(
        self, tx: ManagedTransaction, user_id: UUID4, viewer_id: UUID4 | None = None
    ) -> User:
        """Get a user's profile information.

        If viewer_id is provided, checks for block relationships and privacy settings.
        For private profiles, only shows full information to followers.

        Args:
            tx: The database transaction
            user_id: ID of the user whose profile to get
            viewer_id: Optional ID of the user viewing the profile

        Returns:
            User containing the profile information

        Raises:
            ValueError: If user not found or viewer is blocked
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        WHERE user IS NOT NULL
        
        // If we have a viewer, check blocks and following status
        OPTIONAL MATCH (viewer:User {user_id: $viewer_id})
        OPTIONAL MATCH (viewer)-[b1:BLOCKS]->(user)
        OPTIONAL MATCH (user)-[b2:BLOCKS]->(viewer)
        OPTIONAL MATCH (viewer)-[f:FOLLOWS]->(user)
        
        WITH user, viewer, b1, b2, f,
             CASE 
                WHEN viewer IS NULL THEN false
                WHEN b1 IS NOT NULL OR b2 IS NOT NULL THEN true
                ELSE false
             END as is_blocked,
             CASE
                WHEN viewer IS NULL THEN false
                WHEN f IS NOT NULL THEN true
                ELSE false
             END as is_following
        
        WHERE NOT is_blocked
        
        // Return limited info for private profiles if not following
        RETURN CASE
            WHEN user.is_private AND NOT is_following AND viewer IS NOT NULL
            THEN {
                user_id: user.user_id,
                username: user.username,
                display_name: user.display_name,
                is_private: user.is_private,
                profile_picture_s3_key: user.profile_picture_s3_key
            }
            ELSE user
        END as profile
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            viewer_id=str(viewer_id) if viewer_id else None,
        )
        if record := result.single():
            return User(**record["profile"])
        raise ValueError("User not found or you are blocked")

    async def get_profile(self, user_id: UUID4, viewer_id: UUID4 | None = None) -> User:
        """Get a user's profile information.

        Public method that handles the database session for getting a profile.

        Args:
            user_id: ID of the user whose profile to get
            viewer_id: Optional ID of the user viewing the profile

        Returns:
            User containing the profile information

        Raises:
            ProfileNotFoundError: If user not found
            ProfileAccessError: If viewer is blocked
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(self._get_profile, user_id, viewer_id)
            except ValueError as e:
                if "blocked" in str(e).lower():
                    raise ProfileAccessError(str(e))
                raise ProfileNotFoundError(str(e))

    def _update_profile(
        self,
        tx: ManagedTransaction,
        user_id: UUID4,
        display_name: str | None = None,
        email: EmailStr | None = None,
        bio: str | None = None,
        is_private: bool | None = None,
        profile_picture_s3_key: str | None = None,
    ) -> User:
        """Update a user's profile information.

        Only updates the fields that are provided (not None).

        Args:
            tx: The database transaction
            user_id: ID of the user whose profile to update
            display_name: Optional new display name
            email: Optional new email address
            bio: Optional new biography
            is_private: Optional new privacy setting
            profile_picture_s3_key: Optional new profile picture S3 key

        Returns:
            Updated User

        Raises:
            ValueError: If user not found
        """
        # Build dynamic SET clause based on provided fields
        set_clauses = []
        params: dict[str, str | bool | None] = {"user_id": str(user_id)}

        if display_name is not None:
            set_clauses.append("user.display_name = $display_name")
            params["display_name"] = display_name

        if email is not None:
            set_clauses.append("user.email = $email")
            params["email"] = str(email)

        if bio is not None:
            set_clauses.append("user.bio = $bio")
            params["bio"] = bio

        if is_private is not None:
            set_clauses.append("user.is_private = $is_private")
            params["is_private"] = is_private

        if profile_picture_s3_key is not None:
            set_clauses.append("user.profile_picture_s3_key = $profile_picture_s3_key")
            params["profile_picture_s3_key"] = profile_picture_s3_key

        # Add updated_at timestamp
        set_clauses.append("user.updated_at = $updated_at")
        params["updated_at"] = datetime.now(UTC).isoformat()

        query = """
        MATCH (user:User {user_id: $user_id})
        WHERE user IS NOT NULL
        SET {set_clauses}
        RETURN user
        """

        result = tx.run(
            query.format(set_clauses=", ".join(set_clauses)),
            parameters=params,
        )
        if record := result.single():
            return User(**record["user"])
        raise ValueError("User not found")

    async def update_profile(
        self,
        user_id: UUID4,
        display_name: str | None = None,
        email: EmailStr | None = None,
        bio: str | None = None,
        is_private: bool | None = None,
        profile_picture_s3_key: str | None = None,
    ) -> User:
        """Update a user's profile information.

        Public method that handles the database session for updating a profile.

        Args:
            user_id: ID of the user whose profile to update
            display_name: Optional new display name
            email: Optional new email address
            bio: Optional new biography
            is_private: Optional new privacy setting
            profile_picture_s3_key: Optional new profile picture S3 key

        Returns:
            Updated User

        Raises:
            ProfileNotFoundError: If user not found
            ProfileUpdateError: If update fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_write(
                    self._update_profile,
                    user_id,
                    display_name,
                    email,
                    bio,
                    is_private,
                    profile_picture_s3_key,
                )
            except ValueError as e:
                if "not found" in str(e).lower():
                    raise ProfileNotFoundError(str(e))
                raise ProfileUpdateError(str(e))

    async def update_location(
        self,
        user_id: UUID4,
        latitude: float,
        longitude: float,
    ) -> User:
        """Update a user's location.

        Args:
            user_id: ID of the user whose location to update
            latitude: New latitude (-90 to 90)
            longitude: New longitude (-180 to 180)

        Returns:
            Updated User

        Raises:
            ProfileNotFoundError: If user not found
            ProfileUpdateError: If update fails or coordinates invalid
        """
        try:
            if not -90 <= latitude <= 90:
                raise ProfileUpdateError("Latitude must be between -90 and 90")
            if not -180 <= longitude <= 180:
                raise ProfileUpdateError("Longitude must be between -180 and 180")

            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_write(
                    self._update_location, user_id, latitude, longitude
                )
        except ValueError as e:
            if "not found" in str(e).lower():
                raise ProfileNotFoundError(str(e))
            raise ProfileUpdateError(str(e))

    def _update_location(
        self,
        tx: ManagedTransaction,
        user_id: UUID4,
        latitude: float,
        longitude: float,
    ) -> User:
        """Update a user's location in the database.

        Args:
            tx: The database transaction
            user_id: ID of the user whose location to update
            latitude: New latitude
            longitude: New longitude

        Returns:
            Updated User

        Raises:
            ValueError: If update fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        SET user.latitude = $latitude,
            user.longitude = $longitude,
            user.location_updated_at = $current_time
        RETURN user
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            latitude=latitude,
            longitude=longitude,
            current_time=datetime.now(UTC).isoformat(),
        )
        if record := result.single():
            return User(**record["user"])
        raise ValueError("User not found")

    async def search_profiles(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        """Search for user profiles.

        This method searches usernames, display names, and bios
        for matching text. Results are ordered by relevance.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            List of matching profiles

        Raises:
            ValueError: If search fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._search_profiles, query, limit, offset)

    def _search_profiles(
        self,
        tx: ManagedTransaction,
        query: str,
        limit: int,
        offset: int,
    ) -> list[User]:
        """Search for user profiles in the database.

        Uses a combination of:
        1. Text matching with relevance scoring
        2. Vector similarity from FastRP embeddings
        3. Engagement metrics for ranking
        4. Profile completeness score

        Args:
            tx: The database transaction
            query: Search query string
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            List of matching profiles ordered by relevance

        Raises:
            ValueError: If search fails
        """
        cypher_query = """
        // Find users matching the search query
        MATCH (user:User)
        WHERE toLower(user.username) CONTAINS toLower($search_query)
           OR toLower(user.display_name) CONTAINS toLower($search_query)
           OR (user.bio IS NOT NULL AND toLower(user.bio) CONTAINS toLower($search_query))
        
        // Calculate text match score
        WITH user,
             CASE
                WHEN toLower(user.username) = toLower($search_query) THEN 1.0
                WHEN toLower(user.username) CONTAINS toLower($search_query) THEN 0.8
                WHEN toLower(user.display_name) = toLower($search_query) THEN 0.6
                WHEN toLower(user.display_name) CONTAINS toLower($search_query) THEN 0.4
                ELSE 0.2  // Bio match
             END as text_score

        // Get similar users based on embeddings
        WITH user, text_score
        MATCH (other:User)
        WHERE other <> user
        WITH user, text_score,
             gds.similarity.cosine(user.embedding, other.embedding) AS embedding_sim
        
        // Calculate profile completeness
        WITH user, text_score, embedding_sim,
             (
                 CASE WHEN user.bio IS NOT NULL THEN 0.2 ELSE 0 END +
                 CASE WHEN user.profile_picture_s3_key IS NOT NULL THEN 0.2 ELSE 0 END +
                 CASE WHEN user.display_name <> user.username THEN 0.2 ELSE 0 END +
                 CASE WHEN user.post_count > 0 THEN 0.2 ELSE 0 END +
                 CASE WHEN user.follower_count > 0 THEN 0.2 ELSE 0 END
             ) as completeness_score
        
        // Calculate engagement score
        WITH user, text_score, embedding_sim, completeness_score,
             (
                 CASE 
                     WHEN user.follower_count + user.following_count > 0
                     THEN log10(1 + user.follower_count + user.following_count)
                     ELSE 0 
                 END * 0.5 +
                 CASE 
                     WHEN user.post_count > 0
                     THEN log10(1 + user.post_count)
                     ELSE 0 
                 END * 0.5
             ) / 4 as engagement_score  // Normalize to 0-1 range
        
        // Calculate final relevance score
        WITH user,
             (
                 text_score * 0.4 +                // Text match relevance
                 COALESCE(embedding_sim, 0) * 0.3 +  // Content/behavior similarity
                 completeness_score * 0.2 +        // Profile completeness
                 engagement_score * 0.1            // Engagement metrics
             ) as relevance
        
        // Return results ordered by relevance
        RETURN user
        ORDER BY relevance DESC
        SKIP $offset
        LIMIT $limit
        """

        result = tx.run(
            cypher_query,
            search_query=query,
            offset=offset,
            limit=limit,
        )
        return [User(**record["user"]) for record in result]
