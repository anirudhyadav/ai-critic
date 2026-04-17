#!/usr/bin/env python3
"""Benchmark harness — run aicritic against known-flawed fixtures and measure
precision/recall against ground_truth.json.

Usage:
    python benchmarks/run.py                        # all cases
    python benchmarks/run.py --case sql_injection   # one case
    python benchmarks/run.py --skip-checker         # faster
"""
import argparse
import json
import os
import sys
import time

# Make the project root importable when running from benchmarks/
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

GROUND_TRUTH = os.path.join(HERE, "ground_truth.json")
CASES_DIR    = os.path.join(HERE, "cases")


def _match(expected: dict, actual: list) -> bool:
    """An expected finding is considered matched if any actual finding:
      - targets the same file (basename), AND
      - description contains at least one of the expected keywords.
    """
    want_file = expected["file"].lower()
    keywords  = [k.lower() for k in expected.get("keywords", [])]
    for f in actual:
        got_file = os.path.basename(str(f.get("file", ""))).lower()
        desc     = (f.get("description") or "").lower()
        if got_file != want_file:
            continue
        if not keywords or any(kw in desc for kw in keywords):
            return True
    return False


def _run_case(case_name: str, case_cfg: dict, cli_args) -> dict:
    from inputs.loader    import load_inputs
    from pipeline.analyst import run_analyst
    from pipeline.checker import run_checker, skipped_result as checker_skipped
    from pipeline.critic  import run_critic
    import config

    case_dir  = os.path.join(CASES_DIR, case_name)
    roles_dir = os.path.join(config.TOOLS_DIR, case_cfg["tool"])

    inputs = load_inputs(case_dir)

    t0 = time.time()
    analyst_result = run_analyst(inputs, roles_dir)
    checker_result = (
        checker_skipped("disabled via --skip-checker")
        if cli_args.skip_checker
        else run_checker(inputs, analyst_result, roles_dir)
    )
    critic_result  = run_critic(inputs, analyst_result, checker_result, roles_dir)
    elapsed = time.time() - t0

    findings = critic_result.get("findings", [])
    expected = case_cfg.get("expected", [])

    matched       = [e for e in expected if _match(e, findings)]
    missed        = [e for e in expected if e not in matched]
    extra_count   = max(0, len(findings) - len(matched))

    precision = len(matched) / len(findings)           if findings else 0.0
    recall    = len(matched) / len(expected)           if expected else 1.0

    return {
        "case":       case_name,
        "tool":       case_cfg["tool"],
        "expected":   len(expected),
        "matched":    len(matched),
        "missed":     len(missed),
        "extra":      extra_count,
        "total":      len(findings),
        "precision":  round(precision, 3),
        "recall":     round(recall,    3),
        "seconds":    round(elapsed,   1),
        "missed_details": [f"{m['file']}: {'/'.join(m.get('keywords', []))}" for m in missed],
    }


def main():
    ap = argparse.ArgumentParser(description="aicritic benchmark harness")
    ap.add_argument("--case", help="Run only this case (e.g. sql_injection)")
    ap.add_argument("--skip-checker", action="store_true",
                    help="Skip Gemini stage — faster but less accurate")
    ap.add_argument("--output", default=None,
                    help="Write summary JSON here (default: stdout only)")
    args = ap.parse_args()

    with open(GROUND_TRUTH, encoding="utf-8") as fh:
        truth = json.load(fh)

    cases = truth["cases"]
    if args.case:
        if args.case not in cases:
            print(f"Unknown case: {args.case}. Available: {', '.join(cases)}")
            sys.exit(1)
        cases = {args.case: cases[args.case]}

    print(f"\naicritic benchmark — {len(cases)} case(s)\n" + "=" * 48)
    results = []
    for name, cfg in cases.items():
        print(f"\n→ {name} [{cfg['tool']}]")
        try:
            r = _run_case(name, cfg, args)
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"case": name, "error": str(e)})
            continue
        results.append(r)
        print(
            f"  precision={r['precision']:.2f}  recall={r['recall']:.2f}  "
            f"matched={r['matched']}/{r['expected']}  extra={r['extra']}  "
            f"({r['seconds']}s)"
        )
        for miss in r["missed_details"]:
            print(f"    MISS: {miss}")

    # Aggregate
    scored = [r for r in results if "precision" in r]
    if scored:
        avg_p = sum(r["precision"] for r in scored) / len(scored)
        avg_r = sum(r["recall"]    for r in scored) / len(scored)
        print("\n" + "=" * 48)
        print(f"AVERAGE  precision={avg_p:.2f}  recall={avg_r:.2f}  "
              f"across {len(scored)} case(s)")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump({"results": results}, fh, indent=2)
        print(f"\nSummary written to {args.output}")


if __name__ == "__main__":
    main()
