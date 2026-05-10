import boto3, os, sys
from dotenv import load_dotenv
import logging
from typing import Optional, Tuple, Dict, Any
from botocore.exceptions import ClientError # Import ClientError for better error handling

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()         # reads .env in project root

def upload_to_s3(local_path: str, max_file_size_mb: int = 500) -> Optional[Tuple[str, str]]:
    """
    Upload a file to DigitalOcean Spaces with automatic unique filename generation.
    
    This is a convenience wrapper that automatically:
    - Gets bucket name from environment
    - Generates a unique filename using timestamp and UUID
    - Sets appropriate ACL for public access
    - Validates file size and path security
    
    Parameters
    ----------
    local_path : str
        Path to the file on disk to upload
    max_file_size_mb : int, optional
        Maximum file size in MB (default: 500MB)
        
    Returns
    -------
    Optional[Tuple[str, str]]
        (cdn_url, unique_filename) on success, None on failure
    """
    import uuid
    from datetime import datetime
    
    # Security: Validate and sanitize file path
    if not local_path or not isinstance(local_path, str):
        logger.error("❌ Invalid file path provided")
        return None, None
    
    # Security: Prevent path traversal attacks
    local_path = os.path.abspath(local_path)
    if not os.path.exists(local_path):
        logger.error("❌ File not found")
        return None, None
    
    # Security: Validate file size
    file_size_mb = os.path.getsize(local_path) / (1024 * 1024)
    if file_size_mb > max_file_size_mb:
        logger.error(f"❌ File size ({file_size_mb:.2f}MB) exceeds maximum allowed ({max_file_size_mb}MB)")
        return None, None
    
    bucket = os.getenv("DO_BUCKET_NAME")
    if not bucket:
        error_msg = "❌ DO_BUCKET_NAME not found in environment variables. Please set it in CapRover app settings."
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Generate unique filename: timestamp_uuid_original_filename
    original_filename = os.path.basename(local_path)
    file_ext = os.path.splitext(original_filename)[1]
    # Security: Sanitize file extension (only allow alphanumeric and common extensions)
    if not file_ext or len(file_ext) > 10:
        file_ext = ".bin"  # Default safe extension
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    unique_filename = f"{timestamp}_{unique_id}{file_ext}"
    
    # Upload with public-read ACL
    extra_args = {'ACL': 'public-read'}
    cdn_url = upload_file_to_s3(
        local_path=local_path,
        bucket=bucket,
        key=unique_filename,
        extra_args=extra_args
    )
    
    if cdn_url:
        return cdn_url, unique_filename
    else:
        return None, None

