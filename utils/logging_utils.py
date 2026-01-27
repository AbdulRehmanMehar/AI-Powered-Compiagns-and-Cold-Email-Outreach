"""
Logging configuration for the cold email system.
Provides consistent logging across all modules.
"""
import logging
import sys
from functools import wraps
import time
from typing import Callable, Any

# Configure root logger
def setup_logging(level: str = "INFO", log_file: str = None):
    """
    Setup logging for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path to write logs
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Format: timestamp - module - level - message
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module."""
    return logging.getLogger(name)


# =============================================================================
# RETRY DECORATOR
# =============================================================================

def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable = None
):
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback function(attempt, exception, delay)
    
    Usage:
        @retry_with_backoff(max_retries=3, exceptions=(ConnectionError, TimeoutError))
        def api_call():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        # Final attempt failed
                        break
                    
                    # Log retry
                    if on_retry:
                        on_retry(attempt + 1, e, delay)
                    
                    # Wait before retry
                    time.sleep(delay)
                    delay *= backoff_factor
            
            # All retries exhausted
            raise last_exception
        
        return wrapper
    return decorator


def retry_on_rate_limit(max_retries: int = 3, initial_delay: float = 5.0):
    """
    Specialized retry decorator for rate limit errors.
    
    Catches rate limit errors and retries with longer delays.
    """
    def is_rate_limit_error(e: Exception) -> bool:
        error_str = str(e).lower()
        return 'rate' in error_str and 'limit' in error_str
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            logger = get_logger(func.__module__)
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if not is_rate_limit_error(e):
                        raise  # Not a rate limit error, don't retry
                    
                    if attempt == max_retries:
                        raise  # Final attempt
                    
                    logger.warning(
                        f"Rate limit hit, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    delay *= 2  # Double delay for rate limits
            
            raise Exception("Max retries exceeded")
        
        return wrapper
    return decorator


# =============================================================================
# EMOJI-FREE LOGGING HELPERS (for production logs)
# =============================================================================

class ProductionLogger:
    """
    Logger that can output either emoji-rich (dev) or clean (production) logs.
    """
    
    def __init__(self, name: str, use_emoji: bool = True):
        self.logger = logging.getLogger(name)
        self.use_emoji = use_emoji
    
    def info(self, msg: str, emoji: str = ""):
        if self.use_emoji and emoji:
            self.logger.info(f"{emoji} {msg}")
        else:
            self.logger.info(msg)
    
    def warning(self, msg: str, emoji: str = "⚠️"):
        if self.use_emoji and emoji:
            self.logger.warning(f"{emoji} {msg}")
        else:
            self.logger.warning(msg)
    
    def error(self, msg: str, emoji: str = "❌"):
        if self.use_emoji and emoji:
            self.logger.error(f"{emoji} {msg}")
        else:
            self.logger.error(msg)
    
    def debug(self, msg: str):
        self.logger.debug(msg)
    
    def success(self, msg: str):
        """Log a success message."""
        if self.use_emoji:
            self.logger.info(f"✅ {msg}")
        else:
            self.logger.info(f"SUCCESS: {msg}")
