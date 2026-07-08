#!/usr/bin/env python3
"""
EC2-optimized script to update nodata values in GeoTIFF files while maintaining proper COG structure.
Supports S3 input/output, parallel processing, and robust error handling for cloud environments.
"""

import subprocess
import rasterio
import numpy as np
from pathlib import Path
import tempfile
import shutil
import sys
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import os


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'nodata_update_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


def parse_s3_path(s3_path):
    """Parse S3 path into bucket and key."""
    if not s3_path.startswith('s3://'):
        return None, None
    parts = s3_path[5:].split('/', 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ''
    return bucket, key


def download_from_s3(s3_path, local_path):
    """Download file from S3 to local path."""
    bucket, key = parse_s3_path(s3_path)
    if not bucket:
        raise ValueError(f"Invalid S3 path: {s3_path}")

    s3_client = boto3.client('s3')
    try:
        logger.info(f"Downloading s3://{bucket}/{key} to {local_path}")
        s3_client.download_file(bucket, key, local_path)
        return True
    except ClientError as e:
        logger.error(f"Failed to download from S3: {e}")
        return False


def upload_to_s3(local_path, s3_path):
    """Upload file from local path to S3."""
    bucket, key = parse_s3_path(s3_path)
    if not bucket:
        raise ValueError(f"Invalid S3 path: {s3_path}")

    s3_client = boto3.client('s3')
    try:
        logger.info(f"Uploading {local_path} to s3://{bucket}/{key}")
        s3_client.upload_file(local_path, bucket, key)
        return True
    except ClientError as e:
        logger.error(f"Failed to upload to S3: {e}")
        return False


def list_s3_files(s3_prefix, pattern='*.tif'):
    """List files in S3 bucket matching pattern."""
    bucket, prefix = parse_s3_path(s3_prefix)
    if not bucket:
        raise ValueError(f"Invalid S3 path: {s3_prefix}")

    s3_client = boto3.client('s3')
    files = []

    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            if 'Contents' not in page:
                continue
            for obj in page['Contents']:
                key = obj['Key']
                if key.lower().endswith(('.tif', '.tiff')):
                    files.append(f"s3://{bucket}/{key}")
        return files
    except ClientError as e:
        logger.error(f"Failed to list S3 files: {e}")
        return []


def update_nodata_cog(input_path: str, output_path: str = None, temp_dir: str = '/tmp'):
    """
    Update nodata value in a GeoTIFF file using GDAL COG driver.
    Auto-determines nodata based on data type:
    - uint8 with 0-255 range: nodata = 0
    - float32/float64: nodata = -9999

    Args:
        input_path: Path to the input GeoTIFF file (local or S3)
        output_path: Path for output file (local or S3). If None, overwrites input.
        temp_dir: Directory for temporary files (default: /tmp for EC2)

    Returns:
        bool: True if successful, False otherwise
    """
    is_s3_input = input_path.startswith('s3://')
    is_s3_output = output_path and output_path.startswith('s3://')

    # Create temp directory if it doesn't exist
    temp_dir = Path(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Handle S3 input
    if is_s3_input:
        local_input = temp_dir / f"input_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.tif"
        if not download_from_s3(input_path, str(local_input)):
            return False
        working_path = local_input
        file_display_name = input_path
    else:
        working_path = Path(input_path)
        file_display_name = working_path.name

    logger.info(f"\nProcessing: {file_display_name}")

    try:
        # Analyze the input file
        with rasterio.open(working_path) as src:
            current_nodata = src.nodata
            dtype = src.dtypes[0]
            data = src.read(1)

            logger.info(f"  Current nodata: {current_nodata}")
            logger.info(f"  Data type: {dtype}")
            logger.info(f"  Shape: {data.shape}")
            logger.info(f"  File size: {working_path.stat().st_size / (1024*1024):.2f} MB")

            # Auto-determine target nodata value
            if dtype in ['uint8', 'byte']:
                target_nodata = 0
                logger.info(f"  Target nodata: 0 (uint8)")
            elif dtype in ['float32', 'float64']:
                target_nodata = -9999
                logger.info(f"  Target nodata: -9999 (float)")
            else:
                target_nodata = -9999
                logger.info(f"  Target nodata: -9999 (default)")

            # Check if we need to remap data values
            needs_remapping = False
            extreme_values = [
                -3.4028234663852886e+38,
                3.4028234663852886e+38,
                -3.40282346638529e+38,
                3.40282346638529e+38,
                3.3999999521443642e+38,
                -3.3999999521443642e+38
            ]

            for extreme_val in extreme_values:
                if np.any(np.isclose(data, extreme_val, rtol=1e-6)):
                    needs_remapping = True
                    logger.info(f"  Detected extreme value: {extreme_val}")
                    break

        # Create temporary files
        temp_remap = temp_dir / f"remap_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.tif"
        temp_cog = temp_dir / f"cog_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.tif"

        try:
            # Step 1: If we need to remap extreme values, do it with rasterio first
            if needs_remapping:
                logger.info(f"  Step 1: Remapping extreme values to {target_nodata}")
                with rasterio.open(working_path) as src:
                    profile = src.profile.copy()
                    profile['nodata'] = target_nodata

                    # Read and remap data
                    data = src.read()
                    for extreme_val in extreme_values:
                        mask = np.isclose(data, extreme_val, rtol=1e-6)
                        if np.any(mask):
                            num_pixels = np.sum(mask)
                            data[mask] = target_nodata
                            logger.info(f"    Remapped {num_pixels} pixels from {extreme_val}")

                    # Write to temp file
                    with rasterio.open(temp_remap, 'w', **profile) as dst:
                        dst.write(data)
                        # Copy tags
                        dst.update_tags(**src.tags())

                input_for_cog = str(temp_remap)
            else:
                input_for_cog = str(working_path)

            # Step 2: Convert to proper COG using rio cogeo
            logger.info(f"  Step 2: Creating COG with proper structure")

            cmd = [
                'rio', 'cogeo', 'create',
                input_for_cog,
                str(temp_cog),
                '--cog-profile', 'zstd',
                '--overview-level', '5',
                '--overview-resampling', 'nearest',
                '--blocksize', '512',
                '--nodata', str(target_nodata)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"  ✗ Error: {result.stderr}")
                return False

            # Step 3: Handle output
            if output_path:
                if is_s3_output:
                    # Upload to S3
                    if not upload_to_s3(str(temp_cog), output_path):
                        return False
                    logger.info(f"  ✓ Successfully uploaded to {output_path}")
                else:
                    # Copy to local output path
                    shutil.copy(str(temp_cog), output_path)
                    logger.info(f"  ✓ Successfully saved to {output_path}")
            else:
                # Overwrite input
                if is_s3_input:
                    if not upload_to_s3(str(temp_cog), input_path):
                        return False
                    logger.info(f"  ✓ Successfully updated {input_path}")
                else:
                    shutil.move(str(temp_cog), str(working_path))
                    logger.info(f"  ✓ Successfully updated {working_path}")

            # Verify
            verify_path = temp_cog if temp_cog.exists() else (output_path if output_path and not is_s3_output else working_path)
            if Path(verify_path).exists():
                with rasterio.open(verify_path) as src:
                    logger.info(f"  ✓ Verified: nodata={src.nodata}, dtype={src.dtypes[0]}, overviews={len(src.overviews(1))} levels")

            return True

        finally:
            # Cleanup temp files
            for tmp in [temp_remap, temp_cog]:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to cleanup {tmp}: {e}")

            # Cleanup downloaded S3 file
            if is_s3_input and working_path.exists():
                try:
                    working_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to cleanup {working_path}: {e}")

    except Exception as e:
        logger.error(f"  ✗ Error processing {file_display_name}: {e}", exc_info=True)
        return False


def process_file_wrapper(args):
    """Wrapper function for parallel processing."""
    input_file, output_dir, temp_dir = args

    if output_dir:
        # Generate output path
        if input_file.startswith('s3://'):
            filename = input_file.split('/')[-1]
        else:
            filename = Path(input_file).name

        if output_dir.startswith('s3://'):
            output_path = f"{output_dir.rstrip('/')}/{filename}"
        else:
            output_path = str(Path(output_dir) / filename)
    else:
        output_path = None

    return input_file, update_nodata_cog(input_file, output_path, temp_dir)


def main():
    """Process GeoTIFF files with nodata value updates."""
    parser = argparse.ArgumentParser(
        description='Update nodata values in GeoTIFF files (supports S3 and parallel processing)'
    )
    parser.add_argument(
        'input',
        help='Input file, directory, or S3 path (e.g., file.tif, *.tif, s3://bucket/prefix/)'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output directory or S3 prefix (if not specified, overwrites input files)'
    )
    parser.add_argument(
        '-j', '--jobs',
        type=int,
        default=1,
        help='Number of parallel jobs (default: 1)'
    )
    parser.add_argument(
        '--temp-dir',
        default='/tmp',
        help='Directory for temporary files (default: /tmp)'
    )

    args = parser.parse_args()

    # Collect files to process
    files = []

    if args.input.startswith('s3://'):
        # S3 input
        files = list_s3_files(args.input)
        if not files:
            logger.error(f"No files found in {args.input}")
            return 1
    elif '*' in args.input or '?' in args.input:
        # Glob pattern
        files = [str(f) for f in Path('.').glob(args.input)]
    else:
        # Single file or directory
        input_path = Path(args.input)
        if input_path.is_file():
            files = [str(input_path)]
        elif input_path.is_dir():
            files = [str(f) for f in input_path.iterdir() if f.suffix.lower() in ('.tif', '.tiff')]
        else:
            logger.error(f"Invalid input: {args.input}")
            return 1

    if not files:
        logger.error(f"No files found matching: {args.input}")
        return 1

    logger.info(f"Found {len(files)} file(s) to process")
    logger.info(f"Using {args.jobs} parallel job(s)")

    # Process files
    success_count = 0
    failed_files = []

    if args.jobs == 1:
        # Sequential processing
        for input_file in files:
            result = process_file_wrapper((input_file, args.output, args.temp_dir))
            if result[1]:
                success_count += 1
            else:
                failed_files.append(result[0])
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = [
                executor.submit(process_file_wrapper, (f, args.output, args.temp_dir))
                for f in files
            ]

            for future in as_completed(futures):
                try:
                    input_file, success = future.result()
                    if success:
                        success_count += 1
                    else:
                        failed_files.append(input_file)
                except Exception as e:
                    logger.error(f"Error in worker thread: {e}", exc_info=True)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"✓ Successfully processed {success_count}/{len(files)} files")

    if failed_files:
        logger.error(f"\n✗ Failed files ({len(failed_files)}):")
        for failed_file in failed_files:
            logger.error(f"  - {failed_file}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
