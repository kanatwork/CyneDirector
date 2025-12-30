# [FILE: core/performance.py]
"""
Performance monitoring and optimization utilities.
"""
import os
from core.logger import get_logger

logger = get_logger(__name__)

# Try to import psutil, but handle gracefully if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - using default memory estimates")

def get_available_memory_mb():
    """Get available system memory in MB."""
    if not PSUTIL_AVAILABLE:
        return 4096  # Default to 4GB if psutil not available
    try:
        return psutil.virtual_memory().available / (1024 * 1024)
    except:
        return 4096  # Default to 4GB if we can't detect

def get_optimal_batch_size(base_batch_size=32, min_batch=8, max_batch=128):
    """
    Calculate optimal batch size based on available memory.
    
    Args:
        base_batch_size: Default batch size
        min_batch: Minimum batch size
        max_batch: Maximum batch size
    
    Returns:
        Optimal batch size
    """
    try:
        available_mb = get_available_memory_mb()
        
        # Adjust batch size based on available memory
        if available_mb > 16000:  # > 16GB RAM
            optimal = min(max_batch, base_batch_size * 2)
        elif available_mb > 8000:  # > 8GB RAM
            optimal = base_batch_size
        elif available_mb > 4000:  # > 4GB RAM
            optimal = max(min_batch, int(base_batch_size * 0.75))
        else:  # < 4GB RAM
            optimal = min_batch
        
        logger.debug(f"Optimal batch size: {optimal} (available RAM: {available_mb:.0f}MB)")
        return optimal
    except Exception as e:
        logger.warning(f"Could not determine optimal batch size: {e}, using default")
        return base_batch_size

def get_memory_usage_mb():
    """Get current process memory usage in MB."""
    if not PSUTIL_AVAILABLE:
        return 0
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except:
        return 0

def log_memory_usage(context=""):
    """Log current memory usage for debugging."""
    try:
        usage = get_memory_usage_mb()
        available = get_available_memory_mb()
        logger.debug(f"Memory usage {context}: {usage:.0f}MB / {available:.0f}MB available")
    except:
        pass

def should_reduce_batch_size(current_batch, memory_threshold_mb=6000):
    """
    Check if we should reduce batch size due to memory pressure.
    
    Args:
        current_batch: Current batch size
        memory_threshold_mb: Memory threshold in MB
    
    Returns:
        True if batch size should be reduced
    """
    try:
        available = get_available_memory_mb()
        return available < memory_threshold_mb
    except:
        return False

