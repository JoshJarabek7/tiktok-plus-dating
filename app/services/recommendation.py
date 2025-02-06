from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.user import User


class RecommendationService:
    """Service for generating personalized recommendations.

    This service handles:
    - User suggestions (who to follow)
    - Content recommendations
    - Creator recommendations
    - Interest-based matching
    """

    def __init__(self) -> None:
        """Initialize the recommendation service.

        Sets up the Graph Data Science library and creates necessary projections.
        """
        self._setup_gds()

    def _setup_gds(self) -> None:
        """Set up Graph Data Science projections and algorithms.

        Creates node projections for users, posts and relationships,
        and configures FastRP for recommendations.
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            # Create graph projection for recommendations
            session.run("""
                CALL gds.graph.project.cypher(
                    'recommendation-graph',
                    'MATCH (n) WHERE n:User OR n:Post RETURN id(n) AS id, labels(n) AS labels',
                    'MATCH (s)-[r:FOLLOWS|POSTED|INTERACTED_WITH]->(t) 
                     RETURN id(s) AS source, id(t) AS target, type(r) AS type, 
                     CASE type(r)
                        WHEN "FOLLOWS" THEN 1.0
                        WHEN "POSTED" THEN 0.5
                        WHEN "INTERACTED_WITH" THEN r.completion_rate
                     END AS weight'
                )
            """)

            # Configure FastRP for embeddings
            session.run("""
                CALL gds.fastRP.write(
                    'recommendation-graph',
                    {
                        embeddingDimension: 256,
                        iterationWeights: [0.8, 1.0, 1.0],
                        relationshipWeightProperty: 'weight',
                        writeProperty: 'embedding'
                    }
                )
            """)

    async def get_user_suggestions(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Get personalized user suggestions.

        Uses multiple signals to find relevant users:
        1. Content interaction overlap
        2. Creator preferences
        3. Mutual follows
        4. Hashtag interests
        5. Engagement patterns
        6. Location proximity (if available)

        Args:
            user_id: ID of the user to get suggestions for
            limit: Maximum number of suggestions to return
            offset: Number of suggestions to skip

        Returns:
            List of suggested users ordered by relevance

        Raises:
            ValueError: If suggestion generation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(
                self._get_user_suggestions, user_id, limit, offset
            )

    def _get_user_suggestions(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[User]:
        """Get user suggestions from the database using FastRP embeddings.

        Uses Graph Data Science with FastRP for high-quality recommendations:
        1. Node embeddings capture structural features
        2. Relationship weights reflect interaction strength
        3. Cosine similarity for user matching
        4. Additional filtering based on business rules

        Args:
            tx: The database transaction
            user_id: ID of the user to get suggestions for
            limit: Maximum number of suggestions to return
            offset: Number of suggestions to skip

        Returns:
            List of suggested users ordered by relevance

        Raises:
            ValueError: If suggestion generation fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        
        // Find potential users to suggest using FastRP embeddings
        MATCH (suggested:User)
        WHERE suggested <> user
        AND NOT (user)-[:FOLLOWS|BLOCKS]->(suggested)
        AND NOT (suggested)-[:BLOCKS]->(user)
        
        // Calculate similarity using embeddings
        WITH user, suggested,
             gds.similarity.cosine(user.embedding, suggested.embedding) AS similarity
        
        // Apply additional business rules
        OPTIONAL MATCH (user)-[:FOLLOWS]->(mutual:User)-[:FOLLOWS]->(suggested)
        OPTIONAL MATCH (user)-[int:INTERACTED_WITH]->(:Post)<-[:POSTED]-(suggested)
        
        WITH user, suggested, similarity,
             count(DISTINCT mutual) as mutual_count,
             count(DISTINCT int) as interaction_count,
             CASE 
                WHEN user.latitude IS NOT NULL 
                     AND user.longitude IS NOT NULL
                     AND suggested.latitude IS NOT NULL
                     AND suggested.longitude IS NOT NULL
                THEN point.distance(
                    point({latitude: user.latitude, longitude: user.longitude}),
                    point({latitude: suggested.latitude, longitude: suggested.longitude})
                ) * 0.000621371  // Convert meters to miles
                ELSE null
             END as distance_miles
        
        // Calculate final score combining multiple signals
        WITH suggested,
             (
                similarity * 0.4 +                    // Embedding similarity
                (mutual_count * 0.2) +               // Social proximity
                (interaction_count * 0.2) +          // Interaction history
                CASE 
                    WHEN distance_miles IS NOT NULL 
                    THEN (1 - COALESCE(distance_miles / 100, 0)) * 0.2  // Location (normalized to 100 miles)
                    ELSE 0 
                END
             ) as score
        
        // Return suggestions ordered by score
        RETURN suggested
        ORDER BY score DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [User(**record["suggested"]) for record in result]

    async def get_creator_suggestions(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Get personalized creator suggestions.

        Uses multiple signals to find relevant creators:
        1. Content preferences
        2. Viewing patterns
        3. Engagement history
        4. Topic interests
        5. Similar audience

        Args:
            user_id: ID of the user to get suggestions for
            limit: Maximum number of suggestions to return
            offset: Number of suggestions to skip

        Returns:
            List of suggested creators ordered by relevance

        Raises:
            ValueError: If suggestion generation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(
                self._get_creator_suggestions, user_id, limit, offset
            )

    def _get_creator_suggestions(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[User]:
        """Get creator suggestions using FastRP embeddings.

        Uses Graph Data Science for creator recommendations:
        1. Node embeddings capture content and audience patterns
        2. Weighted relationships for engagement strength
        3. Similarity calculation using embeddings
        4. Content-based filtering

        Args:
            tx: The database transaction
            user_id: ID of the user to get suggestions for
            limit: Maximum number of suggestions to return
            offset: Number of suggestions to skip

        Returns:
            List of suggested creators ordered by relevance

        Raises:
            ValueError: If suggestion generation fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        
        // Find potential creators using FastRP embeddings
        MATCH (creator:User)-[:POSTED]->(:Post)
        WHERE creator <> user
        AND NOT (user)-[:FOLLOWS|BLOCKS]->(creator)
        AND NOT (creator)-[:BLOCKS]->(user)
        
        // Calculate similarity using embeddings
        WITH user, creator,
             gds.similarity.cosine(user.embedding, creator.embedding) AS similarity
        
        // Get content interaction patterns
        OPTIONAL MATCH (user)-[int:INTERACTED_WITH]->(post:Post)<-[:POSTED]-(creator)
        WITH user, creator, similarity, collect(int) as interactions
        
        // Calculate engagement metrics
        WITH user, creator, similarity,
             CASE WHEN size(interactions) > 0
                  THEN avg(
                    [int in interactions | 
                     int.completion_rate * size(int.engagement_signals) *
                     CASE WHEN int.unregretted THEN 1.5 ELSE 1.0 END
                    ])
                  ELSE 0
             END as engagement_score
        
        // Get audience overlap
        OPTIONAL MATCH (viewer:User)-[:FOLLOWS]->(creator)
        WHERE (viewer)-[:FOLLOWS]->(user) OR (user)-[:FOLLOWS]->(viewer)
        
        // Calculate final score
        WITH creator,
             (
                similarity * 0.4 +                // Embedding similarity
                engagement_score * 0.3 +          // Content engagement
                count(DISTINCT viewer) * 0.3 / 
                CASE WHEN creator.follower_count > 0 
                     THEN creator.follower_count 
                     ELSE 1 
                END                              // Audience overlap (normalized)
             ) as score
        
        // Return suggestions ordered by score
        RETURN creator
        ORDER BY score DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [User(**record["creator"]) for record in result]
