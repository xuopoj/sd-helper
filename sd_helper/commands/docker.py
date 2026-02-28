from __future__ import annotations

import logging
import os

import click
import yaml

from ..docker import (
    get_image_patterns,
    load_progress,
    process_image,
    save_progress,
    validate_manifest,
)


@click.group()
def docker():
    """Docker image management commands."""
    pass


@docker.command("upload-images")
@click.option("--config", "-c", "config_file", default="config.yaml", show_default=True,
              help="Config file with swr endpoint/org and assets_file path")
@click.option("--dir", "-d", "directory", default=".", show_default=True,
              help="Directory containing asset tarballs")
@click.option("--dry-run", is_flag=True, help="Print commands without executing")
@click.option("--validate", is_flag=True, help="Validate manifest files exist on disk, then exit")
@click.option("--reset", "-r", multiple=True, metavar="NAME",
              help="Reset progress for specific image (repeat for multiple)")
@click.option("--reset-all", is_flag=True, help="Reset all progress")
def upload_images(config_file, directory, dry_run, validate, reset, reset_all):
    """Load and push images to SWR.

    Reads the 镜像 section from the assets manifest, matches files on disk,
    then docker load + tag + push each image to SWR. Progress is saved to
    .progress.json so interrupted uploads can be resumed.

    \b
    Examples:
      sd-helper docker upload-images --config config.yaml --dir /path/to/files
      sd-helper docker upload-images --config config.yaml --dir /path/to/files --dry-run
      sd-helper docker upload-images --config config.yaml --dir /path/to/files --validate
      sd-helper docker upload-images --reset-all
      sd-helper docker upload-images --reset "name:tag"
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("upload_images.log"),
        ],
    )

    if reset_all or reset:
        progress = load_progress()
        if reset_all:
            click.echo("Resetting all progress")
            progress = {}
        else:
            for name in reset:
                progress.pop(name, None)
                click.echo(f"Reset: {name}")
        save_progress(progress)
        if not validate:
            return

    if not os.path.exists(config_file):
        raise click.ClickException(f"Config file not found: {config_file}")

    with open(config_file) as f:
        cfg = yaml.safe_load(f)

    manifest_file = cfg.get("assets_file")
    if not manifest_file:
        raise click.ClickException("'assets_file' not set in config")
    if not os.path.exists(manifest_file):
        raise click.ClickException(f"Assets file not found: {manifest_file}")

    if validate:
        found, missing = validate_manifest(manifest_file, directory)
        for sec, pat, actual in found:
            click.echo(f"  OK      [{sec}] {pat} -> {actual}")
        for sec, pat in missing:
            click.echo(f"  MISSING [{sec}] {pat}", err=True)
        click.echo(f"\nResult: {len(found)} found, {len(missing)} missing")
        raise SystemExit(1 if missing else 0)

    swr_endpoint = cfg["swr"]["endpoint"]
    org = cfg["swr"]["org"]
    cleanup = cfg.get("cleanup_after_push", False)

    image_patterns = get_image_patterns(manifest_file)
    if not image_patterns:
        raise click.ClickException("No image patterns found in manifest")

    progress = load_progress()
    click.echo(f"Starting: {len(image_patterns)} images, dry_run={dry_run}")
    if dry_run:
        click.echo("DRY RUN MODE — no commands will be executed")

    for pattern in image_patterns:
        process_image(pattern, swr_endpoint, org, directory, progress, dry_run, cleanup)

    done = sum(1 for v in progress.values() if v == "done")
    failed = sum(1 for v in progress.values() if str(v).startswith("failed"))
    missing_count = sum(1 for v in progress.values() if v == "missing")
    click.echo(f"\nSummary: {done} done, {failed} failed, {missing_count} missing")
