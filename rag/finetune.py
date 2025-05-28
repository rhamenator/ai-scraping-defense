# rag/finetune.py
# Placeholder script demonstrating fine-tuning a language model
# (e.g., from Hugging Face) for bot detection classification.
# NOTE: This requires significant compute resources (GPU), large datasets,
# and careful setup. Libraries like transformers, datasets, accelerate, torch needed.

import os
import datetime
import time # Added for timing
import json
from datasets import load_dataset, Dataset, Features, Value, ClassLabel # Using Hugging Face datasets library
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer
)
from transformers.data.data_collator import DataCollatorWithPadding
from transformers.trainer import Trainer
from transformers.training_args import TrainingArguments
import evaluate # Using Hugging Face evaluate library
import numpy as np
import collections.abc # Added for Sized check

# --- Configuration ---
# Paths assume data is prepared and accessible by training.py's export function
FINETUNE_DATA_DIR = "/app/data/finetuning_data"
TRAINING_DATA_FILE = os.path.join(FINETUNE_DATA_DIR, "finetuning_data_train.jsonl")
VALIDATION_DATA_FILE = os.path.join(FINETUNE_DATA_DIR, "finetuning_data_eval.jsonl")

# Choose a pre-trained model suitable for classification (smaller models are faster)
BASE_MODEL_NAME = "distilbert-base-uncased" # Example: Relatively small & fast
# BASE_MODEL_NAME = "bert-base-uncased"
# BASE_MODEL_NAME = "roberta-base"
OUTPUT_DIR = "/app/models/finetuned_bot_detector" # Where the fine-tuned model will be saved
LOGGING_DIR = "/app/logs/finetuning_logs"

# Training Hyperparameters (Example - Requires Tuning)
NUM_TRAIN_EPOCHS = 3
PER_DEVICE_TRAIN_BATCH_SIZE = 16
PER_DEVICE_EVAL_BATCH_SIZE = 32
LEARNING_RATE = 2e-5
WEIGHT_DECAY = 0.01
LOGGING_STEPS = 50
EVAL_STEPS = 200 # How often to evaluate during training
SAVE_STEPS = 500 # How often to save checkpoints
MAX_SEQ_LENGTH = 256 # Max token length for input sequences

# --- Data Preparation ---

def prepare_text_for_model(log_entry):
    """
    Converts a parsed log entry (dict) into a single text string
    suitable for input into a language model.
    This MUST capture the most salient features from the log_data.
    """
    # Ensure log_entry is the dictionary containing parsed log fields
    if not isinstance(log_entry, dict):
        return "" # Handle potential errors

    # Example: Combine key fields into a structured string
    # Use 'None' or 'N/A' for missing fields consistently
    ua = log_entry.get('user_agent', 'None')
    method = log_entry.get('method', 'UNK')
    path = log_entry.get('path', 'UNK_PATH')
    status = log_entry.get('status', 0)
    referer = log_entry.get('referer', 'None')
    ip = log_entry.get('ip', 'UnknownIP') # Include IP? Might help if model sees patterns

    # Combine headers into a simplified string if available
    headers_str = ""
    headers_dict = log_entry.get('headers') # Assuming headers are passed in log_data
    if isinstance(headers_dict, dict):
         # Selectively include potentially important headers, keep it concise
         # Example: focus on Accept, Language, Cache-Control, Sec-* headers
         # Avoid overly long/verbose headers like Cookie
         important_headers = {
             k: v for k, v in headers_dict.items()
             if k.lower() in ['accept', 'accept-language', 'cache-control', 'sec-ch-ua', 'sec-fetch-dest', 'sec-fetch-mode', 'sec-fetch-site']
         }
         headers_str = " ".join(f"{k[:15]}={v[:40]}" for k, v in important_headers.items()) # Truncated headers

    # Format the input text - Experiment with different formats!
    # This format tries to be somewhat structured.
    text = f"[IP:{ip}] [M:{method}] [S:{status}] [P:{path}] [R:{referer}] [UA:{ua}] [H:{headers_str}]"

    # Truncate to avoid excessive length (tokenizers handle max_length, but good practice)
    return text[:MAX_SEQ_LENGTH * 5] # Allow more chars before tokenization


