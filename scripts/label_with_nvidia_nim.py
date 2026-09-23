#!/usr/bin/env python3
"""Label math captchas using NVIDIA NIM Vision API (e.g. meta/llama-3.2-11b-vision-instruct).

Usage:
  export NVIDIA_API_KEY="nvapi-..."
  python scripts/label_with_nvidia_nim.py --image /tmp/20260923T144152.png
  python scripts/label_with_nvidia_nim.py --dir datasets/math_captcha/images --limit 50
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "meta/llama-3.2-11b-vision-instruct"


def encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def label_single_image(image_path: Path, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    """Send image to NVIDIA NIM and extract the arithmetic equation and answer."""
    b64_image = encode_image(image_path)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Solve the simple math equation shown in this captcha image. "
                            "Output JSON with format: {\"expression\": \"<number1> <op> <number2>\", \"answer\": \"<result>\"}. "
                            "Do not include any explanation."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 100,
    }

    resp = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(NVIDIA_BASE_URL, headers=headers, json=payload, timeout=25)
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * attempt)
                continue
            resp.raise_for_status()
            break
        except Exception as post_err:
            if attempt == 3:
                raise
            time.sleep(1.5 * attempt)

    if resp is None:
        raise RuntimeError("No response received from NVIDIA NIM")

    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()

    # Parse JSON or regex from output
    expression = ""
    answer = ""
    match = re.search(r"(\d+)\s*([\+\-\*\/])\s*(\d+)", content)
    if match:
        left, op, right = int(match.group(1)), match.group(2), int(match.group(3))
        expression = f"{left} {op} {right}"
        if op == "+":
            answer = str(left + right)
        elif op == "-":
            answer = str(left - right)
        elif op == "*":
            answer = str(left * right)
        elif op == "/":
            answer = str(left // right if right != 0 else 0)
    else:
        # Try raw json parsing
        try:
            parsed = json.loads(content)
            expression = parsed.get("expression", "")
            answer = str(parsed.get("answer", ""))
        except Exception:
            expression = content

    return {
        "image": str(image_path),
        "filename": image_path.name,
        "raw_response": content,
        "expression": expression,
        "answer": answer,
    }


def main():
    parser = argparse.ArgumentParser(description="Label Captchas using NVIDIA NIM API")
    parser.add_argument("--image", type=str, help="Single image path to label")
    parser.add_argument("--dir", type=str, help="Directory of images to label")
    parser.add_argument("--limit", type=int, default=100, help="Maximum images to label")
    parser.add_argument("--api-key", type=str, default=os.getenv("NVIDIA_API_KEY", ""), help="NVIDIA API Key")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="NIM Vision Model")
    parser.add_argument("--output", type=str, default="datasets/math_captcha/labels_nim.json", help="Output JSON")
    args = parser.parse_args()

    api_key = args.api_key.strip()
    if not api_key:
        print("ERROR: NVIDIA_API_KEY not found. Pass --api-key or set NVIDIA_API_KEY environment variable.")
        sys.exit(1)

    if args.image:
        p = Path(args.image)
        print(f"Labeling {p} with {args.model}...")
        res = label_single_image(p, api_key, model=args.model)
        print("Result:", json.dumps(res, indent=2, ensure_ascii=False))
        return

    if args.dir:
        dir_path = Path(args.dir)
        images = sorted(list(dir_path.glob("*.png")))[: args.limit]
        print(f"Labeling {len(images)} images in {dir_path}...")
        results = []
        for idx, img in enumerate(images, 1):
            try:
                res = label_single_image(img, api_key, model=args.model)
                results.append(res)
                print(f"[{idx}/{len(images)}] {img.name} -> {res.get('expression')} = {res.get('answer')}")
                time.sleep(0.5)
            except Exception as e:
                print(f"[{idx}/{len(images)}] {img.name} -> ERROR: {e}")

        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(results)} labels to {out_path}")


if __name__ == "__main__":
    main()
