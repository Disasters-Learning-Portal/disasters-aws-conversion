"""
Reprojection module - handles coordinate system transformations.
Single responsibility: Reprojection and coordinate transformation.
"""

import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.windows import Window
import gc
from tqdm import tqdm


def calculate_transform_parameters(src, dst_crs='EPSG:4326'):
    """
    Calculate transformation parameters for reprojection.

    Args:
        src: Source rasterio dataset
        dst_crs: Destination CRS

    Returns:
        tuple: (transform, width, height)
    """
    transform, width, height = calculate_default_transform(
        src.crs, dst_crs, src.width, src.height, *src.bounds
    )
    return transform, width, height


def reproject_chunk(src, band_idx, src_window, dst_window, src_transform,
                   dst_transform, src_crs, dst_crs, src_nodata, chunk_data):
    """
    Reproject a single chunk of data.

    Args:
        src: Source dataset
        band_idx: Band index to reproject
        src_window: Source window
        dst_window: Destination window
        src_transform: Source transform
        dst_transform: Destination transform
        src_crs: Source CRS
        dst_crs: Destination CRS
        src_nodata: Source nodata value
        chunk_data: Array to fill with reprojected data

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        reproject(
            source=rasterio.band(src, band_idx),
            destination=chunk_data,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
            src_nodata=src_nodata,
            dst_nodata=src_nodata
        )
        return True

    except Exception as e:
        print(f"   [REPROJECT ERROR] Failed to reproject chunk: {e}")
        return False


def process_with_fixed_chunks(src, dst, src_crs, dst_crs, transform, width, height,
                             chunk_size, src_nodata, chunk_config, initial_memory):
    """
    Process file with FIXED chunk size throughout the entire operation.
    This prevents the striping issue caused by changing chunk sizes mid-loop.

    Args:
        src: Source dataset
        dst: Destination dataset
        src_crs: Source CRS
        dst_crs: Destination CRS
        transform: Destination transform
        width: Destination width
        height: Destination height
        chunk_size: FIXED chunk size to use
        src_nodata: Nodata value
        chunk_config: Chunk configuration
        initial_memory: Initial memory usage

    Returns:
        None
    """
    from ..utils.memory_management import get_memory_usage
    from ..core.validation import check_and_fix_nan_values

    # Ensure chunk_size stays fixed
    FIXED_CHUNK_SIZE = chunk_size
    print(f"   [CHUNKS] Using FIXED chunk size: {FIXED_CHUNK_SIZE}x{FIXED_CHUNK_SIZE}")

    # Calculate total chunks
    total_chunks_x = (width + FIXED_CHUNK_SIZE - 1) // FIXED_CHUNK_SIZE
    total_chunks_y = (height + FIXED_CHUNK_SIZE - 1) // FIXED_CHUNK_SIZE
    total_chunks = total_chunks_x * total_chunks_y

    print(f"   [CHUNKS] Processing {total_chunks} chunks ({total_chunks_x}x{total_chunks_y}) with fixed size {FIXED_CHUNK_SIZE}x{FIXED_CHUNK_SIZE}")

    # Process each band
    for band_idx in range(1, src.count + 1):
        print(f"   [BAND {band_idx}/{src.count}] Processing...")

        chunk_iterator = tqdm(total=total_chunks, desc="Processing chunks", disable=not chunk_config.get('show_progress', True))

        for chunk_y in range(0, height, FIXED_CHUNK_SIZE):
            for chunk_x in range(0, width, FIXED_CHUNK_SIZE):
                # Calculate window size (handle edge chunks)
                win_width = min(FIXED_CHUNK_SIZE, width - chunk_x)
                win_height = min(FIXED_CHUNK_SIZE, height - chunk_y)

                # Check memory and use sub-chunking if needed
                current_memory = get_memory_usage()
                memory_safe_mode = current_memory > chunk_config.get('memory_limit_mb', 500)

                if memory_safe_mode and win_width > 128 and win_height > 128:
                    # Process in smaller sub-chunks but maintain grid alignment
                    sub_chunk_size = 128

                    for sub_y in range(0, win_height, sub_chunk_size):
                        for sub_x in range(0, win_width, sub_chunk_size):
                            sub_win_width = min(sub_chunk_size, win_width - sub_x)
                            sub_win_height = min(sub_chunk_size, win_height - sub_y)

                            # Calculate actual positions
                            x = chunk_x + sub_x
                            y = chunk_y + sub_y

                            # Create windows
                            dst_window = Window(x, y, sub_win_width, sub_win_height)

                            # Initialize chunk
                            chunk_data = np.full(
                                (sub_win_height, sub_win_width),
                                src_nodata if src_nodata is not None else 0,
                                dtype=src.dtypes[0]
                            )

                            # Reproject sub-chunk with error handling
                            try:
                                reproject(
                                    source=rasterio.band(src, band_idx),
                                    destination=chunk_data,
                                    src_transform=src.transform,
                                    src_crs=src_crs,
                                    dst_transform=rasterio.windows.transform(dst_window, transform),
                                    dst_crs=dst_crs,
                                    resampling=Resampling.nearest,
                                    src_nodata=src_nodata,
                                    dst_nodata=src_nodata
                                )
                            except Exception as reproject_error:
                                print(f"\n   [CHUNK ERROR] Failed at chunk ({x}, {y}) window ({sub_x}, {sub_y})")
                                print(f"   [CHUNK ERROR] Window size: {sub_win_width}x{sub_win_height}")
                                print(f"   [CHUNK ERROR] Error: {str(reproject_error)}")

                                # If we're streaming and getting chunk errors, switch to download
                                if "chunk and warp" in str(reproject_error).lower() and "/vsis3/" in str(getattr(src, 'name', '')):
                                    print(f"   [CHUNK ERROR] Streaming error detected - need to switch to download mode")
                                    raise Exception("STREAMING_CHUNK_ERROR: Need to retry with download")

                                # Try to recover by filling with nodata
                                print(f"   [CHUNK RECOVERY] Filling failed chunk with nodata value")
                                chunk_data.fill(src_nodata if src_nodata is not None else 0)

                            # Fix NaN values
                            chunk_data, _ = check_and_fix_nan_values(
                                chunk_data, src_nodata, src.dtypes[0], band_idx=None
                            )

                            # Write sub-chunk
                            dst.write(chunk_data, band_idx, window=dst_window)

                            del chunk_data
                            gc.collect()
                else:
                    # Normal processing for full chunk
                    window = Window(chunk_x, chunk_y, win_width, win_height)

                    # Initialize chunk
                    chunk_data = np.full(
                        (win_height, win_width),
                        src_nodata if src_nodata is not None else 0,
                        dtype=src.dtypes[0]
                    )

                    # Reproject chunk with error handling
                    try:
                        reproject(
                            source=rasterio.band(src, band_idx),
                            destination=chunk_data,
                            src_transform=src.transform,
                            src_crs=src_crs,
                            dst_transform=rasterio.windows.transform(window, transform),
                            dst_crs=dst_crs,
                            resampling=Resampling.nearest,
                            src_nodata=src_nodata,
                            dst_nodata=src_nodata
                        )
                    except Exception as reproject_error:
                        print(f"\n   [CHUNK ERROR] Failed at chunk ({chunk_x}, {chunk_y}), band {band_idx}")
                        print(f"   [CHUNK ERROR] Window: {window}")
                        print(f"   [CHUNK ERROR] Error type: {type(reproject_error).__name__}")
                        print(f"   [CHUNK ERROR] Error message: {str(reproject_error)}")

                        # Check if it's a streaming issue
                        if ("curl" in str(reproject_error).lower() or
                            "vsi" in str(reproject_error).lower() or
                            "chunk and warp" in str(reproject_error).lower()):

                            # Check if we're actually streaming
                            if "/vsis3/" in str(getattr(src, 'name', '')):
                                print(f"   [CHUNK ERROR] S3 streaming error detected")
                                raise Exception("STREAMING_CHUNK_ERROR: Need to retry with download")

                        # Try to recover by filling with nodata
                        print(f"   [CHUNK RECOVERY] Attempting recovery by filling with nodata")
                        chunk_data.fill(src_nodata if src_nodata is not None else 0)

                    # Fix NaN values
                    chunk_data, _ = check_and_fix_nan_values(
                        chunk_data, src_nodata, src.dtypes[0], band_idx=None
                    )

                    # Write chunk
                    dst.write(chunk_data, band_idx, window=window)

                    del chunk_data
                    if chunk_config.get('aggressive_gc', False):
                        gc.collect()

                chunk_iterator.update(1)

        chunk_iterator.close()

        # Memory report after each band
        if chunk_config.get('enable_memory_monitoring', True):
            current_memory = get_memory_usage()
            print(f"      Memory after band {band_idx}: {current_memory:.1f} MB")

        # Aggressive GC after each band
        if chunk_config.get('aggressive_gc', False):
            gc.collect()