from typing import Any, Dict, List

from agent.intent import extract_filters, infer_intent, parse_time_range, should_use_rag
from agent.state import AgentState
from rag.retriever import retrieve_knowledge
from tools.defect_tools import (
    FACE_LABELS,
    LENGTH_REGION_LABELS,
    WIDTH_REGION_LABELS,
    generate_defect_report,
    get_defect_images,
    get_top_ng_billets,
    group_defects_by_face,
    group_defects_by_position,
    group_defects_by_type,
    query_defect_stats,
    query_defects_by_furnace,
)

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - fallback keeps the MVP runnable without LangGraph installed.
    END = None
    StateGraph = None


def parse_intent_node(state: AgentState) -> AgentState:
    question = state["question"]
    intent = infer_intent(question)
    start_time, end_time = parse_time_range(question)
    state.update(
        {
            "intent": intent,
            "start_time": start_time,
            "end_time": end_time,
            "filters": extract_filters(question),
            "tool_results": {},
            "errors": [],
            "need_rag": should_use_rag(question, intent),
        }
    )
    return state


def query_data_node(state: AgentState) -> AgentState:
    start_time = state.get("start_time")
    end_time = state.get("end_time")
    filters = state.get("filters", {})
    intent = state.get("intent", "general_stats")
    results: Dict[str, Any] = {}

    try:
        if intent in {"general_stats", "recent_defects"}:
            results["stats"] = query_defect_stats(start_time, end_time, filters)
            results["by_type"] = group_defects_by_type(start_time, end_time, filters)
            results["recent_images"] = get_defect_images(start_time, end_time, filters, limit=5)
        elif intent == "group_by_type":
            results["by_type"] = group_defects_by_type(start_time, end_time, filters)
        elif intent == "group_by_face":
            results["by_face"] = group_defects_by_face(start_time, end_time, filters)
        elif intent == "group_by_position":
            results["by_position"] = group_defects_by_position(start_time, end_time, filters)
            if filters.get("defect_type"):
                results["by_face"] = group_defects_by_face(start_time, end_time, filters)
        elif intent == "top_ng":
            results["top_ng"] = get_top_ng_billets(start_time, end_time, filters, limit=10)
            results["by_billet"] = query_defects_by_furnace(start_time, end_time, filters, "billet_id")
        elif intent == "furnace_quality":
            results["by_furnace"] = query_defects_by_furnace(start_time, end_time, filters, "furnace_no")
            results["top_ng"] = get_top_ng_billets(start_time, end_time, filters, limit=5)
        elif intent == "plan_quality":
            results["by_plan"] = query_defects_by_furnace(start_time, end_time, filters, "plan_no")
            results["top_ng"] = get_top_ng_billets(start_time, end_time, filters, limit=5)
        elif intent == "images":
            results["images"] = get_defect_images(start_time, end_time, filters, limit=20)
        elif intent == "report":
            report = generate_defect_report(start_time, end_time, filters)
            results["report"] = report
            state["report_path"] = report["report_path"]
        else:
            results["stats"] = query_defect_stats(start_time, end_time, filters)
    except Exception as exc:
        state.setdefault("errors", []).append(f"tool_call_failed: {exc}")

    state["tool_results"] = results
    return state


def analyze_node(state: AgentState) -> AgentState:
    results = state.get("tool_results", {})
    if not results and not state.get("errors"):
        state.setdefault("errors", []).append("no_tool_results")
    return state


def route_after_analyze(state: AgentState) -> str:
    return "retrieve_knowledge" if state.get("need_rag") else "generate_answer"


def retrieve_knowledge_node(state: AgentState) -> AgentState:
    state["kb_evidence"] = retrieve_knowledge(state["question"], top_k=3)
    return state


def _time_window_text(state: AgentState) -> str:
    return f"{state.get('start_time') or '不限'} 至 {state.get('end_time') or '不限'}"


def _format_items(items: List[Dict[str, Any]], key_name: str = "label", max_items: int = 5) -> str:
    if not items:
        return "- 暂无数据"
    lines = []
    for item in items[:max_items]:
        label = item.get(key_name) or item.get("key")
        count = item.get("defect_count", item.get("count", "-"))
        ratio = item.get("ratio_pct")
        suffix = f"，占比 {ratio}%" if ratio is not None else ""
        extra = ""
        if "critical_count" in item:
            extra = f"，严重缺陷 {item.get('critical_count', 0)} 条"
        if "avg_confidence" in item:
            extra += f"，平均置信度 {item.get('avg_confidence')}"
        lines.append(f"- {label}: {count} 条{suffix}{extra}")
    return "\n".join(lines)


