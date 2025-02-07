from datetime import UTC, datetime

from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.user import User
from app.schemas.database_records import CreateBlockRecord, RemoveBlockRecord


class BlockError(Exception):
    """Base exception for block-related errors."""

    pass


class BlockNotFoundError(BlockError):
    """Exception raised when a block relationship is not found."""

    pass


class BlockUpdateError(BlockError):
    """Exception raised when block update fails."""

    pass


class BlockService:
    """Service for managing user blocks.

    This service handles creating and removing block relationships,
    including cleaning up any affected follow relationships.
    """

    def _create_block_relationship(
        self, tx: ManagedTransaction, origin_id: UUID4, target_id: UUID4
    ) -> CreateBlockRecord:
        # language=cypher
        query = """
        MATCH (blocker:User {user_id: $origin_id})
        MATCH (blockee:User {user_id: $target_id})
        WHERE blocker <> blockee

        // Find any existing follow relationships in both directions
        OPTIONAL MATCH (blocker)-[f1:FOLLOWS]->(blockee)
        OPTIONAL MATCH (blockee)-[f2:FOLLOWS]->(blocker)

        // Delete follow relationships if they exist in both directions
        WITH blocker, blockee, f1, f2,
            CASE WHEN f1 IS NOT NULL THEN 1 ELSE 0 END as f1_exists,
            CASE WHEN f2 IS NOT NULL THEN 1 ELSE 0 END as f2_exists
        DELETE f1, f2

        // Update follower/following counts based on what relationships existed
        SET blocker.following_count = CASE

            WHEN f1_exists = 1 THEN coalesce(blocker.following_count, 1) - 1
            ELSE blocker.following_count END,

            blocker.follower_count = CASE
            WHEN f2_exists = 1 THEN coalesce(blocker.follower_count, 1) - 1
            ELSE blocker.follower_count END,

            blockee.following_count = CASE
            WHEN f2_exists = 1 THEN coalesce(blockee.following_count, 1) - 1
            ELSE blockee.following_count END,

            blockee.follower_count = CASE
            WHEN f1_exists = 1 THEN coalesce(blockee.follower_count, 1) - 1
            ELSE blockee.follower_count END


        // Create the block relationships
        MERGE (blocker)-[r:BLOCKS]->(blockee)
        ON CREATE
            SET r.created_at = $current_time

        RETURN {
            success: true,
            blocked_user: blockee.user_id,
            removed_forward_follow: f1_exists = 1,
            removed_reverse_follow: f2_exists = 1
        } as result
        """
        result = tx.run(
            query,
            origin_id=str(origin_id),
            target_id=str(target_id),
            current_time=datetime.now(UTC),
        )
        if data := result.single():
            return CreateBlockRecord(**data["result"])
        else:
            raise ValueError("Something went wrong when trying to block user")

    async def block(self, origin_id: UUID4, target_id: UUID4) -> CreateBlockRecord:
        """Block a user.

        Args:
            origin_id: ID of the user doing the blocking
            target_id: ID of the user to block

        Returns:
            Record of the block creation

        Raises:
            BlockError: If block creation fails
        """
        if origin_id == target_id:
            raise BlockError("Users cannot block themselves")

        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_write(
                    self._create_block_relationship, origin_id, target_id
                )
            except Exception as e:
                raise BlockError(f"Failed to block user: {str(e)}")

    def _remove_block_relationship(
        self, tx: ManagedTransaction, origin_id: UUID4, target_id: UUID4
    ) -> RemoveBlockRecord:
        query = """
        OPTIONAL MATCH (blocker:User {user_id: $origin_id})
        OPTIONAL MATCH (blockee:User {user_id: $target_id})
        OPTIONAL MATCH (blocker)-[r:BLOCKS]->(blockee)
        WHERE r IS NOT NULL
        DELETE r
        WITH blocker, blockee, (blocker IS NOT NULL) as blocker_exists,
            (blockee IS NOT NULL) as blockee_exists
        RETURN {
            success: true,
            blocker_exists: blocker_exists,
            blockee_exists: blockee_exists,
            blocker: blocker,
            blockee: blockee
        }
        """
        result = tx.run(query, origin_id=str(origin_id), target_id=str(target_id))
        if data := result.single():
            return RemoveBlockRecord(**data["result"])
        else:
            raise ValueError("Block does not exist")

    async def unblock(self, origin_id: UUID4, target_id: UUID4) -> None:
        """Unblock a user.

        Args:
            origin_id: ID of the user doing the unblocking
            target_id: ID of the user to unblock

        Raises:
            BlockNotFoundError: If block relationship not found
            BlockError: If unblock fails
        """
        if origin_id == target_id:
            raise BlockError("Users cannot unblock themselves")

        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                session.execute_write(
                    self._remove_block_relationship, origin_id, target_id
                )
            except ValueError as e:
                if "not found" in str(e).lower():
                    raise BlockNotFoundError(str(e))
                raise BlockError(f"Failed to unblock user: {str(e)}")

    async def get_blocked_users(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Get users blocked by a user.

        Args:
            user_id: ID of the user whose blocks to get
            limit: Maximum number of users to return
            offset: Number of users to skip

        Returns:
            List of blocked users

        Raises:
            BlockError: If fetching blocks fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(
                    self._get_blocked_users, user_id, limit, offset
                )
            except Exception as e:
                raise BlockError(f"Failed to get blocked users: {str(e)}")

    def _get_blocked_users(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[User]:
        """Get blocked users from the database.

        Args:
            tx: The database transaction
            user_id: ID of the user whose blocks to get
            limit: Maximum number of users to return
            offset: Number of users to skip

        Returns:
            List of blocked users

        Raises:
            ValueError: If query fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})-[r:BLOCKS]->(blocked:User)
        RETURN blocked
        ORDER BY blocked.username
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [User(**record["blocked"]) for record in result]

    async def is_blocked(self, user_id: UUID4, target_id: UUID4) -> bool:
        """Check if a user is blocked.

        Args:
            user_id: ID of the user to check from
            target_id: ID of the user to check

        Returns:
            True if target is blocked by user, False otherwise

        Raises:
            BlockError: If check fails
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            try:
                return session.execute_read(
                    self._check_block_status, user_id, target_id
                )
            except Exception as e:
                raise BlockError(f"Failed to check block status: {str(e)}")

    def _check_block_status(
        self, tx: ManagedTransaction, user_id: UUID4, target_id: UUID4
    ) -> bool:
        """Check block status in the database.

        Args:
            tx: The database transaction
            user_id: ID of the user to check from
            target_id: ID of the user to check

        Returns:
            True if target is blocked by user, False otherwise

        Raises:
            ValueError: If query fails
        """
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (target:User {user_id: $target_id})
        RETURN exists((user)-[:BLOCKS]->(target)) as is_blocked
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            target_id=str(target_id),
        )
        if record := result.single():
            return record["is_blocked"]
        return False
