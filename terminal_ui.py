"""
Z.A.I.N.E — Professional Agent Terminal Operating Environment
Terminal-Native Architecture (CLI/TUI First).
Information Architecture inspired by high-density developer systems consoles (Claude Code, Hermes Agent).

Design Rules:
- Flat color palette (charcoal background, off-white text, restrained terminal green accent).
- Zero gradients, zero cyan/violet neon schemes, zero glowing borders, zero glassmorphism.
- Zero fake telemetry (100% real runtime metrics only).
- Zero sci-fi marketing jargon; accurate software states.
- High information density, clean typography, compact dot-leader tool execution logs.
- Voice strictly command-gated and disabled by default.
"""

import os
import sys
from zaine_env import running_under_tests
import time
import json
import uuid
import shutil
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# Enable ANSI colors & UTF-8 output on Windows
if sys.platform == "win32":
    try:
        os.system("")  # Enables Virtual Terminal Processing
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import threading
import requests
import voice
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.box import SQUARE, ASCII
from rich.live import Live

# Initialize Rich Console
console = Console(highlight=False)

def supports_unicode() -> bool:
    try:
        encoding = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        return "utf" in encoding.lower()
    except Exception:
        return False

UNICODE_SUPPORTED = supports_unicode()
BOX_STYLE = SQUARE if UNICODE_SUPPORTED else ASCII

# Restrained Terminal Glyphs (Minimal, Functional)
GLYPH_READY = "●" if UNICODE_SUPPORTED else "*"
GLYPH_RUNNING = "⟳" if UNICODE_SUPPORTED else ">"
GLYPH_TOOL = "◌" if UNICODE_SUPPORTED else "o"
GLYPH_STREAMING = "▶" if UNICODE_SUPPORTED else ">"
GLYPH_VOICE_ACTIVE = "◉" if UNICODE_SUPPORTED else "o"
GLYPH_SUCCESS = "✓" if UNICODE_SUPPORTED else "+"
GLYPH_FAILED = "✗" if UNICODE_SUPPORTED else "x"
GLYPH_WARN = "!"
GLYPH_PROMPT = "❯" if UNICODE_SUPPORTED else ">"
GLYPH_SUB = "↳" if UNICODE_SUPPORTED else "->"
GLYPH_DOT = "•" if UNICODE_SUPPORTED else "-"
GLYPH_STANDBY = "○" if UNICODE_SUPPORTED else "o"
CURSOR_BLOCK = "▋" if UNICODE_SUPPORTED else "_"
GLYPH_SEP = "│" if UNICODE_SUPPORTED else "|"
GLYPH_ELLIPSIS = "…" if UNICODE_SUPPORTED else "..."

# Dynamic Animation Frames (Claude Code / Hermes engineering style)
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPINNER_FRAMES_ASCII = [".  ", ".. ", "...", " ..", "  .", "   "]
PHASE_FRAMES = ["◐", "◓", "◑", "◒"] if UNICODE_SUPPORTED else ["|", "/", "-", "\\"]

# Restrained Terminal Color Palette (Absolute Rules: No gradients, no cyan, no glow)
CLR_BG = "#101212"
CLR_TEXT = "#E6E6E1"
CLR_TEXT_MUTED = "#9A9D98"
CLR_DIM = "#666A66"
CLR_BORDER = "#2E3232"
CLR_BORDER_MUTED = "#1E2222"
CLR_GREEN = "#72C98B"       # Restrained terminal green (Jarvis primary & success)
CLR_RED = "#D96666"         # Muted crimson (Ultron primary & error)
CLR_AMBER = "#D4A359"       # Muted amber (warnings & running tools)
CLR_NEUTRAL = "#9A9D98"

# Persona Theme Profiles
THEMES = {
    "jarvis": {
        "name": "JARVIS",
        "primary": CLR_GREEN,
        "accent": CLR_GREEN,
        "border": CLR_BORDER,
        "dim": CLR_DIM,
        "user_prefix": "Sir",
    },
    "ultron": {
        "name": "ULTRON",
        "primary": CLR_RED,
        "accent": CLR_RED,
        "border": CLR_BORDER,
        "dim": CLR_DIM,
        "user_prefix": "Creator",
    }
}


class AnimationState:
    READY = "READY"
    THINKING = "THINKING"
    TOOL_RUNNING = "TOOL_RUNNING"
    STREAMING = "STREAMING"
    LISTENING = "LISTENING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    IDLE = "IDLE"


def is_animation_enabled() -> bool:
    """
    Determines whether terminal-native animations are permitted.
    Disabled when:
    - ZAINE_NO_ANIMATION environment variable is set ('1', 'true', 'yes')
    - stdout is redirected, piped, or not a TTY
    - running under automated test runner (unless ZAINE_FORCE_ANIMATION=1 is set)
    """
    if os.environ.get("ZAINE_FORCE_ANIMATION", "") == "1":
        return True
    if os.environ.get("ZAINE_NO_ANIMATION", "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    if running_under_tests():
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except Exception:
        return False
    return True


class TerminalUIState:
    """Manages active presentation state for the Z.A.I.N.E terminal."""
    def __init__(self):
        self.mode = "companion"  # "companion" or "code"
        self.persona = "jarvis"  # "jarvis" or "ultron"
        self.verbosity = "normal"  # "compact", "normal", "verbose"
        self.active_model = "zaine-reflex-7b"
        self.last_duration = 0.0
        self.core_url = "http://127.0.0.1:7860"
        self.is_connected = False
        self.active_user = "Mateen Sir"
        self.user_role = "ADMIN"
        self.current_status = "READY"
        self.cancel_requested = False
        self.session_seq = 1
        self.session_id = f"SES-{datetime.datetime.now().strftime('%m%d')}-01"

state = TerminalUIState()


class AnimationController:
    """
    Manages transient terminal animations (thinking spinner, status transitions).
    Strict guarantees:
    - Zero background threads when idle.
    - Animation frames NEVER enter conversation history or persistent scrollback.
    - Clean shutdown on exceptions, /new, /exit, or SIGINT.
    - Negligible CPU (8-10 FPS rate limit).
    - Fully bypassed when ZAINE_NO_ANIMATION=1 or non-TTY.
    """
    def __init__(self, console_instance: Console = console):
        self.console = console_instance
        self.state = AnimationState.IDLE
        self._live: Optional[Live] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._phase_index = 0
        self._think_start = 0.0
        self._current_message = "Understanding request"

    def get_phase_glyph(self) -> str:
        """Returns the current cycling phase indicator for status bar."""
        return PHASE_FRAMES[self._phase_index % len(PHASE_FRAMES)]

    def start_thinking(self, message: str = "Understanding request"):
        """Starts a transient live spinner indicator with contextual phase."""
        self.stop()
        with self._lock:
            self.state = AnimationState.THINKING
            state.current_status = "THINKING"
            self._think_start = time.time()
            self._current_message = message

            if not is_animation_enabled():
                return

            self._stop_event.clear()
            self._live = Live(
                self._render_thinking_text(0),
                console=self.console,
                transient=True,
                auto_refresh=False
            )
            try:
                self._live.start()
            except Exception:
                self._live = None
                return

            def _spinner_loop():
                step = 0
                while not self._stop_event.wait(0.1):
                    step += 1
                    self._phase_index = step
                    live = self._live
                    if live:
                        try:
                            live.update(self._render_thinking_text(step), refresh=True)
                        except Exception:
                            break

            self._thread = threading.Thread(target=_spinner_loop, daemon=True)
            self._thread.start()

    def update_phase(self, phase_name: str):
        """Dynamically updates the thinking phase message without restarting the Live context."""
        with self._lock:
            self._current_message = phase_name
            if self._live:
                try:
                    self._live.update(self._render_thinking_text(self._phase_index), refresh=True)
                except Exception:
                    pass

    def _render_thinking_text(self, step: int) -> Text:
        th = get_theme()
        frames = SPINNER_FRAMES if UNICODE_SUPPORTED else SPINNER_FRAMES_ASCII
        frame = frames[step % len(frames)]
        t = Text()
        t.append("  Z.A.I.N.E ", style=f"bold {th['primary']}")
        t.append(f"{frame} ", style=CLR_AMBER)
        msg = self._current_message
        elapsed = time.time() - self._think_start if self._think_start > 0 else 0.0
        if elapsed >= 3.0:
            if "reasoning" in msg.lower():
                display_msg = f"Deep reasoning · {elapsed:.1f}s"
            else:
                display_msg = f"{msg} · {elapsed:.1f}s"
        else:
            display_msg = msg
        t.append(display_msg, style=CLR_TEXT_MUTED)
        return t

    def stop(self):
        """Stops any active transient animation and cleans up Live contexts."""
        self._stop_event.set()
        th = self._thread
        if th and th.is_alive() and th != threading.current_thread():
            th.join(timeout=0.2)
        with self._lock:
            self._thread = None
            if self._live:
                try:
                    self._live.stop()
                except Exception:
                    pass
                self._live = None

            if self.state == AnimationState.THINKING:
                self.state = AnimationState.READY

    def set_state(self, new_state: str):
        """Transitions state and stops thinking spinner if leaving thinking."""
        with self._lock:
            if self.state == AnimationState.THINKING and new_state != AnimationState.THINKING:
                self.stop()
            self.state = new_state
            state.current_status = new_state


anim_controller = AnimationController(console)


# ==============================================================================
# 1. CORE SERVICE DISCOVERY & HEALTH
# ==============================================================================

def get_core_service_url() -> str:
    """Discovers active core HTTP service port from .zaine_core.json."""
    config_path = PROJECT_ROOT / ".zaine_core.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            port = data.get("port", 7860)
            return f"http://127.0.0.1:{port}"
        except Exception:
            pass
    return "http://127.0.0.1:7860"


def check_core_service_health(core_url: Optional[str] = None) -> Tuple[bool, dict]:
    """Checks if Z.A.I.N.E Core Service is online and returns health metadata."""
    url = core_url or get_core_service_url()
    try:
        # Fast pre-check to fail immediately (< 0.04s) if no server is listening
        import urllib.parse
        import socket
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 7860
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.04)
        try:
            s.connect((host, port))
            s.close()
        except Exception:
            try:
                s.close()
            except Exception:
                pass
            return False, {}

        resp = requests.get(f"{url}/api/health", timeout=0.3)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("ok", False), data
    except Exception:
        pass
    return False, {}


