"""Data collector for offline debugging."""

import platform
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .http_logger import HTTPLogger, LoggingClient
from .storage import save_collection


class DataCollector:
    """
    Collect data for offline debugging.

    Usage:
        collector = DataCollector()

        # Use the logging HTTP client
        response = collector.client.post(url, json=payload)

        # Add custom data
        collector.add("my_data", {"key": "value"})

        # Save everything
        collector.save("debug_session")
    """

    def __init__(self, mask_sensitive: bool = True):
        self.logger = HTTPLogger(mask_sensitive=mask_sensitive)
        self.client = LoggingClient(logger=self.logger)
        self.custom_data: dict[str, Any] = {}
        self.notes: list[str] = []
        self.started_at = datetime.now()

    def add(self, key: str, data: Any) -> None:
        """Add custom data to the collection."""
        self.custom_data[key] = data

    def add_note(self, note: str) -> None:
        """Add a note to the collection."""
        self.notes.append({
            "timestamp": datetime.now().isoformat(),
            "note": note,
        })

    def get_system_info(self) -> dict:
        """Collect system and network information."""
        info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
        }

        # Try to get IP addresses
        try:
            info["fqdn"] = socket.getfqdn()
        except Exception:
            pass

        try:
            # Get all IPs
            hostname = socket.gethostname()
            info["local_ips"] = socket.gethostbyname_ex(hostname)[2]
        except Exception:
            info["local_ips"] = []

        return info

    def test_connectivity(self, urls: Optional[list[str]] = None) -> dict:
        """
        Test connectivity to various endpoints.

        Args:
            urls: List of URLs to test, or None for defaults
        """
        if urls is None:
            urls = [
                "https://iam.myhuaweicloud.com",
                "https://iam.cn-north-4.myhuaweicloud.com",
            ]

        results = {}
        for url in urls:
            try:
                response = self.client.get(url, timeout=10.0)
                results[url] = {
                    "status": "ok",
                    "status_code": response.status_code,
                }
            except Exception as e:
                results[url] = {
                    "status": "error",
                    "error": str(e),
                }

        return results

    def to_dict(self) -> dict:
        """Export all collected data as a dictionary."""
        return {
            "session": {
                "started_at": self.started_at.isoformat(),
                "ended_at": datetime.now().isoformat(),
            },
            "system_info": self.get_system_info(),
            "notes": self.notes,
            "custom_data": self.custom_data,
            **self.logger.to_dict(),
        }

    def save(
        self,
        name: Optional[str] = None,
        base_dir: Optional[Path] = None,
        format: str = "yaml",
    ) -> Path:
        """
        Save collected data to a file.

        Args:
            name: Collection name
            base_dir: Directory to save to
            format: Output format ('yaml' or 'json')

        Returns:
            Path to saved file
        """
        return save_collection(
            data=self.to_dict(),
            name=name,
            base_dir=base_dir,
            format=format,
        )

    def clear(self) -> None:
        """Clear all collected data."""
        self.logger.clear()
        self.custom_data.clear()
        self.notes.clear()
        self.started_at = datetime.now()
