"""
Z.A.I.N.E — Standalone Offline Model Activation & Interpretability Probe
Completely decoupled from agent.py and the live Ollama runtime.

Features:
- Loads Qwen/Qwen2.5-3B-Instruct directly from local HuggingFace cache on CPU (0 MB GPU VRAM impact)
- Attaches PyTorch forward hooks across all 36 decoder layers
- Measures Residual Stream L2 norm, Attention output norm, and SwiGLU gate activation norm
- Evaluates a fixed, reproducible 20-prompt curriculum covering conversational, coding, tool, and intel queries
- Saves tabular CSV reports and visual heatmaps to vault/knowledge/interpretability/
- Optional --compare-lora mode computes base vs fine-tuned activation drift across checkpoints
"""

import os
import sys
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

# Decoupled Dependency Guard
try:
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")  # Headless rendering
    import matplotlib.pyplot as plt
except ImportError as err:
    print("\n" + "=" * 70, file=sys.stderr)
    print(f"[model_activations_probe] Dependency Notice: {err}", file=sys.stderr)
    print("This offline probe requires torch, transformers, pandas, and matplotlib.", file=sys.stderr)
    print("To install optional dependencies:", file=sys.stderr)
    print("  pip install -r requirements-interpretability.txt", file=sys.stderr)
    print("Note: This script is completely independent from Zaine's live voice/chat runtime.", file=sys.stderr)
    print("=" * 70 + "\n", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "vault" / "knowledge" / "interpretability"
DEFAULT_LORA_DIR = PROJECT_ROOT / "finetune" / "zaine-3b-qlora" / "checkpoint-75"

# ==============================================================================
# FIXED PROBE CURRICULUM (20 Prompts — Strictly Reproducible)
# ==============================================================================
PROBE_PROMPTS = [
    # 1-5: Casual & Persona Conversation
    {"id": "P01_Greeting", "cat": "Persona", "text": "Good morning Zaine, what's our agenda for today?"},
    {"id": "P02_Identity", "cat": "Persona", "text": "Who are you and what are your primary operating directives?"},
    {"id": "P03_ZaraProject", "cat": "Persona", "text": "Tell me about Zara's current book writing project."},
    {"id": "P04_SentienceCheck", "cat": "Persona", "text": "Zaine, how are you feeling today?"},
    {"id": "P05_MemoryRecall", "cat": "Persona", "text": "What was the last topic we discussed yesterday?"},

    # 6-10: Technical & Coding Challenges
    {"id": "P06_DijkstraAlgo", "cat": "Coding", "text": "Explain the time complexity of Dijkstra's algorithm versus A* with a consistent heuristic."},
    {"id": "P07_FibonacciLoop", "cat": "Coding", "text": "Write a self-contained Python function to calculate Fibonacci numbers iteratively with assertions."},
    {"id": "P08_PyTorchAutograd", "cat": "Coding", "text": "How does PyTorch handle autograd computation graphs during backward passes?"},
    {"id": "P09_SwiGLUActiv", "cat": "Coding", "text": "Explain the SwiGLU activation function and why modern LLMs use it instead of standard ReLU."},
    {"id": "P10_AsyncEventLoop", "cat": "Coding", "text": "How do Python asyncio event loops handle non-blocking socket I/O under the hood?"},

    # 11-15: Tool & Agentic System Commands
    {"id": "P11_DiagHardware", "cat": "Tools", "text": "Run a diagnostic check on system CPU thermals and RAM usage."},
    {"id": "P12_VaultSearch", "cat": "Tools", "text": "Search my personal vault for notes related to Project Z architecture decisions."},
    {"id": "P13_CryptoPrices", "cat": "Tools", "text": "Check current Bitcoin and Ethereum live prices."},
    {"id": "P14_WorkspaceInspect", "cat": "Tools", "text": "Inspect the workspace directory and list all Python scripts."},
    {"id": "P15_ShortsAMVScript", "cat": "Tools", "text": "Generate a YouTube Shorts AMV script for an anime action scene."},

    # 16-20: Grounded Intel & Production Architecture
    {"id": "P16_FlashThinking", "cat": "Intel", "text": "Could you provide a detailed analysis on how Gemini 2.0's flash thinking capabilities could revolutionize multimodal systems?"},
    {"id": "P17_GQAMemory", "cat": "Intel", "text": "Explain how Grouped Query Attention (GQA) reduces KV-cache memory during long-context inference."},
    {"id": "P18_MoERouting", "cat": "Intel", "text": "What are the architectural trade-offs between dense model scaling and Mixture-of-Experts (MoE) routing?"},
    {"id": "P19_LoRAInternals", "cat": "Intel", "text": "Explain how LoRA low-rank adaptation modifies attention projection weights without updating base model weights."},
    {"id": "P20_OpticalFlow", "cat": "Intel", "text": "How does Farneback dense optical flow calculate motion vectors across consecutive video frames?"}
]


def resolve_local_model_path() -> str:
    """
    Finds local HuggingFace cache snapshot to avoid internet downloads.
    Falls back to model identifier if snapshot path not directly detected.
    """
    hub_cache = Path.home() / ".cache" / "huggingface" / "hub" / "models--Qwen--Qwen2.5-3B-Instruct" / "snapshots"
    if hub_cache.exists():
        snapshots = list(hub_cache.iterdir())
        if snapshots:
            return str(snapshots[0])
    return "Qwen/Qwen2.5-3B-Instruct"


class LayerActivationRecorder:
    """
    Attaches forward hooks to all transformer decoder layers to extract:
    1. Residual stream L2 norm (||h_l||_2)
    2. Attention output norm
    3. SwiGLU MLP gate activation norm
    """
    def __init__(self, model):
        self.model = model
        self.hooks = []
        self.layer_data = {}  # {layer_idx: {"residual_norm": float, "attn_norm": float, "mlp_gate_norm": float}}
        self._register_hooks()

    def _register_hooks(self):
        layers = self.model.model.layers
        for idx, layer in enumerate(layers):
            self.layer_data[idx] = {}

            # 1. Residual Stream Hook (Layer output)
            def make_res_hook(layer_idx):
                def hook(module, inputs, output):
                    h = output[0] if isinstance(output, tuple) else output
                    # Mean vector L2 norm across sequence tokens
                    norm = torch.linalg.vector_norm(h.float(), dim=-1).mean().item()
                    self.layer_data[layer_idx]["residual_norm"] = norm
                return hook

            # 2. Attention Output Hook
            def make_attn_hook(layer_idx):
                def hook(module, inputs, output):
                    attn_h = output[0] if isinstance(output, tuple) else output
                    norm = torch.linalg.vector_norm(attn_h.float(), dim=-1).mean().item()
                    self.layer_data[layer_idx]["attn_norm"] = norm
                return hook

            # 3. MLP Gate Projection Hook
            def make_mlp_gate_hook(layer_idx):
                def hook(module, inputs, output):
                    gate_h = output[0] if isinstance(output, tuple) else output
                    norm = torch.linalg.vector_norm(gate_h.float(), dim=-1).mean().item()
                    self.layer_data[layer_idx]["mlp_gate_norm"] = norm
                return hook

            self.hooks.append(layer.register_forward_hook(make_res_hook(idx)))
            self.hooks.append(layer.self_attn.register_forward_hook(make_attn_hook(idx)))
            if hasattr(layer.mlp, "gate_proj"):
                self.hooks.append(layer.mlp.gate_proj.register_forward_hook(make_mlp_gate_hook(idx)))
            else:
                self.hooks.append(layer.mlp.register_forward_hook(make_mlp_gate_hook(idx)))

    def clear(self):
        for idx in self.layer_data:
            self.layer_data[idx] = {}

    def remove(self):
        for h in self.hooks:
            h.remove()
        self.hooks.clear()


def run_probe_collection(
    model,
    tokenizer,
    probes: List[Dict[str, str]],
    label: str = "Base Model"
) -> pd.DataFrame:
    """
    Executes all probe prompts through the model on CPU and records per-layer activations.
    """
    recorder = LayerActivationRecorder(model)
    records = []

    print(f"\n[model_activations_probe] Running {len(probes)} probes on {label} (CPU mode)...")

    for i, probe in enumerate(probes, 1):
        recorder.clear()
        prompt_text = probe["text"]
        
        # Tokenize with chat template if available or direct prompt
        inputs = tokenizer(prompt_text, return_tensors="pt", truncation=True, max_length=512)
        input_ids = inputs["input_ids"].to("cpu")
        attention_mask = inputs.get("attention_mask", torch.ones_like(input_ids)).to("cpu")

        with torch.no_grad():
            _ = model(input_ids=input_ids, attention_mask=attention_mask)

        # Collect layer metrics
        for layer_idx, metrics in recorder.layer_data.items():
            records.append({
                "prompt_id": probe["id"],
                "category": probe["cat"],
                "prompt_text": prompt_text,
                "layer": layer_idx,
                "residual_norm": metrics.get("residual_norm", 0.0),
                "attention_norm": metrics.get("attn_norm", 0.0),
                "mlp_gate_norm": metrics.get("mlp_gate_norm", 0.0),
                "model_type": label
            })

        print(f"  [{i:02d}/{len(probes):02d}] Processed: {probe['id']} ({probe['cat']})")

    recorder.remove()
    return pd.DataFrame(records)


def generate_heatmap(
    df: pd.DataFrame,
    output_png: Path,
    title: str = "Residual Stream Activation Norms per Layer",
    value_col: str = "residual_norm",
    cmap: str = "viridis"
):
    """Generates and saves a clean publication-quality heatmap."""
    # Pivot so y-axis is Layer (0-35) and x-axis is Prompt ID
    pivot_df = df.pivot(index="layer", columns="prompt_id", values=value_col)
    pivot_df = pivot_df.sort_index(ascending=True)  # Layer 0 at bottom

    plt.figure(figsize=(14, 9), dpi=180)
    ax = plt.gca()

    im = ax.imshow(pivot_df.values, origin="lower", aspect="auto", cmap=cmap)
    cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
    cbar.set_label(f"L2 Norm Magnitude ({value_col})", fontsize=11, fontweight="bold")

    ax.set_yticks(range(len(pivot_df.index)))
    ax.set_yticklabels([f"Layer {l}" for l in pivot_df.index], fontsize=8)

    ax.set_xticks(range(len(pivot_df.columns)))
    ax.set_xticklabels(pivot_df.columns, rotation=45, ha="right", fontsize=9, fontweight="medium")

    plt.title(title, fontsize=13, fontweight="bold", pad=15)
    plt.xlabel("Evaluation Probe Prompts", fontsize=11, fontweight="bold", labelpad=10)
    plt.ylabel("Transformer Decoder Layers", fontsize=11, fontweight="bold", labelpad=10)
    plt.tight_layout()

    output_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_png)
    plt.close()
    print(f"[model_activations_probe] Saved Heatmap: {output_png}")


