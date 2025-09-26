"""
Compression module - handles compression settings and nodata values.
Single responsibility: Compression configuration and data type handling.
"""


def get_predictor_for_dtype(dtype):
    """
    Determine the appropriate predictor based on data type.

    Args:
        dtype: numpy dtype or string representation of dtype

    Returns:
        int: Predictor value (1, 2, or 3)
    """
    dtype_str = str(dtype)

    # Integer types use predictor 2 (horizontal differencing)
    if dtype_str in ['uint8', 'uint16', 'uint32', 'int8', 'int16', 'int32']:
        return 2

    # Floating-point types use predictor 3 (floating point predictor)
    elif dtype_str in ['float32', 'float64']:
        return 3

    # Default to no predictor
    else:
        return 1


def set_nodata_value(ds):
    """
    Set appropriate nodata value based on data type for a dataset object.

    Args:
        ds: Dataset object with dtype attribute

    Returns:
        Appropriate nodata value for the data type
    """
    print(f"   [NODATA] Data type: {ds.dtype}")

    if ds.dtype == 'uint8':
        # For uint8 data, use 0 as nodata
        nodata_value = 0
        print(f"   [NODATA] Using nodata value {nodata_value} for uint8 data")

    elif ds.dtype == 'uint16':
        # For uint16, use 0 as nodata
        nodata_value = 0
        print(f"   [NODATA] Using nodata value {nodata_value} for uint16 data")

    elif ds.dtype == 'int8':
        # For int8, must use value within -128 to 127 range
        nodata_value = -128
        print(f"   [NODATA] Using nodata value {nodata_value} for int8 data")

    elif ds.dtype == 'int16':
        # For int16, -9999 is fine
        nodata_value = -9999
        print(f"   [NODATA] Using nodata value {nodata_value} for int16 data")

    else:
        # For float32, int32, etc., use -9999
        nodata_value = -9999
        print(f"   [NODATA] Using nodata value {nodata_value} for {ds.dtype} data")

    return nodata_value


def set_nodata_value_src(src):
    """
    Set appropriate nodata value based on data type for a rasterio source.

    Args:
        src: Rasterio source object with dtypes attribute

    Returns:
        Appropriate nodata value for the data type
    """
    print(f"   [NODATA] Data type: {src.dtypes[0]}")

    if src.dtypes[0] == 'uint8':
        # For uint8 data, use 0 as nodata
        nodata_value = 0
        print(f"   [NODATA] Using nodata value {nodata_value} for uint8 data")

    elif src.dtypes[0] == 'uint16':
        # For uint16, use 0 as nodata
        nodata_value = 0
        print(f"   [NODATA] Using nodata value {nodata_value} for uint16 data")

    elif src.dtypes[0] == 'int8':
        # For int8, must use value within -128 to 127 range
        nodata_value = -128
        print(f"   [NODATA] Using nodata value {nodata_value} for int8 data")

    elif src.dtypes[0] == 'int16':
        # For int16, -9999 is fine
        nodata_value = -9999
        print(f"   [NODATA] Using nodata value {nodata_value} for int16 data")

    else:
        # For float32, int32, etc., use -9999
        nodata_value = -9999
        print(f"   [NODATA] Using nodata value {nodata_value} for {src.dtypes[0]} data")

    return nodata_value


def get_compression_config(file_size_gb=0, dtype='float32'):
    """
    Get optimal compression configuration based on file size and data type.

    Args:
        file_size_gb: File size in gigabytes
        dtype: Data type string

    Returns:
        dict: Compression configuration
    """
    # Base configuration
    config = {
        'driver': 'GTiff',
        'compress': 'zstd',
        'zstd_level': 22,  # Maximum compression
        'tiled': True,
        'blockxsize': 512,
        'blockysize': 512,
        'bigtiff': 'YES' if file_size_gb > 3 else 'IF_SAFER',
        'num_threads': 'ALL_CPUS'
    }

    # Add predictor based on data type
    config['predictor'] = get_predictor_for_dtype(dtype)

    # Adjust for very large files
    if file_size_gb > 10:
        config['blockxsize'] = 256
        config['blockysize'] = 256

    return config


def export_cog_profile():
    """
    Export standard COG profile configuration.

    Returns:
        dict: COG profile settings
    """
    return {
        'driver': 'GTiff',
        'compress': 'ZSTD',
        'zstd_level': 22,
        'predictor': 2,
        'tiled': True,
        'blockxsize': 512,
        'blockysize': 512,
        'bigtiff': 'IF_SAFER',
        'num_threads': 'ALL_CPUS'
    }