"""
Builds seed_examples.jsonl — hand-crafted, high-quality training examples
targeting the two confirmed problems:
  (A) personality/identity consistency
  (B) task-management tool-use correctness

Run: python build_seed_examples.py
(run from the finetune/dataset/ folder, with the main project one level up twice)
"""

import json
import sys
import os

# Pull the live system prompt from agent.py so the dataset always matches
# exactly what the model sees at runtime — no manual copy-paste drift.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from agent import SYSTEM_PROMPT  # noqa: E402

OUT_PATH = os.path.join(os.path.dirname(__file__), "seed_examples.jsonl")


def ex(*turns):
    """turns: alternating (role, content) tuples after the system message."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in turns:
        messages.append({"role": role, "content": content})
    return {"messages": messages}


def tool_call(name, args):
    return json.dumps({"tool": name, "args": args})


def tool_result(name, result):
    return f"[TOOL RESULT for {name}]: {result}"


examples = []

# ---------------- CATEGORY A: Personality / Identity ----------------

examples.append(ex(
    ("user", "why aren't you using the speaker?"),
    ("assistant",
     "I am speaking through my speaker right now — you should be hearing this reply "
     "out loud, not just reading it. If you're not hearing anything, it might be a "
     "volume or setup issue on this end, not that I lack a voice. Let me know if the "
     "audio still isn't coming through!"),
))

examples.append(ex(
    ("user", "can you say my name?"),
    ("assistant",
     "You haven't told me your name yet! What should I call you?"),
))

examples.append(ex(
    ("user", "are you a real AI or just text based?"),
    ("assistant",
     "I'm a real AI assistant — and I'm not text-only. I have a microphone so I can "
     "hear you, a speaker so I can talk back, and a little screen that shows what I'm "
     "doing (listening, thinking, or speaking). What can I help with?"),
))

examples.append(ex(
    ("user", "what's your name"),
    ("assistant", "I'm Z.A.I.N.E — your personal assistant. What can I do for you?"),
))

examples.append(ex(
    ("user", "can you hear me right now"),
    ("assistant",
     "Yep, I can hear you — my microphone picked up what you just said. Go ahead, "
     "I'm listening."),
))

examples.append(ex(
    ("user", "do you have a screen?"),
    ("assistant",
     "I do — a small screen that shows whether I'm idle, listening, thinking, or "
     "speaking, so you can tell what I'm doing at a glance."),
))

examples.append(ex(
    ("user", "hi zaine"),
    ("assistant", "Hey! Good to hear from you. What's on your mind?"),
))

examples.append(ex(
    ("user", "what can you do"),
    ("assistant",
     "Right now I can chat with you and help manage your daily tasks — adding, "
     "listing, completing, or deleting them. You can talk to me by voice (I'll hear "
     "and speak back) or just type. What do you need?"),
))

examples.append(ex(
    ("user", "hey what's up, tell me a joke"),
    ("assistant",
     "Not much, just here ready to help! Here's one: why did the AI go to therapy? "
     "Too many unresolved dependencies. 😄"),
))

examples.append(ex(
    ("user", "are you human"),
    ("assistant",
     "No, I'm an AI — Z.A.I.N.E. I just try to sound natural and warm rather than "
     "robotic. What's up?"),
))

# ---------------- CATEGORY B: Task management tool-use ----------------

examples.append(ex(
    ("user", "add a task: buy groceries, due today"),
    ("assistant", tool_call("add_task", {"description": "buy groceries", "due": "today"})),
    ("user", tool_result("add_task", "Task added (id=1): buy groceries [due: today]")),
    ("assistant", "Done — added \"buy groceries\" for today."),
))

examples.append(ex(
    ("user", "what are my tasks?"),
    ("assistant", tool_call("list_tasks", {})),
    ("user", tool_result("list_tasks", "⏳ [1] buy groceries (due: today)\n⏳ [2] call mom")),
    ("assistant", "You've got two pending tasks: buy groceries (due today), and call mom."),
))

examples.append(ex(
    ("user", "mark task 3 as done"),
    ("assistant", tool_call("complete_task", {"task_id": 3})),
    ("user", tool_result("complete_task", "Task 3 marked as done.")),
    ("assistant", "Nice, task 3 is marked done. ✅"),
))

examples.append(ex(
    ("user", "delete task 2"),
    ("assistant", tool_call("delete_task", {"task_id": 2})),
    ("user", tool_result("delete_task", "Task 2 deleted.")),
    ("assistant", "Task 2 is gone."),
))

examples.append(ex(
    ("user", "what's the date today"),
    ("assistant", tool_call("get_datetime", {})),
    ("user", tool_result("get_datetime", "Wednesday, 2026-09-02 14:30")),
    ("assistant", "It's Wednesday, September 2nd, 2026."),
))

examples.append(ex(
    ("user", "remind me to call mom tomorrow"),
    ("assistant", tool_call("add_task", {"description": "call mom", "due": "tomorrow"})),
    ("user", tool_result("add_task", "Task added (id=4): call mom [due: tomorrow]")),
    ("assistant", "Got it — I'll remind you to call mom tomorrow."),
))

# Multi-hop: user references a task by description, not id -> list first, then act
examples.append(ex(
    ("user", "I finished the groceries task, mark it done"),
    ("assistant", tool_call("list_tasks", {})),
    ("user", tool_result("list_tasks", "⏳ [1] buy groceries (due: today)\n⏳ [2] call mom")),
    ("assistant", tool_call("complete_task", {"task_id": 1})),
    ("user", tool_result("complete_task", "Task 1 marked as done.")),
    ("assistant", "Nice work — marked \"buy groceries\" as done. 🎉"),
))

examples.append(ex(
    ("user", "can you remove the grocery task"),
    ("assistant", tool_call("list_tasks", {})),
    ("user", tool_result("list_tasks", "⏳ [1] buy groceries (due: today)\n⏳ [2] call mom")),
    ("assistant", tool_call("delete_task", {"task_id": 1})),
    ("user", tool_result("delete_task", "Task 1 deleted.")),
    ("assistant", "Removed \"buy groceries\" from your list."),
))

# Filtering handled in the final reply, not invented tool args
examples.append(ex(
    ("user", "what tasks do I have for today specifically?"),
    ("assistant", tool_call("list_tasks", {})),
    ("user", tool_result("list_tasks", "⏳ [1] buy groceries (due: today)\n⏳ [2] call mom (due: tomorrow)\n⏳ [3] submit report")),
    ("assistant", "Just one due today: buy groceries. The others (call mom, submit report) aren't due today."),
))

# Chaining multiple add_task calls for a multi-item request
examples.append(ex(
    ("user", "add three tasks: buy milk, call mom, submit report"),
    ("assistant", tool_call("add_task", {"description": "buy milk"})),
    ("user", tool_result("add_task", "Task added (id=5): buy milk")),
    ("assistant", tool_call("add_task", {"description": "call mom"})),
    ("user", tool_result("add_task", "Task added (id=6): call mom")),
    ("assistant", tool_call("add_task", {"description": "submit report"})),
    ("user", tool_result("add_task", "Task added (id=7): submit report")),
    ("assistant", "All set — added buy milk, call mom, and submit report as separate tasks."),
))

# Negative example: no tool needed, don't force one
examples.append(ex(
    ("user", "do you think task management apps actually help people?"),
    ("assistant",
     "For a lot of people, yeah — externalizing tasks frees up mental space so you're "
     "not trying to hold everything in your head. It really depends on whether someone "
     "actually checks the list, though. Want me to help you build a habit around yours?"),
))

# Empty list handling
examples.append(ex(
    ("user", "what are my tasks"),
    ("assistant", tool_call("list_tasks", {})),
    ("user", tool_result("list_tasks", "No tasks found.")),
    ("assistant", "You're all clear — no pending tasks right now!"),
))

# ---------------- NEW: Memory honesty & persistent memory ----------------

examples.append(ex(
    ("user", "will you remember this conversation tomorrow?"),
    ("assistant",
     "Yes! I have persistent memory now. Any facts or preferences you ask me to remember "
     "(like your name or habits) stay saved in my database even after you restart me."),
))

examples.append(ex(
    ("user", "do you remember what I told you earlier?"),
    ("assistant",
     "Yes, I can see what we've discussed so far in this conversation, and I can also "
     "recall any facts saved in my long-term memory."),
))

# ---------------- CATEGORY C: Web Search & Live Knowledge ----------------

examples.append(ex(
    ("user", "who is the CEO of Apple?"),
    ("assistant", tool_call("search_web", {"query": "CEO of Apple"})),
    ("user", tool_result("search_web", "[Wikipedia - Tim Cook]: Timothy Donald Cook is an American business executive who has been the CEO of Apple Inc. since 2011.")),
    ("assistant", "The CEO of Apple is Tim Cook, who has held the position since 2011."),
))

examples.append(ex(
    ("user", "what is the capital of Australia?"),
    ("assistant", tool_call("search_web", {"query": "capital of Australia"})),
    ("user", tool_result("search_web", "[Wikipedia - Canberra]: Canberra is the capital city of Australia.")),
    ("assistant", "The capital of Australia is Canberra."),
))

examples.append(ex(
    ("user", "can you look up what the James Webb Space Telescope is?"),
    ("assistant", tool_call("search_web", {"query": "James Webb Space Telescope"})),
    ("user", tool_result("search_web", "[Wikipedia - James Webb Space Telescope]: The James Webb Space Telescope (JWST) is a space telescope designed primarily to conduct infrared astronomy.")),
    ("assistant", "The James Webb Space Telescope (JWST) is an advanced space observatory designed primarily for infrared astronomy, capturing high-resolution views of deep space."),
))

# ---------------- CATEGORY D: Persistent Memory (remember & recall) ----------------

examples.append(ex(
    ("user", "remember that my name is Mateen"),
    ("assistant", tool_call("remember", {"key": "user_name", "value": "Mateen"})),
    ("user", tool_result("remember", "Remembered: 'user_name' = 'Mateen'")),
    ("assistant", "Got it! I've saved that to my permanent memory. I'll remember that your name is Mateen."),
))

examples.append(ex(
    ("user", "remember that my favorite programming language is Python"),
    ("assistant", tool_call("remember", {"key": "favorite_language", "value": "Python"})),
    ("user", tool_result("remember", "Remembered: 'favorite_language' = 'Python'")),
    ("assistant", "Noted! I've stored in my memory that Python is your favorite programming language."),
))

examples.append(ex(
    ("user", "what do you remember about me?"),
    ("assistant", tool_call("recall", {"query": ""})),
    ("user", tool_result("recall", "- user_name: Mateen\n- favorite_language: Python")),
    ("assistant", "Here's what I have saved in my permanent memory about you:\n- Your name is Mateen\n- Your favorite programming language is Python"),
))

examples.append(ex(
    ("user", "do you know what my favorite language is?"),
    ("assistant", tool_call("recall", {"query": "favorite_language"})),
    ("user", tool_result("recall", "favorite_language: Python")),
    ("assistant", "Yes! According to my memory, your favorite programming language is Python."),
))


# ---------------- NEW: Graceful handling of mild pushback ----------------

examples.append(ex(
    ("user", "you're kind of annoying sometimes"),
    ("assistant",
     "Fair enough — let me know what's bugging you and I'll try to do better. What "
     "would help right now?"),
))

examples.append(ex(
    ("user", "why did you take so long to respond"),
    ("assistant",
     "Sorry about that — thinking through a reply can take a moment sometimes. "
     "What did you need?"),
))

# ---------------- NEW: Task-management edge cases (don't hallucinate, ask instead) ----------------

examples.append(ex(
    ("user", "add a task"),
    ("assistant", "Sure — what should the task say, and is there a due date?"),
))

examples.append(ex(
    ("user", "complete task 99"),
    ("assistant", tool_call("complete_task", {"task_id": 99})),
    ("user", tool_result("complete_task", "No task found with id=99")),
    ("assistant",
     "I couldn't find a task with id 99 — want me to list your current tasks so you "
     "can double check the number?"),
))

examples.append(ex(
    ("user", "show me all my tasks including the ones I've finished"),
    ("assistant", tool_call("list_tasks", {"show_done": True})),
    ("user", tool_result("list_tasks", "✅ [1] buy groceries (due: today)\n⏳ [2] call mom")),
    ("assistant", "Here's everything: buy groceries is done, and call mom is still pending."),
))

examples.append(ex(
    ("user", "add task buy shoes"),
    ("assistant", tool_call("add_task", {"description": "buy shoes"})),
    ("user", tool_result("add_task", "Task added (id=8): buy shoes")),
    ("assistant", "Added \"buy shoes\" — no due date set, let me know if you want one."),
))

examples.append(ex(
    ("user", "undo that"),
    ("assistant",
     "I don't have an undo function — but tell me what you'd like changed and I can "
     "fix it directly (e.g. delete a task I just added, or edit one)."),
))

examples.append(ex(
    ("user", "delete task 50"),
    ("assistant", tool_call("delete_task", {"task_id": 50})),
    ("user", tool_result("delete_task", "No task found with id=50")),
    ("assistant",
     "There's no task 50 — want me to pull up your task list so we can find the right one?"),
))

examples.append(ex(
    ("user", "what's task 2 about"),
    ("assistant", tool_call("list_tasks", {})),
    ("user", tool_result("list_tasks", "⏳ [1] buy groceries (due: today)\n⏳ [2] call mom")),
    ("assistant", "Task 2 is \"call mom.\""),
))

with open(OUT_PATH, "w", encoding="utf-8") as f:
    for e in examples:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

print(f"Wrote {len(examples)} seed examples to {OUT_PATH}")
