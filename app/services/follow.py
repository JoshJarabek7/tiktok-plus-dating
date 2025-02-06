from datetime import UTC, datetime

from neo4j import ManagedTransaction
from pydantic import UUID4
from schemas.database_records import (
    AcceptFollowRequestRecord,
    CreateFollowRecord,
)

from app.db import DatabaseManager
from app.models.user import User


class FollowError(Exception):
    """Base exception for follow-related errors."""

    pass


class FollowNotFoundError(FollowError):
    """Exception raised when a follow relationship is not found."""

    pass


class FollowRequestNotFoundError(FollowError):
    """Exception raised when a follow request is not found."""

    pass


class FollowCreationError(FollowError):
    """Exception raised when follow creation fails."""

    pass


class FollowRequestError(FollowError):
    """Exception raised when follow request processing fails."""

    pass


class FollowService:
    """Service for managing user follow relationships.

    This service handles:
    - Following/unfollowing users
    - Follow requests for private accounts
    - Accepting/denying follow requests
    - Getting followers/following lists
    """

    async def follow_user(
        self, origin_id: UUID4, target_id: UUID4
    ) -> CreateFollowRecord:
        """Follow a user or create a follow request.

        For public accounts, creates a direct follow relationship.
        For private accounts, creates a follow request that must be accepted.

        Args:
            origin_id: ID of the user doing the following
            target_id: ID of the user to follow

        Returns:
            Record containing the created relationship

        Raises:
            FollowCreationError: If follow creation fails
        """
        if origin_id == target_id:
            raise FollowCreationError("Users cannot follow themselves")

        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_write(
                    self._create_follow_relationship, origin_id, target_id
                )
        except Exception as e:
            raise FollowCreationError(f"Failed to create follow: {str(e)}")

    def _create_follow_relationship(
        self, tx: ManagedTransaction, origin_id: UUID4, target_id: UUID4
    ) -> CreateFollowRecord:
        """Create a follow relationship in the database.

        Args:
            tx: The database transaction
            origin_id: ID of the user doing the following
            target_id: ID of the user to follow

        Returns:
            Record containing the created relationship

        Raises:
            FollowCreationError: If follow creation fails
        """
        query = """
        // Match both users
        MATCH (follower:User {user_id: $origin_id})
        MATCH (following:User {user_id: $target_id})
        WHERE follower <> following

        // Check for any blocking relationships in either direction
        OPTIONAL MATCH (follower)-[b1:BLOCKS]->(following)
        OPTIONAL MATCH (following)-[b2:BLOCKS]->(follower)

        // Check for existing follow request or follow relationship
        OPTIONAL MATCH (follower)-[existing_req:REQUESTED_TO_FOLLOW]->(following)
        OPTIONAL MATCH (follower)-[existing_follow:FOLLOWS]->(following)

        WITH follower, following, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL AND existing_req IS NULL AND existing_follow IS NULL

        // Handle based on account privacy
        CALL {
            WITH follower, following
            WITH follower, following, following.is_private AS is_private
            WITH follower, following, is_private
            WHERE is_private = true
            // Create follow request for private accounts
            CREATE (follower)-[r:REQUESTED_TO_FOLLOW {
                created_at: $current_time,
                status: 'PENDING'
            }]->(following)
            RETURN r, false as direct_follow

            UNION

            WITH follower, following
            WITH follower, following, following.is_private AS is_private
            WHERE is_private = false OR is_private IS NULL
            // Create direct follow for public accounts
            CREATE (follower)-[r:FOLLOWS {
                created_at: $current_time
            }]->(following)
            SET follower.following_count = coalesce(follower.following_count, 0) + 1,
                following.follower_count = coalesce(following.follower_count, 0) + 1
            RETURN r, true as direct_follow
        }
        RETURN {
            success: true,
            follower: follower,
            following: following,
            relationship: r,
            is_direct_follow: direct_follow
        } as result
        """
        result = tx.run(
            query,
            origin_id=str(origin_id),
            target_id=str(target_id),
            current_time=datetime.now(UTC),
        )

        if record := result.single():
            return CreateFollowRecord(**record["result"])

        # Check why the follow failed
        check_query = """
        MATCH (u1:User {user_id: $origin_id})
        MATCH (u2:User {user_id: $target_id})
        OPTIONAL MATCH (u1)-[b1:BLOCKS]->(u2)
        OPTIONAL MATCH (u2)-[b2:BLOCKS]->(u1)
        RETURN {
            blocked_by_follower: b1 IS NOT NULL,
            blocked_by_target: b2 IS NOT NULL
        } as block_status
        """
        block_status = tx.run(
            check_query, origin_id=str(origin_id), target_id=str(target_id)
        )
        if block_data := block_status.single():
            status = block_data["block_status"]
            if status["blocked_by_follower"]:
                raise FollowCreationError("Cannot follow a user you have blocked")
            elif status["blocked_by_target"]:
                raise FollowCreationError("Cannot follow a user who has blocked you")
        raise FollowCreationError("Unknown error when following user")

    async def accept_request(
        self, request_user_id: UUID4, target_user_id: UUID4
    ) -> AcceptFollowRequestRecord:
        """Accept a follow request.

        Args:
            request_user_id: ID of the user who requested to follow
            target_user_id: ID of the user accepting the request

        Returns:
            Record containing the accepted follow relationship

        Raises:
            FollowRequestNotFoundError: If request not found
            FollowRequestError: If request processing fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_write(
                    self._accept_follow_request, request_user_id, target_user_id
                )
        except FollowRequestNotFoundError:
            raise
        except Exception as e:
            raise FollowRequestError(f"Failed to accept follow request: {str(e)}")

    def _accept_follow_request(
        self, tx: ManagedTransaction, request_user_id: UUID4, target_user_id: UUID4
    ) -> AcceptFollowRequestRecord:
        """Accept a follow request in the database.

        Args:
            tx: The database transaction
            request_user_id: ID of the user who requested to follow
            target_user_id: ID of the user accepting the request

        Returns:
            Record containing the accepted follow relationship

        Raises:
            FollowRequestNotFoundError: If request not found
            FollowRequestError: If request processing fails
        """
        query = """
        MATCH (requester:User {user_id: $request_user_id})
        MATCH (target:User {user_id: $target_user_id})
        MATCH (requester)-[request:REQUESTED_TO_FOLLOW]->(target)
        WHERE request.status = 'PENDING'

        // Delete the request and create a follow relationship
        DELETE request
        CREATE (requester)-[follow:FOLLOWS {
            created_at: $current_time,
            request_accepted_at: $current_time
        }]->(target)

        // Update counts
        SET requester.following_count = coalesce(requester.following_count, 0) + 1,
            target.follower_count = coalesce(target.follower_count, 0) + 1

        RETURN {
            success: true,
            follower: requester,
            following: target,
            relationship: follow
        } as result
        """

        result = tx.run(
            query,
            request_user_id=str(request_user_id),
            target_user_id=str(target_user_id),
            current_time=datetime.now(UTC),
        )

        if record := result.single():
            return AcceptFollowRequestRecord(**record["result"])
        raise FollowRequestNotFoundError(
            "Follow request not found or already processed"
        )

    def _deny_follow_request(
        self, tx: ManagedTransaction, request_user_id: UUID4, target_user_id: UUID4
    ) -> None:
        query = """
        MATCH (requester:User {user_id: $request_user_id})
        MATCH (target:User {user_id: $target_user_id})
        MATCH (requester)-[request:REQUESTED_TO_FOLLOW]->(target)
        WHERE request.status = 'PENDING'
        DELETE request
        """

        result = tx.run(
            query,
            request_user_id=str(request_user_id),
            target_user_id=str(target_user_id),
        )

        if not result.consume().counters.relationships_deleted:
            raise FollowRequestNotFoundError(
                "Follow request not found or already processed"
            )

    async def deny_request(self, request_user_id: UUID4, target_user_id: UUID4) -> None:
        """Deny a follow request.

        Args:
            request_user_id: ID of the user who requested to follow
            target_user_id: ID of the user denying the request

        Raises:
            FollowRequestNotFoundError: If request not found
            FollowRequestError: If request processing fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                session.execute_write(
                    self._deny_follow_request,
                    request_user_id,
                    target_user_id,
                )
        except FollowRequestNotFoundError:
            raise
        except Exception as e:
            raise FollowRequestError(f"Failed to deny follow request: {str(e)}")

    async def unfollow_user(self, origin_id: UUID4, target_id: UUID4) -> None:
        """Unfollow a user.

        Args:
            origin_id: ID of the user doing the unfollowing
            target_id: ID of the user to unfollow

        Raises:
            FollowNotFoundError: If follow relationship not found
            FollowError: If unfollow fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                session.execute_write(self._remove_follow, origin_id, target_id)
        except FollowNotFoundError:
            raise
        except Exception as e:
            raise FollowError(f"Failed to unfollow user: {str(e)}")

    def _remove_follow(
        self, tx: ManagedTransaction, origin_id: UUID4, target_id: UUID4
    ) -> None:
        query = """
        MATCH (follower:User {user_id: $origin_id})-[r:FOLLOWS]->(following:User {user_id: $target_id})
        DELETE r
        SET follower.following_count = follower.following_count - 1,
            following.follower_count = following.follower_count - 1
        """
        result = tx.run(
            query,
            origin_id=str(origin_id),
            target_id=str(target_id),
        )
        if not result.consume().counters.relationships_deleted:
            raise FollowNotFoundError("Follow relationship not found")

    async def get_followers(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Get a user's followers.

        Args:
            user_id: ID of the user
            limit: Maximum number of followers to return
            offset: Number of followers to skip

        Returns:
            List of users who follow the specified user

        Raises:
            FollowError: If fetching followers fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_read(self._get_followers, user_id, limit, offset)
        except Exception as e:
            raise FollowError(f"Failed to get followers: {str(e)}")

    def _get_followers(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[User]:
        query = """
        MATCH (follower:User)-[:FOLLOWS]->(user:User {user_id: $user_id})
        RETURN follower
        ORDER BY follower.username
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [record["follower"] for record in result]

    async def get_following(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Get users followed by a user.

        Args:
            user_id: ID of the user
            limit: Maximum number of followed users to return
            offset: Number of followed users to skip

        Returns:
            List of users followed by the specified user

        Raises:
            FollowError: If fetching following fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_read(self._get_following, user_id, limit, offset)
        except Exception as e:
            raise FollowError(f"Failed to get following: {str(e)}")

    def _get_following(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[User]:
        query = """
        MATCH (user:User {user_id: $user_id})-[:FOLLOWS]->(following:User)
        RETURN following
        ORDER BY following.username
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [record["following"] for record in result]

    async def get_mutual_follows(
        self, user_id: UUID4, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Get users who mutually follow a user.

        Args:
            user_id: ID of the user
            limit: Maximum number of mutual follows to return
            offset: Number of mutual follows to skip

        Returns:
            List of users who mutually follow the specified user

        Raises:
            FollowError: If fetching mutual follows fails
        """
        try:
            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                return session.execute_read(
                    self._get_mutual_follows, user_id, limit, offset
                )
        except Exception as e:
            raise FollowError(f"Failed to get mutual follows: {str(e)}")

    def _get_mutual_follows(
        self, tx: ManagedTransaction, user_id: UUID4, limit: int, offset: int
    ) -> list[User]:
        query = """
        MATCH (user:User {user_id: $user_id})-[:FOLLOWS]->(mutual:User)-[:FOLLOWS]->(user)
        RETURN mutual
        ORDER BY mutual.username
        SKIP $offset
        LIMIT $limit
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            offset=offset,
            limit=limit,
        )
        return [record["mutual"] for record in result]
