"""
agents/registry.py
Loads and validates agent profiles and picks the agent for a turn.

Selection is deterministic (no extra LLM call), in this order:
  1. an @mention at the start of the message ("@edith fix this test")
  2. the session pin set with /agent <name>
  3. routing: the tool-cluster keywords that already shape the prompt, mapped through each
     profile's route_clusters (coding keywords -> E.D.I.T.H., system -> F.R.I.D.A.Y., ...)
  4. the default agent (J.A.R.V.I.S.)
"""

import json
import re
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROFILES_PATH = Path(__file__).resolve().parent / "profiles.json"

# Tools implemented by the agent runtime itself rather than tools.py (not part of any cluster).
AGENT_RUNTIME_TOOLS = {"ask_agent", "delegate", "read_result"}
DELEGATION_TOOLS = frozenset({"ask_agent", "delegate"})

_MENTION_RE = re.compile(r"^\s*@([A-Za-z][\w.\-&]*)[\s,:]+(.*)$", re.S)


@dataclass(frozen=True)
class AgentProfile:
    agent_id: str
    display_name: str
    title: str
    role_prompt: str
    allowed_clusters: Tuple[str, ...]
    extra_tools: Tuple[str, ...]
    denied_tools: Tuple[str, ...]
    route_clusters: Tuple[str, ...]
    aliases: Tuple[str, ...]
    max_tool_hops: int
    color: str
    interactive: bool
    auto_route: bool
    voice: str = "en-GB-RyanNeural"
    voice_pitch: str = "+0Hz"
    voice_rate: str = "+0%"
    allowed_tools: frozenset = field(default_factory=frozenset)
    allow_all_tools: bool = False  # default agent: every registered tool, including runtime custom tools
    role: str = ""
    subagent_allowed_tools: frozenset = field(default_factory=frozenset)
    step_budget: int = 0
    context_scope: str = ""

    def allows(self, tool_name: str) -> bool:
        return self.allow_all_tools or tool_name in self.allowed_tools

    def for_subagent(self) -> "AgentProfile":
        """Returns a strictly scoped copy for depth>=1 subagent execution (never spawns subagents)."""
        scoped = (self.subagent_allowed_tools or self.allowed_tools) - DELEGATION_TOOLS
        return replace(
            self,
            allowed_tools=frozenset(scoped),
            allow_all_tools=False,
            max_tool_hops=self.step_budget or self.max_tool_hops,
        )

    def summary(self) -> Dict:
        data = {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "title": self.title,
            "clusters": list(self.allowed_clusters),
            "tool_count": "all" if self.allow_all_tools else len(self.allowed_tools),
            "max_tool_hops": self.max_tool_hops,
            "color": self.color,
            "voice": self.voice,
            "voice_pitch": self.voice_pitch,
            "voice_rate": self.voice_rate,
            "interactive": self.interactive,
            "auto_route": self.auto_route,
            "aliases": list(self.aliases),
        }
        if self.role:
            data["role"] = self.role
        if self.step_budget:
            data["step_budget"] = self.step_budget
        if self.context_scope:
            data["context_scope"] = self.context_scope
        return data


@dataclass(frozen=True)
class AgentSelection:
    profile: AgentProfile
    reason: str          # human-readable why
    source: str          # "mention" | "pinned" | "routed" | "default"
    message: str         # user message with any @mention removed


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


class AgentRegistry:
    def __init__(self, profiles: List[AgentProfile], default_id: str):
        self.profiles: Dict[str, AgentProfile] = {p.agent_id: p for p in profiles}
        self.default_id = default_id
        self._lookup: Dict[str, str] = {}
        self._role_lookup: Dict[str, str] = {}
        for p in profiles:
            for name in (p.agent_id, p.agent_id.replace("zaine-", ""), p.display_name, *p.aliases):
                self._lookup[_key(name)] = p.agent_id
            if p.role:
                self._role_lookup[_key(p.role)] = p.agent_id
        self._pin_lock = threading.Lock()
        self._pinned: Optional[str] = None

    @property
    def default(self) -> AgentProfile:
        return self.profiles[self.default_id]

    def resolve(self, name: str) -> Optional[AgentProfile]:
        k = _key(name)
        agent_id = self._lookup.get(k) or self._role_lookup.get(k)
        return self.profiles.get(agent_id) if agent_id else None

    def interactive(self) -> List[AgentProfile]:
        return [p for p in self.profiles.values() if p.interactive]

    # Session pin (one core = one operator; Telegram and the TUI share it).
    @property
    def pinned(self) -> Optional[AgentProfile]:
        with self._pin_lock:
            return self.profiles.get(self._pinned) if self._pinned else None

    def pin(self, name: Optional[str]) -> Tuple[bool, str]:
        """Pin an agent by name/alias, or clear the pin with None/'auto'."""
        if not name or _key(name) in ("auto", "none", "off", "default"):
            with self._pin_lock:
                self._pinned = None
            return True, "Automatic agent routing restored."
        profile = self.resolve(name)
        if profile is None:
            return False, f"Unknown agent '{name}'. Available: " + ", ".join(p.display_name for p in self.interactive())
        if not profile.interactive:
            return False, f"{profile.display_name} is a background agent and cannot take chat turns."
        with self._pin_lock:
            self._pinned = profile.agent_id
        return True, f"{profile.display_name} pinned for this session ({profile.title})."


