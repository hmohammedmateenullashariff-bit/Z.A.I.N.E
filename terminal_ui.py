"""
Z.A.I.N.E — Professional Agent Terminal UI Engine
Inspired by modern agentic CLIs (Hermes Agent, Claude Code) with distinct Z.A.I.N.E identity.

Preserves:
- Unified Phase 2a core service connection (no duplicate ZaineAgent!)
- Jarvis / Ultron dual personas with live UI switching
- Model routing visibility (Reflex, Reasoning, Coder, Vision)
- Real-time streaming and tool execution tracking
- Collapsible reasoning and tool output
- Interactive slash commands and session management
"""

import os
import sys
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

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.box import ROUNDED, HEAVY, ASCII, DOUBLE, SQUARE

# Initialize Rich Console
console = Console(highlight=False)

# Detect Unicode Support
def supports_unicode() -> bool:
    try:
        encoding = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        return "utf" in encoding.lower()
    except Exception:
        return False

UNICODE_SUPPORTED = supports_unicode()
BOX_STYLE = ROUNDED if UNICODE_SUPPORTED else ASCII

# Glyphs
GLYPH_READY = "●" if UNICODE_SUPPORTED else "*"
GLYPH_RUNNING = "⟳" if UNICODE_SUPPORTED else ">"
GLYPH_SUCCESS = "✓" if UNICODE_SUPPORTED else "+"
GLYPH_FAILED = "✗" if UNICODE_SUPPORTED else "x"
GLYPH_REASONING = "▸" if UNICODE_SUPPORTED else ">"
GLYPH_REASONING_EXP = "▼" if UNICODE_SUPPORTED else "v"
GLYPH_LIGHTNING = "⚡" if UNICODE_SUPPORTED else "[!]"
GLYPH_GEAR = "⚙" if UNICODE_SUPPORTED else "[*]"
GLYPH_SEARCH = "🔎" if UNICODE_SUPPORTED else "[?]"
GLYPH_FOLDER = "📁" if UNICODE_SUPPORTED else "[#]"
GLYPH_WARN = "⚠" if UNICODE_SUPPORTED else "!"

# Theme Definitions
THEMES = {
    "jarvis": {
        "name": "JARVIS",
        "primary": "cyan",
        "secondary": "dodger_blue1",
        "accent": "bright_cyan",
        "border": "cyan",
        "dim": "grey62",
        "user_prefix": "Sir",
        "tag_bg": "on cyan",
    },
    "ultron": {
        "name": "ULTRON",
        "primary": "bright_red",
        "secondary": "dark_orange3",
        "accent": "red",
        "border": "bright_red",
        "dim": "grey54",
        "user_prefix": "Creator",
        "tag_bg": "on bright_red",
    }
}

class TerminalUIState:
    """Manages active presentation state for the Z.A.I.N.E terminal."""
    def __init__(self):
        self.mode = "companion"  # "companion" or "code"
        self.persona = "jarvis"  # "jarvis" or "ultron"
        self.verbosity = "normal"  # "compact", "normal", "verbose"
        self.active_model = "qwen2.5:3b"
        self.last_duration = 0.0
        self.core_url = "http://127.0.0.1:7860"
        self.is_connected = False
        self.active_user = "Mateen Sir"
        self.user_role = "ADMIN"
        self.current_status = "READY"
        self.cancel_requested = False

