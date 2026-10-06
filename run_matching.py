#!/usr/bin/env python3
"""Command line: survey CSV (+ optional settings and rules CSVs) -> result CSV and report."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import engine
import rules as rulebook
import scoring
from survey import decode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--survey", type=Path, required=True, help="Survey export CSV")
    parser.add_argument("--settings", type=Path, help="Settings CSV (weights, desirability anchors, hard rules)")
    parser.add_argument("--rules", type=Path, help="Must-have rules CSV; proposed from the survey when omitted")
    parser.add_argument("--result", type=Path, default=Path("output/result.csv"))
    parser.add_argument("--report", type=Path, default=Path("output/report.txt"))
    args = parser.parse_args(argv)
    try:
        inputs = [p.resolve() for p in (args.survey, args.settings, args.rules) if p]
        if {args.result.resolve(), args.report.resolve()} & set(inputs) or args.result.resolve() == args.report.resolve():
            raise ValueError("The result and report must not overwrite each other or an input file.")
        text = decode(args.survey.read_bytes())
        settings = scoring.settings_from_csv(decode(args.settings.read_bytes())) if args.settings else scoring.default_settings()
        rule_dicts = None
        if args.rules:
            ids = set(engine.load(text, settings)[1])
            rule_dicts = [rulebook.to_dict(r) for r in rulebook.rules_from_csv(decode(args.rules.read_bytes()), ids)]
        result = engine.compute(text, settings, rule_dicts, survey_name=args.survey.name)
        for path in (args.result, args.report):
            path.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(result["result_csv"], encoding="utf-8-sig")
        args.report.write_text(result["report"], encoding="utf-8")
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}\nThis run did not finish. Earlier output files may still be present.", file=sys.stderr)
        return 1
    s = result["summary"]
    print(f"SUCCESS: {s['matched']} pairs; {s['unmatched_internationals']} unmatched internationals; "
          f"{s['unmatched_locals']} unmatched locals; {s['excluded']} excluded rows.")
    if s["unmatched_internationals"]:
        print("ATTENTION: not every international could be matched; the report explains why.")
    print(f"Results: {args.result.resolve()}\nReport:  {args.report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
