"""Message handlers for auth request processing."""

from auth_processor_worker.handlers.processor import ProcessingResult, process_auth_request

__all__ = ["process_auth_request", "ProcessingResult"]
