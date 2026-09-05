"""
Expands seed_examples.jsonl into a larger training set by generating paraphrased
variations of each USER message (keeping the assistant's correct behavior fixed).
Uses your already-running local Ollama model — no extra API cost.

Run: python generate_variations.py
Output: augmented_dataset.jsonl (seed examples + N variations of each)

IMPORTANT: Review the output before training. This script paraphrases the user's
question; it does NOT change or validate the assistant's answer. If a paraphrase
shifts the meaning enough that the original answer no longer fits, delete that line.
"""

import json
import os
import requests

SEED_PATH = os.path.join(os.path.dirname(__file__), "seed_examples.jsonl")
OUT_PATH = os.path.join(os.path.dirname(__file__), "augmented_dataset.jsonl")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"

VARIATIONS_PER_EXAMPLE = 4


def get_first_user_message(messages):
    for m in messages:
        if m["role"] == "user":
            return m["content"]
    return None


def paraphrase(text: str, n: int) -> list:
    prompt = (
        f"Give me {n} different ways to phrase this message, keeping the exact same "
        f"meaning and intent, but make each one STYLISTICALLY DIFFERENT — not just "
        f"synonym swaps. Vary things like: one very casual/slangy, one formal/polite, "
        f"one short and terse, one with a typo or lowercase/no punctuation (like real "
        f"quick typing), one that adds a bit of filler ('umm', 'hey so'). "
        f"One per line, no numbering, no extra commentary:\n\n{text}"
    )
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    reply = resp.json()["message"]["content"]
    lines = [l.strip("- ").strip() for l in reply.split("\n") if l.strip()]
    return lines[:n]


def main():
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        seeds = [json.loads(line) for line in f if line.strip()]

    all_examples = list(seeds)  # keep originals too

    for i, seed in enumerate(seeds):
        first_user_msg = get_first_user_message(seed["messages"])
        if not first_user_msg:
            continue

        print(f"[{i+1}/{len(seeds)}] Paraphrasing: {first_user_msg[:60]}...")
        try:
            variations = paraphrase(first_user_msg, VARIATIONS_PER_EXAMPLE)
        except Exception as e:
            print(f"  Skipped (error: {e})")
            continue

        for v in variations:
            if not v or v == first_user_msg:
                continue
            new_example = json.loads(json.dumps(seed))  # deep copy
            # Replace only the first user message with the paraphrase
            replaced = False
            for m in new_example["messages"]:
                if m["role"] == "user" and not replaced:
                    m["content"] = v
                    replaced = True
            all_examples.append(new_example)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(all_examples)} total examples to {OUT_PATH}")
    print("Review this file before training — delete/fix anything that doesn't fit.")


if __name__ == "__main__":
    main()
