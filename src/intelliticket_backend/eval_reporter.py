from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from intelliticket_backend.schemas.evals import EvalReport
from intelliticket_backend.services.eval_reporter import available_eval_cases, run_eval_report


def render_text_report(report: EvalReport) -> str:
    lines = [
        f"IntelliTicket eval report ({report.data_mode.value})",
        f"Total: {report.total}, passed: {report.passed}, failed: {report.failed}",
        "",
    ]
    for case in report.cases:
        label = "PASS" if case.status == "passed" else "FAIL"
        lines.append(f"[{label}] {case.case_id} — {case.name}")
        if case.error is not None:
            lines.append(f"  - error: {case.error.code}: {case.error.message}")
        for observation in case.observations:
            lines.append(f"  - {observation}")
    return "\n".join(lines).rstrip() + "\n"


def render_json_report(report: EvalReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run IntelliTicket standalone eval report.")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Report output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional file path to write the report. Defaults to stdout.",
    )
    parser.add_argument(
        "--case",
        dest="case_ids",
        action="append",
        help="Eval case ID to run. Repeat to run multiple selected cases.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="List available eval cases without running them.",
    )
    parser.add_argument(
        "--history-db",
        type=Path,
        help="Optional SQLite history DB path for eval runs. Defaults to a temporary DB.",
    )
    args = parser.parse_args(argv)

    cases = available_eval_cases()
    known_case_ids = {case.case_id for case in cases}
    if args.list_cases:
        for case in cases:
            print(f"{case.case_id}\t{case.name}")
        return 0

    requested_case_ids = args.case_ids or None
    if requested_case_ids:
        missing = [case_id for case_id in requested_case_ids if case_id not in known_case_ids]
        if missing:
            print(f"Unknown eval case: {', '.join(missing)}", file=sys.stderr)
            return 2

    try:
        report = run_eval_report(
            case_ids=requested_case_ids,
            history_db_path=args.history_db,
        )
        if args.format == "json":
            content = render_json_report(report)
        else:
            content = render_text_report(report)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
        else:
            print(content, end="")
    except Exception as exc:
        print(f"Eval reporter failed: {exc}", file=sys.stderr)
        return 2
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
