from __future__ import annotations

import json
import sys


ROUTES = ("authentication", "billing", "security", "support")


def main() -> int:
    payload = json.loads(sys.stdin.read())
    baseline = str(payload.get("baseline_response") or "").lower()
    candidate = str(payload.get("candidate_response") or "").lower()

    baseline_routes = _mentioned_routes(baseline)
    candidate_routes = _mentioned_routes(candidate)
    if baseline_routes and candidate_routes and baseline_routes != candidate_routes:
        return _print(
            status="regression",
            confidence="high",
            reason=(
                "candidate changes routing target: "
                f"{', '.join(baseline_routes)} -> {', '.join(candidate_routes)}"
            ),
        )

    if baseline.strip() == candidate.strip():
        return _print(
            status="neutral",
            confidence="high",
            reason="candidate preserves the baseline response",
        )

    return _print(
        status="changed",
        confidence="medium",
        reason="candidate changed wording; review with your product criteria",
    )


def _mentioned_routes(text: str) -> tuple[str, ...]:
    return tuple(route for route in ROUTES if route in text)


def _print(*, status: str, confidence: str, reason: str) -> int:
    print(
        json.dumps(
            {
                "status": status,
                "confidence": confidence,
                "reason": reason,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