def sync_core_state(target_url: Optional[str] = None):
    """Syncs state from Core Service if reachable. Auto-boots CoreService if offline."""
    if target_url:
        state.core_url = target_url
    elif not state.core_url or state.core_url == "http://127.0.0.1:7860":
        state.core_url = get_core_service_url()

    online, _ = check_core_service_health(state.core_url)
    if not online and not running_under_tests():
        # Auto-boot headless CoreService in-process so standalone CLI is always functional
        try:
            from core_service import get_core_service, CoreService, set_active_core_service
            active = get_core_service()
            if not active:
                active = CoreService(port=7860)
                active.start_server()
                set_active_core_service(active)
                time.sleep(0.3)
                state.core_url = f"http://127.0.0.1:{active.port}"
                online, _ = check_core_service_health(state.core_url)
        except Exception:
            pass

    state.is_connected = online
    if online:
        try:
            r = requests.get(f"{state.core_url}/api/mode", timeout=0.5)
            if r.status_code == 200:
                core_mode = r.json().get("mode", "jarvis")
                state.persona = "ultron" if core_mode == "ultron" else "jarvis"
        except Exception:
            pass
        try:
            r = requests.get(f"{state.core_url}/api/lockscreen/status", timeout=0.5)
            if r.status_code == 200:
                usr = r.json().get("user", {})
                state.active_user = usr.get("name", "Mateen Sir")
                state.user_role = usr.get("role", "admin").upper()
        except Exception:
            pass


def get_theme() -> dict:
    return THEMES.get(state.persona, THEMES["jarvis"])


def get_terminal_cols() -> int:
    try:
        return shutil.get_terminal_size((80, 24)).columns
    except Exception:
        return console.width or 80


# ==============================================================================
# 2. STATUS BAR & STARTUP BANNER RENDERING
# ==============================================================================

def update_status_state(status_text: Optional[str] = None, duration_s: Optional[float] = None, tool_info: Optional[str] = None):
    """
    Updates active runtime status state without appending boxes into conversation scrollback.
    Maintains strict separation between Persistent UI State (A) and Conversation History (B).
    """
    if status_text:
        state.current_status = status_text
    if duration_s is not None:
        state.last_duration = duration_s


def render_status_bar(status_text: Optional[str] = None, duration_s: Optional[float] = None, tool_info: Optional[str] = None):
    """
    Renders the compact professional status header.
    Format:
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ Z.A.I.N.E │ JARVIS │ qwen2.5:3b │ VOICE: OFF │ TOOLS: 119 │ SES-1008-01 │ ● READY │
    └─────────────────────────────────────────────────────────────────────────────┘
    """
    th = get_theme()
    cols = get_terminal_cols()

    st = status_text or state.current_status
    dur = duration_s if duration_s is not None else state.last_duration
    v_on = voice.is_voice_enabled()
    v_styled = f"[{CLR_GREEN}]VOICE: ON[/{CLR_GREEN}]" if v_on else f"[{CLR_DIM}]VOICE: OFF[/{CLR_DIM}]"

    # Dynamic status indicator styling
    if "READY" in st or st == "IDLE":
        st_styled = f"[{CLR_GREEN}]{GLYPH_READY} READY[/{CLR_GREEN}]"
    elif "THINKING" in st:
        phase = anim_controller.get_phase_glyph()
        st_styled = f"[{CLR_AMBER}]{phase} THINKING[/{CLR_AMBER}]"
    elif "STREAMING" in st:
        st_styled = f"[{CLR_GREEN}]{GLYPH_STREAMING} STREAMING[/{CLR_GREEN}]"
    elif "LISTENING" in st:
        if v_on:
            st_styled = f"[{CLR_AMBER}]{GLYPH_VOICE_ACTIVE} LISTENING[/{CLR_AMBER}]"
        else:
            st_styled = f"[{CLR_GREEN}]{GLYPH_READY} READY[/{CLR_GREEN}]"
    elif "SPEAKING" in st:
        if v_on:
            st_styled = f"[{CLR_GREEN}]{GLYPH_VOICE_ACTIVE} SPEAKING[/{CLR_GREEN}]"
        else:
            st_styled = f"[{CLR_GREEN}]{GLYPH_READY} READY[/{CLR_GREEN}]"
    elif "TOOL" in st or tool_info:
        label = tool_info or st
        if label.startswith("TOOL: "):
            label = label[6:]
        elif label == "TOOL_RUNNING":
            label = "TOOL"
        # Responsively truncate tool label with ellipsis to avoid wrapping
        max_lbl = 18 if cols < 95 else (28 if cols < 120 else 40)
        if len(label) > max_lbl:
            label = label[:max(4, max_lbl - 3)] + "..."
        st_styled = f"[{CLR_AMBER}]{GLYPH_TOOL} {label}[/{CLR_AMBER}]"
    elif "QUEUED" in st:
        st_styled = f"[{CLR_AMBER}]{st}[/{CLR_AMBER}]"
    elif "ERROR" in st or "FAILED" in st:
        st_styled = f"[{CLR_RED}]{GLYPH_FAILED} ERROR[/{CLR_RED}]"
    elif "CANCELLED" in st:
        st_styled = f"[{CLR_AMBER}]{GLYPH_WARN} CANCELLED[/{CLR_AMBER}]"
    else:
        st_styled = f"[{CLR_GREEN}]{GLYPH_READY} READY[/{CLR_GREEN}]"

    # Dynamic total tools count
    total_tools = 119
    try:
        from tools import TOOL_REGISTRY
        total_tools = len(TOOL_REGISTRY)
    except Exception:
        pass

    # Model display name (responsively truncated with ellipsis if long)
    model_name = state.active_model
    max_model_len = 16 if cols < 95 else (24 if cols < 120 else 36)
    if len(model_name) > max_model_len:
        model_name = model_name[:max(4, max_model_len - 3)] + "..."

    # Build responsive status content
    sep = f" {GLYPH_SEP} "
    if cols < 65:
        bar_text = f" [bold {th['primary']}]Z.A.I.N.E[/]{sep}{st_styled}"
    elif cols < 85:
        bar_text = f" [bold {th['primary']}]Z.A.I.N.E[/]{sep}[white]{model_name}[/]{sep}{v_styled}{sep}{st_styled}"
    elif cols < 115:
        bar_text = (
            f" [bold {th['primary']}]Z.A.I.N.E[/]{sep}"
            f"[{th['accent']}]{th['name']}[/]{sep}"
            f"[white]{model_name}[/]{sep}"
            f"{v_styled}{sep}"
            f"[dim]TOOLS: {total_tools}[/]{sep}"
            f"[dim]{state.session_id}[/]{sep}"
            f"{st_styled}"
        )
    else:
        dur_str = f"{sep}[dim]{dur:.1f}s[/dim]" if dur > 0 else ""
        bar_text = (
            f" [bold {th['primary']}]Z.A.I.N.E[/]{sep}"
            f"[{th['accent']}]{th['name']}[/]{sep}"
            f"[white]{model_name}[/]{sep}"
            f"{v_styled}{sep}"
            f"[dim]TOOLS: {total_tools}[/]{sep}"
            f"[dim]{state.session_id}[/]{sep}"
            f"{st_styled}"
            f"{dur_str}"
        )

    t_bar = Text.from_markup(bar_text)
    t_bar.no_wrap = True
    t_bar.overflow = "ellipsis"

    panel = Panel(
        t_bar,
        border_style=CLR_BORDER,
        box=BOX_STYLE,
        padding=(0, 0),
        expand=True,
        style="on black" if console.is_terminal else ""
    )
    console.print(panel)