state = TerminalUIState()


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
        resp = requests.get(f"{url}/api/health", timeout=1.5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("ok", False), data
    except Exception:
        pass
    return False, {}


def sync_core_state(target_url: Optional[str] = None):
    """Syncs state (mode, user, status) from Core Service if reachable."""
    if target_url:
        state.core_url = target_url
    elif not state.core_url or state.core_url == "http://127.0.0.1:7860":
        state.core_url = get_core_service_url()

    online, _ = check_core_service_health(state.core_url)
    state.is_connected = online
    if online:
        try:
            r = requests.get(f"{state.core_url}/api/mode", timeout=1.0)
            if r.status_code == 200:
                core_mode = r.json().get("mode", "jarvis")
                state.persona = "ultron" if core_mode == "ultron" else "jarvis"
        except Exception:
            pass
        try:
            r = requests.get(f"{state.core_url}/api/lockscreen/status", timeout=1.0)
            if r.status_code == 200:
                usr = r.json().get("user", {})
                state.active_user = usr.get("name", "Mateen Sir")
                state.user_role = usr.get("role", "admin").upper()
        except Exception:
            pass


# ==============================================================================
# 2. STATUS BAR & BANNER RENDERING
# ==============================================================================

def get_theme() -> dict:
    return THEMES.get(state.persona, THEMES["jarvis"])


def render_status_bar(status_text: Optional[str] = None, duration_s: Optional[float] = None, tool_info: Optional[str] = None):
    """
    Renders the persistent compact status bar.
    Example:
    Z.A.I.N.E │ JARVIS │ qwen2.5:3b │ COMPANION │ ● READY │ 0.8s
    """
    th = get_theme()
    w = max(console.width, 60)
    
    st = status_text or state.current_status
    dur = duration_s if duration_s is not None else state.last_duration
    mode_str = state.mode.upper()
    
    # Status styling
    if "READY" in st:
        st_styled = f"[green]{GLYPH_READY} READY[/green]"
    elif "THINKING" in st:
        st_styled = f"[bright_cyan]{GLYPH_RUNNING} THINKING[/bright_cyan]"
    elif "STREAMING" in st:
        st_styled = f"[green]{GLYPH_REASONING} STREAMING[/green]"
    elif "TOOL" in st or tool_info:
        label = tool_info or st
        st_styled = f"[yellow]{GLYPH_GEAR} {label}[/yellow]"
    elif "QUEUED" in st:
        st_styled = f"[yellow]⏳ {st}[/yellow]"
    elif "ERROR" in st:
        st_styled = f"[red]{GLYPH_FAILED} {st}[/red]"
    elif "CANCELLED" in st:
        st_styled = f"[yellow]{GLYPH_WARN} CANCELLED[/yellow]"
    else:
        st_styled = f"[cyan]{st}[/cyan]"

    # Shorten for narrow terminals (< 80 columns)
    if w < 80:
        bar_text = f" [bold {th['primary']}]Z.A.I.N.E[/] │ [{th['accent']}]{th['name']}[/] │ {st_styled} │ [dim]{dur:.1f}s[/dim]"
    else:
        bar_text = (
            f" [bold {th['primary']}]Z.A.I.N.E[/] "
            f"│ [{th['accent']}]{th['name']}[/] "
            f"│ [white]{state.active_model}[/] "
            f"│ [dim]{mode_str}[/] "
            f"│ {st_styled} "
            f"│ [dim]{dur:.1f}s[/dim]"
        )

    panel = Panel(
        Text.from_markup(bar_text),
        border_style=th["border"],
        box=BOX_STYLE,
        padding=(0, 0),
        style="on black" if console.is_terminal else ""
    )
    console.print(panel)


def render_startup_panel():
    """
    Renders the dynamic Startup Capability Panel based on actual runtime state.
    Hermes reference layout with Z.A.I.N.E identity.
    """
    sync_core_state()
    th = get_theme()
    
    # Dynamic capabilities introspection
    total_tools = 119
    try:
        from tools import TOOL_REGISTRY
        total_tools = len(TOOL_REGISTRY)
    except Exception:
        pass

    # Model resolution
    reflex_m = "qwen2.5:3b"
    reason_m = "deepseek-r1:7b"
    coder_m = "qwen2.5-coder:3b"
    vision_m = "moondream"
    try:
        from core_router import router
        reflex_m = router.reflex_model
        reason_m = router.deep_model
        coder_m = router.coder_model
    except Exception:
        pass

    # Telegram status
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_status = "[green]Connected[/green]" if tg_token else "[dim]Offline[/dim]"

    conn_status = f"[green]● Online[/green] ({state.core_url})" if state.is_connected else f"[red]● Offline[/red] ({state.core_url})"

    w = max(console.width, 60)
    
    # Header
    title_text = Text()
    title_text.append("Z.A.I.N.E\n", style=f"bold {th['primary']}")
    title_text.append("AUTONOMOUS AGENTIC OPERATING ENVIRONMENT\n", style="dim white")

    # Table layout for two-column details
    table = Table.grid(padding=(0, 2), expand=True)
    table.add_column("Left", ratio=1)
    table.add_column("Right", ratio=1)

    left_text = Text()
    left_text.append("Brain Architecture\n", style=f"bold {th['accent']}")
    left_text.append(f"  Reflex       ", style="dim")
    left_text.append(f"{reflex_m}\n", style="white")
    left_text.append(f"  Reasoning    ", style="dim")
    left_text.append(f"{reason_m}\n", style="white")
    left_text.append(f"  Coding       ", style="dim")
    left_text.append(f"{coder_m}\n", style="white")
    left_text.append(f"  Vision       ", style="dim")
    left_text.append(f"{vision_m}\n", style="white")

    right_text = Text()
    right_text.append("Agent Capabilities\n", style=f"bold {th['accent']}")
    right_text.append(f"  Registered Tools  ", style="dim")
    right_text.append(f"{total_tools} active\n", style="bold green")
    right_text.append(f"  Personas          ", style="dim")
    right_text.append(f"Jarvis / Ultron\n", style="white")
    right_text.append(f"  Memory Engine     ", style="dim")
    right_text.append(f"SQLite FTS5 (Local)\n", style="white")
    right_text.append(f"  Telegram Gateway  ", style="dim")
    right_text.append_text(Text.from_markup(tg_status + "\n"))

    table.add_row(left_text, right_text)

    # Runtime footer
    runtime_text = Text()
    runtime_text.append("\nRuntime Status\n", style=f"bold {th['accent']}")
    runtime_text.append(f"  Core Service:  ", style="dim")
    runtime_text.append_text(Text.from_markup(f"{conn_status}   "))
    runtime_text.append(f"Active Identity: ", style="dim")
    runtime_text.append(f"{state.active_user} ({state.user_role})   ", style="bold white")
    runtime_text.append(f"Mode: ", style="dim")
    runtime_text.append(f"{state.mode.upper()}\n", style=f"bold {th['primary']}")

    content_group = Text()
    content_group.append_text(title_text)
    content_group.append("\n")

    panel = Panel(
        table,
        title=f"[bold {th['primary']}] Z.A.I.N.E // {th['name']} AGENT [/]",
        subtitle=f"[dim]Type [bold]/help[/bold] for command menu │ Press Ctrl+C to cancel action[/dim]",
        border_style=th["border"],
        box=BOX_STYLE,
        padding=(1, 2)
    )
    console.print(panel)


# ==============================================================================
# 3. REASONING, TOOL & RESPONSE RENDERERS
# ==============================================================================

def format_tool_args_summary(args: Any) -> str:
    """Creates a concise, clean one-line representation of tool arguments."""
    if not isinstance(args, dict):
        s = str(args).strip().replace("\n", " ")
        return s[:70] + "..." if len(s) > 70 else s
    parts = []
    for k, v in args.items():
        v_str = str(v).strip().replace("\n", " ")
        if len(v_str) > 40:
            v_str = v_str[:37] + "..."
        parts.append(f"{k}='{v_str}'")
    return ", ".join(parts)


class ToolExecutionRenderer:
    """
    Renders compact agent-style tool execution lines with execution timing,
    collapsing, and status glyphs.
    """
    def __init__(self):
        self.active_tools = {}

    def on_start(self, tool_name: str, args: Any):
        t0 = time.time()
        self.active_tools[tool_name] = {"start_time": t0, "args": args}
        th = get_theme()
        args_summary = format_tool_args_summary(args)
        
        # Tool glyph
        glyph = GLYPH_GEAR
        if "search" in tool_name or "find" in tool_name or "inspect" in tool_name:
            glyph = GLYPH_SEARCH
        elif "file" in tool_name or "workspace" in tool_name:
            glyph = GLYPH_FOLDER
        
        if state.verbosity == "compact":
            console.print(f"  [yellow]{glyph} {tool_name}[/yellow] [dim]running...[/dim]")
        else:
            console.print(f"  [yellow]{glyph} [bold]{tool_name}[/bold][/yellow]  [dim]{args_summary}[/dim]")

    def on_done(self, tool_name: str, result: Any):
        info = self.active_tools.pop(tool_name, None)
        dur = (time.time() - info["start_time"]) if info else 0.0
        th = get_theme()
        
        res_str = str(result).strip()
        is_error = any(m in res_str for m in ("Error:", "Traceback", "SyntaxError", "NameError", "exited with code"))
        
        glyph = GLYPH_FAILED if is_error else GLYPH_SUCCESS
        color = "red" if is_error else "green"

        if state.verbosity == "compact":
            console.print(f"  [{color}]{glyph} {tool_name}[/{color}] [dim]· {dur:.1f}s[/dim]")
        elif state.verbosity == "normal":
            # Show summary with first line preview
            lines = res_str.splitlines()
            preview = lines[0] if lines else ""
            if len(preview) > 85:
                preview = preview[:82] + "..."
            if len(lines) > 1:
                preview += f" [dim]({len(lines)} lines output)[/dim]"
            console.print(f"  [{color}]{glyph} [bold]{tool_name}[/bold][/{color}] [dim]· {dur:.1f}s[/dim]")
            if preview and not is_error:
                console.print(f"     [dim]↳ {preview}[/dim]")
            elif is_error:
                console.print(f"     [red]↳ {preview}[/red]")
        else:
            # Verbose: full expandable box
            console.print(f"  [{color}]{glyph} [bold]{tool_name}[/bold][/{color}] [dim]· {dur:.1f}s[/dim]")
            snippet = res_str[:600] + ("\n... [truncated]" if len(res_str) > 600 else "")
            box = Panel(
                snippet,
                title=f"Tool Output: {tool_name}",
                border_style="dim white",
                box=BOX_STYLE,
                padding=(0, 1)
            )
            console.print(box)


def render_reasoning_block(reasoning_text: str, duration_s: float = 0.0):
    """
    Renders agent reasoning/planning block cleanly.
    Collapsed by default or expanded if in verbose mode.
    """
    clean_text = reasoning_text.strip()
    if not clean_text:
        return
    th = get_theme()
    
    if state.verbosity == "compact":
        console.print(f"  [dim cyan]{GLYPH_REASONING} Reasoning · {duration_s:.1f}s[/dim cyan]")
    elif state.verbosity == "normal":
        # Compact single-box or two-line summary
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
        preview = lines[0] if lines else ""
        if len(lines) > 1:
            preview += f" [dim]({len(lines)} thoughts)[/dim]"
        console.print(f"  [cyan]{GLYPH_REASONING} [bold]Reasoning[/bold][/cyan] [dim]· {duration_s:.1f}s[/dim]")
        console.print(f"     [dim]{preview}[/dim]")
    else:
        # Verbose: full panel
        panel = Panel(
            clean_text,
            title=f"[cyan]{GLYPH_REASONING_EXP} Agent Reasoning · {duration_s:.1f}s[/cyan]",
            border_style="dim cyan",
            box=BOX_STYLE,
            padding=(0, 1)
        )
        console.print(panel)


def render_response(markdown_content: str):
    """Renders the final conversational response with rich formatting."""
    th = get_theme()
    clean = markdown_content.strip()
    if not clean:
        return
    
    console.print()
    # Check if content has markdown elements (headers, code blocks, bullet points)
    has_md = any(c in clean for c in ("```", "#", "* ", "- ", "1. ", "**"))
    if has_md:
        try:
            md = Markdown(clean)
            console.print(md)
        except Exception:
            console.print(clean)
    else:
        console.print(f"[white]{clean}[/white]")
    console.print()


def render_error_card(title: str, message: str, details: Optional[str] = None):
    """Renders a structured, non-catastrophic error panel."""
    th = get_theme()
    err_text = Text()
    err_text.append(f"{message}\n", style="bold red")
    if details:
        err_text.append(f"\nDetails:\n{details}", style="dim")
        
    panel = Panel(
        err_text,
        title=f"[red]{GLYPH_FAILED} {title}[/red]",
        border_style="red",
        box=BOX_STYLE,
        padding=(0, 2)
    )
    console.print(panel)


# ==============================================================================
# 4. CHAT STREAMING & EXECUTION ENGINE
# ==============================================================================

def execute_chat_turn(user_message: str, core_url: Optional[str] = None):
    """
    Executes a natural language user turn against the unified Core Service via SSE,
    rendering live reasoning, tools, and response.
    """
    clean_msg = user_message.strip()
    if not clean_msg:
        return

    th = get_theme()
    sync_core_state(target_url=core_url)

    # Pre-classify model routing
    task_tier = "REFLEX"
    target_model = state.active_model
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

    # Status Bar: Thinking
    render_status_bar(status_text="THINKING", duration_s=0.0)

    t_start = time.time()
    tool_renderer = ToolExecutionRenderer()
    
    reasoning_chunks = []
    response_tokens = []
    is_in_reasoning = False
    first_token_time = None
    stream_started = False

    req_id = f"term-{uuid.uuid4().hex[:8]}"
    payload = {
        "message": clean_msg,
        "client": "terminal-ui",
        "request_id": req_id
    }

    base_url = state.core_url
    stream_url = f"{base_url}/api/chat/stream"

    try:
        resp = requests.post(stream_url, json=payload, stream=True, timeout=180)
        if resp.status_code != 200:
            # Fallback to non-streaming endpoint
            fb_resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=90)
            if fb_resp.status_code == 200:
                reply = fb_resp.json().get("reply", "")
                render_response(reply)
                duration = time.time() - t_start
                state.last_duration = duration
                render_status_bar(status_text="READY", duration_s=duration)
                return
            else:
                render_error_card("Core Service Error", f"HTTP {resp.status_code}: {resp.text}")
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
                render_status_bar(status_text=f"QUEUED #{pos}")

            # 2. Execution Started
            elif ev_type == "running":
                waited = event.get("waited_seconds", 0)
                render_status_bar(status_text="THINKING")

            # 3. Model/Tier Routing Event
            elif ev_type == "tool_event" and event.get("stage") == "route":
                route_data = event.get("data", {})
                if isinstance(route_data, dict):
                    m = route_data.get("model")
                    if m:
                        state.active_model = m

            # 4. Reasoning/CoT Thinking Token
            elif ev_type == "tool_event" and event.get("stage") == "think":
                reasoning_chunks.append(str(event.get("data", "")))

            elif ev_type == "tool_event" and event.get("stage") == "think_done":
                full_reasoning = "".join(reasoning_chunks)
                r_dur = time.time() - t_start
                render_reasoning_block(full_reasoning, duration_s=r_dur)
                reasoning_chunks.clear()

            # 5. Tool Action Events
            elif ev_type == "tool_event":
                stage = event.get("stage", "")
                tool_name = event.get("tool", "")
                data = event.get("data", "")
                if stage == "start":
                    render_status_bar(status_text=f"TOOL: {tool_name}")
                    tool_renderer.on_start(tool_name, data)
                elif stage == "done":
                    tool_renderer.on_done(tool_name, data)

            # 6. Streamed Token / Sentence
            elif ev_type == "token":
                content = event.get("content", "")
                if not stream_started:
                    stream_started = True
                    first_token_time = time.time()
                    render_status_bar(status_text="STREAMING")
                    # If we had buffered reasoning, render it now
                    if reasoning_chunks:
                        r_dur = first_token_time - t_start
                        render_reasoning_block("".join(reasoning_chunks), duration_s=r_dur)
                        reasoning_chunks.clear()
                    console.print()

                response_tokens.append(content)
                # Print token cleanly
                sys.stdout.write(content + " ")
                sys.stdout.flush()

            # 7. Error Event
            elif ev_type == "error":
                render_error_card("Core Stream Error", event.get("message", "Unknown error"))
                break

            # 8. Done Event
            elif ev_type == "done":
                state.persona = event.get("mode", state.persona)
                break

        total_dur = time.time() - t_start
        state.last_duration = total_dur
        if stream_started:
            print("\n")
        render_status_bar(status_text="READY", duration_s=total_dur)

    except requests.exceptions.ConnectionError:
        render_error_card(
            "Connection Lost",
            f"Cannot reach Z.A.I.N.E Core Service at {base_url}.",
            "Please ensure the main server is running: python main.py"
        )
    except KeyboardInterrupt:
        total_dur = time.time() - t_start
        console.print(f"\n  [yellow]{GLYPH_WARN} Operation cancelled by user.[/yellow]\n")
        render_status_bar(status_text="CANCELLED", duration_s=total_dur)
    except Exception as e:
        render_error_card("Execution Exception", str(e))


