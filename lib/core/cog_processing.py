"""
COG processing module - handles end-to-end COG creation from S3 files.
Single responsibility: Complete S3-to-S3 COG processing workflow.
"""

import os
import tempfile
import subprocess
from pathlib import Path


def process_single_file(s3_client, bucket, source_key, dest_key,
                       nodata=None, verify=True, check_source_is_cog=True,
                       skip_if_source_is_cog=True, verbose=True):
    """
    Process a single file from S3 to COG.

    This function:
    1. Optionally checks if source is already a valid COG
    2. Downloads the file from S3
    3. Converts to COG with proper compression
    4. Uploads back to S3
    5. Optionally verifies the output

    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        source_key: S3 key for source file
        dest_key: S3 key for destination COG
        nodata: Nodata value (None to auto-detect)
        verify: Verify COG after creation
        check_source_is_cog: Check if source is already a COG
        skip_if_source_is_cog: Skip processing if source is already a valid COG
        verbose: Print progress messages

    Returns:
        bool: True if successful
    """
    try:
        # Step 1: Check if source is already a valid COG
        if check_source_is_cog:
            from lib.core.validation import is_s3_file_cog

            if verbose:
                print(f"   [COG-CHECK] Checking if source is already a valid COG...")

            is_cog, details = is_s3_file_cog(s3_client, bucket, source_key, verbose=False)

            if is_cog:
                if verbose:
                    print(f"   [COG-CHECK] ✅ Source is already a valid COG")

                if skip_if_source_is_cog:
                    if verbose:
                        print(f"   [COG-CHECK] ⏭️  Skipping processing (source is valid COG)")

                    # Copy the file instead of processing
                    if verbose:
                        print(f"   [S3] Copying COG to destination...")

                    copy_source = {'Bucket': bucket, 'Key': source_key}
                    s3_client.copy_object(
                        CopySource=copy_source,
                        Bucket=bucket,
                        Key=dest_key
                    )

                    if verbose:
                        print(f"   [S3] ✅ Copied to {dest_key}")

                    return True
                else:
                    if verbose:
                        print(f"   [COG-CHECK] ⚠️  Source is COG but skip_if_source_is_cog=False, will reprocess")

        # Step 2: Create temporary files
        temp_input = None
        temp_output = None

        try:
            # Download source file
            if verbose:
                print(f"   [S3] Downloading {source_key}...")

            suffix = os.path.splitext(source_key)[1] or '.tif'
            temp_input_fd, temp_input = tempfile.mkstemp(suffix=suffix)
            os.close(temp_input_fd)

            s3_client.download_file(bucket, source_key, temp_input)

            if verbose:
                file_size_mb = os.path.getsize(temp_input) / (1024 * 1024)
                print(f"   [S3] Downloaded {file_size_mb:.2f} MB")

            # Step 3: Convert to COG
            if verbose:
                print(f"   [COG] Converting to Cloud Optimized GeoTIFF...")

            temp_output_fd, temp_output = tempfile.mkstemp(suffix='.tif')
            os.close(temp_output_fd)

            # Build rio cogeo command with compression settings from config
            # Using ZSTD level 22 for maximum compression (from configs/profiles.py)
            cmd = [
                'rio', 'cogeo', 'create',
                temp_input,
                temp_output,
                '--cog-profile', 'zstd',
                '--overview-level', '5',
                '--overview-resampling', 'nearest',
                '--blocksize', '512',
                # Set compression level to 22 (maximum) as per configs/profiles.py
                '-co', 'ZSTD_LEVEL=22',
                '-co', 'PREDICTOR=2',
                '-co', 'NUM_THREADS=ALL_CPUS',
                '-co', 'BIGTIFF=IF_SAFER'
            ]

            # Add nodata if specified
            if nodata is not None:
                cmd.extend(['--nodata', str(nodata)])

            # Run conversion
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                if verbose:
                    print(f"   [COG] ❌ Conversion failed: {result.stderr}")
                return False

            if verbose:
                output_size_mb = os.path.getsize(temp_output) / (1024 * 1024)
                print(f"   [COG] ✅ Created COG ({output_size_mb:.2f} MB)")

            # Step 4: Verify COG if requested
            if verify:
                from lib.core.validation import validate_cog

                if verbose:
                    print(f"   [VALIDATE] Verifying COG...")

                is_valid, validation_details = validate_cog(temp_output)

                if not is_valid:
                    if verbose:
                        print(f"   [VALIDATE] ❌ COG validation failed")
                        for error in validation_details.get('errors', []):
                            print(f"      - {error}")
                    return False

                if verbose:
                    print(f"   [VALIDATE] ✅ COG is valid")

            # Step 5: Upload to S3
            if verbose:
                print(f"   [S3] Uploading to {dest_key}...")

            s3_client.upload_file(temp_output, bucket, dest_key)

            if verbose:
                print(f"   [S3] ✅ Uploaded successfully")

            return True

        finally:
            # Clean up temporary files
            for temp_file in [temp_input, temp_output]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass

    except Exception as e:
        if verbose:
            print(f"   [ERROR] ❌ Failed to process file: {e}")
        return False
