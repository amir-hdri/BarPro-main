#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd
import base64

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.automation.captcha.fuel_captcha_solver import PyTorchFuelCaptchaProvider
from app.automation.captcha.persian_number_parser import persian_words_to_number

def main():
    labels_file = PROJECT_ROOT / "datasets" / "fuel_captcha" / "labels.csv"
    images_dir = PROJECT_ROOT / "datasets" / "fuel_captcha" / "images"
    
    if not labels_file.exists():
        print(f"Error: Labels file not found at {labels_file}")
        return
        
    df = pd.read_csv(labels_file)
    df = df.dropna(subset=['words', 'digits'])
    
    print(f"Loaded {len(df)} samples for evaluation.")
    
    provider = PyTorchFuelCaptchaProvider()
    
    correct = 0
    total = 0
    
    for idx, row in df.iterrows():
        img_name = row['filename']
        expected_digits = str(int(row['digits'])) # convert float/int to string cleanly
        expected_words = row['words']
        
        img_path = images_dir / img_name
        if not img_path.exists():
            continue
            
        with open(img_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
            
        import asyncio
        result = asyncio.run(provider.solve_text_captcha(img_b64))
        
        if result.solved and result.value == expected_digits:
            correct += 1
            print(f"✅ {img_name}: true={expected_digits}, solved={result.value}")
        else:
            val_str = result.value if result.solved else f"Unsolved ({result.error})"
            print(f"❌ {img_name}: true={expected_digits}, solved={val_str} (words: '{expected_words}')")
            
        total += 1
        
    accuracy = (correct / total) * 100 if total else 0
    print("\n" + "="*50)
    print(f"PyTorch Captcha Solver Accuracy: {correct}/{total} = {accuracy:.2f}%")
    print("="*50)

if __name__ == "__main__":
    main()
