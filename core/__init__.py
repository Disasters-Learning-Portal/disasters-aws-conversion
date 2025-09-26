"""
Core functionality for disaster AWS conversion.
"""

from .s3_operations import (
    initialize_s3_client,
    check_s3_file_exists,
    download_from_s3,
    upload_to_s3,
    setup_vsi_credentials,
    list_s3_files,
    get_file_size_from_s3
)

from .validation import (
    validate_cog,
    check_and_fix_nan_values,
    validate_data_integrity,
    check_cog_with_warnings
)

from .reprojection import (
    reproject_chunk,
    calculate_transform_parameters,
    process_with_fixed_chunks
)

from .compression import (
    get_predictor_for_dtype,
    get_compression_config,
    set_nodata_value,
    set_nodata_value_src
)

__all__ = [
    # S3 operations
    'initialize_s3_client',
    'check_s3_file_exists',
    'download_from_s3',
    'upload_to_s3',
    'setup_vsi_credentials',
    'list_s3_files',
    'get_file_size_from_s3',
    # Validation
    'validate_cog',
    'check_and_fix_nan_values',
    'validate_data_integrity',
    'check_cog_with_warnings',
    # Reprojection
    'reproject_chunk',
    'calculate_transform_parameters',
    'process_with_fixed_chunks',
    # Compression
    'get_predictor_for_dtype',
    'get_compression_config',
    'set_nodata_value',
    'set_nodata_value_src'
]