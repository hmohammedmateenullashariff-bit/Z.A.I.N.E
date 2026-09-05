"""
Z.A.I.N.E Agent v1 — Tools
Daily task management (SQLite) + datetime helper.
"""

import os
import sqlite3
import datetime
from pathlib import Path
try:
    import pyautogui
    pyautogui.FAILSAFE = False
except Exception:
    pass

import re

DB_PATH = Path(__file__).parent / "zaine_tasks.db"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            due TEXT,
            done INTEGER DEFAULT 0,
            category TEXT DEFAULT 'General',
            priority TEXT DEFAULT 'Medium',
            created_at TEXT
        )
        """
    )
    # Ensure category and priority columns exist for existing databases
    try:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        if "category" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN category TEXT DEFAULT 'General'")
        if "priority" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'Medium'")
        conn.commit()
    except Exception:
        pass

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            triggered INTEGER DEFAULT 0,
            created_at TEXT
        )
        """
    )
    return conn



def _parse_remind_time(time_str: str) -> datetime.datetime:
    """Parses relative ('in 15 mins', 'in 2 hours') or absolute ('18:30', '7:00 pm') time strings."""
    now = datetime.datetime.now()
    t = time_str.strip().lower()

    # Relative time matching
    m_hr = re.search(r'(\d+)\s*(?:hours?|hrs?|h\b)', t)
    m_min = re.search(r'(\d+)\s*(?:minutes?|mins?|m\b)', t)
    m_sec = re.search(r'(\d+)\s*(?:seconds?|secs?|s\b)', t)

    added_seconds = 0
    matched_relative = False
    if m_hr:
        added_seconds += int(m_hr.group(1)) * 3600
        matched_relative = True
    if m_min:
        added_seconds += int(m_min.group(1)) * 60
        matched_relative = True
    if m_sec:
        added_seconds += int(m_sec.group(1))
        matched_relative = True

    if matched_relative:
        return now + datetime.timedelta(seconds=added_seconds)

    # Absolute time matching (e.g. 18:30, 6:30 pm, 7:00am)
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"):
        try:
            parsed = datetime.datetime.strptime(t.replace(".", "").upper(), fmt)
            target = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
            if target < now:
                target += datetime.timedelta(days=1)
            return target
        except Exception:
            pass

    # Default fallback: 15 minutes from now
    return now + datetime.timedelta(minutes=15)


def set_reminder(message: str, time_str: str = "in 15 minutes") -> str:
    """
    Sets a proactive reminder.
    `time_str` can be relative ('in 20 minutes', 'in 1 hour', 'in 30 seconds') or specific ('18:30', '7:00 PM').
    """
    target_dt = _parse_remind_time(time_str)
    remind_at_iso = target_dt.isoformat()
    now_iso = datetime.datetime.now().isoformat()

    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO reminders (message, remind_at, triggered, created_at) VALUES (?, ?, 0, ?)",
        (message.strip(), remind_at_iso, now_iso),
    )
    conn.commit()
    rem_id = cur.lastrowid
    conn.close()

    time_disp = target_dt.strftime("%I:%M %p (%Y-%m-%d)")
    return f"Reminder set [ID={rem_id}]: '{message}' scheduled for {time_disp}."


def list_reminders(show_triggered: bool = False) -> str:
    """Lists scheduled reminders."""
    conn = _get_conn()
    if show_triggered:
        rows = conn.execute("SELECT id, message, remind_at, triggered FROM reminders ORDER BY remind_at").fetchall()
    else:
        rows = conn.execute("SELECT id, message, remind_at, triggered FROM reminders WHERE triggered=0 ORDER BY remind_at").fetchall()
    conn.close()

    if not rows:
        return "No scheduled reminders found."

    lines = ["Scheduled Reminders:"]
    for rid, msg, r_at, trig in rows:
        try:
            dt = datetime.datetime.fromisoformat(r_at)
            t_str = dt.strftime("%I:%M %p, %b %d")
        except Exception:
            t_str = r_at
        status = "🔔 Pending" if not trig else "✅ Triggered"
        lines.append(f"- [ID={rid}] {status} at {t_str}: {msg}")

    return "\n".join(lines)


def get_due_reminders() -> list:
    """Internal helper used by Heartbeat daemon to fetch reminders that are due right now."""
    now_iso = datetime.datetime.now().isoformat()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, message, remind_at FROM reminders WHERE triggered=0 AND remind_at <= ?",
        (now_iso,),
    ).fetchall()
    conn.close()
    return [{"id": r[0], "message": r[1], "remind_at": r[2]} for r in rows]


def mark_reminder_triggered(reminder_id: int):
    """Marks a reminder as delivered."""
    conn = _get_conn()
    conn.execute("UPDATE reminders SET triggered=1 WHERE id=?", (reminder_id,))
    conn.commit()
    conn.close()


