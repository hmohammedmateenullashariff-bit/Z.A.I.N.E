# Project-Z (Z.A.I.N.E) Legacy Archive

This directory contains preserved historical code, discarded training scripts, transient test benches, and experimental stubs from Project-Z development (September–November 2026).

**Directive:**
- No production runtime code in the active repository may import from this directory.
- All code here is preserved for reference, recovery, or future resurrection by Zaine / E.D.I.T.H.
- Do not delete files from this archive.

---

## 1. `training/` (Early Fine-Tuning & Adapter Experiments)
* `simulate_training.py` — Synthetic QLoRA training run simulator.
* `repo_trainer.py` — PyTorch / Hugging Face local fine-tuning trainer for Qwen/DeepSeek.
* `self_distillation.py` — Prompt distillation pipeline from larger models.
* `merge_adapter.py` — Peft / LoRA adapter merge script to fuse weights into base model.
* `model_activations_probe.py` — PyTorch hook inspector for probing internal attention activations.
* `merged_model/` — Destination folder for fused GGUF/HF weights.

## 2. `transient_tests/` (Ad-Hoc Investigative Test Scripts)
* `test_terminal_animation.py` — Console cursor and loading spinner prototypes.
* `test_memory_subsystem.py` — Early SQLite vector/FTS5 verification script.
* `test_approval_timeout_fix.py` — Benchmark reproducing the 9–10 Oct approval deadlock.
* `test_subagents.py` — Prototype delegation script between Jarvis and Edith.
* `test_stage2_tui.py` through `test_stage5_digraph.py` — Milestone test harnesses for Textual widgets.
* `test_harness.py` — Test runner for `harness.py` functions.
* `test_cli_architecture.py` — Subprocess integration test for CLI arguments.
* `test_person_memory_regression.py` — Verification test for the person entity search starvation bug.
* `test_tool_dispatch.py` — Isolated tool dispatcher check.
* `test_mic.py` — PyAudio microphone hardware loopback diagnostic.
* `eval_test_prompts.py` — 10-prompt benchmark probe.

## 3. `deprecated_pipelines/` (Superseded Daemons & Pipelines)
* `daily_qa_generator.py` — Standalone synthetic Q&A pair generator.
* `gemini_validator.py` — Google Gemini API evaluation probe (deprecated in favor of local Ollama sovereignty).
* `migrate_memory_sqlite_to_obsidian.py` — One-time DB-to-Vault sync script from early September.
* `overnight_autonomous_pipeline.py` — Batch script for unattended multi-step tasks (superseded by subagent delegation).
* `telegram_daemon.py` — Test launcher for Telegram bot (superseded by `telegram_bridge.py`).
* `zaine_cascade.py` — Hard-coded sequential fallback router (superseded by `core_router.py`).

