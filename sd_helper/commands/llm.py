from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import httpx

from ..auth import (
    get_default_profile,
    get_token_from_config,
    load_config,
    load_global_config,
    load_local_config,
    save_global_config,
    save_local_config,
)
from ..api import LLMClient, build_vision_message, get_model_config, list_models


@click.group()
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
@click.option("--image", "-i", "images", multiple=True, help="Image file path or URL (vLLM vision format, can repeat)")
@click.option("--no-verify", is_flag=True, help="Disable SSL certificate verification")
@click.option("--debug", is_flag=True, help="Print debug info (request payload)")
def chat(message, model, endpoint, profile, temperature, max_tokens, no_stream, system, files, images, no_verify, debug):
    """Chat with an LLM model.

    If MESSAGE is provided, sends a single message and exits.
    Otherwise, starts an interactive chat session.

    Examples:
        sd-helper llm chat "What is ModelArts?"
        sd-helper llm chat -m pangu "Hello"
        sd-helper llm chat -f code.py "Explain this code"
        sd-helper llm chat -i photo.jpg "Describe this image"
        sd-helper llm chat -i https://example.com/img.png "What do you see?"
    """
    config = load_config(profile)

    if endpoint:
        model_type = "modelarts"
        effective_temp = temperature if temperature is not None else 0.7
        effective_max_tokens = max_tokens if max_tokens is not None else 4096
        effective_system = system
        effective_verify_ssl = not no_verify
        model_name = "custom"
    else:
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
        effective_temp = temperature if temperature is not None else model_config.temperature
        effective_max_tokens = max_tokens if max_tokens is not None else model_config.max_tokens
        effective_system = system if system is not None else model_config.system
        effective_verify_ssl = False if no_verify else model_config.verify_ssl

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

    file_context = ""
    if files:
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

    if message:
        full_message = file_context + message if file_context else message
        if images:
            messages.append(build_vision_message(full_message, list(images)))
        else:
            messages.append({"role": "user", "content": full_message})
        response = _send_chat(client, messages, effective_temp, effective_max_tokens, stream=not no_stream, debug=debug)
        if response:
            messages.append({"role": "assistant", "content": response})
        click.echo()
        return

    elif file_context:
        messages.append({"role": "user", "content": file_context.rstrip()})
        messages.append({"role": "assistant", "content": "I've received the file content. How can I help you with it?"})
    elif images:
        messages.append(build_vision_message("I've attached image(s) for context.", list(images)))
        messages.append({"role": "assistant", "content": "I can see the image(s). How can I help you?"})

    initial_messages = messages.copy()
    from ..tui import ChatApp
    app = ChatApp(
        client=client,
        messages=messages,
        initial_messages=initial_messages,
        model_name=model_name,
        model_type=model_type,
        temperature=effective_temp,
        max_tokens=effective_max_tokens,
        debug=debug,
    )
    app.run()


def _send_chat(
    client: LLMClient,
    messages: list,
    temperature: float,
    max_tokens: int,
    stream: bool = True,
    debug: bool = False,
) -> str | None:
    """Send chat request and display response."""
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
                for chunk in client.chat(messages=messages, stream=True, temperature=temperature, max_tokens=max_tokens):
                    try:
                        data = json.loads(chunk)
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
                        click.echo(chunk, nl=False)
                        full_response.append(chunk)
            except KeyboardInterrupt:
                cancelled = True
                click.echo("\n[cancelled]")

            if not cancelled:
                click.echo()
            return "".join(full_response) if full_response else None
        else:
            response = client.chat(messages=messages, stream=False, temperature=temperature, max_tokens=max_tokens)
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
              type=click.Choice(["modelarts", "pangu", "vl"]), help="Model type")
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

    if "llm" not in config:
        config["llm"] = {"models": {}}
    if "models" not in config["llm"]:
        config["llm"]["models"] = {}

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

    if local:
        config_path = save_local_config(config)
    else:
        config_path = save_global_config(config, profile)

    click.echo(f"Model '{model_name}' saved to {config_path}")
    if set_default:
        click.echo(f"Set as default model.")
