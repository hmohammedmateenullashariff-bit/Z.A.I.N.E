"""
Z.A.I.N.E — Autonomous Dynamic Daily Q&A Generator & Curriculum Synthesizer
Generates diverse, realistic task prompts once per night using the local Tier 0 model (qwen2.5:3b):
- Topic-grounded across Developer Knowledge Vault, AI Intel, and Zaine Tool Schemas
- Duplicate & Diversity Guard via CPU-only Ollama Embeddings (nomic-embed-text, num_gpu: 0)
- Quality & Persona Gating via Structured Google Gemini API Validation
- Candidate isolation: Writes exclusively to data/nightly_validated_qa.jsonl for manual review
- Rejection auditing: Logs discarded prompts to data/rejected_training_data.jsonl
"""

import os
import sys
import json
import time
import math
import random
import argparse
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
from dotenv import load_dotenv

load_dotenv()

from agent import ZaineAgent
import gemini_validator

OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
GENERATION_MODEL = os.getenv("QA_GEN_MODEL", "qwen2.5:3b")
EMBEDDING_MODEL = os.getenv("QA_EMBED_MODEL", "nomic-embed-text")

CANDIDATE_DATASET_PATH = PROJECT_ROOT / "data" / "nightly_validated_qa.jsonl"
REJECTED_DATASET_PATH = PROJECT_ROOT / "data" / "rejected_training_data.jsonl"
VAULT_KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge_vault"
AI_INTEL_PATH = PROJECT_ROOT / "vault" / "knowledge" / "daily_ai_intel.md"

SIMILARITY_THRESHOLD = 0.85
QUALITY_THRESHOLD = 0.80
MAX_RETRIES_PER_SLOT = 3

print("[daily_qa_generator] Writing candidate pool to: data/nightly_validated_qa.jsonl (requires manual promotion to final_dataset.jsonl — does not auto-train).")



def get_cpu_embedding(text: str) -> Optional[List[float]]:
    """
    Computes text embedding using Ollama's CPU-only endpoint.
    Explicitly enforces num_gpu: 0 to protect GPU VRAM for the reflex core.
    Falls back to a deterministic normalized character/token vector if Ollama is unreachable.
    """
    url = f"{OLLAMA_API_BASE}/api/embeddings"
    payload = {
        "model": EMBEDDING_MODEL,
        "prompt": text,
        "options": {
            "num_gpu": 0
        }
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            emb = resp.json().get("embedding", [])
            if emb:
                return emb
    except Exception as e:
        print(f"[daily_qa_generator] Embedding API notice: {e}", file=sys.stderr)

    # Fallback: Lightweight token bag-of-words pseudo-embedding (zero external dependency)
    words = text.lower().split()
    vec = [0.0] * 128
    for w in words:
        h = hash(w) % 128
        vec[h] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        return [x / norm for x in vec]
    return vec


def compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot_product / (norm1 * norm2)))


