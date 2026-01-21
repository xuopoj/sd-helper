"""Huawei Cloud IAM authentication module."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import yaml


def get_global_config_dir() -> Path:
    """Get global config directory following XDG Base Directory specification."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        base = Path(xdg_config)
    else:
        base = Path.home() / ".config"

    config_dir = base / "sd-helper"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_local_config_file() -> Optional[Path]:
    """Get local config file path if it exists."""
    local_config = Path.cwd() / ".sd-helper.yaml"
    if local_config.exists():
        return local_config
    return None


def get_token_cache_file(profile: str) -> Path:
    """Get path to token cache file for a profile."""
    return get_global_config_dir() / f"token_cache_{profile}.json"


def get_global_config_file() -> Path:
    """Get path to global config file."""
    return get_global_config_dir() / "config.yaml"


def load_raw_config() -> dict:
    """Load raw config file content."""
    config_path = get_global_config_file()
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
            return data if data else {"default_profile": "default", "profiles": {}}
    return {"default_profile": "default", "profiles": {}}


def save_raw_config(raw_config: dict) -> Path:
    """Save raw config to file."""
    config_path = get_global_config_file()
    with open(config_path, "w") as f:
        yaml.safe_dump(raw_config, f, default_flow_style=False, sort_keys=False)
    return config_path


def get_default_profile() -> str:
    """Get the default profile name from config."""
    raw = load_raw_config()
    return raw.get("default_profile", "default")


def set_default_profile(profile: str) -> Path:
    """Set the default profile in config."""
    raw = load_raw_config()
    raw["default_profile"] = profile
    return save_raw_config(raw)


def list_profiles() -> list[str]:
    """List all available profiles."""
    raw = load_raw_config()
    return list(raw.get("profiles", {}).keys())


def load_global_config(profile: str = None) -> dict:
    """Load global configuration for a specific profile."""
    if profile is None:
        profile = get_default_profile()
    raw = load_raw_config()
    return raw.get("profiles", {}).get(profile, {})


def load_local_config(profile: str = None) -> dict:
    """Load local configuration from current directory."""
    local_path = get_local_config_file()
    if not local_path:
        return {}

    with open(local_path) as f:
        data = yaml.safe_load(f)
        if not data:
            return {}

    # Handle profiles structure (same as global config)
    if "profiles" in data:
        if profile is None:
            profile = data.get("default_profile", get_default_profile())
        return data.get("profiles", {}).get(profile, {})

    # Flat structure (legacy support)
    return data


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts. Override values take precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(profile: str = None) -> dict:
    """Load merged configuration (local overrides global profile)."""
    if profile is None:
        profile = get_default_profile()
    global_config = load_global_config(profile)
    local_config = load_local_config(profile)

    # Deep merge - local config overrides global config
    return _deep_merge(global_config, local_config)


def save_global_config(config: dict, profile: str = None) -> Path:
    """Save configuration to global config file for a profile."""
    if profile is None:
        profile = get_default_profile()
    raw = load_raw_config()
    if "profiles" not in raw:
        raw["profiles"] = {}
    raw["profiles"][profile] = config
    return save_raw_config(raw)


