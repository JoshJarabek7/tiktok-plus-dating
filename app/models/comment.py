from pydantic import UUID4, BaseModel, ConfigDict, Field


class CommentBase(BaseModel):
    """Base model for comment data.

    This model contains the common fields shared between Comment, CommentCreate,
    and CommentUpdate models.

    Attributes:
        content: The text content of the comment
    """

    model_config = ConfigDict(frozen=True)

    content: str = Field(min_length=1)


class CommentCreate(CommentBase):
    """Model for creating a new comment.

    This model extends CommentBase with fields required for comment creation.

    Attributes:
        creator_id: ID of the user creating the comment
        post_id: ID of the post being commented on
        in_reply_to: Optional ID of parent comment if this is a reply
    """

    creator_id: UUID4
    post_id: UUID4
    in_reply_to: UUID4 | None = None


class CommentUpdate(CommentBase):
    """Model for updating an existing comment.

    This model extends CommentBase with fields that can be updated.
    Currently only the content can be updated.
    """

    pass


class Comment(CommentBase):
    """Model representing a comment on a post.

    This model contains all information about a comment including its content,
    relationships to other entities, and engagement metrics.

    Attributes:
        comment_id: Unique identifier for the comment
        user_id: ID of the user who created the comment
        post_id: ID of the post being commented on
        content: The text content of the comment
        in_reply_to: ID of parent comment if this is a reply
        like_count: Number of likes on the comment
        reply_count: Number of replies to this comment
    """

    model_config = ConfigDict(frozen=True)

    comment_id: UUID4
    user_id: UUID4
    post_id: UUID4
    in_reply_to: UUID4 | None = None
    like_count: int = Field(default=0, ge=0)
    reply_count: int = Field(default=0, ge=0)
