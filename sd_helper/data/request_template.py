"""Request template for offline data collection."""

from pathlib import Path
from typing import Optional

import yaml

DEFAULT_TEMPLATE = {
    "name": "api_collection",
    "description": "API collection session",
    "base_url": "",
    "default_headers": {
        "Content-Type": "application/json",
    },
    "auth": {
        "type": "token",  # token, basic, or none
        "token": "",      # X-Auth-Token value
        # "username": "",  # for basic auth
        # "password": "",  # for basic auth
    },
    "requests": [
        {
            "name": "get_token",
            "description": "Fetch IAM token",
            "method": "POST",
            "path": "/v3/auth/tokens",
            "headers": {},
            "body": {
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": "YOUR_USERNAME",
                                "password": "YOUR_PASSWORD",
                                "domain": {"name": "YOUR_DOMAIN"},
                            }
                        },
                    },
                    "scope": {
                        "project": {"name": "YOUR_PROJECT"}
                    },
                }
            },
        },
        {
            "name": "list_projects",
            "description": "List available projects",
            "method": "GET",
            "path": "/v3/projects",
            "headers": {},
            "body": None,
        },
    ],
}


IAM_TEMPLATE = {
    "name": "iam_debug",
    "description": "IAM authentication debug collection",
    "base_url": "https://iam.cn-north-4.myhuaweicloud.com",
    "default_headers": {
        "Content-Type": "application/json",
    },
    "auth": {
        "type": "none",
    },
    "requests": [
        {
            "name": "get_token",
            "description": "Fetch IAM token with password auth",
            "method": "POST",
            "path": "/v3/auth/tokens",
            "headers": {},
            "body": {
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": "YOUR_USERNAME",
                                "password": "YOUR_PASSWORD",
                                "domain": {"name": "YOUR_DOMAIN"},
                            }
                        },
                    },
                    "scope": {
                        "project": {"name": "YOUR_PROJECT"}
                    },
                }
            },
        },
        {
            "name": "get_token_info",
            "description": "Get token info (requires valid token in auth section)",
            "method": "GET",
            "path": "/v3/auth/tokens",
            "headers": {
                "X-Subject-Token": "${auth.token}",
            },
            "body": None,
            "skip": True,  # Skip by default, enable after getting token
        },
    ],
}


MODELARTS_TEMPLATE = {
    "name": "modelarts_debug",
    "description": "ModelArts API debug collection",
    "base_url": "https://modelarts.cn-north-4.myhuaweicloud.com",
    "default_headers": {
        "Content-Type": "application/json",
    },
    "auth": {
        "type": "token",
        "token": "YOUR_TOKEN_HERE",
    },
    "variables": {
        "project_id": "YOUR_PROJECT_ID",
    },
    "requests": [
        {
            "name": "list_services",
            "description": "List deployed services",
            "method": "GET",
            "path": "/v1/${project_id}/services",
            "headers": {},
            "body": None,
        },
        {
            "name": "list_models",
            "description": "List models",
            "method": "GET",
            "path": "/v1/${project_id}/models",
            "headers": {},
            "body": None,
        },
    ],
}


TEMPLATES = {
    "default": DEFAULT_TEMPLATE,
    "iam": IAM_TEMPLATE,
    "modelarts": MODELARTS_TEMPLATE,
}


def get_template(name: str = "default") -> dict:
    """Get a request template by name."""
    return TEMPLATES.get(name, DEFAULT_TEMPLATE).copy()


def list_templates() -> list[str]:
    """List available template names."""
    return list(TEMPLATES.keys())


def save_template(template: dict, path: Path) -> Path:
    """Save template to a YAML file."""
    with open(path, "w") as f:
        yaml.safe_dump(template, f, default_flow_style=False, sort_keys=False)
    return path


def load_template(path: Path) -> dict:
    """Load template from a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def substitute_variables(text: str, variables: dict) -> str:
    """Replace ${var} placeholders with values from variables dict."""
    import re

    def replacer(match):
        var_path = match.group(1)
        parts = var_path.split(".")
        value = variables
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return match.group(0)  # Keep original if not found
        return str(value)

    return re.sub(r'\$\{([^}]+)\}', replacer, text)


def process_template_value(value, variables: dict):
    """Recursively process template values, substituting variables."""
    if isinstance(value, str):
        return substitute_variables(value, variables)
    elif isinstance(value, dict):
        return {k: process_template_value(v, variables) for k, v in value.items()}
    elif isinstance(value, list):
        return [process_template_value(item, variables) for item in value]
    return value
