"""Shared model client configuration for API and worker processes."""

from agent import LLMClient
from services.content_review import reviewer_model_settings


def generation_client(*, timeout: float | None = None) -> LLMClient:
    """Interactive generation should fail fast instead of retrying a slow upstream call."""
    return LLMClient(max_retries=0, timeout=timeout)


def reviewer_client(*, timeout: float | None = None) -> LLMClient:
    """Use an optional cheaper/dedicated reviewer model, otherwise shared config."""
    model, api_key, base_url = reviewer_model_settings()
    if not any((model, api_key, base_url)):
        return generation_client(timeout=timeout)
    if not all((model, api_key, base_url)):
        raise ValueError("REVIEW_MODEL、REVIEW_API_KEY 和 REVIEW_BASE_URL 必须同时配置")
    return LLMClient(model=model, api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout)
