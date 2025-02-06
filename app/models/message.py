from datetime import datetime
from enum import Enum

from pydantic import UUID4, BaseModel, ConfigDict, Field


class ReactionType(str, Enum):
    """Enumeration of possible message reactions.

    Each reaction is represented by an emoji character.
    """

    LIKE = "❤️"
    LAUGH = "😂"
    SAD = "🥲"
    ANGRY = "😠"
    THUMBS_UP = "👍"
    THUMBS_DOWN = "👎"


class Message(BaseModel):
    """Model representing a direct message between users.

    This model contains all information about a message including its content,
    relationships to other entities, and metadata.

    Attributes:
        message_id: Unique identifier for the message
        content: The text content of the message
        sender_id: ID of the user sending the message
        receiver_id: ID of the user receiving the message
        shared_post_id: ID of a shared post if this message shares one
        reply_to_message_id: ID of the message being replied to if this is a reply
        created_at: When the message was created
        is_deleted: Whether the message has been deleted
    """

    model_config = ConfigDict(frozen=True)

    message_id: UUID4
    content: str = Field(min_length=1)
    sender_id: UUID4
    receiver_id: UUID4
    shared_post_id: UUID4 | None = None
    reply_to_message_id: UUID4 | None = None
    created_at: datetime
    is_deleted: bool = False


class MessageReaction(BaseModel):
    """Model representing a reaction to a message.

    This model contains information about a user's reaction to a specific message.

    Attributes:
        message_id: ID of the message being reacted to
        user_id: ID of the user adding the reaction
        reaction_type: Type of reaction from ReactionType enum
        created_at: When the reaction was created
    """

    model_config = ConfigDict(frozen=True)

    message_id: UUID4
    user_id: UUID4
    reaction_type: ReactionType
    created_at: datetime
