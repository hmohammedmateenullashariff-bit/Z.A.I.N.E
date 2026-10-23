"""
tui/exec_graph.py
Live execution digraph of one Z.A.I.N.E turn, built only from real SSE events emitted by core_service:
prompt -> router (tier/model) -> LLM hop(s) -> tool calls -> approvals -> reply.

Pure data, no Textual imports, so it can be unit-tested and rendered by any widget.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Node kinds
PROMPT, ROUTER, MODEL, TOOL, APPROVAL, REPLY, ERROR = "prompt", "router", "model", "tool", "approval", "reply", "error"

# Node statuses
RUNNING, OK, FAILED, WAITING, BLOCKED, CANCELLED = "running", "ok", "failed", "waiting", "blocked", "cancelled"


@dataclass
class GraphNode:
    node_id: str
    kind: str
    label: str
    detail: str = ""
    status: str = RUNNING
    started: float = field(default_factory=time.perf_counter)
    ended: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> Optional[float]:
        if self.ended is None:
            return None
        return max(0.0, self.ended - self.started)

    def finish(self, status: str, detail: Optional[str] = None) -> None:
        self.status = status
        if detail is not None:
            self.detail = detail
        if self.ended is None:
            self.ended = time.perf_counter()


def classify_tool_result(result: Any) -> Tuple[str, str]:
    """Maps a tool result string to (tool_status, approval_outcome) using the strings tools.py returns."""
    text = str(result or "")
    if "Security Authorization Failed" in text:
        if "Denied" in text:
            return BLOCKED, "DENIED"
        if "Expired" in text:
            return BLOCKED, "EXPIRED"
        if "Cancelled" in text:
            return BLOCKED, "CANCELLED"
        return BLOCKED, "NOT EXECUTED"
    head = text.strip()[:40].lower()
    if head.startswith(("error", "❌")) or "traceback" in head:
        return FAILED, "APPROVED"
    return OK, "APPROVED"


def _short(value: Any, limit: int) -> str:
    if isinstance(value, dict):
        value = " ".join(f"{k}={v}" for k, v in value.items())
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class ExecGraph:
    """Directed acyclic graph of the current turn plus a log of the real events that built it."""

    MAX_EVENTS = 200

    def __init__(self) -> None:
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[Tuple[str, str]] = []
        self.events: List[Tuple[str, str, str]] = []  # (HH:MM:SS, channel, text)
        self.turn_index = 0
        self.prompt = ""
        self.started: Optional[float] = None
        self.ended: Optional[float] = None
        self.tier = ""
        self.model = ""
        self._seq = 0
        self._frontier: List[str] = []       # nodes the next step connects from
        self._open_model: Optional[str] = None  # LLM hop currently generating
        self._last_model: Optional[str] = None  # most recent LLM hop (open or finished)
        self._hop_tools: List[str] = []      # tools started since the last LLM hop
        self._running_tools: Dict[str, List[str]] = {}  # tool name -> node ids still running
        self._approval_for_tool: Dict[str, str] = {}    # tool node id -> approval node id
        self._streamed = ""                              # tail of streamed reply text

    # ── construction helpers ────────────────────────────────────────────────
    def _add(self, kind: str, label: str, detail: str = "", status: str = RUNNING, sources=None, **meta) -> GraphNode:
        self._seq += 1
        node = GraphNode(f"{kind}-{self._seq}", kind, label, detail, status, meta=meta)
        self.nodes[node.node_id] = node
        for src in (sources if sources is not None else self._frontier):
            if src in self.nodes:
                self.edges.append((src, node.node_id))
        return node

    def _log(self, channel: str, text: str) -> None:
        self.events.append((datetime.now().strftime("%H:%M:%S"), channel, text))
        if len(self.events) > self.MAX_EVENTS:
            del self.events[: len(self.events) - self.MAX_EVENTS]

    def _ensure_model(self) -> GraphNode:
        """Returns the LLM hop the current event belongs to.

        core_service emits `profiler` when an Ollama call finishes, and the tool calls that call produced
        arrive afterwards, so a hop is reused until tools have run; only then does a new hop start.
        """
        if self._open_model and self.nodes[self._open_model].status == RUNNING:
            return self.nodes[self._open_model]
        if self._last_model and not self._hop_tools:
            return self.nodes[self._last_model]
        hop = sum(1 for n in self.nodes.values() if n.kind == MODEL) + 1
        sources = self._hop_tools or self._frontier
        node = self._add(MODEL, f"LLM hop {hop}", self.model or "generating", sources=sources, hop=hop)
        self._open_model = node.node_id
        self._last_model = node.node_id
        self._frontier = [node.node_id]
        self._hop_tools = []
        return node

    def _close_model(self) -> None:
        if self._open_model:
            node = self.nodes[self._open_model]
            if node.status == RUNNING:
                node.finish(OK)
            self._open_model = None

    # ── public API ──────────────────────────────────────────────────────────
    @property
    def is_empty(self) -> bool:
        return not self.nodes

    @property
    def is_active(self) -> bool:
        return self.started is not None and self.ended is None

    def start_turn(self, prompt: str) -> None:
        self.nodes.clear()
        self.edges.clear()
        self._seq = 0
        self._frontier = []
        self._open_model = None
        self._last_model = None
        self._hop_tools = []
        self._running_tools = {}
        self._approval_for_tool = {}
        self._streamed = ""
        self.turn_index += 1
        self.prompt = prompt
        self.tier = ""
        self.model = ""
        self.started = time.perf_counter()
        self.ended = None
        node = self._add(PROMPT, "Operator prompt", _short(prompt, 60), status=OK, sources=[])
        node.ended = node.started
        self._frontier = [node.node_id]
        self._log("USER", _short(prompt, 120))

    def apply(self, event: Dict[str, Any]) -> None:
        """Folds one SSE event from /api/chat/stream into the graph."""
        if self.started is None:
            return
        ev_type = event.get("type")
        if ev_type == "queued":
            self._log("COORD", f"queued at position {event.get('position', '?')}")
        elif ev_type == "warming":
            self._log("CORE", "model warming up")
        elif ev_type == "running":
            self._log("COORD", "turn granted")
        elif ev_type == "token":
            self._ensure_model()
            chunk = event.get("content") or event.get("token") or event.get("text") or ""
            self._streamed = (self._streamed + str(chunk))[-400:]
        elif ev_type == "tool_event":
            self._apply_tool_event(event.get("stage", ""), event.get("tool", ""), event.get("data"))
        elif ev_type == "done":
            self.finish_turn(reply=str(event.get("reply") or ""))
        elif ev_type == "error":
            self.abort(str(event.get("message") or "core error"))

    def _apply_tool_event(self, stage: str, tool: str, data: Any) -> None:
        if stage == "route":
            info = data if isinstance(data, dict) else {}
            self.tier = str(info.get("tier") or "")
            self.model = str(info.get("model") or "")
            node = self._add(ROUTER, f"Router · {self.tier or 'n/a'}", self.model, status=OK)
            node.ended = node.started
            self._frontier = [node.node_id]
            self._log("ROUTER", f"tier {self.tier or 'n/a'} -> {self.model or 'n/a'}")
        elif stage in ("think", "generating"):
            self._ensure_model()
        elif stage == "profiler":
            # One completed Ollama call: attach real token counts to the hop that produced it.
            info = data if isinstance(data, dict) else {}
            node = self._ensure_model()
            eval_count = int(info.get("eval_count") or 0)
            eval_s = float(info.get("eval_duration_s") or 0.0)
            node.meta.update(
                model=info.get("model") or tool or self.model,
                eval_count=eval_count,
                prompt_tokens=int(info.get("prompt_eval_count") or 0),
                tok_s=(eval_count / eval_s) if eval_s > 0 else 0.0,
                load_s=float(info.get("load_duration_s") or 0.0),
                wall_s=float(info.get("wall_time_s") or 0.0),
            )
            node.detail = str(node.meta["model"])
            node.finish(OK)
            self._open_model = None
            self._log("OLLAMA", f"{node.meta['model']}: {eval_count} tok @ {node.meta['tok_s']:.1f} tok/s")
        elif stage == "start":
            # Tools belong to the hop that requested them, even when several run one after another.
            if self._open_model and self.nodes[self._open_model].status == RUNNING:
                model = self.nodes[self._open_model]
            elif self._last_model:
                model = self.nodes[self._last_model]
            else:
                model = self._ensure_model()
            self._close_model()
            node = self._add(TOOL, tool or "tool", _short(data, 48), sources=[model.node_id])
            self._running_tools.setdefault(tool, []).append(node.node_id)
            self._hop_tools.append(node.node_id)
            self._log("TOOL", f"{tool} {_short(data, 80)}")
        elif stage == "approval_required":
            info = data if isinstance(data, dict) else {}
            tool_id = (self._running_tools.get(tool) or [None])[-1]
            sources = [tool_id] if tool_id else self._frontier
            node = self._add(
                APPROVAL, "Guardrail approval", _short(info.get("command") or info.get("reason"), 48),
                status=WAITING, sources=sources, proposal_id=info.get("proposal_id", ""),
                risk=info.get("risk_level", ""),
            )
            if tool_id:
                self.nodes[tool_id].status = WAITING
                self._approval_for_tool[tool_id] = node.node_id
            self._log("GUARD", f"approval required {info.get('proposal_id', '')}: {_short(info.get('command'), 60)}")
        elif stage == "approval_wait":
            info = data if isinstance(data, dict) else {}
            for node in self.nodes.values():
                if node.kind == APPROVAL and node.status == WAITING:
                    node.meta["waited"] = info.get("waited")
        elif stage == "done":
            ids = self._running_tools.get(tool) or []
            tool_id = ids.pop(0) if ids else None
            tool_status, outcome = classify_tool_result(data)
            if tool_id:
                self.nodes[tool_id].finish(tool_status)
                approval_id = self._approval_for_tool.get(tool_id)
                if approval_id:
                    appr = self.nodes[approval_id]
                    appr.finish(OK if outcome == "APPROVED" else BLOCKED)
                    appr.meta["outcome"] = outcome
                    self._log("GUARD", f"{appr.meta.get('proposal_id', '')} {outcome}")
            self._log("TOOL", f"{tool} -> {tool_status}: {_short(data, 70)}")

    def finish_turn(self, reply: str = "") -> None:
        if self.started is None or self.ended is not None:
            return
        self._close_model()
        self._settle_running(OK)
        text = reply or self._streamed
        sources = self._hop_tools or self._frontier
        node = self._add(REPLY, "Reply", _short(text, 60) or "(empty reply)", status=OK, sources=sources)
        node.ended = node.started
        self.ended = time.perf_counter()
        self._log("REPLY", f"{len(text)} chars in {self.ended - self.started:.2f}s")

    def abort(self, reason: str, status: str = FAILED) -> None:
        """Ends the turn on error, timeout or cancel so nothing is left drawn as running."""
        if self.started is None or self.ended is not None:
            return
        self._settle_running(CANCELLED if status == CANCELLED else FAILED)
        sources = [nid for nid, n in self.nodes.items() if not any(s == nid for s, _ in self.edges)] or self._frontier
        node = self._add(ERROR, "Cancelled" if status == CANCELLED else "Error", _short(reason, 60),
                         status=status, sources=sources)
        node.ended = node.started
        self.ended = time.perf_counter()
        self._log("ERROR" if status != CANCELLED else "CANCEL", _short(reason, 120))

    def _settle_running(self, status: str) -> None:
        for node in self.nodes.values():
            if node.status in (RUNNING, WAITING):
                node.finish(status)

    # ── summaries ───────────────────────────────────────────────────────────
    def summary(self) -> Dict[str, Any]:
        models = [n for n in self.nodes.values() if n.kind == MODEL]
        tools = [n for n in self.nodes.values() if n.kind == TOOL]
        approvals = [n for n in self.nodes.values() if n.kind == APPROVAL]
        tokens = sum(int(n.meta.get("eval_count") or 0) for n in models)
        rates = [n.meta["tok_s"] for n in models if n.meta.get("tok_s")]
        end = self.ended if self.ended is not None else time.perf_counter()
        return {
            "turn": self.turn_index,
            "prompt": self.prompt,
            "tier": self.tier or "n/a",
            "model": self.model or "n/a",
            "hops": len(models),
            "tokens": tokens,
            "tok_s": (sum(rates) / len(rates)) if rates else 0.0,
            "tools": len(tools),
            "tools_failed": sum(1 for n in tools if n.status in (FAILED, BLOCKED)),
            "approvals": [(n.meta.get("proposal_id", ""), n.meta.get("outcome", "PENDING")) for n in approvals],
            "elapsed_s": (end - self.started) if self.started else 0.0,
            "active": self.is_active,
        }

    def layers(self) -> List[List[str]]:
        """Groups node ids into columns by longest path from the root (topological layering)."""
        depth: Dict[str, int] = {}
        incoming: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for src, dst in self.edges:
            if dst in incoming:
                incoming[dst].append(src)
        for nid in self.nodes:  # insertion order is already topological
            preds = [depth[p] for p in incoming[nid] if p in depth]
            depth[nid] = (max(preds) + 1) if preds else 0
        columns: Dict[int, List[str]] = {}
        for nid, d in depth.items():
            columns.setdefault(d, []).append(nid)
        return [columns[d] for d in sorted(columns)]
