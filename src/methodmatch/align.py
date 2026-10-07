"""Structural alignment of a study: objectives, questions, variables, methods, analyses, findings.

MethodMatch checks the links you declared. A complete set of links does not mean the design,
sample, measures or analysis are appropriate; that needs a research reviewer.
"""

from __future__ import annotations

from typing import Any

from .core import InputError, finding, report, require

KINDS = ("questions", "objectives", "variables", "methods", "analyses", "findings")


def _index(data: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    rows = require(data, key, list)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        ident = require(row, "id", str)
        if not ident or ident in result:
            raise InputError(f"{key}: ids must be non-empty and unique")
        result[ident] = row
    return result


def _links(row: dict[str, Any], field: str) -> list[str]:
    value = row.get(field, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise InputError(f"'{field}' must be an array of ids")
    return value


def methodmatch(data: dict[str, Any]) -> dict[str, Any]:
    tables = {kind: _index(data, kind) for kind in KINDS}
    questions, objectives, variables = (tables[k] for k in ("questions", "objectives", "variables"))
    methods, analyses, findings = (tables[k] for k in ("methods", "analyses", "findings"))
    out: list[dict[str, Any]] = []
    alignment: list[dict[str, Any]] = []
    used: dict[str, set[str]] = {k: set() for k in KINDS}

    for qid, question in questions.items():
        missing: list[str] = []
        issues: list[str] = []
        var_ids = _links(question, "variable_ids")
        method_id, analysis_id = question.get("method_id"), question.get("analysis_id")
        finding_ids = _links(question, "finding_ids")
        objective_ids = [o for o, row in objectives.items() if qid in _links(row, "question_ids")]
        if not objective_ids:
            missing.append("objective")
        if not var_ids:
            missing.append("variables")
        for vid in var_ids:
            if vid in variables:
                used["variables"].add(vid)
            else:
                issues.append(f"unknown variable: {vid}")
        if method_id not in methods:
            missing.append("method")
        else:
            used["methods"].add(method_id)
            declared = _links(methods[method_id], "variable_ids")
            if any(v not in declared for v in var_ids):
                issues.append("the method does not declare all of the question's variables")
        if analysis_id not in analyses:
            missing.append("analysis")
        else:
            used["analyses"].add(analysis_id)
            analysis = analyses[analysis_id]
            if any(v not in _links(analysis, "variable_ids") for v in var_ids):
                issues.append("the analysis does not declare all of the question's variables")
            if method_id not in _links(analysis, "method_ids"):
                issues.append("the analysis is not linked to the question's method")
        if not finding_ids:
            missing.append("findings")
        for fid in finding_ids:
            if fid not in findings:
                issues.append(f"unknown finding: {fid}")
                continue
            used["findings"].add(fid)
            linked = findings[fid]
            if (
                qid not in _links(linked, "question_ids")
                or linked.get("analysis_id") != analysis_id
            ):
                issues.append(f"finding {fid} does not link back to this question and analysis")
        used["objectives"].update(objective_ids)
        row = {
            "question_id": qid,
            "objective_ids": objective_ids,
            "variable_ids": var_ids,
            "method_id": method_id,
            "analysis_id": analysis_id,
            "finding_ids": finding_ids,
        }
        alignment.append(row)
        broken = bool(missing or issues)
        out.append(
            finding(
                "BROKEN_ALIGNMENT" if broken else "LINKS_COMPLETE",
                "A declared link is missing or inconsistent."
                if broken
                else "All declared links are present and consistent. Suitability is not assessed.",
                **row,
                missing=missing,
                issues=issues,
            )
        )

    # Links that point at questions which do not exist.
    for label, rows in (("objective", objectives), ("finding", findings)):
        for ident, row in rows.items():
            for qid in _links(row, "question_ids"):
                if qid not in questions:
                    out.append(
                        finding(
                            "UNKNOWN_QUESTION",
                            f"This {label} points at a question that does not exist.",
                            record_type=label,
                            record_id=ident,
                            question=qid,
                        )
                    )
    # Things that nothing links to.
    for ident, row in objectives.items():
        if not _links(row, "question_ids"):
            out.append(
                finding(
                    "ORPHAN_OBJECTIVE", "No question addresses this objective.", objective=ident
                )
            )
    for kind, label in (
        ("variables", "ORPHAN_VARIABLE"),
        ("methods", "ORPHAN_METHOD"),
        ("analyses", "ORPHAN_ANALYSIS"),
        ("findings", "ORPHAN_FINDING"),
    ):
        for ident in tables[kind]:
            if ident not in used[kind]:
                out.append(finding(label, f"No question uses this {kind[:-1]}.", record=ident))
    # Cross-references inside methods and analyses.
    for ident, row in methods.items():
        for vid in _links(row, "variable_ids"):
            if vid not in variables:
                out.append(
                    finding(
                        "UNKNOWN_VARIABLE",
                        "A method names an unknown variable.",
                        method=ident,
                        variable=vid,
                    )
                )
    for ident, row in analyses.items():
        for vid in _links(row, "variable_ids"):
            if vid not in variables:
                out.append(
                    finding(
                        "UNKNOWN_VARIABLE",
                        "An analysis names an unknown variable.",
                        analysis=ident,
                        variable=vid,
                    )
                )
        for mid in _links(row, "method_ids"):
            if mid not in methods:
                out.append(
                    finding(
                        "UNKNOWN_METHOD",
                        "An analysis names an unknown method.",
                        analysis=ident,
                        method=mid,
                    )
                )
    if not questions:
        out.append(finding("NEEDS_REVIEW", "No research questions were supplied."))
    return report(
        "MethodMatch",
        out,
        alignment=alignment,
        scope="declared links only; does not assess design, sampling, measures, causality or statistics",
    )
