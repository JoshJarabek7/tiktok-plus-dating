from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field


class BookmarkCollectionBase(BaseModel):
    """Base model for bookmark collection data.

    This model contains the common fields shared between BookmarkCollection
    and BookmarkCollectionCreate.

    Attributes:
        title: Name of the collection
        owned_by: ID of the user who owns the collection
    """

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    owned_by: UUID4


class BookmarkCollectionCreate(BookmarkCollectionBase):
    """Model for creating a new bookmark collection.

    This model extends BookmarkCollectionBase with any fields required
    for collection creation.
    """

    pass


class BookmarkCollection(BookmarkCollectionBase):
    """Model representing a collection of bookmarked posts.

    This model contains information about a user's bookmark collection including
    metadata and engagement metrics.

    Attributes:
        collection_id: Unique identifier for the collection
        title: Name of the collection
        owned_by: ID of the user who owns the collection
        bookmark_count: Number of bookmarks in the collection
        updated_at: When the collection was last updated
        created_at: When the collection was created
    """

    model_config = ConfigDict(frozen=True)

    collection_id: UUID4
    bookmark_count: int = Field(default=0, ge=0)
    updated_at: datetime
    created_at: datetime