def _load(path: Path = PROFILES_PATH) -> AgentRegistry:
    from tool_clusters import TOOL_CLUSTERS

    data = json.loads(path.read_text(encoding="utf-8"))
    known_tools = {t for c in TOOL_CLUSTERS.values() for t in c.get("tools", [])} | AGENT_RUNTIME_TOOLS
    profiles, seen = [], set()
    for raw in data["agents"]:
        aid = raw["agent_id"]
        if aid in seen:
            raise ValueError(f"duplicate agent_id {aid}")
        seen.add(aid)
        for c in list(raw.get("allowed_clusters", [])) + list(raw.get("route_clusters", [])):
            if c not in TOOL_CLUSTERS:
                raise ValueError(f"{aid}: unknown cluster {c}")
        for t in list(raw.get("extra_tools", [])) + list(raw.get("denied_tools", [])) + list(raw.get("allowed_tools", [])):
            if t not in known_tools:
                raise ValueError(f"{aid}: unknown tool {t}")
        allowed = {t for c in raw.get("allowed_clusters", []) for t in TOOL_CLUSTERS[c]["tools"]}
        allowed |= set(raw.get("extra_tools", []))
        allowed -= set(raw.get("denied_tools", []))
        sub_allowed = raw.get("allowed_tools")
        profiles.append(AgentProfile(
            agent_id=aid,
            display_name=raw["display_name"],
            title=raw.get("title", ""),
            role_prompt=raw.get("role_prompt", ""),
            allowed_clusters=tuple(raw.get("allowed_clusters", [])),
            extra_tools=tuple(raw.get("extra_tools", [])),
            denied_tools=tuple(raw.get("denied_tools", [])),
            route_clusters=tuple(raw.get("route_clusters", [])),
            aliases=tuple(raw.get("aliases", [])),
            max_tool_hops=int(raw.get("max_tool_hops", 6)),
            color=raw.get("color", "#f0fdf4"),
            voice=raw.get("voice", "en-GB-RyanNeural"),
            voice_pitch=raw.get("voice_pitch", "+0Hz"),
            voice_rate=raw.get("voice_rate", "+0%"),
            interactive=bool(raw.get("interactive", True)),
            auto_route=bool(raw.get("auto_route", True)),
            allowed_tools=frozenset(allowed),
            allow_all_tools=bool(raw.get("allow_all_tools", False)),
            role=str(raw.get("role", "")),
            subagent_allowed_tools=frozenset(sub_allowed) if sub_allowed is not None else frozenset(),
            step_budget=int(raw.get("step_budget", 0) or 0),
            context_scope=str(raw.get("context_scope", "")),
        ))
    default_id = data.get("default_agent") or profiles[0].agent_id
    if default_id not in seen:
        raise ValueError(f"default_agent {default_id} is not defined")
    return AgentRegistry(profiles, default_id)


_registry: Optional[AgentRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> AgentRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = _load()
        return _registry


def parse_mention(message: str) -> Tuple[Optional[AgentProfile], str]:
    """'@edith fix this' -> (E.D.I.T.H., 'fix this'); unknown or absent mention -> (None, message)."""
    m = _MENTION_RE.match(message or "")
    if not m:
        return None, message
    profile = get_registry().resolve(m.group(1))
    if profile is None or not profile.interactive:
        return None, message
    return profile, m.group(2).strip() or message


def _cluster_scores(message: str) -> Dict[str, int]:
    """Same keyword scoring as tool_clusters.classify_intent_clusters, but without its default fallback."""
    from tool_clusters import TOOL_CLUSTERS
    lower = message.lower()
    return {name: sum(1 for kw in spec["keywords"] if kw in lower) for name, spec in TOOL_CLUSTERS.items()}


def select_agent(message: str, task_tier: str = "") -> AgentSelection:
    reg = get_registry()
    mentioned, stripped = parse_mention(message)
    if mentioned:
        return AgentSelection(mentioned, f"@{mentioned.aliases[0] if mentioned.aliases else mentioned.agent_id}", "mention", stripped)
    pinned = reg.pinned
    if pinned:
        return AgentSelection(pinned, "pinned with /agent", "pinned", message)

    scores = _cluster_scores(message)
    touched = {c for c, s in scores.items() if s > 0}
    specialists = [p for p in reg.profiles.values() if p.auto_route and p.route_clusters and p.agent_id != reg.default_id]

    # A specialist takes the turn only if every tool area the message touches is within its permissions;
    # mixed requests ("open chrome and write code") stay with the default agent, which has every tool.
    if task_tier == "DEEP_CODE":
        coder = next((p for p in specialists if "DEV_CODE" in p.route_clusters), None)
        if coder and touched <= set(coder.allowed_clusters):
            return AgentSelection(coder, "routed: coding task tier", "routed", message)

    if touched:
        fits = [p for p in specialists if touched & set(p.route_clusters) and touched <= set(p.allowed_clusters)]
        if fits:
            best = max(fits, key=lambda p: max(scores[c] for c in p.route_clusters))
            area = max(best.route_clusters, key=lambda c: scores[c])
            return AgentSelection(best, f"routed: {area.lower()} keywords", "routed", message)
    return AgentSelection(reg.default, "default agent" if not touched else "default agent (mixed request)", "default", message)
