from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict


class Block(BaseModel):
    """Model representing a block relationship between users.

    This model contains information about a block relationship including
    who blocked whom and when.

    Attributes:
        blocker_id: ID of the user doing the blocking
        blocked_id: ID of the user being blocked
        created_at: When the block was created
    """

    model_config = ConfigDict(frozen=True)

    blocker_id: UUID4
    blocked_id: UUID4
    created_at: datetime
