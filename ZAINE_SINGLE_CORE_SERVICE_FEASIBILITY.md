# Z.A.I.N.E Single Core Service Feasibility Report

**Author:** Manus AI  
**Project:** Project-Z  
**Assessment date:** 17 September 2026  
**Scope:** Feasibility and minimal-disruption path for consolidating Z.A.I.N.E into one persistent core service with thin HUD, Telegram, and Cascade clients.

## Executive conclusion

Consolidating Z.A.I.N.E into one persistent core service is **feasible and recommended**. The lowest-risk path is to use the existing `ui.py` HTTP server as a transitional core host, keep one production `ZaineAgent` instance behind it, and convert the HUD, Telegram, and Cascade interfaces into clients of a small HTTP contract.

This work should be split into two phases:

- **Phase 2a — Process unification:** One core process, one active `ZaineAgent`, and one global continuous conversation. Do not introduce durable conversations yet.
- **Phase 2b — Session infrastructure:** Add durable conversation IDs, messages, session-scoped memory, chat history, and thread switching after the unified core is stable.

The implemented Option A prototype demonstrates the direction, but independent verification found two blockers before it should be treated as production-ready. First, the agent lock remains held for the entire duration of streaming, so concurrent requests wait behind a long response. Second, the idempotency cache is not atomic: two simultaneous requests with the same request ID can both execute the agent call. These are solvable with a serialized request coordinator and an atomic in-flight request registry.

> **Decision:** Proceed with process unification as Phase 2a, but harden request serialization and idempotency before accepting the implementation. Do not combine the first process-unification change with the full session/thread migration.

## Current architecture and feasibility

The current production desktop path creates one global agent in `main.py`:

```python
agent = ZaineAgent()
ui = ZaineUI(agent=agent)
```

When Telegram is embedded inside `main.py`, it receives that same object:

```python
bridge = TelegramBridge(agent=agent)
```

However, standalone Telegram creates another agent through its default constructor:

```python
class TelegramBridge:
    def __init__(self, agent=None):
        if agent is None:
            from agent import ZaineAgent
            self.agent = ZaineAgent()
```

Cascade also creates a separate agent when launched as a CLI:

```python
def run_cascade_cli():
    agent = ZaineAgent()
```

The result is multiple live `ConversationMemory` buffers, independent Ultron mode state, independent model-router state, and repeated model warm-up. SQLite files are shared by the processes, but the active FIFO conversation buffer remains process-local.

The existing UI server is a practical transition point because it already provides:

- A persistent `ThreadingHTTPServer`.
- An existing `/api/chat` endpoint.
- A `/api/chat/stream` endpoint in the Option A implementation.
- A `/api/health` endpoint.
- A `/api/context/clear` endpoint.
- Existing HUD status and SSE broadcasting.
- A startup path that can bind the server before dependent clients begin.

The server is not yet a clean permanent core boundary because `ui.py` also contains static file serving, telemetry, vision caches, workspace operations, lock-screen logic, and HUD presentation state. It is therefore best treated as a **transitional host**, not the final architecture.

## State ownership after unification

### State that is currently process-local

Each `ZaineAgent()` owns its own `ConversationMemory`:

```python
self.memory = ConversationMemory()
```

The active buffer retains 12 turns, or up to 24 message records. The following state is also process-local:

- Current FIFO conversation history.
- `session_start` and `session_recalled` flags.
- `last_tool_called`.
- `ultron_mode`.
- Model installation-cache state in `core_router.py`.
- Model warm-up state.
- HUD status, mode, SSE subscribers, and visual caches.
- Telegram Whisper model cache and typing-heartbeat threads.

A single core process would consolidate the first group of agent-owned state automatically.

### State that is already shared through files and databases

The active production code uses `zaine_tasks.db` for tasks, reminders, persistent memories, task learnings, conversation episodes, enrolled faces, and Telegram chat settings. Other shared stores include the approval database, idea database, knowledge FTS database, vault database, YouTube queue/state files, and pending-review JSON files.

The repository still contains legacy artifacts such as root and `data/` versions of `zaine_memory.db`, plus an empty legacy face database. These do not prevent process unification, but they should be removed or explicitly classified during the later state-consolidation work.

## Recommended Phase 2a architecture

The first unified architecture should preserve the existing application shape while changing ownership of general agent requests:

```text
                         ┌──────────────────────────┐
                         │ Persistent core process  │
                         │                          │
                         │ ZaineAgent               │
                         │ ConversationMemory      │
                         │ Tool executor            │
                         │ Model router             │
                         │ Request coordinator      │
                         │ HTTP API                 │
                         └─────────────┬────────────┘
                                       │
             ┌─────────────────────────┼─────────────────────────┐
             │                         │                         │
          HUD client             Telegram client            Cascade client
```

The initial HTTP contract should remain deliberately small:

