import boto3
import os
import uuid
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_to_s3(file_path: str, bucket_name: str = None) -> tuple[str, str]:
    """
    Uploads a file to an S3 bucket.

    :param file_path: Path to the file to upload.
    :param bucket_name: Name of the S3 bucket. If not provided, it will try to get it from
                        the VITE_AWS_BUCKET_NAME environment variable.
    :return: A tuple containing the S3 URL of the uploaded file and the unique filename.
    :raises ValueError: If the bucket name is not provided and the environment variable is not set.
    :raises Exception: For S3 upload errors.
    """
    try:
        s3_client = boto3.client('s3',
                                 aws_access_key_id=os.getenv("VITE_AWS_ACCESS_KEY"),
                                 aws_secret_access_key=os.getenv("VITE_AWS_SECRET_KEY"),
                                 region_name=os.getenv("VITE_AWS_REGION"))
        
        bucket_to_use = bucket_name or os.getenv("VITE_AWS_BUCKET_NAME")
        if not bucket_to_use:
            logger.error("S3 bucket name is not configured.")
            raise ValueError("S3 bucket name not provided and VITE_AWS_BUCKET_NAME environment variable is not set.")

        file_extension = Path(file_path).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"

        s3_client.upload_file(file_path, bucket_to_use, unique_filename)
        logger.info(f"Successfully uploaded {file_path} to {bucket_to_use}/{unique_filename}")

        region = os.getenv("VITE_AWS_REGION", "us-east-1")
        s3_url = f"https://{bucket_to_use}.s3.{region}.amazonaws.com/{unique_filename}"
        
        return s3_url, unique_filename

    except Exception as e:
        logger.error(f"Failed to upload {file_path} to S3. Error: {str(e)}")
        raise 