from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import HttpUrl

from app.models.dating import (
    DatingFilter,
    DatingMatch,
    DatingProfile,
    Gender,
    Sexuality,
)
from app.models.interaction import InteractionType
from app.models.user import User
from app.services.dating import (
    ActionRecordingError,
    DatingError,
    DatingService,
    MatchCreationError,
)


@pytest.mark.unit
class TestDatingService:
    @pytest.fixture
    def test_dating_profile(self, test_user: User) -> DatingProfile:
        current_time = datetime.now(UTC)
        return DatingProfile(
            user_id=test_user.user_id,
            bio="Test bio",
            birth_date=date(1990, 1, 1),
            gender=Gender.MALE,
            sexuality=Sexuality.STRAIGHT,
            photos=[HttpUrl("https://example.com/photo1.jpg")],
            max_distance_miles=50,
            min_age_preference=21,
            max_age_preference=35,
            gender_preference=[Gender.FEMALE],
            is_visible=True,
            created_at=current_time,
            updated_at=current_time,
        )

    @pytest.fixture
    def test_dating_filter(self) -> DatingFilter:
        return DatingFilter(
            min_age=21,
            max_age=35,
            gender_preference=[Gender.FEMALE],
            max_distance_miles=50,
            min_compatibility=0.5,
            exclude_seen=True,
            exclude_matched=True,
            limit=50,
            offset=0,
        )

    @pytest.fixture
    def test_dating_match(
        self, test_user: User, another_test_user: User
    ) -> DatingMatch:
        return DatingMatch(
            match_id=uuid4(),
            user_id_a=test_user.user_id,
            user_id_b=another_test_user.user_id,
            user_a_action=InteractionType.SWIPE_RIGHT,
            user_b_action=InteractionType.SWIPE_RIGHT,
            distance_miles=10.0,
            compatibility_score=0.8,
            is_mutual=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_create_dating_profile_success(
        self,
        dating_service: DatingService,
        test_dating_profile: DatingProfile,
    ):
        # Arrange
        with patch.object(dating_service, "_create_dating_profile") as mock_create:
            mock_create.return_value = test_dating_profile

            # Act
            result = dating_service.create_dating_profile(test_dating_profile)

            # Assert
            assert result == test_dating_profile
            mock_create.assert_called_once_with(test_dating_profile)

    @pytest.mark.asyncio
    async def test_create_dating_profile_failure(
        self,
        dating_service: DatingService,
        test_dating_profile: DatingProfile,
    ):
        # Arrange
        with patch.object(dating_service, "_create_dating_profile") as mock_create:
            mock_create.side_effect = ValueError("Failed to create profile")

            # Act & Assert
            with pytest.raises(ValueError):
                dating_service.create_dating_profile(test_dating_profile)

    @pytest.mark.asyncio
    async def test_get_potential_matches_success(
        self,
        dating_service: DatingService,
        test_user: User,
        test_dating_filter: DatingFilter,
        test_dating_profile: DatingProfile,
    ):
        # Arrange
        with patch.object(dating_service, "_get_potential_matches") as mock_get:
            mock_get.return_value = [test_dating_profile]

            # Act
            result = dating_service.get_potential_matches(
                test_user.user_id, test_dating_filter
            )

            # Assert
            assert len(result) == 1
            assert result[0] == test_dating_profile
            mock_get.assert_called_once_with(test_user.user_id, test_dating_filter)

    @pytest.mark.asyncio
    async def test_get_potential_matches_failure(
        self,
        dating_service: DatingService,
        test_user: User,
        test_dating_filter: DatingFilter,
    ):
        # Arrange
        with patch.object(dating_service, "_get_potential_matches") as mock_get:
            mock_get.side_effect = ValueError("Failed to get matches")

            # Act & Assert
            with pytest.raises(ValueError):
                dating_service.get_potential_matches(
                    test_user.user_id, test_dating_filter
                )

    @pytest.mark.asyncio
    async def test_record_dating_action_success(
        self,
        dating_service: DatingService,
        test_user: User,
        another_test_user: User,
        test_dating_match: DatingMatch,
    ):
        # Arrange
        with patch.object(dating_service, "_record_dating_action") as mock_record:
            mock_record.return_value = test_dating_match

            # Act
            result = await dating_service.record_dating_action(
                test_user.user_id,
                another_test_user.user_id,
                InteractionType.SWIPE_RIGHT,
            )

            # Assert
            assert result == test_dating_match
            mock_record.assert_called_once_with(
                test_user.user_id,
                another_test_user.user_id,
                InteractionType.SWIPE_RIGHT,
            )

    @pytest.mark.asyncio
    async def test_record_dating_action_self_fails(
        self,
        dating_service: DatingService,
        test_user: User,
    ):
        # Act & Assert
        with pytest.raises(ActionRecordingError):
            await dating_service.record_dating_action(
                test_user.user_id,
                test_user.user_id,
                InteractionType.SWIPE_RIGHT,
            )

    @pytest.mark.asyncio
    async def test_record_dating_action_invalid_type(
        self,
        dating_service: DatingService,
        test_user: User,
        another_test_user: User,
    ):
        # Act & Assert
        with pytest.raises(ActionRecordingError):
            await dating_service.record_dating_action(
                test_user.user_id,
                another_test_user.user_id,
                InteractionType.COMMENT,  # Invalid for dating
            )

    @pytest.mark.asyncio
    async def test_get_dating_profile_success(
        self,
        dating_service: DatingService,
        test_user: User,
        test_dating_profile: DatingProfile,
    ):
        # Arrange
        with patch.object(dating_service, "_get_dating_profile") as mock_get:
            mock_get.return_value = test_dating_profile

            # Act
            result = dating_service.get_dating_profile(test_user.user_id)

            # Assert
            assert result == test_dating_profile
            mock_get.assert_called_once_with(test_user.user_id)

    @pytest.mark.asyncio
    async def test_get_dating_profile_not_found(
        self,
        dating_service: DatingService,
        test_user: User,
    ):
        # Arrange
        with patch.object(dating_service, "_get_dating_profile") as mock_get:
            mock_get.side_effect = ValueError("Profile not found")

            # Act & Assert
            with pytest.raises(ValueError):
                dating_service.get_dating_profile(test_user.user_id)

    @pytest.mark.asyncio
    async def test_update_dating_profile_success(
        self,
        dating_service: DatingService,
        test_dating_profile: DatingProfile,
    ):
        # Arrange
        updated_profile = DatingProfile(
            **{
                **test_dating_profile.model_dump(),
                "bio": "Updated bio",
            }
        )
        with patch.object(dating_service, "_update_dating_profile") as mock_update:
            mock_update.return_value = updated_profile

            # Act
            result = dating_service.update_dating_profile(updated_profile)

            # Assert
            assert result == updated_profile
            assert result.bio == "Updated bio"
            mock_update.assert_called_once_with(updated_profile)

    @pytest.mark.asyncio
    async def test_update_dating_profile_not_found(
        self,
        dating_service: DatingService,
        test_dating_profile: DatingProfile,
    ):
        # Arrange
        with patch.object(dating_service, "_update_dating_profile") as mock_update:
            mock_update.side_effect = ValueError("Profile not found")

            # Act & Assert
            with pytest.raises(ValueError):
                dating_service.update_dating_profile(test_dating_profile)

    @pytest.mark.asyncio
    async def test_get_mutual_matches_success(
        self,
        dating_service: DatingService,
        test_user: User,
        test_dating_match: DatingMatch,
    ):
        # Arrange
        with patch.object(dating_service, "_get_mutual_matches") as mock_get:
            mock_get.return_value = [test_dating_match]

            # Act
            result = dating_service.get_mutual_matches(test_user.user_id)

            # Assert
            assert len(result) == 1
            assert result[0] == test_dating_match
            mock_get.assert_called_once_with(test_user.user_id, 50, 0)

    @pytest.mark.asyncio
    async def test_get_mutual_matches_with_pagination(
        self,
        dating_service: DatingService,
        test_user: User,
    ):
        # Arrange
        limit = 10
        offset = 5
        with patch.object(dating_service, "_get_mutual_matches") as mock_get:
            mock_get.return_value = []

            # Act
            dating_service.get_mutual_matches(
                test_user.user_id, limit=limit, offset=offset
            )

            # Assert
            mock_get.assert_called_once_with(test_user.user_id, limit, offset)

    @pytest.mark.asyncio
    async def test_record_profile_view(
        self,
        dating_service: DatingService,
        test_user: User,
        another_test_user: User,
    ):
        # Arrange
        with patch.object(dating_service, "_record_profile_view") as mock_record:
            # Act
            dating_service.record_profile_view(
                test_user.user_id, another_test_user.user_id
            )

            # Assert
            mock_record.assert_called_once_with(
                test_user.user_id, another_test_user.user_id
            )
