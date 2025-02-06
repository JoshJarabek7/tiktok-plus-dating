from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4

from app.api.auth import get_current_user
from app.models.user import User
from app.services.profile import (
    ProfileAccessError,
    ProfileError,
    ProfileNotFoundError,
    ProfileService,
    ProfileUpdateError,
)

router = APIRouter(prefix="/profile", tags=["profile"])
profile_service = ProfileService()


@router.get("/me", response_model=User)
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get the current user's profile.

    Args:
        current_user: The authenticated user

    Returns:
        The user's profile

    Raises:
        HTTPException: If profile not found
    """
    try:
        return await profile_service.get_profile(current_user.user_id)
    except ProfileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/{user_id}", response_model=User)
async def get_profile(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get a user's profile.

    Args:
        user_id: ID of the user whose profile to get
        current_user: The authenticated user

    Returns:
        The requested user's profile

    Raises:
        HTTPException: If profile not found or access denied
    """
    try:
        return await profile_service.get_profile(user_id, current_user.user_id)
    except ProfileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ProfileAccessError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.put("/me", response_model=User)
async def update_my_profile(
    profile: User,
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Update the current user's profile.

    Args:
        profile: The updated profile data
        current_user: The authenticated user

    Returns:
        The updated profile

    Raises:
        HTTPException: If update fails
    """
    if profile.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update another user's profile",
        )

    try:
        return await profile_service.update_profile(
            user_id=profile.user_id,
            display_name=profile.display_name,
            email=profile.email,
            bio=profile.bio,
            is_private=profile.is_private,
            profile_picture_s3_key=profile.profile_picture_s3_key,
        )
    except ProfileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ProfileUpdateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/{user_id}/location", response_model=User)
async def update_location(
    user_id: UUID4,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Update a user's location.

    Args:
        user_id: ID of the user whose location to update
        latitude: New latitude
        longitude: New longitude
        current_user: The authenticated user

    Returns:
        The updated profile

    Raises:
        HTTPException: If update fails or user not authorized
    """
    if user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update another user's location",
        )

    try:
        return await profile_service.update_location(user_id, latitude, longitude)
    except ProfileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ProfileUpdateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/search", response_model=list[User])
async def search_profiles(
    query: str,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Search for user profiles.

    Args:
        query: Search query string
        current_user: The authenticated user
        limit: Maximum number of results to return
        offset: Number of results to skip

    Returns:
        List of matching profiles

    Raises:
        HTTPException: If search fails
    """
    try:
        return await profile_service.search_profiles(query, limit=limit, offset=offset)
    except ProfileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ProfileError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
