"""
Validation module - handles COG validation and data integrity checks.
Single responsibility: Data and format validation.
"""

import numpy as np
from rio_cogeo.cogeo import cog_validate
from rio_cogeo.cogeo import cog_info


def validate_cog(file_path):
    """
    Validate if a file is a proper Cloud Optimized GeoTIFF.

    Args:
        file_path: Path to the file to validate

    Returns:
        tuple: (is_valid, validation_details)
    """
    try:
        # Use rio-cogeo for validation
        is_valid = cog_validate(file_path, quiet=True)[0]

        # Get detailed info if needed
        info = cog_info(file_path)

        validation_details = {
            'valid': is_valid,
            'errors': [],
            'warnings': []
        }

        if not is_valid:
            validation_details['errors'].append("File is not a valid COG")

        return is_valid, validation_details

    except Exception as e:
        return False, {'valid': False, 'errors': [str(e)], 'warnings': []}


def check_cog_with_warnings(file_path, verbose=True):
    """
    Check COG validity and print warnings.

    Args:
        file_path: Path to the file to validate
        verbose: Print validation messages

    Returns:
        bool: True if valid COG
    """
    if verbose:
        print(f"   [VALIDATE] Checking COG validity...")

    is_valid, validation_details = validate_cog(file_path)

    if is_valid:
        if verbose:
            print(f"   [VALIDATE] ✅ Valid COG")
    else:
        if verbose:
            print(f"   [VALIDATE] ⚠️ COG validation warnings")
            if 'errors' in validation_details:
                for error in validation_details['errors']:
                    print(f"      - {error}")
            if 'warnings' in validation_details:
                for warning in validation_details['warnings']:
                    print(f"      - {warning}")

    return is_valid


def check_and_fix_nan_values(data, nodata_value, dtype, band_idx=None, verbose=False):
    """
    Check for NaN values and fix them.

    Args:
        data: numpy array with data
        nodata_value: Value to use for nodata
        dtype: Data type of the array
        band_idx: Band index for reporting
        verbose: Print messages

    Returns:
        tuple: (fixed_data, had_nan)
    """
    had_nan = False

    # Check for NaN values (only for float dtypes)
    if np.issubdtype(dtype, np.floating):
        nan_count = np.isnan(data).sum()
        if nan_count > 0:
            had_nan = True
            if verbose:
                band_str = f"band {band_idx}" if band_idx else "data"
                print(f"   [NAN] Found {nan_count} NaN values in {band_str}")

            # Replace NaN with nodata value
            data = np.where(np.isnan(data), nodata_value, data)

            if verbose:
                print(f"   [NAN] Replaced NaN values with {nodata_value}")

    # Check for infinity values
    if np.issubdtype(dtype, np.floating):
        inf_count = np.isinf(data).sum()
        if inf_count > 0:
            had_nan = True
            if verbose:
                print(f"   [INF] Found {inf_count} infinity values")

            # Replace infinity with nodata value
            data = np.where(np.isinf(data), nodata_value, data)

    return data, had_nan


def validate_data_integrity(data, expected_shape=None, expected_dtype=None, verbose=True):
    """
    Validate data integrity with comprehensive checks.

    Args:
        data: numpy array to validate
        expected_shape: Expected shape tuple
        expected_dtype: Expected data type
        verbose: Print validation messages

    Returns:
        dict: Validation results
    """
    results = {
        'valid': True,
        'issues': [],
        'stats': {}
    }

    # Check shape
    if expected_shape and data.shape != expected_shape:
        results['valid'] = False
        results['issues'].append(f"Shape mismatch: expected {expected_shape}, got {data.shape}")

    # Check dtype
    if expected_dtype and data.dtype != expected_dtype:
        results['issues'].append(f"Dtype mismatch: expected {expected_dtype}, got {data.dtype}")

    # Calculate statistics
    results['stats']['shape'] = data.shape
    results['stats']['dtype'] = str(data.dtype)
    results['stats']['min'] = float(np.nanmin(data))
    results['stats']['max'] = float(np.nanmax(data))
    results['stats']['mean'] = float(np.nanmean(data))
    results['stats']['has_nan'] = bool(np.isnan(data).any())
    results['stats']['has_inf'] = bool(np.isinf(data).any())

    # Check for common issues
    if results['stats']['has_nan']:
        results['issues'].append("Data contains NaN values")

    if results['stats']['has_inf']:
        results['issues'].append("Data contains infinity values")

    # Check if all values are the same
    if np.all(data == data.flat[0]):
        results['issues'].append("All values are identical")

    if verbose and results['issues']:
        print(f"   [VALIDATE] Data validation issues found:")
        for issue in results['issues']:
            print(f"      - {issue}")

    return results