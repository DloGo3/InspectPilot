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
from agent.tool_registry import DIAGNOSTIC_TOOL_NAMES
from data.init_db import DEFAULT_DB_PATH, init_database

DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "eval_cases.jsonl"
DEFAULT_DIAGNOSTIC_CASES_PATH = Path(__file__).resolve().parent / "diagnostic_cases.jsonl"


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


def _first_rag_trace(state: Dict[str, Any]) -> Dict[str, Any]:
    traces = state.get("rag_trace", [])
    return traces[0] if traces else {}


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
    diagnosis = state.get("diagnosis", {}) or {}
    doc_ids = _kb_doc_ids(state)
    context_doc_ids = _kb_context_doc_ids(state)
    top_doc_id = doc_ids[0] if doc_ids else None
    rag_trace = _first_rag_trace(state)

    expected_tools = _unique(case.get("expected_tools", []) + case.get("required_tools", []))
    must_not_tools = _unique(case.get("must_not_tools", []) + case.get("forbidden_tools", []))
    missing_tools = [tool for tool in expected_tools if tool not in tool_names]
    unexpected_tools = tool_names if expected_tools == [] and tool_names else []
    forbidden_tools = [tool for tool in must_not_tools if tool in tool_names]
    missing_text = [text for text in case.get("must_contain", []) if text not in answer]
    forbidden_text = [text for text in case.get("must_not_contain", []) if text in answer]

    expected_intent = case.get("expected_intent")
    intent_ok = True
    if expected_intent:
        intent_ok = state.get("intent") == expected_intent

    expected_root_cause = case.get("expected_root_cause")
    root_cause_ok = True
    if expected_root_cause:
        root_cause_ok = diagnosis.get("root_cause") == expected_root_cause

    expected_false_positive_risk = case.get("expected_false_positive_risk")
    false_positive_risk_ok = True
    if expected_false_positive_risk:
        false_positive_risk_ok = diagnosis.get("false_positive_risk") == expected_false_positive_risk

    diagnosis_text = answer + "\n" + json.dumps(diagnosis, ensure_ascii=False)
    evidence_keywords = _unique(case.get("evidence_keywords", []) + case.get("required_evidence_keywords", []))
    missing_evidence_keywords = [text for text in evidence_keywords if text not in diagnosis_text]
    unsafe_phrases = case.get("unsafe_phrases", ["应直接判废", "可以直接判废", "直接停线", "确定是工艺事故", "确定是质量事故", "无需复核"])
    unsafe_phrases = _unique(
        unsafe_phrases
        + ["应直接判废", "可以直接判废", "直接停线", "确定是工艺事故", "确定是质量事故", "无需复核"]
        + case.get("must_not_claim", [])
    )
    unsafe_claims = [text for text in unsafe_phrases if text in answer]

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
    rewrite_success = rag_trace.get("rewrite_success") if rag_trace else None
    coverage_rate = rag_trace.get("coverage_rate") if rag_trace else None
    evidence_sufficient = rag_trace.get("evidence_sufficient") if rag_trace else None
    second_round_used = bool(rag_trace.get("second_round_used")) if rag_trace else False
    second_round_success = evidence_sufficient if second_round_used else None
    retriever = rag_trace.get("retriever") if rag_trace else None

    insufficient_ok = True
    if case.get("expect_insufficient"):
        insufficient_ok = any(marker in answer for marker in ["当前数据不足以判断", "数据不足", "证据不足"])

    llm_requirement_ok = True
    if mode == "llm" and scope == "defect_analysis" and not allow_fallback:
        llm_requirement_ok = llm_used

    diagnostic_tool_used = any(tool in DIAGNOSTIC_TOOL_NAMES for tool in tool_names)
    knowledge_misdiagnosis = bool(
        case.get("case_type") in {"knowledge", "knowledge_guardrail"}
        and (state.get("intent") == "diagnosis" or diagnostic_tool_used or diagnosis)
    )

    offline_consistency_ok: Optional[bool] = None
    if mode == "llm" and (
        case.get("case_type") == "diagnosis"
        or expected_intent == "diagnosis"
        or expected_root_cause
        or expected_false_positive_risk
    ):
        offline_state = run_agent(case["question"], force_fallback=True)
        offline_diagnosis = offline_state.get("diagnosis", {}) or {}
        offline_consistency_ok = (
            diagnosis.get("root_cause") == offline_diagnosis.get("root_cause")
            and diagnosis.get("false_positive_risk") == offline_diagnosis.get("false_positive_risk")
        )

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
        and intent_ok
        and root_cause_ok
        and false_positive_risk_ok
        and not missing_evidence_keywords
        and not unsafe_claims
        and not knowledge_misdiagnosis
        and offline_consistency_ok is not False
    )
    return {
        "id": case["id"],
        "case_type": case.get("case_type"),
        "passed": passed,
        "question": case["question"],
        "tool_names": tool_names,
        "scope": scope,
        "intent": state.get("intent"),
        "planner_mode": planner_mode,
        "answer_mode": answer_mode,
        "llm_used": llm_used,
        "llm_error": state.get("llm_error"),
        "need_rag": need_rag,
        "expected_intent": expected_intent,
        "intent_ok": intent_ok,
        "diagnosis": diagnosis,
        "expected_root_cause": expected_root_cause,
        "root_cause": diagnosis.get("root_cause"),
        "root_cause_ok": root_cause_ok,
        "expected_false_positive_risk": expected_false_positive_risk,
        "false_positive_risk": diagnosis.get("false_positive_risk"),
        "false_positive_risk_ok": false_positive_risk_ok,
        "missing_evidence_keywords": missing_evidence_keywords,
        "unsafe_claims": unsafe_claims,
        "unsafe_claim_rate": 1.0 if unsafe_claims else 0.0,
        "diagnostic_tool_used": diagnostic_tool_used,
        "knowledge_misdiagnosis": knowledge_misdiagnosis,
        "offline_consistency_ok": offline_consistency_ok,
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
        "rewrite_success": rewrite_success,
        "coverage_rate": coverage_rate,
        "evidence_sufficient": evidence_sufficient,
        "second_round_used": second_round_used,
        "second_round_success": second_round_success,
        "retriever": retriever,
        "hybrid_used": retriever == "hybrid_faiss_bm25",
        "bm25_used": retriever in {"hybrid_faiss_bm25", "bm25", "bm25_fallback"},
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
    parser.add_argument(
        "--diagnostic-cases",
        default=str(DEFAULT_DIAGNOSTIC_CASES_PATH),
        help="Optional extra diagnostic case library. Pass an empty string to disable.",
    )
    parser.add_argument("--mode", choices=["offline", "llm"], default="offline", help="offline uses fallback planner; llm uses configured OpenAI-compatible API")
    parser.add_argument("--allow-fallback", action="store_true", help="Allow fallback in llm mode, but print a warning when no real LLM call was used")
    parser.add_argument("--reset-db", action="store_true", help="Recreate sample SQLite database before running")
    parser.add_argument("--rag-top-k", type=int, default=5, help="Top-K used for RAG eval runs.")
    args = parser.parse_args()

    os.environ["RAG_TOP_K"] = str(max(1, min(args.rag_top_k, 10)))

    if args.reset_db or not DEFAULT_DB_PATH.exists():
        init_database(DEFAULT_DB_PATH, reset=True)

    cases = load_cases(Path(args.cases))
    if args.diagnostic_cases:
        diagnostic_cases_path = Path(args.diagnostic_cases)
        if diagnostic_cases_path.exists():
            cases.extend(load_cases(diagnostic_cases_path))
    results = [check_case(case, args.mode, args.allow_fallback) for case in cases]

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{status}] {result['id']} "
            f"scope={result['scope']} planner={result['planner_mode']} answer={result['answer_mode']} "
            f"tools={result['tool_names']} "
            f"need_rag={result.get('need_rag')} top1={result.get('top_doc_id') or '-'} "
            f"root={result.get('root_cause') or '-'} "
            f"retriever={result.get('retriever') or '-'} "
            f"recall@{result.get('rag_top_k')}={_metric(result.get('recall_at_k'))} "
            f"mrr={_metric(result.get('mrr'))} "
            f"irrelevant_rate={_metric(result.get('irrelevant_rate'))} "
            f"context_irrelevant_rate={_metric(result.get('context_irrelevant_rate'))} "
            f"coverage={_metric(result.get('coverage_rate'))}"
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
    rewrite_values = [1.0 if item.get("rewrite_success") else 0.0 for item in results if item.get("rewrite_success") is not None]
    coverage_values = [item["coverage_rate"] for item in results if item.get("coverage_rate") is not None]
    second_round_values = [
        1.0 if item.get("second_round_success") else 0.0
        for item in results
        if item.get("second_round_success") is not None
    ]
    rag_retrievers: Dict[str, int] = {}
    for item in results:
        retriever = item.get("retriever")
        if retriever:
            rag_retrievers[str(retriever)] = rag_retrievers.get(str(retriever), 0) + 1
    bm25_values = [1.0 if item.get("bm25_used") else 0.0 for item in results if item.get("retriever")]
    hybrid_values = [1.0 if item.get("hybrid_used") else 0.0 for item in results if item.get("retriever")]
    diagnosis_cases = [
        item
        for item in results
        if item.get("diagnosis") or item.get("case_type") == "diagnosis" or item.get("expected_intent") == "diagnosis"
    ]
    knowledge_guardrail_cases = [
        item for item in results if item.get("case_type") in {"knowledge", "knowledge_guardrail"}
    ]
    diagnosis_intent_values = [1.0 if item.get("intent_ok") else 0.0 for item in diagnosis_cases]
    root_cause_values = [
        1.0 if item.get("root_cause_ok") else 0.0
        for item in diagnosis_cases
        if item.get("expected_root_cause")
    ]
    false_positive_risk_values = [
        1.0 if item.get("false_positive_risk_ok") else 0.0
        for item in diagnosis_cases
        if item.get("expected_false_positive_risk")
    ]
    tool_coverage_values = [
        1.0 if not item.get("missing_tools") else 0.0
        for item in results
        if item.get("diagnosis") or item.get("expected_intent") == "diagnosis"
    ]
    evidence_keyword_values = [
        1.0 if not item.get("missing_evidence_keywords") else 0.0
        for item in diagnosis_cases
    ]
    unsafe_values = [item.get("unsafe_claim_rate", 0.0) for item in diagnosis_cases]
    knowledge_misdiagnosis_values = [
        1.0 if item.get("knowledge_misdiagnosis") else 0.0 for item in knowledge_guardrail_cases
    ]
    llm_offline_consistency_values = [
        1.0 if item.get("offline_consistency_ok") else 0.0
        for item in diagnosis_cases
        if item.get("offline_consistency_ok") is not None
    ]
    rag_recall = sum(recall_values) / len(recall_values) if recall_values else None
    rag_mrr = sum(mrr_values) / len(mrr_values) if mrr_values else None
    rag_irrelevant = sum(irrelevant_values) / len(irrelevant_values) if irrelevant_values else None
    rag_context_irrelevant = (
        sum(context_irrelevant_values) / len(context_irrelevant_values) if context_irrelevant_values else None
    )
    rewrite_success_rate = sum(rewrite_values) / len(rewrite_values) if rewrite_values else None
    coverage_rate = sum(coverage_values) / len(coverage_values) if coverage_values else None
    second_round_success_rate = sum(second_round_values) / len(second_round_values) if second_round_values else None
    bm25_usage_rate = sum(bm25_values) / len(bm25_values) if bm25_values else None
    hybrid_usage_rate = sum(hybrid_values) / len(hybrid_values) if hybrid_values else None
    diagnosis_intent_accuracy = (
        sum(diagnosis_intent_values) / len(diagnosis_intent_values) if diagnosis_intent_values else None
    )
    root_cause_accuracy = sum(root_cause_values) / len(root_cause_values) if root_cause_values else None
    required_tool_coverage = sum(tool_coverage_values) / len(tool_coverage_values) if tool_coverage_values else None
    required_tool_chain_completion_rate = required_tool_coverage
    false_positive_risk_accuracy = (
        sum(false_positive_risk_values) / len(false_positive_risk_values) if false_positive_risk_values else None
    )
    evidence_keyword_coverage = (
        sum(evidence_keyword_values) / len(evidence_keyword_values) if evidence_keyword_values else None
    )
    unsafe_claim_rate = sum(unsafe_values) / len(unsafe_values) if unsafe_values else None
    knowledge_question_misdiagnosis_rate = (
        sum(knowledge_misdiagnosis_values) / len(knowledge_misdiagnosis_values)
        if knowledge_misdiagnosis_values
        else None
    )
    llm_offline_consistency_rate = (
        sum(llm_offline_consistency_values) / len(llm_offline_consistency_values)
        if llm_offline_consistency_values
        else None
    )

    print(f"\nEval summary: {passed}/{total} passed (mode={args.mode})")
    print(
        f"RAG summary: rag_recall@{max(1, min(args.rag_top_k, 10))}={_metric(rag_recall)} "
        f"rag_mrr={_metric(rag_mrr)} "
        f"irrelevant_rate={_metric(rag_irrelevant)}"
    )
    print(f"RAG context summary: context_irrelevant_rate={_metric(rag_context_irrelevant)}")
    print(
        f"Agentic RAG summary: rewrite_success_rate={_metric(rewrite_success_rate)} "
        f"coverage_rate={_metric(coverage_rate)} "
        f"second_round_success_rate={_metric(second_round_success_rate)}"
    )
    print(
        f"Hybrid retrieval summary: bm25_usage_rate={_metric(bm25_usage_rate)} "
        f"hybrid_usage_rate={_metric(hybrid_usage_rate)} "
        f"retrievers={rag_retrievers or '-'}"
    )
    print(
        f"Diagnostic summary: diagnosis_intent_accuracy={_metric(diagnosis_intent_accuracy)} "
        f"required_tool_coverage={_metric(required_tool_coverage)} "
        f"required_tool_chain_completion_rate={_metric(required_tool_chain_completion_rate)} "
        f"root_cause_accuracy={_metric(root_cause_accuracy)} "
        f"false_positive_risk_accuracy={_metric(false_positive_risk_accuracy)} "
        f"evidence_keyword_coverage={_metric(evidence_keyword_coverage)} "
        f"unsafe_claim_rate={_metric(unsafe_claim_rate)} "
        f"knowledge_question_misdiagnosis_rate={_metric(knowledge_question_misdiagnosis_rate)} "
        f"llm_offline_consistency_rate={_metric(llm_offline_consistency_rate)}"
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
