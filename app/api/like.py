from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4

from app.api.auth import get_current_user
from app.models.like import ContentType, Like
from app.models.user import User
from app.services.like import LikeService

router = APIRouter(prefix="/like", tags=["like"])
like_service = LikeService()


@router.post("/post/{post_id}", response_model=Like)
async def like_post(
    post_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Like:
    """Like a post.

    Args:
        post_id: ID of the post to like
        current_user: The authenticated user

    Returns:
        The created like

    Raises:
        HTTPException: If like creation fails
    """
    try:
        return await like_service.like_post(
            current_user.user_id, post_id, ContentType.POST
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/post/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_post(
    post_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Unlike a post.

    Args:
        post_id: ID of the post to unlike
        current_user: The authenticated user

    Raises:
        HTTPException: If unlike fails
    """
    try:
        await like_service.unlike_post(current_user.user_id, post_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/post/{post_id}/users", response_model=list[User])
async def get_post_likers(
    post_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Get users who liked a post.

    Args:
        post_id: ID of the post
        current_user: The authenticated user
        limit: Maximum number of users to return
        offset: Number of users to skip

    Returns:
        List of users who liked the post

    Raises:
        HTTPException: If fetching likers fails
    """
    try:
        return await like_service.get_post_likers(
            post_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}/posts", response_model=list[Like])
async def get_user_likes(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Like]:
    """Get posts liked by a user.

    Args:
        user_id: ID of the user
        current_user: The authenticated user
        limit: Maximum number of likes to return
        offset: Number of likes to skip

    Returns:
        List of the user's likes

    Raises:
        HTTPException: If fetching likes fails
    """
    try:
        return await like_service.get_user_likes(
            user_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