def load_and_prepare_dataset(file_path, tokenizer):
    """Loads JSON lines data, prepares text fields, and tokenizes."""
    print(f"Loading and preparing dataset from: {file_path}")
    try:
        # Load from JSON Lines file
        # Expected format per line: {"log_data": {parsed_log_dict}, "label": "bot" or "human"}
        raw_dataset = load_dataset('json', data_files=file_path, split='train')

        # Define expected features for validation and ClassLabel mapping
        # Ensure 'human' is 0 and 'bot' is 1 to match training.py's label encoding if reusing metrics
        label_map = ['human', 'bot']
        expected_features = Features({
            'log_data': Value('string'), # Temporarily treat as string for mapping, then re-parse or adjust
            'label': ClassLabel(names=label_map),
            # Add other fields if they exist at the top level
        })

        # Preprocessing function to extract log_data, prepare text, and tokenize
        def preprocess_function(examples):
            # The 'log_data' field is loaded as a string by default by `load_dataset('json')`
            # We need to parse it back to dict if needed by prepare_text_for_model
            # Alternatively, modify prepare_text_for_model to expect the stringified dict if simpler.
            # Here, we assume prepare_text_for_model handles the dict directly if passed.
            # The `map` function passes each row (example) as a dict.
            processed_texts = []
            labels = []
            for i in range(len(examples['label'])):
                # If log_data loaded as string, parse it back; otherwise use directly if dict
                log_dict = json.loads(examples['log_data'][i]) if isinstance(examples['log_data'][i], str) else examples['log_data'][i]
                processed_texts.append(prepare_text_for_model(log_dict))
                # Map label string to integer ID
                labels.append(label_map.index(examples['label'][i]))

            tokenized_inputs = tokenizer(
                processed_texts,
                max_length=MAX_SEQ_LENGTH,
                truncation=True,
                padding=False # Padding handled dynamically by DataCollator
            )
            # Add labels to the tokenized inputs
            tokenized_inputs['label'] = labels
            return tokenized_inputs

        # Apply preprocessing
        # Note: Adjust `batched` and potentially `num_proc` for performance
        processed_dataset = raw_dataset.map(
            preprocess_function,
            batched=True,
            remove_columns=["log_data", "label"] # Remove original columns after processing
        )

        try:
            if isinstance(processed_dataset, collections.abc.Sized): # Check if the object is Sized
                num_examples = len(processed_dataset) # Now Pylance might be more confident
                print(f"Dataset prepared. Number of examples: {num_examples}")
            else:
                print("Dataset prepared. Number of examples: (IterableDataset, length unknown)")
        except Exception:
            print("Dataset prepared. Number of examples: (IterableDataset, length unknown)")
        # print("Example processed sample:", processed_dataset[0]) # Debug: check structure
        return processed_dataset

    except FileNotFoundError:
        print(f"ERROR: Data file not found at {file_path}")
    except Exception as e:
        print(f"ERROR: Failed to load or prepare dataset from {file_path}: {e}")
        # import traceback; traceback.print_exc() # Uncomment for detailed traceback
    return None

# --- Model Training ---

def compute_metrics(eval_pred):
    """Computes evaluation metrics (accuracy, F1)."""
    try:
        metric_acc = evaluate.load("accuracy")
        metric_f1 = evaluate.load("f1")
    except Exception as e:
        print(f"Error loading evaluation metrics: {e}. Check network or cache.")
        return {"accuracy": 0.0, "f1": 0.0}


    logits, labels = eval_pred
    # Logits are output neurons, need argmax to get predicted class index
    predictions = np.argmax(logits, axis=-1)

    try:
        accuracy = metric_acc.compute(predictions=predictions, references=labels)
        f1_score = metric_f1.compute(predictions=predictions, references=labels, average="binary") # Use 'binary' for 2 classes

        return {
            "accuracy": accuracy["accuracy"] if accuracy and "accuracy" in accuracy else 0.0,
            "f1": f1_score["f1"] if f1_score and "f1" in f1_score else 0.0,
        }
    except Exception as e:
        print(f"Error computing metrics: {e}")
        return {"accuracy": 0.0, "f1": 0.0}


