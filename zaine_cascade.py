"""
Z.A.I.N.E Cascade — Autonomous Coding Engine for VS Code
Designed to run directly inside VS Code's integrated terminal panel or as a standalone companion window.
Powered by Qwen2.5-Coder and Zaine Orchestrator:
- Multi-file code inspection, editing, and synthesis
- Autonomous test execution and traceback auto-debugging
- Real-time tool call streaming and diff tracking
"""

import os
import sys
from pathlib import Path

# Enable ANSI colors & UTF-8 output on Windows
if sys.platform == "win32":
    try:
        os.system("")  # Enables Virtual Terminal Processing in conhost/cmd
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

import json
import uuid
from typing import Any, Optional
import requests
import tools


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


def check_core_service_health(core_url: str = None) -> bool:
    """Checks if Z.A.I.N.E Core Service is online."""
    url = core_url or get_core_service_url()
    try:
        resp = requests.get(f"{url}/api/health", timeout=1.5)
        return resp.status_code == 200 and resp.json().get("ok", False)
    except Exception:
        return False

# ANSI Terminal Styling
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_banner():
    banner = f"""
{CYAN}{BOLD}+==================================================================+
|   [⚡] Z.A.I.N.E  C A S C A D E  —  V S  C O D E  E D I T I O N   |
|   Autonomous Pair Programming & Continuous Coding Engine         |
+==================================================================+{RESET}
{DIM}Workspace: {WORKSPACE_DIR}{RESET}
{DIM}Engines: Qwen2.5-7B (Reasoning) + Qwen2.5-Coder (Synthesis) | Local GPU{RESET}
{DIM}Commands: /code <prompt> | /inspect <file> | /run <file> | /test | /files | /exit{RESET}
"""
    print(banner)


def format_tool_args(args: dict) -> str:
    """Formats arguments cleanly for terminal display."""
    items = []
    for k, v in args.items():
        v_str = str(v)
        if len(v_str) > 60:
            v_str = v_str[:57] + "..."
        # Replace newlines
        v_str = v_str.replace("\n", "\\n")
        items.append(f"{k}='{v_str}'")
    return ", ".join(items)


def on_tool_event(stage: str, tool_name: str, data):
    """Real-time tool execution callback for interactive feedback."""
    if stage == "start":
        args_str = format_tool_args(data) if isinstance(data, dict) else str(data)
        print(f"\n{YELLOW}{BOLD}⚡ [CASCADE ACTION]{RESET} {YELLOW}Executing {tool_name}({args_str})...{RESET}")
    elif stage == "done":
        res_str = str(data).strip()
        lines = res_str.splitlines()
        preview = lines[0] if lines else ""
        if len(lines) > 1:
            preview += f" ... ({len(lines)} lines output)"
        if len(preview) > 100:
            preview = preview[:97] + "..."
        print(f"{GREEN}✓ [RESULT]{RESET} {DIM}{preview}{RESET}")


