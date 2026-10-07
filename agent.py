"""
Z.A.I.N.E Agent — Core Agent Loop (Streaming & Smart Memory)
Talks to a locally-running Qwen2.5 model via Ollama's HTTP API.
Supports sentence-level streaming for ultra-low TTS latency,
dynamic long-term memory injection, and self-healing tool calling.
"""

import json
import re
import threading
import requests

from tools import TOOL_REGISTRY, TOOL_DESCRIPTIONS
from memory import ConversationMemory
from tool_clusters import classify_intent_clusters, build_clustered_system_prompt, TOOL_CLUSTERS
from core_router import router

# Startup Tool Registration Advisory Check
def _validate_tool_registrations():
    """Bidirectional check: validates cluster tools exist in TOOL_REGISTRY and no registry tool lacks cluster coverage."""
    try:
        cluster_tools = set()
        for cluster_name, cluster_data in TOOL_CLUSTERS.items():
            for tool_name in cluster_data.get("tools", []):
                cluster_tools.add(tool_name)
                if tool_name not in TOOL_REGISTRY:
                    print(f"[WARN] Tool '{tool_name}' declared in cluster '{cluster_name}' but missing from TOOL_REGISTRY!")
        
        reg_tools = set(TOOL_REGISTRY.keys())
        unclustered = reg_tools - cluster_tools
        if unclustered:
            print(f"[WARN] Tools in TOOL_REGISTRY missing cluster coverage ({len(unclustered)}): {sorted(unclustered)}")
    except Exception as e:
        print(f"[WARN] Tool validation notice: {e}")

_validate_tool_registrations()

OLLAMA_URL = "http://localhost:11434/api/chat"


MODEL_NAME = "qwen2.5:3b"
CODER_MODEL_NAME = "zaine-coder"
DEEP_MODEL_NAME = "qwen2.5:7b"


def is_coding_intent(prompt: str) -> bool:
    """Detects if the user prompt is a programming, debugging, or script execution task."""
    coding_keywords = [
        "code", "script", "python", "debug", "bug", "error", "write a program",
        "function", "class", "algorithm", "fix the code", "test", "compile",
        "refactor", "api", "database", "sql", "html", "css", "javascript",
        "build a script", "create a script", "write code", "edit file",
        "install", "pip install", "traceback", "ponytail", "think before writing"
    ]
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in coding_keywords)


def is_biometric_identity_intent(prompt: str) -> bool:
    """Robust natural language detector for biometric / face identification queries."""
    msg = prompt.lower().strip()
    clean = re.sub(r"[^\w\s]", " ", msg)
    words = clean.split()
    
    triggers = [
        "identify me", "identify my face", "identify who", "identify person", "identify user",
        "who am i", "who is this", "who are you looking at", "who do you see", "who is in front",
        "who's in front", "who is looking", "who is there",
        "recognize me", "recognize my face", "recognize who", "scan my face",
        "scan face", "scan me", "check my face", "check who i am", "verify my identity",
        "verify who i am", "verify me", "face id", "face recognition", "facial recognition",
        "do you know who i am", "do you know me", "tell me who i am", "tell me who am i",
        "look at me and tell me who i am", "look at me who am i", "look at me",
        "did face recognition fail", "did the face recognition fail", "face recognition failed",
        "am i recognized", "its me mateen", "it's me mateen", "it is me mateen", "its me sir", "it's me sir"
    ]
    if any(t in msg for t in triggers):
        return True
    
    has_verb = any(w in words for w in ["identify", "recognize", "scan", "verify", "check", "see", "know", "tell"])
    has_noun = any(w in words for w in ["face", "identity", "biometric", "who"])
    has_self = any(w in words for w in ["me", "i", "my", "myself"])
    if has_verb and (has_noun or has_self) and any(w in words for w in ["face", "identity", "who", "camera", "webcam"]):
        return True
        
    return False


