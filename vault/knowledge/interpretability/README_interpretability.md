# Z.A.I.N.E — Transformer Layer Activation & Interpretability Analysis

This module implements offline mechanistic interpretability probes for **Z.A.I.N.E's Tier 0 reflex core (`Qwen2.5-3B-Instruct`)**. It extracts layer-by-layer hidden state representations, residual stream dynamics, and fine-tuning weight shifts without touching GPU VRAM or interrupting the live voice/chat runtime.

---

## 1. Architectural Design & Zero-VRAM Isolation

- **CPU Host-RAM Execution:** Forced to `device="cpu"` using `torch.bfloat16`. Uses ~5.8 GB of system host RAM (16 GB available) with **0 MB GPU VRAM allocation**.
- **Ollama Invariant:** The live production assistant (`qwen2.5:3b` pinned in GPU VRAM via Ollama) continues running in real time with `<800ms` voice latency while this probe operates completely decoupled.
- **PyTorch Forward Hooks:** Non-invasive hooks are attached across all 36 decoder layers (`model.model.layers[0]` to `[35]`).

---

## 2. Captured Metrics

For every prompt and each of the 36 transformer layers, the probe records three core tensor norms:

1. **Residual Stream L2 Norm ($\|h_l\|_2$):**
   - Measures the total vector magnitude in the residual stream after layer $l$'s attention and MLP contributions have been accumulated.
   - Typically grows with depth as features accumulate, with characteristic spikes at layers responsible for complex reasoning or prompt syntax resolution.
2. **Attention Output Norm:**
   - Measures the norm of the multi-head self-attention output tensor before it is added to the residual stream ($x + \text{Attn}(x)$).
   - Reveals which layers perform heavy inter-token routing and associative context gathering.
3. **SwiGLU MLP Gate Activation Norm:**
   - Measures the norm of the feed-forward SwiGLU gating projection.
   - Highlights factual recall, memorized knowledge extraction, and vocabulary projection.

---

## 3. Evaluation Curriculum (20 Fixed Probes)

The curriculum is stored as a constant list (`PROBE_PROMPTS`) in `model_activations_probe.py` across four representative operational domains:
- **Persona & Conversation (`P01`–`P05`):** Identity, tone, episodic callbacks, and relational grounding.
- **Coding & Algorithms (`P06`–`P10`):** Graph theory, recursion, PyTorch autograd, SwiGLU mechanics, and asynchronous event loops.
- **Agentic Tools & OS Commands (`P11`–`P15`):** Hardware thermals, SQLite vault retrieval, crypto rates, and multimedia script generation.
- **Grounded AI Intel & Systems (`P16`–`P20`):** Multimodal Flash Thinking, Grouped Query Attention (GQA), MoE routing, and LoRA internals.

---

## 4. Understanding the Heatmaps & Output Files

The probe generates timestamped artifacts in `vault/knowledge/interpretability/`:

| Artifact | Description |
| :--- | :--- |
| `activation_report_<timestamp>.csv` | Complete tabular dataset containing `prompt_id`, `category`, `layer` (0–35), `residual_norm`, `attention_norm`, and `mlp_gate_norm`. |
| `activation_heatmap_<timestamp>.png` | 2D color matrix where **Y-axis = Layers 0 to 35** (bottom to top), **X-axis = 20 Evaluation Prompts**, and **Color = L2 Norm Magnitude**. |
| `activation_drift_report_<timestamp>.csv` | *(Generated with `--compare-lora`)* Delta metrics ($\|h_{\text{lora}}\| - \|h_{\text{base}}\|$) across all 36 layers. |
| `activation_drift_heatmap_<timestamp>.png` | Diverging color map (`coolwarm`) showing where LoRA weight adaptations shifted the internal representation most heavily. |

### Key Observations & Interview Takeaways
- **Early Layers (0–8):** Focus on lexical parsing and syntactic disambiguation. Norms remain relatively stable across diverse prompts.
- **Middle Layers (9–26):** Deep reasoning, semantic synthesis, and knowledge retrieval. Technical coding prompts exhibit higher MLP gate activation norms than casual greetings.
- **Late Layers (27–35):** Final token distribution formatting and persona calibration. Under `--compare-lora`, LoRA adapters targeting persona ("Sir" salutation, concise Jarvis cadence) show localized activation drift in these upper layers while preserving the base model's lower-layer foundational knowledge.

---

## 5. How to Run

```bash
# Standard Base Model Probe (Outputs CSV and Heatmap)
python model_activations_probe.py

# Base vs Fine-Tuned LoRA Drift Analysis
python model_activations_probe.py --compare-lora

# Custom LoRA Checkpoint or Output Directory
python model_activations_probe.py --compare-lora --lora-dir finetune/zaine-3b-qlora/checkpoint-75 --output-dir vault/knowledge/interpretability
```
