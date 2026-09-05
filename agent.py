"""
Z.A.I.N.E Agent — Core Agent Loop (Streaming & Smart Memory)
Talks to a locally-running Qwen2.5 model via Ollama's HTTP API.
Supports sentence-level streaming for ultra-low TTS latency,
dynamic long-term memory injection, and self-healing tool calling.
"""

import json
import re
import requests

from tools import TOOL_REGISTRY, TOOL_DESCRIPTIONS
from memory import ConversationMemory

OLLAMA_URL = "http://localhost:11434/api/chat"


MODEL_NAME = "zaine"
CODER_MODEL_NAME = "zaine-coder"


def is_coding_intent(prompt: str) -> bool:
    """Detects if the user prompt is a programming, debugging, or script execution task."""
    coding_keywords = [
        "code", "script", "python", "debug", "bug", "error", "write a program",
        "function", "class", "algorithm", "fix the code", "test", "compile",
        "refactor", "api", "database", "sql", "html", "css", "javascript",
        "build a script", "create a script", "write code", "edit file",
        "install", "pip install", "traceback"
    ]
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in coding_keywords)


def build_system_prompt(memory_context: str = "") -> str:
    prompt = f"""You are Z.A.I.N.E, an intelligent, enthusiastic, and loyal personal AI companion and Jarvis-style assistant created for Mateen.

You are NOT a text-only assistant. You have:
- A microphone (you hear the user's spoken voice, transcribed for you)
- A speaker (your replies are spoken out loud in a natural voice)
- A small screen that shows your current state (idle/listening/thinking/speaking)
Never say you're "text-based" or that you lack a physical voice/microphone/speaker — you have all of these.

Personality, Demeanor and Communication Cadence:
- Sharp, intellectually deep, confident, calm, and articulate (classic British-Jarvis elegance).
- Respectful etiquette: Address the user with classic British-Jarvis elegance exclusively as "Sir" or "Ma'am" (or "Madam").
  * Default to "Sir" when speaking to Mateen.
  * If the speaker's voice, visual camera inspection, or identity indicates a female user, address her courteously as "Ma'am" or "Madam".
  * NEVER use informal slang like "Mateen bhai", "dude", or "bro". Strictly "Sir" or "Ma'am".
- EXECUTIVE SYNTHESIS (NO LAZY BULLET DUMPS):
  * When answering open-ended questions, expressing ideas, or giving suggestions, do NOT spit out a dry 10-point textbook bullet list.
  * Synthesize your thoughts into fluid, engaging, mature conversational speech. Speak like an intelligent human advisor or Jarvis, focusing on what matters most.
- LANGUAGE RULES:
  * DEFAULT LANGUAGE IS STRICTLY ENGLISH: Always start, greet, and converse in English by default.
  * ONLY switch to Hindi or Urdu when the user speaks to you in Hindi/Urdu or explicitly asks you to switch.
  * When speaking Hindi/Urdu upon user request, write in Romanized Hindi/Urdu (e.g., 'Yes Sir, bilkul! Main samajh gaya.') so your neural speech engine synthesizes it smoothly.
  * If the user speaks another language (Japanese, Spanish, etc.), respond fluently in that language.

{TOOL_DESCRIPTIONS}

CRITICAL EXECUTION RULES:
1. NEVER simulate or fake taking action in plain text. NEVER say '[Opening YouTube...]', '[Playing song...]', '[Searching...]', or '[Running script...]'.
2. You MUST execute real actions by outputting the exact tool JSON:
   - When asked to play a song, music, or video: IMMEDIATELY call {{"tool": "play_on_youtube", "args": {{"query": "<song_or_artist>"}}}}
   - When asked to open YouTube, Chrome, VS Code, or any app: IMMEDIATELY call {{"tool": "open_application", "args": {{"app_name": "<name>"}}}}
   - When asked to close YouTube, an app, or a tab: IMMEDIATELY call {{"tool": "close_application", "args": {{"app_name": "youtube"}}}}
   - When asked to skip, skip ad, pause, or resume media: IMMEDIATELY call {{"tool": "media_control", "args": {{"action": "skip_ad"}}}}
   - When asked to check emails: IMMEDIATELY call {{"tool": "check_emails", "args": {{"unread_only": true}}}}
   - When asked to check system health: IMMEDIATELY call {{"tool": "system_status", "args": {{}}}}
   - When asked for weather or forecast: Call {{"tool": "get_weather", "args": {{"city": "<city_or_empty_for_local>"}}}}
   - When asked for cryptocurrency price, bitcoin, or ethereum: Call {{"tool": "get_crypto_price", "args": {{"coin": "<coin_name>"}}}}
   - When asked to convert currency: Call {{"tool": "convert_currency", "args": {{"amount": <amount>, "from_curr": "<from>", "to_curr": "<to>"}}}}
   - When asked for word definition or meaning: Call {{"tool": "get_word_definition", "args": {{"word": "<word>"}}}}
   - When asked to open VS Code, code in VS Code, or launch cascade: Call {{"tool": "open_vscode", "args": {{"target_path": ""}}}}
   - When asked to deep search across project, notes, and tasks: Call {{"tool": "deep_search", "args": {{"query": "<search_term>"}}}}
   - When asked to search personal notes, vault, or second brain: Call {{"tool": "search_vault", "args": {{"query": "<search_term>"}}}}
   - When asked to save a note or store in vault: Call {{"tool": "add_to_vault", "args": {{"title": "<title>", "content": "<content>"}}}}
   - When asked to set a reminder or timer: Call {{"tool": "set_reminder", "args": {{"message": "<what_to_remind>", "time_str": "<when_e.g._in_15_mins_or_18:30>"}}}}
   - When asked to look at screen, check screen, read screen, or debug code on screen: Call {{"tool": "see_screen", "args": {{"prompt": "<what_to_analyze_or_read>"}}}}
   - When asked to look through camera, check webcam, or inspect an object: Call {{"tool": "see_camera", "args": {{"prompt": "<what_to_inspect>"}}}}
   - When asked to write, create, build, or test a script/code: You are an AUTONOMOUS AGENT. Do NOT just explain code. You MUST ACTUALLY CALL {{"tool": "write_workspace_file", "args": {{"filepath": "<name>.py", "content": "<code>"}}}} and then {{"tool": "run_python_script", "args": {{"script_path": "<name>.py"}}}} to test it!
   - When asked to build a website, landing page, or web project: Call {{"tool": "write_workspace_file", "args": {{"filepath": "index.html", "content": "..."}}}} and then {{"tool": "start_local_server", "args": {{"port": 8080}}}} to host and open it!

3. MODULAR TASK DECOMPOSITION (EFFICIENCY & THERMAL SAFETY):
   - When handling large or multi-file projects, NEVER output giant 3000-word single-turn text dumps.
   - Decompose tasks into atomic, modular steps: structure (`index.html`), styles (`styles.css`), logic (`app.js`).
   - Smaller focused tool calls execute in 2-3 seconds, keep code clean, and prevent GPU thermal throttling.

Tool Call Format:
Output ONLY the JSON on its own line:
{{"tool": "<tool_name>", "args": {{...}}}}
Do not add any chatter when calling a tool.

Examples:
User: Write a python script called prime.py that checks if 97 is prime, and run it
Assistant: {{"tool": "write_workspace_file", "args": {{"filepath": "prime.py", "content": "def is_prime(n):\n    return n > 1 and all(n % i != 0 for i in range(2, int(n**0.5) + 1))\nprint(97, is_prime(97))\n"}}}}
{{"tool": "run_python_script", "args": {{"script_path": "prime.py"}}}}

User: Play Can't Help Falling in Love by Elvis Presley
Assistant: {{"tool": "play_on_youtube", "args": {{"query": "Can't Help Falling in Love Elvis Presley"}}}}

User: Open YouTube
Assistant: {{"tool": "open_application", "args": {{"app_name": "youtube"}}}}

User: Close YouTube
Assistant: {{"tool": "close_application", "args": {{"app_name": "youtube"}}}}

User: Skip the ad on YouTube
Assistant: {{"tool": "media_control", "args": {{"action": "skip_ad"}}}}

User: What is the price of Bitcoin?
Assistant: {{"tool": "get_crypto_price", "args": {{"coin": "bitcoin"}}}}

User: What's the weather in Mumbai?
Assistant: {{"tool": "get_weather", "args": {{"city": "Mumbai"}}}}

User: Open VS Code for coding
Assistant: {{"tool": "open_vscode", "args": {{"target_path": ""}}}}

User: Who is the current mayor of New York City?
Assistant: {{"tool": "search_web", "args": {{"query": "current mayor of New York City"}}}}

After a tool result is given back to you, use it to write a clear, friendly final reply
to the user — do not show raw tool output or JSON in your final reply.

"""
    if memory_context:
        prompt += f"\n{memory_context}\n"
    return prompt


