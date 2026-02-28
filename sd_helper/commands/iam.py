from __future__ import annotations

import click

from ..auth import (
    clear_token_cache,
    configure_credentials,
    debug_token_fetch,
    fetch_token,
    get_default_profile,
    get_global_config_dir,
    get_local_config_file,
    get_token_from_config,
    list_profiles,
    load_config,
    set_default_profile,
)


@click.group()
def iam():
    """IAM authentication commands."""
    pass


@iam.command()
@click.option("--username", "-u", prompt=True, help="IAM username")
@click.option("--password", "-p", prompt=True, hide_input=True, help="IAM password")
@click.option("--domain", "-d", prompt="Domain name", help="Account domain name")
@click.option("--project", "-P", prompt="Project name", help="Project name")
@click.option("--region", "-r", default=None, help="Region (for public cloud)")
@click.option("--iam-url", default=None, help="Custom IAM URL (for private cloud)")
@click.option("--profile", default=None, help="Profile name (default: from config)")
@click.option("--local", "-l", is_flag=True, help="Save to local .sd-helper.yaml")
def configure(username, password, domain, project, region, iam_url, profile, local):
    """Configure IAM credentials."""
    config_path = configure_credentials(
        username=username,
        password=password,
        domain_name=domain,
        project_name=project,
        region=region,
        iam_url=iam_url,
        profile=profile,
        local=local,
    )
    profile_name = profile or get_default_profile()
    click.echo(f"Configuration saved to {config_path} [profile: {profile_name}]")


@iam.command()
@click.option("--no-cache", is_flag=True, help="Force fetch new token, ignore cache")
@click.option("--profile", default=None, help="Profile name (default: from config)")
@click.option("--username", "-u", help="IAM username (overrides config)")
@click.option("--password", "-p", help="IAM password (overrides config)")
@click.option("--domain", "-d", help="Domain name (overrides config)")
@click.option("--project", "-P", help="Project name (overrides config)")
@click.option("--region", "-r", help="Region (overrides config)")
@click.option("--iam-url", help="Custom IAM URL (overrides config)")
def token(no_cache, profile, username, password, domain, project, region, iam_url):
    """Fetch IAM token."""
    try:
        if username and password and domain and project:
            result = fetch_token(
                username=username,
                password=password,
                domain_name=domain,
                project_name=project,
                region=region,
                iam_url=iam_url,
                use_cache=not no_cache,
                profile=profile,
            )
        else:
            result = get_token_from_config(profile=profile, use_cache=not no_cache)

        click.echo(f"Token: {result['token'][:50]}...")
        click.echo(f"Project ID: {result['project_id']}")
        click.echo(f"Expires at: {result['expires_at']}")
        if result.get("from_cache"):
            click.echo("(from cache)")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"Failed to fetch token: {e}", err=True)
        raise SystemExit(1)


@iam.command("clear-cache")
@click.option("--profile", default=None, help="Profile to clear (default: all profiles)")
def clear_cache(profile):
    """Clear cached token."""
    if clear_token_cache(profile):
        if profile:
            click.echo(f"Token cache cleared for profile: {profile}")
        else:
            click.echo("All token caches cleared.")
    else:
        click.echo("No cache to clear.")


@iam.command("set-default")
@click.argument("profile")
def set_default(profile):
    """Set the default profile."""
    config_path = set_default_profile(profile)
    click.echo(f"Default profile set to: {profile}")
    click.echo(f"Config saved to: {config_path}")


@iam.command("list-profiles")
def list_profiles_cmd():
    """List all configured profiles."""
    profiles = list_profiles()
    default = get_default_profile()

    if not profiles:
        click.echo("No profiles configured.")
        return

    click.echo("Profiles:")
    for p in profiles:
        marker = " (default)" if p == default else ""
        click.echo(f"  - {p}{marker}")


@iam.command("show-config")
@click.option("--profile", default=None, help="Profile to show (default: from config)")
def show_config(profile):
    """Show current configuration."""
    from pathlib import Path
    global_dir = get_global_config_dir()
    local_file = get_local_config_file()
    default_profile = get_default_profile()
    active_profile = profile or default_profile

    click.echo("Config locations:")
    click.echo(f"  Global: {global_dir / 'config.yaml'}")
    click.echo(f"  Local:  {local_file or '.sd-helper.yaml (not found)'}")
    click.echo(f"  Cache:  {global_dir / f'token_cache_{active_profile}.json'}")

    click.echo(f"\nDefault profile: {default_profile}")
    click.echo(f"Active profile:  {active_profile}")

    click.echo(f"\nConfiguration for [{active_profile}]:")
    config = load_config(profile)
    if not config:
        click.echo("  (no configuration found)")
    else:
        for key, value in config.items():
            if key in ("password", "sk"):
                click.echo(f"  {key}: ****")
            else:
                click.echo(f"  {key}: {value}")


@iam.command("debug")
@click.option("--profile", default=None, help="Profile to use (default: from config)")
@click.option("--username", "-u", help="IAM username (overrides config)")
@click.option("--password", "-p", help="IAM password (overrides config)")
@click.option("--domain", "-d", help="Domain name (overrides config)")
@click.option("--project", "-P", help="Project name (overrides config)")
@click.option("--region", "-r", help="Region (overrides config)")
@click.option("--iam-url", help="Custom IAM URL (overrides config)")
@click.option("--output", "-o", default=None, help="Output file name")
@click.option("--no-mask", is_flag=True, help="Don't mask sensitive data in output")
def iam_debug(profile, username, password, domain, project, region, iam_url, output, no_mask):
    """Debug IAM token fetch with full request/response logging.

    Use this when on customer networks to diagnose authentication issues.
    All data is saved locally for offline analysis.
    """
    if not all([username, password, domain, project]):
        config = load_config(profile)
        username = username or config.get("username")
        password = password or config.get("password")
        domain = domain or config.get("domain_name")
        project = project or config.get("project_name")
        region = region or config.get("region")
        iam_url = iam_url or config.get("iam_url")

    if not all([username, password, domain, project]):
        click.echo("Error: Missing required credentials. Provide via options or configure a profile.", err=True)
        raise SystemExit(1)

    click.echo("Starting IAM debug session...")
    endpoint = iam_url or f"https://iam.{region or ''}.myhuaweicloud.com"
    click.echo(f"  Endpoint: {endpoint}")
    click.echo(f"  Domain: {domain}")
    click.echo(f"  Project: {project}")
    click.echo()

    collector = debug_token_fetch(
        username=username,
        password=password,
        domain_name=domain,
        project_name=project,
        region=region,
        iam_url=iam_url,
        mask_sensitive=not no_mask,
    )

    result = collector.custom_data.get("result", {})
    if result.get("success"):
        click.echo("Result: SUCCESS")
        click.echo(f"  Project ID: {result.get('project_id')}")
        click.echo(f"  Expires at: {result.get('expires_at')}")
    else:
        click.echo("Result: FAILED")
        click.echo(f"  Status: {result.get('status_code', 'N/A')}")
        click.echo(f"  Error: {result.get('error', 'Unknown')}")

    file_path = collector.save(name=output)
    click.echo(f"\nDebug data saved to: {file_path}")
