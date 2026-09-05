"""
Z.A.I.N.E — Merge LoRA Adapter into Base Model

After training with qlora_train.py, this merges the LoRA adapter weights into
the base model to produce one standalone model (no adapter loading needed at
inference time). Run this in the same Colab/Kaggle session right after training,
or in a fresh session as long as ADAPTER_DIR is available.

Setup (if a fresh session):
    !pip install -q -U transformers peft accelerate
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# ============================== CONFIG ==============================
# CRITICAL: this must be the EXACT SAME base model used in qlora_train.py's
# BASE_MODEL — a LoRA adapter is only compatible with the exact model it was
# trained on. Since training switched to the 3B model (Colab compute limits),
# this must say 3B too, or merging will fail / silently produce garbage.
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"       # <-- MUST match qlora_train.py
ADAPTER_DIR = "./zaine-qlora-adapter"         # OUTPUT_DIR from qlora_train.py
MERGED_OUTPUT_DIR = "./zaine-merged-model"
# ======================================================================


def main():
    print(f"Loading base model {BASE_MODEL}...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

    print(f"Loading LoRA adapter from {ADAPTER_DIR}...")
    model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)

    print("Merging adapter into base model weights...")
    merged_model = model.merge_and_unload()

    print(f"Saving merged model to {MERGED_OUTPUT_DIR}...")
    merged_model.save_pretrained(MERGED_OUTPUT_DIR, safe_serialization=True)
    tokenizer.save_pretrained(MERGED_OUTPUT_DIR)

    print("\nDone. Next step — get this running in Ollama:")
    print("  1. Download the MERGED_OUTPUT_DIR folder.")
    print("  2. Convert to GGUF using llama.cpp's convert script:")
    print("     https://github.com/ggerganov/llama.cpp (see convert_hf_to_gguf.py)")
    print("  3. Create an Ollama Modelfile pointing at the .gguf file:")
    print('     FROM ./zaine-merged.gguf')
    print("     ollama create zaine-finetuned -f Modelfile")
    print("  4. Update MODEL_NAME in agent.py to \"zaine-finetuned\"")


if __name__ == "__main__":
    main()