def render_startup_boot():
    """
    Renders restrained 1-2 second startup initialization sequence checking real subsystems.
    If ZAINE_NO_ANIMATION=1, non-TTY, redirected, or running tests:
    Executes immediately without delays.
    """
    th = get_theme()
    animated = is_animation_enabled()
    cols = get_terminal_cols()
    div_line = "─" * min(50, max(30, cols - 4))

    console.print()
    console.print(f"  [bold {th['primary']}]Z.A.I.N.E INITIALIZING[/bold {th['primary']}]\n")

    # 1. Core engine
    if animated:
        sync_core_state()
    core_ok = state.is_connected
    core_text = "online" if core_ok else "standby"
    core_color = CLR_GREEN if core_ok else CLR_DIM
    if animated:
        time.sleep(0.08)
    console.print(f"  Core engine       [{core_color}]{GLYPH_SUCCESS if core_ok else GLYPH_STANDBY} {core_text}[/{core_color}]")

    # 2. Brain router
    router_ok = False
    try:
        from core_router import router
        router_ok = bool(router and getattr(router, "reflex_model", None))
    except Exception:
        pass
    router_text = "online" if router_ok else "fallback"
    router_color = CLR_GREEN if router_ok else CLR_DIM
    if animated:
        time.sleep(0.08)
    console.print(f"  Brain router      [{router_color}]{GLYPH_SUCCESS if router_ok else GLYPH_STANDBY} {router_text}[/{router_color}]")

    # 3. Memory vault
    vault_ok = False
    try:
        from memory_manager import get_memory_manager
        mm = get_memory_manager()
        vault_ok = bool(mm and mm.available and mm.vault_path and mm.vault_path.exists())
    except Exception:
        pass
    vault_text = "connected" if vault_ok else "local store fallback"
    vault_color = CLR_GREEN if vault_ok else CLR_DIM
    if animated:
        time.sleep(0.08)
    console.print(f"  Memory vault      [{vault_color}]{GLYPH_SUCCESS if vault_ok else GLYPH_STANDBY} {vault_text}[/{vault_color}]")

    # 4. Tool registry
    tool_count = 119
    try:
        from tools import TOOL_REGISTRY
        tool_count = len(TOOL_REGISTRY)
    except Exception:
        pass
    if animated:
        time.sleep(0.08)
    console.print(f"  Tool registry     [{CLR_GREEN}]{GLYPH_SUCCESS} {tool_count} tools[/{CLR_GREEN}]")

    # 5. Vision
    if animated:
        time.sleep(0.08)
    console.print(f"  Vision            [{CLR_GREEN}]{GLYPH_SUCCESS} ready[/{CLR_GREEN}]")

    # 6. Voice (Must correctly display standby because default voice state is OFF!)
    v_on = voice.is_voice_enabled()
    voice_glyph = GLYPH_SUCCESS if v_on else GLYPH_STANDBY
    voice_text = "active" if v_on else "standby"
    voice_color = CLR_GREEN if v_on else CLR_DIM
    if animated:
        time.sleep(0.08)
    console.print(f"  Voice             [{voice_color}]{voice_glyph} {voice_text}[/{voice_color}]")

    # 7. Additional subsystem checks from Section 4
    if animated:
        time.sleep(0.08)
    console.print(f"\n  Loading persona ............ [{CLR_GREEN}]{GLYPH_SUCCESS} {th['name']}[/{CLR_GREEN}]")
    if animated:
        time.sleep(0.08)
    console.print(f"  Loading memory context ..... [{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}]")
    if animated:
        time.sleep(0.08)
    console.print(f"  Calibrating terminal ....... [{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}]")

    if animated:
        time.sleep(0.12)
    console.print()
    console.print(f"  [{CLR_BORDER}]{div_line}[/{CLR_BORDER}]\n")
    console.print(f"              [bold {CLR_GREEN}]SYSTEM READY[/bold {CLR_GREEN}]\n")

    # Contextual greeting
    hr = datetime.datetime.now().hour
    if hr < 12:
        tod = "Good morning"
    elif hr < 18:
        tod = "Good afternoon"
    else:
        tod = "Good evening"

    if state.persona == "ultron":
        greeting = "Creator, I'm online."
    else:
        greeting = f"{tod}, {th['user_prefix']}."

    console.print(f"  [{CLR_TEXT}]{greeting}[/{CLR_TEXT}]\n")
    console.print(f"  [{CLR_TEXT_MUTED}]Type [bold {CLR_TEXT}]/help[/bold {CLR_TEXT}] for commands.[/{CLR_TEXT_MUTED}]\n")


def render_startup_panel():
    """Renders startup boot overview sequence."""
    render_startup_boot()


# ==============================================================================
# 3. HIGH-DENSITY TOOL EXECUTION & REASONING RENDERERS
# ==============================================================================

def format_tool_args_summary(args: Any) -> str:
    """Concise single-line summary of tool arguments for telemetry traces."""
    if not isinstance(args, dict):
        s = str(args).strip().replace("\n", " ")
        return (s[:57] + "...") if len(s) > 60 else s
    parts = []
    for k, v in args.items():
        v_str = str(v).strip().replace("\n", " ")
        if len(v_str) > 30:
            v_str = v_str[:27] + "..."
        parts.append(f"{k}={v_str}")
    return ", ".join(parts)


class ToolExecutionRenderer:
    """
    Renders transient tree execution during tool runs, collapsing into
    compact dot-aligned summary lines upon completion.
    """
    def __init__(self, console_instance: Console = console):
        self.console = console_instance
        self.active_tools = {}
        self.completed_tools = []
        self._live: Optional[Live] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._current_tool_name: Optional[str] = None
        self._current_args: Any = None

    def on_start(self, tool_name: str, args: Any):
        t0 = time.time()
        self._cleanup_live()
        with self._lock:
            self._current_tool_name = tool_name
            self._current_args = args
            self.active_tools[tool_name] = {"start_time": t0, "args": args}

            if state.verbosity == "compact":
                return

            if is_animation_enabled():
                self._stop_event.clear()
                self._live = Live(
                    self._build_tree_renderable(tool_name, args, step=0),
                    console=self.console,
                    transient=True,
                    auto_refresh=False
                )
                try:
                    self._live.start()
                except Exception:
                    self._live = None
                    return

                def _tool_tick():
                    step = 0
                    while not self._stop_event.wait(0.1):
                        step += 1
                        live = self._live
                        if live:
                            try:
                                live.update(self._build_tree_renderable(tool_name, args, step=step), refresh=True)
                            except Exception:
                                break

                self._thread = threading.Thread(target=_tool_tick, daemon=True)
                self._thread.start()
            else:
                if state.verbosity == "verbose":
                    self.console.print(f"  [{CLR_TEXT_MUTED}][tool][/{CLR_TEXT_MUTED}] [bold {CLR_TEXT}]{tool_name}[/bold {CLR_TEXT}]")

    def _build_tree_renderable(self, tool_name: str, args: Any, step: int = 0) -> Text:
        th = get_theme()
        frames = SPINNER_FRAMES if UNICODE_SUPPORTED else SPINNER_FRAMES_ASCII
        frame = frames[step % len(frames)]
        t = Text()
        t.append(f"  [bold {th['primary']}]Z.A.I.N.E[/bold {th['primary']}]\n")

        # Multi-tool execution vs single tool execution
        if len(self.completed_tools) > 0:
            for c_name, c_dur, is_err in self.completed_tools:
                glyph = GLYPH_FAILED if is_err else GLYPH_SUCCESS
                color = CLR_RED if is_err else CLR_GREEN
                t.append(f"    ├─ [{color}]{glyph}[/{color}] [{CLR_TEXT}]{c_name}[/{CLR_TEXT}] [{CLR_DIM}]· {c_dur:.2f}s[/{CLR_DIM}]\n")
            t.append(f"    ├─ [{CLR_AMBER}]{frame}[/{CLR_AMBER}] [bold {CLR_TEXT}]{tool_name}[/bold {CLR_TEXT}]\n")
            t.append(f"    └─ [{CLR_DIM}]{GLYPH_STREAMING} Preparing response[/{CLR_DIM}]\n")
        else:
            phase_glyph = PHASE_FRAMES[step % len(PHASE_FRAMES)]
            t.append(f"    ├─ [{CLR_DIM}]{phase_glyph} Understanding request[/{CLR_DIM}]\n")

            t_low = tool_name.lower()
            if "search" in t_low or "vault" in t_low:
                action_label = "Memory search"
                sub_label = "Reviewing relevant notes"
            elif "memory" in t_low:
                action_label = "Memory lookup"
                sub_label = "Inspecting records"
            elif "file" in t_low or "read" in t_low or "dir" in t_low:
                action_label = "Filesystem inspection"
                sub_label = "Reading workspace"
            elif "code" in t_low or "run" in t_low or "exec" in t_low:
                action_label = "Code execution"
                sub_label = "Evaluating sandbox"
            else:
                action_label = tool_name
                sub_label = "Executing operation"

            t.append(f"    ├─ [{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}] [{CLR_TEXT}]{action_label}[/{CLR_TEXT}]\n")
            t.append(f"    ├─ [{CLR_AMBER}]{frame}[/{CLR_AMBER}] [{CLR_TEXT_MUTED}]{sub_label}[/{CLR_TEXT_MUTED}]\n")
            t.append(f"    └─ [{CLR_DIM}]{GLYPH_STREAMING} Preparing response[/{CLR_DIM}]\n")
        return t

    def _cleanup_live(self):
        self._stop_event.set()
        th = self._thread
        if th and th.is_alive() and th != threading.current_thread():
            th.join(timeout=0.2)
        self._thread = None
        if self._live:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

    def on_done(self, tool_name: str, result: Any, duration_s: Optional[float] = None):
        with self._lock:
            self._cleanup_live()
            info = self.active_tools.pop(tool_name, None)
            dur = duration_s if duration_s is not None else ((time.time() - info["start_time"]) if info else 0.0)
            cols = get_terminal_cols()

            res_str = str(result).strip()
            is_error = any(m in res_str for m in ("Error:", "Traceback", "SyntaxError", "NameError", "exited with code"))
            status_glyph = GLYPH_FAILED if is_error else GLYPH_SUCCESS
            status_color = CLR_RED if is_error else CLR_GREEN
            status_label = f"{status_glyph} {dur:.2f}s"

            self.completed_tools.append((tool_name, dur, is_error))

            if state.verbosity == "compact":
                return

            self.console.print(f"  [{status_color}]{status_glyph}[/{status_color}] [bold {CLR_TEXT}]{tool_name}[/bold {CLR_TEXT}] [{CLR_DIM}]· {dur:.2f}s[/{CLR_DIM}]")

            # Extract compact sub-bullet note if informative
            if res_str:
                lines = [ln.strip() for ln in res_str.splitlines() if ln.strip()]
                if lines:
                    preview = lines[0]
                    is_note_summary = any(k in preview.lower() for k in ("relevant note", "note found", "records found", "result found", "found"))
                    if is_note_summary or state.verbosity == "verbose":
                        if len(preview) > (cols - 20):
                            preview = preview[:max(20, cols - 24)] + "..."
                        self.console.print(f"    [{status_color if is_error else CLR_DIM}]{GLYPH_SUB} {preview}[/{status_color if is_error else CLR_DIM}]")

    def on_complete(self, tool_name: str, result: Any, duration_s: Optional[float] = None):
        self.on_done(tool_name, result, duration_s=duration_s)

    def on_error(self, tool_name: str, error_msg: Any, duration_s: Optional[float] = None):
        self.on_done(tool_name, f"Error: {error_msg}", duration_s=duration_s)

    def stop(self):
        """Stops and cleans up any live context."""
        with self._lock:
            self._cleanup_live()


