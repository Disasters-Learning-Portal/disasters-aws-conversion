"""
Quick test script to verify S3 upload permissions with external ID.
This creates a test.txt file and uploads it to the nasa-disasters bucket.
"""

from core.s3_operations import initialize_s3_client, upload_to_s3
import tempfile
import os
from datetime import datetime


def test_s3_upload():
    """Test uploading a file to S3 to verify upload permissions."""

    print("🧪 Testing S3 Upload Permissions")
    print("="*60)

    # Initialize S3 client (will try external ID first, then fall back to default)
    print("\n1. Initializing S3 client...")
    s3_client, _ = initialize_s3_client(bucket_name='nasa-disasters', verbose=True)

    if not s3_client:
        print("\n❌ Failed to initialize S3 client")
        return False

    # Create a temporary test file
    print("\n2. Creating test file...")
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        test_content = f"""Test Upload
Timestamp: {datetime.now().isoformat()}
Purpose: Verify S3 upload permissions with external ID authentication
"""
        f.write(test_content)
        temp_file = f.name

    print(f"   ✅ Created: {temp_file}")

    # Upload to S3
    print("\n3. Uploading to S3...")
    bucket = 'nasa-disasters'
    key = 'test_uploads/test.txt'

    try:
        success = upload_to_s3(
            s3_client=s3_client,
            local_path=temp_file,
            bucket=bucket,
            key=key,
            verbose=True
        )

        if success:
            print(f"\n✅ SUCCESS! File uploaded to s3://{bucket}/{key}")
            print("\n🎉 Upload permissions are working correctly!")
            print("   You can now process and upload COG files.")

            # Try to verify the file exists
            print("\n4. Verifying upload...")
            try:
                response = s3_client.head_object(Bucket=bucket, Key=key)
                size = response['ContentLength']
                print(f"   ✅ File verified in S3 ({size} bytes)")
            except Exception as e:
                print(f"   ⚠️ Could not verify file: {e}")
        else:
            print(f"\n❌ Upload failed")
            print("   This likely means you don't have upload permissions.")
            print("   Check your aws_credentials.py configuration.")
            return False

    except Exception as e:
        print(f"\n❌ Upload error: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Verify aws_credentials.py exists with correct EXTERNAL_ID")
        print("   2. Check that EXTERNAL_ID matches the value from your administrator")
        print("   3. Ensure the role ARN is correct: arn:aws:iam::515966502221:role/Jupyterhub-Data-Upload")
        return False
    finally:
        # Clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"\n   🧹 Cleaned up temporary file")

    print("\n" + "="*60)
    return True


