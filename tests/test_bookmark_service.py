from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.bookmark import Bookmark, BookmarkCreate
from app.models.post import Post
from app.models.user import User
from app.services.bookmark import BookmarkError, BookmarkNotFoundError, BookmarkService


@pytest.mark.unit
class TestBookmarkService:
    @pytest.fixture
    def test_post(self) -> Post:
        return Post(
            post_id=uuid4(),
            creator_id=uuid4(),
            title="Test Post",
            description="Test Description",
            video_s3_key="test_video.mp4",
            thumbnail_s3_key="test_thumbnail.jpg",
            duration_seconds=60.0,
            created_at=datetime.now(UTC),
            view_count=0,
            like_count=0,
            comment_count=0,
            share_count=0,
            hashtags=["test"],
            is_private=False,
            allows_comments=True,
        )

    @pytest.fixture
    def test_bookmark(self, test_user: User, test_post: Post) -> Bookmark:
        return Bookmark(
            bookmark_id=uuid4(),
            user_id=test_user.user_id,
            post_id=test_post.post_id,
            collection_id=uuid4(),
            created_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_create_bookmark_success(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        collection_id = uuid4()
        bookmark_create = BookmarkCreate(
            user_id=test_user.user_id,
            collection_id=collection_id,
        )
        with patch.object(bookmark_service, "_create_bookmark") as mock_create:
            mock_create.return_value = Bookmark(
                bookmark_id=uuid4(),
                user_id=test_user.user_id,
                post_id=test_post.post_id,
                collection_id=collection_id,
                created_at=datetime.now(UTC),
            )

            # Act
            result = await bookmark_service.create_bookmark(
                test_post.post_id, bookmark_create
            )

            # Assert
            assert isinstance(result, Bookmark)
            assert result.user_id == test_user.user_id
            assert result.post_id == test_post.post_id
            assert result.collection_id == collection_id
            mock_create.assert_called_once_with(test_post.post_id, bookmark_create)

    @pytest.mark.asyncio
    async def test_create_bookmark_failure(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        collection_id = uuid4()
        bookmark_create = BookmarkCreate(
            user_id=test_user.user_id,
            collection_id=collection_id,
        )
        with patch.object(bookmark_service, "_create_bookmark") as mock_create:
            mock_create.side_effect = BookmarkError("Failed to create bookmark")

            # Act & Assert
            with pytest.raises(BookmarkError):
                await bookmark_service.create_bookmark(
                    test_post.post_id, bookmark_create
                )

    @pytest.mark.asyncio
    async def test_remove_bookmark_success(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        with patch.object(bookmark_service, "_remove_bookmark") as mock_remove:
            # Act
            await bookmark_service.remove_bookmark(test_user.user_id, test_post.post_id)

            # Assert
            mock_remove.assert_called_once_with(test_user.user_id, test_post.post_id)

    @pytest.mark.asyncio
    async def test_remove_nonexistent_bookmark(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        with patch.object(bookmark_service, "_remove_bookmark") as mock_remove:
            mock_remove.side_effect = BookmarkNotFoundError("Bookmark not found")

            # Act & Assert
            with pytest.raises(BookmarkNotFoundError):
                await bookmark_service.remove_bookmark(
                    test_user.user_id, test_post.post_id
                )

    @pytest.mark.asyncio
    async def test_is_bookmarked_true(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        with patch.object(bookmark_service, "_check_bookmark") as mock_check:
            mock_check.return_value = True

            # Act
            result = await bookmark_service.is_bookmarked(
                test_user.user_id, test_post.post_id
            )

            # Assert
            assert result is True
            mock_check.assert_called_once_with(test_user.user_id, test_post.post_id)

    @pytest.mark.asyncio
    async def test_is_bookmarked_false(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        with patch.object(bookmark_service, "_check_bookmark") as mock_check:
            mock_check.return_value = False

            # Act
            result = await bookmark_service.is_bookmarked(
                test_user.user_id, test_post.post_id
            )

            # Assert
            assert result is False
            mock_check.assert_called_once_with(test_user.user_id, test_post.post_id)

    @pytest.mark.asyncio
    async def test_get_bookmarked_posts(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
        test_post: Post,
    ):
        # Arrange
        with patch.object(bookmark_service, "_get_bookmarked_posts") as mock_get:
            mock_get.return_value = [test_post]

            # Act
            result = await bookmark_service.get_bookmarked_posts(test_user.user_id)

            # Assert
            assert len(result) == 1
            assert result[0] == test_post
            mock_get.assert_called_once_with(test_user.user_id, 50, 0)

    @pytest.mark.asyncio
    async def test_get_bookmarked_posts_with_pagination(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
    ):
        # Arrange
        limit = 10
        offset = 5
        with patch.object(bookmark_service, "_get_bookmarked_posts") as mock_get:
            mock_get.return_value = []

            # Act
            await bookmark_service.get_bookmarked_posts(
                test_user.user_id, limit=limit, offset=offset
            )

            # Assert
            mock_get.assert_called_once_with(test_user.user_id, limit, offset)

    @pytest.mark.asyncio
    async def test_get_bookmarked_posts_error(
        self,
        bookmark_service: BookmarkService,
        test_user: User,
    ):
        # Arrange
        with patch.object(bookmark_service, "_get_bookmarked_posts") as mock_get:
            mock_get.side_effect = BookmarkError("Failed to get bookmarked posts")

            # Act & Assert
            with pytest.raises(BookmarkError):
                await bookmark_service.get_bookmarked_posts(test_user.user_id)
