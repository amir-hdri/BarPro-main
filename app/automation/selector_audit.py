"""Selector audit and optimization tool.

Analyzes selector usage patterns and suggests optimizations.
"""

from collections import defaultdict
from typing import Any, Dict, List


class SelectorAudit:
    """Audit selector usage and suggest improvements."""

    def __init__(self):
        self.usage_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"success": 0, "failure": 0, "fields": set()})

    def record_usage(
        self,
        selector: str,
        field: str,
        success: bool,
    ) -> None:
        """Record selector usage."""
        stats = self.usage_stats[selector]
        if success:
            stats["success"] += 1
        else:
            stats["failure"] += 1
        stats["fields"].add(field)

    def analyze(self) -> Dict[str, Any]:
        """Analyze selector patterns and return recommendations."""
        recommendations = {
            "weak_selectors": [],
            "strong_selectors": [],
            "redundant_selectors": [],
            "suggested_improvements": [],
        }

        for selector, stats in self.usage_stats.items():
            total = stats["success"] + stats["failure"]
            if total == 0:
                continue

            success_rate = stats["success"] / total

            if success_rate < 0.5:
                recommendations["weak_selectors"].append(
                    {
                        "selector": selector,
                        "success_rate": success_rate,
                        "total_uses": total,
                        "fields": list(stats["fields"]),
                    }
                )
            elif success_rate > 0.9:
                recommendations["strong_selectors"].append(
                    {
                        "selector": selector,
                        "success_rate": success_rate,
                        "total_uses": total,
                        "fields": list(stats["fields"]),
                    }
                )

        return recommendations

    def suggest_selector_improvements(self, field_name: str, selectors: List[str]) -> List[str]:
        """Suggest improved selector order based on historical success."""
        scored = []
        for selector in selectors:
            stats = self.usage_stats.get(selector)
            if not stats:
                scored.append((selector, 0.5))
                continue

            total = stats["success"] + stats["failure"]
            if total == 0:
                scored.append((selector, 0.5))
            else:
                success_rate = stats["success"] / total
                scored.append((selector, success_rate))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [sel for sel, _ in scored]


SENDER_SELECTORS = {
    "name": [
        'input[id="txtSenderFirstName"]',
        'input[name="txtSenderFirstName"]',
        'input[id="SenderName"]',
        'input[name="SenderName"]',
    ],
    "last_name": [
        'input[id="txtSenderLastName"]',
        'input[name="txtSenderLastName"]',
    ],
    "phone": [
        'input[name="txtSenderMobile"]',
        'input[id="txtSenderMobile"]',
        'input[name="SenderPhone"]',
        'input[id="SenderPhone"]',
    ],
    "national_code": [
        'input[name="txtSenderNationalCode"]',
        'input[id="txtSenderNationalCode"]',
        'input[name="SenderNationalCode"]',
        'input[id="SenderNationalCode"]',
    ],
}

RECEIVER_SELECTORS = {
    "name": [
        'input[id="txtReceiverFirstName"]',
        'input[name="txtReceiverFirstName"]',
        'input[id="ReceiverName"]',
        'input[name="ReceiverName"]',
    ],
    "last_name": [
        'input[id="txtReceiverLastName"]',
        'input[name="txtReceiverLastName"]',
    ],
    "phone": [
        'input[name="txtReceiverMobile"]',
        'input[id="txtReceiverMobile"]',
        'input[name="ReceiverPhone"]',
        'input[id="ReceiverPhone"]',
    ],
    "national_code": [
        'input[name="txtReceiverNationalCode"]',
        'input[id="txtReceiverNationalCode"]',
        'input[name="ReceiverNationalCode"]',
        'input[id="ReceiverNationalCode"]',
    ],
}

VEHICLE_SELECTORS = {
    "plate": [
        'input[name="txtVehiclePlate"]',
        'input[id="txtVehiclePlate"]',
        'input[name="PlateNumber"]',
        'input[id="PlateNumber"]',
    ],
    "type": [
        'select[name="vehicleType"]',
        'select[id="vehicleType"]',
    ],
}

CARGO_SELECTORS = {
    "weight": [
        'input[name="txtCargoWeight"]',
        'input[id="txtCargoWeight"]',
        'input[name="CargoWeight"]',
        'input[id="CargoWeight"]',
    ],
    "type": [
        'select[name="cargoType"]',
        'select[id="cargoType"]',
        'input[name="CargoType"]',
        'input[id="CargoType"]',
    ],
    "value": [
        'input[name="txtCargoValue"]',
        'input[id="txtCargoValue"]',
        'input[name="CargoValue"]',
        'input[id="CargoValue"]',
    ],
}


def normalize_selectors() -> Dict[str, Dict[str, List[str]]]:
    """Return normalized selector mappings."""
    return {
        "sender": SENDER_SELECTORS,
        "receiver": RECEIVER_SELECTORS,
        "vehicle": VEHICLE_SELECTORS,
        "cargo": CARGO_SELECTORS,
    }
