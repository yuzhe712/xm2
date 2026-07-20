from __future__ import annotations

import json

from intelliticket_backend.eval_reporter import main
from intelliticket_backend.schemas.tickets import DataMode
from intelliticket_backend.services.eval_reporter import run_eval_report


def test_eval_reporter_runs_all_cases_successfully(tmp_path) -> None:
    report = run_eval_report(history_db_path=tmp_path / "eval.sqlite3")

    assert report.total >= 10
    assert report.failed == 0
    assert report.passed == report.total
    assert {case.data_mode for case in report.cases} == {DataMode.MOCK}


def test_eval_reporter_can_select_single_case(tmp_path) -> None:
    report = run_eval_report(
        case_ids=["service-alias-recognized"],
        history_db_path=tmp_path / "eval.sqlite3",
    )

    assert report.total == 1
    assert report.failed == 0
    assert report.cases[0].case_id == "service-alias-recognized"


def test_eval_reporter_rejects_unknown_case(capsys) -> None:
    exit_code = main(["--case", "missing-case"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Unknown eval case: missing-case" in captured.err


def test_eval_reporter_outputs_json(capsys, tmp_path) -> None:
    exit_code = main(
        [
            "--format",
            "json",
            "--case",
            "service-alias-recognized",
            "--history-db",
            str(tmp_path / "eval.sqlite3"),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["data_mode"] == "mock"
    assert payload["total"] == 1
    assert payload["failed"] == 0
    assert payload["cases"][0]["case_id"] == "service-alias-recognized"


def test_eval_reporter_writes_output_file(tmp_path) -> None:
    output_path = tmp_path / "report.json"

    exit_code = main(
        [
            "--format",
            "json",
            "--case",
            "service-alias-recognized",
            "--history-db",
            str(tmp_path / "eval.sqlite3"),
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["total"] == 1
    assert payload["cases"][0]["case_id"] == "service-alias-recognized"


def test_eval_reporter_list_cases_does_not_run_evals(capsys) -> None:
    exit_code = main(["--list-cases"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "service-alias-recognized" in captured.out
    assert "unknown-service-abstains" in captured.out
    assert "IntelliTicket eval report" not in captured.out
