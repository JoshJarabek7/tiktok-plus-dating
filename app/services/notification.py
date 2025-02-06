from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from neo4j import ManagedTransaction
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.notification import Notification


class NotificationBaseService(ABC):
    """Base class for all notification services.

    This abstract class defines the interface that all notification services
    must implement, ensuring consistent behavior across different notification types.
    """

    @abstractmethod
    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        """Create a notification in the database.

        Args:
            tx: The database transaction
            notification: The notification to create

        Returns:
            Dict containing success status and any relevant data

        Raises:
            ValueError: If the notification cannot be created
        """
        raise NotImplementedError

    @abstractmethod
    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status and any relevant data

        Raises:
            ValueError: If the notification cannot be created
        """
        raise NotImplementedError

    @abstractmethod
    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        """Mark a notification as read in the database.

        Args:
            tx: The database transaction
            content_id: ID of the content the notification is about
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and any relevant data

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        raise NotImplementedError

    @abstractmethod
    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a notification as read.

        Args:
            content_id: ID of the content the notification is about
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and any relevant data

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        raise NotImplementedError


class MessageCreatedNotification(NotificationBaseService):
    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (message:Message {message_id: $content_id})
        
        // Check for blocks in either direction
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        
        WITH from_user, to_user, message, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL
        
        MERGE (message)-[r:NOTIFICATION {
            notification_id: $notification_id,
            notification_type: $notification_type,
            from_user_id: $from_user_id,
            to_user_id: $to_user_id,
            content_id: $content_id
        }]->(to_user)
        ON CREATE
            SET r.created_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            notification_id=str(notification.notification_id),
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
            notification_type=str(notification.notification_type.value),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the notification creation failed
        check_query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (message:Message {message_id: $content_id})
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        RETURN {
            from_user_exists: from_user IS NOT NULL,
            to_user_exists: to_user IS NOT NULL,
            message_exists: message IS NOT NULL,
            blocked_by_sender: b1 IS NOT NULL,
            blocked_by_receiver: b2 IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["from_user_exists"]:
                raise ValueError("Sender not found")
            elif not status["to_user_exists"]:
                raise ValueError("Receiver not found")
            elif not status["message_exists"]:
                raise ValueError("Message not found")
            elif status["blocked_by_sender"]:
                raise ValueError("Cannot send notification to a user you have blocked")
            elif status["blocked_by_receiver"]:
                raise ValueError(
                    "Cannot send notification to a user who has blocked you"
                )
        raise ValueError("Something went wrong when creating the notification")

    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a message notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status

        Raises:
            ValueError: If the notification cannot be created
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_notification, notification=notification
            )

    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (message:Message {message_id: $content_id})
        MATCH (message)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        WHERE r.seen_at IS NULL
        SET r.seen_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the read operation failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (message:Message {message_id: $content_id})
        OPTIONAL MATCH (message)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        RETURN {
            user_exists: user IS NOT NULL,
            message_exists: message IS NOT NULL,
            notification_exists: r IS NOT NULL,
            already_seen: r.seen_at IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["message_exists"]:
                raise ValueError("Message not found")
            elif not status["notification_exists"]:
                raise ValueError("Notification not found")
            elif status["already_seen"]:
                raise ValueError("Notification has already been marked as read")
        raise ValueError("Something went wrong when marking the notification as read")

    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a message notification as read.

        Args:
            content_id: ID of the message
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._read_notification,
                content_id=content_id,
                notification_id=notification_id,
                user_id=user_id,
            )


