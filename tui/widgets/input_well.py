"""
Z.A.I.N.E TUI Bottom Input Well Widget
"""

from textual.widget import Widget
from textual.widgets import Input, Static
from textual.containers import Horizontal
from textual.app import ComposeResult

from tui.theme import COLOR_EMERALD, COLOR_AMBER, COLOR_TEXT_MUTED, COLOR_TEXT_DIM


class InputWell(Widget):
    """Bottom input well with mode hints and prompt field."""

    DEFAULT_CSS = """
    InputWell {
        dock: bottom;
        height: auto;
        background: #0b0f19;
        border: solid #1e293b;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(id="input-well", **kwargs)
        self.is_generating = False

    def compose(self) -> ComposeResult:
        hints_text = "HINTS: /help  /memory  /status  /clear  /exit  ·  [F2] Toggle HUD  ·  [Esc] Clear Focus"
        yield Static(hints_text, id="input-hints")
        with Horizontal(id="prompt-row"):
            yield Static("$ zaine > ", id="prompt-label")
            yield Input(
                placeholder="Type prompt or /command (e.g. /help, /status, refactor code)...",
                id="user-input",
            )

    @property
    def input_field(self) -> Input:
        return self.query_one("#user-input", Input)

    def set_generating(self, generating: bool) -> None:
        """Toggle generating/busy visual state in input well."""
        self.is_generating = generating
        try:
            hints = self.query_one("#input-hints", Static)
            label = self.query_one("#prompt-label", Static)
            field = self.query_one("#user-input", Input)

            if generating:
                hints.update("STREAMING IN PROGRESS · Press [Esc] to cancel stream · [F2] Toggle HUD")
                label.update("$ zaine [BUSY] > ")
                field.placeholder = "[GENERATING...] Press Esc to cancel response stream..."
            else:
                hints.update("HINTS: /help  /memory  /status  /clear  /exit  ·  [F2] Toggle HUD  ·  [Esc] Clear Focus")
                label.update("$ zaine > ")
                field.placeholder = "Type prompt or /command (e.g. /help, /status, refactor code)..."
        except Exception:
            pass