# ==============================================================================
# 5. SLASH COMMAND SYSTEM
# ==============================================================================

def cmd_help():
    th = get_theme()
    table = Table(
        title=f"Z.A.I.N.E Agent Command Reference ({th['name']} Protocol)",
        border_style=th["border"],
        box=BOX_STYLE,
        show_header=True,
        header_style=f"bold {th['accent']}"
    )
    table.add_column("Command", style="bold white", width=22)
    table.add_column("Description", style="dim")
    table.add_column("Scope", style="cyan", width=14)

    # General Commands
    table.add_row("/help", "Show this interactive command menu", "Global")
    table.add_row("/mode [companion|code]", "Toggle or switch agent operation mode", "Global")
    table.add_row("/persona [jarvis|ultron]", "Switch active persona protocol", "Global")
    table.add_row("/status", "Display hardware telemetry & neural queue", "Global")
    table.add_row("/tools [filter]", "Inspect all 119+ registered agent tools", "Global")
    table.add_row("/model", "Inspect model tiers and Ollama models", "Global")
    table.add_row("/verbose [compact|normal|verbose]", "Set tool execution verbosity", "Global")
    table.add_row("/new", "Clear conversation memory buffer for new session", "Session")
    table.add_row("/history", "Browse summarized past session episodes", "Session")
    table.add_row("/clear", "Clear terminal screen and reprint banner", "Global")
    table.add_row("/exit, /quit", "Gracefully terminate agent session", "Global")

    # Coding / Cascade Commands
    table.add_row("/code <prompt>", "Direct synthesis via Qwen2.5-Coder", "Code Mode")
    table.add_row("/inspect <file>", "View workspace/project file with line numbers", "Code Mode")
    table.add_row("/run <file>", "Execute a Python script and capture output", "Code Mode")
    table.add_row("/test [pattern]", "Execute automated unittest suite", "Code Mode")
    table.add_row("/files", "List files in workspace and project", "Code Mode")

    console.print(table)
    console.print("[dim]Tip: You can also ask any question or give instructions in natural language.[/dim]\n")


