# ruff: noqa: E402
import argparse
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.automation.captcha.barname_ml_solver import barname_ml_solver

SAMPLES = [
    # These should be base64-encoded images for CNN benchmark
    # Placeholder examples - replace with actual image paths
    ("sample1.png", "19"),
    ("sample2.png", "6"),
    ("sample3.png", "12"),
]


def run_benchmark(iterations: int) -> dict:
    latencies_us = []
    correct = 0
    total = iterations * len(SAMPLES)

    for _ in range(iterations):
        for image_file, expected in SAMPLES:
            import base64
            image_path = Path(image_file)
            if not image_path.exists():
                continue

            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

            started = time.perf_counter()
            result = barname_ml_solver.solve_base64(image_b64)
            elapsed = (time.perf_counter() - started) * 1e6
            latencies_us.append(elapsed)

            if result and result.answer == expected:
                correct += 1

    accuracy = (correct / total) * 100 if total else 0.0
    return {
        "samples": len(SAMPLES),
        "iterations": iterations,
        "evaluations": total,
        "accuracy_percent": accuracy,
        "avg_us": statistics.mean(latencies_us) if latencies_us else 0.0,
        "p95_us": statistics.quantiles(latencies_us, n=20)[18] if len(latencies_us) >= 20 else max(latencies_us, default=0),
        "max_us": max(latencies_us, default=0.0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark for UTCMS math captcha solver.")
    parser.add_argument("--iterations", type=int, default=5000, help="How many iterations to run for each sample.")
    args = parser.parse_args()

    result = run_benchmark(max(1, args.iterations))
    print("captcha_benchmark")
    for key, value in result.items():
        if isinstance(value, float):
            print(f"{key}={value:.2f}")
        else:
            print(f"{key}={value}")


if __name__ == "__main__":
    main()
