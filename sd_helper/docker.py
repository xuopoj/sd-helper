"""MAS asset management: image upload to SWR."""

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SIG_SUFFIXES = (".asc", ".cms", ".p7s", ".crl", ".sha256")
PROGRESS_FILE = ".progress.json"


def parse_manifest(manifest_file: str) -> dict:
    sections = {}
    section = "default"
    with open(manifest_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                section = line.lstrip("#").strip()
            else:
                sections.setdefault(section, []).append(line)
    return sections


def get_image_patterns(manifest_file: str) -> list:
    sections = parse_manifest(manifest_file)
    for key, patterns in sections.items():
        if "镜像" in key:
            return patterns
    log.warning("No 镜像 section found in manifest, using all entries")
    return [p for patterns in sections.values() for p in patterns]


def pattern_to_glob(pattern: str) -> str:
    return re.sub(r'x{3,}', '*', pattern)


def find_matching_file(directory: str, pattern: str) -> Optional[str]:
    glob_pat = pattern_to_glob(pattern)
    matches = [
        m for m in Path(directory).glob(glob_pat)
        if m.is_file() and not any(m.name.endswith(s) for s in SIG_SUFFIXES)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        log.warning("Multiple matches for '%s': %s — using first", pattern, [m.name for m in matches])
    return str(matches[0])


def load_progress(progress_file: str = PROGRESS_FILE) -> dict:
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            return json.load(f)
    return {}


def save_progress(progress: dict, progress_file: str = PROGRESS_FILE):
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)


def run_cmd(cmd: list, dry_run: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
    log.info("$ %s", " ".join(cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, stdout="[dry-run]", stderr="")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        err = result.stderr.strip() if capture else "(see above)"
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}\n{err}")
    return result


def docker_load(tarball: str, dry_run: bool = False) -> list:
    result = run_cmd(["docker", "load", "-i", tarball], dry_run=dry_run, capture=True)
    if dry_run:
        return [f"dry-run/{Path(tarball).stem}:latest"]
    images = []
    for line in result.stdout.splitlines():
        m = re.match(r"Loaded image(?:\s+ID)?:\s*(.+)", line, re.IGNORECASE)
        if m:
            images.append(m.group(1).strip())
    if not images:
        raise RuntimeError(f"Could not parse loaded image from output:\n{result.stdout}")
    return images


def build_target_ref(swr_endpoint: str, org: str, loaded_ref: str) -> str:
    parts = loaded_ref.split("/")
    if len(parts) >= 2 and ("." in parts[0] or ":" in parts[0]):
        name_tag = "/".join(parts[2:]) if len(parts) > 2 else parts[1]
    else:
        name_tag = parts[-1]
    return f"{swr_endpoint}/{org}/{name_tag}"


def process_image(pattern: str, swr_endpoint: str, org: str, directory: str,
                  progress: dict, dry_run: bool, cleanup: bool = False,
                  progress_file: str = PROGRESS_FILE):
    tarball = find_matching_file(directory, pattern)
    if not tarball:
        log.error("[MISSING] No file found for: %s", pattern)
        progress[pattern] = "missing"
        save_progress(progress, progress_file)
        return

    try:
        loaded_images = docker_load(tarball, dry_run=dry_run)
        log.info("Loaded: %s", loaded_images)

        for loaded_ref in loaded_images:
            if progress.get(loaded_ref) == "done":
                log.info("[SKIP] %s (already done)", loaded_ref)
                continue

            target = build_target_ref(swr_endpoint, org, loaded_ref)
            run_cmd(["docker", "tag", loaded_ref, target], dry_run=dry_run)
            run_cmd(["docker", "push", target], dry_run=dry_run)
            log.info("[PUSHED] %s", target)

            if cleanup:
                for img in (loaded_ref, target):
                    try:
                        run_cmd(["docker", "rmi", img], dry_run=dry_run)
                    except RuntimeError as e:
                        log.warning("Failed to remove image %s: %s", img, e)

            progress[loaded_ref] = "done"
            save_progress(progress, progress_file)
            log.info("[DONE] %s", loaded_ref)

    except RuntimeError as e:
        log.error("[FAILED] %s: %s", pattern, e)
        progress[pattern] = f"failed: {e}"
        save_progress(progress, progress_file)


def validate_manifest(manifest_file: str, directory: str) -> list:
    sections = parse_manifest(manifest_file)
    found, missing = [], []
    for section, patterns in sections.items():
        for pattern in patterns:
            match = find_matching_file(directory, pattern)
            if match:
                found.append((section, pattern, Path(match).name))
            else:
                missing.append((section, pattern))
    return found, missing