def cmd_status():
    th = get_theme()
    sync_core_state()
    try:
        r = requests.get(f"{state.core_url}/api/status", timeout=2.0)
        telem = r.json() if r.status_code == 200 else {}
    except Exception:
        telem = {}

    table = Table(
        title="Z.A.I.N.E System & Hardware Telemetry",
        border_style=th["border"],
        box=BOX_STYLE
    )
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="cyan")

    table.add_row("Core Service URL", state.core_url)
    table.add_row("Connection Status", "[green]Online[/green]" if state.is_connected else "[red]Offline[/red]")
    table.add_row("Active Persona", f"[bold]{th['name']}[/bold]")
    table.add_row("Active Mode", state.mode.upper())
    table.add_row("Current Model", state.active_model)
    table.add_row("Active Identity", f"{state.active_user} ({state.user_role})")
    table.add_row("CPU Utilization", f"{telem.get('cpu', 'N/A')}%")
    table.add_row("RAM Utilization", f"{telem.get('ram', 'N/A')}%")
    table.add_row("CPU Temperature", f"{telem.get('temperature', 'N/A')} °C" if telem.get("temperature") else "Normal")
    table.add_row("Battery", f"{telem.get('battery', 100)}% ({'Plugged' if telem.get('battery_plugged') else 'Discharging'})")
    table.add_row("Free Disk Space", f"{telem.get('disk_free', 'N/A')} GB")
    table.add_row("Verbosity Level", state.verbosity.upper())

    console.print(table)
    console.print()