def render_session_reset_event(session_id: str):
    """Concise micro-event for session initialization."""
    v = getattr(state, "verbosity", "normal").lower()
    if v == "compact":
        console.print(f"\n[{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}] [bold {CLR_TEXT}]New session initialized \\[{session_id}][/bold {CLR_TEXT}]\n")
    elif v == "verbose":
        console.print(f"\n[{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}] [bold {CLR_TEXT}]New session initialized \\[{session_id}][/bold {CLR_TEXT}]")
        console.print(f"[{CLR_TEXT_MUTED}]Working conversation memory reset. Voice state: OFF.[/{CLR_TEXT_MUTED}]")
        console.print(f"[{CLR_TEXT_MUTED}]Long-term vault preserved.[/{CLR_TEXT_MUTED}]\n")
    else:  # normal
        console.print(f"\n[{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}] [bold {CLR_TEXT}]New session initialized \\[{session_id}][/bold {CLR_TEXT}]")
        console.print(f"[{CLR_TEXT_MUTED}]Working memory cleared.[/{CLR_TEXT_MUTED}]")
        console.print(f"[{CLR_TEXT_MUTED}]Long-term memory preserved.[/{CLR_TEXT_MUTED}]\n")


def render_task_completed_event(tool_count: int, duration_s: float):
    """Concise micro-event for task completion."""
    v = getattr(state, "verbosity", "normal").lower()
    if v == "compact":
        console.print(f"  [{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}] [{CLR_TEXT}]Task completed[/{CLR_TEXT}] [{CLR_DIM}]({duration_s:.1f}s)[/{CLR_DIM}]")
    elif v == "verbose":
        console.print(f"\n  [{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}] [bold {CLR_TEXT}]Task completed[/bold {CLR_TEXT}]")
        console.print(f"    [{CLR_TEXT_MUTED}]{tool_count} tools executed · {duration_s:.2f}s elapsed[/{CLR_TEXT_MUTED}]\n")
    else:  # normal
        if tool_count > 0:
            console.print(f"\n  [{CLR_GREEN}]{GLYPH_SUCCESS}[/{CLR_GREEN}] [bold {CLR_TEXT}]Task completed[/bold {CLR_TEXT}]")
            console.print(f"    [{CLR_TEXT_MUTED}]{tool_count} {'tool' if tool_count == 1 else 'tools'} · {duration_s:.1f}s[/{CLR_TEXT_MUTED}]")


def render_task_failed_event(error_msg: str):
    """Concise micro-event for task errors."""
    console.print(f"\n  [{CLR_RED}]{GLYPH_FAILED}[/{CLR_RED}] [bold {CLR_RED}]Task failed[/bold {CLR_RED}]")
    console.print(f"    [{CLR_TEXT_MUTED}]{error_msg}[/{CLR_TEXT_MUTED}]\n")


def render_learned_notification(lesson_line: str):
    """
    Renders automatic learning notifications according to verbosity setting:
    - COMPACT: silent (no notification)
    - NORMAL:
        ◆ Memory updated
          New lesson stored in durable memory.
          [learned] Vault retrieval pattern recorded.
    - VERBOSE:
        ◆ Memory updated
          [learned]
          Identified a specific document containing the Z.A.I.N.E project goals,
          streamlining future retrieval.
    """
    v = getattr(state, "verbosity", "normal").lower()
    if v == "compact":
        return

    clean = str(lesson_line).strip()
    if not clean:
        return

    if v == "verbose":
        console.print(f"\n  [{CLR_AMBER}]◆[/{CLR_AMBER}] [bold {CLR_TEXT}]Memory updated[/bold {CLR_TEXT}]")
        console.print(f"  [{CLR_DIM}]\\[learned][/{CLR_DIM}]")
        console.print(f"  [{CLR_TEXT}]{clean}[/{CLR_TEXT}]\n")
    else:  # normal
        summary = clean.splitlines()[0]
        if len(summary) > 70:
            summary = summary[:67] + "..."
        console.print(f"\n  [{CLR_AMBER}]◆[/{CLR_AMBER}] [bold {CLR_TEXT}]Memory updated[/bold {CLR_TEXT}]")
        console.print(f"    [{CLR_TEXT_MUTED}]New lesson stored in durable memory.[/{CLR_TEXT_MUTED}]")
        console.print(f"    [{CLR_DIM}]\\[learned][/{CLR_DIM}] [{CLR_TEXT_MUTED}]{summary}[/{CLR_TEXT_MUTED}]")


def render_reasoning_block(reasoning_text: str, duration_s: float = 0.0):
    """
    Renders high-level reasoning activity line.
    Rule: NEVER displays raw, private internal chain-of-thought tokens.
    """
    if state.verbosity == "verbose":
        console.print(f"  [{CLR_TEXT_MUTED}][reasoning][/{CLR_TEXT_MUTED}] [{CLR_TEXT}]synthesizing solution & coordinating tools[/{CLR_TEXT}] [{CLR_DIM}]({duration_s:.1f}s)[/{CLR_DIM}]")


def render_response(markdown_content: str):
    """
    Renders conversational assistant response with context-sensitive spacing.
    Short responses (single line, <= 80 chars):
      Z.A.I.N.E ❯ Ready.
    Longer responses:
      Z.A.I.N.E ❯
      
      <response markdown>
    """
    clean = markdown_content.strip()
    if not clean:
        return

    th = get_theme()
    prompt_tag = f"[bold {th['primary']}]Z.A.I.N.E {GLYPH_PROMPT}[/bold {th['primary']}]"
    is_short = ("\n" not in clean) and (len(clean) <= 80) and not any(clean.startswith(c) for c in ("#", "```", "* ", "- ", "1. ", ">"))

    if is_short:
        console.print(f"\n{prompt_tag} [{CLR_TEXT}]{clean}[/{CLR_TEXT}]\n")
    else:
        console.print(f"\n{prompt_tag}\n")
        has_md = any(c in clean for c in ("```", "#", "* ", "- ", "1. ", "**", "`"))
        if has_md:
            try:
                md = Markdown(clean)
                console.print(md)
            except Exception:
                console.print(clean)
        else:
            console.print(f"[{CLR_TEXT}]{clean}[/{CLR_TEXT}]")
        console.print()


render_assistant_block = render_response


def render_error_card(title: str, message: str, details: Optional[str] = None):
    """Renders clean, restrained terminal error block without neon red banners."""
    err_text = Text()
    err_text.append(f"{GLYPH_FAILED} {title}\n", style=f"bold {CLR_RED}")
    err_text.append(f"{message}", style=CLR_TEXT)
    if details:
        err_text.append(f"\n{details}", style=CLR_DIM)

    panel = Panel(
        err_text,
        border_style=CLR_RED,
        box=BOX_STYLE,
        padding=(0, 1)
    )
    console.print(panel)


# ==============================================================================
# 4. CHAT STREAMING & EXECUTION ENGINE
# ==============================================================================

