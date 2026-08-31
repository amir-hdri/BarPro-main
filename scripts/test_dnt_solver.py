#!/usr/bin/env python3
"""
Test script for DNT Captcha PyTorch CRNN Solver.
Evaluates model on sample synthetic and real captcha images.
"""

import sys
import os
import json
import base64
from pathlib import Path
from PIL import Image
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.automation.captcha.dnt_captcha_solver import DntCaptchaProvider
from app.automation.captcha.persian_number_parser import persian_words_to_number

def test_samples():
    solver = DntCaptchaProvider()
    # Check if custom model path is provided via env
    custom_model = os.getenv("MODEL_PATH")
    custom_vocab = os.getenv("VOCAB_PATH")
    if custom_model:
        solver.model_path = Path(custom_model)
    if custom_vocab:
        solver.vocab_path = Path(custom_vocab)

    print(f"Loading solver from:\n  Model: {solver.model_path}\n  Vocab: {solver.vocab_path}")
    loaded = solver._load_model()
    if not loaded:
        print("❌ Failed to load model.")
        return

    # Test on synthetic samples
    dataset_dir = Path(os.getenv("DATASET_DIR", "/tmp/datasets/dnt_captcha"))
    labels_file = dataset_dir / "labels.csv"
    if labels_file.exists():
        import csv
        with open(labels_file, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        
        test_rows = reader[-10:] # last 10 samples
        print(f"\n--- Testing on {len(test_rows)} validation samples ---")
        correct = 0
        for r in test_rows:
            img_path = dataset_dir / "images" / r["filename"]
            if not img_path.exists():
                continue
            with open(img_path, "rb") as img_f:
                b64 = base64.b64encode(img_f.read()).decode("utf-8")
            
            res = solver._solve_sync(b64)
            expected_num = str(r["number"])
            expected_words = str(r["words"])
            is_match = (res.value == expected_num)
            if is_match:
                correct += 1
            print(f"[{'✅' if is_match else '❌'}] Expected: {expected_num} ('{expected_words}') | Got: {res.value} (Solved={res.solved}, Error={res.error})")
        print(f"\nValidation score: {correct}/{len(test_rows)}")

if __name__ == "__main__":
    test_samples()