class LikedPostNotification(NotificationBaseService):
    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a post like notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be created
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_notification, notification=notification
            )

    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (post:Post {post_id: $content_id})
        
        // Check for blocks in either direction
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        
        WITH from_user, to_user, post, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL
        
        MERGE (post)-[r:NOTIFICATION {
            notification_id: $notification_id,
            notification_type: $notification_type,
            from_user_id: $from_user_id,
            to_user_id: $to_user_id,
            content_id: $content_id
        }]->(to_user)
        ON CREATE
            SET r.created_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            notification_id=str(notification.notification_id),
            notification_type=notification.notification_type.value,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the notification creation failed
        check_query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (post:Post {post_id: $content_id})
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        RETURN {
            from_user_exists: from_user IS NOT NULL,
            to_user_exists: to_user IS NOT NULL,
            post_exists: post IS NOT NULL,
            blocked_by_sender: b1 IS NOT NULL,
            blocked_by_receiver: b2 IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["from_user_exists"]:
                raise ValueError("Sender not found")
            elif not status["to_user_exists"]:
                raise ValueError("Receiver not found")
            elif not status["post_exists"]:
                raise ValueError("Post not found")
            elif status["blocked_by_sender"]:
                raise ValueError("Cannot send notification to a user you have blocked")
            elif status["blocked_by_receiver"]:
                raise ValueError(
                    "Cannot send notification to a user who has blocked you"
                )
        raise ValueError("Something went wrong when creating the notification")

    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a post like notification as read.

        Args:
            content_id: ID of the post
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._read_notification,
                content_id=content_id,
                notification_id=notification_id,
                user_id=user_id,
            )

    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $content_id})
        MATCH (post)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        WHERE r.seen_at IS NULL
        SET r.seen_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the read operation failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $content_id})
        OPTIONAL MATCH (post)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        RETURN {
            user_exists: user IS NOT NULL,
            post_exists: post IS NOT NULL,
            notification_exists: r IS NOT NULL,
            already_seen: r.seen_at IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["post_exists"]:
                raise ValueError("Post not found")
            elif not status["notification_exists"]:
                raise ValueError("Notification not found")
            elif status["already_seen"]:
                raise ValueError("Notification has already been marked as read")
        raise ValueError("Something went wrong when marking the notification as read")


class LikedCommentNotification(NotificationBaseService):
    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a comment like notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be created
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_notification, notification=notification
            )

    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        
        // Check for blocks in either direction
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        
        WITH from_user, to_user, comment, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL
        
        MERGE (comment)-[r:NOTIFICATION {
            notification_id: $notification_id,
            notification_type: $notification_type,
            from_user_id: $from_user_id,
            to_user_id: $to_user_id,
            content_id: $content_id
        }]->(to_user)
        ON CREATE
            SET r.created_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            notification_id=str(notification.notification_id),
            notification_type=notification.notification_type.value,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the notification creation failed
        check_query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        RETURN {
            from_user_exists: from_user IS NOT NULL,
            to_user_exists: to_user IS NOT NULL,
            comment_exists: comment IS NOT NULL,
            blocked_by_sender: b1 IS NOT NULL,
            blocked_by_receiver: b2 IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["from_user_exists"]:
                raise ValueError("Sender not found")
            elif not status["to_user_exists"]:
                raise ValueError("Receiver not found")
            elif not status["comment_exists"]:
                raise ValueError("Comment not found")
            elif status["blocked_by_sender"]:
                raise ValueError("Cannot send notification to a user you have blocked")
            elif status["blocked_by_receiver"]:
                raise ValueError(
                    "Cannot send notification to a user who has blocked you"
                )
        raise ValueError("Something went wrong when creating the notification")

    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a comment like notification as read.

        Args:
            content_id: ID of the comment
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._read_notification,
                content_id=content_id,
                notification_id=notification_id,
                user_id=user_id,
            )

    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        MATCH (comment)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        WHERE r.seen_at IS NULL
        SET r.seen_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the read operation failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        OPTIONAL MATCH (comment)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        RETURN {
            user_exists: user IS NOT NULL,
            comment_exists: comment IS NOT NULL,
            notification_exists: r IS NOT NULL,
            already_seen: r.seen_at IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["comment_exists"]:
                raise ValueError("Comment not found")
            elif not status["notification_exists"]:
                raise ValueError("Notification not found")
            elif status["already_seen"]:
                raise ValueError("Notification has already been marked as read")
        raise ValueError("Something went wrong when marking the notification as read")


class CommentOnPostNotification(NotificationBaseService):
    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a comment on post notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be created
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_notification, notification=notification
            )

    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        
        // Check for blocks in either direction
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        
        WITH from_user, to_user, comment, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL
        
        MERGE (comment)-[r:NOTIFICATION {
            notification_id: $notification_id,
            notification_type: $notification_type,
            from_user_id: $from_user_id,
            to_user_id: $to_user_id,
            content_id: $content_id
        }]->(to_user)
        ON CREATE
            SET r.created_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            notification_id=str(notification.notification_id),
            notification_type=notification.notification_type.value,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the notification creation failed
        check_query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        RETURN {
            from_user_exists: from_user IS NOT NULL,
            to_user_exists: to_user IS NOT NULL,
            comment_exists: comment IS NOT NULL,
            blocked_by_sender: b1 IS NOT NULL,
            blocked_by_receiver: b2 IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["from_user_exists"]:
                raise ValueError("Sender not found")
            elif not status["to_user_exists"]:
                raise ValueError("Receiver not found")
            elif not status["comment_exists"]:
                raise ValueError("Comment not found")
            elif status["blocked_by_sender"]:
                raise ValueError("Cannot send notification to a user you have blocked")
            elif status["blocked_by_receiver"]:
                raise ValueError(
                    "Cannot send notification to a user who has blocked you"
                )
        raise ValueError("Something went wrong when creating the notification")

    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a comment on post notification as read.

        Args:
            content_id: ID of the comment
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._read_notification,
                content_id=content_id,
                notification_id=notification_id,
                user_id=user_id,
            )

    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        MATCH (comment)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        WHERE r.seen_at IS NULL
        SET r.seen_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the read operation failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        OPTIONAL MATCH (comment)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        RETURN {
            user_exists: user IS NOT NULL,
            comment_exists: comment IS NOT NULL,
            notification_exists: r IS NOT NULL,
            already_seen: r.seen_at IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["comment_exists"]:
                raise ValueError("Comment not found")
            elif not status["notification_exists"]:
                raise ValueError("Notification not found")
            elif status["already_seen"]:
                raise ValueError("Notification has already been marked as read")
        raise ValueError("Something went wrong when marking the notification as read")


class ReplyToCommentNotification(NotificationBaseService):
    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a reply to comment notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be created
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_notification, notification=notification
            )

    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (reply:Comment {comment_id: $content_id})
        
        // Check for blocks in either direction
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        
        WITH from_user, to_user, reply, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL
        
        MERGE (reply)-[r:NOTIFICATION {
            notification_id: $notification_id,
            notification_type: $notification_type,
            from_user_id: $from_user_id,
            to_user_id: $to_user_id,
            content_id: $content_id
        }]->(to_user)
        ON CREATE
            SET r.created_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            notification_id=str(notification.notification_id),
            notification_type=notification.notification_type.value,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the notification creation failed
        check_query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (reply:Comment {comment_id: $content_id})
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        RETURN {
            from_user_exists: from_user IS NOT NULL,
            to_user_exists: to_user IS NOT NULL,
            reply_exists: reply IS NOT NULL,
            blocked_by_sender: b1 IS NOT NULL,
            blocked_by_receiver: b2 IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["from_user_exists"]:
                raise ValueError("Sender not found")
            elif not status["to_user_exists"]:
                raise ValueError("Receiver not found")
            elif not status["reply_exists"]:
                raise ValueError("Reply not found")
            elif status["blocked_by_sender"]:
                raise ValueError("Cannot send notification to a user you have blocked")
            elif status["blocked_by_receiver"]:
                raise ValueError(
                    "Cannot send notification to a user who has blocked you"
                )
        raise ValueError("Something went wrong when creating the notification")

    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a reply to comment notification as read.

        Args:
            content_id: ID of the reply
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._read_notification,
                content_id=content_id,
                notification_id=notification_id,
                user_id=user_id,
            )

    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (reply:Comment {comment_id: $content_id})
        MATCH (reply)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        WHERE r.seen_at IS NULL
        SET r.seen_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the read operation failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (reply:Comment {comment_id: $content_id})
        OPTIONAL MATCH (reply)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        RETURN {
            user_exists: user IS NOT NULL,
            reply_exists: reply IS NOT NULL,
            notification_exists: r IS NOT NULL,
            already_seen: r.seen_at IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["reply_exists"]:
                raise ValueError("Reply not found")
            elif not status["notification_exists"]:
                raise ValueError("Notification not found")
            elif status["already_seen"]:
                raise ValueError("Notification has already been marked as read")
        raise ValueError("Something went wrong when marking the notification as read")


class MentionedInCommentNotification(NotificationBaseService):
    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a mentioned in comment notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be created
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_notification, notification=notification
            )

    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        
        // Check for blocks in either direction
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        
        WITH from_user, to_user, comment, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL
        
        MERGE (comment)-[r:NOTIFICATION {
            notification_id: $notification_id,
            notification_type: $notification_type,
            from_user_id: $from_user_id,
            to_user_id: $to_user_id,
            content_id: $content_id
        }]->(to_user)
        ON CREATE
            SET r.created_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            notification_id=str(notification.notification_id),
            notification_type=notification.notification_type.value,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the notification creation failed
        check_query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        RETURN {
            from_user_exists: from_user IS NOT NULL,
            to_user_exists: to_user IS NOT NULL,
            comment_exists: comment IS NOT NULL,
            blocked_by_sender: b1 IS NOT NULL,
            blocked_by_receiver: b2 IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["from_user_exists"]:
                raise ValueError("Sender not found")
            elif not status["to_user_exists"]:
                raise ValueError("Receiver not found")
            elif not status["comment_exists"]:
                raise ValueError("Comment not found")
            elif status["blocked_by_sender"]:
                raise ValueError("Cannot send notification to a user you have blocked")
            elif status["blocked_by_receiver"]:
                raise ValueError(
                    "Cannot send notification to a user who has blocked you"
                )
        raise ValueError("Something went wrong when creating the notification")

    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a mentioned in comment notification as read.

        Args:
            content_id: ID of the comment
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._read_notification,
                content_id=content_id,
                notification_id=notification_id,
                user_id=user_id,
            )

    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        MATCH (comment)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        WHERE r.seen_at IS NULL
        SET r.seen_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the read operation failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (comment:Comment {comment_id: $content_id})
        OPTIONAL MATCH (comment)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        RETURN {
            user_exists: user IS NOT NULL,
            comment_exists: comment IS NOT NULL,
            notification_exists: r IS NOT NULL,
            already_seen: r.seen_at IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["comment_exists"]:
                raise ValueError("Comment not found")
            elif not status["notification_exists"]:
                raise ValueError("Notification not found")
            elif status["already_seen"]:
                raise ValueError("Notification has already been marked as read")
        raise ValueError("Something went wrong when marking the notification as read")


class MentionedInPostNotification(NotificationBaseService):
    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a mentioned in post notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be created
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_notification, notification=notification
            )

    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (post:Post {post_id: $content_id})
        
        // Check for blocks in either direction
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        
        WITH from_user, to_user, post, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL
        
        MERGE (post)-[r:NOTIFICATION {
            notification_id: $notification_id,
            notification_type: $notification_type,
            from_user_id: $from_user_id,
            to_user_id: $to_user_id,
            content_id: $content_id
        }]->(to_user)
        ON CREATE
            SET r.created_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            notification_id=str(notification.notification_id),
            notification_type=notification.notification_type.value,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the notification creation failed
        check_query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (post:Post {post_id: $content_id})
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        RETURN {
            from_user_exists: from_user IS NOT NULL,
            to_user_exists: to_user IS NOT NULL,
            post_exists: post IS NOT NULL,
            blocked_by_sender: b1 IS NOT NULL,
            blocked_by_receiver: b2 IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["from_user_exists"]:
                raise ValueError("Sender not found")
            elif not status["to_user_exists"]:
                raise ValueError("Receiver not found")
            elif not status["post_exists"]:
                raise ValueError("Post not found")
            elif status["blocked_by_sender"]:
                raise ValueError("Cannot send notification to a user you have blocked")
            elif status["blocked_by_receiver"]:
                raise ValueError(
                    "Cannot send notification to a user who has blocked you"
                )
        raise ValueError("Something went wrong when creating the notification")

    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a mentioned in post notification as read.

        Args:
            content_id: ID of the post
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._read_notification,
                content_id=content_id,
                notification_id=notification_id,
                user_id=user_id,
            )

    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $content_id})
        MATCH (post)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        WHERE r.seen_at IS NULL
        SET r.seen_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the read operation failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (post:Post {post_id: $content_id})
        OPTIONAL MATCH (post)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        RETURN {
            user_exists: user IS NOT NULL,
            post_exists: post IS NOT NULL,
            notification_exists: r IS NOT NULL,
            already_seen: r.seen_at IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["post_exists"]:
                raise ValueError("Post not found")
            elif not status["notification_exists"]:
                raise ValueError("Notification not found")
            elif status["already_seen"]:
                raise ValueError("Notification has already been marked as read")
        raise ValueError("Something went wrong when marking the notification as read")


class MentionedInReplyNotification(NotificationBaseService):
    def create(self, notification: Notification) -> dict[str, Any]:
        """Create a mentioned in reply notification.

        Args:
            notification: The notification to create

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be created
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._create_notification, notification=notification
            )

    def _create_notification(
        self, tx: ManagedTransaction, notification: Notification
    ) -> dict[str, Any]:
        query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (reply:Comment {comment_id: $content_id})
        
        // Check for blocks in either direction
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        
        WITH from_user, to_user, reply, b1, b2
        WHERE b1 IS NULL AND b2 IS NULL
        
        MERGE (reply)-[r:NOTIFICATION {
            notification_id: $notification_id,
            notification_type: $notification_type,
            from_user_id: $from_user_id,
            to_user_id: $to_user_id,
            content_id: $content_id
        }]->(to_user)
        ON CREATE
            SET r.created_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            notification_id=str(notification.notification_id),
            notification_type=notification.notification_type.value,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the notification creation failed
        check_query = """
        MATCH (from_user:User {user_id: $from_user_id})
        MATCH (to_user:User {user_id: $to_user_id})
        MATCH (reply:Comment {comment_id: $content_id})
        OPTIONAL MATCH (from_user)-[b1:BLOCKS]->(to_user)
        OPTIONAL MATCH (to_user)-[b2:BLOCKS]->(from_user)
        RETURN {
            from_user_exists: from_user IS NOT NULL,
            to_user_exists: to_user IS NOT NULL,
            reply_exists: reply IS NOT NULL,
            blocked_by_sender: b1 IS NOT NULL,
            blocked_by_receiver: b2 IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            from_user_id=str(notification.from_user_id),
            to_user_id=str(notification.to_user_id),
            content_id=str(notification.content_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["from_user_exists"]:
                raise ValueError("Sender not found")
            elif not status["to_user_exists"]:
                raise ValueError("Receiver not found")
            elif not status["reply_exists"]:
                raise ValueError("Reply not found")
            elif status["blocked_by_sender"]:
                raise ValueError("Cannot send notification to a user you have blocked")
            elif status["blocked_by_receiver"]:
                raise ValueError(
                    "Cannot send notification to a user who has blocked you"
                )
        raise ValueError("Something went wrong when creating the notification")

    def read(
        self, content_id: UUID4, notification_id: UUID4, user_id: UUID4
    ) -> dict[str, Any]:
        """Mark a mentioned in reply notification as read.

        Args:
            content_id: ID of the reply
            notification_id: ID of the notification
            user_id: ID of the user reading the notification

        Returns:
            Dict containing success status and notification ID

        Raises:
            ValueError: If the notification cannot be marked as read
        """
        db_manager = DatabaseManager()
        with db_manager.driver.session(database=db_manager.database) as session:
            return session.execute_write(
                self._read_notification,
                content_id=content_id,
                notification_id=notification_id,
                user_id=user_id,
            )

    def _read_notification(
        self,
        tx: ManagedTransaction,
        content_id: UUID4,
        notification_id: UUID4,
        user_id: UUID4,
    ) -> dict[str, Any]:
        query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (reply:Comment {comment_id: $content_id})
        MATCH (reply)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        WHERE r.seen_at IS NULL
        SET r.seen_at = $current_datetime
        RETURN { success: true, notification_id: $notification_id } as result
        """
        result = tx.run(
            query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
            current_datetime=datetime.now(UTC),
        )
        if record := result.single():
            return record["result"]

        # Check why the read operation failed
        check_query = """
        MATCH (user:User {user_id: $user_id})
        MATCH (reply:Comment {comment_id: $content_id})
        OPTIONAL MATCH (reply)-[r:NOTIFICATION {notification_id: $notification_id}]->(user)
        RETURN {
            user_exists: user IS NOT NULL,
            reply_exists: reply IS NOT NULL,
            notification_exists: r IS NOT NULL,
            already_seen: r.seen_at IS NOT NULL
        } as status
        """
        status = tx.run(
            check_query,
            user_id=str(user_id),
            content_id=str(content_id),
            notification_id=str(notification_id),
        )
        if status_data := status.single():
            status = status_data["status"]
            if not status["user_exists"]:
                raise ValueError("User not found")
            elif not status["reply_exists"]:
                raise ValueError("Reply not found")
            elif not status["notification_exists"]:
                raise ValueError("Notification not found")
            elif status["already_seen"]:
                raise ValueError("Notification has already been marked as read")
        raise ValueError("Something went wrong when marking the notification as read")