def cmd_persona(arg: str):
    target = arg.strip().lower()
    if not target:
        # Toggle
        target = "ultron" if state.persona == "jarvis" else "jarvis"
    
    if target in ("ultron", "unchained", "creator"):
        enable_ultron = True
        state.persona = "ultron"
    elif target in ("jarvis", "companion", "sir"):
        enable_ultron = False
        state.persona = "jarvis"
    else:
        console.print(f"[yellow]Unknown persona '{target}'. Choose 'jarvis' or 'ultron'.[/yellow]")
        return

    # Notify Core Service if online
    if state.is_connected:
        try:
            requests.post(f"{state.core_url}/api/mode", json={"mode": state.persona}, timeout=2.0)
        except Exception:
            pass

    th = get_theme()
    console.print(f"\n[{th['primary']}]{GLYPH_LIGHTNING} Persona switched to [bold]{th['name']}[/bold] protocol.[/{th['primary']}]")
    render_status_bar()
    console.print()


def cmd_mode(arg: str):
    target = arg.strip().lower()
    if not target:
        state.mode = "code" if state.mode == "companion" else "companion"
    elif target in ("code", "dev", "coder", "cascade"):
        state.mode = "code"
    elif target in ("companion", "chat", "assistant"):
        state.mode = "companion"
    else:
        console.print(f"[yellow]Unknown mode '{target}'. Choose 'companion' or 'code'.[/yellow]")
        return

    th = get_theme()
    console.print(f"\n[{th['accent']}]Mode switched to [bold]{state.mode.upper()}[/bold].[/{th['accent']}]")
    render_status_bar()
    console.print()


