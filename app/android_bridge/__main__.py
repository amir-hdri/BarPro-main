"""Run `python -m app.android_bridge [--layout]` for sanitized diagnostics."""

import argparse
import asyncio
import json
from dataclasses import asdict

from .client import AndroidBridge, BridgeConfig, BridgeError


async def observe(include_layout: bool) -> dict:
    bridge = AndroidBridge(BridgeConfig.from_env())
    snapshot = await bridge.probe()
    result = asdict(snapshot)
    result["observed_at"] = snapshot.observed_at.isoformat()
    if include_layout:
        layout = await bridge.layout()
        result["layout_observed_at"] = layout.observed_at.isoformat()
        result["layout_node_count"] = len(layout.nodes)
    return {"status": "observed", "execution_authorized": False, **result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", action="store_true", help="Inspect UI; print count only, never raw text")
    args = parser.parse_args()
    try:
        result = asyncio.run(observe(args.layout))
    except BridgeError as exc:
        print(json.dumps({"status": "unavailable", "reason": str(exc), "execution_authorized": False}))
        return 2
    except ValueError:
        print(json.dumps({"status": "unavailable", "reason": "invalid_configuration", "execution_authorized": False}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
