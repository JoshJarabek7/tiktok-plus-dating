from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import httpx
from fastapi import Request
from jose import JWTError, jwt
from jose.exceptions import JWTClaimsError
from neo4j import ManagedTransaction
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db import DatabaseManager
from app.models.user import User


class Auth0Profile(BaseModel):
    """Model representing an Auth0 user profile.

    This model contains the normalized user data from various social providers
    after being processed by Auth0.

    Attributes:
        sub: Unique Auth0 identifier (e.g., 'google-oauth2|12345')
        email: User's email address
        email_verified: Whether the email has been verified
        name: User's full name
        picture: URL to user's profile picture
        given_name: User's first name if available
        family_name: User's last name if available
        nickname: User's nickname or username
        locale: User's locale setting
        updated_at: When the profile was last updated
    """

    model_config = ConfigDict(frozen=True)

    sub: str = Field(description="Unique Auth0 identifier")
    email: EmailStr = Field(description="User's email address")
    email_verified: bool = Field(description="Whether the email has been verified")
    name: str = Field(description="User's full name")
    picture: str | None = Field(None, description="URL to user's profile picture")
    given_name: str | None = Field(None, description="User's first name if available")
    family_name: str | None = Field(None, description="User's last name if available")
    nickname: str = Field(description="User's nickname or username")
    locale: str | None = Field(None, description="User's locale setting")
    updated_at: str = Field(description="When the profile was last updated")


class AuthError(Exception):
    """Base exception for auth-related errors."""

    pass


class InvalidTokenError(AuthError):
    """Exception raised when a token is invalid."""

    pass


class TokenExpiredError(AuthError):
    """Exception raised when a token has expired."""

    pass


class UserNotFoundError(AuthError):
    """Exception raised when a user cannot be found."""

    pass


class AuthService:
    """Service for handling Auth0 authentication and user management.

    This service handles token validation, user creation/linking for social
    providers, and provides methods for protecting endpoints.

    Attributes:
        domain: Auth0 domain
        audience: Auth0 API audience
        algorithms: List of supported JWT algorithms
    """

    def __init__(self) -> None:
        """Initialize the auth service with Auth0 configuration."""
        from os import environ

        self.domain: str = environ.get("AUTH0_DOMAIN", "")
        self.audience: str = environ.get("AUTH0_AUDIENCE", "")
        self.algorithms: list[str] = ["RS256"]

    def _get_token_from_header(self, request: Request) -> str:
        """Extract the JWT token from the Authorization header.

        Args:
            request: The FastAPI request object

        Returns:
            The JWT token string

        Raises:
            InvalidTokenError: If no token is found or format is invalid
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise InvalidTokenError("No authorization header found")

        try:
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                raise InvalidTokenError("Invalid authentication scheme")
            return token
        except ValueError:
            raise InvalidTokenError("Invalid authorization header format")

    def validate_token(self, token: str) -> dict[str, Any]:
        """Validate an Auth0 JWT token.

        Args:
            token: The JWT token to validate

        Returns:
            The decoded token payload

        Raises:
            InvalidTokenError: If token is invalid
            TokenExpiredError: If token has expired
        """
        try:
            # Get Auth0 public key
            jwks_url = f"https://{self.domain}/.well-known/jwks.json"
            jwks = httpx.get(jwks_url).json()

            # Decode header to get key ID
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}

            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"],
                    }
                    break

            if not rsa_key:
                raise InvalidTokenError("Unable to find appropriate key")

            # Validate token
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=f"https://{self.domain}/",
            )
            return cast(dict[str, Any], payload)

        except JWTClaimsError as e:
            raise InvalidTokenError(f"Invalid claims: {str(e)}")
        except JWTError as e:
            if "expired" in str(e).lower():
                raise TokenExpiredError("Token has expired")
            raise InvalidTokenError(f"Invalid token: {str(e)}")

    def _get_auth0_profile(self, access_token: str) -> Auth0Profile:
        """Get user profile information from Auth0.

        Args:
            access_token: Valid Auth0 access token

        Returns:
            Auth0Profile containing normalized user data

        Raises:
            InvalidTokenError: If profile fetch fails
        """
        try:
            url = f"https://{self.domain}/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}

            with httpx.Client() as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                return Auth0Profile(**response.json())

        except httpx.HTTPError as e:
            raise InvalidTokenError(f"Failed to get user profile: {str(e)}")

    def _create_user_from_auth0(
        self, tx: ManagedTransaction, profile: Auth0Profile
    ) -> User:
        """Create a new user from Auth0 profile data.

        Args:
            tx: The database transaction
            profile: Auth0 profile data

        Returns:
            The created UserModel

        Raises:
            ValueError: If user creation fails
        """
        query = """
        CREATE (user:User {
            user_id: $user_id,
            auth_id: $auth_id,
            username: $username,
            email: $email,
            display_name: $display_name,
            profile_picture_s3_key: $profile_picture_s3_key,
            is_private: false,
            created_at: $created_at,
            follower_count: 0,
            following_count: 0,
            likes_count: 0,
            post_count: 0
        })
        RETURN user
        """

        # Generate a unique username if nickname is taken
        base_username = profile.nickname.lower()
        username = base_username
        attempt = 1

        while True:
            check_query = """
            MATCH (u:User {username: $username})
            RETURN count(u) as count
            """
            result = tx.run(check_query, username=username)
            count = result.single()
            if count and count["count"] == 0:
                break
            username = f"{base_username}{attempt}"
            attempt += 1

        result = tx.run(
            query,
            user_id=str(uuid4()),
            auth_id=profile.sub,
            username=username,
            email=str(profile.email),
            display_name=profile.name,
            profile_picture_s3_key=profile.picture,
            created_at=datetime.now(UTC).isoformat(),
        )

        if record := result.single():
            return User(**record["user"])
        raise ValueError("Failed to create user")

    async def get_current_user(self, token: str) -> User:
        """Get the current authenticated user from token.

        Args:
            token: The JWT token string

        Returns:
            UserModel for the authenticated user

        Raises:
            InvalidTokenError: If token is invalid
            TokenExpiredError: If token has expired
            UserNotFoundError: If user cannot be found
        """
        try:
            self.validate_token(token)  # Validates token format and signature
            return self.get_or_create_user(token)  # Gets or creates user
        except AuthError:
            raise  # Re-raise auth errors
        except Exception as e:
            raise UserNotFoundError(f"Failed to get user: {str(e)}")

    def get_or_create_user(self, access_token: str) -> User:
        """Get existing user or create new one from Auth0 profile.

        Args:
            access_token: Valid Auth0 access token

        Returns:
            UserModel for existing or newly created user

        Raises:
            UserNotFoundError: If user fetch/creation fails
        """
        try:
            profile = self._get_auth0_profile(access_token)

            db_manager = DatabaseManager()
            with db_manager.driver.session(database=db_manager.database) as session:
                # Try to find existing user
                query = """
                MATCH (user:User {auth_id: $auth_id})
                RETURN user
                """
                result = session.run(query, auth_id=profile.sub)
                if record := result.single():
                    return User(**record["user"])

                # Create new user if not found
                return session.execute_write(self._create_user_from_auth0, profile)
        except Exception as e:
            raise UserNotFoundError(f"Failed to get or create user: {str(e)}")