def cmd_verbose(arg: str):
    val = arg.strip().lower()
    if not val:
        # Cycle through: compact -> normal -> verbose -> compact
        cycle = {"compact": "normal", "normal": "verbose", "verbose": "compact"}
        state.verbosity = cycle.get(state.verbosity, "normal")
    elif val in ("compact", "normal", "verbose"):
        state.verbosity = val
    else:
        console.print("[yellow]Usage: /verbose [compact|normal|verbose][/yellow]")
        return

    console.print(f"\n[cyan]Tool execution verbosity set to: [bold]{state.verbosity.upper()}[/bold][/cyan]\n")


def cmd_tools(arg: str):
    th = get_theme()
    try:
        from tools import TOOL_REGISTRY, TOOL_CLUSTERS
        query = arg.strip().lower()
        
        table = Table(
            title=f"Z.A.I.N.E Registered Tools ({len(TOOL_REGISTRY)} active)",
            border_style=th["border"],
            box=BOX_STYLE
        )
        table.add_column("Tool Name", style="bold white", width=26)
        table.add_column("Cluster", style="cyan", width=18)
        table.add_column("Status", style="green", width=10)

        # Build cluster reverse lookup
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

        console.print(table)
        console.print(f"[dim]Showing {matched} tools matching '{query}'[/dim]\n" if query else f"[dim]Total: {matched} tools available.[/dim]\n")
    except Exception as e:
        console.print(f"[red]Error listing tools: {e}[/red]\n")


