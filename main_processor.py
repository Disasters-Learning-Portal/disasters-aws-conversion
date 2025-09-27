"""
Main processor that combines all modules for complete file processing.
This is the primary entry point for COG conversion.
"""

import os
import gc
import tempfile
import rasterio
import numpy as np
from datetime import datetime

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
from core.reprojection import calculate_transform_parameters, process_with_fixed_chunks

# Import utils
from utils.memory_management import get_memory_usage, get_available_memory_mb
from utils.error_handling import cleanup_temp_files, setup_temp_directory
from utils.logging import print_status

# Import processors
from processors.cog_creator import create_cog_with_overviews

# Import configs
from configs.profiles import select_profile_by_size, get_compression_profile
from configs.chunk_configs import get_chunk_config


def convert_to_cog(name, bucket, cog_filename, cog_data_bucket, cog_data_prefix,
                   s3_client, cog_profile=None, local_output_dir=None,
                   chunk_config=None, manual_nodata=None, overwrite=False):
    """
    Main function to convert a file to Cloud Optimized GeoTIFF.

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

    Returns:
        None (raises exception on error)
    """
    # Initialize
    start_time = datetime.now()
    s3_key = f"{cog_data_prefix}/{cog_filename}"
    reproject_filename = f"reproj/{cog_filename}"
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

        # Step 2: Get file size and select appropriate configuration
        file_size_gb = get_file_size_from_s3(s3_client, bucket, name)
        print(f"   [INFO] File size: {file_size_gb:.1f} GB")

        # Auto-select configuration if not provided
        if chunk_config is None:
            chunk_config = get_chunk_config(file_size_gb)
            print(f"   [CONFIG] Using {'fixed' if not chunk_config['adaptive_chunks'] else 'adaptive'} chunks")

        # Step 3: Setup directories
        os.makedirs("reproj", exist_ok=True)
        setup_temp_directory()

        # Step 4: Memory monitoring
        initial_memory = get_memory_usage()
        available_memory = get_available_memory_mb()
        print(f"   [MEMORY] Initial: {initial_memory:.1f} MB, Available: {available_memory:.1f} MB")

        # Step 5: Determine input path (streaming vs download)
        input_path = None

        # Try streaming first if configured
        if chunk_config.get('use_streaming', True) and setup_vsi_credentials(s3_client):
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

        # Step 6: Process file
        with rasterio.open(input_path) as src:
            # Get chunk size based on configuration
            chunk_size = chunk_config.get('default_chunk_size', 512)
            if not chunk_config.get('adaptive_chunks', True):
                print(f"   [CHUNKS] Using FIXED chunk size: {chunk_size}x{chunk_size}")
            else:
                print(f"   [CHUNKS] Using adaptive chunk size starting at: {chunk_size}x{chunk_size}")

            # Calculate reprojection parameters
            print(f"   [REPROJECT] Converting to EPSG:4326 using fixed-grid chunked processing...")
            dst_crs = 'EPSG:4326'
            transform, width, height = calculate_transform_parameters(src, dst_crs)

            # Get or set nodata value
            if manual_nodata is not None:
                # Use manual no-data if provided
                src_nodata = manual_nodata
                print(f"   [NODATA] Using manual no-data value: {manual_nodata}")
            elif src.nodata is not None:
                src_nodata = src.nodata
                print(f"   [NODATA] Using existing no-data value: {src.nodata}")
            else:
                src_nodata = set_nodata_value_src(src, manual_nodata)

            # Get appropriate predictor
            predictor = get_predictor_for_dtype(src.dtypes[0])

            # Prepare output profile
            kwargs = src.meta.copy()
            kwargs.update({
                'driver': 'GTiff',
                'compress': 'ZSTD',
                'zstd_level': 9,
                'predictor': predictor,
                'crs': dst_crs,
                'transform': transform,
                'width': width,
                'height': height,
                'tiled': True,
                'blockxsize': 512,
                'blockysize': 512,
                'nodata': src_nodata
            })

            # Process with fixed chunks
            with rasterio.open(reproject_filename, 'w', **kwargs) as dst:
                process_with_fixed_chunks(
                    src, dst, src.crs, dst_crs, transform,
                    width, height, chunk_size, src_nodata,
                    chunk_config, initial_memory
                )

        temp_files.append(reproject_filename)
        print(f"   [COGIFY] Preparing file for upload...")

        # Step 7: Check if already valid COG
        is_valid_cog = check_cog_with_warnings(reproject_filename)

        if is_valid_cog:
            print(f"   [COG] Reprojected file is already a valid COG, but rebuilding with overviews...")
        else:
            print(f"   [COG] Creating optimized COG using rasterio...")

        # Step 8: Create final COG with maximum compression and overviews
        file_size_mb = os.path.getsize(reproject_filename) / (1024 * 1024)
        print(f"   [COG] Processing {file_size_mb:.1f} MB file...")

        # Get compression configuration
        compression_config = get_compression_profile(
            dtype=str(src.dtypes[0]),
            file_size_gb=file_size_mb / 1024
        )

        # Create temporary COG with overviews
        temp_cog = f"cog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tif"
        temp_files.append(temp_cog)

        if create_cog_with_overviews(reproject_filename, temp_cog, compression_config):
            # Upload to S3
            if upload_to_s3(s3_client, temp_cog, cog_data_bucket, s3_key):
                print(f"   [SUCCESS] ✅ Uploaded to s3://{cog_data_bucket}/{s3_key}")

                # Save locally if requested
                if local_output_dir:
                    os.makedirs(local_output_dir, exist_ok=True)
                    local_path = os.path.join(local_output_dir, cog_filename)
                    import shutil
                    shutil.copy2(temp_cog, local_path)
                    print(f"   [LOCAL] Saved to {local_path}")
            else:
                raise Exception("Failed to upload COG to S3")
        else:
            raise Exception("Failed to create COG")

        # Step 9: Report memory usage
        final_memory = get_memory_usage()
        print(f"   [MEMORY] Final: {final_memory:.1f} MB (Change: {final_memory - initial_memory:+.1f} MB)")

        # Step 10: Report total time
        total_time = (datetime.now() - start_time).total_seconds()
        print(f"   [TIME] Total processing time: {total_time:.1f} seconds")

    except Exception as e:
        print(f"   [ERROR] {str(e)}")

        # Check for specific errors and retry
        error_msg = str(e).lower()
        if ("streaming_chunk_error" in error_msg or
            "chunk and warp" in error_msg) and chunk_config.get('use_streaming', True):
            print(f"   [RETRY] Streaming error detected, retrying with download...")

            # Retry with download
            new_config = chunk_config.copy()
            new_config['use_streaming'] = False
            return convert_to_cog(
                name, bucket, cog_filename, cog_data_bucket, cog_data_prefix,
                s3_client, cog_profile, local_output_dir, new_config
            )

        raise

    finally:
        # Cleanup temporary files
        cleanup_temp_files(*temp_files)
        gc.collect()


# Wrapper for backwards compatibility
def convert_to_proper_CRS_and_cogify_improved_fixed(name, BUCKET, cog_filename,
                                                    cog_data_bucket, cog_data_prefix,
                                                    s3_client, COG_PROFILE=None,
                                                    local_output_dir=None,
                                                    chunk_config=None,
                                                    manual_nodata=None,
                                                    overwrite=False):
    """
    Wrapper function for backwards compatibility with existing notebooks.
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