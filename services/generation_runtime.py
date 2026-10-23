"""Shared model client configuration for API and worker processes."""

from agent import LLMClient


def generation_client(*, timeout: float | None = None) -> LLMClient:
    """Interactive generation should fail fast instead of retrying a slow upstream call."""
    return LLMClient(max_retries=0, timeout=timeout)
