from datetime import datetime
from enum import Enum

from pydantic import UUID4, BaseModel, ConfigDict


class FollowRequestStatus(str, Enum):
    """Status of a follow request.

    Attributes:
        PENDING: Request is waiting for response
        ACCEPTED: Request was accepted
        DENIED: Request was denied
    """

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DENIED = "DENIED"


class Follow(BaseModel):
    """Model representing a follow relationship between users.

    This model contains information about a follow relationship including
    who follows whom and when it was created/accepted.

    Attributes:
        follower_id: ID of the user doing the following
        following_id: ID of the user being followed
        created_at: When the follow was created
        request_accepted_at: When the follow request was accepted (for private accounts)
    """

    model_config = ConfigDict(frozen=True)

    follower_id: UUID4
    following_id: UUID4
    created_at: datetime
    request_accepted_at: datetime | None = None


class FollowRequest(BaseModel):
    """Model representing a follow request for private accounts.

    This model contains information about a pending follow request.

    Attributes:
        requester_id: ID of the user requesting to follow
        target_id: ID of the user being requested to follow
        created_at: When the request was created
        status: Current status of the request
    """

    model_config = ConfigDict(frozen=True)

    requester_id: UUID4
    target_id: UUID4
    created_at: datetime
    status: FollowRequestStatus = FollowRequestStatus.PENDING
