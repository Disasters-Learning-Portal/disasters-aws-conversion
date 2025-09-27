"""
Optimized main processor using rio-cogeo for single-pass COG creation.
This version eliminates double processing by creating COGs directly.
"""

import os
import gc
import tempfile
import rasterio
import numpy as np
from datetime import datetime
from rio_cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

# Import core modules
from core.s3_operations import (
    check_s3_file_exists,
    download_from_s3,
    upload_to_s3,
    setup_vsi_credentials,
    get_file_size_from_s3
)
from core.validation import check_cog_with_warnings
from core.compression import set_nodata_value_src, get_predictor_for_dtype
from utils.memory_management import get_memory_usage, get_available_memory_mb
from utils.error_handling import cleanup_temp_files, setup_temp_directory
from utils.logging import print_status
from configs.chunk_configs import get_chunk_config


def convert_to_cog_optimized(name, bucket, cog_filename, cog_data_bucket, cog_data_prefix,
                             s3_client, cog_profile=None, local_output_dir=None,
                             chunk_config=None, manual_nodata=None, overwrite=False,
                             skip_validation=True):
    """
    Optimized COG conversion using rio-cogeo for single-pass processing.

    Args:
        name: S3 key of source file
        bucket: Source S3 bucket
        cog_filename: Output COG filename
        cog_data_bucket: Destination S3 bucket
        cog_data_prefix: Destination S3 prefix
        s3_client: Boto3 S3 client
        cog_profile: COG profile (optional)
        local_output_dir: Local output directory (optional)
        chunk_config: Chunk configuration (optional)
        manual_nodata: Manual no-data value (optional)
        overwrite: Whether to overwrite existing files (default: False)
        skip_validation: Skip COG validation for speed (default: True)

    Returns:
        None (raises exception on error)
    """
    # Initialize
    start_time = datetime.now()
    s3_key = f"{cog_data_prefix}/{cog_filename}"
    cog_output_path = f"cog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tif"
    temp_files = []

    try:
        # Step 1: Check if file already exists in S3
        print(f"   [CHECK] Checking if file already exists in S3: s3://{cog_data_bucket}/{s3_key}")
        if check_s3_file_exists(s3_client, cog_data_bucket, s3_key):
            if overwrite:
                print(f"   [OVERWRITE] File exists but overwrite=True, reprocessing: {cog_filename}")
            else:
                print(f"   [SKIP] File already exists in S3, skipping processing: {cog_filename}")
                raise FileExistsError(f"File already exists: {cog_filename}")

        # Step 2: Get file size
        file_size_gb = get_file_size_from_s3(s3_client, bucket, name)
        print(f"   [INFO] File size: {file_size_gb:.1f} GB")

        # Step 3: Setup directories
        setup_temp_directory()

        # Step 4: Memory monitoring
        initial_memory = get_memory_usage()
        available_memory = get_available_memory_mb()
        print(f"   [MEMORY] Initial: {initial_memory:.1f} MB, Available: {available_memory:.1f} MB")

        # Step 5: Determine input path (streaming vs download)
        input_path = None

        # Try streaming first
        if setup_vsi_credentials(s3_client):
            input_path = f"/vsis3/{bucket}/{name}"
            print(f"   [STREAM] Attempting to stream from S3: {input_path}")

            # Test if streaming works
            try:
                with rasterio.open(input_path) as test_src:
                    _ = test_src.profile
                print(f"   [STREAM] ✅ Successfully opened file via streaming")
            except Exception as e:
                print(f"   [STREAM] ❌ Streaming failed: {e}")
                input_path = None

        # Fallback to download
        if input_path is None:
            local_download_path = f"data_download/{name}"
            os.makedirs(os.path.dirname(local_download_path), exist_ok=True)

            if os.path.exists(local_download_path):
                print(f"   [CACHE HIT] Using cached file: {local_download_path}")
                input_path = local_download_path
            else:
                print(f"   [DOWNLOAD] Downloading from S3...")
                if download_from_s3(s3_client, bucket, name, local_download_path):
                    input_path = local_download_path
                    temp_files.append(local_download_path)
                else:
                    raise Exception("Failed to download file from S3")

        # Step 6: Determine no-data value
        with rasterio.open(input_path) as src:
            if manual_nodata is not None:
                src_nodata = manual_nodata
                print(f"   [NODATA] Using manual no-data value: {manual_nodata}")
            elif src.nodata is not None:
                src_nodata = src.nodata
                print(f"   [NODATA] Using existing no-data value: {src.nodata}")
            else:
                src_nodata = set_nodata_value_src(src, manual_nodata)
                print(f"   [NODATA] Set no-data value: {src_nodata}")

            # Get data type for predictor
            dtype = src.dtypes[0]
            predictor = get_predictor_for_dtype(dtype)

        # Step 7: Create COG using rio-cogeo (single pass!)
        print(f"   [COG] Creating COG with reprojection in single pass...")

        # Prepare COG profile
        output_profile = cog_profiles.get("zstd")
        output_profile.update({
            "ZSTD_LEVEL": 22,  # Maximum compression as requested
            "PREDICTOR": predictor,
            "BLOCKSIZE": 512
        })

        # Additional options for cog_translate
        config = {
            "GDAL_NUM_THREADS": "ALL_CPUS",
            "GDAL_TIFF_INTERNAL_MASK": "YES",
            "GDAL_TIFF_OVR_BLOCKSIZE": "512"
        }

        # Use rio-cogeo to create COG with reprojection
        cog_translate(
            input_path,
            cog_output_path,
            output_profile,
            dst_crs="EPSG:4326",  # Reproject to WGS84
            nodata=src_nodata,
            overview_level=5,  # Create 5 levels of overviews
            overview_resampling="average",
            config=config,
            quiet=False
        )

        temp_files.append(cog_output_path)
        print(f"   [COG] ✅ COG created successfully")

        # Step 8: Optional validation
        if not skip_validation:
            is_valid_cog = check_cog_with_warnings(cog_output_path)
            if not is_valid_cog:
                print(f"   [WARNING] COG validation failed but continuing...")

        # Step 9: Upload to S3
        print(f"   [UPLOAD] Uploading to S3...")
        if upload_to_s3(s3_client, cog_output_path, cog_data_bucket, s3_key):
            print(f"   [UPLOAD] ✅ Successfully uploaded to s3://{cog_data_bucket}/{s3_key}")

            # Save locally if requested
            if local_output_dir:
                os.makedirs(local_output_dir, exist_ok=True)
                local_path = os.path.join(local_output_dir, cog_filename)
                import shutil
                shutil.copy2(cog_output_path, local_path)
                print(f"   [LOCAL] Saved to {local_path}")
        else:
            raise Exception("Failed to upload COG to S3")

        # Step 10: Report performance
        final_memory = get_memory_usage()
        print(f"   [MEMORY] Final: {final_memory:.1f} MB (Change: {final_memory - initial_memory:+.1f} MB)")

        total_time = (datetime.now() - start_time).total_seconds()
        print(f"   [TIME] Total processing time: {total_time:.1f} seconds")

    except Exception as e:
        print(f"   [ERROR] {str(e)}")
        raise

    finally:
        # Cleanup temporary files
        cleanup_temp_files(*temp_files)
        gc.collect()


