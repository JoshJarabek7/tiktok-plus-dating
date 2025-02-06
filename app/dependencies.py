from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer

from app.models.user import User
from app.services.auth import (
    AuthService,
    InvalidTokenError,
    TokenExpiredError,
    UserNotFoundError,
)

security = HTTPBearer()
auth_service = AuthService()


async def get_current_user(request: Request) -> User:
    """Dependency for getting the current authenticated user.

    This dependency validates the JWT token and returns the user.
    Use this to protect routes that require authentication.

    Args:
        request: The FastAPI request object

    Returns:
        UserModel for the authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    try:
        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise InvalidTokenError("No authorization header found")

        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise InvalidTokenError("Invalid authentication scheme")

        return await auth_service.get_current_user(token)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}",
        )