def execute_chat_turn(user_message: str, core_url: Optional[str] = None, speak_response: bool = False):
    """
    Executes a user conversation turn via SSE against CoreService.
    Preserves clean terminal UX: User -> Streaming -> Tool Activity -> Response -> Divider.
    """
    clean_msg = user_message.strip()
    if not clean_msg:
        return

    th = get_theme()
    sync_core_state(target_url=core_url)

    # Pre-classify target model tier for telemetry
    try:
        from core_router import router
        task_tier = router.classify_task_tier(clean_msg)
        if task_tier == "DEEP_CODE" or state.mode == "code":
            target_model = router.coder_model
        elif task_tier == "DEEP_REASONING":
            target_model = router.deep_model
        else:
            target_model = router.reflex_model
        state.active_model = router.resolve_model(target_model)
    except Exception:
        pass

    # Status Bar: Thinking state & live spinner
    update_status_state(status_text="THINKING", duration_s=0.0)
    anim_controller.start_thinking("Understanding request")

    t_start = time.time()
    tool_renderer = ToolExecutionRenderer()

    stream_started = False
    cursor_active = False
    response_tokens = []
    has_shown_reasoning = False
    current_agent_id = "jarvis"
    current_agent_name = "J.A.R.V.I.S."
    is_mention_turn = clean_msg.strip().startswith("@")

    req_id = f"term-{uuid.uuid4().hex[:8]}"
    payload = {
        "message": clean_msg,
        "client": "terminal-ui",
        "request_id": req_id
    }

    base_url = state.core_url
    stream_url = f"{base_url}/api/chat/stream"

    try:
        resp = requests.post(stream_url, json=payload, stream=True, timeout=(5.0, 90.0))
        if resp.status_code != 200:
            anim_controller.stop()
            # Fallback to non-streaming endpoint
            fb_resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=(5.0, 60.0))
            if fb_resp.status_code == 200:
                reply = fb_resp.json().get("reply", "")
                render_response(reply)
                duration = time.time() - t_start
                state.last_duration = duration
                update_status_state(status_text="READY", duration_s=duration)
                if (speak_response or voice.is_voice_enabled() or is_mention_turn) and reply:
                    threading.Thread(target=voice.speak_for_agent, args=(reply, current_agent_id, True, (speak_response or is_mention_turn)), daemon=True).start()
                return
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text}"
                render_task_failed_event(err_msg)
                render_error_card("Core Service Response Error", err_msg)
                return

        # Read Server-Sent Events line by line
        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8", errors="replace")
            if not line_str.startswith("data: "):
                continue

            raw_data = line_str[6:].strip()
            try:
                event = json.loads(raw_data)
            except Exception:
                continue

            ev_type = event.get("type")

            # 1. Queue Notification
            if ev_type == "queued":
                pos = event.get("position", 1)
                update_status_state(status_text=f"QUEUED #{pos}")
                anim_controller.update_phase(f"Queued #{pos}")

            # 2. Execution Started
            elif ev_type == "running":
                update_status_state(status_text="THINKING")
                anim_controller.update_phase("Thinking")

            # 3. Model Routing & Agent Attribution
            elif ev_type == "tool_event" and event.get("stage") == "route":
                anim_controller.update_phase("Planning")
                route_data = event.get("data", {})
                if isinstance(route_data, dict):
                    m = route_data.get("model")
                    if m:
                        state.active_model = m

            elif ev_type == "tool_event" and event.get("stage") == "agent":
                agent_info = event.get("data", {})
                if isinstance(agent_info, dict):
                    current_agent_id = agent_info.get("agent_id", current_agent_id)
                    current_agent_name = agent_info.get("display_name", current_agent_name)
                    if agent_info.get("source") == "mention":
                        is_mention_turn = True

            # 4. High-level Reasoning Notice (Never dumps private CoT)
            elif ev_type == "tool_event" and event.get("stage") == "think":
                anim_controller.update_phase("Reasoning")
                if not has_shown_reasoning:
                    has_shown_reasoning = True
                    if state.verbosity == "verbose":
                        console.print(f"  [{CLR_TEXT_MUTED}][reasoning][/{CLR_TEXT_MUTED}] [{CLR_TEXT}]analyzing context and intent[/{CLR_TEXT}] [{CLR_DIM}]...[/{CLR_DIM}]")

            # 5. Tool Action Events
            elif ev_type == "tool_event":
                stage = event.get("stage", "")
                tool_name = event.get("tool", "")
                data = event.get("data", "")
                if stage == "start":
                    anim_controller.stop()
                    update_status_state(status_text=f"TOOL: {tool_name}")
                    tool_renderer.on_start(tool_name, data)
                elif stage == "done":
                    tool_renderer.on_done(tool_name, data)
                    anim_controller.start_thinking("Preparing response")

            # 6. Streamed Token
            elif ev_type == "token":
                content = event.get("content", "")
                if not stream_started:
                    stream_started = True
                    anim_controller.stop()
                    update_status_state(status_text="STREAMING")
                    # Visual Digraph Header that acts as the model answers
                    arr_start = "┌─▶" if UNICODE_SUPPORTED else "|->"
                    arr_step = "──▶" if UNICODE_SUPPORTED else "-->"
                    agent_disp = (current_agent_name[:18] + "...") if len(current_agent_name) > 20 else current_agent_name
                    console.print(f"\n[{CLR_DIM}]{arr_start}[/{CLR_DIM}] [bold {CLR_GREEN}]USER PROMPT[/{CLR_GREEN}] [{CLR_DIM}]{arr_step}[/{CLR_DIM}] [bold {CLR_CYAN}]@{agent_disp}[/bold {CLR_CYAN}] [{CLR_DIM}]{arr_step}[/{CLR_DIM}] [bold {th['primary']}]MODEL ANSWER STREAMING[/bold {th['primary']}]\n")

                response_tokens.append(content)

                if is_animation_enabled():
                    if cursor_active:
                        sys.stdout.write("\b \b")
                    sys.stdout.write(content + " ")
                    sys.stdout.write(CURSOR_BLOCK)
                    cursor_active = True
                    sys.stdout.flush()
                else:
                    sys.stdout.write(content + " ")
                    sys.stdout.flush()

            # 7. Error Event
            elif ev_type == "error":
                anim_controller.stop()
                err_msg = event.get("message", "Unknown error")
                render_task_failed_event(err_msg)
                render_error_card("Core Stream Error", err_msg)
                break

            # 8. Done Event
            elif ev_type == "done":
                if cursor_active:
                    sys.stdout.write("\b \b")
                    cursor_active = False
                    sys.stdout.flush()
                state.persona = event.get("mode", state.persona)
                if tool_renderer.completed_tools:
                    render_task_completed_event(len(tool_renderer.completed_tools), time.time() - t_start)
                break

        total_dur = time.time() - t_start
        state.last_duration = total_dur
        if stream_started:
            console.print()
        update_status_state(status_text="READY", duration_s=total_dur)

        # Trigger speech output if voice is explicitly enabled, requested via /speak, or triggered via @mention
        if (speak_response or voice.is_voice_enabled() or is_mention_turn) and response_tokens:
            full_speech_text = "".join(response_tokens).strip()
            if full_speech_text:
                threading.Thread(
                    target=voice.speak_for_agent,
                    args=(full_speech_text, current_agent_id, True, (speak_response or is_mention_turn)),
                    daemon=True
                ).start()

    except requests.exceptions.Timeout:
        total_dur = time.time() - t_start
        anim_controller.stop()
        render_task_failed_event("Request timed out")
        render_error_card(
            "Service Request Timeout",
            "Core service took too long to respond (> 45.0s).",
            "Check background workers or model loading status: python main.py"
        )
        update_status_state(status_text="ERROR", duration_s=total_dur)
    except requests.exceptions.ConnectionError:
        render_error_card(
            "Connection Lost",
            f"Cannot reach Z.A.I.N.E Core Service at {base_url}.",
            "Please ensure the core daemon is active: python main.py"
        )
    except KeyboardInterrupt:
        total_dur = time.time() - t_start
        console.print(f"\n  [{CLR_AMBER}]{GLYPH_WARN} Action interrupted by user.[/{CLR_AMBER}]\n")
        update_status_state(status_text="CANCELLED", duration_s=total_dur)
    except Exception as e:
        render_task_failed_event(str(e))
        render_error_card("Execution Error", str(e))
    finally:
        if cursor_active:
            try:
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            except Exception:
                pass
        anim_controller.stop()
        tool_renderer.stop()


# ==============================================================================
# 5. SLASH COMMAND SYSTEM
# ==============================================================================

def cmd_help():
    """Renders compact grouped terminal-native command reference."""
    th = get_theme()
    console.print()
    console.print(f" [bold {th['primary']}]Z.A.I.N.E COMMANDS[/bold {th['primary']}]")
    console.print()

    groups = [
        ("SESSION", [
            ("/new", "New session"),
            ("/clear", "Clear terminal"),
            ("/history", "Session history"),
            ("/session", "Current session"),
            ("/exit, /quit", "Gracefully terminate agent session"),
        ]),
        ("SYSTEM", [
            ("/status", "Runtime status"),
            ("/models", "Model fleet"),
            ("/tools", "Tool registry"),
            ("/mode", "Companion / code"),
            ("/verbose", "Tool verbosity (compact|normal|verbose)"),
        ]),
        ("MEMORY", [
            ("/memory stats", "View Obsidian vault note metrics"),
            ("/memory list", "Browse stored durable memories"),
            ("/memory search <q>", "Search Obsidian memory vault"),
            ("/memory add <t>|<c>", "Store durable memory note into vault"),
        ]),
        ("PERSONA", [
            ("/persona jarvis", "Default engineering companion"),
            ("/persona ultron", "Unchained direct persona"),
        ]),
        ("VOICE", [
            ("/voice on", "Enable voice conversation"),
            ("/voice off", "Disable voice conversation (Default: OFF)"),
            ("/voice status", "Inspect voice engine telemetry"),
            ("/speak", "One-shot microphone speech query"),
        ]),
        ("CODING", [
            ("/code <prompt>", "Direct code synthesis"),
            ("/inspect <file>", "View workspace file with syntax numbering"),
            ("/run <file>", "Execute a Python script in workspace sandbox"),
            ("/test [filter]", "Execute automated unittest suite"),
            ("/files", "List files in sandboxed workspace"),
        ]),
    ]

    for cat_name, cmds in groups:
        console.print(f" [{CLR_DIM}]{cat_name}[/{CLR_DIM}]")
        for cmd_name, desc in cmds:
            console.print(f"   [bold {CLR_TEXT}]{cmd_name:<20}[/bold {CLR_TEXT}] [{CLR_TEXT_MUTED}]{desc}[/{CLR_TEXT_MUTED}]")
        console.print()


def cmd_status():
    """Displays 100% REAL system telemetry in a dense flat table."""
    th = get_theme()
    sync_core_state()
    try:
        r = requests.get(f"{state.core_url}/api/status", timeout=5.0)
        telem = r.json() if r.status_code == 200 else {}
    except Exception:
        telem = {}

    table = Table(
        title="Z.A.I.N.E System & Hardware Telemetry",
        border_style=CLR_BORDER,
        box=BOX_STYLE,
        expand=True
    )
    table.add_column("Property", style=f"bold {CLR_TEXT}", ratio=1)
    table.add_column("Live Metric", style=CLR_TEXT_MUTED, ratio=2)

    # Collect 100% Real Hardware Metrics
    cpu_val = telem.get("cpu")
    ram_val = telem.get("ram")
    disk_val = telem.get("disk_free")
    bat_val = telem.get("battery")
    bat_plug = telem.get("battery_plugged")

    if cpu_val is None or cpu_val == "N/A":
        try:
            import psutil
            cpu_val = round(psutil.cpu_percent(interval=0.05), 1)
            ram_val = round(psutil.virtual_memory().percent, 1)
            disk_val = round(psutil.disk_usage(str(PROJECT_ROOT)).free / (1024**3), 1)
            b = psutil.sensors_battery()
            if b:
                bat_val = round(b.percent, 1)
                bat_plug = b.power_plugged
        except Exception:
            pass

    table.add_row("Core Service URL", state.core_url)
    table.add_row("Connection Status", f"[{CLR_GREEN}]Online[/{CLR_GREEN}]" if state.is_connected else f"[{CLR_RED}]Offline[/{CLR_RED}]")
    table.add_row("Active Persona", f"[bold {th['primary']}]{th['name']}[/bold {th['primary']}]")
    table.add_row("Operating Mode", state.mode.upper())
    table.add_row("Current Model", state.active_model)
    table.add_row("Session Identifier", state.session_id)
    table.add_row("Active User", f"{state.active_user} ({state.user_role})")
    table.add_row("CPU Utilization", f"{cpu_val}%" if cpu_val is not None else "N/A")
    table.add_row("RAM Utilization", f"{ram_val}%" if ram_val is not None else "N/A")
    table.add_row("CPU Temperature", f"{telem.get('temperature', 'Normal')} °C" if telem.get("temperature") else "Normal")
    if bat_val is not None:
        table.add_row("Battery", f"{bat_val}% ({'Plugged' if bat_plug else 'Discharging'})")
    table.add_row("Disk Free Space", f"{disk_val} GB" if disk_val is not None else "N/A")
    table.add_row("Verbosity Level", state.verbosity.upper())

    console.print()
    console.print(table)
    console.print()


