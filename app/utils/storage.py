from io import BytesIO
from os import environ
from uuid import uuid4

import aioboto3
from botocore.exceptions import ClientError
from pydantic import UUID4


class Storage:
    """Storage service for handling file operations with S3.

    This class provides methods for uploading and deleting files from S3.
    It uses aioboto3 for async operations.

    Attributes:
        bucket: Name of the S3 bucket
        access_key: AWS access key for authentication
    """

    def __init__(self) -> None:
        """Initialize the storage service with S3 configuration."""
        self.bucket: str = environ.get("S3_BUCKET_NAME", "")
        self.access_key: str = environ.get("S3_ACCESS_KEY", "")

    async def upload(self, file: BytesIO) -> UUID4:
        """Upload a file to S3.

        Args:
            file: The file to upload as a BytesIO object

        Returns:
            UUID4: The unique identifier assigned to the uploaded file

        Raises:
            ClientError: If the upload fails
        """
        uuid = uuid4()
        str_uuid = str(uuid)
        session = aioboto3.Session()
        async with session.client("s3") as s3:
            try:
                await s3.upload_fileobj(file, self.bucket, str_uuid)
                return uuid
            except ClientError as e:
                raise e

    async def delete(self, file_id: UUID4) -> None:
        """Delete a file from S3.

        Args:
            file_id: The unique identifier of the file to delete

        Raises:
            ClientError: If the deletion fails
        """
        session = aioboto3.Session()
        async with session.client("s3") as s3:
            try:
                await s3.delete_object(Bucket=self.bucket, Key=str(file_id))
            except ClientError as e:
                raise e
