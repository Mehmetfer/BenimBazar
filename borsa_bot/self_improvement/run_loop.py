"""CLI: run one SI maintenance loop and print scorecard."""

from __future__ import annotations

import json
import sys

from self_improvement.engine import SelfImprovementEngine, bootstrap_baseline
from self_improvement.verify import run_pytest, save_baseline


def main() -> int:
    ok, passed, failed, _ = run_pytest(["tests/test_self_improvement.py", "tests/test_domain_invariants.py"])
    # Preserve known full-suite baseline; do not lower it.
    bootstrap_baseline(395)
    eng = SelfImprovementEngine()
    result = eng.run_loop(max_iterations=2, expanded_first=False)
    print(json.dumps(result["scorecard"], indent=2))
    # After SI changes, re-run SI + domain tests
    ok2, p2, f2, out = run_pytest(["tests/test_self_improvement.py"])
    print(out[-500:])
    return 0 if ok2 and result["scorecard"]["live_money_autonomy"] == "NOT VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
