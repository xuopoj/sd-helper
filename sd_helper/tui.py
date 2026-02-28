"""Textual TUI for interactive LLM chat sessions."""
from __future__ import annotations
import json
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, RichLog, Static, TextArea
from textual.worker import get_current_worker


def _extract_content(chunk: str) -> str:
    try:
        data = json.loads(chunk)
        if "choices" in data:
            return data["choices"][0].get("delta", {}).get("content", "") or ""
        if "content" in data:
            return data["content"] or ""
        if "text" in data:
            return data["text"] or ""
    except json.JSONDecodeError:
        return chunk
    return ""


class ChatApp(App):
    CSS = """
    #history { height: 1fr; padding: 0 1; border: none; }
    #live    { height: auto; min-height: 1; padding: 0 1; color: $text-muted; }
    #input   { height: auto; max-height: 6; border: tall $accent; padding: 0 1; }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_history", "Clear"),
    ]

    def __init__(self, *, client, messages, initial_messages,
                 model_name, model_type, temperature, max_tokens, debug=False):
        super().__init__()
        self._client = client
        self._messages = messages
        self._initial = list(initial_messages)
        self._model_name = model_name
        self._model_type = model_type
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._debug = debug
        self._current_chunks: list[str] = []
        self._stream_worker = None
        self._streaming = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="history", markup=True, highlight=True, wrap=True)
        yield Static("", id="live")
        yield TextArea(id="input")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "SD-Helper Chat"
        self.sub_title = (
            f"{self._model_name}  |  {self._model_type}"
            f"  |  temp={self._temperature}  |  max_tokens={self._max_tokens}"
        )
        log = self.query_one("#history", RichLog)
        for msg in self._messages:
            if msg["role"] == "system":
                log.write(f"[dim]System: {msg['content']}[/dim]")
            elif msg["role"] == "user":
                log.write(f"[bold cyan]You>[/bold cyan] {msg['content']}")
            elif msg["role"] == "assistant":
                log.write(f"[bold green]Assistant>[/bold green] {msg['content']}")
        self.query_one("#input", TextArea).focus()

    def on_key(self, event) -> None:
        if event.key == "enter":
            event.prevent_default()
            self._submit()
        # shift+enter: TextArea handles as newline

    def action_clear_history(self) -> None:
        if self._stream_worker and not self._stream_worker.is_done:
            self._stream_worker.cancel()
        self._messages.clear()
        self._messages.extend(self._initial)
        self.query_one("#history", RichLog).clear()
        self.query_one("#live", Static).update("")
        self.query_one("#history", RichLog).write("[dim]History cleared.[/dim]")
        self._streaming = False

    def action_quit(self) -> None:
        if self._stream_worker and not self._stream_worker.is_done:
            self._stream_worker.cancel()
        self.exit()

    def on_key_ctrl_c(self) -> None:
        if self._streaming:
            if self._stream_worker:
                self._stream_worker.cancel()
        else:
            self.action_quit()

    def _submit(self) -> None:
        ta = self.query_one("#input", TextArea)
        text = ta.text.strip()
        if not text or self._streaming:
            return
        if text == "/clear":
            ta.clear()
            self.action_clear_history()
            return
        if text in ("/exit", "/quit"):
            self.action_quit()
            return
        ta.clear()
        self.query_one("#history", RichLog).write(
            f"[bold cyan]You>[/bold cyan] {text}"
        )
        self._messages.append({"role": "user", "content": text})
        self._current_chunks = []
        self._streaming = True
        self._stream_worker = self._stream_response()

    @work(thread=True, exclusive=True, group="stream")
    def _stream_response(self) -> None:
        worker = get_current_worker()
        chunks: list[str] = []
        cancelled = False
        error = None

        try:
            for raw_chunk in self._client.chat(
                messages=self._messages,
                stream=True,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            ):
                if worker.is_cancelled:
                    cancelled = True
                    break
                content = _extract_content(raw_chunk)
                if content:
                    chunks.append(content)
                    preview = "[bold green]Assistant>[/bold green] " + "".join(chunks)
                    self.call_from_thread(
                        self.query_one("#live", Static).update, preview
                    )
        except Exception as e:
            error = str(e)

        def _finish():
            live = self.query_one("#live", Static)
            log = self.query_one("#history", RichLog)
            live.update("")
            if chunks:
                full = "".join(chunks)
                log.write(f"[bold green]Assistant>[/bold green] {full}")
                self._messages.append({"role": "assistant", "content": full})
            if cancelled:
                log.write("[dim][cancelled][/dim]")
            if error:
                log.write(f"[red]Error: {error}[/red]")
                if self._messages and self._messages[-1]["role"] == "user":
                    self._messages.pop()
            self._streaming = False
            self.query_one("#input", TextArea).focus()

        self.call_from_thread(_finish)
