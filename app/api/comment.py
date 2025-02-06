from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import UUID4

from app.api.auth import get_current_user
from app.models.comment import Comment, CommentCreate, CommentUpdate
from app.models.user import User
from app.services.comment import (
    CommentCreationError,
    CommentDeletionError,
    CommentError,
    CommentNotFoundError,
    CommentService,
    CommentUpdateError,
)

router = APIRouter(prefix="/comment", tags=["comment"])
comment_service = CommentService()


@router.post("/post/{post_id}", response_model=Comment)
async def create_comment(
    post_id: UUID4,
    comment: CommentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Comment:
    """Create a new comment on a post.

    Args:
        post_id: ID of the post to comment on
        comment: The comment data
        current_user: The authenticated user

    Returns:
        The created comment

    Raises:
        HTTPException: If comment creation fails
    """
    if comment.creator_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create comment for another user",
        )

    try:
        return await comment_service.create_comment(post_id, comment)
    except CommentCreationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{comment_id}", response_model=Comment)
async def get_comment(
    comment_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Comment:
    """Get a comment by ID.

    Args:
        comment_id: ID of the comment to get
        current_user: The authenticated user

    Returns:
        The requested comment

    Raises:
        HTTPException: If comment not found
    """
    try:
        return await comment_service.get_comment(comment_id)
    except CommentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.put("/{comment_id}", response_model=Comment)
async def update_comment(
    comment_id: UUID4,
    comment: CommentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Comment:
    """Update a comment.

    Args:
        comment_id: ID of the comment to update
        comment: The updated comment data
        current_user: The authenticated user

    Returns:
        The updated comment

    Raises:
        HTTPException: If update fails or user not authorized
    """
    try:
        existing = await comment_service.get_comment(comment_id)
        if existing.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update another user's comment",
            )
        return await comment_service.update_comment(comment_id, comment)
    except CommentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CommentUpdateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete a comment.

    Args:
        comment_id: ID of the comment to delete
        current_user: The authenticated user

    Raises:
        HTTPException: If deletion fails or user not authorized
    """
    try:
        existing = await comment_service.get_comment(comment_id)
        if existing.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete another user's comment",
            )
        await comment_service.delete_comment(comment_id)
    except CommentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except CommentDeletionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/post/{post_id}", response_model=list[Comment])
async def get_post_comments(
    post_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Comment]:
    """Get comments on a post.

    Args:
        post_id: ID of the post
        current_user: The authenticated user
        limit: Maximum number of comments to return
        offset: Number of comments to skip

    Returns:
        List of comments on the post

    Raises:
        HTTPException: If fetching comments fails
    """
    try:
        return await comment_service.get_post_comments(
            post_id,
            limit=limit,
            offset=offset,
        )
    except CommentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}", response_model=list[Comment])
async def get_user_comments(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Comment]:
    """Get comments by a user.

    Args:
        user_id: ID of the user
        current_user: The authenticated user
        limit: Maximum number of comments to return
        offset: Number of comments to skip

    Returns:
        List of the user's comments

    Raises:
        HTTPException: If fetching comments fails
    """
    try:
        return await comment_service.get_user_comments(
            user_id,
            limit=limit,
            offset=offset,
        )
    except CommentError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
