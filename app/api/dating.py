from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4

from app.api.auth import get_current_user
from app.models.dating import DatingFilter, DatingMatch, DatingProfile, Gender
from app.models.interaction import InteractionType
from app.models.user import User
from app.services.dating import ActionRecordingError, DatingService, MatchCreationError

router = APIRouter(prefix="/dating", tags=["dating"])
dating_service = DatingService()


@router.post("/profile", response_model=DatingProfile)
async def create_dating_profile(
    profile: DatingProfile,
    current_user: Annotated[User, Depends(get_current_user)],
) -> DatingProfile:
    """Create a new dating profile for the current user.

    Args:
        profile: The profile data to create
        current_user: The authenticated user

    Returns:
        The created dating profile

    Raises:
        HTTPException: If profile creation fails or user already has a profile
    """
    if profile.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create profile for another user",
        )

    try:
        return dating_service.create_dating_profile(profile)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/profile/{user_id}", response_model=DatingProfile)
async def get_dating_profile(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> DatingProfile:
    """Get a user's dating profile.

    Args:
        user_id: ID of the user whose profile to get
        current_user: The authenticated user

    Returns:
        The requested dating profile

    Raises:
        HTTPException: If profile not found or access denied
    """
    try:
        profile = dating_service.get_dating_profile(user_id)
        # Record profile view if viewing someone else's profile
        if user_id != current_user.user_id:
            dating_service.record_profile_view(current_user.user_id, user_id)
        return profile
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.put("/profile/{user_id}", response_model=DatingProfile)
async def update_dating_profile(
    user_id: UUID4,
    profile: DatingProfile,
    current_user: Annotated[User, Depends(get_current_user)],
) -> DatingProfile:
    """Update a user's dating profile.

    Args:
        user_id: ID of the user whose profile to update
        profile: The updated profile data
        current_user: The authenticated user

    Returns:
        The updated dating profile

    Raises:
        HTTPException: If update fails or user not authorized
    """
    if user_id != current_user.user_id or profile.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update another user's profile",
        )

    try:
        return dating_service.update_dating_profile(profile)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/matches", response_model=list[DatingProfile])
async def get_potential_matches(
    current_user: Annotated[User, Depends(get_current_user)],
    max_distance: Annotated[float, Query(ge=1, le=100)] = 50,
    min_age: Annotated[int, Query(ge=18, le=100)] = 18,
    max_age: Annotated[int, Query(ge=18, le=100)] = 100,
    gender_preference: list[Gender] | None = None,
    exclude_seen: bool = True,
    exclude_matched: bool = True,
    min_compatibility: Annotated[float, Query(ge=0, le=1)] = 0.0,
) -> list[DatingProfile]:
    """Get potential dating matches for the current user.

    Args:
        current_user: The authenticated user
        max_distance: Maximum distance in miles
        min_age: Minimum age for matches
        max_age: Maximum age for matches
        gender_preference: List of acceptable genders
        exclude_seen: Whether to exclude previously seen profiles
        exclude_matched: Whether to exclude existing matches
        min_compatibility: Minimum compatibility score required

    Returns:
        List of potential matches ordered by compatibility

    Raises:
        HTTPException: If match finding fails
    """
    try:
        filters = DatingFilter(
            max_distance_miles=max_distance,
            min_age=min_age,
            max_age=max_age,
            gender_preference=gender_preference,
            exclude_seen=exclude_seen,
            exclude_matched=exclude_matched,
            min_compatibility=min_compatibility,
        )
        return dating_service.get_potential_matches(current_user.user_id, filters)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/action/{target_id}", response_model=DatingMatch | None)
async def record_dating_action(
    target_id: UUID4,
    action: InteractionType,
    current_user: Annotated[User, Depends(get_current_user)],
) -> DatingMatch | None:
    """Record a dating action (like/pass/super) for a profile.

    Args:
        target_id: ID of the profile being acted on
        action: The action being taken (like/pass/super)
        current_user: The authenticated user

    Returns:
        DatingMatch if mutual match created, None otherwise

    Raises:
        HTTPException: If action recording fails
    """
    if action not in {
        InteractionType.SWIPE_RIGHT,
        InteractionType.SWIPE_LEFT,
        InteractionType.SUPER_LIKE,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid dating action",
        )

    try:
        return await dating_service.record_dating_action(
            current_user.user_id, target_id, action
        )
    except ActionRecordingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except MatchCreationError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/matches/mutual", response_model=list[DatingMatch])
async def get_mutual_matches(
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DatingMatch]:
    """Get the user's mutual matches (both users liked each other).

    Args:
        current_user: The authenticated user
        limit: Maximum number of matches to return
        offset: Number of matches to skip

    Returns:
        List of mutual matches ordered by match date

    Raises:
        HTTPException: If fetching matches fails
    """
    try:
        return dating_service.get_mutual_matches(
            current_user.user_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
