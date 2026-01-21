"""Execute request templates and collect results."""

from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from .collector import DataCollector
from .request_template import load_template, process_template_value


class TemplateRunner:
    """Execute API requests from a template file."""

    def __init__(self, template_path: Path, mask_sensitive: bool = True):
        self.template = load_template(template_path)
        self.collector = DataCollector(mask_sensitive=mask_sensitive)
        self.variables = self.template.get("variables", {})
        self.results = {}

        # Add auth to variables for substitution
        if "auth" in self.template:
            self.variables["auth"] = self.template["auth"]

    def _get_headers(self, request_headers: dict) -> dict:
        """Build headers for a request."""
        headers = dict(self.template.get("default_headers", {}))
        headers.update(request_headers)

        # Add auth header if configured
        auth = self.template.get("auth", {})
        auth_type = auth.get("type", "none")

        if auth_type == "token" and auth.get("token"):
            headers["X-Auth-Token"] = auth["token"]
        elif auth_type == "basic":
            import base64
            credentials = f"{auth.get('username', '')}:{auth.get('password', '')}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        # Process variable substitution in headers
        headers = process_template_value(headers, self.variables)

        return headers

    def _build_url(self, path: str) -> str:
        """Build full URL from base_url and path."""
        base_url = self.template.get("base_url", "")
        # Process variables in path
        path = process_template_value(path, self.variables)

        if base_url:
            return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
        return path

    def run_request(self, request: dict) -> dict:
        """Execute a single request from the template."""
        name = request.get("name", "unnamed")
        method = request.get("method", "GET").upper()
        path = request.get("path", "/")
        headers = self._get_headers(request.get("headers", {}))
        body = request.get("body")

        # Process variable substitution in body
        if body:
            body = process_template_value(body, self.variables)

        url = self._build_url(path)

        self.collector.add_note(f"Executing request: {name} ({method} {path})")

        result = {
            "name": name,
            "description": request.get("description", ""),
            "method": method,
            "url": url,
            "success": False,
        }

        try:
            if method == "GET":
                response = self.collector.client.get(url, headers=headers)
            elif method == "POST":
                response = self.collector.client.post(url, headers=headers, json=body)
            elif method == "PUT":
                response = self.collector.client.put(url, headers=headers, json=body)
            elif method == "DELETE":
                response = self.collector.client.delete(url, headers=headers)
            else:
                result["error"] = f"Unsupported method: {method}"
                return result

            result["status_code"] = response.status_code
            result["success"] = 200 <= response.status_code < 300

            # Try to extract useful info from response
            try:
                result["response_body"] = response.json()
            except Exception:
                result["response_body"] = response.text[:1000] if response.text else None

            # Extract token from IAM responses
            if "X-Subject-Token" in response.headers:
                token = response.headers["X-Subject-Token"]
                result["token_received"] = True
                # Update variables for subsequent requests
                self.variables.setdefault("auth", {})["token"] = token

        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e)}"
            result["success"] = False

        self.results[name] = result
        return result

    def run_all(self, skip_on_error: bool = False) -> dict:
        """Execute all requests in the template."""
        requests = self.template.get("requests", [])

        self.collector.add_note(f"Starting template: {self.template.get('name', 'unnamed')}")
        self.collector.add("template_info", {
            "name": self.template.get("name"),
            "description": self.template.get("description"),
            "base_url": self.template.get("base_url"),
            "total_requests": len(requests),
        })

        for request in requests:
            # Skip if marked
            if request.get("skip", False):
                self.collector.add_note(f"Skipping request: {request.get('name')} (marked skip)")
                continue

            result = self.run_request(request)

            if not result["success"] and skip_on_error:
                self.collector.add_note(f"Stopping due to error in: {request.get('name')}")
                break

        return self.get_summary()

    def get_summary(self) -> dict:
        """Get summary of all executed requests."""
        total = len(self.results)
        success = sum(1 for r in self.results.values() if r.get("success"))
        failed = total - success

        return {
            "total_requests": total,
            "successful": success,
            "failed": failed,
            "results": self.results,
        }

    def save(self, name: Optional[str] = None, base_dir: Optional[Path] = None) -> Path:
        """Save collected data."""
        # Add summary to collector
        self.collector.add("execution_summary", self.get_summary())

        # Use template name if no name provided
        if name is None:
            name = self.template.get("name", "collection")

        return self.collector.save(name=name, base_dir=base_dir)