def save_local_config(config: dict) -> Path:
    """Save configuration to local .sd-helper.yaml."""
    config_path = Path.cwd() / ".sd-helper.yaml"
    with open(config_path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
    return config_path


def save_config(config: dict, profile: str = None, local: bool = False) -> Path:
    """
    Save configuration to config file.

    Args:
        config: Configuration dict to save
        profile: Profile name (ignored if local=True)
        local: If True, save to local .sd-helper.yaml, otherwise global config

    Returns:
        Path to the saved config file
    """
    if local:
        return save_local_config(config)
    return save_global_config(config, profile)


def load_cached_token(profile: str = None) -> Optional[dict]:
    """Load cached token if valid."""
    if profile is None:
        profile = get_default_profile()
    cache_file = get_token_cache_file(profile)
    if not cache_file.exists():
        return None

    with open(cache_file) as f:
        cache = json.load(f)

    expires_at = datetime.fromisoformat(cache.get("expires_at", ""))
    # Make comparison timezone-aware if expires_at has timezone info
    now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
    if now < expires_at - timedelta(minutes=5):
        return cache

    return None


def save_token_cache(
    token: str,
    expires_at: datetime,
    project_id: str,
    iam_url: str,
    profile: str = None,
) -> None:
    """Save token to cache file."""
    if profile is None:
        profile = get_default_profile()
    cache = {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "project_id": project_id,
        "iam_url": iam_url,
        "cached_at": datetime.now().isoformat(),
    }
    with open(get_token_cache_file(profile), "w") as f:
        json.dump(cache, f, indent=2)


def get_iam_endpoint(region: str = None, iam_url: str = None) -> str:
    """
    Get IAM endpoint URL.

    Args:
        region: Huawei Cloud region (for public cloud)
        iam_url: Custom IAM URL (for private cloud, overrides region)

    Returns:
        IAM endpoint URL
    """
    if iam_url:
        return iam_url.rstrip("/")
    if region:
        return f"https://iam.{region}.myhuaweicloud.com"
    return "https://iam.myhuaweicloud.com"


def fetch_token(
    username: str,
    password: str,
    domain_name: str,
    project_name: str,
    region: str = None,
    iam_url: str = None,
    use_cache: bool = True,
    profile: str = None,
) -> dict:
    """
    Fetch IAM token from Huawei Cloud.

    Args:
        username: IAM username
        password: IAM password
        domain_name: Account domain name
        project_name: Project name
        region: Huawei Cloud region (for public cloud)
        iam_url: Custom IAM URL (for private cloud, overrides region)
        use_cache: Whether to use cached token if available
        profile: Profile name for caching

    Returns:
        dict with token, project_id, and expires_at
    """
    if profile is None:
        profile = get_default_profile()
    endpoint = get_iam_endpoint(region=region, iam_url=iam_url)

    if use_cache:
        cached = load_cached_token(profile)
        if cached and cached.get("iam_url") == endpoint:
            return {
                "token": cached["token"],
                "project_id": cached["project_id"],
                "expires_at": cached["expires_at"],
                "from_cache": True,
            }

    url = f"{endpoint}/v3/auth/tokens"

    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": username,
                        "password": password,
                        "domain": {"name": domain_name},
                    }
                },
            },
            "scope": {
                "project": {"name": project_name}
            },
        }
    }

    with httpx.Client(timeout=30.0, verify=False) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

        token = response.headers.get("X-Subject-Token")
        body = response.json()

        expires_at_str = body["token"]["expires_at"]
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        project_id = body["token"]["project"]["id"]

        save_token_cache(token, expires_at, project_id, endpoint, profile)

        return {
            "token": token,
            "project_id": project_id,
            "expires_at": expires_at_str,
            "from_cache": False,
        }


def configure_credentials(
    username: Optional[str] = None,
    password: Optional[str] = None,
    domain_name: Optional[str] = None,
    project_name: Optional[str] = None,
    region: Optional[str] = None,
    iam_url: Optional[str] = None,
    ak: Optional[str] = None,
    sk: Optional[str] = None,
    project_id: Optional[str] = None,
    profile: str = None,
    local: bool = False,
) -> Path:
    """
    Save credentials to config file.

    Supports both password and AK/SK authentication methods.
    Supports both public cloud (region) and private cloud (iam_url).

    Args:
        profile: Profile name to save credentials under
        local: If True, save to local .sd-helper.yaml in current directory

    Returns:
        Path to the saved config file
    """
    if profile is None:
        profile = get_default_profile()
    if local:
        config = load_local_config()
    else:
        config = load_global_config(profile)

    if username:
        config["username"] = username
    if password:
        config["password"] = password
    if domain_name:
        config["domain_name"] = domain_name
    if project_name:
        config["project_name"] = project_name
    if region:
        config["region"] = region
    if iam_url:
        config["iam_url"] = iam_url
    if ak:
        config["ak"] = ak
    if sk:
        config["sk"] = sk
    if project_id:
        config["project_id"] = project_id

    return save_config(config, profile=profile, local=local)


