from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field


class PostBase(BaseModel):
    """Base model for post data.

    This model contains the common fields shared between Post, PostCreate,
    and PostUpdate models.

    Attributes:
        title: Optional title of the post
        description: Optional description of the post
        hashtags: List of hashtags used in the post
        is_private: Whether the post is private
        allows_comments: Whether comments are allowed
    """

    model_config = ConfigDict(frozen=True)

    title: str | None = Field(None, description="Optional title of the post")
    description: str | None = Field(
        None, description="Optional description of the post"
    )
    hashtags: list[str] = Field(
        default=[], description="List of hashtags used in the post"
    )
    is_private: bool = Field(default=False, description="Whether the post is private")
    allows_comments: bool = Field(
        default=True, description="Whether comments are allowed"
    )


class PostCreate(PostBase):
    """Model for creating a new post.

    This model extends PostBase with fields required for post creation.

    Attributes:
        creator_id: ID of the user creating the post
    """

    creator_id: UUID4 = Field(description="ID of the user creating the post")


class PostUpdate(PostBase):
    """Model for updating an existing post.

    This model extends PostBase with fields that can be updated.
    """

    pass


class Post(PostBase):
    """Model representing a video post in the system.

    This model contains all information about a video post including metadata,
    engagement metrics, and content details.

    Attributes:
        post_id: Unique identifier for the post
        creator_id: ID of the user who created the post
        video_s3_key: S3 key for the video file
        thumbnail_s3_key: S3 key for the thumbnail image
        duration_seconds: Duration of the video in seconds
        created_at: When the post was created
        view_count: Number of views
        like_count: Number of likes
        comment_count: Number of comments
        share_count: Number of shares
    """

    model_config = ConfigDict(frozen=True)

    post_id: UUID4 = Field(description="Unique identifier for the post")
    creator_id: UUID4 = Field(description="ID of the user who created the post")
    video_s3_key: str = Field(description="S3 key for the video file")
    thumbnail_s3_key: str = Field(description="S3 key for the thumbnail image")
    duration_seconds: float = Field(
        gt=0, description="Duration of the video in seconds"
    )
    created_at: datetime = Field(description="When the post was created")
    # Engagement Metrics
    view_count: int = Field(default=0, ge=0, description="Number of views")
    like_count: int = Field(default=0, ge=0, description="Number of likes")
    comment_count: int = Field(default=0, ge=0, description="Number of comments")
    share_count: int = Field(default=0, ge=0, description="Number of shares")
