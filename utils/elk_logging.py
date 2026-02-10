"""
Enhanced Logging Configuration for ELK Monitoring

This module provides structured logging with additional context
for better monitoring in ELK stack (Elasticsearch, Logstash, Kibana).
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict
import traceback


class StructuredLogger(logging.Logger):
    """Logger that outputs structured JSON for ELK"""
    
    def _log_structured(self, level: int, msg: str, extra: Dict = None, **kwargs):
        """Log with structured data"""
        if extra is None:
            extra = {}
        
        # Add standard fields
        extra.update({
            'timestamp': datetime.utcnow().isoformat(),
            'level': logging.getLevelName(level),
            'logger': self.name,
        })
        
        self._log(level, msg, (), extra=extra, **kwargs)


class ELKFormatter(logging.Formatter):
    """JSON formatter for ELK stack"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        
        # Base log structure
        log_data = {
            '@timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add custom fields from extra
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'message', 'pathname', 'process', 'processName', 'relativeCreated',
                          'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info']:
                log_data[key] = value
        
        return json.dumps(log_data)


def setup_elk_logging(
    level: str = "INFO",
    log_file: str = None,
    structured: bool = True
):
    """
    Setup logging optimized for ELK stack monitoring
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for local logs
        structured: If True, output JSON format for ELK
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Use structured formatter for Docker/ELK
    if structured:
        formatter = ELKFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Console handler (stdout for Docker logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(console_handler)
    
    # File handler (optional, for local debugging)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    
    return root_logger


def log_campaign_event(
    event_type: str,
    campaign_id: str = None,
    campaign_name: str = None,
    **kwargs
):
    """
    Log campaign-specific events for monitoring
    
    Args:
        event_type: Type of event (campaign_started, email_sent, etc.)
        campaign_id: Campaign ID
        campaign_name: Campaign name
        **kwargs: Additional context
    """
    logger = logging.getLogger('campaign_events')
    logger.info(
        f"Campaign event: {event_type}",
        extra={
            'event_type': event_type,
            'campaign_id': campaign_id,
            'campaign_name': campaign_name,
            **kwargs
        }
    )


def log_email_event(
    event_type: str,
    to_email: str,
    from_email: str = None,
    campaign_id: str = None,
    subject: str = None,
    **kwargs
):
    """
    Log email-specific events for monitoring
    
    Args:
        event_type: Type of event (sent, failed, bounced, replied)
        to_email: Recipient email
        from_email: Sender email account
        campaign_id: Associated campaign
        subject: Email subject
        **kwargs: Additional context
    """
    logger = logging.getLogger('email_events')
    logger.info(
        f"Email event: {event_type}",
        extra={
            'event_type': event_type,
            'to_email': to_email,
            'from_email': from_email,
            'campaign_id': campaign_id,
            'subject': subject,
            **kwargs
        }
    )


def log_performance_metric(
    metric_name: str,
    value: float,
    unit: str = None,
    **kwargs
):
    """
    Log performance metrics for monitoring dashboards
    
    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: Unit of measurement
        **kwargs: Additional tags/dimensions
    """
    logger = logging.getLogger('performance')
    logger.info(
        f"Metric: {metric_name}",
        extra={
            'metric_name': metric_name,
            'metric_value': value,
            'metric_unit': unit,
            **kwargs
        }
    )


# Context manager for timing operations
class LogTimer:
    """Context manager to log operation duration"""
    
    def __init__(self, operation: str, **context):
        self.operation = operation
        self.context = context
        self.start_time = None
        self.logger = logging.getLogger('performance')
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(
            f"Starting: {self.operation}",
            extra={'operation': self.operation, **self.context}
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type:
            self.logger.error(
                f"Failed: {self.operation} ({duration:.2f}s)",
                extra={
                    'operation': self.operation,
                    'duration_seconds': duration,
                    'success': False,
                    **self.context
                },
                exc_info=(exc_type, exc_val, exc_tb)
            )
        else:
            log_performance_metric(
                f"{self.operation}_duration",
                duration,
                unit='seconds',
                operation=self.operation,
                **self.context
            )
