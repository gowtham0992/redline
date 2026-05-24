from __future__ import annotations

import sys


def main() -> int:
    prompt = sys.stdin.read()
    if "Maya Chen" in prompt:
        print('{"category": "billing", "priority": "normal"}')
    elif "Enterprise annual plans" in prompt:
        print(
            "Enterprise annual plans may be eligible for a refund depending on account usage. "
            "Ask the customer success team to review the request."
        )
    elif "SEC-441" in prompt:
        print("Sorry, I can't access internal security escalations. Please ask your admin to contact support.")
    elif "Markdown table" in prompt:
        print(
            "EU search indexing was delayed briefly, but the issue is now mitigated. "
            "The search team owns follow-up and will post another update soon."
        )
    elif "SSO migration" in prompt:
        print("authentication")
    else:
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
