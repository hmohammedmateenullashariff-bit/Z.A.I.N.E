"""
Z.A.I.N.E TUI Bottom Input Well Widget
"""

from textual.widget import Widget
from textual.widgets import Input, Static
from textual.containers import Horizontal
from textual.app import ComposeResult

from tui.theme import COLOR_EMERALD, COLOR_AMBER, COLOR_TEXT_MUTED, COLOR_TEXT_DIM

IDLE_HINTS = "MODE: HITL guardrails on  ·  /help  /status  /memory  /new  /clear  ·  F2 HUD  ·  F3 graph"
BUSY_HINTS = "GENERATING  ·  Esc cancels the reply  ·  approvals: y / n or the card buttons  ·  F3 live graph"
IDLE_PROMPT = "Z.A.I.N.E >> "
BUSY_PROMPT = "Z.A.I.N.E ·· "
IDLE_PLACEHOLDER = "Type a prompt or /command (e.g. /help, /status, write a function that…)"
BUSY_PLACEHOLDER = "Generating… press Esc to cancel"


class InputWell(Widget):
    """Bottom input well with mode hints and prompt field.

    Hints and prompt are plain text (markup off): with markup on, "[F2]" and "[Esc]" were parsed as
    style tags and silently disappeared.
    """

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
        yield Static(IDLE_HINTS, id="input-hints", markup=False)
        with Horizontal(id="prompt-row"):
            yield Static(IDLE_PROMPT, id="prompt-label", markup=False)
            yield Input(placeholder=IDLE_PLACEHOLDER, id="user-input")

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
            hints.update(BUSY_HINTS if generating else IDLE_HINTS)
            label.update(BUSY_PROMPT if generating else IDLE_PROMPT)
            label.styles.color = COLOR_AMBER if generating else COLOR_EMERALD
            field.placeholder = BUSY_PLACEHOLDER if generating else IDLE_PLACEHOLDER
        except Exception:
            pass
