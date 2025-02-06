from datetime import datetime
from enum import Enum

from pydantic import UUID4, BaseModel, ConfigDict, Field


class NotificationCenterType(str, Enum):
    """Types of notifications that can be sent in the system.

    Attributes:
        MESSAGE_CREATED: When a new message is received
        FOLLOW_REQUEST_CREATED: When someone requests to follow
        FOLLOW_REQUEST_ACCEPTED: When a follow request is accepted
        LIKED_POST: When someone likes a post
        LIKED_COMMENT: When someone likes a comment
        COMMENT_ON_POST: When someone comments on a post
        REPLY_TO_COMMENT: When someone replies to a comment
        MENTIONED_IN_COMMENT: When mentioned in a comment
        MENTIONED_IN_POST: When mentioned in a post
        MENTIONED_IN_REPLY: When mentioned in a reply
    """

    # Message
    MESSAGE_CREATED = "message_created"

    # Follow
    FOLLOW_REQUEST_CREATED = "follow_request_created"
    FOLLOW_REQUEST_ACCEPTED = "follow_request_accepted"

    # Like
    LIKED_POST = "liked_post"
    LIKED_COMMENT = "liked_comment"

    # Comment
    COMMENT_ON_POST = "comment_on_post"
    REPLY_TO_COMMENT = "reply_to_comment"

    # Mention
    MENTIONED_IN_COMMENT = "mentioned_in_comment"
    MENTIONED_IN_POST = "mentioned_in_post"
    MENTIONED_IN_REPLY = "mentioned_in_reply"


class Notification(BaseModel):
    """Model representing a notification in the system.

    Attributes:
        notification_id: Unique identifier for the notification
        notification_type: Type of notification from NotificationCenterType
        seen_at: When the notification was seen by the user
        from_user_id: ID of the user who triggered the notification
        to_user_id: ID of the user receiving the notification
        content_id: ID of the related content (post, comment, etc.)
        created_at: When the notification was created
    """

    model_config = ConfigDict(frozen=True)

    notification_id: UUID4 = Field(description="Unique identifier for the notification")
    notification_type: NotificationCenterType = Field(
        description="Type of notification"
    )
    seen_at: datetime | None = Field(None, description="When the notification was seen")
    from_user_id: UUID4 = Field(
        description="ID of the user who triggered the notification"
    )
    to_user_id: UUID4 = Field(description="ID of the user receiving the notification")
    content_id: UUID4 = Field(description="ID of the related content")
    created_at: datetime = Field(description="When the notification was created")