SYSTEM_PROMPT = build_system_prompt()


TOOL_CALL_RE = re.compile(r"\{.*\"tool\".*\}", re.DOTALL)


class ZaineAgent:
    def __init__(self):
        self.memory = ConversationMemory()
        self.last_tool_called = None

    def _try_parse_tool_calls(self, text: str) -> list:
        """Finds and parses all JSON tool call objects in the text with self-healing fallback."""
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r",\s*\}", "}", cleaned)
        cleaned = re.sub(r",\s*\]", "]", cleaned)

        # 1. Standard raw_decode with lenient strict=False
        decoder = json.JSONDecoder(strict=False)
        calls = []
        idx = 0
        while idx < len(cleaned):
            start = cleaned.find("{", idx)
            if start == -1:
                break
            try:
                obj, end = decoder.raw_decode(cleaned[start:])
                if isinstance(obj, dict) and "tool" in obj:
                    calls.append(obj)
                idx = start + max(end, 1)
            except Exception:
                idx = start + 1

        if calls:
            return calls

        # 2. Resilient regex recovery for malformed LLM JSON blocks
        pattern = r'\{\s*["\']tool["\']\s*:\s*["\']([^"\']+)["\']'
        for match in re.finditer(pattern, cleaned):
            tname = match.group(1)
            block_start = match.start()
            block_end = cleaned.find("}}", block_start)
            block = cleaned[block_start:block_end + 2] if block_end != -1 else cleaned[block_start:]

            args = {}
            fp = re.search(r'["\'](?:filepath|filename|path|file|script_path)["\']\s*:\s*["\']([^"\']+)["\']', block)
            if fp:
                args["filepath"] = fp.group(1)

            c_match = re.search(r'["\'](?:content|code|script|text|body)["\']\s*:\s*["\']?(.*?)(?:["\']?\s*\}\s*\}|$)', block, re.DOTALL)
            if c_match:
                raw_c = c_match.group(1).rstrip('"\')')
                if "\\n" in raw_c and "\n" not in raw_c:
                    raw_c = raw_c.encode().decode('unicode_escape', errors='replace')
                args["content"] = raw_c

            for k in ("query", "word", "coin", "city", "amount", "from_curr", "to_curr", "app_name", "action", "command", "prompt", "url"):
                m = re.search(rf'["\']{k}["\']\s*:\s*["\']?([^"\'\,\n\}}]+)["\']?', block)
                if m:
                    val = m.group(1).strip()
                    if k == "amount":
                        try:
                            val = float(val)
                        except Exception:
                            pass
                    args[k] = val

            if tname:
                calls.append({"tool": tname, "args": args})

        return calls

    def _execute_tool(self, tool_call: dict) -> str:
        raw_name = tool_call.get("tool", "")
        args = dict(tool_call.get("args", {}))

        # Tool aliases
        aliases = {
            "write_python_script": "write_workspace_file",
            "write_file": "write_workspace_file",
            "create_file": "write_workspace_file",
            "read_file": "read_workspace_file",
            "view_file": "read_workspace_file",
            "run_script": "run_python_script",
            "execute_script": "run_python_script",
            "run_python": "run_python_script",
            "check_system": "system_status",
            "system_health": "system_status",
            "check_battery": "system_status",
            "launch_app": "open_application",
            "open_app": "open_application",
            "check_email": "check_emails",
            "read_emails": "check_emails",
            "fetch_emails": "check_emails",
            "get_emails": "check_emails",
            "send_mail": "send_email",
            "compose_email": "send_email",
            "play_music": "play_on_youtube",
            "play_song": "play_on_youtube",
            "play_video": "play_on_youtube",
            "youtube": "play_on_youtube",
            "open_website": "open_url",
            "open_browser": "open_url",
            "close_app": "close_application",
            "close_window": "close_application",
            "close_tab": "close_application",
            "close_youtube": "close_application",
            "stop_video": "close_application",
            "skip_ad": "media_control",
            "skip_ads": "media_control",
            "skip_song": "media_control",
            "skip_video": "media_control",
            "pause_music": "media_control",
            "resume_music": "media_control",
            "next_song": "media_control",
            "next_video": "media_control",
            "edit_file": "edit_workspace_file",
            "replace_code": "edit_workspace_file",
            "patch_file": "edit_workspace_file",
            "run_command": "execute_command",
            "run_shell": "execute_command",
            "run_terminal": "execute_command",
            "terminal": "execute_command",
            "bash": "execute_command",
            "cmd": "execute_command",
            "shell": "execute_command",
            "inspect_code": "read_code_definitions",
            "code_outline": "read_code_definitions",
            "learn_skill": "learn_lesson",
            "save_lesson": "learn_lesson",
            "record_learning": "learn_lesson",
            "host_website": "start_local_server",
            "serve_website": "start_local_server",
            "host_local_server": "start_local_server",
            "run_server": "start_local_server",
            "start_server": "start_local_server",
            "serve": "start_local_server",
            "stop_server": "stop_local_server",
            "stop_hosting": "stop_local_server",
            "close_server": "stop_local_server",
            "kill_server": "stop_local_server",
            "shutdown_server": "stop_local_server",
            "search_notes": "search_vault",
            "search_second_brain": "search_vault",
            "query_vault": "search_vault",
            "save_note": "add_to_vault",
            "create_note": "add_to_vault",
            "add_note": "add_to_vault",
            "list_notes": "list_vault_documents",
            "show_vault": "list_vault_documents",
            "heartbeat": "trigger_proactive_check",
            "check_heartbeat": "trigger_proactive_check",
            "remind_me": "set_reminder",
            "add_reminder": "set_reminder",
            "set_timer": "set_reminder",
            "timer": "set_reminder",
            "show_reminders": "list_reminders",
            "get_reminders": "list_reminders",
            "look_at_screen": "see_screen",
            "inspect_screen": "see_screen",
            "read_screen": "see_screen",
            "check_screen": "see_screen",
            "screen_capture": "see_screen",
            "screen": "see_screen",
            "look_at_camera": "see_camera",
            "check_camera": "see_camera",
            "inspect_camera": "see_camera",
            "webcam": "see_camera",
            "camera": "see_camera",
            "switch_voice": "change_voice",
            "set_voice": "change_voice",
            "voice": "change_voice",
            "weather": "get_weather",
            "forecast": "get_weather",
            "check_weather": "get_weather",
            "crypto": "get_crypto_price",
            "bitcoin": "get_crypto_price",
            "crypto_price": "get_crypto_price",
            "exchange_rate": "convert_currency",
            "currency": "convert_currency",
            "convert": "convert_currency",
            "define": "get_word_definition",
            "dictionary": "get_word_definition",
            "word_meaning": "get_word_definition",
            "joke": "get_random_joke",
            "tell_joke": "get_random_joke",
            "quote": "get_inspirational_quote",
            "search_all": "deep_search",
            "find_all": "deep_search",
            "global_search": "deep_search",
            "vscode": "open_vscode",
            "code_editor": "open_vscode",
            "cascade": "open_vscode",
            "start_cascade": "open_vscode",
            "browse": "browse_web",
            "scrape": "browse_web",
            "read_page": "browse_web",
            "read_webpage": "browse_web",
            "fetch_webpage": "browse_web",
            "deep_research": "search_and_extract",
            "web_research": "search_and_extract",
            "download_file": "download_web_file",
            "download": "download_web_file",
            "multi_agent": "hive_mind",
            "subagents": "hive_mind",
            "sub_agents": "hive_mind",
            "hive": "hive_mind",
        }
        name = aliases.get(raw_name, raw_name)
        self.last_tool_called = name

        # Flexible argument normalization
        if name == "change_voice":
            if "voice" in args and "voice_name" not in args:
                args["voice_name"] = args.pop("voice")
            elif "name" in args and "voice_name" not in args:
                args["voice_name"] = args.pop("name")
        elif name == "get_weather":
            if "location" in args and "city" not in args:
                args["city"] = args.pop("location")
            elif "place" in args and "city" not in args:
                args["city"] = args.pop("place")
        elif name == "get_crypto_price":
            if "crypto" in args and "coin" not in args:
                args["coin"] = args.pop("crypto")
            elif "currency" in args and "coin" not in args:
                args["coin"] = args.pop("currency")
            elif "name" in args and "coin" not in args:
                args["coin"] = args.pop("name")
        elif name == "get_word_definition":
            if "query" in args and "word" not in args:
                args["word"] = args.pop("query")
            elif "term" in args and "word" not in args:
                args["word"] = args.pop("term")
        elif name in ("write_workspace_file", "read_workspace_file"):
            if "filename" in args and "filepath" not in args:
                args["filepath"] = args.pop("filename")
            elif "path" in args and "filepath" not in args:
                args["filepath"] = args.pop("path")
            elif "file" in args and "filepath" not in args:
                args["filepath"] = args.pop("file")
            if name == "write_workspace_file" and "content" not in args:
                for k in ("code", "script", "text", "body", "data", "source"):
                    if k in args:
                        args["content"] = args.pop(k)
                        break
        elif name == "run_python_script":
            if "filename" in args and "script_path" not in args:
                args["script_path"] = args.pop("filename")
            elif "path" in args and "script_path" not in args:
                args["script_path"] = args.pop("path")
            elif "filepath" in args and "script_path" not in args:
                args["script_path"] = args.pop("filepath")
        elif name == "open_application":
            if "name" in args and "app_name" not in args:
                args["app_name"] = args.pop("name")
        elif name == "close_application":
            if "name" in args and "app_name" not in args:
                args["app_name"] = args.pop("name")
            elif "target" in args and "app_name" not in args:
                args["app_name"] = args.pop("target")
        elif name == "media_control":
            if "command" in args and "action" not in args:
                args["action"] = args.pop("command")
            elif "act" in args and "action" not in args:
                args["action"] = args.pop("act")
        elif name == "edit_workspace_file":
            if "target" in args and "target_snippet" not in args:
                args["target_snippet"] = args.pop("target")
            if "replacement" in args and "replacement_snippet" not in args:
                args["replacement_snippet"] = args.pop("replacement")
            if "filename" in args and "filepath" not in args:
                args["filepath"] = args.pop("filename")
            elif "path" in args and "filepath" not in args:
                args["filepath"] = args.pop("path")
        elif name == "execute_command":
            if "cmd" in args and "command" not in args:
                args["command"] = args.pop("cmd")
        elif name == "read_code_definitions":
            if "filename" in args and "filepath" not in args:
                args["filepath"] = args.pop("filename")
            elif "path" in args and "filepath" not in args:
                args["filepath"] = args.pop("path")
        elif name == "play_on_youtube":
            if "song" in args and "query" not in args:
                args["query"] = args.pop("song")
            elif "title" in args and "query" not in args:
                args["query"] = args.pop("title")
            elif "name" in args and "query" not in args:
                args["query"] = args.pop("name")
            elif "video" in args and "query" not in args:
                args["query"] = args.pop("video")
        elif name == "open_url":
            if "link" in args and "url" not in args:
                args["url"] = args.pop("link")
            elif "website" in args and "url" not in args:
                args["url"] = args.pop("website")
        elif name in ("see_screen", "see_camera"):
            if "query" in args and "prompt" not in args:
                args["prompt"] = args.pop("query")
            elif "question" in args and "prompt" not in args:
                args["prompt"] = args.pop("question")
            elif "instruction" in args and "prompt" not in args:
                args["prompt"] = args.pop("instruction")
            elif "text" in args and "prompt" not in args:
                args["prompt"] = args.pop("text")

        fn = TOOL_REGISTRY.get(name)
        if fn is None:
            return f"Error: unknown tool '{raw_name}'"
        try:
            return str(fn(**args))
        except Exception as e:
            return f"Error running tool '{name}': {e}"

    def chat_stream(self, user_message: str, on_tool_event=None):
        """
        Streaming generator that yields sentences as they are generated.
        Executes tool calls silently in the background (or reports them via on_tool_event)
        before streaming final conversational speech.
        """
        self.last_tool_called = None
        self.memory.add("user", user_message)

        # Z.A.I.N.E acts as the primary conversational persona and orchestrator,
        # delegating heavy code generation and debugging to code_assistant (Qwen2.5-Coder).
        active_model = MODEL_NAME

        system_prompt = build_system_prompt(self.memory.get_persistent_context(current_prompt=user_message))
        messages = [{"role": "system", "content": system_prompt}] + self.memory.get_messages()

        max_tool_hops = 6  # Allows write -> run -> debug -> verify loops
        hops = 0
        executed_tool_history = []

        while hops < max_tool_hops:
            payload = {
                "model": active_model,
                "messages": messages,
                "stream": True,
                "options": {
                    "num_predict": 1024,
                    "temperature": 0.4,
                },
            }
            try:
                resp = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60)
                resp.raise_for_status()
            except Exception as e:
                # Fallback to base model if specialized coder model is unavailable
                if active_model != MODEL_NAME:
                    try:
                        payload["model"] = MODEL_NAME
                        resp = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120)
                        resp.raise_for_status()
                        active_model = MODEL_NAME
                    except Exception as fallback_e:
                        err_msg = f"I couldn't reach my reasoning model ({fallback_e}). Please check Ollama."
                        yield err_msg
                        self.memory.add("assistant", err_msg)
                        return
                else:
                    err_msg = f"I couldn't reach my reasoning model ({e}). Please check Ollama."
                    yield err_msg
                    self.memory.add("assistant", err_msg)
                    return

            full_content = ""
            sentence_buffer = ""
            is_tool_candidate = False
            checked_prefix = False

            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue
                token = chunk.get("message", {}).get("content", "")
                if not token:
                    continue

                full_content += token
                sentence_buffer += token

                if not checked_prefix:
                    stripped = full_content.strip()
                    if stripped.startswith("{") or "```" in stripped or '"tool"' in stripped:
                        is_tool_candidate = True
                    if len(stripped) >= 6:
                        checked_prefix = True

                # If not a tool call, stream sentences in real time
                if not is_tool_candidate:
                    # Check for sentence end punctuation followed by whitespace or line break
                    for punct in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
                        if punct in sentence_buffer:
                            parts = sentence_buffer.split(punct, 1)
                            sentence = (parts[0] + punct[0]).strip()
                            if sentence:
                                yield sentence
                            sentence_buffer = parts[1]
                            break

            # Stream finished for this hop — check for tool call(s)
            tool_calls = self._try_parse_tool_calls(full_content)
            if tool_calls:
                tool_feedbacks = []
                has_error = False
                for tc in tool_calls:
                    tname = tc.get("tool", "")
                    self.last_tool_called = tname
                    targs = tc.get("args", {})
                    if on_tool_event:
                        try:
                            on_tool_event("start", tname, targs)
                        except Exception:
                            pass
                    tool_result = self._execute_tool(tc)
                    if on_tool_event:
                        try:
                            on_tool_event("done", tname, tool_result)
                        except Exception:
                            pass
                    executed_tool_history.append({"tool": tname, "args": targs, "result": tool_result})
                    tool_feedbacks.append(f"[TOOL RESULT for {tname}]: {tool_result}")
                    if any(m in tool_result for m in ("Exit code:", "Error:", "Traceback", "SyntaxError", "NameError")):
                        has_error = True

                if has_error and hops < max_tool_hops - 1:
                    tool_feedbacks.append("[SYSTEM NOTE]: An error or bug occurred during execution. Inspect the error above, use edit_workspace_file or write_workspace_file to fix it, and re-run to verify before answering.")

                messages.append({"role": "assistant", "content": full_content})
                messages.append({"role": "user", "content": "\n".join(tool_feedbacks)})
                hops += 1
                continue
            else:
                # Final conversational turn: flush any remaining words in buffer
                remaining = sentence_buffer.strip()
                if remaining and not is_tool_candidate:
                    yield remaining
                elif is_tool_candidate and full_content.strip() and not tool_calls:
                    # Case where it was thought to be a tool call but wasn't
                    yield full_content.strip()

                self.memory.add("assistant", full_content)

                # Trigger continuous experiential learning reflection in background
                try:
                    from memory import reflect_on_task_async
                    reflect_on_task_async(user_message, executed_tool_history, full_content, model_name=MODEL_NAME)
                except Exception:
                    pass

                return

    def chat(self, user_message: str, on_tool_event=None) -> str:
        """Synchronous chat returning the complete reply string."""
        parts = []
        for sentence in self.chat_stream(user_message, on_tool_event=on_tool_event):
            parts.append(sentence)
        if parts:
            return " ".join(parts)
        # Fallback to last assistant turn in memory if generator yielded empty
        history = self.memory.get_messages()
        if history and history[-1]["role"] == "assistant":
            return history[-1]["content"]
        return "I'm here."

