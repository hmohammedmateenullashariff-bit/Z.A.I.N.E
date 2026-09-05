# Z.A.I.N.E Fine-Tuning Dataset

## Why this dataset exists
Two concrete problems, confirmed by actual use (not hypothetical):
1. **Task management / conversation mistakes** — the model sometimes mishandles tool
   calls or loses track of context.
2. **Personality/tone inconsistency** — the model doesn't consistently sound like
   Z.A.I.N.E (warm, aware of its own voice/mic/screen, doesn't invent names, etc.)

This is a *targeted* fine-tune, not a general one. Every example should trace back to
one of these two problems. If you're adding an example that isn't fixing an observed
failure or reinforcing the desired persona, it probably doesn't belong here (per the
"don't fine-tune things prompting can already fix" rule from the roadmap).

## Format
JSONL — one JSON object per line. Each object is a full conversation:

```json
{"messages": [
  {"role": "system", "content": "<same system prompt as agent.py>"},
  {"role": "user", "content": "user message"},
  {"role": "assistant", "content": "correct assistant response"}
]}
```

For tool-use examples, the assistant turn should contain ONLY the tool-call JSON
(matching the exact format `agent.py` expects), e.g.:
```json
{"role": "assistant", "content": "{\"tool\": \"add_task\", \"args\": {\"description\": \"buy groceries\", \"due\": \"today\"}}"}
```

Multi-turn tool examples (tool call -> tool result -> final reply) can include more
messages in sequence, mirroring exactly what `agent.py`'s loop produces at runtime.

## How to build this dataset
1. Use `seed_examples.jsonl` as a starting point — hand-written, high-quality, small.
2. Run `generate_variations.py` to paraphrase each seed into several variations using
   your local Ollama model (same style, different phrasing) — this multiplies a small
   hand-written set into a usable training set without writing hundreds by hand.
3. **Review every generated example before training.** Bad data trains bad behavior.
   Delete or fix anything that doesn't match what you actually want.
4. Aim for at least 100-200 solid examples split roughly evenly between the two
   problem categories. More is fine if quality holds up — don't pad with junk just to
   hit a number.

## Files
- `seed_examples.jsonl` — hand-crafted correct examples (start here)
- `generate_variations.py` — expands seeds into more training examples
- `final_dataset.jsonl` — what you upload to Colab/Kaggle for training (after review)
