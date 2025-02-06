from datetime import UTC, datetime
from enum import Enum
from math import asin, cos, radians, sin, sqrt
from typing import Any

from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.interaction import (
    InteractionType,
    UserSimilarityScore,
    VideoInteractionMetrics,
)


class DistanceUnit(str, Enum):
    """Units for distance measurements.

    Used to specify the desired unit for distance calculations
    and filtering in location-based features.
    """

    MILES = "miles"
    KILOMETERS = "kilometers"


class InteractionService:
    """Service for tracking and analyzing user interactions.

    This service handles recording user interactions with content
    and calculating similarity scores for recommendations and dating.
    """

    # Constants for distance calculations
    EARTH_RADIUS_KM = 6371.0
    EARTH_RADIUS_MI = 3958.8
    KM_TO_MI = 0.621371
    MI_TO_KM = 1.60934

    # Constants for time decay
    HALF_LIFE_DAYS = 30
    MIN_WEIGHT = 0.1

    # Constants for CPU-optimized embeddings
    EMBEDDING_DIM = 64  # Reduced from 256 for CPU efficiency
    BATCH_SIZE = 100
    CONCURRENCY = 4
    SAMPLE_RATE = 0.5
    MAX_ITERATIONS = 100
    SIMILARITY_CUTOFF = 0.1
    TOP_K = 10  # Limit similarity comparisons

    def __init__(self) -> None:
        """Initialize the interaction service.

        Sets up the Graph Data Science library with CPU-optimized settings.
        """
        self._setup_gds()

    def _setup_gds(self) -> None:
        """Set up Graph Data Science projections and algorithms.

        Creates node projections for interaction analysis with memory-efficient
        settings suitable for CPU-based servers.
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            # Create graph projection with optimized settings
            session.run(
                """
                CALL gds.graph.project.cypher(
                    'interaction-graph',
                    'MATCH (n) WHERE n:User OR n:Post OR n:Comment 
                     RETURN id(n) AS id, labels(n) AS labels, 
                     CASE WHEN n:User THEN [n.interests] ELSE [] END AS features',
                    'MATCH (s)-[r:INTERACTED_WITH|FOLLOWS|POSTED|COMMENTED]-(t)
                     RETURN id(s) AS source, id(t) AS target, type(r) AS type,
                     CASE type(r)
                        WHEN "INTERACTED_WITH" THEN r.completion_rate * 
                            CASE WHEN r.unregretted THEN 1.5 ELSE 1.0 END
                        WHEN "FOLLOWS" THEN 1.0
                        WHEN "POSTED" THEN 0.8
                        WHEN "COMMENTED" THEN 0.6
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
                    'interaction-graph',
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
                    'interaction-graph',
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

    def _record_video_interaction(
        self, tx: ManagedTransaction, metrics: VideoInteractionMetrics
    ) -> None:
        """Record a video interaction in the database.

        Creates or updates interaction metrics for a video viewing session.

        Args:
            tx: The database transaction
            metrics: The interaction metrics to record

        Raises:
            ValueError: If recording fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (video:Post {post_id: $video_id})
        
        MERGE (user)-[r:INTERACTED_WITH]->(video)
        ON CREATE SET
            r.view_count = 1,
            r.total_duration_ms = $view_duration_ms,
            r.avg_duration_ms = $view_duration_ms,
            r.completion_rate = $completion_rate,
            r.loop_count = $loop_count,
            r.engagement_signals = $engagement_signals,
            r.unregretted = $unregretted,
            r.created_at = $current_time,
            r.updated_at = $current_time
        ON MATCH SET
            r.view_count = r.view_count + 1,
            r.total_duration_ms = r.total_duration_ms + $view_duration_ms,
            r.avg_duration_ms = (r.total_duration_ms + $view_duration_ms) / (r.view_count + 1),
            r.completion_rate = (r.completion_rate * r.view_count + $completion_rate) / (r.view_count + 1),
            r.loop_count = r.loop_count + $loop_count,
            r.engagement_signals = r.engagement_signals + $engagement_signals,
            r.unregretted = CASE WHEN $unregretted THEN true ELSE r.unregretted END,
            r.updated_at = $current_time

        WITH user, video
        
        // Update creator interaction metrics
        MATCH (video)<-[:POSTED]-(creator:User)
        WHERE creator <> user
        MERGE (user)-[cr:CREATOR_INTERACTION]->(creator)
        ON CREATE SET
            cr.profile_view_count = 0,
            cr.total_view_duration_ms = $view_duration_ms,
            cr.video_count = 1,
            cr.completion_rate_sum = $completion_rate,
            cr.completion_rate_avg = $completion_rate,
            cr.created_at = $current_time,
            cr.updated_at = $current_time
        ON MATCH SET
            cr.total_view_duration_ms = cr.total_view_duration_ms + $view_duration_ms,
            cr.video_count = cr.video_count + 1,
            cr.completion_rate_sum = cr.completion_rate_sum + $completion_rate,
            cr.completion_rate_avg = cr.completion_rate_sum / cr.video_count,
            cr.updated_at = $current_time
        """

        result = tx.run(
            query,
            user_id=str(metrics.user_id),
            video_id=str(metrics.video_id),
            view_duration_ms=metrics.view_duration_ms,
            completion_rate=metrics.completion_rate,
            loop_count=metrics.loop_count,
            engagement_signals=[signal.value for signal in metrics.engagement_signals],
            unregretted=metrics.unregretted,
            current_time=datetime.now(UTC).isoformat(),
        )

        if (
            not result.consume().counters.relationships_created
            and not result.consume().counters.properties_set
        ):
            raise ValueError("Failed to record video interaction")

    def record_video_interaction(self, metrics: VideoInteractionMetrics) -> None:
        """Record a video interaction.

        Public method that handles the database session for recording
        video interaction metrics.

        Args:
            metrics: The interaction metrics to record

        Raises:
            ValueError: If recording fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.execute_write(self._record_video_interaction, metrics)

    def _record_profile_view(
        self, tx: ManagedTransaction, viewer_id: UUID4, creator_id: UUID4
    ) -> None:
        """Record a profile view interaction.

        Updates creator interaction metrics when a user views a profile.

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
        
        MERGE (viewer)-[r:CREATOR_INTERACTION]->(creator)
        ON CREATE SET
            r.profile_view_count = 1,
            r.total_view_duration_ms = 0,
            r.video_count = 0,
            r.completion_rate_sum = 0,
            r.completion_rate_avg = 0,
            r.created_at = $current_time,
            r.updated_at = $current_time
        ON MATCH SET
            r.profile_view_count = r.profile_view_count + 1,
            r.updated_at = $current_time
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

    def record_profile_view(self, viewer_id: UUID4, creator_id: UUID4) -> None:
        """Record a profile view.

        Public method that handles the database session for recording
        profile view interactions.

        Args:
            viewer_id: ID of the user viewing the profile
            creator_id: ID of the creator being viewed

        Raises:
            ValueError: If recording fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.execute_write(self._record_profile_view, viewer_id, creator_id)

    def calculate_haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        unit: DistanceUnit = DistanceUnit.MILES,
    ) -> float:
        """Calculate the great circle distance between two points on Earth.

        Uses the Haversine formula to compute the distance between two
        latitude/longitude points in the specified unit.

        Args:
            lat1: Latitude of first point in degrees
            lon1: Longitude of first point in degrees
            lat2: Latitude of second point in degrees
            lon2: Longitude of second point in degrees
            unit: Unit to return distance in (miles or kilometers)

        Returns:
            Distance between points in specified unit
        """
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))

        # Calculate distance in requested unit
        if unit == DistanceUnit.MILES:
            return c * self.EARTH_RADIUS_MI
        return c * self.EARTH_RADIUS_KM

    def _calculate_location_score(
        self,
        distance: float,
        max_distance: float = 50.0,  # Default 50 miles
        unit: DistanceUnit = DistanceUnit.MILES,
    ) -> float:
        """Calculate a normalized location score based on distance.

        Converts distance into a similarity score between 0 and 1,
        where closer distances result in higher scores.

        Args:
            distance: Distance between users in specified unit
            max_distance: Maximum distance to consider for scoring
            unit: Unit of distance measurement (miles or kilometers)

        Returns:
            Location similarity score between 0 and 1
        """
        if distance > max_distance:
            return 0.0
        # Inverse linear relationship - closer means higher score
        return 1.0 - (distance / max_distance)

    def _calculate_user_similarity(
        self,
        tx: ManagedTransaction,
        user_id_a: UUID4,
        user_id_b: UUID4,
        max_distance: float | None = 50.0,  # Default 50 miles
        unit: DistanceUnit = DistanceUnit.MILES,
    ) -> UserSimilarityScore:
        """Calculate similarity scores between two users.

        Uses Graph Data Science algorithms to analyze:
        1. Node embeddings from FastRP
        2. Node similarity based on interaction patterns
        3. Path-based similarity metrics
        4. Location proximity when available

        Args:
            tx: The database transaction
            user_id_a: First user's ID
            user_id_b: Second user's ID
            max_distance: Maximum distance filter for dating matches
            unit: Unit for distance calculations (miles or kilometers)

        Returns:
            UserSimilarityScore containing various similarity metrics

        Raises:
            ValueError: If calculation fails or users are too far apart
        """
        # Convert max_distance to kilometers for Neo4j calculation
        max_distance_km = (
            (
                max_distance * self.MI_TO_KM
                if unit == DistanceUnit.MILES
                else max_distance
            )
            if max_distance is not None
            else None
        )

        query = """
        MATCH (user_a:User {user_id: $user_id_a})
        MATCH (user_b:User {user_id: $user_id_b})
        WHERE user_a <> user_b

        // Calculate embedding similarity
        WITH user_a, user_b,
             gds.similarity.cosine(user_a.embedding, user_b.embedding) AS embedding_sim

        // Get node similarity score
        OPTIONAL MATCH (user_a)-[sim:SIMILAR]-(user_b)
        WITH user_a, user_b, embedding_sim, sim.similarity AS node_sim

        // Calculate path-based similarity using shortest path
        WITH user_a, user_b, embedding_sim, node_sim,
             gds.alpha.shortestPath.stream({
                 sourceNode: id(user_a),
                 targetNode: id(user_b),
                 relationshipWeightProperty: 'weight'
             }) AS path_score

        // Calculate location similarity if available
        WITH user_a, user_b, embedding_sim, node_sim, path_score,
             CASE 
                WHEN user_a.latitude IS NOT NULL 
                     AND user_a.longitude IS NOT NULL
                     AND user_b.latitude IS NOT NULL
                     AND user_b.longitude IS NOT NULL
                THEN point.distance(
                    point({latitude: user_a.latitude, longitude: user_a.longitude}),
                    point({latitude: user_b.latitude, longitude: user_b.longitude})
                ) / 1000  // Convert meters to kilometers
                ELSE null
             END as distance_km

        // Apply distance filter if specified
        WHERE $max_distance_km IS NULL OR distance_km <= $max_distance_km

        // Calculate location score
        WITH user_a, user_b, embedding_sim, node_sim, path_score,
             CASE
                WHEN distance_km IS NOT NULL
                THEN 1.0 - (distance_km / CASE 
                    WHEN $max_distance_km IS NOT NULL THEN $max_distance_km 
                    ELSE 100.0 END)
                ELSE 0.5  // Neutral score if location unknown
             END as location_sim

        // Calculate final scores
        RETURN {
            user_id: user_a.user_id,
            target_id: user_b.user_id,
            content_similarity: embedding_sim,
            interaction_similarity: COALESCE(node_sim, 0.0),
            social_similarity: CASE 
                WHEN path_score IS NOT NULL 
                THEN 1.0 / (1.0 + path_score) 
                ELSE 0.0 
            END,
            location_similarity: location_sim,
            total_score: (
                embedding_sim * 0.3 +
                COALESCE(node_sim, 0.0) * 0.3 +
                CASE 
                    WHEN path_score IS NOT NULL 
                    THEN (1.0 / (1.0 + path_score)) * 0.2
                    ELSE 0.0 
                END +
                location_sim * 0.2
            )
        } as similarity
        """

        result = tx.run(
            query,
            user_id_a=str(user_id_a),
            user_id_b=str(user_id_b),
            max_distance_km=max_distance_km,
        )

        if record := result.single():
            similarity_data = record["similarity"]
            similarity_data["user_id"] = str(similarity_data["user_id"])
            similarity_data["target_id"] = str(similarity_data["target_id"])
            return UserSimilarityScore(**similarity_data)
        raise ValueError("Failed to calculate user similarity")

    def calculate_user_similarity(
        self,
        user_id_a: UUID4,
        user_id_b: UUID4,
        max_distance: float | None = 50.0,  # Default 50 miles
        unit: DistanceUnit = DistanceUnit.MILES,
    ) -> UserSimilarityScore:
        """Calculate similarity between two users.

        Public method that handles the database session for calculating
        user similarity scores. Includes location-based filtering for
        dating matches.

        Args:
            user_id_a: First user's ID
            user_id_b: Second user's ID
            max_distance: Maximum distance filter for dating matches
            unit: Unit for distance calculations (miles or kilometers)

        Returns:
            UserSimilarityScore containing various similarity metrics

        Raises:
            ValueError: If calculation fails or users are too far apart
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(
                self._calculate_user_similarity,
                user_id_a,
                user_id_b,
                max_distance,
                unit,
            )

    async def record_interaction(
        self,
        user_id: UUID4,
        target_id: UUID4,
        interaction_type: InteractionType,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a user interaction.

        Args:
            user_id: ID of the user performing the interaction
            target_id: ID of the content/user being interacted with
            interaction_type: Type of interaction
            metadata: Optional metadata about the interaction

        Raises:
            ValueError: If interaction recording fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.execute_write(
                self._create_interaction,
                user_id,
                target_id,
                interaction_type,
                metadata or {},
            )

    def _create_interaction(
        self,
        tx: ManagedTransaction,
        user_id: UUID4,
        target_id: UUID4,
        interaction_type: InteractionType,
        metadata: dict[str, Any],
    ) -> None:
        """Create an interaction record in the database.

        Args:
            tx: The database transaction
            user_id: ID of the user performing the interaction
            target_id: ID of the content/user being interacted with
            interaction_type: Type of interaction
            metadata: Metadata about the interaction

        Raises:
            ValueError: If interaction creation fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (target:User {user_id: $target_id})
        CREATE (user)-[r:INTERACTED {
            type: $interaction_type,
            created_at: $current_datetime,
            metadata: $metadata
        }]->(target)
        RETURN { success: true } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            target_id=str(target_id),
            interaction_type=interaction_type.value,
            current_datetime=datetime.now(UTC),
            metadata=metadata,
        )
        if not result.single():
            raise ValueError("Failed to record interaction")

    async def get_user_similarity(
        self, user_id: UUID4, target_id: UUID4
    ) -> UserSimilarityScore:
        """Calculate similarity score between two users.

        This method considers:
        1. Content similarity (what they interact with)
        2. Interaction similarity (how they interact)
        3. Social similarity (mutual connections)

        Args:
            user_id: ID of the first user
            target_id: ID of the second user

        Returns:
            Similarity score between the users

        Raises:
            ValueError: If similarity calculation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._calculate_similarity, user_id, target_id)

    def _calculate_similarity(
        self, tx: ManagedTransaction, user_id: UUID4, target_id: UUID4
    ) -> UserSimilarityScore:
        """Calculate similarity score between two users in the database.

        Args:
            tx: The database transaction
            user_id: ID of the first user
            target_id: ID of the second user

        Returns:
            Similarity score between the users

        Raises:
            ValueError: If similarity calculation fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (target:User {user_id: $target_id})

        // Calculate content similarity
        OPTIONAL MATCH (user)-[r1:INTERACTED]->(content)<-[r2:INTERACTED]-(target)
        WHERE content:Post OR content:Comment
        WITH user, target,
             CASE WHEN count(content) > 0
                  THEN toFloat(count(content)) / sqrt(
                       toFloat(size((user)-[:INTERACTED]->(:Post|:Comment))) *
                       toFloat(size((target)-[:INTERACTED]->(:Post|:Comment)))
                  )
                  ELSE 0.0
             END as content_similarity

        // Calculate interaction similarity
        OPTIONAL MATCH (user)-[r3:INTERACTED]->(shared_target)<-[r4:INTERACTED]-(target)
        WHERE r3.type = r4.type
        WITH user, target, content_similarity,
             CASE WHEN count(shared_target) > 0
                  THEN toFloat(count(shared_target)) / sqrt(
                       toFloat(size((user)-[:INTERACTED]->(:User))) *
                       toFloat(size((target)-[:INTERACTED]->(:User)))
                  )
                  ELSE 0.0
             END as interaction_similarity

        // Calculate social similarity (mutual connections)
        OPTIONAL MATCH (user)-[:FOLLOWS]->(mutual:User)<-[:FOLLOWS]-(target)
        WITH user, target, content_similarity, interaction_similarity,
             CASE WHEN count(mutual) > 0
                  THEN toFloat(count(mutual)) / sqrt(
                       toFloat(size((user)-[:FOLLOWS]->(:User))) *
                       toFloat(size((target)-[:FOLLOWS]->(:User)))
                  )
                  ELSE 0.0
             END as social_similarity

        // Calculate total score with weights
        WITH user, target,
             content_similarity,
             interaction_similarity,
             social_similarity,
             (content_similarity * 0.4 +
              interaction_similarity * 0.3 +
              social_similarity * 0.3) as total_score

        RETURN {
            user_id: user.user_id,
            target_id: target.user_id,
            content_similarity: content_similarity,
            interaction_similarity: interaction_similarity,
            social_similarity: social_similarity,
            total_score: total_score
        } as similarity
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            target_id=str(target_id),
        )
        if record := result.single():
            similarity_data = record["similarity"]
            similarity_data["user_id"] = str(similarity_data["user_id"])
            similarity_data["target_id"] = str(similarity_data["target_id"])
            return UserSimilarityScore(**similarity_data)
        raise ValueError("Failed to calculate user similarity")
