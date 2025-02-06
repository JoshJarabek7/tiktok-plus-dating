from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4
from schemas.database_records import CreateFollowRecord

from app.api.auth import get_current_user
from app.models.user import User
from app.services.follow import (
    FollowCreationError,
    FollowError,
    FollowNotFoundError,
    FollowRequestError,
    FollowRequestNotFoundError,
    FollowService,
)

router = APIRouter(prefix="/follow", tags=["follow"])
follow_service = FollowService()


@router.post("/user/{target_id}", response_model=CreateFollowRecord)
async def follow_user(
    target_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CreateFollowRecord:
    """Follow a user.

    Args:
        target_id: ID of the user to follow
        current_user: The authenticated user

    Returns:
        The created follow relationship record

    Raises:
        HTTPException: If follow creation fails
    """
    if target_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot follow yourself",
        )

    try:
        return await follow_service.follow_user(current_user.user_id, target_id)
    except FollowCreationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/user/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
    target_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Unfollow a user.

    Args:
        target_id: ID of the user to unfollow
        current_user: The authenticated user

    Raises:
        HTTPException: If unfollow fails
    """
    try:
        await follow_service.unfollow_user(current_user.user_id, target_id)
    except FollowNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except FollowError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/request/{target_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept_follow_request(
    target_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Accept a follow request.

    Args:
        target_id: ID of the user who requested to follow
        current_user: The authenticated user

    Raises:
        HTTPException: If request acceptance fails
    """
    try:
        await follow_service.accept_request(target_id, current_user.user_id)
    except FollowRequestNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except FollowRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/request/{target_id}/deny", status_code=status.HTTP_204_NO_CONTENT)
async def deny_follow_request(
    target_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Deny a follow request.

    Args:
        target_id: ID of the user who requested to follow
        current_user: The authenticated user

    Raises:
        HTTPException: If request denial fails
    """
    try:
        await follow_service.deny_request(target_id, current_user.user_id)
    except FollowRequestNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except FollowRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}/followers", response_model=list[User])
async def get_followers(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Get a user's followers.

    Args:
        user_id: ID of the user
        current_user: The authenticated user
        limit: Maximum number of followers to return
        offset: Number of followers to skip

    Returns:
        List of users who follow the specified user

    Raises:
        HTTPException: If fetching followers fails
    """
    try:
        return await follow_service.get_followers(
            user_id,
            limit=limit,
            offset=offset,
        )
    except FollowError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}/following", response_model=list[User])
async def get_following(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Get users followed by a user.

    Args:
        user_id: ID of the user
        current_user: The authenticated user
        limit: Maximum number of followed users to return
        offset: Number of followed users to skip

    Returns:
        List of users followed by the specified user

    Raises:
        HTTPException: If fetching following fails
    """
    try:
        return await follow_service.get_following(
            user_id,
            limit=limit,
            offset=offset,
        )
    except FollowError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}/mutual", response_model=list[User])
async def get_mutual_follows(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Get users who mutually follow a user.

    Args:
        user_id: ID of the user
        current_user: The authenticated user
        limit: Maximum number of mutual follows to return
        offset: Number of mutual follows to skip

    Returns:
        List of users who mutually follow the specified user

    Raises:
        HTTPException: If fetching mutual follows fails
    """
    try:
        return await follow_service.get_mutual_follows(
            user_id,
            limit=limit,
            offset=offset,
        )
    except FollowError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
