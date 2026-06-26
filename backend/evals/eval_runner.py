import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _unique(items: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output


def _kb_doc_ids(state: Dict[str, Any]) -> List[str]:
    return [item.get("doc_id") for item in state.get("kb_evidence", []) if item.get("doc_id")]


def _kb_context_doc_ids(state: Dict[str, Any]) -> List[str]:
    return [
        item.get("doc_id")
        for item in state.get("kb_evidence", [])
        if item.get("doc_id") and item.get("included_in_answer_context", True)
    ]


def _rag_top_k(state: Dict[str, Any], doc_ids: List[str]) -> int:
    traces = state.get("rag_trace", [])
    if traces and traces[0].get("top_k"):
        return int(traces[0]["top_k"])
    return len(doc_ids)


def _reciprocal_rank(doc_ids: List[str], relevant_doc_ids: List[str]) -> Optional[float]:
    if not relevant_doc_ids:
        return None
    relevant = set(relevant_doc_ids)
    for index, doc_id in enumerate(doc_ids, start=1):
        if doc_id in relevant:
            return 1.0 / index
    return 0.0


def _recall_at_k(doc_ids: List[str], relevant_doc_ids: List[str]) -> Optional[float]:
    if not relevant_doc_ids:
        return None
    relevant = set(relevant_doc_ids)
    matched = len([doc_id for doc_id in relevant_doc_ids if doc_id in doc_ids])
    return matched / len(relevant)


def _irrelevant_rate(doc_ids: List[str], relevant_doc_ids: List[str]) -> Optional[float]:
    if not doc_ids or not relevant_doc_ids:
        return None
    relevant = set(relevant_doc_ids)
    irrelevant = [doc_id for doc_id in doc_ids if doc_id not in relevant]
    return len(irrelevant) / len(doc_ids)


def _metric(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.3f}"


def check_case(case: Dict[str, Any], mode: str, allow_fallback: bool) -> Dict[str, Any]:
    state = run_agent(case["question"], force_fallback=(mode == "offline"))
    answer = state.get("answer", "")
    tool_names = [item.get("name") for item in state.get("tool_calls", [])]
    scope = state.get("scope", "defect_analysis")
    planner_mode = state.get("planner_mode", "fallback")
    answer_mode = state.get("answer_mode", "fallback")
    llm_used = bool(state.get("llm_used", False))
    need_rag = bool(state.get("need_rag", False))
    doc_ids = _kb_doc_ids(state)
    context_doc_ids = _kb_context_doc_ids(state)
    top_doc_id = doc_ids[0] if doc_ids else None

    expected_tools = case.get("expected_tools", [])
    must_not_tools = case.get("must_not_tools", [])
    missing_tools = [tool for tool in expected_tools if tool not in tool_names]
    unexpected_tools = tool_names if expected_tools == [] and tool_names else []
    forbidden_tools = [tool for tool in must_not_tools if tool in tool_names]
    missing_text = [text for text in case.get("must_contain", []) if text not in answer]
    forbidden_text = [text for text in case.get("must_not_contain", []) if text in answer]

    need_rag_ok = True
    if "expected_need_rag" in case:
        need_rag_ok = need_rag == bool(case["expected_need_rag"])

    expected_top_doc_ids = case.get("expected_top_doc_ids", [])
    top_doc_ok = True
    if expected_top_doc_ids:
        top_doc_ok = top_doc_id in expected_top_doc_ids

    expected_any_doc_ids = case.get("expected_any_doc_ids", [])
    any_doc_ok = True
    if expected_any_doc_ids:
        any_doc_ok = any(doc_id in doc_ids for doc_id in expected_any_doc_ids)

    relevant_doc_ids = _unique(case.get("expected_relevant_doc_ids", []) or (expected_top_doc_ids + expected_any_doc_ids))
    recall_at_k = _recall_at_k(doc_ids, relevant_doc_ids)
    mrr = _reciprocal_rank(doc_ids, relevant_doc_ids)
    irrelevant_rate = _irrelevant_rate(doc_ids, relevant_doc_ids)
    context_recall_at_k = _recall_at_k(context_doc_ids, relevant_doc_ids)
    context_irrelevant_rate = _irrelevant_rate(context_doc_ids, relevant_doc_ids)

    insufficient_ok = True
    if case.get("expect_insufficient"):
        insufficient_ok = any(marker in answer for marker in ["当前数据不足以判断", "数据不足"])

    llm_requirement_ok = True
    if mode == "llm" and scope == "defect_analysis" and not allow_fallback:
        llm_requirement_ok = llm_used

    passed = (
        not missing_tools
        and not unexpected_tools
        and not forbidden_tools
        and not missing_text
        and not forbidden_text
        and insufficient_ok
        and llm_requirement_ok
        and need_rag_ok
        and top_doc_ok
        and any_doc_ok
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
        "need_rag": need_rag,
        "rag_top_k": _rag_top_k(state, doc_ids),
        "top_doc_id": top_doc_id,
        "kb_doc_ids": doc_ids,
        "kb_context_doc_ids": context_doc_ids,
        "rag_trace": state.get("rag_trace", []),
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "irrelevant_rate": irrelevant_rate,
        "context_recall_at_k": context_recall_at_k,
        "context_irrelevant_rate": context_irrelevant_rate,
        "missing_tools": missing_tools,
        "unexpected_tools": unexpected_tools,
        "forbidden_tools": forbidden_tools,
        "missing_text": missing_text,
        "forbidden_text": forbidden_text,
        "need_rag_ok": need_rag_ok,
        "top_doc_ok": top_doc_ok,
        "any_doc_ok": any_doc_ok,
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
    parser.add_argument("--rag-top-k", type=int, default=5, help="Top-K used for RAG eval runs.")
    args = parser.parse_args()

    os.environ["RAG_TOP_K"] = str(max(1, min(args.rag_top_k, 10)))

    if args.reset_db or not DEFAULT_DB_PATH.exists():
        init_database(DEFAULT_DB_PATH, reset=True)

    cases = load_cases(Path(args.cases))
    results = [check_case(case, args.mode, args.allow_fallback) for case in cases]

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{status}] {result['id']} "
            f"scope={result['scope']} planner={result['planner_mode']} answer={result['answer_mode']} "
            f"tools={result['tool_names']} "
            f"need_rag={result.get('need_rag')} top1={result.get('top_doc_id') or '-'} "
            f"recall@{result.get('rag_top_k')}={_metric(result.get('recall_at_k'))} "
            f"mrr={_metric(result.get('mrr'))} "
            f"irrelevant_rate={_metric(result.get('irrelevant_rate'))} "
            f"context_irrelevant_rate={_metric(result.get('context_irrelevant_rate'))}"
        )
        if args.mode == "llm" and args.allow_fallback and not result["llm_used"]:
            print(f"  [WARN] llm fallback used; llm_error={result['llm_error']}")
        if not result["passed"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    recall_values = [item["recall_at_k"] for item in results if item.get("recall_at_k") is not None]
    mrr_values = [item["mrr"] for item in results if item.get("mrr") is not None]
    irrelevant_values = [item["irrelevant_rate"] for item in results if item.get("irrelevant_rate") is not None]
    context_irrelevant_values = [
        item["context_irrelevant_rate"] for item in results if item.get("context_irrelevant_rate") is not None
    ]
    rag_recall = sum(recall_values) / len(recall_values) if recall_values else None
    rag_mrr = sum(mrr_values) / len(mrr_values) if mrr_values else None
    rag_irrelevant = sum(irrelevant_values) / len(irrelevant_values) if irrelevant_values else None
    rag_context_irrelevant = (
        sum(context_irrelevant_values) / len(context_irrelevant_values) if context_irrelevant_values else None
    )

    print(f"\nEval summary: {passed}/{total} passed (mode={args.mode})")
    print(
        f"RAG summary: rag_recall@{max(1, min(args.rag_top_k, 10))}={_metric(rag_recall)} "
        f"rag_mrr={_metric(rag_mrr)} "
        f"irrelevant_rate={_metric(rag_irrelevant)}"
    )
    print(f"RAG context summary: context_irrelevant_rate={_metric(rag_context_irrelevant)}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