def load_recent_accepted_questions(days: int = 7) -> List[Dict[str, Any]]:
    """
    Loads accepted questions from data/nightly_validated_qa.jsonl
    within the last N days for diversity comparisons.
    """
    if not CANDIDATE_DATASET_PATH.exists():
        return []

    cutoff = time.time() - (days * 86400)
    questions = []

    try:
        with open(CANDIDATE_DATASET_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    ts_str = data.get("timestamp", "")
                    try:
                        ts_epoch = datetime.datetime.fromisoformat(ts_str).timestamp()
                    except Exception:
                        ts_epoch = time.time()

                    if ts_epoch >= cutoff:
                        prompt = data.get("prompt", "")
                        if prompt:
                            questions.append({
                                "prompt": prompt,
                                "timestamp": ts_str,
                                "embedding": data.get("embedding")
                            })
                except Exception:
                    pass
    except Exception as e:
        print(f"[daily_qa_generator] Error loading recent questions: {e}", file=sys.stderr)

    return questions


def log_rejected_data(prompt: str, reason: str, details: Optional[Dict[str, Any]] = None):
    """Appends rejected question/QA pair to data/rejected_training_data.jsonl."""
    REJECTED_DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "prompt": prompt,
        "reason": reason,
        "details": details or {},
        "timestamp": datetime.datetime.now().isoformat(),
    }
    with open(REJECTED_DATASET_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def harvest_topic_seeds() -> List[Dict[str, str]]:
    """
    Gathers topic seeds from developer knowledge vault datasets,
    daily AI intelligence markdown, and Zaine system administration tools.
    """
    seeds = []

    # 1. Developer Knowledge Vault
    if VAULT_KNOWLEDGE_DIR.exists():
        for json_file in VAULT_KNOWLEDGE_DIR.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                    domain = json_file.stem
                    if isinstance(data, list):
                        for item in data[:8]:
                            name = item.get("name") or item.get("topic") or item.get("title") or item.get("system", "")
                            summary = item.get("summary") or item.get("description") or item.get("use_cases", "")
                            if name:
                                seeds.append({
                                    "domain": domain.replace("_", " ").title(),
                                    "topic": name,
                                    "context": str(summary)[:200]
                                })
            except Exception:
                pass

    # 2. Daily AI Intelligence
    if AI_INTEL_PATH.exists():
        try:
            content = AI_INTEL_PATH.read_text(encoding="utf-8", errors="ignore")
            for line in content.split("\n"):
                if line.startswith("### ") and "[" in line:
                    title = line.replace("### ", "").strip()
                    seeds.append({
                        "domain": "Frontier AI Intel",
                        "topic": title,
                        "context": "Recent breakthroughs in autonomous agents, reasoning architectures, and local inference."
                    })
        except Exception:
            pass

    # 3. Zaine Core Systems & Tools
    core_tools = [
        {"domain": "Zaine System Tools", "topic": "Workspace File Execution", "context": "Writing, verifying, and executing self-contained Python scripts in the workspace directory."},
        {"domain": "Zaine System Tools", "topic": "System Diagnostics & Hardware", "context": "Querying hardware metrics, CPU thermals, RAM availability, and battery states."},
        {"domain": "Zaine System Tools", "topic": "Second Brain Vault", "context": "Adding and retrieving atomic notes and ideas using SQLite FTS5 BM25 search."},
        {"domain": "Zaine System Tools", "topic": "Real-Time APIs", "context": "Querying live cryptocurrency prices, weather forecasts, and foreign exchange rates without API keys."},
        {"domain": "Zaine System Tools", "topic": "Visual Grounding & Screen", "context": "Desktop screen inspection, UI state reasoning, and window management."}
    ]
    seeds.extend(core_tools)

    random.shuffle(seeds)
    return seeds


def generate_candidate_prompt(seed: Dict[str, str]) -> str:
    """
    Calls local Tier 0 model (qwen2.5:3b) via Ollama to formulate a realistic,
    diverse user prompt based on the provided topic seed.
    """
    system_instruction = (
        "You are an expert prompt engineer creating realistic, challenging test prompts for Z.A.I.N.E, "
        "an elite personal AI assistant. Formulate ONE realistic, conversational prompt from a human user "
        "(addressed to Zaine or direct instruction) that asks to solve, explain, implement, or diagnose "
        "the given topic. Output ONLY the single user prompt, with no surrounding quotes or extra preamble."
    )

    user_query = f"Domain: {seed['domain']}\nTopic: {seed['topic']}\nContext: {seed['context']}\n\nGenerate one user request:"

    url = f"{OLLAMA_API_BASE}/api/chat"
    payload = {
        "model": GENERATION_MODEL,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_query}
        ],
        "options": {
            "temperature": 0.75,
            "top_p": 0.90
        },
        "stream": False
    }

    try:
        resp = requests.post(url, json=payload, timeout=45)
        if resp.status_code == 200:
            content = resp.json().get("message", {}).get("content", "").strip()
            # Clean up formatting artifacts
            clean = content.strip('"\'').strip()
            if clean:
                return clean
    except Exception as e:
        print(f"[daily_qa_generator] Generation error: {e}", file=sys.stderr)

    # Fallback to direct prompt template if LLM call fails
    return f"Can you explain the architecture of {seed['topic']} ({seed['domain']}) and provide a concise implementation example?"


