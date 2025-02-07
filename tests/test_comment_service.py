from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.comment import Comment, CommentCreate, CommentUpdate
from app.models.post import Post
from app.models.user import User
from app.services.comment import (
    CommentCreationError,
    CommentDeletionError,
    CommentError,
    CommentNotFoundError,
    CommentService,
    CommentUpdateError,
)


@pytest.mark.unit
class TestCommentService:
    @pytest.fixture
    def test_comment(self, test_user: User, test_post: Post) -> Comment:
        current_time = datetime.now(UTC)
        return Comment(
            comment_id=uuid4(),
            user_id=test_user.user_id,
            post_id=test_post.post_id,
            content="Test comment",
            like_count=0,
            reply_count=0,
        )

    @pytest.mark.asyncio
    async def test_create_comment_success(
        self,
        comment_service: CommentService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        comment_create = CommentCreate(
            creator_id=test_user.user_id,
            content="Test comment",
            post_id=test_post.post_id,
        )
        with patch.object(comment_service, "_create_comment") as mock_create:
            mock_create.return_value = Comment(
                comment_id=uuid4(),
                user_id=test_user.user_id,
                post_id=test_post.post_id,
                content="Test comment",
                like_count=0,
                reply_count=0,
            )

            # Act
            result = await comment_service.create_comment(
                test_post.post_id, comment_create
            )

            # Assert
            assert isinstance(result, Comment)
            assert result.user_id == test_user.user_id
            assert result.post_id == test_post.post_id
            assert result.content == "Test comment"
            mock_create.assert_called_once_with(test_post.post_id, comment_create)

    @pytest.mark.asyncio
    async def test_create_comment_failure(
        self,
        comment_service: CommentService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        comment_create = CommentCreate(
            creator_id=test_user.user_id,
            content="Test comment",
            post_id=test_post.post_id,
        )
        with patch.object(comment_service, "_create_comment") as mock_create:
            mock_create.side_effect = CommentCreationError("Failed to create comment")

            # Act & Assert
            with pytest.raises(CommentCreationError):
                await comment_service.create_comment(test_post.post_id, comment_create)

    @pytest.mark.asyncio
    async def test_get_comment_success(
        self,
        comment_service: CommentService,
        test_comment: Comment,
    ):
        # Arrange
        with patch.object(comment_service, "_get_comment") as mock_get:
            mock_get.return_value = test_comment

            # Act
            result = await comment_service.get_comment(test_comment.comment_id)

            # Assert
            assert result == test_comment
            mock_get.assert_called_once_with(test_comment.comment_id)

    @pytest.mark.asyncio
    async def test_get_comment_not_found(
        self,
        comment_service: CommentService,
    ):
        # Arrange
        comment_id = uuid4()
        with patch.object(comment_service, "_get_comment") as mock_get:
            mock_get.side_effect = CommentNotFoundError("Comment not found")

            # Act & Assert
            with pytest.raises(CommentNotFoundError):
                await comment_service.get_comment(comment_id)

    @pytest.mark.asyncio
    async def test_update_comment_success(
        self,
        comment_service: CommentService,
        test_comment: Comment,
    ):
        # Arrange
        update = CommentUpdate(content="Updated comment")
        with patch.object(comment_service, "_update_comment") as mock_update:
            mock_update.return_value = Comment(
                **{
                    **test_comment.model_dump(),
                    "content": update.content,
                }
            )

            # Act
            result = await comment_service.update_comment(
                test_comment.comment_id, update
            )

            # Assert
            assert result.content == update.content
            mock_update.assert_called_once_with(test_comment.comment_id, update)

    @pytest.mark.asyncio
    async def test_update_comment_not_found(
        self,
        comment_service: CommentService,
    ):
        # Arrange
        comment_id = uuid4()
        update = CommentUpdate(content="Updated comment")
        with patch.object(comment_service, "_update_comment") as mock_update:
            mock_update.side_effect = CommentNotFoundError("Comment not found")

            # Act & Assert
            with pytest.raises(CommentNotFoundError):
                await comment_service.update_comment(comment_id, update)

    @pytest.mark.asyncio
    async def test_delete_comment_success(
        self,
        comment_service: CommentService,
        test_comment: Comment,
    ):
        # Arrange
        with patch.object(comment_service, "_delete_comment") as mock_delete:
            # Act
            await comment_service.delete_comment(test_comment.comment_id)

            # Assert
            mock_delete.assert_called_once_with(test_comment.comment_id)

    @pytest.mark.asyncio
    async def test_delete_comment_not_found(
        self,
        comment_service: CommentService,
    ):
        # Arrange
        comment_id = uuid4()
        with patch.object(comment_service, "_delete_comment") as mock_delete:
            mock_delete.side_effect = CommentNotFoundError("Comment not found")

            # Act & Assert
            with pytest.raises(CommentNotFoundError):
                await comment_service.delete_comment(comment_id)

    @pytest.mark.asyncio
    async def test_get_post_comments_success(
        self,
        comment_service: CommentService,
        test_post: Post,
        test_comment: Comment,
    ):
        # Arrange
        with patch.object(comment_service, "_get_post_comments") as mock_get:
            mock_get.return_value = [test_comment]

            # Act
            result = await comment_service.get_post_comments(test_post.post_id)

            # Assert
            assert len(result) == 1
            assert result[0] == test_comment
            mock_get.assert_called_once_with(test_post.post_id, 50, 0)

    @pytest.mark.asyncio
    async def test_get_post_comments_with_pagination(
        self,
        comment_service: CommentService,
        test_post: Post,
    ):
        # Arrange
        limit = 10
        offset = 5
        with patch.object(comment_service, "_get_post_comments") as mock_get:
            mock_get.return_value = []

            # Act
            await comment_service.get_post_comments(
                test_post.post_id, limit=limit, offset=offset
            )

            # Assert
            mock_get.assert_called_once_with(test_post.post_id, limit, offset)

    @pytest.mark.asyncio
    async def test_get_user_comments_success(
        self,
        comment_service: CommentService,
        test_user: User,
        test_comment: Comment,
    ):
        # Arrange
        with patch.object(comment_service, "_get_user_comments") as mock_get:
            mock_get.return_value = [test_comment]

            # Act
            result = await comment_service.get_user_comments(test_user.user_id)

            # Assert
            assert len(result) == 1
            assert result[0] == test_comment
            mock_get.assert_called_once_with(test_user.user_id, 50, 0)

    @pytest.mark.asyncio
    async def test_get_user_comments_with_pagination(
        self,
        comment_service: CommentService,
        test_user: User,
    ):
        # Arrange
        limit = 10
        offset = 5
        with patch.object(comment_service, "_get_user_comments") as mock_get:
            mock_get.return_value = []

            # Act
            await comment_service.get_user_comments(
                test_user.user_id, limit=limit, offset=offset
            )

            # Assert
            mock_get.assert_called_once_with(test_user.user_id, limit, offset)

    @pytest.mark.asyncio
    async def test_get_user_comments_error(
        self,
        comment_service: CommentService,
        test_user: User,
    ):
        # Arrange
        with patch.object(comment_service, "_get_user_comments") as mock_get:
            mock_get.side_effect = CommentError("Failed to get user comments")

            # Act & Assert
            with pytest.raises(CommentError):
                await comment_service.get_user_comments(test_user.user_id)