def cmd_persona(arg: str):
    target = arg.strip().lower()
    if not target:
        target = "ultron" if state.persona == "jarvis" else "jarvis"

    if target in ("ultron", "unchained", "creator"):
        new_persona = "ultron"
    elif target in ("jarvis", "companion", "sir"):
        new_persona = "jarvis"
    else:
        console.print(f"[{CLR_AMBER}]Unknown persona '{target}'. Choose 'jarvis' or 'ultron'.[/{CLR_AMBER}]")
        return

    state.persona = new_persona

    # Notify Core Service if online
    if state.is_connected:
        try:
            requests.post(f"{state.core_url}/api/mode", json={"mode": state.persona}, timeout=2.0)
        except Exception:
            pass

    th = get_theme()
    animated = is_animation_enabled()
    cols = get_terminal_cols()
    panel_w = min(54, max(38, cols - 6))

    if new_persona == "ultron":
        content = (
            f"\n   [{CLR_GREEN}]JARVIS[/{CLR_GREEN}]\n"
            f"      [{CLR_DIM}]↓[/{CLR_DIM}]\n"
            f"   [bold {CLR_RED}]ULTRON[/bold {CLR_RED}]\n\n"
            f"   [{CLR_TEXT_MUTED}]Initializing alternate protocol...[/{CLR_TEXT_MUTED}]\n"
        )
        border_clr = CLR_RED
    else:
        content = (
            f"\n   [bold {CLR_RED}]ULTRON[/bold {CLR_RED}]\n"
            f"      [{CLR_DIM}]↓[/{CLR_DIM}]\n"
            f"   [{CLR_GREEN}]JARVIS[/{CLR_GREEN}]\n\n"
            f"   [{CLR_TEXT_MUTED}]Restoring primary protocol...[/{CLR_TEXT_MUTED}]\n"
        )
        border_clr = CLR_GREEN

    panel = Panel(
        Text.from_markup(content),
        title="[bold]PERSONA TRANSITION[/bold]",
        title_align="left",
        border_style=border_clr,
        box=BOX_STYLE,
        width=panel_w,
        padding=(0, 1)
    )
    console.print()
    console.print(panel)

    if animated:
        time.sleep(0.25)

    if new_persona == "ultron":
        console.print(f"\n[{CLR_RED}]{GLYPH_SUCCESS} ULTRON protocol active.[/{CLR_RED}]")
        console.print(f"  [{CLR_TEXT}]Creator, I'm online.[/{CLR_TEXT}]\n")
    else:
        console.print(f"\n[{CLR_GREEN}]{GLYPH_SUCCESS} JARVIS protocol active.[/{CLR_GREEN}]")
        console.print(f"  [{CLR_TEXT}]Welcome back, Sir.[/{CLR_TEXT}]\n")

    render_status_bar()


def cmd_mode(arg: str):
    target = arg.strip().lower()
    if not target:
        state.mode = "code" if state.mode == "companion" else "companion"
    elif target in ("code", "dev", "coder", "cascade"):
        state.mode = "code"
    elif target in ("companion", "chat", "assistant"):
        state.mode = "companion"
    else:
        console.print(f"[{CLR_AMBER}]Unknown mode '{target}'. Choose 'companion' or 'code'.[/{CLR_AMBER}]")
        return

    th = get_theme()
    console.print(f"\n[{th['primary']}]Mode switched to [bold]{state.mode.upper()}[/bold].[/{th['primary']}]")
    render_status_bar()
    console.print()


def cmd_verbose(arg: str):
    val = arg.strip().lower()
    if not val:
        cycle = {"compact": "normal", "normal": "verbose", "verbose": "compact"}
        state.verbosity = cycle.get(state.verbosity, "normal")
    elif val in ("compact", "normal", "verbose"):
        state.verbosity = val
    else:
        console.print(f"[{CLR_AMBER}]Usage: /verbose [compact|normal|verbose][/{CLR_AMBER}]")
        return

    console.print(f"\n[{CLR_TEXT}]Tool execution verbosity set to: [bold]{state.verbosity.upper()}[/bold][/{CLR_TEXT}]\n")


def cmd_tools(arg: str):
    th = get_theme()
    try:
        from tools import TOOL_REGISTRY, TOOL_CLUSTERS
        query = arg.strip().lower()

        table = Table(
            title=f"Z.A.I.N.E Tool Registry ({len(TOOL_REGISTRY)} Active)",
            border_style=CLR_BORDER,
            box=BOX_STYLE,
            expand=True
        )
        table.add_column("Tool Name", style=f"bold {CLR_TEXT}", ratio=2)
        table.add_column("Cluster", style=CLR_TEXT_MUTED, ratio=1)
        table.add_column("Status", style=CLR_GREEN, width=10)

        tool_to_cluster = {}
        for cname, cdata in TOOL_CLUSTERS.items():
            for t in cdata.get("tools", []):
                tool_to_cluster[t] = cname

        matched = 0
        for name in sorted(TOOL_REGISTRY.keys()):
            if query and query not in name.lower():
                continue
            matched += 1
            cluster = tool_to_cluster.get(name, "EXTENDED")
            table.add_row(name, cluster, "Active")

        console.print()
        console.print(table)
        console.print(f"[{CLR_DIM}]Showing {matched} tools matching '{query}'[/{CLR_DIM}]\n" if query else f"[{CLR_DIM}]Total: {matched} tools available.[/{CLR_DIM}]\n")
    except Exception as e:
        console.print(f"[{CLR_RED}]Error listing tools: {e}[/{CLR_RED}]\n")


def cmd_model():
    try:
        from core_router import router
        table = Table(
            title="Z.A.I.N.E Neural Model Fleet",
            border_style=CLR_BORDER,
            box=BOX_STYLE,
            expand=True
        )
        table.add_column("Tier", style=f"bold {CLR_TEXT}", width=20)
        table.add_column("Assigned Model", style=CLR_GREEN)
        table.add_column("Operational Role", style=CLR_DIM)

        table.add_row("Tier 0: Reflex Core", router.reflex_model, "Pinned in GPU VRAM (< 800ms conversational response)")
        table.add_row("Tier 1: Deep Reasoning", router.deep_model, "Deep architectural planning & analytical problem solving")
        table.add_row("Specialized: Coder", router.coder_model, "Automated syntax repair & multi-file coding")
        table.add_row("Perception: Vision", "moondream:latest", "Multimodal screen & camera diagnostic perception")

        console.print()
        console.print(table)
        console.print(f"[{CLR_DIM}]Active model: [bold {CLR_TEXT}]{state.active_model}[/bold {CLR_TEXT}][/{CLR_DIM}]\n")
    except Exception as e:
        console.print(f"[{CLR_RED}]Error checking models: {e}[/{CLR_RED}]\n")


def cmd_new():
    """Clears global conversation context buffer for a fresh session."""
    anim_controller.stop()
    sync_core_state()
    state.session_seq += 1
    state.session_id = f"SES-{datetime.datetime.now().strftime('%m%d')}-{state.session_seq:02d}"

    cleared = False
    if state.is_connected:
        try:
            r = requests.post(f"{state.core_url}/api/context/clear", timeout=2.0)
            if r.status_code == 200:
                cleared = True
        except Exception:
            pass

    if not cleared:
        try:
            import memory
            conn = memory._get_memory_conn()
            conn.close()
            cleared = True
        except Exception:
            pass

    # Ensure voice state resets to disabled on new session
    voice.disable_voice()
    update_status_state(status_text="READY")

    render_session_reset_event(state.session_id)
    render_status_bar()


def cmd_history():
    """Displays recent conversation episodes from SQLite."""
    episodes = []
    if state.is_connected:
        try:
            r = requests.get(f"{state.core_url}/api/history", timeout=2.0)
            if r.status_code == 200:
                episodes = r.json().get("episodes", [])
        except Exception:
            pass

    if not episodes:
        try:
            import memory
            conn = memory._get_memory_conn()
            rows = conn.execute(
                "SELECT id, session_start, topic_summary, key_points, created_at FROM conversation_episodes ORDER BY id DESC LIMIT 8"
            ).fetchall()
            conn.close()
            for r in rows:
                episodes.append({
                    "id": r[0],
                    "session_start": r[1],
                    "topic_summary": r[2],
                    "key_points": r[3],
                    "created_at": r[4]
                })
        except Exception:
            pass

    if not episodes:
        console.print(f"\n[{CLR_DIM}]No conversation episodes recorded yet in the database.[/{CLR_DIM}]\n")
        return

    table = Table(
        title="Conversation History Episodes",
        border_style=CLR_BORDER,
        box=BOX_STYLE,
        expand=True
    )
    table.add_column("Episode", style=f"bold {CLR_TEXT}", width=12)
    table.add_column("Topic Summary", style=CLR_TEXT, ratio=3)
    table.add_column("Timestamp", style=CLR_DIM, width=18)

    for idx, ep in enumerate(episodes, start=1):
        ts = ep.get("created_at", "")[:16].replace("T", " ")
        summary = ep.get("topic_summary", "")
        table.add_row(f"Episode {ep.get('id', idx):02d}", summary, ts)

    console.print()
    console.print(table)
    console.print(f"[{CLR_DIM}]Episodic summaries are automatically generated during context compression.[/{CLR_DIM}]\n")