def generate_daily_qa_batch(
    count: int = 15,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    quality_threshold: float = QUALITY_THRESHOLD
) -> Dict[str, Any]:
    """
    Main nightly orchestration routine:
    1. Loads prior 7-day accepted question embeddings.
    2. Synthesizes N diverse questions via qwen2.5:3b.
    3. Enforces CPU embedding cosine diversity (discard if > similarity_threshold).
    4. Runs Zaine agent to produce answers.
    5. Validates (question, answer) via Google Gemini structured JSON.
    6. Appends accepted pairs to data/nightly_validated_qa.jsonl.
    7. Logs all rejections to data/rejected_training_data.jsonl.
    """
    print("[daily_qa_generator] Writing candidate pool to: data/nightly_validated_qa.jsonl (requires manual promotion to final_dataset.jsonl — does not auto-train).")

    seeds = harvest_topic_seeds()
    if not seeds:
        print("[daily_qa_generator] No topic seeds discovered.")
        return {"accepted": 0, "rejected": 0, "status": "NO_SEEDS"}

    recent_history = load_recent_accepted_questions(days=7)
    print(f"[daily_qa_generator] Loaded {len(recent_history)} prior questions from 7-day history for diversity checking.")

    # Precompute embeddings for history items if missing
    for item in recent_history:
        if not item.get("embedding"):
            item["embedding"] = get_cpu_embedding(item["prompt"])

    accepted_batch = []
    rejected_count = 0

    agent = ZaineAgent()

    for slot_idx in range(1, count + 1):
        slot_accepted = False
        seed = seeds[(slot_idx - 1) % len(seeds)]

        print(f"\n[{slot_idx}/{count}] Target Domain: {seed['domain']} — '{seed['topic']}'")

        for attempt in range(1, MAX_RETRIES_PER_SLOT + 1):
            candidate_prompt = generate_candidate_prompt(seed)
            if not candidate_prompt or len(candidate_prompt) < 10:
                continue

            print(f"  Attempt {attempt}: Evaluating prompt: '{candidate_prompt[:65]}...'")

            # 1. Compute CPU-only embedding
            candidate_emb = get_cpu_embedding(candidate_prompt)
            if not candidate_emb:
                print("  [Notice] Could not compute embedding; proceeding with novelty check.")

            # 2. Diversity / Similarity Check vs Last 7 Days
            is_duplicate = False
            max_sim = 0.0
            conflict_prompt = ""

            if candidate_emb and recent_history:
                for hist in recent_history:
                    h_emb = hist.get("embedding")
                    if h_emb:
                        sim = compute_cosine_similarity(candidate_emb, h_emb)
                        if sim > max_sim:
                            max_sim = sim
                            conflict_prompt = hist["prompt"]
                        if sim > similarity_threshold:
                            is_duplicate = True
                            break

            if is_duplicate:
                print(f"  ⚠️ Duplicate detected (Similarity: {max_sim:.3f} > {similarity_threshold}). Discarding.")
                log_rejected_data(
                    prompt=candidate_prompt,
                    reason="DUPLICATE_SIMILARITY_EXCEEDED",
                    details={
                        "similarity": round(max_sim, 3),
                        "conflict_with": conflict_prompt,
                        "slot": slot_idx,
                        "attempt": attempt
                    }
                )
                rejected_count += 1
                continue

            # 3. Prompt Accepted! Generate Zaine's Response
            print("  ✅ Prompt is diverse and novel. Generating Zaine response...")
            t0 = time.time()
            try:
                # Use synchronous chat interface
                response = agent.chat(candidate_prompt)
                elapsed = round(time.time() - t0, 2)
            except Exception as ae:
                print(f"  Agent response error: {ae}")
                response = f"Execution error generating response: {ae}"
                elapsed = round(time.time() - t0, 2)

            # 4. Gemini Structured Quality Validation
            print("  Validating Q&A quality via Gemini...")
            validation_result = gemini_validator.validate_qa_pair(
                question=candidate_prompt,
                answer=response,
                threshold=quality_threshold
            )

            is_valid = validation_result.get("valid", False)
            score = validation_result.get("score", 0.0)
            feedback = validation_result.get("feedback", "")
            mode = validation_result.get("mode", "UNKNOWN")

            print(f"  Validation: valid={is_valid}, score={score:.2f} (Mode: {mode})")

            if is_valid and score >= quality_threshold:
                # 5. Commit to Candidate Pool
                record = {
                    "iteration": slot_idx,
                    "prompt": candidate_prompt,
                    "tool": getattr(agent, "last_tool_called", None) or "",
                    "response": response,
                    "elapsed_sec": elapsed,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "gemini_validation": {
                        "valid": is_valid,
                        "score": score,
                        "feedback": feedback,
                        "mode": mode
                    }
                }

                CANDIDATE_DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(CANDIDATE_DATASET_PATH, "a", encoding="utf-8") as f_out:
                    f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

                # Track in local history to avoid subsequent duplicates within the same batch
                recent_history.append({
                    "prompt": candidate_prompt,
                    "timestamp": record["timestamp"],
                    "embedding": candidate_emb
                })

                accepted_batch.append(record)
                slot_accepted = True
                print(f"  🎉 Slot {slot_idx} accepted and staged into candidate pool!")
                break
            else:
                print(f"  ❌ Gemini rejected Q&A pair (score {score} < {quality_threshold}): {feedback}")
                log_rejected_data(
                    prompt=candidate_prompt,
                    reason="GEMINI_QUALITY_REJECT",
                    details={
                        "score": score,
                        "feedback": feedback,
                        "response_preview": response[:200],
                        "slot": slot_idx
                    }
                )
                rejected_count += 1

        if not slot_accepted:
            print(f"  ⏭️ Slot {slot_idx} skipped after {MAX_RETRIES_PER_SLOT} attempts.")

    print("\n==================================================================")
    print(f"[daily_qa_generator Batch Complete]")
    print(f"Staged Candidates: {len(accepted_batch)} / {count}")
    print(f"Rejected / Discarded: {rejected_count}")
    print(f"Candidate Storage: {CANDIDATE_DATASET_PATH}")
    print(f"Rejection Log:     {REJECTED_DATASET_PATH}")
    print("==================================================================")

    return {
        "status": "SUCCESS",
        "requested": count,
        "accepted": len(accepted_batch),
        "rejected": rejected_count,
        "candidate_pool_path": str(CANDIDATE_DATASET_PATH),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Z.A.I.N.E Autonomous Daily Q&A Generator")
    parser.add_argument("--count", type=int, default=15, help="Number of Q&A candidates to generate (default: 15)")
    parser.add_argument("--sim-threshold", type=float, default=SIMILARITY_THRESHOLD, help="Cosine similarity threshold (default: 0.85)")
    parser.add_argument("--quality-threshold", type=float, default=QUALITY_THRESHOLD, help="Gemini quality threshold (default: 0.80)")
    args = parser.parse_args()

    generate_daily_qa_batch(
        count=args.count,
        similarity_threshold=args.sim_threshold,
        quality_threshold=args.quality_threshold
    )
