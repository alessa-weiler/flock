"""
Storage Manager for DigitalOcean Spaces (S3-compatible)
Handles file upload, download, and deletion operations
"""

import os
import boto3
from botocore.exceptions import ClientError
from typing import BinaryIO, Optional
import magic  # for file type validation


class StorageManager:
    """Manages file storage operations with DigitalOcean Spaces"""

    # Supported file types and their MIME types
    ALLOWED_TYPES = {
        'pdf': ['application/pdf'],
        'docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
        'txt': ['text/plain'],
        'md': ['text/markdown', 'text/plain'],
        'csv': ['text/csv', 'text/plain']
    }

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

    def __init__(self):
        """Initialize S3 client for DigitalOcean Spaces"""
        self.endpoint_url = os.environ.get('DO_SPACES_ENDPOINT')
        self.access_key = os.environ.get('DO_SPACES_KEY')
        self.secret_key = os.environ.get('DO_SPACES_SECRET')
        self.region = os.environ.get('DO_SPACES_REGION', 'nyc3')
        self.bucket_name = os.environ.get('DO_SPACES_BUCKET', 'flock-documents')

        if not all([self.endpoint_url, self.access_key, self.secret_key]):
            raise ValueError(
                "Missing DigitalOcean Spaces credentials. "
                "Set DO_SPACES_ENDPOINT, DO_SPACES_KEY, and DO_SPACES_SECRET"
            )

        # Initialize boto3 S3 client
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )

    def validate_file(self, file_obj: BinaryIO, filename: str) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Validate file type and size

        Args:
            file_obj: File object to validate
            filename: Name of the file

        Returns:
            Tuple of (is_valid, error_message, detected_file_type)
        """
        # Get file extension
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

        if file_ext not in self.ALLOWED_TYPES:
            return False, f"File type .{file_ext} not allowed. Supported: {', '.join(self.ALLOWED_TYPES.keys())}", None

        # Check file size
        file_obj.seek(0, 2)  # Seek to end
        file_size = file_obj.tell()
        file_obj.seek(0)  # Reset to beginning

        if file_size > self.MAX_FILE_SIZE:
            return False, f"File size {file_size / 1024 / 1024:.1f}MB exceeds maximum of 50MB", None

        if file_size == 0:
            return False, "File is empty", None

        # Validate MIME type using python-magic (basic virus scan via magic numbers)
        try:
            mime = magic.from_buffer(file_obj.read(2048), mime=True)
            file_obj.seek(0)  # Reset to beginning

            if mime not in self.ALLOWED_TYPES[file_ext]:
                # Allow some flexibility for text-based files
                if file_ext in ['txt', 'md', 'csv'] and mime.startswith('text/'):
                    return True, None, file_ext
                return False, f"File content type {mime} doesn't match extension .{file_ext}", None

        except Exception as e:
            print(f"Warning: Could not verify MIME type: {e}")
            # Continue anyway if magic check fails

        return True, None, file_ext

    def upload_file(self, file_obj: BinaryIO, org_id: int, doc_id: int, filename: str) -> str:
        """
        Upload file to DigitalOcean Spaces

        Args:
            file_obj: File object to upload
            org_id: Organization ID
            doc_id: Document ID
            filename: Original filename

        Returns:
            Storage URL of uploaded file

        Raises:
            Exception if upload fails
        """
        # Construct storage path: org_{org_id}/documents/{doc_id}/{filename}
        storage_key = f"org_{org_id}/documents/{doc_id}/{filename}"

        # Determine content type
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        content_type_map = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain',
            'md': 'text/markdown',
            'csv': 'text/csv'
        }
        content_type = content_type_map.get(file_ext, 'application/octet-stream')

        try:
            # Upload to Spaces
            file_obj.seek(0)  # Ensure we're at the beginning
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                storage_key,
                ExtraArgs={
                    'ACL': 'private',  # Keep files private
                    'ContentType': content_type
                }
            )

            # Construct and return storage URL
            storage_url = f"{self.endpoint_url}/{self.bucket_name}/{storage_key}"
            return storage_url

        except ClientError as e:
            raise Exception(f"Failed to upload file: {e}")

    def generate_download_url(self, storage_url: str, expires_in: int = 3600) -> str:
        """
        Generate presigned URL for downloading a file

        Args:
            storage_url: Full storage URL of the file
            expires_in: Expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL
        """
        # Extract storage key from URL
        # URL format: https://endpoint/bucket/org_X/documents/Y/filename.ext
        try:
            storage_key = storage_url.split(f"/{self.bucket_name}/")[-1]

            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': storage_key
                },
                ExpiresIn=expires_in
            )

            return presigned_url

        except ClientError as e:
            raise Exception(f"Failed to generate download URL: {e}")

    def delete_file(self, storage_url: str) -> bool:
        """
        Delete file from DigitalOcean Spaces

        Args:
            storage_url: Full storage URL of the file

        Returns:
            True if deleted successfully
        """
        try:
            # Extract storage key from URL
            storage_key = storage_url.split(f"/{self.bucket_name}/")[-1]

            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )

            return True

        except ClientError as e:
            print(f"Failed to delete file: {e}")
            return False

    def download_to_temp(self, storage_url: str, temp_path: str) -> str:
        """
        Download file from storage to a temporary location

        Args:
            storage_url: Full storage URL of the file
            temp_path: Path where to save the temp file

        Returns:
            Path to downloaded file
        """
        try:
            # Extract storage key from URL
            storage_key = storage_url.split(f"/{self.bucket_name}/")[-1]

            # Download file
            with open(temp_path, 'wb') as f:
                self.s3_client.download_fileobj(
                    self.bucket_name,
                    storage_key,
                    f
                )

            return temp_path

        except ClientError as e:
            raise Exception(f"Failed to download file: {e}")
