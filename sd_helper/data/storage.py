"""Local storage for collected data."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml


def get_data_dir(base_dir: Optional[Path] = None) -> Path:
    """Get or create data directory for collected data."""
    if base_dir:
        data_dir = base_dir / ".sd-helper-data"
    else:
        data_dir = Path.cwd() / ".sd-helper-data"

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def generate_collection_name(prefix: str = "collection") -> str:
    """Generate a unique collection name with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}"


def save_collection(
    data: dict,
    name: Optional[str] = None,
    base_dir: Optional[Path] = None,
    format: str = "yaml",
) -> Path:
    """
    Save collected data to a file.

    Args:
        data: Data to save
        name: Collection name (auto-generated if not provided)
        base_dir: Base directory for data storage
        format: Output format ('yaml' or 'json')

    Returns:
        Path to saved file
    """
    data_dir = get_data_dir(base_dir)

    if name is None:
        name = generate_collection_name()

    ext = "yaml" if format == "yaml" else "json"
    file_path = data_dir / f"{name}.{ext}"

    # Add metadata
    data_with_meta = {
        "_metadata": {
            "collected_at": datetime.now().isoformat(),
            "name": name,
        },
        **data,
    }

    with open(file_path, "w") as f:
        if format == "yaml":
            yaml.safe_dump(data_with_meta, f, default_flow_style=False, sort_keys=False)
        else:
            json.dump(data_with_meta, f, indent=2, default=str)

    return file_path


def load_collection(name: str, base_dir: Optional[Path] = None) -> dict:
    """
    Load a saved collection.

    Args:
        name: Collection name (with or without extension)
        base_dir: Base directory for data storage

    Returns:
        Loaded data dict
    """
    data_dir = get_data_dir(base_dir)

    # Try with provided name first, then try adding extensions
    candidates = [
        data_dir / name,
        data_dir / f"{name}.yaml",
        data_dir / f"{name}.json",
    ]

    for path in candidates:
        if path.exists():
            with open(path) as f:
                if path.suffix == ".json":
                    return json.load(f)
                else:
                    return yaml.safe_load(f)

    raise FileNotFoundError(f"Collection not found: {name}")


def list_collections(base_dir: Optional[Path] = None) -> list[dict]:
    """
    List all saved collections.

    Args:
        base_dir: Base directory for data storage

    Returns:
        List of collection info dicts
    """
    data_dir = get_data_dir(base_dir)

    collections = []
    for path in sorted(data_dir.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.suffix in (".yaml", ".json"):
            stat = path.stat()
            collections.append({
                "name": path.stem,
                "file": path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    return collections


def delete_collection(name: str, base_dir: Optional[Path] = None) -> bool:
    """
    Delete a saved collection.

    Args:
        name: Collection name
        base_dir: Base directory for data storage

    Returns:
        True if deleted, False if not found
    """
    data_dir = get_data_dir(base_dir)

    candidates = [
        data_dir / name,
        data_dir / f"{name}.yaml",
        data_dir / f"{name}.json",
    ]

    for path in candidates:
        if path.exists():
            path.unlink()
            return True

    return False
