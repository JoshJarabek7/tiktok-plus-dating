from datetime import UTC, datetime
from uuid import uuid4

from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.bookmark import Bookmark, BookmarkCreate
from app.models.post import Post


class BookmarkError(Exception):
    """Base exception for bookmark-related errors."""

    pass


class BookmarkNotFoundError(BookmarkError):
    """Exception raised when a bookmark is not found."""

    pass


class BookmarkService:
    """Service for managing bookmarks.

    This service handles creating and removing bookmarks,
    as well as querying bookmark status and bookmarked posts.
    """

    async def create_bookmark(
        self, post_id: UUID4, bookmark: BookmarkCreate
    ) -> Bookmark:
        """Create a new bookmark.

        Args:
            post_id: ID of the post to bookmark
            bookmark: The bookmark data

        Returns:
            The created bookmark

        Raises:
            BookmarkError: If bookmark creation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_write(self._create_bookmark, post_id, bookmark)
            except Exception as e:
                raise BookmarkError(f"Failed to create bookmark: {str(e)}")

    def _create_bookmark(
        self, tx: ManagedTransaction, post_id: UUID4, bookmark: BookmarkCreate
    ) -> Bookmark:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $post_id})
        CREATE (b:Bookmark {
            bookmark_id: $bookmark_id,
            user_id: $user_id,
            post_id: $post_id,
            created_at: $current_time
        })
        CREATE (user)-[:BOOKMARKED]->(b)-[:BOOKMARKS]->(post)
        SET post.bookmark_count = coalesce(post.bookmark_count, 0) + 1
        RETURN b
        """
        current_time = datetime.now(UTC)
        result = tx.run(
            query,
            bookmark_id=str(uuid4()),
            user_id=str(bookmark.user_id),
            post_id=str(post_id),
            current_time=current_time,
        )
        if record := result.single():
            return Bookmark(**record["b"])
        raise BookmarkError("Failed to create bookmark")

    async def remove_bookmark(self, user_id: UUID4, post_id: UUID4) -> None:
        """Remove a bookmark.

        Args:
            user_id: ID of the user removing the bookmark
            post_id: ID of the post to unbookmark

        Raises:
            BookmarkNotFoundError: If bookmark not found
            BookmarkError: If removal fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                session.execute_write(self._remove_bookmark, user_id, post_id)
            except Exception as e:
                if "not found" in str(e).lower():
                    raise BookmarkNotFoundError(str(e))
                raise BookmarkError(f"Failed to remove bookmark: {str(e)}")

    def _remove_bookmark(
        self, tx: ManagedTransaction, user_id: UUID4, post_id: UUID4
    ) -> None:
        query = """
        MATCH (user:User {user_id: $user_id})-[:BOOKMARKED]->(b:Bookmark)-[:BOOKMARKS]->(post:Post {post_id: $post_id})
        OPTIONAL MATCH (b)-[r]-()
        DELETE r, b
        SET post.bookmark_count = post.bookmark_count - 1
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            post_id=str(post_id),
        )
        if not result.consume().counters.nodes_deleted:
            raise BookmarkNotFoundError("Bookmark not found")

    async def is_bookmarked(self, user_id: UUID4, post_id: UUID4) -> bool:
        """Check if a post is bookmarked.

        Args:
            user_id: ID of the user to check for
            post_id: ID of the post to check

        Returns:
            True if the post is bookmarked, False otherwise

        Raises:
            BookmarkError: If check fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(self._check_bookmark, user_id, post_id)
            except Exception as e:
                raise BookmarkError(f"Failed to check bookmark status: {str(e)}")

    def _check_bookmark(
        self, tx: ManagedTransaction, user_id: UUID4, post_id: UUID4
    ) -> bool:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $post_id})
        RETURN exists((user)-[:BOOKMARKED]->(:Bookmark)-[:BOOKMARKS]->(post)) as is_bookmarked
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            post_id=str(post_id),
        )
        if record := result.single():
            return record["is_bookmarked"]
        return False

    async def get_bookmarked_posts(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[Post]:
        """Get posts bookmarked by a user.

        Args:
            user_id: ID of the user
            limit: Maximum number of posts to return
            offset: Number of posts to skip

        Returns:
            List of bookmarked posts

        Raises:
            BookmarkError: If fetching fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(
                    self._get_bookmarked_posts, user_id, limit, offset
                )
            except Exception as e:
                raise BookmarkError(f"Failed to get bookmarked posts: {str(e)}")

    def _get_bookmarked_posts(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[Post]:
        query = """
        MATCH (user:User {user_id: $user_id})-[:BOOKMARKED]->(b:Bookmark)-[:BOOKMARKS]->(p:Post)
        RETURN p
        ORDER BY b.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [Post(**record["p"]) for record in result]