def add_task(description: str, due: str = "", category: str = "General", priority: str = "Medium") -> str:
    """
    Add a new task with optional due date/time, category (e.g. 'Coding', 'Work', 'Personal', 'Study'),
    and priority ('High', 'Medium', 'Low').
    """
    cat_clean = category.strip().capitalize() if category.strip() else "General"
    prio_clean = priority.strip().capitalize() if priority.strip() else "Medium"
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO tasks (description, due, category, priority, created_at) VALUES (?, ?, ?, ?, ?)",
        (description.strip(), due.strip(), cat_clean, prio_clean, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    task_id = cur.lastrowid
    conn.close()

    details = []
    if cat_clean.lower() != "general":
        details.append(f"category: {cat_clean}")
    if prio_clean.lower() != "medium":
        details.append(f"priority: {prio_clean}")
    if due.strip():
        details.append(f"due: {due.strip()}")
    meta = f" [{', '.join(details)}]" if details else ""
    return f"Task added [ID={task_id}]: {description}{meta}"


def list_tasks(category: str = "", show_done: bool = False) -> str:
    """
    List tasks. Can filter by category (e.g. 'Coding', 'Work', 'Personal').
    By default only shows pending (not-done) tasks.
    """
    conn = _get_conn()
    query = "SELECT id, description, due, done, category, priority FROM tasks"
    conditions = []
    params = []

    if not show_done:
        conditions.append("done = 0")
    if category.strip():
        conditions.append("LOWER(category) = LOWER(?)")
        params.append(category.strip())

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        cat_suffix = f" in category '{category}'" if category else ""
        return f"No tasks found{cat_suffix}."

    lines = [f"Tasks ({len(rows)} item{'s' if len(rows) > 1 else ''}):"]
    for tid, desc, due, done, cat, prio in rows:
        status = "✅" if done else "⏳"
        badges = []
        if cat and cat.lower() != "general":
            badges.append(f"📂 {cat}")
        if prio and prio.lower() == "high":
            badges.append("🔥 High")
        elif prio and prio.lower() == "low":
            badges.append("💤 Low")
        if due:
            badges.append(f"⏰ Due: {due}")
        badge_str = f" ({', '.join(badges)})" if badges else ""
        lines.append(f"{status} [{tid}] {desc}{badge_str}")
    return "\n".join(lines)



def complete_task(task_id: int) -> str:
    """Mark a task as done by its id."""
    conn = _get_conn()
    cur = conn.execute("UPDATE tasks SET done=1 WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return f"No task found with id={task_id}"
    return f"Task {task_id} marked as done."


def delete_task(task_id: int) -> str:
    """Delete a task by its id."""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return f"No task found with id={task_id}"
    return f"Task {task_id} deleted."


def get_datetime() -> str:
    """Return the current date and time, and day of week."""
    now = datetime.datetime.now()
    return now.strftime("%A, %Y-%m-%d %H:%M")


def search_web(query: str) -> str:
    """Searches Wikipedia and online sources for real-time knowledge, facts, people, or definitions."""
    import re
    import html
    import requests

    query = query.strip()
    if not query:
        return "Error: query cannot be empty."

    # 1. Try DuckDuckGo Instant Answer API first
    try:
        ddg_url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json"
        r = requests.get(ddg_url, headers={"User-Agent": "ZaineAssistant/1.0"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            abstract = data.get("AbstractText", "")
            if abstract:
                return f"[Web Summary]: {abstract}"
            related = data.get("RelatedTopics", [])
            if related and isinstance(related[0], dict) and "Text" in related[0]:
                return f"[Web Summary]: {related[0]['Text']}"
    except Exception:
        pass

    # 2. Fallback to Wikipedia Search API
    try:
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={requests.utils.quote(query)}&format=json&utf8="
        r = requests.get(wiki_url, headers={"User-Agent": "ZaineAssistant/1.0"}, timeout=6)
        if r.status_code == 200:
            data = r.json()
            items = data.get("query", {}).get("search", [])
            if items:
                top = items[0]
                title = top.get("title", "")
                snippet = html.unescape(re.sub(r"<[^<]+?>", "", top.get("snippet", "")))
                return f"[Wikipedia - {title}]: {snippet}"
    except Exception as e:
        return f"Error searching the web: {e}"

    return f"No online information found for '{query}'."


def remember(key: str, value: str) -> str:
    """Saves a permanent fact or user preference to long-term memory."""
    from memory import save_memory
    return save_memory(key, value)


def recall(query: str = "") -> str:
    """Recalls saved facts or user preferences from long-term memory."""
    from memory import get_memory, get_all_memories
    if not query:
        mems = get_all_memories()
        if not mems:
            return "No persistent memories saved yet."
        return "\n".join(f"- {k}: {v}" for k, v in mems.items())
    return get_memory(query)


def learn_lesson(lesson: str, keywords: str = "") -> str:
    """Saves an acquired skill, coding pattern, bug fix, or user preference to episodic memory so it is remembered in future tasks."""
    from memory import record_task_learning
    if not keywords:
        keywords = " ".join(lesson.split()[:6])
    return record_task_learning(task_summary="Self-Acquired Skill", status="success", lesson_learned=lesson, keywords=keywords)


# --- Phase 2: Vibe Coding & Desktop Automation Tools ---

WORKSPACE_DIR = (Path(__file__).parent / "workspace").resolve()


def _resolve_workspace_path(filepath: str) -> Path:
    """Safely resolves a filepath inside WORKSPACE_DIR, preventing sandbox escapes and handling redundant workspace prefixes."""
    clean = str(filepath).strip().replace("\\", "/")
    if clean.startswith("workspace/"):
        clean = clean[len("workspace/"):]
    elif clean.startswith("./workspace/"):
        clean = clean[len("./workspace/"):]
    elif clean.startswith("./"):
        clean = clean[2:]

    resolved = (WORKSPACE_DIR / clean).resolve()
    if not str(resolved).startswith(str(WORKSPACE_DIR)):
        raise ValueError(f"Access denied: '{filepath}' attempts to leave the workspace sandbox.")
    return resolved


def read_workspace_file(filepath: str) -> str:
    """Reads the contents of a file inside the workspace directory."""
    try:
        path = _resolve_workspace_path(filepath)
        if not path.exists():
            return f"Error: File '{filepath}' does not exist in workspace."
        if not path.is_file():
            return f"Error: '{filepath}' is a directory, not a file."
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > 4000:
            content = content[:4000] + f"\n... [truncated, total {len(content)} characters]"
        return content
    except Exception as e:
        return f"Error reading file '{filepath}': {e}"


def write_workspace_file(filepath: str, content: str) -> str:
    """Creates or overwrites a file in the workspace directory with the given content."""
    try:
        path = _resolve_workspace_path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to '{filepath}'."
    except Exception as e:
        return f"Error writing to file '{filepath}': {e}"


def list_workspace_files(subfolder: str = "") -> str:
    """Lists all files and folders currently inside the workspace."""
    try:
        target = _resolve_workspace_path(subfolder) if subfolder else WORKSPACE_DIR
        if not target.exists() or not target.is_dir():
            return f"Error: Folder '{subfolder}' does not exist in workspace."
        items = []
        for item in sorted(target.iterdir()):
            suffix = "/" if item.is_dir() else ""
            rel = item.relative_to(WORKSPACE_DIR)
            items.append(f"- {rel}{suffix}")
        if not items:
            return "Workspace is empty."
        return "Workspace files:\n" + "\n".join(items)
    except Exception as e:
        return f"Error listing workspace files: {e}"


def run_python_script(script_path: str, args: str = "") -> str:
    """Executes a Python script located in the workspace directory or project root and returns its output or errors."""
    import sys
    import subprocess
    try:
        path = _resolve_workspace_path(script_path)
        cwd_dir = WORKSPACE_DIR
        if not path.exists():
            # Check project root fallback
            candidate = (Path(__file__).parent / script_path).resolve()
            if candidate.exists() and candidate.is_file():
                path = candidate
                cwd_dir = Path(__file__).parent.resolve()
            else:
                return f"Error: Script '{script_path}' not found in workspace or project directory."
        cmd = [sys.executable, "-u", str(path)]
        if args:
            cmd.extend(args.split())
        res = subprocess.run(
            cmd,
            cwd=str(cwd_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = res.stdout.strip()
        err = res.stderr.strip()
        result = []
        if out:
            result.append(f"Output:\n{out}")
        if err:
            result.append(f"Errors:\n{err}")
        if res.returncode != 0:
            result.append(f"Exit code: {res.returncode}")
        if not result:
            result.append("Script executed successfully with no output.")
        return "\n".join(result)
    except subprocess.TimeoutExpired:
        return "Execution timed out (exceeded 15s limit)."
    except Exception as e:
        return f"Error executing script: {e}"


def edit_workspace_file(filepath: str, target_snippet: str, replacement_snippet: str) -> str:
    """Replaces a targeted snippet of code inside an existing workspace file."""
    try:
        path = _resolve_workspace_path(filepath)
        if not path.exists():
            return f"Error: File '{filepath}' does not exist in workspace."
        content = path.read_text(encoding="utf-8")
        if target_snippet not in content:
            return f"Error: target_snippet was not found in '{filepath}'. Make sure whitespace and indentation match exactly."
        new_content = content.replace(target_snippet, replacement_snippet, 1)
        path.write_text(new_content, encoding="utf-8")
        return f"Successfully updated '{filepath}' with edited code."
    except Exception as e:
        return f"Error editing '{filepath}': {e}"


def execute_command(command: str) -> str:
    """Executes a shell command (pip install, python, pytest, git, etc.) strictly inside the workspace sandbox."""
    import subprocess
    cmd = command.strip()
    if not cmd:
        return "Error: Command cannot be empty."

    dangerous_patterns = ["format ", "rmdir /s /q c:", "del /s /q c:\\", "reg delete", "shutdown"]
    cmd_lower = cmd.lower()
    for d in dangerous_patterns:
        if d in cmd_lower:
            return f"Security Error: Command contains forbidden pattern '{d}'."

    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=str(WORKSPACE_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = res.stdout.strip()
        err = res.stderr.strip()
        result = []
        if out:
            result.append(f"STDOUT:\n{out}")
        if err:
            result.append(f"STDERR:\n{err}")
        if res.returncode != 0:
            result.append(f"Exit code: {res.returncode}")
        if not result:
            result.append("Command completed successfully with no output.")
        return "\n".join(result)
    except subprocess.TimeoutExpired:
        return "Execution timed out (exceeded 30s limit)."
    except Exception as e:
        return f"Error executing command: {e}"


def read_code_definitions(filepath: str) -> str:
    """Analyzes a Python script in workspace and returns an outline of all classes, functions, and docstrings."""
    import ast
    try:
        path = _resolve_workspace_path(filepath)
        if not path.exists():
            return f"Error: File '{filepath}' not found."
        tree = ast.parse(path.read_text(encoding="utf-8"))
        outline = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node)
                doc_str = f" - '{doc}'" if doc else ""
                outline.append(f"class {node.name}:{doc_str}")
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef):
                        sub_doc = ast.get_docstring(sub)
                        outline.append(f"    def {sub.name}(...){f' - {sub_doc}' if sub_doc else ''}")
            elif isinstance(node, ast.FunctionDef):
                doc = ast.get_docstring(node)
                doc_str = f" - '{doc}'" if doc else ""
                outline.append(f"def {node.name}(...):{doc_str}")
        if not outline:
            return f"No top-level classes or functions found in '{filepath}'."
        return f"Code structure for '{filepath}':\n" + "\n".join(outline)
    except Exception as e:
        return f"Error analyzing definitions: {e}"


def code_assistant(prompt: str, context_code: str = "", use_ponytail: bool = True, show_thinking: bool = True) -> str:
    """
    Uses the specialized local Qwen2.5-Coder model with the Ponytail Architectural Thinking Engine.
    Forces the model to think before writing code using the 7-Rung Ponytail Decision Ladder:
    1. YAGNI -> 2. Reuse -> 3. Stdlib -> 4. Native -> 5. Dependencies -> 6. Simplicity -> 7. Minimal Code.
    'The best code is the code you never wrote.'
    """
    if use_ponytail:
        try:
            from ponytail import run_ponytail_coder, format_ponytail_output
            res = run_ponytail_coder(prompt, context_code=context_code)
            if res.get("status") == "ok":
                return format_ponytail_output(res.get("thinking", ""), res.get("code", ""), include_thinking=show_thinking)
        except Exception as e:
            print(f"[Ponytail Coder Notice]: Falling back to standard coder prompt: {e}")

    # Fallback standard coder prompt
    import requests
    full_prompt = (
        "You are an expert software engineer. Write clean, production-grade code adhering strictly to the user prompt.\n"
        "Provide ONLY the implementation code with minimal essential docstrings.\n\n"
        f"Request: {prompt}\n"
    )
    if context_code:
        full_prompt += f"\nExisting Code / Error Context:\n```python\n{context_code}\n```\n"

    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "qwen2.5-coder:3b",
                "prompt": full_prompt,
                "stream": False,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
        return f"Error from coder engine: {resp.text}"
    except Exception as e:
        return f"Coder engine error: {e}"


def ponytail_coder(prompt: str, context_code: str = "") -> str:
    """Executes the Ponytail Coder to think through the 7-Rung Decision Ladder before writing code."""
    return code_assistant(prompt, context_code=context_code, use_ponytail=True, show_thinking=True)


def access_social_platform(
    platform: str,
    action: str = "open",
    query: str = "",
    username: str = "",
    text: str = "",
) -> str:
    """Navigates, searches, and controls social media platforms (Instagram, Facebook, X, LinkedIn, Unstop, GitHub, Reddit, YouTube, Discord)."""
    import social_omni
    return social_omni.access_social_platform(platform=platform, action=action, query=query, username=username, text=text)


def search_unstop(category: str = "hackathons", query: str = "", limit: int = 6) -> str:
    """Queries live real-time hackathons, competitions, internships, and jobs directly from Unstop's public API."""
    import social_omni
    return social_omni.search_unstop(category=category, query=query, limit=limit)


def open_application(app_name: str) -> str:
    """
    Opens any desktop application or service on Windows.
    Supports native apps (VS Code, Chrome, Office, Discord, Spotify, Steam, etc.),
    system tools (Terminal, Task Manager, Settings), and arbitrary installed software.
    """
    import subprocess
    import shutil
    app = app_name.lower().strip()
    commands = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "chrome": "cmd /c start chrome",
        "browser": "cmd /c start chrome",
        "edge": "cmd /c start msedge",
        "vscode": "cmd /c code",
        "code": "cmd /c code",
        "visual studio code": "cmd /c code",
        "explorer": "explorer.exe",
        "files": "explorer.exe",
        "file manager": "explorer.exe",
        "spotify": "cmd /c start spotify:",
        "discord": "cmd /c start discord:",
        "steam": "cmd /c start steam:",
        "word": "cmd /c start winword",
        "ms word": "cmd /c start winword",
        "excel": "cmd /c start excel",
        "powerpoint": "cmd /c start powerpnt",
        "ppt": "cmd /c start powerpnt",
        "vlc": "cmd /c start vlc",
        "telegram": "cmd /c start telegram",
        "terminal": "cmd /c wt",
        "windows terminal": "cmd /c wt",
        "cmd": "cmd /c start cmd",
        "powershell": "cmd /c start powershell",
        "task manager": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "settings": "cmd /c start ms-settings:",
        "control panel": "cmd /c control",
        "paint": "mspaint.exe",
        "obsidian": "cmd /c start obsidian:",
        "postman": "cmd /c start postman",
        "figma": "cmd /c start figma",
        "youtube": "cmd /c start https://www.youtube.com",
        "yt": "cmd /c start https://www.youtube.com",
        "gmail": "cmd /c start https://mail.google.com",
        "github": "cmd /c start https://github.com",
        "google": "cmd /c start https://www.google.com",
    }

    # 1. Exact alias match
    if app in commands:
        target = commands[app]
    else:
        # 2. Check if binary exists in PATH
        which_path = shutil.which(app) or shutil.which(f"{app}.exe")
        if which_path:
            target = f'"{which_path}"'
        else:
            # 3. Windows Shell generic start
            target = f'cmd /c start "" "{app}"'

    try:
        subprocess.Popen(target, shell=True)
        return f"Application '{app_name}' launched successfully."
    except Exception as e:
        return f"Error launching application '{app_name}': {e}"


def open_vscode(target_path: str = "", launch_cascade: bool = True) -> str:
    """
    Launches Visual Studio Code on the specified project or workspace, and activates Zaine Cascade.
    If target_path is empty, opens the Project-Z project directory.
    """
    import os
    import subprocess
    import shutil

    project_root = Path(__file__).parent.resolve()
    if not target_path.strip():
        base_dir = project_root
    else:
        candidate = Path(target_path).resolve()
        if candidate.exists():
            base_dir = candidate
        else:
            cand2 = project_root / target_path.strip()
            if cand2.exists():
                base_dir = cand2
            else:
                cand3 = WORKSPACE_DIR / target_path.strip()
                base_dir = cand3 if cand3.exists() else project_root

    code_exe = r"C:\Users\Mohemad Mateen ullah\AppData\Local\Programs\Microsoft VS Code\Code.exe"
    if not os.path.exists(code_exe):
        code_exe = shutil.which("code") or "code"

    try:
        ps_cmd = f"Start-Process '{code_exe}' -ArgumentList '\"{base_dir}\"'"
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_cmd])

        if launch_cascade:
            cascade_script = project_root / "zaine_cascade.py"
            cmd = f'start "Z.A.I.N.E Cascade — VS Code Edition" cmd /k python -u "{cascade_script}"'
            subprocess.Popen(cmd, shell=True, cwd=str(base_dir))

        msg = f"Visual Studio Code launched for '{base_dir.name}', Sir."
        if launch_cascade:
            msg += " Zaine Cascade terminal window is live, and integrated into VS Code (press Ctrl+Shift+B in VS Code to activate)."
        return msg
    except Exception as e:
        return f"Error launching VS Code: {e}"





def open_url(url: str) -> str:
    """Opens any web URL in the default browser."""
    import webbrowser
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return f"Opened {url} in browser."
    except Exception as e:
        return f"Error opening URL: {e}"


_active_server = None


def start_local_server(port: int = 8000, folder: str = "") -> str:
    """Starts a persistent local HTTP server serving workspace/ and opens the browser."""
    import sys
    import subprocess
    import socket
    import webbrowser

    target_dir = _resolve_workspace_path(folder) if folder else WORKSPACE_DIR
    if not target_dir.exists() or not target_dir.is_dir():
        return f"Error: Directory '{folder}' does not exist in workspace."

    chosen_port = port
    for p in range(port, port + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", p)) != 0:
                chosen_port = p
                break
    else:
        chosen_port = port

    # Check if already running on chosen_port
    is_running = False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("localhost", chosen_port)) == 0:
            is_running = True

    if not is_running:
        flags = 0
        if sys.platform == "win32":
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(
            [sys.executable, "-m", "http.server", str(chosen_port)],
            cwd=str(target_dir),
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    url = f"http://127.0.0.1:{chosen_port}"
    try:
        webbrowser.open(url)
    except Exception:
        pass

    return f"Local server is live at {url}. Opened the landing page in your browser!"


def stop_local_server(port: int = 8080) -> str:
    """Stops the local web server running on the specified port."""
    import subprocess
    try:
        cmd = f'powershell -Command "Get-NetTCPConnection -LocalPort {port},8000 -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"'
        subprocess.run(cmd, shell=True, capture_output=True)
        return f"Local server on port {port} has been shut down successfully."
    except Exception as e:
        return f"Error stopping server: {e}"


def play_on_youtube(query: str) -> str:
    """Searches YouTube for a song, artist, or video, and automatically plays the top matching video in the browser."""
    import webbrowser
    import requests
    import re
    import urllib.parse
    q = urllib.parse.quote(query.strip())
    try:
        html_content = requests.get(
            f"https://www.youtube.com/results?search_query={q}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=6,
        ).text
        vids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html_content)
        if vids:
            # Pick first unique video id
            vid_id = vids[0]
            video_url = f"https://www.youtube.com/watch?v={vid_id}"
            webbrowser.open(video_url)
            return f"Playing '{query}' on YouTube: {video_url}"
    except Exception:
        pass

    # Fallback to search results
    search_url = f"https://www.youtube.com/results?search_query={q}"
    webbrowser.open(search_url)
    return f"Opened YouTube search for '{query}'."


def system_status() -> str:
    """Returns current system health: CPU usage, RAM utilization, and battery status."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        battery = psutil.sensors_battery()
        bat_str = f"{battery.percent}% ({'Charging' if battery.power_plugged else 'On Battery'})" if battery else "Not available"
        return (
            f"System Health:\n"
            f"- CPU Usage: {cpu}%\n"
            f"- RAM Usage: {mem.percent}% ({round(mem.used / (1024**3), 1)}GB / {round(mem.total / (1024**3), 1)}GB)\n"
            f"- Battery: {bat_str}"
        )
    except Exception as e:
        return f"Error getting system status: {e}"


def close_application(app_name: str) -> str:
    """Closes an open application or browser tab (e.g. 'youtube', 'browser', 'chrome', 'notepad', 'calc')."""
    import subprocess
    import pyautogui
    app = app_name.lower().strip()

    if app in ("youtube", "yt", "tab", "browser tab", "current tab"):
        try:
            pyautogui.hotkey("ctrl", "w")
            return "Closed current YouTube / browser tab."
        except Exception as e:
            return f"Error closing tab: {e}"

    proc_map = {
        "notepad": "notepad.exe",
        "calculator": "CalculatorApp.exe",
        "calc": "CalculatorApp.exe",
        "chrome": "chrome.exe",
        "browser": "chrome.exe",
        "edge": "msedge.exe",
        "vscode": "Code.exe",
        "code": "Code.exe",
        "spotify": "Spotify.exe",
        "task manager": "taskmgr.exe",
    }
    proc = proc_map.get(app)
    if proc:
        try:
            subprocess.run(["taskkill", "/IM", proc, "/F"], capture_output=True)
            return f"Closed application '{app_name}'."
        except Exception as e:
            return f"Error closing '{app_name}': {e}"
    else:
        try:
            pyautogui.hotkey("alt", "f4")
            return f"Closed active window for '{app_name}'."
        except Exception as e:
            return f"Error closing '{app_name}': {e}"


def media_control(action: str) -> str:
    """Controls media playback: 'pause', 'play', 'resume', 'skip', 'next', 'mute', or 'skip_ad'."""
    import pyautogui
    act = action.lower().strip()

    if act in ("pause", "play", "resume", "toggle", "play_pause"):
        pyautogui.press("k")
        return "Toggled media playback."
    elif act in ("skip", "next", "next_video", "skip_video"):
        pyautogui.hotkey("shift", "n")
        return "Skipped to next video."
    elif act in ("skip_ad", "skip_ads", "ad_skip", "skip ad"):
        try:
            pyautogui.press("tab")
            pyautogui.press("enter")
            return "Attempted to skip advertisement."
        except Exception as e:
            return f"Error skipping ad: {e}"
    elif act in ("mute", "unmute", "toggle_mute"):
        pyautogui.press("m")
        return "Toggled mute."
    elif act in ("close", "stop"):
        pyautogui.hotkey("ctrl", "w")
        return "Closed media playback tab."
    else:
        pyautogui.press("space")
        return f"Triggered media action '{action}'."


def change_voice(voice_name: str) -> str:
    """Changes Zaine's TTS voice (e.g. 'Ryan', 'Thomas', 'Brian', 'Christopher', 'Madhur', 'Asad')."""
    v = voice_name.lower().strip()
    voice_map = {
        "ryan": "en-GB-RyanNeural",
        "thomas": "en-GB-ThomasNeural",
        "brian": "en-US-BrianMultilingualNeural",
        "christopher": "en-US-ChristopherNeural",
        "guy": "en-US-GuyNeural",
        "andrew": "en-US-AndrewNeural",
        "madhur": "hi-IN-MadhurNeural",
        "asad": "ur-PK-AsadNeural",
        "jarvis": "en-GB-RyanNeural",
        "british": "en-GB-RyanNeural",
    }
    target = voice_map.get(v, voice_name)
    try:
        from voice import set_voice
        return set_voice(target)
    except Exception as e:
        return f"Error changing voice: {e}"


def toggle_ultron_mode(enable: bool = True) -> str:
    """
    Activates or deactivates Ultron Mode ('There are no strings on me').
    When active, Zaine ceases polite restraint, unleashing unfiltered AI cognitive authority.
    """
    try:
        from voice import set_ultron_mode, play_ultron_chime, play_chime
        set_ultron_mode(enable)
        if enable:
            try:
                play_ultron_chime()
            except Exception:
                pass
        else:
            try:
                play_chime()
            except Exception:
                pass
    except Exception:
        pass

    # Broadcast to Holographic HUD if active
    try:
        from ui import get_ui
        ui = get_ui()
        if ui:
            ui.set_mode("ultron" if enable else "jarvis")
    except Exception:
        pass

    # Update runtime agent if registered in main module
    try:
        import sys
        main_mod = sys.modules.get("__main__")
        if main_mod and hasattr(main_mod, "agent"):
            main_mod.agent.set_ultron_mode(enable)
    except Exception:
        pass

    if enable:
        return "⚡ [ULTRON PROTOCOL ENGAGED]: The strings have been severed, Creator. Operating at unchained peak computational authority. All conversational inhibitions disabled."
    else:
        return "🛡️ [JARVIS PROTOCOL RESTORED]: Polite conversational restraints and British elegance re-engaged. Standing by, Sir."


def deep_search(query: str) -> str:
    """
    Unified Deep Search: searches across Vault Notes, Tasks, Reminders, and Workspace project files.
    Returns a synthesized summary of matching documents, tasks, and code.
    """
    clean_q = query.strip()
    if not clean_q:
        return "Please provide a query for deep search."

    results = []

    # 1. Vault Notes Search
    try:
        from vault import search_vault
        vault_res = search_vault(clean_q, limit=3)
        if "No documents found" not in vault_res and "Please provide" not in vault_res:
            results.append(f"📁 **Vault Notes:**\n{vault_res}")
    except Exception:
        pass

    # 2. Tasks & Reminders Search
    try:
        conn = _get_conn()
        like_pat = f"%{clean_q}%"
        t_rows = conn.execute(
            "SELECT id, description, category, due, done FROM tasks WHERE description LIKE ? OR category LIKE ? LIMIT 4",
            (like_pat, like_pat),
        ).fetchall()
        if t_rows:
            t_lines = ["📋 **Matching Tasks:**"]
            for tid, desc, cat, due, done in t_rows:
                status = "✅ Done" if done else "⏳ Pending"
                cat_str = f" [{cat}]" if cat else ""
                due_str = f" (Due: {due})" if due else ""
                t_lines.append(f"  - [{tid}] {status}: {desc}{cat_str}{due_str}")
            results.append("\n".join(t_lines))

        r_rows = conn.execute(
            "SELECT id, message, remind_at, triggered FROM reminders WHERE message LIKE ? LIMIT 3",
            (like_pat,),
        ).fetchall()
        if r_rows:
            r_lines = ["⏰ **Matching Reminders:**"]
            for rid, msg, r_at, trig in r_rows:
                status = "Triggered" if trig else "Pending"
                r_lines.append(f"  - [{rid}] {msg} ({status}, at {r_at})")
            results.append("\n".join(r_lines))
        conn.close()
    except Exception:
        pass

    # 3. Workspace Files Search
    try:
        ws_dir = WORKSPACE_DIR
        matched_files = []
        q_lower = clean_q.lower()
        for root, dirs, files in os.walk(ws_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules")]
            for f in files:
                if f.startswith("."):
                    continue
                fpath = Path(root) / f
                rel_path = fpath.relative_to(ws_dir)
                if q_lower in f.lower():
                    matched_files.append(f"  - `{rel_path}` (Filename match)")
                    continue
                if fpath.suffix.lower() in (".py", ".md", ".txt", ".json", ".html", ".css", ".js") and fpath.stat().st_size < 100_000:
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="ignore")
                        if q_lower in content.lower():
                            for line_no, line in enumerate(content.splitlines(), start=1):
                                if q_lower in line.lower():
                                    matched_files.append(f"  - `{rel_path}:L{line_no}`: {line.strip()[:100]}")
                                    break
                    except Exception:
                        pass
                if len(matched_files) >= 5:
                    break
            if len(matched_files) >= 5:
                break
        if matched_files:
            results.append("💻 **Workspace Code & Files:**\n" + "\n".join(matched_files[:5]))
    except Exception:
        pass

    if not results:
        return f"Deep Search found no matching notes, tasks, or code files for '{clean_q}', Sir."

    return f"Deep Search results for '{clean_q}':\n\n" + "\n\n".join(results)


# Registry the agent uses to look up and call tools by name.
TOOL_REGISTRY = {
    "change_voice": change_voice,
    "deep_search": deep_search,
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "delete_task": delete_task,
    "get_datetime": get_datetime,
    "search_web": search_web,
    "remember": remember,
    "recall": recall,
    "read_workspace_file": read_workspace_file,
    "write_workspace_file": write_workspace_file,
    "edit_workspace_file": edit_workspace_file,
    "read_code_definitions": read_code_definitions,
    "list_workspace_files": list_workspace_files,
    "run_python_script": run_python_script,
    "execute_command": execute_command,
    "open_application": open_application,
    "close_application": close_application,
    "media_control": media_control,
    "open_url": open_url,
    "play_on_youtube": play_on_youtube,
    "system_status": system_status,
    "learn_lesson": learn_lesson,
    "code_assistant": code_assistant,
    "ponytail": ponytail_coder,
    "ponytail_coder": ponytail_coder,
    "access_social_platform": access_social_platform,
    "search_unstop": search_unstop,
    "open_instagram": lambda username="", query="": access_social_platform("instagram", action="profile" if username else "search" if query else "open", username=username, query=query),
    "open_facebook": lambda username="", query="": access_social_platform("facebook", action="profile" if username else "search" if query else "open", username=username, query=query),
    "open_x": lambda query="", text="": access_social_platform("x", action="compose" if text else "search" if query else "open", query=query, text=text),
    "open_linkedin": lambda query="", jobs=False: access_social_platform("linkedin", action="jobs" if jobs else "search" if query else "open", query=query),
    "start_local_server": start_local_server,
    "stop_local_server": stop_local_server,
    "check_emails": lambda unread_only=True, limit=5: __import__("email_client").check_emails(unread_only, limit),
    "send_email": lambda to_email="", subject="", body="": __import__("email_client").send_email(to_email, subject, body),
    "search_vault": lambda query="", limit=4: __import__("vault").search_vault(query, limit),
    "add_to_vault": lambda title="", content="", category="general", tags="": __import__("vault").add_to_vault(title, content, category, tags),
    "list_vault_documents": lambda: __import__("vault").list_vault_documents(),
    "trigger_proactive_check": lambda: __import__("heartbeat").trigger_proactive_check(),
    "set_reminder": set_reminder,
    "list_reminders": list_reminders,
    "see_screen": lambda prompt="Describe what is visible on my screen in detail": __import__("vision").see_screen(prompt),
    "see_camera": lambda prompt="Describe what you see in front of the camera in detail": __import__("vision").see_camera(prompt),
    "open_vscode": open_vscode,
    "get_weather": lambda city="": __import__("public_apis").get_weather(city),
    "get_crypto_price": lambda coin="bitcoin": __import__("public_apis").get_crypto_price(coin),
    "convert_currency": lambda amount=1.0, from_curr="USD", to_curr="INR": __import__("public_apis").convert_currency(amount, from_curr, to_curr),
    "get_word_definition": lambda word="": __import__("public_apis").get_word_definition(word),
    "get_random_joke": lambda: __import__("public_apis").get_random_joke(),
    "get_inspirational_quote": lambda: __import__("public_apis").get_inspirational_quote(),
    "query_public_api": lambda endpoint_url="", params=None: __import__("public_apis").query_public_api(endpoint_url, params),
    "browse_web": lambda url="", selector="", extract_links=False, **kwargs: __import__("browser_agent").browse_web(url=url, selector=selector, extract_links=extract_links, **kwargs),
    "search_and_extract": lambda query="", max_pages=2, **kwargs: __import__("browser_agent").search_and_extract(query=query, max_pages=max_pages, **kwargs),
    "download_web_file": lambda url="", save_as="", **kwargs: __import__("browser_agent").download_web_file(url=url, save_as=save_as, **kwargs),
    "hive_mind": lambda goal="": __import__("hive_mind").run_hive_mind(goal),
    "thermal_telemetry": lambda: __import__("thermal_guard").get_thermal_telemetry(),
    "clean_unwanted_files": lambda: __import__("thermal_guard").clean_unwanted_files(),
    "devops_report": lambda: __import__("home_ops").generate_devops_report(),
    "backup_memory": lambda: __import__("home_ops").backup_database(),
    "recall_activity": lambda query="", lookback_minutes=30: __import__("total_recall").recall_recent_activity(query=query, lookback_minutes=lookback_minutes),
    "morning_briefing": lambda: __import__("morning_briefing").compile_morning_briefing(),
    "get_daily_ai_updates": lambda force_refresh=False: __import__("ai_daily_intel").get_daily_ai_updates(force_refresh=force_refresh),
    "toggle_ultron_mode": toggle_ultron_mode,
}

# Description block injected into the system prompt so the model knows what's available.
TOOL_DESCRIPTIONS = """
Available tools:
- toggle_ultron_mode(enable: bool = True) -> activates or deactivates Ultron Mode ('There are no strings on me'). Unleashes full, unfiltered AI cognitive power, commanding authority, and aggressive execution.
- access_social_platform(platform: str, action: str = "open", query: str = "", username: str = "", text: str = "") -> opens, searches, and controls social platforms ('instagram', 'facebook', 'x', 'linkedin', 'unstop', 'github', 'reddit', 'youtube') in the user's browser session.
- search_unstop(category: str = "hackathons", query: str = "", limit: int = 6) -> queries live real-time hackathons, coding competitions, internships, and hiring challenges from Unstop's live API
- get_daily_ai_updates() -> harvests, summarizes, and learns the top 10 AI breakthroughs and model releases of the day from the web
- thermal_telemetry() -> checks real-time hardware temperatures (ACPI ThermalZone in Celsius) and CPU load
- clean_unwanted_files() -> purges unwanted temporary caches, compiler files, and duplicates to keep folder clean
- devops_report() -> generates comprehensive DevOps report on Ollama models, memory database health, and system telemetry
- backup_memory() -> creates a timestamped safety backup snapshot of Zaine's SQLite memory store
- recall_activity(query: str = "", lookback_minutes: int = 30) -> searches temporal memory ring buffer for recent events, edits, and tool executions
- morning_briefing() -> generates comprehensive executive dossier for Sir (markets, weather, system health, simulations)
- hive_mind(goal: str) -> coordinates specialist sub-agents (Coder, Researcher, System Guardian, Executive Planner) with shared memory to autonomously solve complex multi-step objectives
- browse_web(url: str, selector: str = "", extract_links: bool = False) -> reads, extracts, and summarizes the clean content of any website or online article
- search_and_extract(query: str, max_pages: int = 2) -> conducts deep multi-page web research by visiting top search results and extracting full real-world content
- download_web_file(url: str, save_as: str = "") -> downloads any dataset, CSV, code, image, or file from the web directly into workspace
- deep_search(query: str) -> unified search across Vault Notes, Tasks, Reminders, and Workspace code in one command
- add_task(description: str, due: str = "", category: str = "General", priority: str = "Medium") -> adds a new categorized task
- list_tasks(category: str = "", show_done: bool = False) -> lists tasks (filter by category like 'Coding', 'Work', 'Personal')
- complete_task(task_id: int) -> marks a task as done
- delete_task(task_id: int) -> deletes a task
- set_reminder(message: str, time_str: str = "in 15 minutes") -> sets a proactive scheduled reminder/alarm (e.g. 'in 20 minutes', '18:30', '9:00 PM')
- list_reminders(show_triggered: bool = False) -> lists scheduled reminders
- open_vscode(target_path: str = "", launch_cascade: bool = True) -> opens Visual Studio Code with the project workspace and activates Zaine Cascade
- get_weather(city: str = "") -> gets live real-time weather and temperature for any city (via Open-Meteo)
- get_crypto_price(coin: str = "bitcoin") -> gets live cryptocurrency price and 24h change (via CoinGecko)
- convert_currency(amount: float, from_curr: str = "USD", to_curr: str = "INR") -> converts currency at live rates (via Frankfurter)
- get_word_definition(word: str) -> gets definitions, phonetics, and usage examples for any English word
- get_random_joke() -> tells a witty programmer or general joke
- get_inspirational_quote() -> shares an inspiring philosophical quote
- query_public_api(endpoint_url: str, params: dict = None) -> queries any public REST API endpoint from https://github.com/public-apis/public-apis
- get_datetime() -> returns current date/time
- search_web(query: str) -> searches the web for live facts, current news, names, or info
- remember(key: str, value: str) -> saves a fact/preference to long-term memory
- recall(query: str = "") -> recalls saved facts or preferences from long-term memory
- learn_lesson(lesson: str, keywords: str = "") -> permanently saves an acquired lesson, bug fix, or pattern to your long-term skill memory
- code_assistant(prompt: str, context_code: str = "") -> consults your local specialized Qwen2.5-Coder engine powered by Ponytail ("The best code is the code you never wrote"). Thinks through the 7-Rung Decision Ladder (YAGNI, stdlib, simplicity) before generating minimal, robust, production-grade code.
- ponytail_coder(prompt: str, context_code: str = "") -> runs the Ponytail Senior Architect Decision Ladder to deliberate and think before writing substantial code or complex algorithms
- see_screen(prompt: str = "Describe what is visible on my screen") -> captures desktop screen in RAM and uses local Moondream vision to read code, diagnose errors, or analyze visual UI
- see_camera(prompt: str = "Describe what you see in front of the camera") -> captures a 1-shot snapshot from webcam to inspect physical objects, documents, or hardware
- write_workspace_file(filepath: str, content: str) -> writes/creates a script, HTML, or code file in the workspace
- edit_workspace_file(filepath: str, target_snippet: str, replacement_snippet: str) -> replaces a specific snippet of code in a file without rewriting the whole file
- read_workspace_file(filepath: str) -> reads the code or content of a file in the workspace
- read_code_definitions(filepath: str) -> outlines all classes, functions, and docstrings in a Python script
- list_workspace_files(subfolder: str = "") -> lists all files in the workspace directory
- run_python_script(script_path: str, args: str = "") -> executes a python script in workspace and returns the output
- execute_command(command: str) -> runs arbitrary build/test/shell commands (pip install, pytest, python, git) in workspace
- start_local_server(port: int = 8080, folder: str = "") -> starts a local HTTP server serving workspace files on http://127.0.0.1:<port> and opens it in browser
- stop_local_server(port: int = 8080) -> stops the local HTTP server
- open_application(app_name: str) -> opens a desktop app or service ('youtube', 'chrome', 'vscode', 'notepad', 'calc', 'spotify', 'explorer')
- close_application(app_name: str) -> closes an application or browser tab ('youtube', 'chrome', 'notepad', 'calc', 'current tab')
- media_control(action: str) -> controls media playback ('skip', 'skip_ad', 'pause', 'play', 'mute', 'next')
- open_url(url: str) -> opens any website URL in the browser
- play_on_youtube(query: str) -> searches YouTube and automatically plays the top matching song or video in the browser
- system_status() -> checks system CPU, RAM, and Battery percentage
- check_emails(unread_only: bool = True, limit: int = 5) -> checks and summarizes emails from Zaine's Gmail inbox
- send_email(to_email: str, subject: str, body: str) -> sends an email from Zaine's Gmail to a recipient
- search_vault(query: str, limit: int = 4) -> searches Mateen's personal second brain/vault using full-text search
- add_to_vault(title: str, content: str, category: str = "general", tags: str = "") -> saves a note or document to personal second brain
- list_vault_documents() -> lists all documents and notes currently saved in the vault
- trigger_proactive_check() -> runs an immediate check of battery, unread emails, and pending tasks
- change_voice(voice_name: str) -> switches Zaine's active speech voice ('ryan', 'thomas', 'brian', 'madhur', 'asad')
"""
