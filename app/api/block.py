from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4

from app.api.auth import get_current_user
from app.models.user import User
from app.services.block import (
    BlockError,
    BlockNotFoundError,
    BlockService,
    CreateBlockRecord,
)

router = APIRouter(prefix="/block", tags=["block"])
block_service = BlockService()


@router.post("/user/{target_id}", response_model=CreateBlockRecord)
async def block_user(
    target_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CreateBlockRecord:
    """Block a user.

    Args:
        target_id: ID of the user to block
        current_user: The authenticated user

    Returns:
        The created block relationship record

    Raises:
        HTTPException: If block creation fails
    """
    if target_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot block yourself",
        )

    try:
        return await block_service.block(current_user.user_id, target_id)
    except BlockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/user/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_user(
    target_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Unblock a user.

    Args:
        target_id: ID of the user to unblock
        current_user: The authenticated user

    Raises:
        HTTPException: If unblock fails
    """
    try:
        await block_service.unblock(current_user.user_id, target_id)
    except BlockNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except BlockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}/blocked", response_model=list[User])
async def get_blocked_users(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Get users blocked by a user.

    Args:
        user_id: ID of the user
        current_user: The authenticated user
        limit: Maximum number of blocked users to return
        offset: Number of blocked users to skip

    Returns:
        List of users blocked by the specified user

    Raises:
        HTTPException: If fetching blocked users fails or access denied
    """
    if user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view another user's blocked list",
        )

    try:
        return await block_service.get_blocked_users(
            user_id,
            limit=limit,
            offset=offset,
        )
    except BlockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/check/{target_id}", response_model=bool)
async def check_block_status(
    target_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> bool:
    """Check if a user is blocked.

    Args:
        target_id: ID of the user to check
        current_user: The authenticated user

    Returns:
        True if the target user is blocked, False otherwise

    Raises:
        HTTPException: If check fails
    """
    try:
        return await block_service.is_blocked(current_user.user_id, target_id)
    except BlockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