| Endpoint | Purpose | Phase 2a behavior |
|---|---|---|
| `GET /api/health` | Liveness check | Authoritative check; discovery JSON is only a port hint. |
| `POST /api/chat` | Non-streaming chat | Serializes against the shared global memory. |
| `POST /api/chat/stream` | Streaming chat | Uses the same request coordinator and reports queue/busy state. |
| `POST /api/context/clear` | Clear context | Explicitly clears the one global FIFO buffer until Phase 2b. |
| `GET /api/state` | Mode/status metadata | Returns current core state without exposing Python objects. |

Every request should include a client label and request ID:

```json
{
  "message": "Continue the architecture review.",
  "client": "telegram",
  "request_id": "tg-8f1d2c3a"
}
```

The request ID is for idempotency and diagnostics in Phase 2a. It is **not yet a conversation ID**.

## Client responsibilities in Phase 2a

### HUD

The HUD remains local to the core-hosting process initially. Its current chat endpoint can call the core agent directly because it is already inside the core process. The future cleanup should route it through an internal service object rather than through `ui_instance.agent` directly.

### Telegram

Telegram should remain responsible for Telegram-specific behavior:

- Long polling.
- Authentication and pairing.
- Voice-note download.
- Faster-Whisper transcription.
- Voice reply synthesis and upload.
- Message chunking and Markdown fallback.
- Typing indicators.
- Per-chat `/voicemode` settings.
- Telegram callback-query presentation.

General natural-language text should call `POST /api/chat`. The existing per-chat voice-mode setting is stored in SQLite and does not need session infrastructure. Telegram can continue deciding whether to send a text or voice response based on `from_voice` and the stored chat preference.

Direct commands such as `/faces`, `/vault`, `/tasks`, `/screen`, `/camera`, `/approve`, `/deny`, and `/voicemode` can remain local during the first migration. This is the lowest-disruption option, although it means Phase 2a is a partial rather than total capability centralization.

The `/clear` command requires special handling. In the unified global-session model, it must call `/api/context/clear` and be described as clearing shared context across HUD, Telegram, and Cascade. It must not silently clear only a client-local buffer.

### Cascade

Cascade should stop creating a fallback `ZaineAgent` in normal operation. It should:

1. Read `.zaine_core.json` only to discover a candidate port.
2. Call `GET /api/health` to verify liveness.
3. Use `/api/chat/stream` for natural-language requests.
4. Preserve its local terminal commands such as `/inspect`, `/run`, `/test`, and `/files` initially.
5. Fail clearly if the core is unavailable instead of silently creating another agent.

This prevents the split-brain architecture from returning through an implicit fallback.

### Training and evaluation scripts

The following should remain independent and should not call the production core:

- `eval_test_prompts.py`
- `repo_trainer.py`
- `simulate_training.py`
- `daily_qa_generator.py`

They require isolated agent instances for reproducibility, batch execution, or evaluation. Their independence is a feature rather than an architectural defect.

## Verified risks in the current Option A implementation

### Streaming lock duration

`agent.py` currently wraps the complete generator in an `RLock`:

```python
def chat_stream(self, user_message: str, on_tool_event=None):
    with self._chat_lock:
        yield from self._chat_stream_impl(
            user_message,
            on_tool_event=on_tool_event
        )
```

This means the lock remains held through all model streaming, tool hops, and response delivery.

A live controlled test started a slow stream and then issued a second `/api/chat` request. The second request waited:

```text
second_wait_seconds: 2.701
second_result: 200
stream_thread_done: true
```

This behavior is safe for memory ordering but poor for multi-client responsiveness. The first implementation should use a request coordinator with explicit queue state rather than allowing clients to wait invisibly behind a lock.

### Idempotency race

The current endpoint performs a cache read and later performs a cache write. Each operation uses `_PROCESSED_REQUESTS_LOCK`, but the complete claim-and-execute sequence is not atomic.

A duplicate-request race test sent two concurrent requests with the same ID. The result was:

```text
agent_chat_calls: 2
results: [200, 200]
cache_present: true
```

The cache correctly stored a result eventually, but it failed to prevent duplicate execution. This is unacceptable for side-effecting tools.

The fix should introduce an in-flight registry. The first request atomically claims the request ID. Later requests should wait for or reuse the first request’s result.

## Guardian approval compatibility

The current Telegram approval callback remains a direct local call:

```python
ApprovalRegistry.approve(
    action_id,
    note="Approved via Telegram inline button"
)
```

An end-to-end same-process test created a proposal and processed a synthetic Telegram callback. It produced:

```text
status: APPROVED
resolution_note: Approved via Telegram inline button
```

This confirms that Option A did not break the existing same-process callback path.

However, `ApprovalRegistry` still stores approval callbacks in a process-local dictionary:

```python
_action_callbacks: Dict[str, Callable[[], Any]] = {}
```

If a proposal is created in the core process and approved by a separate Telegram process, the proposal status will be shared through SQLite, but the callback closure will not be available in the Telegram process. Cross-process approval execution therefore remains an existing limitation and must be addressed before moving all Guardian execution behind a separate service boundary.

## Discovery file and lifecycle

