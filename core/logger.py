# [FILE: core/logger.py]
"""
Centralized logging infrastructure for CyneDirector.
Replaces scattered debug logging with proper Python logging.
"""
import logging
import os
from pathlib import Path
from datetime import datetime
from config import LOG_DIR, APP_NAME, VERSION

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Log file paths
LOG_FILE = LOG_DIR / f"{APP_NAME.lower()}.log"
ERROR_LOG_FILE = LOG_DIR / f"{APP_NAME.lower()}_errors.log"

# Configure root logger
_logger = None

def get_logger(name=None):
    """
    Get or create a logger instance.
    
    Args:
        name: Logger name (typically __name__). If None, returns root logger.
    
    Returns:
        logging.Logger instance
    """
    global _logger
    
    if _logger is None:
        # Create root logger
        _logger = logging.getLogger(APP_NAME)
        _logger.setLevel(logging.DEBUG)
        
        # Prevent duplicate handlers if called multiple times
        if _logger.handlers:
            return _logger.getChild(name) if name else _logger
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # File handler for all logs
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        _logger.addHandler(file_handler)
        
        # File handler for errors only
        error_handler = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        _logger.addHandler(error_handler)
        
        # Console handler (INFO and above)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        _logger.addHandler(console_handler)
        
        # Log startup
        _logger.info(f"{APP_NAME} v{VERSION} - Logging initialized")
        _logger.info(f"Log files: {LOG_FILE}, {ERROR_LOG_FILE}")
    
    if name:
        return _logger.getChild(name)
    return _logger

def set_log_level(level):
    """
    Set the logging level for console output.
    
    Args:
        level: One of 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    """
    logger = get_logger()
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    
    if isinstance(level, str):
        level = level_map.get(level.upper(), logging.INFO)
    
    # Update console handler level
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(level)
            break

# Initialize logger on import
get_logger()