def generate_answer_node(state: AgentState) -> AgentState:
    intent = state.get("intent", "general_stats")
    results = state.get("tool_results", {})
    errors = state.get("errors", [])
    lines = [
        f"分析口径：时间窗 { _time_window_text(state) }；过滤条件 {state.get('filters') or '无'}；默认排除已标记误检的记录。",
    ]

    if errors:
        lines.append(f"工具调用出现问题：{'; '.join(errors)}。当前结论只基于已成功返回的数据。")

    if intent in {"general_stats", "recent_defects"}:
        stats = results.get("stats", {})
        lines.append(
            f"共检出 {stats.get('total_defects', 0)} 条有效缺陷，涉及 {stats.get('affected_billets', 0)} 支方坯、"
            f"{stats.get('affected_furnaces', 0)} 个炉号、{stats.get('affected_plans', 0)} 个计划号。"
        )
        lines.append("缺陷类别 Top：")
        lines.append(_format_items(results.get("by_type", {}).get("items", []), "label"))
        images = results.get("recent_images", {}).get("items", [])
        if images:
            lines.append("最近原图证据：")
            for item in images[:3]:
                lines.append(
                    f"- {item['defect_id']} / {item['defect_type']} / {item['face_label']} / "
                    f"{item['billet_id']} / {item['timestamp']} / {item['image_path']}"
                )

    elif intent == "group_by_type":
        lines.append("按缺陷类别统计如下：")
        lines.append(_format_items(results.get("by_type", {}).get("items", []), "label"))

    elif intent == "group_by_face":
        lines.append("按方坯表面统计如下：")
        lines.append(_format_items(results.get("by_face", {}).get("items", []), "label"))

    elif intent == "group_by_position":
        pos = results.get("by_position", {})
        lines.append("长度方向分布：")
        lines.append(_format_items(pos.get("by_length_region", []), "label"))
        lines.append("宽度方向分布：")
        lines.append(_format_items(pos.get("by_width_region", []), "label"))
        heatmap = pos.get("heatmap", [])
        if heatmap:
            top = heatmap[0]
            lines.append(
                f"最集中的空间区域是 {top.get('length_label')} + {top.get('width_label')}，"
                f"{top.get('defect_count')} 条，占比 {top.get('ratio_pct')}%。"
            )
        if results.get("by_face"):
            lines.append("该缺陷在表面上的分布：")
            lines.append(_format_items(results["by_face"].get("items", []), "label"))

    elif intent == "top_ng":
        lines.append("方坯 NG 率排名如下，NG 率口径为 ng_frames / inspected_frames：")
        items = results.get("top_ng", {}).get("items", [])
        if not items:
            lines.append("- 暂无质量汇总数据")
        for item in items[:8]:
            lines.append(
                f"- {item['billet_id']}: NG率 {item['ng_rate_pct']}%，缺陷记录 {item['defect_count']} 条，"
                f"严重缺陷 {item['critical_count']} 条，炉号 {item['furnace_no']}，计划号 {item['plan_no']}"
            )

    elif intent == "furnace_quality":
        lines.append("炉号维度质量异常关注项：")
        lines.append(_format_items(results.get("by_furnace", {}).get("items", []), "key"))

    elif intent == "plan_quality":
        lines.append("计划号维度质量异常关注项：")
        lines.append(_format_items(results.get("by_plan", {}).get("items", []), "key"))

    elif intent == "images":
        lines.append("检索到的缺陷原图记录：")
        for item in results.get("images", {}).get("items", []):
            lines.append(
                f"- {item['defect_id']} / {item['defect_type']} / {item['face_label']} / "
                f"{item['length_region_label']}-{item['width_region_label']} / {item['image_path']}"
            )

    elif intent == "report":
        report = results.get("report", {})
        summary = report.get("summary", {})
        lines.append(f"已生成缺陷统计与空间分布分析报告：{report.get('report_path')}")
        if summary.get("top_type"):
            lines.append(f"报告核心发现：最多缺陷类别为 {summary['top_type']['label']}，最多表面为 {summary.get('top_face', {}).get('label', '暂无')}。")

    if state.get("kb_evidence"):
        lines.append("知识库证据：")
        for doc in state["kb_evidence"]:
            lines.append(f"- [{doc['doc_id']}] {doc['title']}: {doc['content'][:90]}")

    lines.append("证据来源：SQLite defect_records / billet_quality 统计结果；如需质量闭环，应结合人工复核和现场工艺记录。")
    state["answer"] = "\n".join(lines)
    return state


def build_graph():
    if StateGraph is None:
        return None

    graph = StateGraph(AgentState)
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("query_data", query_data_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("retrieve_knowledge", retrieve_knowledge_node)
    graph.add_node("generate_answer", generate_answer_node)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "query_data")
    graph.add_edge("query_data", "analyze")
    graph.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {"retrieve_knowledge": "retrieve_knowledge", "generate_answer": "generate_answer"},
    )
    graph.add_edge("retrieve_knowledge", "generate_answer")
    graph.add_edge("generate_answer", END)
    return graph.compile()


COMPILED_GRAPH = build_graph()


def run_agent(question: str) -> AgentState:
    initial_state: AgentState = {"question": question}
    if COMPILED_GRAPH is not None:
        return COMPILED_GRAPH.invoke(initial_state)

    state = parse_intent_node(initial_state)
    state = query_data_node(state)
    state = analyze_node(state)
    if route_after_analyze(state) == "retrieve_knowledge":
        state = retrieve_knowledge_node(state)
    state = generate_answer_node(state)
    return state

