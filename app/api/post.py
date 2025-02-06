from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import UUID4

from app.api.auth import get_current_user
from app.models.post import Post, PostCreate, PostUpdate
from app.models.user import User
from app.services.post import PostService

router = APIRouter(prefix="/post", tags=["post"])
post_service = PostService()


@router.post("", response_model=Post)
async def create_post(
    post: PostCreate,
    video: UploadFile,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Post:
    """Create a new video post.

    Args:
        post: The post metadata
        video: The video file to upload
        current_user: The authenticated user

    Returns:
        The created post

    Raises:
        HTTPException: If post creation fails
    """
    if post.creator_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create post for another user",
        )

    try:
        return await post_service.create_post(post, video)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{post_id}", response_model=Post)
async def get_post(
    post_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Post:
    """Get a post by ID.

    Args:
        post_id: ID of the post to get
        current_user: The authenticated user

    Returns:
        The requested post

    Raises:
        HTTPException: If post not found or access denied
    """
    try:
        return await post_service.get_post(post_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.put("/{post_id}", response_model=Post)
async def update_post(
    post_id: UUID4,
    post: PostUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Post:
    """Update a post.

    Args:
        post_id: ID of the post to update
        post: The updated post data
        current_user: The authenticated user

    Returns:
        The updated post

    Raises:
        HTTPException: If update fails or user not authorized
    """
    try:
        existing = await post_service.get_post(post_id)
        if existing.creator_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update another user's post",
            )
        return await post_service.update_post(post_id, post)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete a post.

    Args:
        post_id: ID of the post to delete
        current_user: The authenticated user

    Raises:
        HTTPException: If deletion fails or user not authorized
    """
    try:
        existing = await post_service.get_post(post_id)
        if existing.creator_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete another user's post",
            )
        await post_service.delete_post(post_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/feed", response_model=list[Post])
async def get_feed(
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Post]:
    """Get the user's personalized feed.

    Args:
        current_user: The authenticated user
        limit: Maximum number of posts to return
        offset: Number of posts to skip

    Returns:
        List of posts for the user's feed

    Raises:
        HTTPException: If feed generation fails
    """
    try:
        return await post_service.get_feed(
            current_user.user_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/user/{user_id}", response_model=list[Post])
async def get_user_posts(
    user_id: UUID4,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Post]:
    """Get a user's posts.

    Args:
        user_id: ID of the user whose posts to get
        current_user: The authenticated user
        limit: Maximum number of posts to return
        offset: Number of posts to skip

    Returns:
        List of the user's posts

    Raises:
        HTTPException: If fetching posts fails
    """
    try:
        return await post_service.get_user_posts(
            user_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/search", response_model=list[Post])
async def search_posts(
    query: str,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Post]:
    """Search for posts.

    This endpoint provides personalized search results based on:
    1. Text match relevance
    2. Content similarity to user's interests
    3. Creator similarity
    4. Engagement metrics
    5. Recency

    Args:
        query: Search query string
        current_user: The authenticated user
        limit: Maximum number of results to return
        offset: Number of results to skip

    Returns:
        List of matching posts ordered by relevance

    Raises:
        HTTPException: If search fails
    """
    try:
        return await post_service.search_posts(
            query,
            current_user.user_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
