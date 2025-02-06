from datetime import UTC, datetime
from uuid import uuid4

from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.bookmark import Bookmark
from app.models.bookmark_collection import BookmarkCollection, BookmarkCollectionCreate


class CollectionError(Exception):
    """Base exception for collection-related errors."""

    pass


class CollectionNotFoundError(CollectionError):
    """Exception raised when a collection is not found."""

    pass


class CollectionUpdateError(CollectionError):
    """Exception raised when collection update fails."""

    pass


class CollectionService:
    """Service for managing bookmark collections.

    This service handles creating, updating, and deleting bookmark collections,
    as well as managing bookmarks within collections.
    """

    async def create(
        self, collection: BookmarkCollectionCreate, user_id: UUID4
    ) -> BookmarkCollection:
        """Create a new bookmark collection.

        Args:
            collection: The collection data to create
            user_id: ID of the user creating the collection

        Returns:
            The created collection

        Raises:
            CollectionError: If collection creation fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_write(
                    self._create_collection, collection, user_id
                )
            except Exception as e:
                raise CollectionError(f"Failed to create collection: {str(e)}")

    def _create_collection(
        self,
        tx: ManagedTransaction,
        collection: BookmarkCollectionCreate,
        user_id: UUID4,
    ) -> BookmarkCollection:
        query = """
        MATCH (user:User {user_id: $user_id})
        CREATE (c:BookmarkCollection {
            collection_id: $collection_id,
            title: $title,
            owned_by: $user_id,
            bookmark_count: 0,
            created_at: $current_time,
            updated_at: $current_time
        })
        CREATE (user)-[:OWNS]->(c)
        RETURN c
        """
        current_time = datetime.now(UTC)
        result = tx.run(
            query,
            collection_id=str(uuid4()),
            title=collection.title,
            user_id=str(user_id),
            current_time=current_time,
        )
        if record := result.single():
            return BookmarkCollection(**record["c"])
        raise CollectionError("Failed to create collection")

    async def get_collection(self, collection_id: UUID4) -> BookmarkCollection:
        """Get a bookmark collection by ID.

        Args:
            collection_id: ID of the collection to get

        Returns:
            The requested collection

        Raises:
            CollectionNotFoundError: If collection not found
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(self._get_collection, collection_id)
            except Exception as e:
                raise CollectionNotFoundError(f"Collection not found: {str(e)}")

    def _get_collection(
        self, tx: ManagedTransaction, collection_id: UUID4
    ) -> BookmarkCollection:
        query = """
        MATCH (c:BookmarkCollection {collection_id: $collection_id})
        RETURN c
        """
        result = tx.run(query, collection_id=str(collection_id))
        if record := result.single():
            return BookmarkCollection(**record["c"])
        raise CollectionNotFoundError("Collection not found")

    async def update_collection(
        self, collection_id: UUID4, collection: BookmarkCollection
    ) -> BookmarkCollection:
        """Update a bookmark collection.

        Args:
            collection_id: ID of the collection to update
            collection: The updated collection data

        Returns:
            The updated collection

        Raises:
            CollectionNotFoundError: If collection not found
            CollectionUpdateError: If update fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_write(
                    self._update_collection, collection_id, collection
                )
            except CollectionNotFoundError:
                raise
            except Exception as e:
                raise CollectionUpdateError(f"Failed to update collection: {str(e)}")

    def _update_collection(
        self,
        tx: ManagedTransaction,
        collection_id: UUID4,
        collection: BookmarkCollection,
    ) -> BookmarkCollection:
        query = """
        MATCH (c:BookmarkCollection {collection_id: $collection_id})
        SET c.title = $title,
            c.updated_at = $current_time
        RETURN c
        """
        result = tx.run(
            query,
            collection_id=str(collection_id),
            title=collection.title,
            current_time=datetime.now(UTC),
        )
        if record := result.single():
            return BookmarkCollection(**record["c"])
        raise CollectionNotFoundError("Collection not found")

    async def delete(self, collection_id: UUID4, user_id: UUID4) -> None:
        """Delete a bookmark collection.

        Args:
            collection_id: ID of the collection to delete
            user_id: ID of the user deleting the collection

        Raises:
            CollectionNotFoundError: If collection not found
            CollectionError: If deletion fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                session.execute_write(self._delete_collection, collection_id, user_id)
            except Exception as e:
                raise CollectionError(f"Failed to delete collection: {str(e)}")

    def _delete_collection(
        self, tx: ManagedTransaction, collection_id: UUID4, user_id: UUID4
    ) -> None:
        query = """
        MATCH (user:User {user_id: $user_id})-[owns:OWNS]->(c:BookmarkCollection {collection_id: $collection_id})
        OPTIONAL MATCH (c)-[r]-()
        DELETE r, c
        """
        result = tx.run(
            query,
            collection_id=str(collection_id),
            user_id=str(user_id),
        )
        if not result.consume().counters.nodes_deleted:
            raise CollectionNotFoundError("Collection not found")

    async def add_bookmark(self, collection_id: UUID4, bookmark_id: UUID4) -> None:
        """Add a bookmark to a collection.

        Args:
            collection_id: ID of the collection
            bookmark_id: ID of the bookmark to add

        Raises:
            CollectionNotFoundError: If collection not found
            CollectionError: If addition fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                session.execute_write(self._add_bookmark, collection_id, bookmark_id)
            except Exception as e:
                raise CollectionError(f"Failed to add bookmark: {str(e)}")

    def _add_bookmark(
        self, tx: ManagedTransaction, collection_id: UUID4, bookmark_id: UUID4
    ) -> None:
        query = """
        MATCH (c:BookmarkCollection {collection_id: $collection_id})
        MATCH (b:Bookmark {bookmark_id: $bookmark_id})
        MERGE (c)-[r:CONTAINS]->(b)
        SET c.bookmark_count = c.bookmark_count + 1,
            c.updated_at = $current_time
        """
        result = tx.run(
            query,
            collection_id=str(collection_id),
            bookmark_id=str(bookmark_id),
            current_time=datetime.now(UTC),
        )
        if not result.consume().counters.relationships_created:
            raise CollectionError("Failed to add bookmark")

    async def remove_bookmark(self, collection_id: UUID4, bookmark_id: UUID4) -> None:
        """Remove a bookmark from a collection.

        Args:
            collection_id: ID of the collection
            bookmark_id: ID of the bookmark to remove

        Raises:
            CollectionNotFoundError: If collection not found
            CollectionError: If removal fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                session.execute_write(self._remove_bookmark, collection_id, bookmark_id)
            except Exception as e:
                raise CollectionError(f"Failed to remove bookmark: {str(e)}")

    def _remove_bookmark(
        self, tx: ManagedTransaction, collection_id: UUID4, bookmark_id: UUID4
    ) -> None:
        query = """
        MATCH (c:BookmarkCollection {collection_id: $collection_id})-[r:CONTAINS]->(b:Bookmark {bookmark_id: $bookmark_id})
        DELETE r
        SET c.bookmark_count = c.bookmark_count - 1,
            c.updated_at = $current_time
        """
        result = tx.run(
            query,
            collection_id=str(collection_id),
            bookmark_id=str(bookmark_id),
            current_time=datetime.now(UTC),
        )
        if not result.consume().counters.relationships_deleted:
            raise CollectionError("Bookmark not found in collection")

    async def get_collection_bookmarks(
        self, collection_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[Bookmark]:
        """Get bookmarks in a collection.

        Args:
            collection_id: ID of the collection
            limit: Maximum number of bookmarks to return
            offset: Number of bookmarks to skip

        Returns:
            List of bookmarks in the collection

        Raises:
            CollectionNotFoundError: If collection not found
            CollectionError: If fetching fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(
                    self._get_collection_bookmarks, collection_id, limit, offset
                )
            except Exception as e:
                raise CollectionError(f"Failed to get bookmarks: {str(e)}")

    def _get_collection_bookmarks(
        self, tx: ManagedTransaction, collection_id: UUID4, limit: int, offset: int
    ) -> list[Bookmark]:
        query = """
        MATCH (c:BookmarkCollection {collection_id: $collection_id})-[:CONTAINS]->(b:Bookmark)
        RETURN b
        ORDER BY b.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            collection_id=str(collection_id),
            offset=offset,
            limit=limit,
        )
        return [Bookmark(**record["b"]) for record in result]

    async def get_user_collections(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[BookmarkCollection]:
        """Get a user's bookmark collections.

        Args:
            user_id: ID of the user
            limit: Maximum number of collections to return
            offset: Number of collections to skip

        Returns:
            List of the user's collections

        Raises:
            CollectionError: If fetching fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(
                    self._get_user_collections, user_id, limit, offset
                )
            except Exception as e:
                raise CollectionError(f"Failed to get collections: {str(e)}")

    def _get_user_collections(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[BookmarkCollection]:
        query = """
        MATCH (user:User {user_id: $user_id})-[:OWNS]->(c:BookmarkCollection)
        RETURN c
        ORDER BY c.created_at DESC
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [BookmarkCollection(**record["c"]) for record in result]
