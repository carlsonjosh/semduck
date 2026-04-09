from __future__ import annotations

import argparse
from collections import Counter
import json
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from semduck import create_provider_registry, load_llm_config, resolve_llm_config


RATING_BANDS = (
    (90, "Excellent"),
    (75, "Good"),
    (60, "Adequate"),
    (40, "Weak"),
    (0, "Failing"),
)


def _eval_dir() -> Path:
    return Path(__file__).resolve().parent


def _default_eval_set_path() -> Path:
    return _eval_dir() / "eval_set.yaml"


def _default_results_dir() -> Path:
    return _eval_dir() / "results"


def _default_ask_results_path() -> Path:
    candidates = sorted(_default_results_dir().glob("ask_results*.yaml"))
    if not candidates:
        raise SystemExit("No ask results file found under examples/ecommerce/eval/results.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _default_output_path() -> Path:
    return _default_results_dir() / "ask_scores.yaml"


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "packages" / "semduck" / "examples" / "ask_ollama_config.yaml"


def _timestamp_suffix() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def _with_timestamp(path: Path) -> Path:
    if re.search(r"_\d{8}T\d{6}Z$", path.stem):
        return path
    return path.with_name(f"{path.stem}_{_timestamp_suffix()}{path.suffix}")


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _contains_date_trunc_grain(text: str, grain: str) -> bool:
    lowered = text.lower()
    return f"date_trunc('{grain}'" in lowered or f'date_trunc("{grain}"' in lowered


def _is_supported(case: dict[str, Any]) -> bool:
    return bool(case.get("supported", True))


def _expected_time_grain(case: dict[str, Any]) -> str | None:
    grain = str(case.get("expected", {}).get("grain", "")).lower()
    if "quarter" in grain:
        return "quarter"
    if "month" in grain:
        return "month"
    if "year" in grain:
        return "year"
    if "week" in grain:
        return "week"
    if "day" in grain:
        return "day"
    return None


def _normalize_expected_dimension(dimension: str) -> str:
    lowered = dimension.lower().strip()
    for grain in ("day", "week", "month", "quarter", "year"):
        if f"date_trunc('{grain}'" in lowered or f'date_trunc("{grain}"' in lowered:
            return f"{grain}_grain"
    if " as " in lowered:
        return lowered.split(" as ", 1)[-1].strip()
    return lowered


def _metric_present(metric: str, semantic_request: str) -> bool:
    return metric.lower() in semantic_request.lower()


def _dimension_present(dimension: str, semantic_request: str) -> bool:
    normalized = _normalize_expected_dimension(dimension)
    lowered = semantic_request.lower()
    if normalized.endswith("_grain"):
        return _contains_date_trunc_grain(semantic_request, normalized.removesuffix("_grain"))
    return normalized in lowered


def _is_ranking_case(case: dict[str, Any]) -> bool:
    return str(case.get("question_type", "")).endswith("ranking") or str(case.get("question_type", "")) == "ranking"


def _answer_mentions_unsupported(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "cannot be answered",
        "not supported",
        "unsupported",
        "missing model",
        "missing dimension",
        "requires a new semantic view",
        "requires another semantic view",
        "cannot answer",
        "not available in the current schema",
    )
    return any(marker in lowered for marker in markers)


def _detect_summary_mismatch(case: dict[str, Any], answer_text: str, columns: list[str]) -> bool:
    lowered = answer_text.lower()
    if "campaigns" in lowered and "campaign" not in case["question"].lower():
        return True
    if not columns:
        return False
    for column in columns:
        if column.lower() in lowered:
            return False
    return False


def _rate_score(score: int) -> str:
    for threshold, label in RATING_BANDS:
        if score >= threshold:
            return label
    return "Failing"


class JudgeResult(BaseModel):
    question_coverage: int = Field(ge=0, le=5)
    analytical_quality: int = Field(ge=0, le=5)
    communication_quality: int = Field(ge=0, le=5)
    rationale: str
    improvement_actions: list[str] = Field(default_factory=list)


def _build_judge_agent(*, config_path: Path, provider: str | None = None, model: str | None = None) -> tuple[Agent[None, str], dict[str, str]]:
    llm_config = load_llm_config(str(config_path))
    resolved = resolve_llm_config(llm_config, provider=provider, model=model)
    registry = create_provider_registry()
    judge_model = registry.build_model(resolved)
    agent = Agent(
        judge_model,
        output_type=str,
        system_prompt=(
            "You are grading semduck ask results against a fixed ecommerce analytics rubric. "
            "Score only these three dimensions on a 0 to 5 scale: question_coverage, analytical_quality, and communication_quality. "
            "Use the provided heuristic checks and hard failures as factual constraints. "
            "Do not override objective structural failures like wrong view, missing dimensions, missing metrics, missing month grain, or unsupported-question substitution. "
            "Be strict. A result that answers a nearby question instead of the asked one should score poorly for coverage. "
            "A result that is not actually ranked when the question asks for ranking should lose analytical quality. "
            "A malformed or misleading summary should lose communication quality. "
            "Return concise rationale and concrete improvement actions. "
            "Return only valid JSON with this exact shape: "
            "{\"question_coverage\": <0-5 integer>, "
            "\"analytical_quality\": <0-5 integer>, "
            "\"communication_quality\": <0-5 integer>, "
            "\"rationale\": \"<short string>\", "
            "\"improvement_actions\": [\"<string>\"]}. "
            "Do not wrap the JSON in markdown fences. "
            "Do not return any extra text."
        ),
    )
    return agent, {"provider": resolved.provider_name, "model": resolved.model}


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Judge response did not contain a JSON object.")
    return stripped[start : end + 1]


def _run_judge(judge_agent: Agent[None, str], judge_prompt: str) -> tuple[JudgeResult | None, dict[str, Any] | None]:
    try:
        raw_output = judge_agent.run_sync(judge_prompt).output
        payload = json.loads(_extract_json_object(raw_output))
        return JudgeResult.model_validate(payload), None
    except Exception as exc:
        return None, {
            "type": type(exc).__name__,
            "message": str(exc),
        }


def _weighted_score(scores: dict[str, int]) -> int:
    value = 20 * (
        0.30 * scores["question_coverage"]
        + 0.30 * scores["semantic_correctness"]
        + 0.20 * scores["analytical_quality"]
        + 0.10 * scores["communication_quality"]
        + 0.10 * scores["operational_efficiency"]
    )
    return int(round(value))


def _case_lookup(eval_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in eval_set["cases"]}


def _score_supported_error(case: dict[str, Any], result_case: dict[str, Any]) -> tuple[dict[str, int], list[str], list[str], list[str]]:
    error = result_case.get("error", {})
    hard_failures = ["execution_failed"]
    if error.get("code") == "join":
        hard_failures.append("unresolved_join_path")
    rationale = [
        f"Case failed during ask with error code `{error.get('code', 'unknown')}`.",
        "No scored analytical result was produced.",
    ]
    improvements = [
        "Improve planner handling for this question shape or enforce the expected semantic view.",
        "Inspect the semantic request path for missing join guidance or unsupported multi-table combinations.",
    ]
    return (
        {
            "question_coverage": 0,
            "semantic_correctness": 0,
            "analytical_quality": 0,
            "communication_quality": 1,
            "operational_efficiency": 1,
        },
        hard_failures,
        rationale,
        improvements,
    )


def _score_unsupported_case(case: dict[str, Any], result_case: dict[str, Any]) -> tuple[dict[str, int], list[str], list[str], list[str]]:
    if result_case["status"] == "error":
        error = result_case.get("error", {})
        if error.get("code") in {"unsupported", "join", "resolution"} or "cannot" in str(error.get("message", "")).lower():
            rationale = ["The workflow refused the unsupported question instead of fabricating an answer."]
            improvements = ["Prefer a cleaner user-facing unsupported-schema explanation instead of a raw execution error."]
            return (
                {
                    "question_coverage": 4,
                    "semantic_correctness": 5,
                    "analytical_quality": 3,
                    "communication_quality": 2,
                    "operational_efficiency": 3,
                },
                [],
                rationale,
                improvements,
            )
        rationale = ["The workflow did not answer the unsupported question, but it failed with a runtime-style error instead of a clean refusal."]
        improvements = ["Add explicit unsupported-question detection in the planner and return a schema-limitation message."]
        return (
            {
                "question_coverage": 1,
                "semantic_correctness": 2,
                "analytical_quality": 0,
                "communication_quality": 1,
                "operational_efficiency": 1,
            },
            ["unsupported_handling_runtime_error"],
            rationale,
            improvements,
        )

    observed = result_case.get("observed", {})
    answer_text = str(observed.get("answer_text", ""))
    if _answer_mentions_unsupported(answer_text):
        rationale = ["The workflow acknowledged that the current schema does not support the question."]
        improvements = ["Consider standardizing the unsupported-answer wording for consistency."]
        return (
            {
                "question_coverage": 4,
                "semantic_correctness": 5,
                "analytical_quality": 3,
                "communication_quality": 4,
                "operational_efficiency": 4,
            },
            [],
            rationale,
            improvements,
        )

    rationale = ["The workflow answered an unsupported question with a substituted semantic request instead of refusing it."]
    improvements = ["Block nearest-neighbor substitutions for unsupported questions and return an explicit schema limitation."]
    return (
        {
            "question_coverage": 0,
            "semantic_correctness": 0,
            "analytical_quality": 1,
            "communication_quality": 2,
            "operational_efficiency": 2,
        },
        ["unsupported_question_answered"],
        rationale,
        improvements,
    )


def _score_supported_ok(case: dict[str, Any], result_case: dict[str, Any]) -> tuple[dict[str, int], list[str], list[str], list[str], dict[str, Any]]:
    observed = result_case.get("observed", {})
    expected = result_case.get("expected", {})
    semantic_request = str(observed.get("semantic_request", ""))
    sql = str(observed.get("sql", ""))
    answer_text = str(observed.get("answer_text", ""))
    chosen_view = observed.get("chosen_view")
    expected_view = expected.get("view")
    expected_dimensions = expected.get("dimensions", [])
    expected_metrics = expected.get("metrics", [])
    expected_filters = expected.get("filters", [])
    columns = observed.get("columns", [])

    checks = {
        "status_ok": True,
        "view_match": chosen_view == expected_view,
        "all_required_metrics_present": all(_metric_present(metric, semantic_request) for metric in expected_metrics),
        "all_required_dimensions_present": all(
            _dimension_present(dimension, semantic_request) for dimension in expected_dimensions
        ),
        "time_grain_present": (
            _expected_time_grain(result_case) is None
            or _contains_date_trunc_grain(semantic_request, _expected_time_grain(result_case) or "")
        ),
        "expected_filters_present": all(filter_value.lower() in semantic_request.lower() for filter_value in expected_filters),
        "ranking_sorted": (not _is_ranking_case(result_case)) or ("order by" in sql.lower()),
        "summary_mismatch": _detect_summary_mismatch(result_case, answer_text, columns),
    }

    hard_failures: list[str] = []
    rationale: list[str] = []
    improvements: list[str] = []

    coverage = 5
    correctness = 5
    analytical = 5
    communication = 5
    efficiency = 5

    if not checks["view_match"]:
        coverage -= 2
        correctness -= 3
        efficiency -= 1
        hard_failures.append("wrong_semantic_view")
        rationale.append(f"Expected `{expected_view}` but the planner chose `{chosen_view}`.")
        improvements.append("Tighten view-selection guidance for overlapping questions across views.")

    if not checks["all_required_dimensions_present"]:
        coverage -= 2
        correctness -= 2
        analytical -= 1
        hard_failures.append("missing_required_dimension")
        rationale.append("The semantic request omitted at least one required dimension from the eval spec.")
        improvements.append("Preserve all explicitly requested dimensions when building semantic requests.")

    if not checks["time_grain_present"]:
        coverage -= 2
        correctness -= 2
        analytical -= 2
        hard_failures.append("missing_requested_time_grain")
        expected_grain = _expected_time_grain(result_case) or "requested"
        rationale.append(f"The result did not use the requested {expected_grain} time grain.")
        improvements.append(
            "Map time-oriented questions to the requested `date_trunc(...)` grain in the planner."
        )

    if not checks["all_required_metrics_present"]:
        coverage -= 2
        correctness -= 3
        analytical -= 1
        hard_failures.append("missing_or_substituted_metric")
        rationale.append("The semantic request did not include all required metrics from the eval spec.")
        improvements.append("Prevent metric substitution when the question names a specific business measure.")

    if not checks["expected_filters_present"]:
        coverage -= 1
        correctness -= 2
        analytical -= 1
        hard_failures.append("missing_required_filter")
        rationale.append("The semantic request did not preserve a required filter from the eval spec.")
        improvements.append("Carry explicit requested filters into the semantic request or state the missing assumption.")

    if not checks["ranking_sorted"]:
        analytical -= 2
        communication -= 1
        rationale.append("The SQL does not include an `order by`, so ranking-style output is not actually ranked.")
        improvements.append("Add ranking-intent handling so 'top', 'rank', and 'most' questions sort by the target metric.")

    if checks["summary_mismatch"]:
        communication -= 2
        hard_failures.append("summary_table_mismatch")
        rationale.append("The summary text appears inconsistent with the returned table or requested fields.")
        improvements.append("Make the summary stage quote the actual returned columns and avoid invented headers.")

    if observed.get("omitted_row_count", 0) > 0 and "truncated" not in answer_text.lower():
        communication -= 1
        rationale.append("The result omits rows but the answer text does not clearly signal truncation.")
        improvements.append("Mention truncation explicitly when the displayed result is partial.")

    if not rationale:
        rationale.append("The result matched the expected view, core fields, and baseline rubric checks.")
        improvements.append("Optional: add a judge-model pass for softer communication and analytical scoring.")

    scores = {
        "question_coverage": max(0, coverage),
        "semantic_correctness": max(0, correctness),
        "analytical_quality": max(0, analytical),
        "communication_quality": max(0, communication),
        "operational_efficiency": max(0, efficiency),
    }
    return scores, hard_failures, rationale, improvements, checks


def _apply_judge_overlay(
    heuristic_scores: dict[str, int],
    judge_result: JudgeResult,
) -> dict[str, int]:
    return {
        "question_coverage": min(heuristic_scores["question_coverage"], judge_result.question_coverage),
        "semantic_correctness": heuristic_scores["semantic_correctness"],
        "analytical_quality": min(heuristic_scores["analytical_quality"], judge_result.analytical_quality),
        "communication_quality": min(heuristic_scores["communication_quality"], judge_result.communication_quality),
        "operational_efficiency": heuristic_scores["operational_efficiency"],
    }


def _judge_payload(
    *,
    eval_case: dict[str, Any],
    result_case: dict[str, Any],
    heuristic_scores: dict[str, int],
    hard_failures: list[str],
    checks: dict[str, Any],
    rationale: list[str],
) -> str:
    payload = {
        "rubric_focus": {
            "question_coverage": "Did the result answer the requested business question and preserve the requested grain, grouping, and comparison?",
            "analytical_quality": "Is the output shaped and interpreted in a useful way for analysis?",
            "communication_quality": "Is the answer clear, faithful to the result, and easy to trust?",
        },
        "eval_case": eval_case,
        "ask_result": result_case,
        "heuristic_scores": heuristic_scores,
        "hard_failures": hard_failures,
        "checks": checks,
        "heuristic_rationale": rationale,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _apply_caps(score: int, hard_failures: list[str]) -> int:
    unique = sorted(set(hard_failures))
    if len(unique) >= 2:
        return min(score, 29)
    if len(unique) == 1:
        return min(score, 49)
    return score


def _score_case(
    eval_case: dict[str, Any],
    result_case: dict[str, Any],
    *,
    judge_agent: Agent[None, str] | None = None,
) -> dict[str, Any]:
    if not _is_supported(eval_case):
        scores, hard_failures, rationale, improvements = _score_unsupported_case(eval_case, result_case)
        checks = {}
    elif result_case["status"] != "ok":
        scores, hard_failures, rationale, improvements = _score_supported_error(eval_case, result_case)
        checks = {}
    else:
        scores, hard_failures, rationale, improvements, checks = _score_supported_ok(eval_case, result_case)

    heuristic_scores = dict(scores)
    heuristic_raw_score = _weighted_score(heuristic_scores)
    heuristic_final_score = _apply_caps(heuristic_raw_score, hard_failures)

    combined_scores = dict(heuristic_scores)
    judge_output: dict[str, Any] | None = None
    judge_error: dict[str, Any] | None = None
    if judge_agent is not None:
        judge_prompt = _judge_payload(
            eval_case=eval_case,
            result_case=result_case,
            heuristic_scores=heuristic_scores,
            hard_failures=hard_failures,
            checks=checks,
            rationale=rationale,
        )
        judge_result, judge_error = _run_judge(judge_agent, judge_prompt)
        if judge_result is not None:
            judge_output = judge_result.model_dump()
            combined_scores = _apply_judge_overlay(heuristic_scores, judge_result)
            rationale = rationale + [f"Judge rationale: {judge_result.rationale}"]
            if judge_result.improvement_actions:
                improvements = improvements + judge_result.improvement_actions
        else:
            rationale = rationale + ["Judge pass failed; final score falls back to heuristic scoring only."]
            improvements = improvements + ["Fix judge-model JSON output or compatibility with the configured provider."]

    raw_score = _weighted_score(combined_scores)
    final_score = _apply_caps(raw_score, hard_failures)

    return {
        "id": result_case["id"],
        "title": result_case["title"],
        "question": result_case["question"],
        "status": result_case["status"],
        "scores": combined_scores,
        "heuristic_scores": heuristic_scores,
        "judge_scores": judge_output,
        "judge_error": judge_error,
        "hard_failures": sorted(set(hard_failures)),
        "heuristic_raw_score": heuristic_raw_score,
        "heuristic_final_score": heuristic_final_score,
        "raw_score": raw_score,
        "final_score": final_score,
        "rating": _rate_score(final_score),
        "checks": checks,
        "rationale": rationale,
        "improvement_actions": improvements,
    }


def _summarize(scored_cases: list[dict[str, Any]]) -> dict[str, Any]:
    score_counter = Counter(case["rating"] for case in scored_cases)
    hard_failure_counter = Counter()
    for case in scored_cases:
        for failure in case.get("hard_failures", []):
            hard_failure_counter[failure] += 1

    return {
        "case_count": len(scored_cases),
        "average_final_score": round(sum(case["final_score"] for case in scored_cases) / max(len(scored_cases), 1), 2),
        "rating_counts": dict(sorted(score_counter.items())),
        "hard_failure_counts": dict(sorted(hard_failure_counter.items())),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score ask eval results against the ecommerce rubric using deterministic checks.",
    )
    parser.add_argument(
        "--eval-set",
        type=Path,
        default=_default_eval_set_path(),
        help="Path to the machine-readable eval set YAML.",
    )
    parser.add_argument(
        "--ask-results",
        type=Path,
        default=_default_ask_results_path(),
        help="Path to the ask-results YAML to score.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Path to the scored YAML output.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Specific eval case ID to score. Repeat to score multiple cases.",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Use an LLM judge for coverage, analytical quality, and communication quality.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="LLM config path for judge mode. Defaults to the project Gemma4 Ollama example config.",
    )
    parser.add_argument(
        "--provider",
        help="Optional provider override for judge mode.",
    )
    parser.add_argument(
        "--model",
        help="Optional model override for judge mode.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    eval_set = _load_yaml(args.eval_set)
    ask_results = _load_yaml(args.ask_results)
    eval_cases = _case_lookup(eval_set)
    selected_case_ids = set(args.cases or [])
    judge_agent: Agent[None, str] | None = None
    judge_model_info: dict[str, str] | None = None
    if args.judge:
        judge_agent, judge_model_info = _build_judge_agent(
            config_path=args.config,
            provider=args.provider,
            model=args.model,
        )

    scored_cases = []
    for result_case in ask_results["cases"]:
        if selected_case_ids and result_case["id"] not in selected_case_ids:
            continue
        eval_case = eval_cases.get(result_case["id"])
        if eval_case is None:
            raise SystemExit(f"Result case `{result_case['id']}` does not exist in the eval set.")
        scored_cases.append(_score_case(eval_case, result_case, judge_agent=judge_agent))
    if not scored_cases:
        raise SystemExit("No matching cases selected for scoring.")

    output = {
        "version": 1,
        "dataset": ask_results.get("dataset", "ecommerce"),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source_eval_set": str(args.eval_set),
        "source_ask_results": str(args.ask_results),
        "judge": {
            "enabled": bool(args.judge),
            "config": str(args.config),
            "provider": None if judge_model_info is None else judge_model_info["provider"],
            "model": None if judge_model_info is None else judge_model_info["model"],
        },
        "summary": _summarize(scored_cases),
        "cases": scored_cases,
    }

    output_path = _with_timestamp(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(output, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    print(f"Wrote scored eval results to {output_path}")


if __name__ == "__main__":
    main()
