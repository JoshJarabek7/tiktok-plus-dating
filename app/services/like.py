from datetime import UTC, datetime

from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.like import ContentType, Like
from app.models.user import User


class LikeService:
    """Service for managing likes on posts and comments.

    This service handles creating and removing likes, as well as
    querying like status and liked content.
    """

    async def like_post(
        self, user_id: UUID4, post_id: UUID4, content_type: ContentType
    ) -> Like:
        """Like a post.

        Args:
            user_id: ID of the user liking the post
            post_id: ID of the post to like
            content_type: Type of content being liked

        Returns:
            The created like

        Raises:
            ValueError: If like creation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_post_like, post_id, user_id, content_type
            )

    def _create_post_like(
        self,
        tx: ManagedTransaction,
        post_id: UUID4,
        user_id: UUID4,
        content_type: ContentType,
    ) -> Like:
        """Create a like in the database.

        Args:
            tx: The database transaction
            post_id: ID of the post to like
            user_id: ID of the user liking the post
            content_type: Type of content being liked

        Returns:
            The created like

        Raises:
            ValueError: If like creation fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $post_id})
        WHERE user IS NOT NULL AND post IS NOT NULL
        MERGE (user)-[r:LIKED]->(post)
        ON CREATE
            SET r.created_at = $current_datetime,
                post.like_count = coalesce(post.like_count, 0) + 1
        WITH user, post, r
        RETURN {
            user_id: user.user_id,
            content_id: post.post_id,
            content_type: $content_type,
            created_at: r.created_at
        } as like
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            post_id=str(post_id),
            content_type=content_type.value,
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return Like(**record["like"])

        # Check why the like failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $post_id})
        RETURN {
            user_exists: user IS NOT NULL,
            post_exists: post IS NOT NULL
        } as status
        """
        status = tx.run(check_query, user_id=str(user_id), post_id=str(post_id))
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["post_exists"]:
                raise ValueError("Post not found")
        raise ValueError("Something went wrong while liking the post")

    async def unlike_post(self, user_id: UUID4, post_id: UUID4) -> None:
        """Unlike a post.

        Args:
            user_id: ID of the user unliking the post
            post_id: ID of the post to unlike

        Raises:
            ValueError: If unlike fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.execute_write(self._remove_post_like, post_id, user_id)

    def _remove_post_like(
        self, tx: ManagedTransaction, post_id: UUID4, user_id: UUID4
    ) -> None:
        """Remove a like from the database.

        Args:
            tx: The database transaction
            post_id: ID of the post to unlike
            user_id: ID of the user unliking the post

        Raises:
            ValueError: If unlike fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $post_id})
        OPTIONAL MATCH (user)-[r:LIKED]->(post)
        WITH user, post, r, r IS NOT NULL as like_exists
        WHERE like_exists
        DELETE r
        SET post.like_count = post.like_count - 1
        RETURN { success: true } as result
        """
        result = tx.run(query, post_id=str(post_id), user_id=str(user_id))
        if not result.single():
            # Check why the unlike failed
            check_query = """
            MATCH (user:User {user_id: $user_id})
            MATCH (post:Post {post_id: $post_id})
            OPTIONAL MATCH (user)-[r:LIKED]->(post)
            RETURN {
                user_exists: user IS NOT NULL,
                post_exists: post IS NOT NULL,
                like_exists: r IS NOT NULL
            } as status
            """
            status = tx.run(check_query, user_id=str(user_id), post_id=str(post_id))
            if status_data := status.single():
                status = status_data["status"]
                if not status["user_exists"]:
                    raise ValueError("User not found")
                elif not status["post_exists"]:
                    raise ValueError("Post not found")
                elif not status["like_exists"]:
                    raise ValueError("You haven't liked this post")
            raise ValueError("Something went wrong removing your post like")

    async def get_post_likers(
        self, post_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Get users who liked a post.

        Args:
            post_id: ID of the post
            limit: Maximum number of users to return
            offset: Number of users to skip

        Returns:
            List of users who liked the post

        Raises:
            ValueError: If fetching likers fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._get_post_likers, post_id, limit, offset)

    def _get_post_likers(
        self, tx: ManagedTransaction, post_id: UUID4, limit: int, offset: int
    ) -> list[User]:
        """Get users who liked a post from the database.

        Args:
            tx: The database transaction
            post_id: ID of the post
            limit: Maximum number of users to return
            offset: Number of users to skip

        Returns:
            List of users who liked the post

        Raises:
            ValueError: If fetching likers fails
        """
        query = """
        MATCH (user:User)-[:LIKED]->(post:Post {post_id: $post_id})
        RETURN user
        ORDER BY user.username
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            post_id=str(post_id),
            offset=offset,
            limit=limit,
        )
        return [User(**record["user"]) for record in result]

    async def get_user_likes(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[Like]:
        """Get posts liked by a user.

        Args:
            user_id: ID of the user
            limit: Maximum number of likes to return
            offset: Number of likes to skip

        Returns:
            List of the user's likes

        Raises:
            ValueError: If fetching likes fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_read(self._get_user_likes, user_id, limit, offset)

    def _get_user_likes(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[Like]:
        """Get a user's likes from the database.

        Args:
            tx: The database transaction
            user_id: ID of the user
            limit: Maximum number of likes to return
            offset: Number of likes to skip

        Returns:
            List of the user's likes

        Raises:
            ValueError: If fetching likes fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})-[r:LIKED]->(content)
        WHERE content:Post OR content:Comment
        RETURN {
            user_id: user.user_id,
            content_id: content.post_id,
            content_type: CASE WHEN content:Post THEN 'post' ELSE 'comment' END,
            created_at: r.created_at
        } as like
        ORDER BY r.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [Like(**record["like"]) for record in result]

    def _create_comment_like(
        self, tx: ManagedTransaction, comment_id: UUID4, user_id: UUID4
    ):
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (comment:Comment {comment_id: $comment_id})
        WHERE user IS NOT NULL AND comment IS NOT NULL
        MERGE (user)-[r:LIKED]->(comment)
        ON CREATE
            SET r.created_at = $current_datetime,
                comment.like_count = coalesce(comment.like_count, 0) + 1
        RETURN { success: true } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            comment_id=str(comment_id),
            current_datetime=datetime.now(UTC),
        )
        if not result.single():
            # Check why the like failed
            check_query = """
            MATCH (user:User {user_id: $user_id})
            MATCH (comment:Comment {comment_id: $comment_id})
            RETURN {
                user_exists: user IS NOT NULL,
                comment_exists: comment IS NOT NULL
            } as status
            """
            status = tx.run(
                check_query, user_id=str(user_id), comment_id=str(comment_id)
            )
            if status_data := status.single():
                status = status_data["status"]
                if not status["user_exists"]:
                    raise ValueError("User not found")
                elif not status["comment_exists"]:
                    raise ValueError("Comment not found")
            raise ValueError("Something went wrong while liking the comment")

    async def like_comment(self, comment_id: UUID4, user_id: UUID4) -> None:
        """Like a comment.

        Args:
            comment_id: ID of the comment to like
            user_id: ID of the user liking the comment

        Raises:
            ValueError: If like creation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.execute_write(self._create_comment_like, comment_id, user_id)

    def _remove_comment_like(
        self, tx: ManagedTransaction, comment_id: UUID4, user_id: UUID4
    ):
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (comment:Comment {comment_id: $comment_id})
        OPTIONAL MATCH (user)-[r:LIKED]->(comment)
        WITH user, comment, r, r IS NOT NULL as like_exists
        WHERE like_exists
        DELETE r
        SET comment.like_count = comment.like_count - 1
        RETURN { success: true } as result
        """
        result = tx.run(query, comment_id=str(comment_id), user_id=str(user_id))
        if not result.single():
            # Check why the unlike failed
            check_query = """
            MATCH (user:User {user_id: $user_id})
            MATCH (comment:Comment {comment_id: $comment_id})
            OPTIONAL MATCH (user)-[r:LIKED]->(comment)
            RETURN {
                user_exists: user IS NOT NULL,
                comment_exists: comment IS NOT NULL,
                like_exists: r IS NOT NULL
            } as status
            """
            status = tx.run(
                check_query, user_id=str(user_id), comment_id=str(comment_id)
            )
            if status_data := status.single():
                status = status_data["status"]
                if not status["user_exists"]:
                    raise ValueError("User not found")
                elif not status["comment_exists"]:
                    raise ValueError("Comment not found")
                elif not status["like_exists"]:
                    raise ValueError("You haven't liked this comment")
            raise ValueError("There was a problem removing your comment like")

    async def unlike_comment(self, comment_id: UUID4, user_id: UUID4) -> None:
        """Unlike a comment.

        Args:
            comment_id: ID of the comment to unlike
            user_id: ID of the user unliking the comment

        Raises:
            ValueError: If unlike fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            session.execute_write(self._remove_comment_like, comment_id, user_id)
