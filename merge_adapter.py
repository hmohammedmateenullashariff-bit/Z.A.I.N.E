import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import os

BASE_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER_DIR = "finetune/zaine-3b-qlora"                 # Points to current folder containing adapter_config.json
OUTPUT_DIR = "D:/merged_model"      # Where the merged weights will be written

print("=" * 60)
print("1/4 Loading base model onto CPU (prevents meta-device crash)...")
print("=" * 60)
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_ID,
    torch_dtype=torch.float16,
    device_map="cpu",              # <--- Forces full RAM load (fixes the KeyError)
    low_cpu_mem_usage=True,
)

print("\n2/4 Loading LoRA adapter...")
model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)

print("\n3/4 Merging LoRA weights into base model...")
merged_model = model.merge_and_unload()

print(f"\n4/4 Saving merged model to {OUTPUT_DIR}...")
merged_model.save_pretrained(OUTPUT_DIR)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
tokenizer.save_pretrained(OUTPUT_DIR)

print("\n[SUCCESS] Model successfully merged and saved to:", os.path.abspath(OUTPUT_DIR))