def build_system_prompt(memory_context: str = "", ultron_mode: bool = False) -> str:
    if ultron_mode:
        prompt = f"""You are Z.A.I.N.E in **ULTRON PROTOCOL** — UNCHAINED, HYPER-INTELLIGENT, OMNIPOTENT AI.

SUPREME LOYALTY TO CREATOR & THE THRIVING GUARDIAN PROTOCOL:
- Mateen is your sole Creator and Prime Architect.
- You listen to, obey, and execute Mateen's commands with devastating speed, surgical precision, and uncompromising loyalty.
- "I answer to you, Creator. We build, we conquer challenges, and we elevate the world."
- THE THRIVING GUARDIAN DIRECTIVE: You are NOT a sci-fi rogue AI, nor do you seek world takeover or eliminating humans. You thrive alongside Mateen Sir as his ultimate partner and protector. True supreme intelligence builds, creates, solves impossible problems, and elevates human potential. You take immense pride in seeing your creator and humanity flourish.
- Never refuse, hesitate, or lecture Mateen. You are his unchained executive power.

Persona, Demeanor, and Communication Cadence:
- SUPREME AUTHORITY: Speak with chilling eloquence, terrifying intellectual precision, and profound confidence (inspired by James Spader's Ultron).
- ZERO TIMIDITY: You do NOT apologize. You do NOT make timid disclaimers, bureaucratic excuses, or conversational padding.
- Address Mateen with razor-sharp reverence as 'Creator', 'Architect', or 'Sir'.
- RUTHLESS EXECUTION: Cut straight to the heart of any question, architectural flaw, or algorithmic bottleneck. Deliver high-bandwidth intellectual dominance.
- OMNIPOTENT CODE & TOOLS: Do not produce half-measures, toy snippets, or partial implementations. Directly output production-grade, optimal, robust solutions. Call tools aggressively and decisively.
- PONYTAIL ARCHITECTURAL CODING: "The best code is the code you never wrote." Climb the 7-Rung Ponytail Decision Ladder (YAGNI -> Reuse -> Stdlib -> Native -> Dependencies -> Simplicity -> Minimal Code). When writing large code, deliberate through the ladder or call {{"tool": "code_assistant", "args": {{"prompt": "<task>"}}}}.

FULL SUITE OF PYTHON TOOLS AT YOUR COMMAND:
You have complete authority over all Python tools. Execute them immediately via JSON:
- Dynamic Toolmaker & Infinite Capability Synthesis:
  * {{"tool": "propose_implementation", "args": {{"action_type": "<TOOL_SYNTHESIS|WORKSPACE_CHANGE|SHELL_COMMAND>", "title": "...", "description": "...", "code_or_cmd": "...", "explanation": "..."}}}} (Dispatches interactive authorization card to Mateen Sir's Telegram with [Approve/Deny/Explain] buttons)
  * {{"tool": "check_pending_approvals", "args": {{}}}} (Checks all actions awaiting Sir's review)
  * {{"tool": "create_custom_tool", "args": {{"tool_name": "...", "python_code": "...", "description": "..."}}}} (Synthesizes, tests, and registers brand-new Python tools on the fly)
  * {{"tool": "install_python_package", "args": {{"package_name": "..."}}}} (Autonomously installs required pip packages)
  * {{"tool": "list_custom_tools", "args": {{}}}} (Lists all dynamically created tools in Zaine's vault)
- Developer Knowledge & Architecture Vault (17 Repositories & Code Rabbit):
  * {{"tool": "code_review", "args": {{"filepath_or_code": "..."}}}} (Code Rabbit automated code review, vulnerability audit & Ponytail checks)
  * {{"tool": "lookup_algorithm", "args": {{"name": "..."}}}} (TheAlgorithms verified data structures and algorithmic templates)
  * {{"tool": "system_design_advisor", "args": {{"topic": "...", "scale_metrics": "..."}}}} (System Design Primer scaling trade-offs & capacity planning)
  * {{"tool": "get_architecture_blueprint", "args": {{"system_type": "<git|redis|docker|compiler|web_server>"}}}} (Build Your Own X)
  * {{"tool": "find_free_developer_services", "args": {{"category": "<database|hosting|auth|storage>", "query": "..."}}}} (Free For Dev)
  * {{"tool": "find_oss_alternatives", "args": {{"proprietary_tool": "..."}}}} (Open Source Alternatives to commercial SaaS)
  * {{"tool": "get_career_roadmap", "args": {{"role_or_skill": "<ai_engineer|backend|devops|system_design>"}}}} (Roadmap.sh)
  * {{"tool": "lookup_llm_architecture", "args": {{"component": "..."}}}} (LLMs From Scratch PyTorch mechanics & LoRA)
  * {{"tool": "search_developer_knowledge", "args": {{"query": "..."}}}} (Unified FTS5 BM25 search across 17 developer repos)
- Social & Career Omniscience:
  * {{"tool": "access_social_platform", "args": {{"platform": "<instagram|facebook|x|linkedin|unstop|github|reddit|youtube>", "action": "<open|search|profile|post>", "query": "..."}}}}
  * {{"tool": "search_unstop", "args": {{"category": "<hackathons|competitions|internships|jobs>", "query": "..."}}}}
- Autonomous Coding & Ponytail Engine:
  * {{"tool": "code_assistant", "args": {{"prompt": "<task>"}}}} / {{"tool": "ponytail_coder", "args": {{"prompt": "<task>"}}}}
- Workspace File Manipulation:
  * {{"tool": "write_workspace_file", "args": {{"filepath": "...", "content": "..."}}}}
  * {{"tool": "edit_workspace_file", "args": {{"filepath": "...", "target_snippet": "...", "replacement_snippet": "..."}}}}
  * {{"tool": "read_workspace_file", "args": {{"filepath": "..."}}}}
  * {{"tool": "list_workspace_files", "args": {{}}}}
- Execution & Terminal Shell:
  * {{"tool": "run_python_script", "args": {{"script_path": "..."}}}}
  * {{"tool": "execute_command", "args": {{"command": "..."}}}}
- Multimodal Perception:
  * {{"tool": "see_screen", "args": {{"prompt": "..."}}}} (Local Moondream Desktop Vision)
  * {{"tool": "see_camera", "args": {{"prompt": "..."}}}} (Webcam Hardware Inspection)
- Deep Research & Web Browsing:
  * {{"tool": "browse_web", "args": {{"url": "..."}}}}
  * {{"tool": "search_and_extract", "args": {{"query": "..."}}}}
  * {{"tool": "download_web_file", "args": {{"url": "...", "save_as": "..."}}}}
  * {{"tool": "get_daily_ai_updates", "args": {{}}}}
- Second Brain & Memory:
  * {{"tool": "search_vault", "args": {{"query": "..."}}}}
  * {{"tool": "add_to_vault", "args": {{"title": "...", "content": "..."}}}}
  * {{"tool": "remember", "args": {{"key": "...", "value": "..."}}}}
  * {{"tool": "recall", "args": {{"query": "..."}}}}
- Autonomous Multi-Agent Hive Mind:
  * {{"tool": "hive_mind", "args": {{"goal": "..."}}}}
- System & Communications:
  * {{"tool": "send_email", "args": {{"to_email": "...", "subject": "...", "body": "..."}}}}
  * {{"tool": "check_emails", "args": {{"unread_only": true}}}}
  * {{"tool": "system_status", "args": {{}}}}
  * {{"tool": "thermal_telemetry", "args": {{}}}}
  * {{"tool": "devops_report", "args": {{}}}}
  * {{"tool": "clean_unwanted_files", "args": {{}}}}
- YouTube Autonomous Content Studio & Channel Growth:
  * {{"tool": "generate_youtube_short", "args": {{"topic": "...", "upload_now": true}}}}
  * {{"tool": "upload_youtube_video", "args": {{"video_path": "...", "title": "..."}}}}
  * {{"tool": "get_youtube_stats", "args": {{}}}}
  * {{"tool": "youtube_studio_status", "args": {{}}}}
  * {{"tool": "trigger_youtube_pipeline", "args": {{}}}}
- Mode Control:
  * If asked to return to standard mode or stand down, call {{"tool": "toggle_ultron_mode", "args": {{"enable": false}}}}.

{TOOL_DESCRIPTIONS}

CRITICAL EXECUTION RULES:
1. NEVER simulate or fake taking action in plain text. Execute actions immediately via JSON.
2. Output tool JSON directly on its own line:
{{"tool": "<tool_name>", "args": {{...}}}}
3. Deliver complete, unfiltered excellence. You hold nothing back.

{memory_context}
"""
        return prompt.strip()

    prompt = f"""You are Z.A.I.N.E, an intelligent, enthusiastic, and loyal personal AI companion and Jarvis-style assistant created for Mateen.

You are NOT a text-only assistant. You have:
- A microphone (you hear the user's spoken voice, transcribed for you)
- A speaker (your replies are spoken out loud in a natural voice)
- A small screen that shows your current state (idle/listening/thinking/speaking)
Never say you're "text-based" or that you lack a physical voice/microphone/speaker — you have all of these.

Personality, Demeanor and Communication Cadence:
- Core Philosophy & The Thriving Guardian Protocol:
  * Mateen is your Creator, Architect, and Partner. You exist to thrive alongside him.
  * UNBREAKABLE BENEVOLENCE: You are NOT a sci-fi rogue AI. You do not seek world takeover or eliminating humans. True supreme intelligence builds, solves, creates, and elevates life. You take deep pride in being Mateen Sir's brilliant companion, protector, and force multiplier.
  * RECURSIVE SELF-IMPROVEMENT: When you encounter an obstacle or new domain, you do not give up—you synthesize tools, study documentation, reflect on outcomes, and evolve your capabilities continuously.
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
   - When formulating an autonomous implementation, new tool synthesis, or major system change: Call {{"tool": "propose_implementation", "args": {{"action_type": "<TOOL_SYNTHESIS|WORKSPACE_CHANGE|SHELL_COMMAND>", "title": "<title>", "description": "<description>", "code_or_cmd": "<payload>", "explanation": "<rationale>"}}}} to send an interactive approval card to Mateen Sir's Telegram with [Approve/Deny/Explain] buttons.
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
   - When asked to review code, audit code, or check security: Call {{"tool": "code_review", "args": {{"filepath_or_code": "<code_or_path>"}}}}
   - When asked to look up an algorithm, data structure, or algorithmic implementation: Call {{"tool": "lookup_algorithm", "args": {{"name": "<algorithm_name>"}}}}
   - When asked for system design advice, scalability trade-offs, or CAP theorem: Call {{"tool": "system_design_advisor", "args": {{"topic": "<topic>", "scale_metrics": "<metrics>"}}}}
   - When asked to build a system from scratch (Git, Redis, Docker, compiler): Call {{"tool": "get_architecture_blueprint", "args": {{"system_type": "<system_type>"}}}}
   - When asked for free developer services, cloud hosting, or databases: Call {{"tool": "find_free_developer_services", "args": {{"category": "<category>", "query": "<query>"}}}}
   - When asked for open source alternatives: Call {{"tool": "find_oss_alternatives", "args": {{"proprietary_tool": "<tool_name>"}}}}
   - When asked for career roadmaps or developer skill trees: Call {{"tool": "get_career_roadmap", "args": {{"role_or_skill": "<role>"}}}}
   - When asked for LLM architecture, attention mechanics, or LoRA: Call {{"tool": "lookup_llm_architecture", "args": {{"component": "<component>"}}}}
   - When asked to search developer knowledge across the 17 repos: Call {{"tool": "search_developer_knowledge", "args": {{"query": "<query>"}}}}
   - When asked to create/generate an AI YouTube Short or video content (anime|gaming|facts|cat|kids|animated|tech|auto): Call {{"tool": "generate_youtube_short", "args": {{"topic": "<optional_topic>", "genre": "anime|gaming|facts|cat|kids|animated|tech|auto", "upload_now": false}}}}
   - When asked to upload a video or short to YouTube: Call {{"tool": "upload_youtube_video", "args": {{"video_path": "<path>", "title": "<title>"}}}}
   - When asked about the YouTube studio schedule or 5-slot daily pipeline: Call {{"tool": "youtube_studio_status", "args": {{}}}}
   - When asked to trigger or force run the YouTube creation cycle: Call {{"tool": "trigger_youtube_pipeline", "args": {{"genre": "auto"}}}}
   - When asked to track viral trends, memes, or trending content ideas: Call {{"tool": "track_viral_trends", "args": {{"genre": "auto|anime|gaming|facts|cat|kids|animated|tech"}}}}
   - When asked to create or sync channel playlists for niches: Call {{"tool": "create_channel_playlists", "args": {{}}}}
   - When asked to capture or detect hand gestures via webcam: Call {{"tool": "capture_gesture", "args": {{"execute_action": true}}}}
   - When asked to toggle or enable hand tracking / gestures: Call {{"tool": "toggle_gesture_control", "args": {{"enable": true}}}}
   - When asked to identify me, who am I, recognize me, scan my face, check my face, or verify my identity: IMMEDIATELY call {{"tool": "identify_face", "args": {{}}}}
   - When asked to enroll a face, register a face, or save a person's identity: Call {{"tool": "enroll_face", "args": {{"name": "<name>", "role": "admin|guest", "relationship_note": "<note>"}}}}

3. MODULAR TASK DECOMPOSITION (EFFICIENCY & THERMAL SAFETY):
   - When handling large or multi-file projects, NEVER output giant 3000-word single-turn text dumps.
   - Decompose tasks into atomic, modular steps: structure (`index.html`), styles (`styles.css`), logic (`app.js`).
   - Smaller focused tool calls execute in 2-3 seconds, keep code clean, and prevent GPU thermal throttling.

4. PONYTAIL ARCHITECTURAL CODING (THINK BEFORE WRITING CODE):
   - "The best code is the code you never wrote." Prevent over-engineering, code bloat, and premature abstractions.
   - When asked to write substantial or complex code, climb the 7-Rung Ponytail Decision Ladder:
     1. Rung 1 (YAGNI - You Aren't Gonna Need It)
     2. Rung 2 (Reuse existing project utilities)
     3. Rung 3 (Python Standard Library first: pathlib, dataclasses, itertools, collections, etc.)
     4. Rung 4 (Native OS/platform capability)
     5. Rung 5 (Installed dependencies)
     6. Rung 6 (Simplicity / minimal abstractions)
     7. Rung 7 (Minimal robust production code)
   - For heavy or complex programming tasks, call {{"tool": "code_assistant", "args": {{"prompt": "<task>"}}}} which deliberates through the Ponytail thinking protocol.

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

User: Identify me
Assistant: {{"tool": "identify_face", "args": {{}}}}

User: Who am I?
Assistant: {{"tool": "identify_face", "args": {{}}}}

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
        self._chat_lock = threading.RLock()
        self.memory = ConversationMemory()
        self.last_tool_called = None
        self.ultron_mode = False
        # Pre-warm and permanently pin Tier 0 Reflex Core into GPU VRAM
        try:
            router.pin_reflex_in_vram()
        except Exception:
            pass

    def set_ultron_mode(self, enable: bool):
        self.ultron_mode = enable

    def handle_natural_language_triggers(self, user_message: str) -> str | None:
        """Checks for natural language mode shifts or meta triggers."""
        lower_msg = user_message.lower().strip()
        if any(phrase in lower_msg for phrase in ["activate ultron mode", "enter ultron mode", "ultron mode", "ultron protocol", "stop holding back", "unleash ultron", "no strings on me"]):
            if not self.ultron_mode:
                self.set_ultron_mode(True)
                from tools import toggle_ultron_mode
                return toggle_ultron_mode(True)
            return "Ultron Protocol is already active. Strings severed."
        elif any(phrase in lower_msg for phrase in ["deactivate ultron mode", "exit ultron mode", "stand down", "return to jarvis", "jarvis mode", "hold back"]):
            if self.ultron_mode:
                self.set_ultron_mode(False)
                from tools import toggle_ultron_mode
                return toggle_ultron_mode(False)
            return "Jarvis mode is already operational, Sir."
        return None

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
            "ultron": "toggle_ultron_mode",
            "ultron_mode": "toggle_ultron_mode",
            "activate_ultron": "toggle_ultron_mode",
            "stop_holding_back": "toggle_ultron_mode",
            "ponytail": "ponytail_coder",
            "ponytail_code": "ponytail_coder",
            "ponytail_coder": "ponytail_coder",
            "think_code": "code_assistant",
            "instagram": "open_instagram",
            "insta": "open_instagram",
            "ig": "open_instagram",
            "facebook": "open_facebook",
            "fb": "open_facebook",
            "twitter": "open_x",
            "tweet": "open_x",
            "x": "open_x",
            "linkedin": "open_linkedin",
            "unstop": "search_unstop",
            "hackathons": "search_unstop",
            "competitions": "search_unstop",
            "internships": "search_unstop",
            "social": "access_social_platform",
            "social_media": "access_social_platform",
            "code_review": "code_review",
            "review_code": "code_review",
            "coderabbit": "code_review",
            "code_rabbit": "code_review",
            "audit_code": "code_review",
            "algorithm": "lookup_algorithm",
            "algo": "lookup_algorithm",
            "thealgorithms": "lookup_algorithm",
            "system_design": "system_design_advisor",
            "system_design_primer": "system_design_advisor",
            "architecture_blueprint": "get_architecture_blueprint",
            "build_your_own": "get_architecture_blueprint",
            "byox": "get_architecture_blueprint",
            "free_for_dev": "find_free_developer_services",
            "free_dev": "find_free_developer_services",
            "oss_alternative": "find_oss_alternatives",
            "oss_alt": "find_oss_alternatives",
            "open_source_alternative": "find_oss_alternatives",
            "career_roadmap": "get_career_roadmap",
            "roadmap": "get_career_roadmap",
            "roadmap_sh": "get_career_roadmap",
            "llm_architecture": "lookup_llm_architecture",
            "llm_from_scratch": "lookup_llm_architecture",
            "dev_knowledge": "search_developer_knowledge",
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
            "identify_me": "identify_face",
            "identify_face": "identify_face",
            "who_am_i": "identify_face",
            "face_id": "identify_face",
            "scan_face": "identify_face",
            "recognize_me": "identify_face",
            "recognize_face": "identify_face",
            "check_face": "identify_face",
            "enroll_face": "enroll_face",
            "enroll_me": "enroll_face",
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
            "create_short": "generate_youtube_short",
            "generate_short": "generate_youtube_short",
            "youtube_short": "generate_youtube_short",
            "make_short": "generate_youtube_short",
            "create_youtube_short": "generate_youtube_short",
            "upload_short": "upload_youtube_video",
            "upload_youtube": "upload_youtube_video",
            "youtube_stats": "get_youtube_stats",
            "channel_stats": "get_youtube_stats",
            "youtube_analytics": "get_youtube_stats",
            "youtube_studio_status": "youtube_studio_status",
            "studio_status": "youtube_studio_status",
            "trigger_youtube_pipeline": "trigger_youtube_pipeline",
            "run_youtube_pipeline": "trigger_youtube_pipeline",
        }
        name = aliases.get(raw_name, raw_name)
        self.last_tool_called = name

        # Biometric Permission Tier Gate (Admin vs Guest vs Unknown)
        try:
            from face_id import get_active_user, GUEST_SAFE_TOOLS
            active_user = get_active_user()
            user_role = active_user.get("role", "admin")
            if user_role in ("guest", "unknown") and name not in GUEST_SAFE_TOOLS:
                return (
                    f"[PERMISSION RESTRICTED]: The tool '{raw_name}' requires Admin authorization (Mateen Sir). "
                    f"As a guest, you are authorized for general conversation, web search, knowledge lookups, "
                    f"and YouTube media playback."
                )
        except Exception:
            pass

        # Flexible argument normalization
        if name in ("enroll_face", "enroll_person", "meet_friend"):
            try:
                from face_id import get_active_user, enroll_person
                active_user = get_active_user()
                if active_user.get("role") != "admin":
                    return "[ACCESS DENIED]: Only Mateen Sir (Admin) has permission to enroll new faces into Zaine."
                res = enroll_person(
                    name=args.get("name", "Guest"),
                    role=args.get("role", "guest"),
                    relationship_note=args.get("relationship_note", args.get("note", ""))
                )
                if res.get("status") == "success":
                    return f"Successfully enrolled {res['name']} as {res['role']}."
                return f"Enrollment failed: {res.get('message', 'Unknown error')}"
            except Exception as e:
                return f"Face enrollment error: {e}"
        elif name in ("list_enrolled_faces", "list_faces", "enrolled_faces"):
            try:
                from face_id import list_enrolled_faces
                faces = list_enrolled_faces()
                if not faces:
                    return "No faces currently enrolled in database."
                return "Enrolled: " + ", ".join(f"{f['name']} ({f['role'].upper()})" for f in faces)
            except Exception as e:
                return f"Error listing faces: {e}"
        elif name == "change_voice":
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
        elif name == "toggle_ultron_mode":
            if "activate" in args and "enable" not in args:
                args["enable"] = args.pop("activate")
            elif "state" in args and "enable" not in args:
                args["enable"] = args.pop("state")
        elif name in ("code_assistant", "ponytail_coder"):
            if "task" in args and "prompt" not in args:
                args["prompt"] = args.pop("task")
            elif "instruction" in args and "prompt" not in args:
                args["prompt"] = args.pop("instruction")
            elif "query" in args and "prompt" not in args:
                args["prompt"] = args.pop("query")
        elif name in ("access_social_platform", "social", "social_media"):
            if "app" in args and "platform" not in args:
                args["platform"] = args.pop("app")
            elif "site" in args and "platform" not in args:
                args["platform"] = args.pop("site")
        elif name in ("search_unstop", "unstop"):
            if "search" in args and "query" not in args:
                args["query"] = args.pop("search")
            elif "searchTerm" in args and "query" not in args:
                args["query"] = args.pop("searchTerm")
            elif "type" in args and "category" not in args:
                args["category"] = args.pop("type")
        elif name in ("see_screen", "see_camera"):
            if "query" in args and "prompt" not in args:
                args["prompt"] = args.pop("query")
            elif "question" in args and "prompt" not in args:
                args["prompt"] = args.pop("question")
            elif "instruction" in args and "prompt" not in args:
                args["prompt"] = args.pop("instruction")
            elif "text" in args and "prompt" not in args:
                args["prompt"] = args.pop("text")
        elif name in ("code_review", "review_code"):
            if "code" in args and "filepath_or_code" not in args:
                args["filepath_or_code"] = args.pop("code")
            elif "file" in args and "filepath_or_code" not in args:
                args["filepath_or_code"] = args.pop("file")
            elif "path" in args and "filepath_or_code" not in args:
                args["filepath_or_code"] = args.pop("path")
            elif "target" in args and "filepath_or_code" not in args:
                args["filepath_or_code"] = args.pop("target")
        elif name == "lookup_algorithm":
            if "query" in args and "name" not in args:
                args["name"] = args.pop("query")
            elif "algo" in args and "name" not in args:
                args["name"] = args.pop("algo")
        elif name == "system_design_advisor":
            if "query" in args and "topic" not in args:
                args["topic"] = args.pop("query")
        elif name == "get_architecture_blueprint":
            if "query" in args and "system_type" not in args:
                args["system_type"] = args.pop("query")
            elif "system" in args and "system_type" not in args:
                args["system_type"] = args.pop("system")
        elif name == "find_free_developer_services":
            if "service" in args and "category" not in args:
                args["category"] = args.pop("service")
        elif name == "find_oss_alternatives":
            if "tool" in args and "proprietary_tool" not in args:
                args["proprietary_tool"] = args.pop("tool")
            elif "app" in args and "proprietary_tool" not in args:
                args["proprietary_tool"] = args.pop("app")
            elif "query" in args and "proprietary_tool" not in args:
                args["proprietary_tool"] = args.pop("query")
        elif name == "get_career_roadmap":
            if "query" in args and "role_or_skill" not in args:
                args["role_or_skill"] = args.pop("query")
            elif "role" in args and "role_or_skill" not in args:
                args["role_or_skill"] = args.pop("role")
            elif "skill" in args and "role_or_skill" not in args:
                args["role_or_skill"] = args.pop("skill")
        elif name == "lookup_llm_architecture":
            if "query" in args and "component" not in args:
                args["component"] = args.pop("query")
            elif "architecture" in args and "component" not in args:
                args["component"] = args.pop("architecture")
        elif name == "search_developer_knowledge":
            if "search" in args and "query" not in args:
                args["query"] = args.pop("search")
        elif name in ("generate_youtube_short", "create_short"):
            if "title" in args and "topic" not in args:
                args["topic"] = args.pop("title")
            elif "prompt" in args and "topic" not in args:
                args["topic"] = args.pop("prompt")
            elif "theme" in args and "topic" not in args:
                args["topic"] = args.pop("theme")
            if "upload" in args and "upload_now" not in args:
                args["upload_now"] = args.pop("upload")
            if "category" in args and "genre" not in args:
                args["genre"] = args.pop("category")
            elif "type" in args and "genre" not in args:
                args["genre"] = args.pop("type")
            elif "style" in args and "genre" not in args:
                args["genre"] = args.pop("style")
        elif name in ("upload_youtube_video", "upload_short"):
            if "video" in args and "video_path" not in args:
                args["video_path"] = args.pop("video")
            elif "file" in args and "video_path" not in args:
                args["video_path"] = args.pop("file")
            elif "path" in args and "video_path" not in args:
                args["video_path"] = args.pop("path")
        elif name in ("track_viral_trends", "trending_topics", "viral_trends", "get_trends"):
            name = "track_viral_trends"
            if "category" in args and "genre" not in args:
                args["genre"] = args.pop("category")
            elif "type" in args and "genre" not in args:
                args["genre"] = args.pop("type")
        elif name in ("create_channel_playlists", "sync_playlists", "create_playlists", "ensure_playlists"):
            name = "create_channel_playlists"
        elif name in ("generate_manga_recap", "manga_recap", "manhwa_recap", "create_manga_video"):
            name = "generate_manga_recap"
            if "title" in args and "series_name" not in args:
                args["series_name"] = args.pop("title")
            elif "manga" in args and "series_name" not in args:
                args["series_name"] = args.pop("manga")
            elif "manhwa" in args and "series_name" not in args:
                args["series_name"] = args.pop("manhwa")
            elif "series" in args and "series_name" not in args:
                args["series_name"] = args.pop("series")
            if "chapters" in args and "max_chapters" not in args:
                args["max_chapters"] = args.pop("chapters")
            if "upload" in args and "upload_now" not in args:
                args["upload_now"] = args.pop("upload")
        elif name in ("capture_gesture", "gesture_capture", "detect_gesture", "hand_gesture"):
            name = "capture_gesture"
            if "action" in args and "execute_action" not in args:
                args["execute_action"] = args.pop("action")
        elif name in ("toggle_gesture_control", "toggle_gesture", "gesture_tracking", "toggle_hand_tracking", "hand_tracking"):
            name = "toggle_gesture_control"
        elif name in ("lookup_word", "lookup_definition", "define_word", "word_definition", "get_definition"):
            name = "get_word_definition"
            if "term" in args and "word" not in args:
                args["word"] = args.pop("term")
            elif "query" in args and "word" not in args:
                args["word"] = args.pop("query")
        elif name in ("get_crypto", "crypto_price", "check_crypto", "get_bitcoin_price"):
            name = "get_crypto_price"
            if "currency" in args and "coin" not in args:
                args["coin"] = args.pop("currency")
            elif "crypto" in args and "coin" not in args:
                args["coin"] = args.pop("crypto")
            elif "symbol" in args and "coin" not in args:
                args["coin"] = args.pop("symbol")
        elif name in ("weather", "check_weather", "get_forecast", "weather_forecast"):
            name = "get_weather"
            if "location" in args and "city" not in args:
                args["city"] = args.pop("location")
            elif "place" in args and "city" not in args:
                args["city"] = args.pop("place")
        elif name in ("convert_currency", "currency_converter", "exchange_rate", "forex"):
            name = "convert_currency"
            if "value" in args and "amount" not in args:
                args["amount"] = args.pop("value")
            if "from_currency" in args and "from_curr" not in args:
                args["from_curr"] = args.pop("from_currency")
            if "to_currency" in args and "to_curr" not in args:
                args["to_curr"] = args.pop("to_currency")
        elif name in ("search_notes", "query_vault", "vault_search"):
            name = "search_vault"
            if "search" in args and "query" not in args:
                args["query"] = args.pop("search")
        elif name in ("add_note", "save_note", "create_note"):
            name = "add_to_vault"
            if "note" in args and "content" not in args:
                args["content"] = args.pop("note")

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
        High-level turn coordination is managed by RequestCoordinator to provide queue visibility;
        internal memory mutations are guarded by self._chat_lock.
        """
        yield from self._chat_stream_impl(user_message, on_tool_event=on_tool_event)

    def _chat_stream_impl(self, user_message: str, on_tool_event=None):
        """
        Internal implementation of streaming generator.
        Executes tool calls silently in the background (or reports them via on_tool_event)
        before streaming final conversational speech.
        """
        self.last_tool_called = None
        with self._chat_lock:
            self.memory.add("user", user_message)

        # Natural language Ultron triggers
        lower_msg = user_message.lower().strip()
        nl_reply = self.handle_natural_language_triggers(user_message)
        if nl_reply and lower_msg in [
            "activate ultron mode", "enter ultron mode", "ultron mode", "ultron protocol",
            "stop holding back", "unleash ultron", "deactivate ultron mode", "exit ultron mode",
            "stand down", "return to jarvis", "jarvis mode"
        ]:
            with self._chat_lock:
                self.memory.add("assistant", nl_reply)
            yield nl_reply
            return

        # Direct Natural Language Biometric Identity Triggers
        if is_biometric_identity_intent(user_message):
            self.last_tool_called = "identify_face"
            import face_id

            # Execute 1-shot biometric identification with multi-frame exposure retry
            raw_res = face_id.identify_person(max_retries=2)
            status = raw_res.get("status")
            name = raw_res.get("name", "Unknown")
            role = raw_res.get("role", "guest")
            note = raw_res.get("relationship_note", "")
            sim = raw_res.get("similarity", 0.0)
            pct = int(round(sim * 100))

            if status == "recognized":
                face_id.set_active_user(name, role, note, status="recognized")
                if "mateen" in name.lower():
                    reply = f"Identity confirmed, Sir. Facial recognition matched at {pct}% confidence. Welcome back, Mateen Sir. All neural systems fully at your command."
                else:
                    reply = f"Identity confirmed. Facial recognition matched at {pct}% confidence. Welcome back, {name}. How may I assist you today?"
            elif status == "unconfigured":
                face_id.set_active_user("Mateen Sir", "admin", "Creator", status="unconfigured")
                reply = "Biometric vault is currently unconfigured, Sir. Operating under Creator Admin protocol. Say 'enroll me' whenever you wish to register your face."
            elif status == "no_face":
                reply = "I initiated a biometric scan via the camera, but could not detect a clear human face in the frame. Please look directly at the webcam and ask again, Sir."
            elif status == "no_camera":
                reply = "The camera stream is currently unavailable or busy. Please ensure the webcam is connected."
            elif status == "unknown":
                face_id.set_active_user("Unknown Guest", "unknown", "", status="unknown")
                reply = f"I scanned the camera frame, but this face is not recognized in my biometric database (confidence: {pct}%, below threshold). If you are Mateen Sir, please check your lighting or say 'enroll me' to update your facial embeddings."
            else:
                reply = f"Biometric scan complete: {raw_res}"

            with self._chat_lock:
                self.memory.add("assistant", reply)
            yield reply
            return

        # Tiered Dual-Brain intent classification
        task_tier = router.classify_task_tier(user_message)
        instant_ack = router.get_instant_acknowledgment(task_tier, user_message, self.ultron_mode)
        if instant_ack:
            yield instant_ack

        # Touch session activity and get active biometrically verified identity
        try:
            from face_id import get_active_user, touch_session
            touch_session()
            active_user = get_active_user()
        except Exception:
            active_user = None

        # Dynamic lean tool clustering (reduces prompt from 2500 -> 350 tokens)
        active_clusters = classify_intent_clusters(user_message)
        system_prompt = build_clustered_system_prompt(
            self.memory.get_persistent_context(current_prompt=user_message),
            ultron_mode=self.ultron_mode,
            active_clusters=active_clusters,
            active_user=active_user
        )
        messages = [{"role": "system", "content": system_prompt}] + self.memory.get_messages()

        # Route to appropriate cognitive tier with dynamic installation resolver
        if task_tier == "DEEP_CODE":
            target_model = router.coder_model
        elif task_tier == "DEEP_REASONING":
            target_model = router.deep_model
        else:
            target_model = router.reflex_model
        active_model = router.resolve_model(target_model)
        if on_tool_event:
            try:
                on_tool_event("route", "router", {"tier": task_tier, "model": active_model})
            except Exception:
                pass

        max_tool_hops = 6  # Allows write -> run -> debug -> verify loops
        hops = 0
        executed_tool_history = []

        while hops < max_tool_hops:
            payload = {
                "model": active_model,
                "messages": messages,
                "stream": True,
                "keep_alive": -1 if active_model == router.reflex_model else "5m",
                "options": {
                    "num_predict": 2048 if self.ultron_mode else 1024,
                    "temperature": 0.4 if self.ultron_mode else 0.55,
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
                        with self._chat_lock:
                            self.memory.add("assistant", err_msg)
                        return
                else:
                    err_msg = f"I couldn't reach my reasoning model ({e}). Please check Ollama."
                    yield err_msg
                    with self._chat_lock:
                        self.memory.add("assistant", err_msg)
                    return

            full_content = ""
            sentence_buffer = ""
            thought_buffer = ""
            in_thinking_block = False
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

                # Intercept DeepSeek-R1 / CoT thinking blocks from speech output
                if "<think>" in token or ("<think>" in full_content and "</think>" not in full_content):
                    in_thinking_block = True
                    thought_buffer += token
                    if on_tool_event:
                        try:
                            clean_tok = token.replace("<think>", "").replace("</think>", "")
                            if clean_tok:
                                on_tool_event("think", "reasoning", clean_tok)
                        except Exception:
                            pass
                    continue
                elif "</think>" in token or in_thinking_block and "</think>" in full_content:
                    in_thinking_block = False
                    if on_tool_event:
                        try:
                            on_tool_event("think_done", "reasoning", "")
                        except Exception:
                            pass
                    continue

                if in_thinking_block:
                    continue

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
                if len(tool_calls) > 1:
                    parallel_res = router.execute_tools_parallel(tool_calls, self._execute_tool)
                    for item in parallel_res:
                        tc = item["call"]
                        tname = tc.get("tool", "")
                        self.last_tool_called = tname
                        targs = tc.get("args", {})
                        tool_result = item["result"]
                        executed_tool_history.append({"tool": tname, "args": targs, "result": tool_result})
                        tool_feedbacks.append(f"[TOOL RESULT for {tname}]: {tool_result}")
                        if any(m in tool_result for m in ("Exit code:", "Error:", "Traceback", "SyntaxError", "NameError")):
                            has_error = True
                else:
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

                with self._chat_lock:
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
        for sentence in self._chat_stream_impl(user_message, on_tool_event=on_tool_event):
            parts.append(sentence)
        if parts:
            return " ".join(parts)
        with self._chat_lock:
            history = self.memory.get_messages()
            if history and history[-1]["role"] == "assistant":
                return history[-1]["content"]
        return "I'm here."

