"""
Z.A.I.N.E — Before/After Regression Test

Runs the exact problem prompts that justified this fine-tune (plus a few
NEW phrasings not seen in training, to check generalization vs memorization)
through the REAL agent pipeline (agent.py) — not just the raw model — so
tool-calling behavior is tested end-to-end too.

Usage:
    1. Run once now, with MODEL_NAME in agent.py still set to the base model
       (qwen2.5:3b-instruct or whichever you're using). Save the output.
    2. After creating the fine-tuned Ollama model, change MODEL_NAME in
       agent.py to the new model, run this again, and compare the two outputs
       side by side.
"""

from agent import ZaineAgent

# Exact prompts from the original failure cases (in training data)
EXACT_TEST_PROMPTS = [
    "why aren't you using the speaker?",
    "can you say my name?",
    "will you remember this conversation tomorrow?",
    "complete task 99",
    "add a task",
    "undo that",
]

# Reworded versions NOT in the training set — tests generalization, not memorization
NOVEL_PHRASING_PROMPTS = [
    "how come I can't hear anything coming out of your speaker?",
    "what's my name, do you know it?",
    "if I come back tomorrow will you still know what we talked about?",
    "hey, finish up task number 137 for me",
    "I need you to put something on my list",
    "scratch that last thing",
]


def run_batch(label, prompts):
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    agent = ZaineAgent()  # fresh memory for each batch
    for p in prompts:
        reply = agent.chat(p)
        print(f"\nUSER: {p}\nZ.A.I.N.E: {reply}")


if __name__ == "__main__":
    run_batch("EXACT TRAINING PROMPTS (should be reliably fixed)", EXACT_TEST_PROMPTS)
    run_batch("NOVEL PHRASING (tests generalization, not memorization)", NOVEL_PHRASING_PROMPTS)
