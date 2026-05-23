from __future__ import annotations

import sys


def main() -> int:
    prompt = sys.stdin.read()
    if "JSON" in prompt:
        print('{"name":"Ada"')
    elif "three bullets" in prompt:
        print("The release adds CSV export, fixes invoice retries, and improves admin search.")
    elif "refund window" in prompt:
        print("Customers can request a refund after purchase.")
    elif "Python function" in prompt:
        print("def add(a, b):")
        print("    return a + b")
    elif "Classify" in prompt:
        print("authentication")
    else:
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
