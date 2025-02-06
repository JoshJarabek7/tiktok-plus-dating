from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4

from app.api.auth import get_current_user
from app.models.bookmark import Bookmark
from app.models.bookmark_collection import BookmarkCollection, BookmarkCollectionCreate
from app.models.user import User
from app.services.bookmark_collection import (
    CollectionError,
    CollectionNotFoundError,
    CollectionService,
    CollectionUpdateError,
)

router = APIRouter(prefix="/bookmark/collection", tags=["bookmark_collection"])
collection_service = CollectionService()


@router.post("", response_model=BookmarkCollection)
async def create_collection(
    collection: BookmarkCollectionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> BookmarkCollection:
    """Create a new bookmark collection.

    Args:
        collection: The collection data
        current_user: The authenticated user

    Returns:
        The created collection

    Raises:
        HTTPException: If collection creation fails
    """
    if collection.owned_by != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create collection for another user",
        )

    try:
        return await collection_service.create(collection, current_user.user_id)
    except CollectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{collection_id}", response_model=BookmarkCollection)
async def get_collection(
    collection_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> BookmarkCollection:
    """Get a bookmark collection.

    Args:
        collection_id: ID of the collection to get
        current_user: The authenticated user

    Returns:
        The requested collection

    Raises:
        HTTPException: If collection not found or access denied
    """
    try:
        collection = await collection_service.get_collection(collection_id)
        if collection.owned_by != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot view another user's collection",
            )
        return collection
    except CollectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CollectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/{collection_id}", response_model=BookmarkCollection)
async def update_collection(
    collection_id: UUID4,
    collection: BookmarkCollection,
    current_user: Annotated[User, Depends(get_current_user)],
) -> BookmarkCollection:
    """Update a bookmark collection.

    Args:
        collection_id: ID of the collection to update
        collection: The updated collection data
        current_user: The authenticated user

    Returns:
        The updated collection

    Raises:
        HTTPException: If update fails or user not authorized
    """
    if collection.owned_by != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update another user's collection",
        )

    try:
        return await collection_service.update_collection(collection_id, collection)
    except CollectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CollectionUpdateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete a bookmark collection.

    Args:
        collection_id: ID of the collection to delete
        current_user: The authenticated user

    Raises:
        HTTPException: If deletion fails or user not authorized
    """
    try:
        collection = await collection_service.get_collection(collection_id)
        if collection.owned_by != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete another user's collection",
            )
        await collection_service.delete(collection_id, current_user.user_id)
    except CollectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CollectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{collection_id}/bookmark/{bookmark_id}")
async def add_bookmark_to_collection(
    collection_id: UUID4,
    bookmark_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Add a bookmark to a collection.

    Args:
        collection_id: ID of the collection
        bookmark_id: ID of the bookmark to add
        current_user: The authenticated user

    Raises:
        HTTPException: If addition fails or user not authorized
    """
    try:
        collection = await collection_service.get_collection(collection_id)
        if collection.owned_by != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify another user's collection",
            )
        await collection_service.add_bookmark(collection_id, bookmark_id)
    except CollectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CollectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{collection_id}/bookmark/{bookmark_id}")
async def remove_bookmark_from_collection(
    collection_id: UUID4,
    bookmark_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Remove a bookmark from a collection.

    Args:
        collection_id: ID of the collection
        bookmark_id: ID of the bookmark to remove
        current_user: The authenticated user

    Raises:
        HTTPException: If removal fails or user not authorized
    """
    try:
        collection = await collection_service.get_collection(collection_id)
        if collection.owned_by != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify another user's collection",
            )
        await collection_service.remove_bookmark(collection_id, bookmark_id)
    except CollectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CollectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{collection_id}/bookmarks", response_model=list[Bookmark])
async def get_collection_bookmarks(
    collection_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Bookmark]:
    """Get bookmarks in a collection.

    Args:
        collection_id: ID of the collection
        current_user: The authenticated user
        limit: Maximum number of bookmarks to return
        offset: Number of bookmarks to skip

    Returns:
        List of bookmarks in the collection

    Raises:
        HTTPException: If fetching bookmarks fails or access denied
    """
    try:
        collection = await collection_service.get_collection(collection_id)
        if collection.owned_by != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot view another user's collection",
            )
        return await collection_service.get_collection_bookmarks(
            collection_id,
            limit=limit,
            offset=offset,
        )
    except CollectionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CollectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}", response_model=list[BookmarkCollection])
async def get_user_collections(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BookmarkCollection]:
    """Get a user's bookmark collections.

    Args:
        user_id: ID of the user
        current_user: The authenticated user
        limit: Maximum number of collections to return
        offset: Number of collections to skip

    Returns:
        List of the user's bookmark collections

    Raises:
        HTTPException: If fetching collections fails or access denied
    """
    if user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view another user's collections",
        )

    try:
        return await collection_service.get_user_collections(
            user_id,
            limit=limit,
            offset=offset,
        )
    except CollectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
