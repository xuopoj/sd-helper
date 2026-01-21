"""SD-Helper CLI: Service Delivery Engineer Tool for Huawei Cloud."""

import click
import httpx

from .auth import (
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
    load_global_config,
    load_local_config,
    save_global_config,
    save_local_config,
    set_default_profile,
)
from .api import LLMClient, get_model_config, list_models
from .data import (
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
@click.version_option(version="0.1.0")
def cli():
    """SD-Helper: CLI tool for Huawei Cloud Service Delivery Engineers."""
    pass


@cli.group()
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
    # Get config if not all params provided
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

    # Save debug data
    file_path = collector.save(name=output)
    click.echo(f"\nDebug data saved to: {file_path}")


# Data collection commands
@cli.group()
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
    from .data.storage import delete_collection

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
    from pathlib import Path

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

    if output:
        output_path = Path(output)
    else:
        output_path = Path.cwd() / f".sd-helper-{name}.yaml"

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
    the collected data (requests, responses, timing) for offline analysis.

    Example:
        sd-helper data template iam -o my-requests.yaml
        # Edit my-requests.yaml with your credentials
        sd-helper data run my-requests.yaml
    """
    from pathlib import Path

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


# LLM commands
@cli.group()
def llm():
    """LLM chat commands for ModelArts and Pangu endpoints."""
    pass


@llm.command("list")
@click.option("--profile", default=None, help="Profile name")
def llm_list(profile):
    """List available LLM models."""
    config = load_config(profile)
    models = list_models(config)

    if not models:
        click.echo("No LLM models configured.")
        click.echo("\nAdd models to your config file under 'llm.models':")
        click.echo("  llm:")
        click.echo("    default_model: my-model")
        click.echo("    models:")
        click.echo("      my-model:")
        click.echo("        endpoint: https://...")
        click.echo("        type: modelarts")
        return

    llm_config = config.get("llm", {})
    default_model = llm_config.get("default_model")

    click.echo("Available models:")
    for name in models:
        model_config = get_model_config(config, name)
        marker = " (default)" if name == default_model else ""
        click.echo(f"  {name}{marker}")
        click.echo(f"    type: {model_config.type}")
        click.echo(f"    endpoint: {model_config.endpoint[:50]}...")


@llm.command()
@click.argument("message", required=False)
@click.option("--model", "-m", default=None, help="Model name (from config)")
@click.option("--endpoint", "-e", envvar="SD_LLM_ENDPOINT", help="Direct endpoint URL (overrides model)")
@click.option("--profile", default=None, help="IAM profile for authentication")
@click.option("--temperature", "-t", default=None, type=float, help="Sampling temperature")
@click.option("--max-tokens", default=None, type=int, help="Maximum tokens to generate")
@click.option("--no-stream", is_flag=True, help="Disable streaming output")
@click.option("--system", "-s", default=None, help="System message")
@click.option("--file", "-f", "files", multiple=True, type=click.Path(exists=True), help="File(s) to include in context")
@click.option("--no-verify", is_flag=True, help="Disable SSL certificate verification")
@click.option("--debug", is_flag=True, help="Print debug info (request payload)")
def chat(message, model, endpoint, profile, temperature, max_tokens, no_stream, system, files, no_verify, debug):
    """Chat with an LLM model.

    If MESSAGE is provided, sends a single message and exits.
    Otherwise, starts an interactive chat session.

    Use -f/--file to include file contents in the conversation.

    Examples:
        sd-helper llm chat "What is ModelArts?"
        sd-helper llm chat -m pangu "Hello"
        sd-helper llm chat -f code.py "Explain this code"
        sd-helper llm chat -f data.json -f schema.json "Validate the data"
    """
    config = load_config(profile)

    # Resolve model configuration
    if endpoint:
        # Direct endpoint specified, use defaults
        model_config = None
        model_type = "modelarts"
        effective_temp = temperature if temperature is not None else 0.7
        effective_max_tokens = max_tokens if max_tokens is not None else 4096
        effective_system = system
        effective_verify_ssl = not no_verify
        model_name = "custom"
    else:
        # Try to get model from config
        model_config = get_model_config(config, model)
        if not model_config:
            available = list_models(config)
            if available:
                click.echo(f"Error: Model '{model}' not found.", err=True)
                click.echo(f"Available models: {', '.join(available)}", err=True)
            else:
                click.echo("Error: No LLM models configured.", err=True)
                click.echo("Use --endpoint to specify directly, or configure models:", err=True)
                click.echo("  sd-helper llm list  # for config format", err=True)
            raise SystemExit(1)

        endpoint = model_config.endpoint
        model_type = model_config.type
        model_name = model_config.name
        # Use config defaults, allow CLI overrides
        effective_temp = temperature if temperature is not None else model_config.temperature
        effective_max_tokens = max_tokens if max_tokens is not None else model_config.max_tokens
        effective_system = system if system is not None else model_config.system
        # CLI --no-verify overrides config
        effective_verify_ssl = False if no_verify else model_config.verify_ssl

    # Get token
    try:
        token_info = get_token_from_config(profile=profile)
        token = token_info["token"]
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if debug:
        click.echo(f"[DEBUG] verify_ssl: {effective_verify_ssl}", err=True)

    client = LLMClient(endpoint=endpoint, token=token, model_type=model_type, verify_ssl=effective_verify_ssl)
    messages = []

    if effective_system:
        messages.append({"role": "system", "content": effective_system})

    # Read file contents if provided
    file_context = ""
    if files:
        from pathlib import Path
        file_parts = []
        for file_path in files:
            path = Path(file_path)
            try:
                content = path.read_text()
                file_parts.append(content)
                if debug:
                    click.echo(f"[DEBUG] Loaded file: {path.name} ({len(content)} chars)", err=True)
            except Exception as e:
                click.echo(f"Warning: Could not read {file_path}: {e}", err=True)
        if file_parts:
            file_context = "\n\n".join(file_parts) + "\n\n"

    # Send first message if provided
    if message:
        full_message = file_context + message if file_context else message
        messages.append({"role": "user", "content": full_message})
        response = _send_chat(client, messages, effective_temp, effective_max_tokens, stream=not no_stream, debug=debug)
        if response:
            messages.append({"role": "assistant", "content": response})
        click.echo()
    elif file_context:
        # Add file context as initial message
        messages.append({"role": "user", "content": file_context.rstrip()})
        messages.append({"role": "assistant", "content": "I've received the file content. How can I help you with it?"})

    # Interactive mode - continue conversation
    click.echo("Type /clear to clear history, /exit to quit, Ctrl+C to cancel output.")
    if debug:
        click.echo(f"Model: {model_name} ({model_type})")
        click.echo(f"Endpoint: {endpoint}")

    # Track initial context for /clear
    initial_messages = messages.copy()

    while True:
        try:
            user_input = click.prompt("You", prompt_suffix="> ")

            # Handle commands
            if user_input.lower() in ("/exit", "/quit", "exit", "quit", "q"):
                break
            if user_input.lower() == "/clear":
                messages.clear()
                messages.extend(initial_messages)
                click.echo("History cleared.")
                continue

            messages.append({"role": "user", "content": user_input})
            response = _send_chat(
                client, messages, effective_temp, effective_max_tokens, stream=not no_stream, debug=debug
            )
            if response:
                messages.append({"role": "assistant", "content": response})
            else:
                # Remove the user message if no response (e.g., cancelled)
                messages.pop()
            click.echo()

        except click.exceptions.Abort:
            click.echo("\nGoodbye!")
            break
        except KeyboardInterrupt:
            click.echo("\nGoodbye!")
            break


def _send_chat(
    client: LLMClient,
    messages: list,
    temperature: float,
    max_tokens: int,
    stream: bool = True,
    debug: bool = False,
) -> str | None:
    """Send chat request and display response."""
    import json
    import sys

    if debug:
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        click.echo(f"[DEBUG] Endpoint: {client.endpoint}", err=True)
        click.echo(f"[DEBUG] Payload: {json.dumps(payload, indent=2)}", err=True)

    try:
        if stream:
            click.echo("Assistant> ", nl=False)
            full_response = []
            cancelled = False
            try:
                for chunk in client.chat(
                    messages=messages,
                    stream=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    try:
                        data = json.loads(chunk)
                        # Handle different response formats
                        content = None
                        if "choices" in data:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                        elif "content" in data:
                            content = data["content"]
                        elif "text" in data:
                            content = data["text"]

                        if content:
                            click.echo(content, nl=False)
                            full_response.append(content)
                    except json.JSONDecodeError:
                        # Raw text chunk
                        click.echo(chunk, nl=False)
                        full_response.append(chunk)
            except KeyboardInterrupt:
                cancelled = True
                click.echo("\n[cancelled]")

            if not cancelled:
                click.echo()
            return "".join(full_response) if full_response else None
        else:
            response = client.chat(
                messages=messages,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Handle different response formats
            content = None
            if "choices" in response:
                content = response["choices"][0].get("message", {}).get("content", "")
            elif "content" in response:
                content = response["content"]
            elif "text" in response:
                content = response["text"]

            if content:
                click.echo(f"Assistant> {content}")
                return content
            else:
                click.echo(f"Response: {response}")
                return None

    except KeyboardInterrupt:
        click.echo("\n[cancelled]")
        return None
    except httpx.HTTPStatusError as e:
        click.echo(f"\nHTTP Error: {e.response.status_code}", err=True)
        try:
            # For streaming responses, content may not be read yet
            e.response.read()
            click.echo(f"Response: {e.response.text}", err=True)
        except Exception:
            pass
        return None
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        return None


@llm.command()
@click.argument("model_name")
@click.option("--endpoint", "-e", prompt="LLM endpoint URL", help="LLM endpoint URL")
@click.option("--type", "-t", "model_type", default="modelarts",
              type=click.Choice(["modelarts", "pangu"]), help="Model type")
@click.option("--temperature", default=0.7, type=float, help="Default temperature")
@click.option("--max-tokens", default=2048, type=int, help="Default max tokens")
@click.option("--system", "-s", default=None, help="Default system message")
@click.option("--default", "set_default", is_flag=True, help="Set as default model")
@click.option("--profile", default=None, help="Profile name")
@click.option("--local", "-l", is_flag=True, help="Save to local .sd-helper.yaml")
def add(model_name, endpoint, model_type, temperature, max_tokens, system, set_default, profile, local):
    """Add or update an LLM model configuration.

    Examples:
        sd-helper llm add chatglm -e https://172.x.x.xxx/v1/infers/xxx --default
        sd-helper llm add pangu -e https://172.x.x.xxx/v1/chat -t pangu
        sd-helper llm add coder -e https://xxx --system "You are a coding assistant."
    """
    if local:
        config = load_local_config()
    else:
        if profile is None:
            profile = get_default_profile()
        config = load_global_config(profile)

    # Ensure llm section exists
    if "llm" not in config:
        config["llm"] = {"models": {}}
    if "models" not in config["llm"]:
        config["llm"]["models"] = {}

    # Add/update model
    model_data = {
        "endpoint": endpoint,
        "type": model_type,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system:
        model_data["system"] = system

    config["llm"]["models"][model_name] = model_data

    if set_default:
        config["llm"]["default_model"] = model_name

    # Save
    if local:
        config_path = save_local_config(config)
    else:
        config_path = save_global_config(config, profile)

    click.echo(f"Model '{model_name}' saved to {config_path}")
    if set_default:
        click.echo(f"Set as default model.")


if __name__ == "__main__":
    cli()
