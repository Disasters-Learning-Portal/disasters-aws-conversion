"""
Configuration modules for disaster AWS conversion.
"""

from .profiles import (
    get_cog_profile,
    get_compression_profile,
    get_standard_profile,
    get_large_file_profile,
    get_ultra_large_profile
)

from .chunk_configs import (
    get_chunk_config,
    get_adaptive_chunk_config,
    get_fixed_chunk_config,
    get_memory_safe_config
)

__all__ = [
    # Profiles
    'get_cog_profile',
    'get_compression_profile',
    'get_standard_profile',
    'get_large_file_profile',
    'get_ultra_large_profile',
    # Chunk configs
    'get_chunk_config',
    'get_adaptive_chunk_config',
    'get_fixed_chunk_config',
    'get_memory_safe_config'
]