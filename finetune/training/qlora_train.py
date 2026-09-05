"""
Z.A.I.N.E — QLoRA Fine-Tuning Pipeline (Colab/Kaggle)

This is the reusable pipeline from the roadmap: everything below the CONFIG
section should stay untouched. To fine-tune the code layer later on
Qwen2.5-Coder, you only change BASE_MODEL and DATASET_PATH.

Run this in a Colab/Kaggle notebook with a GPU runtime (T4 16GB is enough for
QLoRA on a 7B model). Paste each section into its own cell, or run as a script.

Setup (run once per session):
    !pip install -q -U transformers accelerate peft bitsandbytes trl datasets
"""

import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig

# ============================== CONFIG ==============================
# Only these two lines should need to change for a different layer/model.
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"       # switched from 7B due to free-tier Colab limits
DATASET_PATH = "final_dataset.jsonl"           # upload this to Colab/Kaggle first

OUTPUT_DIR = "./zaine-qlora-adapter"
MAX_SEQ_LENGTH = 1024

# Training hyperparameters — reasonable defaults for a small (100-300 example) dataset.
NUM_EPOCHS = 3
LEARNING_RATE = 2e-4
BATCH_SIZE = 2
GRAD_ACCUM_STEPS = 4

# LoRA hyperparameters
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]
# ======================================================================


def load_and_format_dataset(tokenizer):
    """Loads the JSONL dataset and renders each example's `messages` through
    the model's chat template into a single training string."""
    dataset = load_dataset("json", data_files=DATASET_PATH, split="train")

    def format_example(example):
        text = tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False
        )
        return {"text": text}

    return dataset.map(format_example, remove_columns=dataset.column_names)


def main():
    print(f"Loading tokenizer for {BASE_MODEL}...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("Formatting dataset...")
    dataset = load_and_format_dataset(tokenizer)
    print(f"Dataset size: {len(dataset)} examples")
    print("Sample:\n", dataset[0]["text"][:500], "...\n")

    print(f"Loading base model in 4-bit ({BASE_MODEL})...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
    )
    model = prepare_model_for_kbit_training(model)

    print("Applying LoRA adapter...")
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGET_MODULES,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    import inspect

    sft_kwargs = {
        "output_dir": OUTPUT_DIR,
        "num_train_epochs": NUM_EPOCHS,
        "per_device_train_batch_size": BATCH_SIZE,
        "gradient_accumulation_steps": GRAD_ACCUM_STEPS,
        "learning_rate": LEARNING_RATE,
        "logging_steps": 5,
        "save_strategy": "epoch",
        "bf16": True,
        "report_to": "none",
    }

    sft_params = inspect.signature(SFTConfig.__init__).parameters
    if "max_length" in sft_params:
        sft_kwargs["max_length"] = MAX_SEQ_LENGTH
    elif "max_seq_length" in sft_params:
        sft_kwargs["max_seq_length"] = MAX_SEQ_LENGTH

    if "dataset_text_field" in sft_params:
        sft_kwargs["dataset_text_field"] = "text"

    sft_config = SFTConfig(**sft_kwargs)

    trainer_kwargs = {
        "model": model,
        "args": sft_config,
        "train_dataset": dataset,
    }

    trainer_params = inspect.signature(SFTTrainer.__init__).parameters
    if "processing_class" in trainer_params:
        trainer_kwargs["processing_class"] = tokenizer
    else:
        trainer_kwargs["tokenizer"] = tokenizer

    if "dataset_text_field" not in sft_params and "dataset_text_field" in trainer_params:
        trainer_kwargs["dataset_text_field"] = "text"

    trainer = SFTTrainer(**trainer_kwargs)

    print("Starting training...")
    trainer.train()

    print(f"Saving adapter to {OUTPUT_DIR}...")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print("\nDone. To use this adapter:")
    print("  1. Download the OUTPUT_DIR folder from Colab/Kaggle.")
    print("  2. See merge_and_export.py for merging it into a full model")
    print("     and converting it for Ollama use.")


if __name__ == "__main__":
    main()
