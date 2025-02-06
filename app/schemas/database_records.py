from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field

from app.models.follow import FollowRequestStatus
from app.models.post import Post
from app.models.user import User


class BaseRelationship(BaseModel):
    """Base class for all relationships, containing common fields.

    Attributes:
        created_at: When the relationship was created
    """

    model_config = ConfigDict(frozen=True)

    created_at: datetime = Field(description="When the relationship was created")


class FollowRelationship(BaseRelationship):
    """Represents a FOLLOWS relationship with optional request acceptance time.

    Attributes:
        request_accepted_at: When the follow request was accepted, if applicable
    """

    request_accepted_at: datetime | None = Field(
        None, description="When the follow request was accepted, if applicable"
    )


class FollowRequestRelationship(BaseRelationship):
    """Represents a REQUESTED_TO_FOLLOW relationship.

    Attributes:
        status: Current status of the request
    """

    status: FollowRequestStatus = Field(description="Current status of the request")


class CreateFollowRecord(BaseModel):
    """Response model for follow/follow request creation.

    Attributes:
        success: Whether the operation was successful
        follower: The user doing the following
        following: The user being followed
        relationship: The created follow relationship
        is_direct_follow: Whether this was a direct follow or a request
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(description="Whether the operation was successful")
    follower: User = Field(description="The user doing the following")
    following: User = Field(description="The user being followed")
    relationship: FollowRelationship | FollowRequestRelationship = Field(
        description="The created follow relationship"
    )
    is_direct_follow: bool = Field(
        description="Whether this was a direct follow or a request"
    )


class FollowRequestRecord(BaseModel):
    """Represents a follow request record.

    Attributes:
        requester: The user requesting to follow
        target: The user being requested to follow
        relationship: The follow request relationship
    """

    model_config = ConfigDict(frozen=True)

    requester: User = Field(description="The user requesting to follow")
    target: User = Field(description="The user being requested to follow")
    relationship: FollowRequestRelationship = Field(
        description="The follow request relationship"
    )


class AcceptFollowRequestRecord(BaseModel):
    """Response model for when a follow request is accepted.

    Attributes:
        success: Whether the operation was successful
        follower: The user doing the following
        following: The user being followed
        relationship: The accepted follow relationship
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(description="Whether the operation was successful")
    follower: User = Field(description="The user doing the following")
    following: User = Field(description="The user being followed")
    relationship: FollowRelationship = Field(
        description="The accepted follow relationship"
    )


class RemoveFollowRecord(BaseModel):
    """Keeps track of the success of an unfollow operation.

    Attributes:
        success: Whether the operation was successful
        follower_exists: Whether the follower user still exists
        following_exists: Whether the followed user still exists
        follower: The user who was following
        following: The user who was being followed
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(description="Whether the operation was successful")
    follower_exists: bool = Field(description="Whether the follower user still exists")
    following_exists: bool = Field(description="Whether the followed user still exists")
    follower: User = Field(description="The user who was following")
    following: User = Field(description="The user who was being followed")


# Your existing block and post records can remain the same
class CreateBlockRecord(BaseModel):
    """Record of a block relationship creation.

    Attributes:
        success: Whether the operation was successful
        blocked_user_id: ID of the user who was blocked
        removed_forward_follow: Whether a follow from blocker to blocked was removed
        removed_reverse_follow: Whether a follow from blocked to blocker was removed
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(description="Whether the operation was successful")
    blocked_user_id: UUID4 = Field(description="ID of the user who was blocked")
    removed_forward_follow: bool = Field(
        description="Whether a follow from blocker to blocked was removed"
    )
    removed_reverse_follow: bool = Field(
        description="Whether a follow from blocked to blocker was removed"
    )


class RemoveBlockRecord(BaseModel):
    """Record of a block relationship removal.

    Attributes:
        success: Whether the operation was successful
        blocker_exists: Whether the blocking user still exists
        blockee_exists: Whether the blocked user still exists
        blocker: The user who had blocked
        blockee: The user who was blocked
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(description="Whether the operation was successful")
    blocker_exists: bool = Field(description="Whether the blocking user still exists")
    blockee_exists: bool = Field(description="Whether the blocked user still exists")
    blocker: User = Field(description="The user who had blocked")
    blockee: User = Field(description="The user who was blocked")


class CreatePostRecord(BaseModel):
    """Record of a post creation.

    Attributes:
        success: Whether the operation was successful
        post: The created post
        creator: The user who created the post
        relationship: The post creation relationship
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(description="Whether the operation was successful")
    post: Post = Field(description="The created post")
    creator: User = Field(description="The user who created the post")
    relationship: BaseRelationship = Field(description="The post creation relationship")