def cmd_model():
    th = get_theme()
    try:
        from core_router import router
        table = Table(
            title="Z.A.I.N.E Cognitive Brain Tiers & Router",
            border_style=th["border"],
            box=BOX_STYLE
        )
        table.add_column("Tier", style="bold white", width=18)
        table.add_column("Assigned Model", style="cyan")
        table.add_column("Role", style="dim")

        table.add_row("Tier 0: Reflex Core", router.reflex_model, "Pinned in GPU VRAM (< 800ms conversational speed)")
        table.add_row("Tier 1: Deep Reasoning", router.deep_model, "Deep architectural planning & chain-of-thought")
        table.add_row("Specialized: Coder", router.coder_model, "Automated syntax repair & multi-file coding")
        table.add_row("Perception: Vision", "moondream:latest", "Multimodal screen & camera inspection")

        console.print(table)
        console.print(f"[dim]Active session brain: [bold]{state.active_model}[/bold][/dim]\n")
    except Exception as e:
        console.print(f"[red]Error checking models: {e}[/red]\n")


def cmd_new():
    """Clears global conversation context buffer for a fresh session."""
    sync_core_state()
    th = get_theme()
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
            # Reset memory in process if available
            conn = memory._get_memory_conn()
            conn.close()
            cleared = True
        except Exception:
            pass

    console.print(f"\n[green]{GLYPH_SUCCESS} New chat session initialized.[/green]")
    console.print("[dim]Conversation working memory reset. Long-term vault & episodic archive preserved.[/dim]\n")
    render_status_bar()


def cmd_history():
    """Displays recent conversation episodes from SQLite."""
    th = get_theme()
    episodes = []
    
    # 1. Try Core HTTP API
    if state.is_connected:
        try:
            r = requests.get(f"{state.core_url}/api/history", timeout=2.0)
            if r.status_code == 200:
                episodes = r.json().get("episodes", [])
        except Exception:
            pass

    # 2. Local fallback
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
        console.print("\n[dim]No recent conversation episodes recorded yet in the archive.[/dim]\n")
        return

    table = Table(
        title="Recent Conversation Episodes & Memory Sessions",
        border_style=th["border"],
        box=BOX_STYLE
    )
    table.add_column("Session #", style="bold cyan", width=11)
    table.add_column("Summary", style="white")
    table.add_column("Recorded", style="dim", width=18)

    for idx, ep in enumerate(episodes, start=1):
        ts = ep.get("created_at", "")[:16].replace("T", " ")
        summary = ep.get("topic_summary", "")
        table.add_row(f"Episode {ep.get('id', idx):02d}", summary, ts)

    console.print(table)
    console.print("[dim]Z.A.I.N.E automatically synthesizes episodic memories when working context turns trim.[/dim]\n")


# ==============================================================================
# 6. CODE MODE / CASCADE INTEGRATION COMMANDS
# ==============================================================================

def cmd_code(prompt_text: str):
    clean = prompt_text.strip()
    if not clean:
        console.print("[yellow]Usage: /code <prompt or coding task>[/yellow]\n")
        return
    console.print(f"\n[magenta]⚡ [Synthesizing code via Qwen2.5-Coder:3B]...[/magenta]")
    t0 = time.time()
    try:
        import tools
        code_out = tools.code_assistant(clean)
        dur = time.time() - t0
        panel = Panel(
            Syntax(code_out, "python", theme="monokai", line_numbers=True),
            title=f"Generated Code · {dur:.1f}s",
            border_style="green",
            box=BOX_STYLE
        )
        console.print(panel)
    except Exception as e:
        console.print(f"[red]Code generation error: {e}[/red]")
    console.print()


def cmd_inspect(target: str):
    clean = target.strip()
    if not clean:
        console.print("[yellow]Usage: /inspect <filepath>[/yellow]\n")
        return

    fpath = WORKSPACE_DIR / clean if not Path(clean).is_absolute() else Path(clean)
    if not fpath.exists():
        candidate = PROJECT_ROOT / clean
        if candidate.exists():
            fpath = candidate

    if not fpath.exists() or not fpath.is_file():
        console.print(f"[red]File '{clean}' not found in workspace or project.[/red]\n")
        return

    try:
        content = fpath.read_text(encoding="utf-8", errors="replace")
        ext = fpath.suffix.lstrip(".").lower() or "python"
        syntax = Syntax(content, ext, theme="monokai", line_numbers=True)
        panel = Panel(
            syntax,
            title=f"Inspecting {fpath.name} ({fpath.stat().st_size} bytes)",
            border_style="yellow",
            box=BOX_STYLE
        )
        console.print(panel)
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
    console.print()