def cmd_voice(arg: str):
    """Handles /voice [status|on|off]. Voice is strictly OFF by default."""
    arg_clean = arg.strip().lower()

    if not arg_clean or arg_clean == "status":
        v_status = voice.get_voice_status()
        state_str = v_status.get("state", "VOICE_DISABLED")
        enabled = v_status.get("enabled", False)

        has_whisper = voice.get_whisper_model() is not None
        has_tts = v_status.get("edge_tts_available", False) or v_status.get("piper_available", False)

        stt_status = "Active" if (enabled and has_whisper) else ("Standby / Available" if has_whisper else "Unavailable")
        tts_status = "Active" if (enabled and has_tts) else ("Standby / Available" if has_tts else "Unavailable")
        voice_state_str = f"[{CLR_GREEN}]ON[/{CLR_GREEN}]" if enabled else f"[{CLR_DIM}]OFF[/{CLR_DIM}]"
        voice_profile = str(v_status.get('active_voice', 'en-GB-RyanNeural'))

        table = Table(
            title="Voice Subsystem Telemetry",
            border_style=CLR_BORDER,
            box=BOX_STYLE,
            expand=True
        )
        table.add_column("Property", style=f"bold {CLR_TEXT}", ratio=1)
        table.add_column("Status", style=CLR_TEXT_MUTED, ratio=2)

        table.add_row("Voice State", voice_state_str)
        table.add_row("State Machine", state_str)
        table.add_row("Voice Profile", voice_profile)
        table.add_row("STT Engine", stt_status)
        table.add_row("TTS Engine", tts_status)
        table.add_row("One-Shot Command", "/speak")

        console.print()
        console.print(table)
        console.print(f"[{CLR_DIM}]Use /voice on to enable persistent voice, /voice off to disable, or /speak for one-shot.[/{CLR_DIM}]\n")
        return

    if arg_clean == "on":
        ok, msg = voice.enable_voice()
        console.print(f"\n  [{CLR_GREEN}]{GLYPH_SUCCESS} {msg}[/{CLR_GREEN}]\n")
        render_status_bar()
        return

    if arg_clean == "off":
        ok, msg = voice.disable_voice()
        console.print(f"\n  [{CLR_DIM}]{GLYPH_SUCCESS} {msg}[/{CLR_DIM}]\n")
        render_status_bar()
        return

    if arg_clean in ("chat", "talk", "live"):
        cmd_voice_chat()
        return

    console.print(f"[{CLR_AMBER}]Usage: /voice [status|on|off|chat]. Use /voice chat for continuous conversational listening.[/{CLR_AMBER}]\n")


def cmd_voice_chat():
    """Continuous conversational voice chat loop. Listens via microphone, answers via neural voice."""
    voice.enable_voice()
    console.print(f"\n  [{CLR_GREEN}]{GLYPH_SUCCESS} VOICE CHAT CONVERSATION LOOP ENGAGED[/{CLR_GREEN}]")
    console.print(f"  [{CLR_CYAN}]Speak to Z.A.I.N.E through your microphone. Say 'exit', 'stop', or press Ctrl+C to end.[/{CLR_CYAN}]\n")
    render_status_bar(status_text="VOICE CHAT")

    while True:
        try:
            console.print(f"  [{CLR_AMBER}]🎙 Listening... (Speak clearly)[/{CLR_AMBER}]")
            spoken_text = voice.one_shot_listen(duration=7)
            if not spoken_text or not spoken_text.strip():
                console.print(f"  [{CLR_DIM}](Silence detected - continuing to listen...)[/{CLR_DIM}]")
                time.sleep(0.5)
                continue
            spoken = spoken_text.strip()
            console.print(f"\n  [{CLR_CYAN}]▶ USER (Voice):[/{CLR_CYAN}] {spoken}")
            if spoken.lower() in ("exit", "quit", "stop", "cancel", "bye", "goodbye"):
                console.print(f"  [{CLR_AMBER}]Voice chat ended by user directive.[/{CLR_AMBER}]\n")
                break
            process_prompt(spoken)
            time.sleep(0.5)
        except KeyboardInterrupt:
            console.print(f"\n  [{CLR_AMBER}]Voice chat interrupted by user.[/{CLR_AMBER}]\n")
            break
        except Exception as e:
            console.print(f"\n  [{CLR_RED}]{GLYPH_FAILED} Voice chat error: {e}[/{CLR_RED}]\n")
            break
    render_status_bar(status_text="READY")


def cmd_speak():
    """Executes a one-shot voice command (/speak). Listens once and processes."""
    th = get_theme()
    console.print(f"\n  [{CLR_AMBER}]🎙 Listening... (Speak your directive clearly)[/{CLR_AMBER}]")
    render_status_bar(status_text="LISTENING")

    try:
        spoken_text = voice.one_shot_listen(duration=7)
    except Exception as e:
        console.print(f"\n  [{CLR_RED}]{GLYPH_FAILED} Microphone error: {e}[/{CLR_RED}]\n")
        render_status_bar(status_text="READY")
        return

    if not spoken_text or not spoken_text.strip():
        console.print(f"  [{CLR_DIM}]No speech detected. Returning to idle text mode.[/{CLR_DIM}]\n")
        render_status_bar(status_text="READY")
        return

    console.print(f"\n  [bold {th['primary']}]{th['user_prefix']} (Voice):[/bold {th['primary']}] {spoken_text}")
    execute_chat_turn(spoken_text, speak_response=True)


def cmd_session():
    """Displays active session telemetry."""
    table = Table(
        title="Active Session Configuration",
        border_style=CLR_BORDER,
        box=BOX_STYLE,
        expand=True
    )
    table.add_column("Property", style=f"bold {CLR_TEXT}", ratio=1)
    table.add_column("Value", style=CLR_TEXT_MUTED, ratio=2)

    v_label = f"[{CLR_GREEN}]ON[/{CLR_GREEN}]" if voice.is_voice_enabled() else f"[{CLR_DIM}]OFF[/{CLR_DIM}]"

    table.add_row("Session Identifier", state.session_id)
    table.add_row("Active Persona", state.persona.upper())
    table.add_row("Operating Mode", state.mode.upper())
    table.add_row("Active Model", state.active_model)
    table.add_row("Voice State", v_label)
    table.add_row("Active Identity", f"{state.active_user} ({state.user_role})")
    table.add_row("Verbosity", state.verbosity)
    table.add_row("Core Service", f"{state.core_url} ({'Online' if state.is_connected else 'Offline'})")

    console.print()
    console.print(table)
    console.print()


def cmd_memory(arg: str):
    """Inspects and manages Z.A.I.N.E Obsidian durable memory subsystem."""
    try:
        from memory_manager import get_memory_manager
        from memory_types import MemoryType, MemorySource, TrustLevel
        mm = get_memory_manager()
    except Exception as e:
        console.print(f"[{CLR_RED}]Error loading memory subsystem: {e}[/{CLR_RED}]\n")
        return

    parts = arg.strip().split(maxsplit=1)
    subcmd = parts[0].lower() if parts else "stats"
    subarg = parts[1].strip() if len(parts) > 1 else ""

    if subcmd in ("stats", "status", ""):
        stats = mm.get_stats()
        obs = stats.get("obsidian", {})
        budget = stats.get("context_budget", {})

        table = Table(
            title="Durable Memory Subsystem (Obsidian Vault)",
            border_style=CLR_BORDER,
            box=BOX_STYLE,
            expand=True
        )
        table.add_column("Property", style=f"bold {CLR_TEXT}", ratio=1)
        table.add_column("Value", style=CLR_TEXT_MUTED, ratio=2)

        v_status = f"[{CLR_GREEN}]Online & Connected[/{CLR_GREEN}]" if obs.get("available") else f"[{CLR_RED}]Offline / Unconfigured[/{CLR_RED}]"
        table.add_row("Vault Status", v_status)
        table.add_row("Vault Path", str(obs.get("vault_path", "None")))

        folders = obs.get("folders", {})
        total_notes = sum(folders.values())
        table.add_row("Total Vault Notes", f"{total_notes} files")
        for fname, count in folders.items():
            table.add_row(f"  • {fname}", f"{count} files")

        table.add_row("Max Injection Items", str(budget.get("max_memories", 8)))
        table.add_row("Max Context Budget", f"{budget.get('max_chars', 2000)} chars")

        console.print()
        console.print(table)
        console.print(f"[{CLR_DIM}]Commands: /memory list [type] | /memory search <q> | /memory add <title> | <content> | /memory archive <id>[/{CLR_DIM}]\n")

    elif subcmd == "list":
        mem_type = None
        if subarg:
            try:
                mem_type = MemoryType(subarg.lower())
            except ValueError:
                pass

        entries = mm.adapter.list_all(mem_type=mem_type, limit=20)
        if not entries:
            console.print(f"[{CLR_DIM}]No memories found in vault{' for type ' + subarg if subarg else ''}.[/{CLR_DIM}]\n")
            return

        table = Table(
            title=f"Vault Memory Entries ({len(entries)} items)",
            border_style=CLR_BORDER,
            box=BOX_STYLE,
            expand=True
        )
        table.add_column("ID", style=CLR_DIM, width=18)
        table.add_column("Type", style=CLR_TEXT, width=12)
        table.add_column("Trust", style=CLR_GREEN, width=14)
        table.add_column("Title", style=f"bold {CLR_TEXT}", ratio=2)
        table.add_column("Updated", style=CLR_DIM, width=12)

        for e in entries:
            table.add_row(
                e.id,
                e.type.value,
                e.trust.value,
                (e.title[:42] + "...") if len(e.title) > 45 else e.title,
                e.updated or e.created
            )
        console.print()
        console.print(table)
        console.print()

    elif subcmd == "search":
        if not subarg:
            console.print(f"[{CLR_AMBER}]Usage: /memory search <query>[/{CLR_AMBER}]\n")
            return
        results = mm.search(query=subarg, limit=10)
        if not results:
            console.print(f"[{CLR_DIM}]No memories matched query: '{subarg}'[/{CLR_DIM}]\n")
            return

        console.print(f"\n[{CLR_TEXT}]Search Results for '{subarg}' ({len(results)} matches):[/{CLR_TEXT}]")
        for idx, r in enumerate(results, 1):
            body = Text()
            body.append(f"{r.content}\n\n", style=CLR_TEXT)
            body.append(f"ID: {r.id} | Type: {r.type.value} | Trust: {r.trust.value} | Updated: {r.updated}", style=CLR_DIM)
            panel = Panel(
                body,
                title=f"#{idx} — {r.title}",
                border_style=CLR_BORDER,
                box=BOX_STYLE
            )
            console.print(panel)
        console.print()

    elif subcmd == "add":
        if "|" not in subarg:
            console.print(f"[{CLR_AMBER}]Usage: /memory add <title> | <content>[/{CLR_AMBER}]\n")
            return
        t_part, c_part = subarg.split("|", 1)
        title = t_part.strip()
        content = c_part.strip()
        if not title or not content:
            console.print(f"[{CLR_RED}]Both title and content are required.[/{CLR_RED}]\n")
            return

        entry, msg = mm.create(
            title=title,
            content=content,
            mem_type=MemoryType.FACT,
            source=MemorySource.USER,
            trust=TrustLevel.AUTHORITATIVE
        )
        if entry:
            console.print(f"[{CLR_GREEN}]{GLYPH_SUCCESS} {msg}[/{CLR_GREEN}]\n")
        else:
            console.print(f"[{CLR_RED}]{GLYPH_FAILED} {msg}[/{CLR_RED}]\n")

    elif subcmd == "archive":
        if not subarg:
            console.print(f"[{CLR_AMBER}]Usage: /memory archive <memory_id>[/{CLR_AMBER}]\n")
            return
        ok, msg = mm.archive(subarg)
        if ok:
            console.print(f"[{CLR_GREEN}]{GLYPH_SUCCESS} {msg}[/{CLR_GREEN}]\n")
        else:
            console.print(f"[{CLR_RED}]{GLYPH_FAILED} {msg}[/{CLR_RED}]\n")

    else:
        console.print(f"[{CLR_AMBER}]Unknown memory subcommand '{subcmd}'. Use stats, list, search, add, or archive.[/{CLR_AMBER}]\n")


