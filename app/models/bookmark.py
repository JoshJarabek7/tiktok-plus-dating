from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict


class BookmarkBase(BaseModel):
    """Base model for bookmark data.

    This model contains the common fields shared between Bookmark and BookmarkCreate.

    Attributes:
        user_id: ID of the user creating the bookmark
        collection_id: ID of the collection to add the bookmark to
        notes: Optional notes about the bookmark
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID4
    collection_id: UUID4
    notes: str | None = None


class BookmarkCreate(BookmarkBase):
    """Model for creating a new bookmark.

    This model extends BookmarkBase with any fields required for bookmark creation.
    """

    pass


class Bookmark(BookmarkBase):
    """Model representing a bookmark in the system.

    This model contains all information about a bookmark including its
    relationships and metadata.

    Attributes:
        bookmark_id: Unique identifier for the bookmark
        post_id: ID of the post being bookmarked
        created_at: When the bookmark was created
    """

    model_config = ConfigDict(frozen=True)

    bookmark_id: UUID4
    post_id: UUID4
    created_at: datetime
