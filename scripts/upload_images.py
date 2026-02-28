#!/usr/bin/env python3
"""
MAS Image Upload Tool
Reads the 镜像 section from the assets manifest, matches files on disk,
then docker load + tag + push each image to SWR.

Usage:
  # Upload all images
  python upload_images.py --config config.yaml --dir /path/to/files

  # Dry run — print commands without executing
  python upload_images.py --config config.yaml --dir /path/to/files --dry-run

  # Validate all manifest files exist on disk, then exit
  python upload_images.py --config config.yaml --dir /path/to/files --validate

  # Reset all progress (re-upload everything)
  python upload_images.py --reset

  # Reset specific images by loaded image name (e.g. to retry a failed push)
  python upload_images.py --reset "name:tag"

  # Run in background (survives SSH disconnect)
  nohup python upload_images.py --config config.yaml --dir /path/to/files > upload.log 2>&1 &
  echo $!                  # note the PID
  tail -f upload.log        # follow live output
  cat .progress.json        # check per-image status

Config (config.yaml):
  assets_file: 资产清单.txt
  swr:
    endpoint: swr.cn-north-4.myhuaweicloud.com
    org: com-huaweicloud-dataengineering
  cleanup_after_push: false   # set true to docker rmi after push

Progress is saved to .progress.json after each image push. Re-running skips
images already marked "done".
"""
import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("upload_images.log"),
    ],
)
log = logging.getLogger(__name__)

PROGRESS_FILE = ".progress.json"
SIG_SUFFIXES = (".asc", ".cms", ".p7s", ".crl", ".sha256")


# --- Manifest parsing ---

def parse_manifest(manifest_file: str) -> dict:
    """
    Parse manifest into sections. Lines starting with # set the current section.
    Returns dict of section_name -> [filename_patterns].
    """
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
    """Return filename patterns from the 镜像 section of the manifest."""
    sections = parse_manifest(manifest_file)
    # Find the images section (key contains 镜像)
    for key, patterns in sections.items():
        if "镜像" in key:
            return patterns
    log.warning("No 镜像 section found in manifest, using all entries")
    return [p for patterns in sections.values() for p in patterns]


# --- File matching ---

def pattern_to_glob(pattern: str) -> str:
    """Replace placeholder sequences (xxx...) with glob wildcard *."""
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


# --- Progress tracking ---

def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# --- Docker operations ---

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


def docker_tag(source: str, target: str, dry_run: bool = False):
    run_cmd(["docker", "tag", source, target], dry_run=dry_run)


def docker_push(image: str, dry_run: bool = False):
    run_cmd(["docker", "push", image], dry_run=dry_run)


def docker_rmi(image: str, dry_run: bool = False):
    try:
        run_cmd(["docker", "rmi", image], dry_run=dry_run)
    except RuntimeError as e:
        log.warning("Failed to remove image %s: %s", image, e)


def build_target_ref(swr_endpoint: str, org: str, loaded_ref: str) -> str:
    """
    Strip any existing registry host from loaded_ref, then prepend swr_endpoint/org.
    e.g. "some.registry/ns/name:tag" -> "swr.cn-north-4.myhuaweicloud.com/myorg/name:tag"
    """
    parts = loaded_ref.split("/")
    if len(parts) >= 2 and ("." in parts[0] or ":" in parts[0]):
        name_tag = "/".join(parts[2:]) if len(parts) > 2 else parts[1]
    else:
        name_tag = parts[-1]
    return f"{swr_endpoint}/{org}/{name_tag}"


# --- Core logic ---

def process_image(pattern: str, cfg: dict, directory: str, progress: dict, dry_run: bool):
    tarball = find_matching_file(directory, pattern)
    if not tarball:
        log.error("[MISSING] No file found for: %s", pattern)
        progress[pattern] = "missing"
        save_progress(progress)
        return

    swr_endpoint = cfg["swr"]["endpoint"]
    org = cfg["swr"]["org"]
    cleanup = cfg.get("cleanup_after_push", False)

    try:
        loaded_images = docker_load(tarball, dry_run=dry_run)
        log.info("Loaded: %s", loaded_images)

        for loaded_ref in loaded_images:
            if progress.get(loaded_ref) == "done":
                log.info("[SKIP] %s (already done)", loaded_ref)
                continue

            target = build_target_ref(swr_endpoint, org, loaded_ref)
            docker_tag(loaded_ref, target, dry_run=dry_run)
            docker_push(target, dry_run=dry_run)
            log.info("[PUSHED] %s", target)
            if cleanup:
                docker_rmi(loaded_ref, dry_run=dry_run)
                docker_rmi(target, dry_run=dry_run)

            progress[loaded_ref] = "done"
            save_progress(progress)
            log.info("[DONE] %s", loaded_ref)

    except RuntimeError as e:
        log.error("[FAILED] %s: %s", pattern, e)
        progress[pattern] = f"failed: {e}"
        save_progress(progress)


def validate(manifest_file: str, directory: str):
    log.info("=== Validating manifest: %s ===", manifest_file)
    sections = parse_manifest(manifest_file)
    found, missing = [], []
    for section, patterns in sections.items():
        for pattern in patterns:
            match = find_matching_file(directory, pattern)
            if match:
                found.append((section, pattern, Path(match).name))
            else:
                missing.append((section, pattern))

    for sec, pat, actual in found:
        log.info("  OK      [%s] %s -> %s", sec, pat, actual)
    for sec, pat in missing:
        log.warning("  MISSING [%s] %s", sec, pat)

    log.info("Result: %d found, %d missing", len(found), len(missing))
    return missing


def main():
    parser = argparse.ArgumentParser(description="Upload MAS images to SWR")
    parser.add_argument("--config", default="config.yaml", help="Config file (default: config.yaml)")
    parser.add_argument("--dir", default=".", help="Directory containing asset files (default: .)")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    parser.add_argument("--validate", action="store_true", help="Validate all manifest assets exist, then exit")
    parser.add_argument("--reset", nargs="*", metavar="NAME",
                        help="Reset progress: all if no args, or specific pattern names")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        log.error("Config file not found: %s", args.config)
        sys.exit(1)

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    manifest_file = cfg.get("assets_file")
    if not manifest_file:
        log.error("'assets_file' not set in config")
        sys.exit(1)
    if not os.path.exists(manifest_file):
        log.error("Assets file not found: %s", manifest_file)
        sys.exit(1)

    if args.reset is not None:
        progress = load_progress()
        if len(args.reset) == 0:
            log.info("Resetting all progress")
            progress = {}
        else:
            for name in args.reset:
                progress.pop(name, None)
                log.info("Reset: %s", name)
        save_progress(progress)
        if not args.validate:
            return

    if args.validate:
        missing = validate(manifest_file, args.dir)
        sys.exit(1 if missing else 0)

    image_patterns = get_image_patterns(manifest_file)
    if not image_patterns:
        log.error("No image patterns found in manifest")
        sys.exit(1)

    progress = load_progress()
    log.info("Starting: %d images, dry_run=%s", len(image_patterns), args.dry_run)
    if args.dry_run:
        log.info("DRY RUN MODE — no commands will be executed")

    for pattern in image_patterns:
        process_image(pattern, cfg, args.dir, progress, args.dry_run)

    done = sum(1 for v in progress.values() if v == "done")
    failed = sum(1 for v in progress.values() if str(v).startswith("failed"))
    missing = sum(1 for v in progress.values() if v == "missing")
    log.info("=== Summary: %d done, %d failed, %d missing ===", done, failed, missing)


if __name__ == "__main__":
    main()
