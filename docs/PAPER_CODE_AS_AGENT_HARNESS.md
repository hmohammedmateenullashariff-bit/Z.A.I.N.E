# "Code as Agent Harness" (arXiv 2605.18747): lessons for Z.A.I.N.E

*Ning et al., 18 May 2026. A survey/position paper (102 pages, no experiments of its own); every figure it quotes comes from other work. Reviewed 2026-10-23 against the Zaine codebase.*

**Core claim:** an agent's reliability depends on its *harness* (tools, sandboxes, memory, validators, permissions, control loop, feedback) as much as on the model. Code is a good harness medium because it is executable (verifiable), inspectable and stateful.

## What it confirms in Zaine's design
- **Deterministic before LLM.** Critique should *interpret sensor outputs rather than replace them* (p.31). This supports keyword routing, approval as the boundary, and ULTRON as advisory only.
- **Quality of experience over quantity** (p.24). This supports the spec's "no autonomous promotion" rule; the 472 auto-lessons are the anti-pattern.
- **Three permission tiers** (read-only / edit / full with mandatory human approval, pp.30–31), matching the spec's `read_only` / `write_local` / `external`.
- **No embeddings needed:** memory "is not simply… a vector database" (p.22).
- **Bounded loops with explicit caps** (p.39): `max_tool_hops`, `SUBAGENT_MAX_HOPS = 3`, and depth-1 `ask_agent`.

## Where it pushes back
- **JSON tool calls vs code-as-action (CodeAct, p.54):** the paper prefers code actions but gives no head-to-head numbers, and requires a sandbox Zaine doesn't have. *Decision: keep JSON, harden it* (validate against signatures; consider Ollama structured output; measure the regex-fallback rate first).
- **More agents ≠ progress:** "topology complexity inversely correlates with harness-state formality" (p.48). With one resident model there is no context-splitting benefit (p.34). *Decision: keep depth-1 delegation; invest in shared structured state before adding agents or a council mode.*
- **A tool-less critic is the weakest variant** (p.38). *Decision: give ULTRON evidence (compiler and lint output), not just code.*

## Top-5 improvements (ordered)

| # | Improvement | Where | Size |
| :--- | :--- | :--- | :--- |
| 1 | **Real plan–execute–verify loop:** a final tool-free answer when the hop cap is hit (today it returns "I'm here."); a structured per-tool outcome `{ok, exit_code, error_kind, stderr_tail}` instead of substring checks; dead-end detection when the same call or error repeats; E.D.I.T.H. stops when checks pass | `agent.py` hop loop | S–M |
| 2 | **Compact tool results with retrievable handles:** cap injected results (~700 chars, deterministic summary), store the full text under `workspace/.runs/`, add a `read_result(id, start, length)` tool | hop loop + new store | S–M |
| 3 | **Turn trace store + replay suite** that gates every change to profiles, keywords or prompts; measure fallback-parse rate, misroutes and hop-cap hits | `_emit`, `ollama_profiler`, `eval_test_prompts.py` | M |
| 4 | **Deterministic sensors for E.D.I.T.H.:** `py_compile` (and `ruff` if present) after every `.py` write, results fed to the next hop and to ULTRON | post-hook after `write_workspace_file` / `edit_workspace_file` | M |
| 5 | **Externalised plan/state with fresh-context steps:** a small structured state (goal, steps, artifact handles, last checks) per hop / consultation / pipeline step; `ask_agent` sends a structured brief; one compact "last turn did X" line in memory | hop loop, `_delegate`, future pipeline engine | M–L |

**Smaller wins:**
- a safe `calc(expr)` tool (AST whitelist);
- file snapshots plus `revert_file`;
- a per-slot context budget inside 4096 tokens;
- an "evidence bundle" (checks run / not run) on E.D.I.T.H. answers;
- propose (never auto-apply) approval rules mined from past denials.

## Results that won't transfer to a 3B/7B on 4 GB
- **Imagined execution:** the "98%+" is on MBPP with large models.
- **Search/MCTS planning.**
- **Adaptive or evolving agent topologies.**
- **LLM failure attribution:** only 14–53% accurate even at frontier scale.
- **Harness-as-training-data RL loops.**
