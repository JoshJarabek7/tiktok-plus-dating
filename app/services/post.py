from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import UploadFile
from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.post import Post, PostCreate, PostUpdate
from app.services.interaction import InteractionService
from app.utils.storage import Storage


class PostService:
    """Service for managing video posts.

    This service handles creating, updating, deleting, and retrieving posts,
    including file storage and database operations.
    """

    def __init__(self) -> None:
        """Initialize the post service with required dependencies."""
        self.storage = Storage()
        self.interaction_service = InteractionService()
        self._setup_gds()

    def _setup_gds(self) -> None:
        """Set up Graph Data Science projections and algorithms.

        Creates node projections for content recommendations and configures
        necessary algorithms.
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            # Create graph projection for content recommendations
            session.run("""
                CALL gds.graph.project.cypher(
                    'content-graph',
                    'MATCH (n) WHERE n:User OR n:Post OR n:Comment 
                     RETURN id(n) AS id, labels(n) AS labels',
                    'MATCH (s)-[r:INTERACTED_WITH|POSTED|COMMENTED]-(t)
                     RETURN id(s) AS source, id(t) AS target, type(r) AS type,
                     CASE type(r)
                        WHEN "INTERACTED_WITH" THEN r.completion_rate * 
                            CASE WHEN r.unregretted THEN 1.5 ELSE 1.0 END
                        WHEN "POSTED" THEN 0.8
                        WHEN "COMMENTED" THEN 0.6
                     END AS weight'
                )
            """)

            # Configure FastRP for embeddings
            session.run("""
                CALL gds.fastRP.write(
                    'content-graph',
                    {
                        embeddingDimension: 256,
                        iterationWeights: [0.8, 1.0, 1.0],
                        relationshipWeightProperty: 'weight',
                        writeProperty: 'embedding'
                    }
                )
            """)

            # Create node similarity graph
            session.run("""
                CALL gds.nodeSimilarity.write(
                    'content-graph',
                    {
                        writeRelationshipType: 'SIMILAR',
                        writeProperty: 'similarity',
                        similarityCutoff: 0.1
                    }
                )
            """)

    async def create_post(self, post: PostCreate, video: UploadFile) -> Post:
        """Create a new video post.

        This method:
        1. Uploads the video file to S3
        2. Generates a thumbnail
        3. Creates the post record in the database

        Args:
            post: The post metadata
            video: The video file to upload

        Returns:
            The created post

        Raises:
            ValueError: If post creation fails
        """
        # Convert to BytesIO for storage
        video_data = BytesIO(await video.read())

        # Upload video to S3
        video_id = await self.storage.upload(video_data)

        # TODO: Generate thumbnail
        thumbnail_id = uuid4()  # Placeholder until thumbnail generation is implemented

        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_post_record,
                post=post,
                video_id=video_id,
                thumbnail_id=thumbnail_id,
            )

    def _create_post_record(
        self,
        tx: ManagedTransaction,
        post: PostCreate,
        video_id: UUID4,
        thumbnail_id: UUID4,
    ) -> Post:
        """Create a post record in the database.

        Args:
            tx: The database transaction
            post: The post metadata
            video_id: ID of the uploaded video file
            thumbnail_id: ID of the generated thumbnail

        Returns:
            The created post

        Raises:
            ValueError: If database operation fails
        """
        query = """
        MATCH (creator:User {user_id: $creator_id})
        CREATE (post:Post {
            post_id: $post_id,
            creator_id: $creator_id,
            title: $title,
            description: $description,
            video_s3_key: $video_s3_key,
            thumbnail_s3_key: $thumbnail_s3_key,
            duration_seconds: $duration_seconds,
            created_at: $current_datetime,
            view_count: 0,
            like_count: 0,
            comment_count: 0,
            share_count: 0,
            hashtags: $hashtags,
            is_private: $is_private,
            allows_comments: $allows_comments
        })
        CREATE (creator)-[r:POSTED {created_at: $current_datetime}]->(post)
        RETURN post
        """
        current_time = datetime.now(UTC)
        result = tx.run(
            query,
            post_id=str(uuid4()),
            creator_id=str(post.creator_id),
            title=post.title,
            description=post.description,
            video_s3_key=str(video_id),
            thumbnail_s3_key=str(thumbnail_id),
            duration_seconds=0.0,  # TODO: Extract actual duration
            current_datetime=current_time,
            hashtags=post.hashtags,
            is_private=post.is_private,
            allows_comments=post.allows_comments,
        )
        if record := result.single():
            return Post(**record["post"])
        raise ValueError("Failed to create post")

    async def get_post(self, post_id: UUID4) -> Post:
        """Get a post by ID.

        Args:
            post_id: ID of the post to get

        Returns:
            The requested post

        Raises:
            ValueError: If post not found
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._get_post, post_id)

    def _get_post(self, tx: ManagedTransaction, post_id: UUID4) -> Post:
        """Get a post from the database.

        Args:
            tx: The database transaction
            post_id: ID of the post to get

        Returns:
            The requested post

        Raises:
            ValueError: If post not found
        """
        query = """
        MATCH (post:Post {post_id: $post_id})
        RETURN post
        """
        result = tx.run(query, post_id=str(post_id))
        if record := result.single():
            return Post(**record["post"])
        raise ValueError("Post not found")

    async def update_post(self, post_id: UUID4, post: PostUpdate) -> Post:
        """Update a post.

        Args:
            post_id: ID of the post to update
            post: The updated post data

        Returns:
            The updated post

        Raises:
            ValueError: If update fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(self._update_post, post_id, post)

    def _update_post(
        self, tx: ManagedTransaction, post_id: UUID4, post: PostUpdate
    ) -> Post:
        """Update a post in the database.

        Args:
            tx: The database transaction
            post_id: ID of the post to update
            post: The updated post data

        Returns:
            The updated post

        Raises:
            ValueError: If update fails
        """
        query = """
        MATCH (post:Post {post_id: $post_id})
        SET post += {
            title: $title,
            description: $description,
            hashtags: $hashtags,
            is_private: $is_private,
            allows_comments: $allows_comments
        }
        RETURN post
        """
        result = tx.run(
            query,
            post_id=str(post_id),
            title=post.title,
            description=post.description,
            hashtags=post.hashtags,
            is_private=post.is_private,
            allows_comments=post.allows_comments,
        )
        if record := result.single():
            return Post(**record["post"])
        raise ValueError("Post not found")

    async def delete_post(self, post_id: UUID4) -> None:
        """Delete a post.

        This method:
        1. Deletes the post record from the database
        2. Deletes associated files from S3

        Args:
            post_id: ID of the post to delete

        Raises:
            ValueError: If deletion fails
        """
        # Get post to get file keys
        post = await self.get_post(post_id)

        # Delete from database
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.execute_write(self._delete_post, post_id)

        # Delete files from S3
        await self.storage.delete(UUID(post.video_s3_key))
        await self.storage.delete(UUID(post.thumbnail_s3_key))

    def _delete_post(self, tx: ManagedTransaction, post_id: UUID4) -> None:
        """Delete a post from the database.

        Args:
            tx: The database transaction
            post_id: ID of the post to delete

        Raises:
            ValueError: If deletion fails
        """
        query = """
        MATCH (post:Post {post_id: $post_id})
        OPTIONAL MATCH (post)-[r]-()
        DELETE r, post
        """
        result = tx.run(query, post_id=str(post_id))
        if not result.consume().counters.nodes_deleted:
            raise ValueError("Post not found")

    async def get_feed(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[Post]:
        """Get a user's personalized feed.

        This method uses the recommendation system to provide a personalized feed
        based on:
        1. User's interaction history
        2. Content similarity
        3. Creator similarity
        4. Following relationships
        5. Recent engagement

        Args:
            user_id: ID of the user requesting the feed
            limit: Maximum number of posts to return
            offset: Number of posts to skip

        Returns:
            List of posts for the user's feed

        Raises:
            ValueError: If feed generation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._get_feed, user_id, limit, offset)

    def _get_feed(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[Post]:
        """Get posts for a user's feed from the database.

        Uses Graph Data Science algorithms for personalized recommendations:
        1. Node embeddings from FastRP
        2. Node similarity based on interaction patterns
        3. Path-based similarity metrics
        4. Time decay and engagement metrics

        Args:
            tx: The database transaction
            user_id: ID of the user requesting the feed
            limit: Maximum number of posts to return
            offset: Number of posts to skip

        Returns:
            List of posts for the user's feed

        Raises:
            ValueError: If feed generation fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        
        // Find potential posts using embeddings and privacy filter
        MATCH (post:Post)
        WHERE NOT post.is_private OR (user)-[:FOLLOWS]->(:User)-[:POSTED]->(post)
        
        // Calculate embedding similarity
        WITH user, post,
             gds.similarity.cosine(user.embedding, post.embedding) AS embedding_sim
        
        // Get node similarity score
        OPTIONAL MATCH (user)-[sim:SIMILAR]-(post)
        WITH user, post, embedding_sim, sim.similarity AS node_sim
        
        // Get creator similarity
        MATCH (creator:User)-[:POSTED]->(post)
        OPTIONAL MATCH (user)-[sim2:SIMILAR]-(creator)
        WITH user, post, embedding_sim, node_sim, sim2.similarity AS creator_sim
        
        // Calculate time decay (half-life of 24 hours)
        WITH user, post, embedding_sim, node_sim, creator_sim,
             exp(ln(0.5) * duration.between(datetime(post.created_at), datetime($current_time)).hours / 24.0) as time_decay
        
        // Calculate engagement score
        WITH user, post, embedding_sim, node_sim, creator_sim, time_decay,
             (
                 post.like_count * 0.4 +
                 post.comment_count * 0.3 +
                 post.share_count * 0.3
             ) / (1 + post.view_count) as engagement_score
        
        // Calculate final score
        WITH post,
             (
                 COALESCE(embedding_sim, 0.0) * 0.3 +
                 COALESCE(node_sim, 0.0) * 0.2 +
                 COALESCE(creator_sim, 0.0) * 0.2 +
                 time_decay * 0.15 +
                 engagement_score * 0.15
             ) as score
        
        // Return posts ordered by score
        RETURN post
        ORDER BY score DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            current_time=datetime.now(UTC).isoformat(),
            offset=offset,
            limit=limit,
        )
        return [Post(**record["post"]) for record in result]

    async def get_user_posts(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[Post]:
        """Get a user's posts.

        Args:
            user_id: ID of the user whose posts to get
            limit: Maximum number of posts to return
            offset: Number of posts to skip

        Returns:
            List of the user's posts

        Raises:
            ValueError: If fetching posts fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._get_user_posts, user_id, limit, offset)

    def _get_user_posts(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[Post]:
        """Get a user's posts from the database.

        Args:
            tx: The database transaction
            user_id: ID of the user whose posts to get
            limit: Maximum number of posts to return
            offset: Number of posts to skip

        Returns:
            List of the user's posts

        Raises:
            ValueError: If fetching posts fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})-[:POSTED]->(post:Post)
        RETURN post
        ORDER BY post.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [Post(**record["post"]) for record in result]

    async def search_posts(
        self, query: str, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[Post]:
        """Search for posts.

        This method uses both text matching and content similarity to find relevant posts.
        Results are ranked based on:
        1. Text match relevance
        2. Content similarity to user's interests
        3. Creator similarity
        4. Engagement metrics
        5. Recency

        Args:
            query: Search query string
            user_id: ID of the user performing the search
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            List of matching posts

        Raises:
            ValueError: If search fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(
                self._search_posts, query, user_id, limit, offset
            )

    def _search_posts(
        self,
        tx: ManagedTransaction,
        search_text: str,
        user_id: UUID4,
        limit: int,
        offset: int,
    ) -> list[Post]:
        """Search for posts in the database.

        Uses Graph Data Science algorithms for personalized search results:
        1. Text matching with relevance scoring
        2. Node embeddings for content similarity
        3. Node similarity for interaction patterns
        4. Engagement metrics and recency

        Args:
            tx: The database transaction
            search_text: Search query string
            user_id: ID of the user performing the search
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            List of matching posts ordered by relevance

        Raises:
            ValueError: If search fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        
        // Find posts matching search text with privacy filter
        MATCH (post:Post)
        WHERE (
            toLower(post.title) CONTAINS toLower($search_text) OR
             toLower(post.description) CONTAINS toLower($search_text) OR
            any(tag IN post.hashtags WHERE toLower(tag) CONTAINS toLower($search_text))
        )
        AND (NOT post.is_private OR (user)-[:FOLLOWS]->(:User)-[:POSTED]->(post))
        
        // Calculate text match score
        WITH user, post,
             CASE
                WHEN toLower(post.title) = toLower($search_text) THEN 1.0
                WHEN toLower(post.title) CONTAINS toLower($search_text) THEN 0.8
                WHEN toLower(post.description) CONTAINS toLower($search_text) THEN 0.6
                ELSE 0.4  // Hashtag match
             END as text_score
        
        // Calculate embedding similarity
        WITH user, post, text_score,
             gds.similarity.cosine(user.embedding, post.embedding) AS embedding_sim
        
        // Get node similarity score
        OPTIONAL MATCH (user)-[sim:SIMILAR]-(post)
        WITH user, post, text_score, embedding_sim, sim.similarity AS node_sim
        
        // Calculate time decay
        WITH user, post, text_score, embedding_sim, node_sim,
             exp(ln(0.5) * duration.between(datetime(post.created_at), datetime($current_time)).hours / 24.0) as time_decay
        
        // Calculate engagement score
        WITH post, text_score, embedding_sim, node_sim, time_decay,
             (
                 post.like_count * 0.4 +
                 post.comment_count * 0.3 +
                 post.share_count * 0.3
             ) / (1 + post.view_count) as engagement_score
        
        // Calculate final score
        WITH post,
             (
                 text_score * 0.35 +
                 COALESCE(embedding_sim, 0.0) * 0.25 +
                 COALESCE(node_sim, 0.0) * 0.2 +
                 time_decay * 0.1 +
                 engagement_score * 0.1
             ) as score
        
        // Return posts ordered by score
        RETURN post
        ORDER BY score DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            search_text=search_text,
            current_time=datetime.now(UTC).isoformat(),
            offset=offset,
            limit=limit,
        )
        return [Post(**record["post"]) for record in result]
