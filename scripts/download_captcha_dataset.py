#!/usr/bin/env python3
"""Download 2000 CAPTCHA samples from UTCMS ShowFuelQuota for dataset creation."""

import io
import sys
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image

CAPTCHA_URL = "https://utcms.ir/Cap.aspx?id=LoginShowFuelQuota"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "datasets" / "fuel_captcha"
TOTAL_SAMPLES = 2000
BATCH_SIZE = 100
DELAY_BETWEEN_REQUESTS = 0.3
MAX_WORKERS = 5

session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
        "Referer": "https://utcms.ir/ShowFuelQuota.aspx",
    }
)


def download_one(index: int) -> dict:
    """Download one CAPTCHA image, convert to PNG, return info dict."""
    try:
        resp = session.get(CAPTCHA_URL, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.content

        img = Image.open(io.BytesIO(raw))
        img_rgb = img.convert("RGB")

        filename = f"captcha_{index:04d}.png"
        filepath = OUTPUT_DIR / "images" / filename
        img_rgb.save(filepath, "PNG")

        return {
            "index": index,
            "filename": filename,
            "size": img.size,
            "mode": img.mode,
            "content_type": content_type,
            "bytes": len(raw),
            "error": None,
        }
    except Exception as e:
        return {
            "index": index,
            "filename": None,
            "size": None,
            "mode": None,
            "content_type": None,
            "bytes": 0,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Download CAPTCHA dataset")
    parser.add_argument("--count", type=int, default=TOTAL_SAMPLES, help="Number of samples")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Parallel workers")
    args = parser.parse_args()

    total = args.count
    workers = args.workers
    images_dir = OUTPUT_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {total} CAPTCHA images to {images_dir}...")
    print(f"URL: {CAPTCHA_URL}")
    print(f"Workers: {workers}, Delay: {DELAY_BETWEEN_REQUESTS}s")
    print()

    start_time = time.time()
    results = []
    successes = 0
    failures = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i in range(1, total + 1):
            future = executor.submit(download_one, i)
            futures[future] = i
            time.sleep(DELAY_BETWEEN_REQUESTS / workers)

            for done in as_completed(list(futures.keys())):
                if done not in futures:
                    continue
                idx = futures.pop(done)
                result = done.result()
                results.append(result)
                if result["error"]:
                    failures += 1
                else:
                    successes += 1

        for future in as_completed(futures):
            idx = futures[future]
            result = future.result()
            results.append(result)
            if result["error"]:
                failures += 1
            else:
                successes += 1

    elapsed = time.time() - start_time

    results.sort(key=lambda r: r["index"])

    import csv

    metadata_path = OUTPUT_DIR / "metadata.csv"
    with open(metadata_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["index", "filename", "size", "mode", "content_type", "bytes", "error"])
        writer.writeheader()
        writer.writerows(results)

    print()
    print(f"{'='*50}")
    print(f"Dataset creation complete!")
    print(f"{'='*50}")
    print(f"  Total requested:   {total}")
    print(f"  Successful:        {successes}")
    print(f"  Failed:            {failures}")
    print(f"  Time elapsed:      {elapsed:.1f}s")
    print(f"  Avg per image:     {elapsed/total:.2f}s" if total else "")
    print(f"  Images directory:  {images_dir}")
    print(f"  Metadata file:     {metadata_path}")
    print(f"{'='*50}")

    if failures > 0:
        print(f"\n⚠️  {failures} downloads failed. Check metadata.csv for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
