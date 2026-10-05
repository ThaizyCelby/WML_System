"""Logging utilities for correlation ID handling."""
import contextvars
import logging

# Global context variable for correlation ID
correlation_id_var = contextvars.ContextVar('correlation_id', default='')


class CorrelationIdFilter(logging.Filter):
    """Logging filter that adds correlation_id to log records."""

    def filter(self, record):
        record.correlation_id = correlation_id_var.get()
        return True