def handle_cascade_command(cmd_text: str, core_url: str = None, agent: Any = None) -> bool:
    clean = cmd_text.strip()
    if not clean:
        return True

    lower = clean.lower()

    # 1. Exit
    if lower in ("/exit", "exit", "quit", "/quit"):
        print(f"\n{CYAN}Zaine Cascade closing. Standby, Sir.{RESET}\n")
        return False

    # 2. Clear
    if lower in ("/clear", "clear", "cls", "/cls"):
        os.system("cls" if os.name == "nt" else "clear")
        print_banner()
        return True

    # 3. Help
    if lower in ("/help", "help", "/?"):
        print(f"""
{BOLD}{CYAN}=== Zaine Cascade Command Reference ==={RESET}
  {BOLD}/code <prompt>{RESET}     Fast direct code generation using Qwen2.5-Coder:3B
  {BOLD}/inspect <file>{RESET}    Inspect a source file with numbered lines
  {BOLD}/run <file>{RESET}        Execute a Python file in workspace/ and capture output
  {BOLD}/test [file]{RESET}       Run automated pytest/unittest on the workspace
  {BOLD}/files{RESET}             List all files in workspace/ and project
  {BOLD}/clear{RESET}             Clear terminal screen
  {BOLD}/exit{RESET}              Exit Zaine Cascade session
  {DIM}Or simply type any instruction in natural language (e.g., 'Refactor demo.py to support float').{RESET}
""")
        return True

    # 4. List Files
    if lower in ("/files", "files", "/ls", "ls"):
        print(f"\n{CYAN}[Workspace Files in {WORKSPACE_DIR}]:{RESET}")
        ws_files = list(WORKSPACE_DIR.glob("**/*"))
        if not ws_files:
            print(f"{DIM}  (Workspace directory is currently empty){RESET}")
        else:
            for f in sorted(ws_files):
                if f.is_file():
                    rel = f.relative_to(WORKSPACE_DIR)
                    print(f"  {CYAN}* {rel}{RESET} ({f.stat().st_size} bytes)")
        print()
        return True

    # 5. Inspect File
    if lower.startswith("/inspect ") or lower.startswith("/view "):
        target = clean.split(maxsplit=1)[1].strip()
        fpath = WORKSPACE_DIR / target if not Path(target).is_absolute() else Path(target)
        if not fpath.exists():
            candidate = PROJECT_ROOT / target
            if candidate.exists():
                fpath = candidate

        if fpath.exists() and fpath.is_file():
            print(f"\n{YELLOW}--- Inspecting {fpath.name} ({fpath.stat().st_size} bytes) ---{RESET}")
            content = fpath.read_text(encoding="utf-8", errors="replace")
            for idx, line in enumerate(content.splitlines(), start=1):
                print(f"{DIM}{idx:4d} |{RESET} {line}")
            print(f"{YELLOW}--- End of File: {fpath.name} ---{RESET}\n")
        else:
            print(f"{RED}File '{target}' not found in workspace or project root.{RESET}\n")
        return True

    # 6. Run Script
    if lower.startswith("/run "):
        target = clean.split(maxsplit=1)[1].strip()
        print(f"\n{CYAN}[Running script: {target}]...{RESET}")
        out = tools.run_python_script(target)
        print(f"{GREEN}Output:{RESET}\n{out}\n")
        return True

    # 7. Fast Direct Code Generation (/code)
    if lower.startswith("/code "):
        code_prompt = clean.split(maxsplit=1)[1].strip()
        print(f"\n{MAGENTA}[Generating code via Qwen2.5-Coder:3B]...{RESET}")
        code_out = tools.code_assistant(code_prompt)
        print(f"\n{BOLD}{GREEN}=== Generated Code ==={RESET}")
        print(code_out)
        print(f"{BOLD}{GREEN}======================{RESET}\n")
        return True

    # 8. Run Tests
    if lower == "/test" or lower.startswith("/test "):
        arg = clean.split(maxsplit=1)[1].strip() if " " in clean else ""
        cmd = f"python -m unittest {arg}" if arg else "python -m unittest discover -s . -p '*test*.py'"
        print(f"\n{CYAN}[Running test suite: {cmd}]...{RESET}")
        res = tools.execute_command(cmd)
        print(f"{GREEN}Test Results:{RESET}\n{res}\n")
        return True

    # 9. Natural Language Pair Programming (Full Agent Orchestration with Live Feedback)
    print(f"\n{CYAN}[Zaine Cascade thinking & synthesizing...]...{RESET}")
    if agent is not None:
        try:
            print(f"\n{BOLD}{CYAN}Zaine Cascade:{RESET} ", end="", flush=True)
            for sentence in agent.chat_stream(clean, on_tool_event=on_tool_event):
                sys.stdout.write(sentence + " ")
                sys.stdout.flush()
            print("\n")
        except Exception as e:
            print(f"\n{RED}Error in Cascade execution: {e}{RESET}\n")
        return True

    # Thin Client: Stream response from core HTTP service
    base_url = core_url or get_core_service_url()
    stream_url = f"{base_url}/api/chat/stream"
    req_id = f"casc-{uuid.uuid4().hex[:8]}"
    payload = {
        "message": clean,
        "client": "cascade",
        "request_id": req_id
    }

    try:
        print(f"\n{BOLD}{CYAN}Zaine Cascade:{RESET} ", end="", flush=True)
        resp = requests.post(stream_url, json=payload, stream=True, timeout=120)
        if resp.status_code == 200:
            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8", errors="replace")
                if line_str.startswith("data: "):
                    raw_data = line_str[6:].strip()
                    try:
                        event = json.loads(raw_data)
                        ev_type = event.get("type")
                        if ev_type == "queued":
                            pos = event.get("position", 1)
                            print(f"\n{YELLOW}[Core Busy: Request queued at position #{pos}. Waiting for turn...]{RESET}", flush=True)
                        elif ev_type == "running":
                            waited = event.get("waited_seconds", 0)
                            if waited > 0:
                                print(f"\n{GREEN}[Turn started after {waited:.1f}s queue wait: Generating response...]{RESET}\n", flush=True)
                        elif ev_type == "tool_event":
                            on_tool_event(event.get("stage", ""), event.get("tool", ""), event.get("data", ""))
                        elif ev_type == "token":
                            sys.stdout.write(event.get("content", "") + " ")
                            sys.stdout.flush()
                        elif ev_type == "error":
                            print(f"\n{RED}Error from core: {event.get('message')}{RESET}")
                        elif ev_type == "done":
                            break
                    except Exception:
                        pass
            print("\n")
        else:
            # Fallback to non-streaming /api/chat
            fb_url = f"{base_url}/api/chat"
            fb_resp = requests.post(fb_url, json=payload, timeout=90)
            if fb_resp.status_code == 200:
                reply = fb_resp.json().get("reply", "")
                print(f"{reply}\n")
            else:
                print(f"\n{RED}Error from core ({fb_resp.status_code}): {fb_resp.text}{RESET}\n")
    except requests.exceptions.ConnectionError:
        print(f"\n{RED}[!] Connection to Z.A.I.N.E Core lost. Please verify main.py is running.{RESET}\n")
    except Exception as e:
        print(f"\n{RED}Error in Cascade execution: {e}{RESET}\n")

    return True


def run_cascade_cli():
    try:
        from terminal_ui import run_terminal_cli, state
        state.mode = "code"
        run_terminal_cli()
        return
    except Exception:
        pass

    print_banner()
    core_url = get_core_service_url()
    if not check_core_service_health(core_url):
        print(f"{RED}{BOLD}[!] Z.A.I.N.E Core Service is offline at {core_url}.{RESET}")
        print(f"{YELLOW}Zaine Cascade operates as a thin client connected to the unified cognitive core.{RESET}")
        print(f"{YELLOW}Please launch Zaine first via: python main.py{RESET}\n")
        return

    print(f"{GREEN}✓ Connected to Z.A.I.N.E Core Service ({core_url}){RESET}\n")
    while True:
        try:
            user_input = input(f"{CYAN}{BOLD}ZAINE CASCADE //>{RESET} ")
            keep_running = handle_cascade_command(user_input, core_url=core_url)
            if not keep_running:
                break
        except (KeyboardInterrupt, EOFError):
            print(f"\n{CYAN}Zaine Cascade stopped.{RESET}\n")
            break


if __name__ == "__main__":
    run_cascade_cli()
