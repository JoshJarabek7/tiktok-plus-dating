import os
from datetime import UTC, datetime
from typing import AsyncGenerator, Generator
from uuid import uuid4

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession, Driver, GraphDatabase
from pydantic import UUID4

from app.db import DatabaseManager
from app.models.user import User
from app.services.auth import AuthService
from app.services.block import BlockService
from app.services.bookmark import BookmarkService
from app.services.comment import CommentService
from app.services.dating import DatingService
from app.services.follow import FollowService
from app.services.interaction import InteractionService
from app.services.like import LikeService
from app.services.message import MessageService
from app.services.notification import NotificationBaseService
from app.services.post import PostService
from app.services.profile import ProfileService
from app.services.recommendation import RecommendationService

# Test configuration
TEST_NEO4J_URI = os.getenv("TEST_NEO4J_URI", "bolt://localhost:7687")
TEST_NEO4J_USER = os.getenv("TEST_NEO4J_USER", "neo4j")
TEST_NEO4J_PASSWORD = os.getenv("TEST_NEO4J_PASSWORD", "password")
TEST_NEO4J_DATABASE = os.getenv("TEST_NEO4J_DATABASE", "neo4j")


# Service fixtures
@pytest.fixture
def auth_service() -> AuthService:
    return AuthService()


@pytest.fixture
def block_service() -> BlockService:
    return BlockService()


@pytest.fixture
def bookmark_service() -> BookmarkService:
    return BookmarkService()


@pytest.fixture
def comment_service() -> CommentService:
    return CommentService()


@pytest.fixture
def dating_service() -> DatingService:
    return DatingService()


@pytest.fixture
def follow_service() -> FollowService:
    return FollowService()


@pytest.fixture
def interaction_service() -> InteractionService:
    return InteractionService()


@pytest.fixture
def like_service() -> LikeService:
    return LikeService()


@pytest.fixture
def message_service() -> MessageService:
    return MessageService()


@pytest.fixture
def post_service() -> PostService:
    return PostService()


@pytest.fixture
def profile_service() -> ProfileService:
    return ProfileService()


@pytest.fixture
def recommendation_service() -> RecommendationService:
    return RecommendationService()


# Database fixtures
@pytest.fixture
def db_driver() -> Generator[Driver, None, None]:
    driver = GraphDatabase.driver(
        TEST_NEO4J_URI, auth=(TEST_NEO4J_USER, TEST_NEO4J_PASSWORD)
    )
    yield driver
    driver.close()


@pytest_asyncio.fixture
async def async_db_driver() -> AsyncGenerator[AsyncDriver, None]:
    driver = AsyncGraphDatabase.driver(
        TEST_NEO4J_URI, auth=(TEST_NEO4J_USER, TEST_NEO4J_PASSWORD)
    )
    yield driver
    await driver.close()


@pytest_asyncio.fixture
async def db_session(
    async_db_driver: AsyncDriver,
) -> AsyncGenerator[AsyncSession, None]:
    async with async_db_driver.session(database=TEST_NEO4J_DATABASE) as session:
        yield session


# Test data fixtures
@pytest.fixture
def test_user() -> User:
    return User(
        user_id=uuid4(),
        username="test_user",
        email="test@example.com",
        display_name="Test User",
        auth_id="auth0|test",
        profile_picture_s3_key=None,
        bio="Test user bio",
        latitude=37.7749,
        longitude=-122.4194,
        is_private=False,
        created_at=datetime.now(UTC),
        follower_count=0,
        following_count=0,
        likes_count=0,
        post_count=0,
    )


@pytest.fixture
def test_user_id() -> UUID4:
    return uuid4()


@pytest.fixture
def another_test_user() -> User:
    return User(
        user_id=uuid4(),
        username="another_test_user",
        email="another_test@example.com",
        display_name="Another Test User",
        auth_id="auth0|another_test",
        profile_picture_s3_key=None,
        bio="Another test user bio",
        latitude=40.7128,
        longitude=-74.0060,
        is_private=False,
        created_at=datetime.now(UTC),
        follower_count=0,
        following_count=0,
        likes_count=0,
        post_count=0,
    )


@pytest.fixture
def private_test_user() -> User:
    return User(
        user_id=uuid4(),
        username="private_test_user",
        email="private_test@example.com",
        display_name="Private Test User",
        auth_id="auth0|private_test",
        profile_picture_s3_key=None,
        bio="Private test user bio",
        latitude=51.5074,
        longitude=-0.1278,
        is_private=True,
        created_at=datetime.now(UTC),
        follower_count=0,
        following_count=0,
        likes_count=0,
        post_count=0,
    )


# Database cleanup fixture
@pytest.fixture(autouse=True)
async def cleanup_database(db_session: AsyncSession):
    yield
    # Clean up all test data after each test
    await db_session.run("""
        MATCH (n)
        DETACH DELETE n
    """)


# Mock S3 storage fixture
@pytest.fixture
def mock_storage(mocker):
    return mocker.patch("app.utils.storage.Storage")