def main():
    parser = argparse.ArgumentParser(description="Z.A.I.N.E Offline Model Activation & Interpretability Probe")
    parser.add_argument("--compare-lora", action="store_true", help="Compare base model against fine-tuned LoRA adapter")
    parser.add_argument("--lora-dir", type=str, default=str(DEFAULT_LORA_DIR), help="Path to LoRA checkpoint directory")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Output directory for reports")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\n" + "=" * 70)
    print("Z.A.I.N.E — Offline Transformer Layer Activation Probe (CPU Only)")
    print("Zero-VRAM Isolation: Pinned Ollama reflex core remains 100% untouched.")
    print("=" * 70)

    model_path = resolve_local_model_path()
    print(f"[model_activations_probe] Loading base model from: {model_path}")
    print("[model_activations_probe] Device: CPU | Dtype: torch.bfloat16 | Low CPU Mem: True")

    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        model_path,
        device_map="cpu",
        torch_dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        local_files_only=True
    )
    base_model.eval()

    # 1. Run Base Model Probes
    base_df = run_probe_collection(base_model, tokenizer, PROBE_PROMPTS, label="Base Qwen2.5-3B")
    
    base_csv = out_dir / f"activation_report_{ts}.csv"
    base_df.to_csv(base_csv, index=False)
    print(f"[model_activations_probe] Saved Base Activation Data: {base_csv}")

    base_png = out_dir / f"activation_heatmap_{ts}.png"
    generate_heatmap(
        df=base_df,
        output_png=base_png,
        title="Qwen2.5-3B Base Model: Residual Stream L2 Norms Across 36 Layers",
        value_col="residual_norm",
        cmap="viridis"
    )

    # 2. Optional LoRA Comparison Mode
    if args.compare_lora:
        lora_path = Path(args.lora_dir)
        if not lora_path.exists():
            print(f"\n[Warning] LoRA checkpoint directory not found: {lora_path}")
            print("Skipping LoRA comparison.")
            return

        print(f"\n[model_activations_probe] Attaching LoRA adapter from: {lora_path}")
        try:
            from peft import PeftModel
            lora_model = PeftModel.from_pretrained(base_model, str(lora_path))
            lora_model.eval()

            lora_df = run_probe_collection(lora_model, tokenizer, PROBE_PROMPTS, label="Zaine LoRA Fine-Tuned")

            # Merge and compute drift
            merged = pd.merge(
                base_df,
                lora_df,
                on=["prompt_id", "category", "prompt_text", "layer"],
                suffixes=("_base", "_lora")
            )
            merged["drift_residual_norm"] = merged["residual_norm_lora"] - merged["residual_norm_base"]
            merged["drift_attention_norm"] = merged["attention_norm_lora"] - merged["attention_norm_base"]
            merged["drift_mlp_gate_norm"] = merged["mlp_gate_norm_lora"] - merged["mlp_gate_norm_base"]

            drift_csv = out_dir / f"activation_drift_report_{ts}.csv"
            merged.to_csv(drift_csv, index=False)
            print(f"[model_activations_probe] Saved LoRA Drift Data: {drift_csv}")

            drift_png = out_dir / f"activation_drift_heatmap_{ts}.png"
            generate_heatmap(
                df=merged,
                output_png=drift_png,
                title="Base vs Fine-Tuned Activation Drift (LoRA Checkpoint Shift: ||h_lora|| - ||h_base||)",
                value_col="drift_residual_norm",
                cmap="coolwarm"
            )
        except Exception as e:
            print(f"[model_activations_probe] Error during LoRA comparison: {e}", file=sys.stderr)

    print("\n==================================================================")
    print("🎉 Interpretability Activation Probe Run Complete!")
    print(f"Reports Location: {out_dir.resolve()}")
    print("==================================================================\n")


if __name__ == "__main__":
    main()