# Wrapper for backwards compatibility
def convert_to_cog(name, bucket, cog_filename, cog_data_bucket, cog_data_prefix,
                   s3_client, cog_profile=None, local_output_dir=None,
                   chunk_config=None, manual_nodata=None, overwrite=False):
    """
    Wrapper function that redirects to optimized version.
    """
    return convert_to_cog_optimized(
        name=name,
        bucket=bucket,
        cog_filename=cog_filename,
        cog_data_bucket=cog_data_bucket,
        cog_data_prefix=cog_data_prefix,
        s3_client=s3_client,
        cog_profile=cog_profile,
        local_output_dir=local_output_dir,
        chunk_config=chunk_config,
        manual_nodata=manual_nodata,
        overwrite=overwrite,
        skip_validation=True  # Skip validation by default for speed
    )


# Legacy wrapper for notebooks
def convert_to_proper_CRS_and_cogify_improved_fixed(name, BUCKET, cog_filename,
                                                    cog_data_bucket, cog_data_prefix,
                                                    s3_client, COG_PROFILE=None,
                                                    local_output_dir=None,
                                                    chunk_config=None,
                                                    manual_nodata=None,
                                                    overwrite=False):
    """
    Legacy wrapper function for backwards compatibility with existing notebooks.
    """
    return convert_to_cog(
        name=name,
        bucket=BUCKET,
        cog_filename=cog_filename,
        cog_data_bucket=cog_data_bucket,
        cog_data_prefix=cog_data_prefix,
        s3_client=s3_client,
        cog_profile=COG_PROFILE,
        local_output_dir=local_output_dir,
        chunk_config=chunk_config,
        manual_nodata=manual_nodata,
        overwrite=overwrite
    )