def cmd_run(target: str):
    clean = target.strip()
    if not clean:
        console.print("[yellow]Usage: /run <script_name.py>[/yellow]\n")
        return

    console.print(f"\n[cyan]⚙ Executing script: {clean}...[/cyan]")
    try:
        import tools
        out = tools.run_python_script(clean)
        panel = Panel(
            out,
            title=f"Script Output: {clean}",
            border_style="green",
            box=BOX_STYLE
        )
        console.print(panel)
    except Exception as e:
        console.print(f"[red]Execution error: {e}[/red]")
    console.print()


def cmd_test(arg: str):
    clean = arg.strip()
    cmd = f"python -m unittest {clean}" if clean else "python -m unittest discover -s . -p '*test*.py'"
    console.print(f"\n[cyan]⚙ Running automated tests: {cmd}...[/cyan]")
    try:
        import tools
        res = tools.execute_command(cmd)
        panel = Panel(
            res,
            title="Test Suite Results",
            border_style="green" if "OK" in res else "yellow",
            box=BOX_STYLE
        )
        console.print(panel)
    except Exception as e:
        console.print(f"[red]Test run error: {e}[/red]")
    console.print()


def cmd_files():
    th = get_theme()
    table = Table(
        title=f"Workspace Files ({WORKSPACE_DIR})",
        border_style=th["border"],
        box=BOX_STYLE
    )
    table.add_column("File / Path", style="bold white")
    table.add_column("Size", style="cyan", width=12)

    files = list(WORKSPACE_DIR.glob("**/*"))
    count = 0
    for f in sorted(files):
        if f.is_file():
            rel = f.relative_to(WORKSPACE_DIR)
            table.add_row(str(rel), f"{f.stat().st_size} B")
            count += 1

    if count == 0:
        console.print("[dim]Workspace directory is currently empty.[/dim]\n")
    else:
        console.print(table)
        console.print(f"[dim]{count} files in workspace.[/dim]\n")


# ==============================================================================
# 7. COMMAND DISPATCHER & MAIN LOOP
# ==============================================================================

def handle_slash_command(user_input: str) -> bool:
    """
    Parses and dispatches slash commands.
    Returns True to keep running, False to terminate session.
    """
    clean = user_input.strip()
    if not clean:
        return True

    cmd_parts = clean.split(maxsplit=1)
    cmd = cmd_parts[0].lower()
    arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

    # Exit
    if cmd in ("/exit", "/quit", "exit", "quit"):
        th = get_theme()
        prefix = th["user_prefix"]
        console.print(f"\n[{th['primary']}]Z.A.I.N.E session closed. Standby, {prefix}.[/{th['primary']}]\n")
        return False

    # Clear
    if cmd in ("/clear", "clear", "cls", "/cls"):
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
    if cmd in ("/persona", "/persona"):
        cmd_persona(arg)
        return True

    # Mode
    if cmd in ("/mode", "/mode"):
        cmd_mode(arg)
        return True

    # Verbosity
    if cmd in ("/verbose", "/verbosity"):
        cmd_verbose(arg)
        return True

    # Tools
    if cmd in ("/tools", "/tools"):
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
    if cmd in ("/history", "/sessions"):
        cmd_history()
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

    # If unrecognized slash command
    if cmd.startswith("/"):
        console.print(f"[yellow]Unknown command '{cmd}'. Type [bold]/help[/bold] for available commands.[/yellow]\n")
        return True

    # Natural Language Turn
    execute_chat_turn(clean)
    return True


def run_terminal_cli():
    """Main interactive terminal CLI loop."""
    sync_core_state()
    render_startup_panel()
    render_status_bar()

    consecutive_ctrl_c = 0

    while True:
        try:
            th = get_theme()
            prompt_str = f"\n[bold {th['primary']}]❯[/bold {th['primary']}] [dim]Ask Z.A.I.N.E anything...[/dim]\n[bold {th['secondary']}]❯[/bold {th['secondary']}] "
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
                console.print(f"\n[cyan]Z.A.I.N.E agent session terminated.[/cyan]\n")
                break
            else:
                console.print(f"\n[yellow]{GLYPH_WARN} Action interrupted. (Press Ctrl+C again or type /exit to terminate)[/yellow]")
        except EOFError:
            break


if __name__ == "__main__":
    run_terminal_cli()