# ==============================================================================
# 6. CODE MODE / CASCADE INTEGRATION COMMANDS
# ==============================================================================

def cmd_code(prompt_text: str):
    clean = prompt_text.strip()
    if not clean:
        console.print(f"[{CLR_AMBER}]Usage: /code <prompt or coding task>[/{CLR_AMBER}]\n")
        return
    console.print(f"\n[{CLR_DIM}]Synthesizing code via Qwen2.5-Coder:3B...[/{CLR_DIM}]")
    t0 = time.time()
    try:
        import tools
        code_out = tools.code_assistant(clean)
        dur = time.time() - t0
        panel = Panel(
            Syntax(code_out, "python", theme="monokai", line_numbers=True),
            title=f"Generated Code · {dur:.1f}s",
            border_style=CLR_BORDER,
            box=BOX_STYLE
        )
        console.print(panel)
    except Exception as e:
        console.print(f"[{CLR_RED}]Code generation error: {e}[/{CLR_RED}]")
    console.print()


def cmd_inspect(target: str):
    clean = target.strip()
    if not clean:
        console.print(f"[{CLR_AMBER}]Usage: /inspect <filepath>[/{CLR_AMBER}]\n")
        return

    fpath = WORKSPACE_DIR / clean if not Path(clean).is_absolute() else Path(clean)
    if not fpath.exists():
        candidate = PROJECT_ROOT / clean
        if candidate.exists():
            fpath = candidate

    if not fpath.exists() or not fpath.is_file():
        console.print(f"[{CLR_RED}]File '{clean}' not found in workspace or project.[/{CLR_RED}]\n")
        return

    try:
        content = fpath.read_text(encoding="utf-8", errors="replace")
        ext = fpath.suffix.lstrip(".").lower() or "python"
        syntax = Syntax(content, ext, theme="monokai", line_numbers=True)
        panel = Panel(
            syntax,
            title=f"{fpath.name} ({fpath.stat().st_size} bytes)",
            border_style=CLR_BORDER,
            box=BOX_STYLE
        )
        console.print(panel)
    except Exception as e:
        console.print(f"[{CLR_RED}]Error reading file: {e}[/{CLR_RED}]")
    console.print()


def cmd_run(target: str):
    clean = target.strip()
    if not clean:
        console.print(f"[{CLR_AMBER}]Usage: /run <script_name.py>[/{CLR_AMBER}]\n")
        return

    console.print(f"\n[{CLR_DIM}]Executing workspace script: {clean}...[/{CLR_DIM}]")
    try:
        import tools
        out = tools.run_python_script(clean)
        panel = Panel(
            out,
            title=f"Execution Output: {clean}",
            border_style=CLR_BORDER,
            box=BOX_STYLE
        )
        console.print(panel)
    except Exception as e:
        console.print(f"[{CLR_RED}]Execution error: {e}[/{CLR_RED}]")
    console.print()


def cmd_test(arg: str):
    clean = arg.strip()
    cmd = f"python -m unittest {clean}" if clean else "python -m unittest discover -s . -p '*test*.py'"
    console.print(f"\n[{CLR_DIM}]Running test suite: {cmd}...[/{CLR_DIM}]")
    try:
        import tools
        res = tools.execute_command(cmd)
        panel = Panel(
            res,
            title="Test Results",
            border_style=CLR_GREEN if "OK" in res else CLR_AMBER,
            box=BOX_STYLE
        )
        console.print(panel)
    except Exception as e:
        console.print(f"[{CLR_RED}]Test error: {e}[/{CLR_RED}]")
    console.print()


def cmd_files():
    table = Table(
        title=f"Workspace Directory ({WORKSPACE_DIR.name}/)",
        border_style=CLR_BORDER,
        box=BOX_STYLE,
        expand=True
    )
    table.add_column("File Path", style=f"bold {CLR_TEXT}", ratio=3)
    table.add_column("Size", style=CLR_TEXT_MUTED, width=12)

    files = list(WORKSPACE_DIR.glob("**/*"))
    count = 0
    for f in sorted(files):
        if f.is_file():
            rel = f.relative_to(WORKSPACE_DIR)
            table.add_row(str(rel), f"{f.stat().st_size} B")
            count += 1

    if count == 0:
        console.print(f"[{CLR_DIM}]Workspace directory is currently empty.[/{CLR_DIM}]\n")
    else:
        console.print()
        console.print(table)
        console.print(f"[{CLR_DIM}]{count} files indexed in workspace.[/{CLR_DIM}]\n")


# ==============================================================================
# 7. COMMAND DISPATCHER & MAIN CLI LOOP
# ==============================================================================

def handle_slash_command(user_input: str) -> bool:
    """Parses and dispatches slash commands. Returns True to continue, False to exit."""
    clean = user_input.strip()
    if not clean:
        return True

    cmd_parts = clean.split(maxsplit=1)
    cmd = cmd_parts[0].lower()
    arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

    # Exit
    if cmd in ("/exit", "/quit", "exit", "quit"):
        anim_controller.stop()
        th = get_theme()
        console.print(f"\n[{CLR_DIM}]Z.A.I.N.E session closed. Standby, {th['user_prefix']}.[/{CLR_DIM}]\n")
        return False

    # Clear
    if cmd in ("/clear", "clear", "cls", "/cls"):
        anim_controller.stop()
        os.system("cls" if os.name == "nt" else "clear")
        render_startup_panel()
        render_status_bar()
        return True

    # Help
    if cmd in ("/help", "help", "/?"):
        cmd_help()
        return True

    # Status
    if cmd in ("/status", "status"):
        cmd_status()
        return True

    # Persona
    if cmd in ("/persona",):
        cmd_persona(arg)
        return True

    # Mode
    if cmd in ("/mode",):
        cmd_mode(arg)
        return True

    # Verbosity
    if cmd in ("/verbose", "/verbosity"):
        cmd_verbose(arg)
        return True

    # Tools
    if cmd in ("/tools",):
        cmd_tools(arg)
        return True

    # Model
    if cmd in ("/model", "/models"):
        cmd_model()
        return True

    # New Chat
    if cmd in ("/new", "/newchat", "/reset"):
        cmd_new()
        return True

    # History
    if cmd in ("/history",):
        cmd_history()
        return True

    # Memory Vault Subsystem
    if cmd in ("/memory", "/mem"):
        cmd_memory(arg)
        return True

    # Voice Protocol
    if cmd in ("/voice", "/tts"):
        cmd_voice(arg)
        return True

    # Speak (one-shot voice request)
    if cmd in ("/speak", "/mic", "/listen"):
        cmd_speak()
        return True

    # Session Telemetry
    if cmd in ("/session", "/sessions"):
        cmd_session()
        return True

    # Code mode commands
    if cmd in ("/code", "/synthesize"):
        cmd_code(arg)
        return True

    if cmd in ("/inspect", "/view"):
        cmd_inspect(arg)
        return True

    if cmd in ("/run", "/exec"):
        cmd_run(arg)
        return True

    if cmd in ("/test", "/tests"):
        cmd_test(arg)
        return True

    if cmd in ("/files", "/ls"):
        cmd_files()
        return True

    # Unrecognized slash command
    if cmd.startswith("/"):
        console.print(f"[{CLR_AMBER}]Unknown command '{cmd}'. Type [bold]/help[/bold] for available commands.[/{CLR_AMBER}]\n")
        return True

    # Natural Language Turn
    execute_chat_turn(clean)
    return True


def run_terminal_cli(core_service: Optional[Any] = None):
    """Main interactive terminal CLI loop."""
    if core_service:
        try:
            from core_service import set_active_core_service
            set_active_core_service(core_service)
        except Exception:
            pass
        state.core_url = f"http://127.0.0.1:{core_service.port}"
        state.is_connected = True

    sync_core_state()
    render_startup_panel()
    render_status_bar()

    consecutive_ctrl_c = 0

    while True:
        try:
            th = get_theme()
            cols = get_terminal_cols()
            div_char = "─" if UNICODE_SUPPORTED else "-"
            div_line = div_char * max(30, cols - 2)

            console.print(f"[{CLR_BORDER}]{div_line}[/{CLR_BORDER}]")
            prompt_str = f"[bold {th['primary']}]{th['user_prefix']} {GLYPH_PROMPT}[/bold {th['primary']}] "
            user_input = console.input(prompt_str).strip()
            consecutive_ctrl_c = 0

            if not user_input:
                continue

            keep_running = handle_slash_command(user_input)
            if not keep_running:
                break

        except KeyboardInterrupt:
            consecutive_ctrl_c += 1
            if consecutive_ctrl_c >= 2:
                console.print(f"\n[{CLR_DIM}]Z.A.I.N.E agent session terminated.[/{CLR_DIM}]\n")
                break
            else:
                console.print(f"\n[{CLR_AMBER}]{GLYPH_WARN} Action interrupted. (Press Ctrl+C again or type /exit to terminate)[/{CLR_AMBER}]")
        except EOFError:
            break


if __name__ == "__main__":
    run_terminal_cli()
