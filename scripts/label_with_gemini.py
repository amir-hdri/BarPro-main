#!/usr/bin/env python3
import os
import csv
import base64
import time
import requests
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

DATASET_DIR = Path(__file__).resolve().parent.parent / "datasets" / "fuel_captcha"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_FILE = DATASET_DIR / "labels.csv"

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("❌ Error: GEMINI_API_KEY environment variable is not set!")
    exit(1)

# List of models to try in sequence when rate limited
AVAILABLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash"
]

def load_existing_labels() -> dict[int, dict]:
    labels = {}
    if LABELS_FILE.exists():
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("index"):
                    idx = int(row["index"])
                    labels[idx] = {
                        "filename": row.get("filename"),
                        "words": row.get("words"),
                        "digits": row.get("digits")
                    }
    return labels

def save_labels(labels: dict[int, dict]):
    with open(LABELS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "filename", "words", "digits"])
        for idx in sorted(labels):
            row = labels[idx]
            writer.writerow([idx, row["filename"], row["words"], row["digits"]])
    print(f"💾 Saved {len(labels)} labels to {LABELS_FILE}")

def get_unlabeled_indices(labels: dict[int, dict]) -> list[int]:
    all_indices = []
    for p in IMAGES_DIR.glob("captcha_*.png"):
        try:
            idx = int(p.stem.split("_")[1])
            all_indices.append(idx)
        except (IndexError, ValueError):
            pass
    
    unlabeled = [idx for idx in all_indices if idx not in labels]
    return sorted(unlabeled)

def call_gemini_ocr(idx: int) -> tuple[int, str, str, str | None]:
    filename = f"captcha_{idx:04d}.png"
    img_path = IMAGES_DIR / filename
    
    if not img_path.exists():
        return idx, filename, "", f"File not found: {img_path}"
        
    try:
        with open(img_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return idx, filename, "", f"Failed to read image: {e}"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "This image is a captcha from a Persian website. It contains Persian words representing a number "
                            "(e.g., 'نود و پنج هزار و هفتصد و پنجاه و نه'). "
                            "Read the Persian text in this image carefully, and return a JSON object with two fields:\n"
                            "1. 'words': The exact Persian words in the image.\n"
                            "2. 'digits': The digit representation of the number (e.g. '95759').\n"
                            "Return ONLY the raw JSON string, without any markdown formatting or code blocks."
                        )
                    },
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": img_data
                        }
                    }
                ]
            }
        ]
    }
    
    headers = {"Content-Type": "application/json"}
    
    max_retries = 3
    backoff = 3.0
    
    for attempt in range(max_retries):
        # Try each model in sequence to bypass rate limits
        for model in AVAILABLE_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=20)
                if resp.status_code == 200:
                    res_json = resp.json()
                    text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    # Clean up any potential markdown code block wrappers
                    if text.startswith("```"):
                        lines = text.splitlines()
                        if lines[0].startswith("```json") or lines[0].startswith("```"):
                            text = "\n".join(lines[1:-1]).strip()
                    
                    # Parse JSON response
                    data = json.loads(text)
                    words = data.get("words", "").strip()
                    digits = data.get("digits", "").strip()
                    if words and digits:
                        return idx, filename, words, digits
                    else:
                        # Bad format, let's try next model
                        continue
                elif resp.status_code == 429:
                    # Rate limited for this model, immediately try next model!
                    continue
                else:
                    # Other error, try next model
                    continue
            except Exception:
                # Connection or parsing error, try next model
                continue
        
        # If we went through all models and all failed/rate limited, wait and retry
        print(f"⚠️ All models rate limited or failed for captcha_{idx:04d}.png. Sleeping {backoff:.1f}s...")
        time.sleep(backoff)
        backoff *= 2.0
                
    return idx, filename, "", "All models rate limited or failed after retries"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Label fuel captchas using Gemini API")
    parser.add_argument("--limit", type=int, default=200, help="Maximum number of new images to label in this run")
    args = parser.parse_args()

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    labels = load_existing_labels()
    unlabeled = get_unlabeled_indices(labels)
    
    if not unlabeled:
        print("🎉 All images are already labeled!")
        return
        
    limit = min(args.limit, len(unlabeled))
    print(f"🚀 Starting parallel labeling of up to {limit} images (out of {len(unlabeled)} unlabeled) using Gemini...")
    
    to_label = unlabeled[:limit]
    
    batch_count = 0
    save_every = 10
    
    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for idx in to_label:
                # Stagger thread submission slightly to avoid hitting API rate limits instantly
                time.sleep(1.2)
                futures.append(executor.submit(call_gemini_ocr, idx))
                
            for future in as_completed(futures):
                result_idx, filename, words, digits = future.result()
                if words and digits:
                    labels[result_idx] = {
                        "filename": filename,
                        "words": words,
                        "digits": digits
                    }
                    batch_count += 1
                    print(f"✅ [{batch_count}/{limit}] captcha_{result_idx:04d}.png: '{words}' -> {digits}")
                    
                    if batch_count % save_every == 0:
                        save_labels(labels)
                else:
                    error_msg = digits if not words else "Unknown error"
                    print(f"❌ Failed for captcha_{result_idx:04d}.png: {error_msg}")
                    
    except KeyboardInterrupt:
        print("\nStopping and saving progress...")
    finally:
        save_labels(labels)
        print("Done.")

if __name__ == "__main__":
    main()
