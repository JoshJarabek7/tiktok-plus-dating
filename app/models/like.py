from datetime import datetime
from enum import Enum

from pydantic import UUID4, BaseModel, ConfigDict


class ContentType(str, Enum):
    """Types of content that can be liked.

    Attributes:
        POST: A video post
        COMMENT: A comment on a post
    """

    POST = "post"
    COMMENT = "comment"


class Like(BaseModel):
    """Model representing a like on content.

    This model contains information about a like including who liked what
    and when. It can represent likes on posts or comments.

    Attributes:
        user_id: ID of the user who created the like
        content_id: ID of the content being liked (post or comment)
        content_type: Type of content being liked (post or comment)
        created_at: When the like was created
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID4
    content_id: UUID4
    content_type: ContentType
    created_at: datetime
