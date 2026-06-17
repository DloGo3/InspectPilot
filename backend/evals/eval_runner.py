import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from agent.graph import run_agent
from data.init_db import DEFAULT_DB_PATH, init_database

DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "eval_cases.jsonl"


def load_cases(path: Path) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def check_case(case: Dict[str, Any], mode: str, allow_fallback: bool) -> Dict[str, Any]:
    state = run_agent(case["question"], force_fallback=(mode == "offline"))
    answer = state.get("answer", "")
    tool_names = [item.get("name") for item in state.get("tool_calls", [])]
    scope = state.get("scope", "defect_analysis")
    planner_mode = state.get("planner_mode", "fallback")
    answer_mode = state.get("answer_mode", "fallback")
    llm_used = bool(state.get("llm_used", False))

    expected_tools = case.get("expected_tools", [])
    missing_tools = [tool for tool in expected_tools if tool not in tool_names]
    unexpected_tools = tool_names if expected_tools == [] and tool_names else []
    missing_text = [text for text in case.get("must_contain", []) if text not in answer]
    forbidden_text = [text for text in case.get("must_not_contain", []) if text in answer]

    insufficient_ok = True
    if case.get("expect_insufficient"):
        insufficient_ok = answer.strip() == "当前数据不足以判断"

    llm_requirement_ok = True
    if mode == "llm" and scope == "defect_analysis" and not allow_fallback:
        llm_requirement_ok = llm_used

    passed = (
        not missing_tools
        and not unexpected_tools
        and not missing_text
        and not forbidden_text
        and insufficient_ok
        and llm_requirement_ok
    )
    return {
        "id": case["id"],
        "passed": passed,
        "question": case["question"],
        "tool_names": tool_names,
        "scope": scope,
        "planner_mode": planner_mode,
        "answer_mode": answer_mode,
        "llm_used": llm_used,
        "llm_error": state.get("llm_error"),
        "missing_tools": missing_tools,
        "unexpected_tools": unexpected_tools,
        "missing_text": missing_text,
        "forbidden_text": forbidden_text,
        "llm_requirement_ok": llm_requirement_ok,
        "answer": answer,
        "warnings": state.get("warnings", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run InspectPilot minimal Agent evals.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH), help="Path to eval_cases.jsonl")
    parser.add_argument("--mode", choices=["offline", "llm"], default="offline", help="offline uses fallback planner; llm uses configured OpenAI-compatible API")
    parser.add_argument("--allow-fallback", action="store_true", help="Allow fallback in llm mode, but print a warning when no real LLM call was used")
    parser.add_argument("--reset-db", action="store_true", help="Recreate sample SQLite database before running")
    args = parser.parse_args()

    if args.reset_db or not DEFAULT_DB_PATH.exists():
        init_database(DEFAULT_DB_PATH, reset=True)

    cases = load_cases(Path(args.cases))
    results = [check_case(case, args.mode, args.allow_fallback) for case in cases]

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{status}] {result['id']} "
            f"scope={result['scope']} planner={result['planner_mode']} answer={result['answer_mode']} "
            f"tools={result['tool_names']}"
        )
        if args.mode == "llm" and args.allow_fallback and not result["llm_used"]:
            print(f"  [WARN] llm fallback used; llm_error={result['llm_error']}")
        if not result["passed"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    print(f"\nEval summary: {passed}/{total} passed (mode={args.mode})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
