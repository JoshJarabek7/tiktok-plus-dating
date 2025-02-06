import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.comment import Comment, CommentCreate, CommentUpdate


class CommentError(Exception):
    """Base exception for comment-related errors."""

    pass


class CommentNotFoundError(CommentError):
    """Exception raised when a comment is not found."""

    pass


class CommentCreationError(CommentError):
    """Exception raised when comment creation fails."""

    pass


class CommentUpdateError(CommentError):
    """Exception raised when comment update fails."""

    pass


class CommentDeletionError(CommentError):
    """Exception raised when comment deletion fails."""

    pass


class CommentService:
    """Service for managing comments on posts.

    This service handles creating, retrieving, and managing comments,
    including handling mentions and replies.
    """

    def _username_is_real(self, tx: ManagedTransaction, username: str) -> UUID4 | None:
        """Check if a username exists in the database.

        Args:
            tx: The database transaction
            username: The username to check

        Returns:
            The user's ID if the username exists, None otherwise
        """
        query = """
        MATCH (user:User {username: $username})
        RETURN user.user_id as user_id
        """
        result = tx.run(query, username=username)
        if record := result.single():
            user_id = record["user_id"]
            if isinstance(user_id, str):
                return UUID(user_id)
            return UUID(str(user_id))
        return None

    def _extract_mentions(self, content: str) -> list[UUID4]:
        """Extract mentioned usernames from comment content.

        Args:
            content: The comment content to extract mentions from

        Returns:
            List of user IDs that were mentioned
        """
        mention_pattern = r"@(\w+)"
        potential_mentions = re.findall(mention_pattern, content)
        if not potential_mentions:
            return []

        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            query = """
            UNWIND $usernames as username
            MATCH (user:User {username: username})
            RETURN user.user_id as user_id
            """
            result = session.run(query, usernames=potential_mentions)
            valid_user_ids = [record["user_id"] for record in result]
        return valid_user_ids

    async def create_comment(self, post_id: UUID4, comment: CommentCreate) -> Comment:
        """Create a new comment on a post.

        Args:
            post_id: ID of the post to comment on
            comment: The comment data to create

        Returns:
            The created comment

        Raises:
            CommentCreationError: If comment creation fails
        """
        try:
            mentioned_user_ids = self._extract_mentions(comment.content)
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_write(
                    self._create_comment, post_id, comment, mentioned_user_ids
                )
        except Exception as e:
            raise CommentCreationError(f"Failed to create comment: {str(e)}")

    def _create_comment(
        self,
        tx: ManagedTransaction,
        post_id: UUID4,
        comment: CommentCreate,
        mentioned_user_ids: list[UUID4],
    ) -> Comment:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $post_id})
        CREATE (comment:Comment {
            comment_id: $comment_id,
            user_id: $user_id,
            post_id: $post_id,
            content: $content,
            created_at: $current_time,
            updated_at: $current_time,
            like_count: 0,
            reply_count: 0
        })
        CREATE (user)-[:AUTHORED]->(comment)
        CREATE (comment)-[:ON_POST]->(post)
        SET post.comment_count = coalesce(post.comment_count, 0) + 1
        FOREACH (mentioned_id IN $mentioned_user_ids |
            MATCH (mentioned_user:User {user_id: mentioned_id})
            CREATE (comment)-[:MENTIONS {created_at: $current_time}]->(mentioned_user)
        )
        RETURN comment
        """
        current_time = datetime.now(UTC)
        result = tx.run(
            query,
            comment_id=str(uuid4()),
            user_id=str(comment.creator_id),
            post_id=str(post_id),
            content=comment.content,
            current_time=current_time,
            mentioned_user_ids=[str(uid) for uid in mentioned_user_ids],
        )
        if record := result.single():
            return Comment(**record["comment"])
        raise CommentCreationError("Failed to create comment")

    async def get_comment(self, comment_id: UUID4) -> Comment:
        """Get a comment by ID.

        Args:
            comment_id: ID of the comment to get

        Returns:
            The requested comment

        Raises:
            CommentNotFoundError: If comment not found
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(self._get_comment, comment_id)
            except Exception as e:
                raise CommentNotFoundError(f"Comment not found: {str(e)}")

    def _get_comment(self, tx: ManagedTransaction, comment_id: UUID4) -> Comment:
        query = """
        MATCH (comment:Comment {comment_id: $comment_id})
        RETURN comment
        """
        result = tx.run(query, comment_id=str(comment_id))
        if record := result.single():
            return Comment(**record["comment"])
        raise CommentNotFoundError(f"Comment {comment_id} not found")

    async def update_comment(self, comment_id: UUID4, update: CommentUpdate) -> Comment:
        """Update a comment.

        Args:
            comment_id: ID of the comment to update
            update: The update data

        Returns:
            The updated comment

        Raises:
            CommentNotFoundError: If comment not found
            CommentUpdateError: If update fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_write(self._update_comment, comment_id, update)
        except CommentNotFoundError:
            raise
        except Exception as e:
            raise CommentUpdateError(f"Failed to update comment: {str(e)}")

    def _update_comment(
        self, tx: ManagedTransaction, comment_id: UUID4, update: CommentUpdate
    ) -> Comment:
        query = """
        MATCH (comment:Comment {comment_id: $comment_id})
        SET comment.content = $content,
            comment.updated_at = $current_time
        RETURN comment
        """
        current_time = datetime.now(UTC)
        result = tx.run(
            query,
            comment_id=str(comment_id),
            content=update.content,
            current_time=current_time,
        )
        if record := result.single():
            return Comment(**record["comment"])
        raise CommentNotFoundError(f"Comment {comment_id} not found")

    async def delete_comment(self, comment_id: UUID4) -> None:
        """Delete a comment.

        Args:
            comment_id: ID of the comment to delete

        Raises:
            CommentNotFoundError: If comment not found
            CommentDeletionError: If deletion fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                session.execute_write(self._delete_comment, comment_id)
        except CommentNotFoundError:
            raise
        except Exception as e:
            raise CommentDeletionError(f"Failed to delete comment: {str(e)}")

    def _delete_comment(self, tx: ManagedTransaction, comment_id: UUID4) -> None:
        query = """
        MATCH (comment:Comment {comment_id: $comment_id})
        OPTIONAL MATCH (comment)-[r]-()
        WITH comment, collect(r) as rels
        FOREACH (rel in rels | DELETE rel)
        DELETE comment
        """
        result = tx.run(query, comment_id=str(comment_id))
        if not result.consume().counters.nodes_deleted:
            raise CommentNotFoundError(f"Comment {comment_id} not found")

    async def get_post_comments(
        self, post_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[Comment]:
        """Get comments on a post.

        Args:
            post_id: ID of the post
            limit: Maximum number of comments to return
            offset: Number of comments to skip

        Returns:
            List of comments on the post

        Raises:
            CommentError: If fetching comments fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_read(
                    self._get_post_comments, post_id, limit, offset
                )
        except Exception as e:
            raise CommentError(f"Failed to get post comments: {str(e)}")

    def _get_post_comments(
        self, tx: ManagedTransaction, post_id: UUID4, limit: int, offset: int
    ) -> list[Comment]:
        query = """
        MATCH (comment:Comment)-[:ON_POST]->(post:Post {post_id: $post_id})
        RETURN comment
        ORDER BY comment.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            post_id=str(post_id),
            offset=offset,
            limit=limit,
        )
        return [Comment(**record["comment"]) for record in result]

    async def get_user_comments(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[Comment]:
        """Get comments by a user.

        Args:
            user_id: ID of the user
            limit: Maximum number of comments to return
            offset: Number of comments to skip

        Returns:
            List of the user's comments

        Raises:
            CommentError: If fetching comments fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_read(
                    self._get_user_comments, user_id, limit, offset
                )
        except Exception as e:
            raise CommentError(f"Failed to get user comments: {str(e)}")

    def _get_user_comments(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[Comment]:
        query = """
        MATCH (user:User {user_id: $user_id})-[:AUTHORED]->(comment:Comment)
        RETURN comment
        ORDER BY comment.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [Comment(**record["comment"]) for record in result]
