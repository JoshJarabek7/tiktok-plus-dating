from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4

from app.api.auth import get_current_user
from app.models.bookmark import Bookmark, BookmarkCreate
from app.models.post import Post
from app.models.user import User
from app.services.bookmark import BookmarkError, BookmarkNotFoundError, BookmarkService

router = APIRouter(prefix="/bookmark", tags=["bookmark"])
bookmark_service = BookmarkService()


@router.post("/post/{post_id}", response_model=Bookmark)
async def bookmark_post(
    post_id: UUID4,
    bookmark: BookmarkCreate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Bookmark:
    """Bookmark a post.

    Args:
        post_id: ID of the post to bookmark
        bookmark: The bookmark data
        current_user: The authenticated user

    Returns:
        The created bookmark

    Raises:
        HTTPException: If bookmark creation fails
    """
    if bookmark.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create bookmark for another user",
        )

    try:
        return await bookmark_service.create_bookmark(post_id, bookmark)
    except BookmarkError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/post/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bookmark(
    post_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Remove a bookmark.

    Args:
        post_id: ID of the post to unbookmark
        current_user: The authenticated user

    Raises:
        HTTPException: If bookmark removal fails
    """
    try:
        await bookmark_service.remove_bookmark(current_user.user_id, post_id)
    except BookmarkNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except BookmarkError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/post/{post_id}/check", response_model=bool)
async def check_bookmark(
    post_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> bool:
    """Check if a post is bookmarked.

    Args:
        post_id: ID of the post to check
        current_user: The authenticated user

    Returns:
        True if the post is bookmarked, False otherwise

    Raises:
        HTTPException: If check fails
    """
    try:
        return await bookmark_service.is_bookmarked(current_user.user_id, post_id)
    except BookmarkError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}/posts", response_model=list[Post])
async def get_bookmarked_posts(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Post]:
    """Get posts bookmarked by a user.

    Args:
        user_id: ID of the user
        current_user: The authenticated user
        limit: Maximum number of posts to return
        offset: Number of posts to skip

    Returns:
        List of bookmarked posts

    Raises:
        HTTPException: If fetching bookmarks fails or access denied
    """
    if user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view another user's bookmarks",
        )

    try:
        return await bookmark_service.get_bookmarked_posts(
            user_id,
            limit=limit,
            offset=offset,
        )
    except BookmarkError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