def get_token_from_config(profile: str = None, use_cache: bool = True) -> dict:
    """
    Fetch token using saved configuration.

    Local config (.sd-helper.yaml) overrides global config.

    Args:
        profile: Profile name to use
        use_cache: Whether to use cached token

    Returns:
        dict with token info

    Raises:
        ValueError: If required credentials are not configured
    """
    if profile is None:
        profile = get_default_profile()
    config = load_config(profile)

    required = ["username", "password", "domain_name", "project_name"]
    missing = [k for k in required if k not in config]

    if missing:
        raise ValueError(
            f"Missing required config: {', '.join(missing)}. "
            f"Run 'sd-helper iam configure --profile {profile}' first."
        )

    return fetch_token(
        username=config["username"],
        password=config["password"],
        domain_name=config["domain_name"],
        project_name=config["project_name"],
        region=config.get("region"),
        iam_url=config.get("iam_url"),
        use_cache=use_cache,
        profile=profile,
    )


def clear_token_cache(profile: str = None) -> bool:
    """
    Clear cached token.

    Args:
        profile: Specific profile to clear, or None to clear all

    Returns:
        True if any cache was cleared
    """
    if profile:
        cache_file = get_token_cache_file(profile)
        if cache_file.exists():
            cache_file.unlink()
            return True
        return False

    # Clear all profile caches
    cleared = False
    config_dir = get_global_config_dir()
    for cache_file in config_dir.glob("token_cache_*.json"):
        cache_file.unlink()
        cleared = True
    return cleared


def debug_token_fetch(
    username: str,
    password: str,
    domain_name: str,
    project_name: str,
    region: str = None,
    iam_url: str = None,
    mask_sensitive: bool = True,
) -> "DataCollector":
    """
    Debug token fetching with full request/response logging.

    Use this when connecting to customer networks to diagnose auth issues.
    All HTTP requests and responses are logged for offline analysis.

    Args:
        username: IAM username
        password: IAM password
        domain_name: Account domain name
        project_name: Project name
        region: Huawei Cloud region (for public cloud)
        iam_url: Custom IAM URL (for private cloud)
        mask_sensitive: Whether to mask sensitive data in logs

    Returns:
        DataCollector with all collected debug data
    """
    from .data import DataCollector

    collector = DataCollector(mask_sensitive=mask_sensitive)
    collector.add_note(f"Starting IAM token debug for domain={domain_name}, project={project_name}")

    endpoint = get_iam_endpoint(region=region, iam_url=iam_url)
    url = f"{endpoint}/v3/auth/tokens"

    collector.add("config", {
        "endpoint": endpoint,
        "region": region,
        "iam_url": iam_url,
        "domain_name": domain_name,
        "project_name": project_name,
    })

    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": username,
                        "password": password,
                        "domain": {"name": domain_name},
                    }
                },
            },
            "scope": {
                "project": {"name": project_name}
            },
        }
    }

    result = {"success": False}

    try:
        response = collector.client.post(url, json=payload, timeout=30.0)

        result["status_code"] = response.status_code
        result["success"] = response.status_code == 201

        if result["success"]:
            token = response.headers.get("X-Subject-Token")
            body = response.json()
            result["token_prefix"] = token[:20] + "..." if token else None
            result["expires_at"] = body.get("token", {}).get("expires_at")
            result["project_id"] = body.get("token", {}).get("project", {}).get("id")
            collector.add_note("Token fetch successful")
        else:
            result["error"] = response.text
            collector.add_note(f"Token fetch failed: HTTP {response.status_code}")

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"
        collector.add_note(f"Token fetch exception: {result['error']}")

    collector.add("result", result)
    return collector
