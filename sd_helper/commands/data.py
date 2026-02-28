from __future__ import annotations

from pathlib import Path

import click

from ..data import (
    DataCollector,
    TemplateRunner,
    get_data_dir,
    get_template,
    list_collections,
    list_templates,
    load_collection,
    save_template,
)


@click.group()
def data():
    """Offline data collection commands."""
    pass


@data.command("list")
def data_list():
    """List saved data collections."""
    collections = list_collections()

    if not collections:
        click.echo("No data collections found.")
        click.echo(f"Data directory: {get_data_dir()}")
        return

    click.echo(f"Data directory: {get_data_dir()}")
    click.echo(f"\nCollections ({len(collections)}):")
    for c in collections:
        click.echo(f"  {c['name']}")
        click.echo(f"    File: {c['file']}, Size: {c['size']} bytes")
        click.echo(f"    Modified: {c['modified']}")


@data.command("show")
@click.argument("name")
@click.option("--format", "-f", type=click.Choice(["yaml", "json"]), default="yaml")
def data_show(name, format):
    """Show contents of a data collection."""
    import json as json_module
    import yaml as yaml_module

    try:
        data = load_collection(name)
        if format == "json":
            click.echo(json_module.dumps(data, indent=2, default=str))
        else:
            click.echo(yaml_module.safe_dump(data, default_flow_style=False, sort_keys=False))
    except FileNotFoundError:
        click.echo(f"Collection not found: {name}", err=True)
        raise SystemExit(1)


@data.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def data_delete(name, yes):
    """Delete a data collection."""
    from ..data.storage import delete_collection

    if not yes:
        click.confirm(f"Delete collection '{name}'?", abort=True)

    if delete_collection(name):
        click.echo(f"Deleted: {name}")
    else:
        click.echo(f"Collection not found: {name}", err=True)
        raise SystemExit(1)


@data.command("collect")
@click.option("--name", "-n", default=None, help="Collection name")
@click.option("--note", multiple=True, help="Add notes to collection")
@click.option("--test-urls", "-t", multiple=True, help="URLs to test connectivity")
def data_collect(name, note, test_urls):
    """Start an interactive data collection session.

    Collects system info, tests connectivity, and saves results.
    """
    collector = DataCollector()

    click.echo("Collecting system info...")
    sys_info = collector.get_system_info()
    click.echo(f"  Hostname: {sys_info.get('hostname')}")
    click.echo(f"  Platform: {sys_info.get('platform')}")
    click.echo(f"  IPs: {sys_info.get('local_ips')}")

    for n in note:
        collector.add_note(n)

    if test_urls:
        click.echo("\nTesting connectivity...")
        results = collector.test_connectivity(list(test_urls))
        for url, result in results.items():
            status = "OK" if result["status"] == "ok" else "FAILED"
            click.echo(f"  {url}: {status}")

    file_path = collector.save(name=name)
    click.echo(f"\nData saved to: {file_path}")


@data.command("template")
@click.argument("name", default="default")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--list", "-l", "list_", is_flag=True, help="List available templates")
def data_template(name, output, list_):
    """Generate a request template file.

    Templates define API requests to execute on customer networks.
    Edit the generated file with your credentials and endpoints,
    then run with 'sd-helper data run <template-file>'.

    Available templates: default, iam, modelarts
    """
    if list_:
        click.echo("Available templates:")
        for t in list_templates():
            click.echo(f"  - {t}")
        return

    template = get_template(name)
    if not template:
        click.echo(f"Unknown template: {name}", err=True)
        click.echo(f"Available: {', '.join(list_templates())}")
        raise SystemExit(1)

    output_path = Path(output) if output else Path.cwd() / f".sd-helper-{name}.yaml"
    save_template(template, output_path)
    click.echo(f"Template saved to: {output_path}")
    click.echo("\nNext steps:")
    click.echo("  1. Edit the template file with your credentials and endpoints")
    click.echo(f"  2. Run: sd-helper data run {output_path}")


@data.command("run")
@click.argument("template_file", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output collection name")
@click.option("--stop-on-error", is_flag=True, help="Stop execution on first error")
@click.option("--no-mask", is_flag=True, help="Don't mask sensitive data")
def data_run(template_file, output, stop_on_error, no_mask):
    """Execute requests from a template file.

    Runs all API requests defined in the template and saves
    the collected data for offline analysis.

    Example:
        sd-helper data template iam -o my-requests.yaml
        sd-helper data run my-requests.yaml
    """
    click.echo(f"Loading template: {template_file}")
    runner = TemplateRunner(Path(template_file), mask_sensitive=not no_mask)

    template_info = runner.template
    click.echo(f"  Name: {template_info.get('name', 'unnamed')}")
    click.echo(f"  Base URL: {template_info.get('base_url', 'N/A')}")
    click.echo(f"  Requests: {len(template_info.get('requests', []))}")
    click.echo()

    click.echo("Executing requests...")
    summary = runner.run_all(skip_on_error=stop_on_error)

    click.echo()
    click.echo(f"Results: {summary['successful']}/{summary['total_requests']} successful")

    for name, result in summary["results"].items():
        status = "OK" if result["success"] else "FAILED"
        status_code = result.get("status_code", "N/A")
        click.echo(f"  [{status}] {name}: HTTP {status_code}")
        if result.get("error"):
            click.echo(f"         Error: {result['error']}")

    file_path = runner.save(name=output)
    click.echo(f"\nData saved to: {file_path}")
