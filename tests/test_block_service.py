from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.user import User
from app.schemas.database_records import CreateBlockRecord
from app.services.block import (
    BlockError,
    BlockNotFoundError,
    BlockService,
    BlockUpdateError,
)


@pytest.mark.unit
class TestBlockService:
    @pytest.mark.asyncio
    async def test_block_user_success(
        self, block_service: BlockService, test_user: User, another_test_user: User
    ):
        # Arrange
        with patch.object(block_service, "_create_block_relationship") as mock_create:
            mock_create.return_value = CreateBlockRecord(
                success=True,
                blocked_user_id=another_test_user.user_id,
                removed_forward_follow=False,
                removed_reverse_follow=False,
            )

            # Act
            result = await block_service.block(
                test_user.user_id, another_test_user.user_id
            )

            # Assert
            assert result.success is True
            assert result.blocked_user_id == another_test_user.user_id
            mock_create.assert_called_once_with(
                test_user.user_id, another_test_user.user_id
            )

    @pytest.mark.asyncio
    async def test_block_self_fails(self, block_service: BlockService, test_user: User):
        # Act & Assert
        with pytest.raises(BlockError, match="Users cannot block themselves"):
            await block_service.block(test_user.user_id, test_user.user_id)

    @pytest.mark.asyncio
    async def test_block_user_with_follows(
        self, block_service: BlockService, test_user: User, another_test_user: User
    ):
        # Arrange
        with patch.object(block_service, "_create_block_relationship") as mock_create:
            mock_create.return_value = CreateBlockRecord(
                success=True,
                blocked_user_id=another_test_user.user_id,
                removed_forward_follow=True,
                removed_reverse_follow=True,
            )

            # Act
            result = await block_service.block(
                test_user.user_id, another_test_user.user_id
            )

            # Assert
            assert result.success is True
            assert result.removed_forward_follow is True
            assert result.removed_reverse_follow is True

    @pytest.mark.asyncio
    async def test_unblock_user_success(
        self, block_service: BlockService, test_user: User, another_test_user: User
    ):
        # Arrange
        with patch.object(block_service, "_remove_block_relationship") as mock_remove:
            mock_remove.return_value = {
                "success": True,
                "blocker_exists": True,
                "blockee_exists": True,
            }

            # Act
            await block_service.unblock(test_user.user_id, another_test_user.user_id)

            # Assert
            mock_remove.assert_called_once_with(
                test_user.user_id, another_test_user.user_id
            )

    @pytest.mark.asyncio
    async def test_unblock_self_fails(
        self, block_service: BlockService, test_user: User
    ):
        # Act & Assert
        with pytest.raises(BlockError, match="Users cannot unblock themselves"):
            await block_service.unblock(test_user.user_id, test_user.user_id)

    @pytest.mark.asyncio
    async def test_unblock_nonexistent_block(
        self, block_service: BlockService, test_user: User, another_test_user: User
    ):
        # Arrange
        with patch.object(block_service, "_remove_block_relationship") as mock_remove:
            mock_remove.side_effect = BlockNotFoundError("Block not found")

            # Act & Assert
            with pytest.raises(BlockNotFoundError):
                await block_service.unblock(
                    test_user.user_id, another_test_user.user_id
                )

    @pytest.mark.asyncio
    async def test_get_blocked_users(
        self, block_service: BlockService, test_user: User, another_test_user: User
    ):
        # Arrange
        with patch.object(block_service, "_get_blocked_users") as mock_get:
            mock_get.return_value = [another_test_user]

            # Act
            result = await block_service.get_blocked_users(test_user.user_id)

            # Assert
            assert len(result) == 1
            assert result[0] == another_test_user
            mock_get.assert_called_once_with(test_user.user_id, 50, 0)

    @pytest.mark.asyncio
    async def test_get_blocked_users_with_pagination(
        self, block_service: BlockService, test_user: User
    ):
        # Arrange
        limit = 10
        offset = 5
        with patch.object(block_service, "_get_blocked_users") as mock_get:
            mock_get.return_value = []

            # Act
            await block_service.get_blocked_users(
                test_user.user_id, limit=limit, offset=offset
            )

            # Assert
            mock_get.assert_called_once_with(test_user.user_id, limit, offset)

    @pytest.mark.asyncio
    async def test_is_blocked_true(
        self, block_service: BlockService, test_user: User, another_test_user: User
    ):
        # Arrange
        with patch.object(block_service, "_check_block_status") as mock_check:
            mock_check.return_value = True

            # Act
            result = await block_service.is_blocked(
                test_user.user_id, another_test_user.user_id
            )

            # Assert
            assert result is True
            mock_check.assert_called_once_with(
                test_user.user_id, another_test_user.user_id
            )

    @pytest.mark.asyncio
    async def test_is_blocked_false(
        self, block_service: BlockService, test_user: User, another_test_user: User
    ):
        # Arrange
        with patch.object(block_service, "_check_block_status") as mock_check:
            mock_check.return_value = False

            # Act
            result = await block_service.is_blocked(
                test_user.user_id, another_test_user.user_id
            )

            # Assert
            assert result is False
            mock_check.assert_called_once_with(
                test_user.user_id, another_test_user.user_id
            )
