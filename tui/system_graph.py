"""
tui/system_graph.py
Real system topology digraph for the F3 workspace, assembled from live local sources only:
core_service /api/status and /api/approvals, Ollama /api/tags and /api/ps, the Telegram poller's
single-instance lock port, tool_clusters.TOOL_CLUSTERS and vault folder counts.

Blocking HTTP with short timeouts: call it from the telemetry thread, never from the UI loop.
"""

import json
import socket
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from tui.exec_graph import GraphNode

OLLAMA_URL = "http://127.0.0.1:11434"
TELEGRAM_LOCK_PORT = 49912  # telegram_bridge.acquire_telegram_lock listens here while a poller runs


def _get_json(url: str, timeout: float = 0.8) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ZaineTUI"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def _port_open(port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


class SystemGraph:
    """Static-shaped digraph (same interface as ExecGraph: nodes, edges, layers, is_active)."""

    is_active = False

    def __init__(self) -> None:
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[Tuple[str, str]] = []
        self._depth: Dict[str, int] = {}
        self.facts: Dict[str, Any] = {}

    def add(self, node_id: str, kind: str, label: str, detail: str, status: str, parent: Optional[str] = None, **meta) -> None:
        self.nodes[node_id] = GraphNode(node_id, kind, label, detail, status, meta=meta)
        self._depth[node_id] = (self._depth[parent] + 1) if parent else 0
        if parent:
            self.edges.append((parent, node_id))

    def layers(self) -> List[List[str]]:
        cols: Dict[int, List[str]] = {}
        for nid, d in self._depth.items():
            cols.setdefault(d, []).append(nid)
        return [cols[d] for d in sorted(cols)]


def collect_system_graph(core_url: str) -> SystemGraph:
    g = SystemGraph()
    status = _get_json(f"{core_url}/api/status")
    core_up = isinstance(status, dict)
    tags = _get_json(f"{OLLAMA_URL}/api/tags") or {}
    ps = _get_json(f"{OLLAMA_URL}/api/ps") or {}
    approvals = _get_json(f"{core_url}/api/approvals") if core_up else None

    if core_up:
        state = "warming" if status.get("warming") else ("ready" if status.get("model_loaded") else "no model")
        g.add("core", "service", "Core Service", f":{status.get('port', '?')} {state}", "online")
    else:
        g.add("core", "service", "Core Service", "unreachable", "offline")

    # Models: installed in Ollama, marked when actually resident (with real VRAM use).
    ollama_up = bool(tags)
    g.add("router", "group", "Router", "Ollama" if ollama_up else "Ollama offline",
          "online" if ollama_up else "offline", parent="core")
    loaded = {m.get("name"): m for m in ps.get("models", [])} if isinstance(ps, dict) else {}
    active = str(status.get("active_model", "")) if core_up else ""
    for m in sorted(tags.get("models", []), key=lambda x: x.get("name", "")):
        name = m.get("name", "?")
        if "embed" in name:
            continue
        short = name.replace(":latest", "")
        res = loaded.get(name)
        if res:
            vram = (res.get("size_vram") or 0) / 1024 ** 3
            detail, st = f"{vram:.1f}G VRAM", "loaded"
        else:
            detail, st = f"{(m.get('size') or 0) / 1024 ** 3:.1f}G disk", "idle"
        if active and short == active.replace(":latest", ""):
            detail += " ★"
        g.add(f"model:{short}", "llm", short, detail, st, parent="router")

    # Tools by cluster (real registry grouping used to build the prompt).
    try:
        from tool_clusters import TOOL_CLUSTERS
        total = len({t for c in TOOL_CLUSTERS.values() for t in c.get("tools", [])})
        g.add("agent", "group", "Agent", f"{total} clustered tools", "online" if core_up else "unknown", parent="core")
        for name, spec in TOOL_CLUSTERS.items():
            g.add(f"cluster:{name}", "cluster", name, f"{len(spec.get('tools', []))} tools", "ok", parent="agent")
    except Exception:
        g.add("agent", "group", "Agent", "clusters unavailable", "unknown", parent="core")

    # Memory: vault folder counts (folder names and counts only, never note titles).
    try:
        from tui.telemetry import get_vault_stats
        vs = get_vault_stats()
        g.add("memory", "store", "Memory", f"vault {vs['status'].lower()}", "online" if vs["available"] else "offline", parent="agent")
        for folder, count in sorted(vs.get("folders", {}).items()):
            if count:
                g.add(f"vault:{folder}", "store", folder, f"{count} notes", "ok", parent="memory")
    except Exception:
        pass

    # Human-in-the-loop path.
    pending = len(approvals.get("pending", [])) if isinstance(approvals, dict) else None
    g.add("guard", "group", "Guardrail", f"{pending} pending" if pending is not None else "n/a",
          ("waiting" if pending else "online") if pending is not None else "unknown", parent="core")
    tg = _port_open(TELEGRAM_LOCK_PORT)
    g.add("telegram", "channel", "Telegram", "poller online" if tg else "poller off", "online" if tg else "offline", parent="guard")

    g.facts = {
        "core_up": core_up,
        "core_status": status if core_up else {},
        "ollama_up": ollama_up,
        "loaded_models": [(n.replace(":latest", ""), (m.get("size_vram") or 0) / 1024 ** 3) for n, m in loaded.items()],
        "pending_approvals": pending,
        "telegram_online": tg,
    }
    return g
