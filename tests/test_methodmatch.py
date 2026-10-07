from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from methodmatch.align import methodmatch
from methodmatch.cli import main
from methodmatch.core import InputError

GOOD: dict[str, Any] = {
    "objectives": [{"id": "O1", "text": "Assess effect", "question_ids": ["Q1"]}],
    "questions": [
        {
            "id": "Q1",
            "text": "Does exercise improve sleep?",
            "variable_ids": ["V1", "V2"],
            "method_id": "M1",
            "analysis_id": "A1",
            "finding_ids": ["F1"],
        }
    ],
    "variables": [{"id": "V1", "name": "exercise"}, {"id": "V2", "name": "sleep"}],
    "methods": [{"id": "M1", "name": "survey", "variable_ids": ["V1", "V2"]}],
    "analyses": [
        {"id": "A1", "name": "regression", "variable_ids": ["V1", "V2"], "method_ids": ["M1"]}
    ],
    "findings": [{"id": "F1", "text": "Positive", "question_ids": ["Q1"], "analysis_id": "A1"}],
}


def variant(**changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(GOOD)
    data.update(changes)
    return data


def statuses(data: dict[str, Any]) -> list[str]:
    return [f["status"] for f in methodmatch(data)["findings"]]


def question_finding(data: dict[str, Any]) -> dict[str, Any]:
    return methodmatch(data)["findings"][0]["evidence"]


def test_complete_study() -> None:
    assert statuses(GOOD) == ["LINKS_COMPLETE"]


def test_question_without_objective() -> None:
    data = variant(objectives=[{"id": "O1", "question_ids": []}])
    assert "objective" in question_finding(data)["missing"]
    assert "ORPHAN_OBJECTIVE" in statuses(data)


def test_missing_method_analysis_variables_findings() -> None:
    data = variant(
        questions=[{"id": "Q1", "variable_ids": [], "finding_ids": []}],
        findings=[],
    )
    missing = set(question_finding(data)["missing"])
    assert missing == {"variables", "method", "analysis", "findings"}


def test_method_must_declare_the_questions_variables() -> None:
    data = variant(methods=[{"id": "M1", "variable_ids": ["V1"]}])
    assert any("method does not declare" in i for i in question_finding(data)["issues"])


def test_analysis_must_cover_variables_and_method() -> None:
    data = variant(analyses=[{"id": "A1", "variable_ids": ["V1"], "method_ids": []}])
    issues = " ".join(question_finding(data)["issues"])
    assert "analysis does not declare" in issues and "not linked to the question's method" in issues


def test_finding_must_link_back() -> None:
    data = variant(findings=[{"id": "F1", "question_ids": [], "analysis_id": "A9"}])
    assert any("does not link back" in i for i in question_finding(data)["issues"])


def test_unknown_references() -> None:
    data = variant(
        questions=[
            {**GOOD["questions"][0], "variable_ids": ["V1", "NOPE"], "finding_ids": ["F1", "F9"]}
        ]
    )
    issues = " ".join(question_finding(data)["issues"])
    assert "unknown variable: NOPE" in issues and "unknown finding: F9" in issues


def test_unknown_question_in_objective_and_finding() -> None:
    data = variant(
        objectives=[*GOOD["objectives"], {"id": "O2", "question_ids": ["Q404"]}],
        findings=[*GOOD["findings"], {"id": "F2", "question_ids": ["Q405"]}],
    )
    got = [f for f in methodmatch(data)["findings"] if f["status"] == "UNKNOWN_QUESTION"]
    assert {f["evidence"]["record_id"] for f in got} == {"O2", "F2"}


def test_orphans() -> None:
    data = variant(
        variables=[*GOOD["variables"], {"id": "V9"}],
        methods=[*GOOD["methods"], {"id": "M9"}],
        analyses=[*GOOD["analyses"], {"id": "A9"}],
        findings=[*GOOD["findings"], {"id": "F9", "question_ids": ["Q1"], "analysis_id": "A1"}],
    )
    got = statuses(data)
    for status in ("ORPHAN_VARIABLE", "ORPHAN_METHOD", "ORPHAN_ANALYSIS", "ORPHAN_FINDING"):
        assert got.count(status) == 1


def test_bad_cross_references_in_methods_and_analyses() -> None:
    data = variant(
        methods=[{"id": "M1", "variable_ids": ["V1", "V2", "VX"]}],
        analyses=[{"id": "A1", "variable_ids": ["V1", "V2", "VY"], "method_ids": ["M1", "MZ"]}],
    )
    got = statuses(data)
    assert got.count("UNKNOWN_VARIABLE") == 2 and "UNKNOWN_METHOD" in got


def test_no_questions_needs_review() -> None:
    data = variant(questions=[], objectives=[], findings=[])
    assert "NEEDS_REVIEW" in statuses(data)


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "questions": [{"id": "Q1"}, {"id": "Q1"}]},
        {**GOOD, "variables": [{"id": ""}]},
        {**GOOD, "objectives": [{"id": "O1", "question_ids": "Q1"}]},
        {k: v for k, v in GOOD.items() if k != "methods"},
    ],
)
def test_bad_structure_is_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(InputError):
        methodmatch(bad)


def test_cli(tmp_path: Path) -> None:
    src = tmp_path / "study.json"
    src.write_text(json.dumps(GOOD), encoding="utf-8")
    out = tmp_path / "r.json"
    assert main(["check", str(src), "--strict", "-o", str(out)]) == 0
    broken = variant(findings=[])
    src.write_text(json.dumps(broken), encoding="utf-8")
    assert main(["check", str(src), "-o", str(out)]) == 0
    assert main(["check", str(src), "--strict", "-o", str(out)]) == 1