`.zaine_core.json` should be treated as a discovery hint, not as proof of liveness. A simulated abrupt termination left the file capable of reporting:

```json
{
  "status": "online",
  "pid": 999999
}
```

The file has no crash recovery, lease expiry, or PID validation. Cascade performs `GET /api/health` at startup, and standalone Telegram polls `GET /api/health` before beginning normal polling. This is the correct authority model, but the Telegram per-request path should also handle stale-port failures cleanly.

The core startup sequence is correctly ordered in source:

1. Start the HTTP server.
2. Poll `/api/health`.
3. Start Telegram.
4. Start heartbeat and local interaction loops.
5. Launch the HUD window.

The current fallback continues startup after a health-gate timeout. A production version should either fail closed, retry for a bounded period, or explicitly start clients in degraded mode.

## Phase 2a implementation sequence

### Step 1 — Establish the core contract

Define a small internal service interface for chat, streaming, health, state, and global context clearing. Keep the current HTTP route names so the change remains compatible with the Option A direction.

### Step 2 — Add a request coordinator

Replace invisible lock contention with a coordinator that owns the single active global conversation. It should expose whether a request is running, queued, completed, or failed. The coordinator may still serialize all Phase 2a requests, but clients should receive explicit status instead of waiting without feedback.

### Step 3 — Add atomic idempotency

Atomically claim a request ID before agent execution. Store in-flight state separately from completed response state. A retry for an active request should wait for the original request or receive a clear in-progress response.

### Step 4 — Make the core lifecycle authoritative

Start the core server before clients. Keep `/api/health` authoritative. Add stale discovery handling, atomic discovery-file writes, and a clear shutdown strategy. Do not trust `status: online` in `.zaine_core.json` without a successful health request.

### Step 5 — Convert clients gradually

Migrate general natural-language chat first:

- Telegram → `POST /api/chat`.
- Cascade → `POST /api/chat/stream`.
- HUD → internal core service call or existing route.

Keep direct Telegram commands and local Cascade workspace commands unchanged until the chat contract is stable.

### Step 6 — Add observability

Record request ID, client, start time, queue wait, execution time, response status, tool name, and failure reason. This is necessary to distinguish model latency from queue latency and network latency.

### Step 7 — Validate before Phase 2b

Acceptance tests should cover:

- One request at a time with explicit queue behavior.
- Duplicate request IDs during active execution.
- Streaming completion and client disconnects.
- Telegram voice-note transcription and voice replies.
- `/voicemode` persistence.
- Guardian approval in same-process and cross-process scenarios.
- Cascade startup while the core is offline.
- Recovery after a crashed core process.

## Phase 2b: session and conversation infrastructure

Once Phase 2a is stable, add durable sessions and messages:

```text
chat_sessions
messages
client_bindings
```

The Phase 2b request contract should become:

```json
{
  "session_id": "session-123",
  "message": "Continue the architecture review.",
  "client": "telegram",
  "request_id": "tg-8f1d2c3a"
}
```

At that point:

- `ConversationMemory` becomes session-scoped.
- `/clear` clears one session instead of global state.
- HUD can provide chat history and New Chat behavior.
- Telegram chats can map to durable sessions.
- Cascade can have a coding-specific session.
- Parallel execution can be considered across independent sessions.

Session IDs should not be introduced in the first unification change unless the product requires separate conversations immediately. Introducing them concurrently would increase the debugging surface and make it harder to isolate transport, locking, persistence, and session-mapping failures.

## Final recommendation

Adopt the following sequence:

```text
Phase 2a:
  one core process
  one ZaineAgent
  one global FIFO conversation
  HTTP thin clients
  serialized request coordinator
  atomic idempotency
  health-first lifecycle

Phase 2b:
  chat_sessions
  messages
  session-scoped memory
  chat history
  per-client/thread routing
  cross-session concurrency
```

The architecture is feasible. The minimal-disruption path is not to rewrite Z.A.I.N.E into a new service framework immediately. It is to harden the existing `ui.py` server into a transitional core host, migrate only natural-language chat first, preserve direct Telegram and Cascade commands, and add durable sessions after the single-core runtime is reliable.

## References

[1]: ../Project-Z/main.py "Desktop startup, agent ownership, health gate, and client lifecycle"
[2]: ../Project-Z/agent.py "ZaineAgent construction, streaming lock, tool loop, and conversation memory ownership"
[3]: ../Project-Z/ui.py "HTTP server, chat endpoints, health endpoint, request cache, and core discovery file"
[4]: ../Project-Z/telegram_bridge.py "Telegram client, voice notes, direct commands, approvals, and core HTTP calls"
[5]: ../Project-Z/zaine_cascade.py "Cascade thin-client discovery, health check, streaming, and local commands"
[6]: ../Project-Z/memory.py "ConversationMemory FIFO buffer and shared SQLite memory path"
[7]: ../Project-Z/approval.py "Guardian proposal persistence, process-local callbacks, and approval execution"
[8]: ../Project-Z/ZAINE_CURRENT_STATE.md "Prior architectural audit and current state inventory"