def fine_tune_model():
    """Main function to load data, model, tokenizer, and run fine-tuning."""
    print("--- Starting Language Model Fine-Tuning ---")

    # 1. Load Tokenizer
    try:
        print(f"Loading tokenizer for base model: {BASE_MODEL_NAME}")
        tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME)
    except Exception as e:
        print(f"ERROR: Failed to load tokenizer '{BASE_MODEL_NAME}': {e}")
        return

    # 2. Load and Prepare Datasets
    # Uses the files generated by training.py's save_data_for_finetuning function
    train_dataset = load_and_prepare_dataset(TRAINING_DATA_FILE, tokenizer)
    eval_dataset = load_and_prepare_dataset(VALIDATION_DATA_FILE, tokenizer)

    if not train_dataset or not eval_dataset:
        print("ERROR: Could not load datasets. Aborting fine-tuning.")
        return

    # 3. Load Base Model for Sequence Classification
    try:
        print(f"Loading base model for sequence classification: {BASE_MODEL_NAME}")
        # num_labels=2 for binary classification (human/bot)
        model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL_NAME, num_labels=2)
    except Exception as e:
        print(f"ERROR: Failed to load base model '{BASE_MODEL_NAME}': {e}")
        return

    # 4. Define Training Arguments
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=NUM_TRAIN_EPOCHS,
        per_device_train_batch_size=PER_DEVICE_TRAIN_BATCH_SIZE,
        per_device_eval_batch_size=PER_DEVICE_EVAL_BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
        logging_dir=LOGGING_DIR,
        logging_strategy="steps", # Log metrics periodically
        logging_steps=LOGGING_STEPS,
        eval_strategy="steps", # Evaluate periodically
        eval_steps=EVAL_STEPS,
        save_strategy="steps",
        save_steps=SAVE_STEPS,
        save_total_limit=2, # Keep only last 2 checkpoints + final model
        load_best_model_at_end=True, # Reload best model found during training
        metric_for_best_model="f1", # Use F1 score to determine best model
        greater_is_better=True,
        report_to="tensorboard", # Log to TensorBoard (requires tensorboard package)
        fp16=True, # Enable mixed precision training if GPU supports it
        # Consider adding:
        # warmup_steps=... ,
        # gradient_accumulation_steps=... ,
        # push_to_hub=False, # Don't push to Hugging Face Hub by default
    )

    # 5. Define Data Collator (handles dynamic padding)
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    # 6. Initialize Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    # 7. Start Fine-Tuning
    print("Starting model fine-tuning...")
    start_time = time.time()
    try:
        train_result = trainer.train()
        end_time = time.time()
        print(f"Fine-tuning finished in {end_time - start_time:.2f} seconds.")

        metrics = train_result.metrics
        trainer.log_metrics("train", metrics)
        trainer.save_metrics("train", metrics)

        trainer.save_model() # Saves the best model to output_dir
        trainer.save_state() # Saves trainer state
        print(f"Best fine-tuned model and state saved to: {OUTPUT_DIR}")

        print("\nEvaluating final best model on evaluation set...")
        eval_metrics = trainer.evaluate(eval_dataset=eval_dataset) # Explicitly evaluate best model
        trainer.log_metrics("eval_final", eval_metrics)
        trainer.save_metrics("eval_final", eval_metrics)

    except Exception as e:
        print(f"ERROR during fine-tuning or evaluation: {e}")
        import traceback; traceback.print_exc()

    print("--- Fine-Tuning Script Finished ---")


# --- Main Execution ---
if __name__ == "__main__":
    # Ensure necessary output directories exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOGGING_DIR, exist_ok=True)

    fine_tune_model()