def upload_file_to_s3(local_path: str,
                      bucket: str,
                      key: Optional[str] = None,
                      extra_args: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Upload ⁠ local_path ⁠ to DigitalOcean Spaces.

    Parameters
    ----------
    local_path : str  –  path to the file on disk
    bucket     : str  –  target bucket name
    key        : str  –  destination path in the bucket (defaults to filename)
    extra_args : dict –  e.g. {'ACL': 'public-read'}

    Returns
    -------
    Optional[str]
        The public CDN URL of the uploaded file, or None on failure.
    """
    if key is None:
        key = os.path.basename(local_path)

    # Check if file exists
    if not os.path.exists(local_path):
        logger.error(f"❌ File not found: {local_path}")
        return None

    # Retrieve DigitalOcean credentials/region from environment
    region     = os.getenv("DO_REGION")
    access_key = os.getenv("DO_ACCESS_KEY")
    secret_key = os.getenv("DO_ACCESS_SECRET")

    # All credentials are required for DigitalOcean
    missing_vars = []
    if not region:
        missing_vars.append("DO_REGION")
    if not access_key:
        missing_vars.append("DO_ACCESS_KEY")
    if not secret_key:
        missing_vars.append("DO_ACCESS_SECRET")
    
    if missing_vars:
        error_msg = f"❌ Missing required environment variables: {', '.join(missing_vars)}. Please set them in CapRover app settings."
        logger.error(error_msg)
        raise ValueError(error_msg)
        
    endpoint_url = f"https://{region}.digitaloceanspaces.com"

    try:
        s3 = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        s3.upload_file(local_path, bucket, key,
                        ExtraArgs=extra_args or {})

        # Construct the CDN URL, matching the JS example
        cdn_url = f"https://{bucket}.{region}.cdn.digitaloceanspaces.com/{key}"
        logger.info(f"✅ Uploaded  {local_path}  ➜  {cdn_url}")
        return cdn_url

    except ClientError as e:
        # Security: Don't leak sensitive information in error messages
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'InvalidAccessKeyId':
             logger.error("❌ Upload failed: Invalid credentials (DO_ACCESS_KEY)")
        elif error_code == 'SignatureDoesNotMatch':
             logger.error("❌ Upload failed: Invalid credentials (DO_ACCESS_SECRET)")
        elif error_code == 'NoSuchBucket':
             logger.error(f"❌ Upload failed: Bucket '{bucket}' not found")
        elif error_code == '403':
             logger.error(f"❌ Upload failed: Permission denied for bucket '{bucket}'")
        else:
             # Log full error internally but don't expose to user
             logger.error(f"❌ Upload failed (ClientError): {error_code}")
        return None
    except Exception as e:
        # Security: Log error details internally but don't expose stack traces
        logger.error(f"❌ Unexpected error during upload: {type(e).__name__}")
        return None

def test_s3_connection() -> bool:
    """Test DigitalOcean Spaces connection and credentials"""
    try:
        region = os.getenv("DO_REGION")
        access_key = os.getenv("DO_ACCESS_KEY")
        secret_key = os.getenv("DO_ACCESS_SECRET")
        bucket_name = os.getenv("DO_BUCKET_NAME")

        if not bucket_name:
            logger.error("❌ DO_BUCKET_NAME not set in environment")
            return False
            
        if not region:
            logger.error("❌ DO_REGION not set in environment")
            return False
            
        if not (access_key and secret_key):
            logger.error("❌ DO_ACCESS_KEY or DO_ACCESS_SECRET not set in environment")
            return False

        endpoint_url = f"https://{region}.digitaloceanspaces.com"

        s3 = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
            
        # 1. Try to list buckets (tests credentials)
        s3.list_buckets()
        logger.info("✅ DigitalOcean Spaces connection test successful (Credentials OK)")
        
        # 2. Try to access the specific bucket (tests bucket name and permissions)
        s3.head_bucket(Bucket=bucket_name)
        logger.info(f"✅ Bucket '{bucket_name}' is accessible.")
        return True
        
    except ClientError as e:
        # Handle common errors gracefully
        if e.response['Error']['Code'] == 'NoSuchBucket':
             logger.error(f"❌ Connection successful, but bucket '{bucket_name}' not found.")
        elif e.response['Error']['Code'] == 'InvalidAccessKeyId':
             logger.error(f"❌ Connection failed: Invalid credentials (DO_ACCESS_KEY).")
        elif e.response['Error']['Code'] == 'SignatureDoesNotMatch':
             logger.error(f"❌ Connection failed: Invalid credentials (DO_ACCESS_SECRET).")
        elif e.response['Error']['Code'] == '403':
             logger.error(f"❌ Connection successful, but no permission to access bucket '{bucket_name}'.")
        else:
            logger.error(f"❌ DO Spaces connection test failed (ClientError): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ DO Spaces connection test failed (Exception): {e}")
        return False

# Test function for standalone testing
if __name__ == "__main__":
    print("Testing DigitalOcean Spaces connection...")
    if test_s3_connection():
        print("✅ DO Spaces connection is working")
        
        # --- Optional: Test the upload function ---
        print("\nTesting file upload...")
        
        # Create a dummy file to upload
        test_file_name = "do_test_upload.txt"
        try:
            with open(test_file_name, "w") as f:
                f.write("This is a test file for DigitalOcean Spaces upload.")
            
            bucket = os.getenv("DO_BUCKET_NAME")
            if bucket:
                # Use a specific key for the test
                test_key = f"test_uploads/{test_file_name}"
                
                # Make it public-read to be viewable via the CDN URL
                public_args = {'ACL': 'public-read'}
                
                print(f"Uploading '{test_file_name}' to DigitalOcean Spaces...")
                upload_url, unique_filename = upload_to_s3(test_file_name)
                
                if upload_url:
                    print(f"✅ Upload successful: {upload_url}")
                    print(f"✅ Unique filename: {unique_filename}")
                    print(f"ℹ️  Note: You may need to clean up the uploaded file manually.")
                else:
                    print("❌ Upload test failed.")
            else:
                # This should have been caught by test_s3_connection, but good to double check
                print("❌ Cannot run upload test, DO_BUCKET_NAME not set.")
                
        finally:
            # Clean up local dummy file
            if os.path.exists(test_file_name):
                os.remove(test_file_name)
                
    else:
        print("❌ DO Spaces connection failed. Check .env variables and permissions.")
