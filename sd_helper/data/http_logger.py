"""HTTP request/response logger."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx


@dataclass
class HTTPRecord:
    """A single HTTP request/response record."""

    timestamp: str
    method: str
    url: str
    request_headers: dict
    request_body: Optional[str]
    status_code: Optional[int]
    response_headers: Optional[dict]
    response_body: Optional[str]
    duration_ms: float
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "method": self.method,
            "url": self.url,
            "duration_ms": self.duration_ms,
            "request": {
                "headers": self.request_headers,
                "body": self.request_body,
            },
            "response": {
                "status_code": self.status_code,
                "headers": self.response_headers,
                "body": self.response_body,
            } if self.status_code else None,
            "error": self.error,
        }


@dataclass
class HTTPLogger:
    """Logger for HTTP requests and responses."""

    records: list[HTTPRecord] = field(default_factory=list)
    mask_sensitive: bool = True
    sensitive_headers: set = field(default_factory=lambda: {
        "authorization", "x-auth-token", "x-subject-token",
        "x-security-token", "cookie", "set-cookie",
    })
    sensitive_fields: set = field(default_factory=lambda: {
        "password", "secret", "token", "key", "credential",
    })

    def _mask_headers(self, headers: dict) -> dict:
        """Mask sensitive header values."""
        if not self.mask_sensitive:
            return dict(headers)

        masked = {}
        for key, value in headers.items():
            if key.lower() in self.sensitive_headers:
                masked[key] = "****MASKED****"
            else:
                masked[key] = value
        return masked

    def _mask_body(self, body: Optional[str]) -> Optional[str]:
        """Mask sensitive fields in body."""
        if not body or not self.mask_sensitive:
            return body

        # Simple masking for common patterns
        import re
        for field_name in self.sensitive_fields:
            # Match "field": "value" or "field": value patterns
            body = re.sub(
                rf'("{field_name}":\s*)"[^"]*"',
                rf'\1"****MASKED****"',
                body,
                flags=re.IGNORECASE,
            )
        return body

    def log_request(
        self,
        request: httpx.Request,
        response: Optional[httpx.Response] = None,
        duration_ms: float = 0,
        error: Optional[str] = None,
    ) -> HTTPRecord:
        """Log an HTTP request and optional response."""
        # Get request body
        request_body = None
        if request.content:
            try:
                request_body = request.content.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                request_body = "<binary data>"

        # Get response details
        status_code = None
        response_headers = None
        response_body = None

        if response is not None:
            status_code = response.status_code
            response_headers = self._mask_headers(dict(response.headers))
            try:
                response_body = response.text
            except Exception:
                response_body = "<could not decode>"

        record = HTTPRecord(
            timestamp=datetime.now().isoformat(),
            method=request.method,
            url=str(request.url),
            request_headers=self._mask_headers(dict(request.headers)),
            request_body=self._mask_body(request_body),
            status_code=status_code,
            response_headers=response_headers,
            response_body=self._mask_body(response_body),
            duration_ms=duration_ms,
            error=error,
        )

        self.records.append(record)
        return record

    def to_dict(self) -> dict:
        """Export all records as a dictionary."""
        return {
            "http_logs": [r.to_dict() for r in self.records],
            "total_requests": len(self.records),
            "failed_requests": sum(1 for r in self.records if r.error or (r.status_code and r.status_code >= 400)),
        }

    def clear(self) -> None:
        """Clear all records."""
        self.records.clear()


class LoggingClient:
    """HTTP client wrapper that logs all requests."""

    def __init__(
        self,
        logger: Optional[HTTPLogger] = None,
        timeout: float = 30.0,
        **httpx_kwargs,
    ):
        self.logger = logger or HTTPLogger()
        self.timeout = timeout
        self.httpx_kwargs = httpx_kwargs

    def request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Make an HTTP request and log it."""
        kwargs.setdefault("timeout", self.timeout)

        with httpx.Client(**self.httpx_kwargs, verify=False) as client:
            request = client.build_request(method, url, **kwargs)

            start_time = time.perf_counter()
            error = None
            response = None

            try:
                response = client.send(request)
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)}"
                raise
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                self.logger.log_request(request, response, duration_ms, error)

            return response

    def get(self, url: str, **kwargs) -> httpx.Response:
        """Make a GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        """Make a POST request."""
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> httpx.Response:
        """Make a PUT request."""
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> httpx.Response:
        """Make a DELETE request."""
        return self.request("DELETE", url, **kwargs)
