from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.user import User
from app.services.auth import (
    AuthError,
    AuthService,
    InvalidTokenError,
    TokenExpiredError,
    UserNotFoundError,
)


@pytest.mark.unit
class TestAuthService:
    @pytest.fixture
    def mock_httpx_client(self):
        with patch("httpx.Client") as mock:
            yield mock

    @pytest.fixture
    def mock_jwt(self):
        with patch("app.services.auth.jwt") as mock:
            yield mock

    async def test_get_current_user_valid_token(
        self, auth_service: AuthService, test_user: User, mock_jwt
    ):
        # Arrange
        token = "valid_token"
        mock_jwt.decode.return_value = {"sub": test_user.auth_id}
        with patch.object(
            auth_service, "get_or_create_user", return_value=test_user
        ) as mock_get_user:
            # Act
            result = await auth_service.get_current_user(token)

            # Assert
            assert result == test_user
            mock_jwt.decode.assert_called_once()
            mock_get_user.assert_called_once_with(token)

    async def test_get_current_user_invalid_token(
        self, auth_service: AuthService, mock_jwt
    ):
        # Arrange
        token = "invalid_token"
        mock_jwt.decode.side_effect = InvalidTokenError("Invalid token")

        # Act & Assert
        with pytest.raises(InvalidTokenError):
            await auth_service.get_current_user(token)

    async def test_get_current_user_expired_token(
        self, auth_service: AuthService, mock_jwt
    ):
        # Arrange
        token = "expired_token"
        mock_jwt.decode.side_effect = TokenExpiredError("Token expired")

        # Act & Assert
        with pytest.raises(TokenExpiredError):
            await auth_service.get_current_user(token)

    async def test_get_or_create_user_existing_user(
        self, auth_service: AuthService, test_user: User, mock_httpx_client
    ):
        # Arrange
        token = "valid_token"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sub": test_user.auth_id,
            "email": test_user.email,
            "name": test_user.display_name,
            "nickname": test_user.username,
            "picture": None,
            "email_verified": True,
            "locale": "en",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_httpx_client.return_value.__enter__.return_value = mock_client

        with patch.object(auth_service, "_get_auth0_profile") as mock_get_profile:
            mock_get_profile.return_value = mock_response.json()

            # Act
            result = auth_service.get_or_create_user(token)

            # Assert
            assert result == test_user
            mock_get_profile.assert_called_once_with(token)

    async def test_get_or_create_user_new_user(
        self, auth_service: AuthService, mock_httpx_client
    ):
        # Arrange
        token = "valid_token"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sub": "auth0|new_user",
            "email": "new@example.com",
            "name": "New User",
            "nickname": "new_user",
            "picture": None,
            "email_verified": True,
            "locale": "en",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_httpx_client.return_value.__enter__.return_value = mock_client

        with patch.object(auth_service, "_get_auth0_profile") as mock_get_profile:
            mock_get_profile.return_value = mock_response.json()

            # Act
            result = auth_service.get_or_create_user(token)

            # Assert
            assert isinstance(result, User)
            assert result.auth_id == "auth0|new_user"
            assert result.email == "new@example.com"
            mock_get_profile.assert_called_once_with(token)

    def test_validate_token_valid(self, auth_service: AuthService, mock_jwt):
        # Arrange
        token = "valid_token"
        expected_payload = {"sub": "auth0|user"}
        mock_jwt.decode.return_value = expected_payload

        # Act
        result = auth_service.validate_token(token)

        # Assert
        assert result == expected_payload
        mock_jwt.decode.assert_called_once_with(
            token,
            mock_jwt.get_unverified_header.return_value,
            algorithms=auth_service.algorithms,
            audience=auth_service.audience,
            issuer=f"https://{auth_service.domain}/",
        )

    def test_validate_token_invalid(self, auth_service: AuthService, mock_jwt):
        # Arrange
        token = "invalid_token"
        mock_jwt.decode.side_effect = InvalidTokenError("Invalid token")

        # Act & Assert
        with pytest.raises(InvalidTokenError):
            auth_service.validate_token(token)

    def test_validate_token_expired(self, auth_service: AuthService, mock_jwt):
        # Arrange
        token = "expired_token"
        mock_jwt.decode.side_effect = TokenExpiredError("Token expired")

        # Act & Assert
        with pytest.raises(TokenExpiredError):
            auth_service.validate_token(token)

    def test_get_token_from_header_valid(self, auth_service: AuthService):
        # Arrange
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer valid_token"}

        # Act
        result = auth_service._get_token_from_header(mock_request)

        # Assert
        assert result == "valid_token"

    def test_get_token_from_header_missing(self, auth_service: AuthService):
        # Arrange
        mock_request = MagicMock()
        mock_request.headers = {}

        # Act & Assert
        with pytest.raises(InvalidTokenError, match="No authorization header found"):
            auth_service._get_token_from_header(mock_request)

    def test_get_token_from_header_invalid_scheme(self, auth_service: AuthService):
        # Arrange
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Basic valid_token"}

        # Act & Assert
        with pytest.raises(InvalidTokenError, match="Invalid authentication scheme"):
            auth_service._get_token_from_header(mock_request)

    def test_get_token_from_header_invalid_format(self, auth_service: AuthService):
        # Arrange
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer"}

        # Act & Assert
        with pytest.raises(
            InvalidTokenError, match="Invalid authorization header format"
        ):
            auth_service._get_token_from_header(mock_request)
