<template>
  <main class="page">
    <section class="panel">
      <h1>InspectPilot</h1>
      <p>工业视觉质检异常诊断 Agent</p>
      <textarea v-model="question" rows="4" />
      <button :disabled="loading" @click="ask">
        {{ loading ? "分析中..." : "开始分析" }}
      </button>
      <section v-if="response" class="result">
        <div class="answer">{{ displayAnswer }}</div>

        <div class="meta-row">
          <span class="badge" :class="{ active: response.need_rag }">
            RAG：{{ response.need_rag ? "已触发" : "未触发" }}
          </span>
          <span class="badge">planner：{{ response.planner_mode || "-" }}</span>
          <span class="badge">answer：{{ response.answer_mode || "-" }}</span>
          <span class="badge">LLM：{{ response.llm_used ? "是" : "否" }}</span>
        </div>

        <section v-if="diagnosis && diagnosis.root_cause" class="evidence-section diagnosis-section">
          <div class="diagnosis-header">
            <div>
              <h2>诊断数据证据</h2>
              <p class="diagnosis-source">诊断结论来自结构化工具结果；RAG 仅用于补充规则解释和复核建议。</p>
            </div>
            <span class="diagnosis-status-pill" :class="diagnosisStatusTone">
              {{ diagnosticEvidenceSufficient === "yes" ? "证据充分" : "证据不足" }}
            </span>
          </div>

          <div class="diagnosis-overview">
            <div class="diagnosis-conclusion">
              <span>结构化结论</span>
              <strong>{{ normalizeCameraText(diagnosis.conclusion || diagnosis.summary) }}</strong>
            </div>
            <div class="diagnosis-state-grid">
              <article
                v-for="item in diagnosisStatusCards"
                :key="item.label"
                class="diagnosis-state-card"
                :class="`tone-${item.tone}`"
              >
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </article>
            </div>
          </div>

          <div v-if="diagnosisMetricCards.length" class="diagnosis-metrics">
            <div v-for="item in diagnosisMetricCards" :key="item.label" class="diagnosis-metric">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>

          <div class="diagnosis-detail-grid">
            <div v-if="diagnosisEvidenceLines.length" class="diagnosis-detail-block">
              <h3>关键证据</h3>
              <ul class="diagnosis-list">
                <li v-for="(item, index) in diagnosisEvidenceLines" :key="`diag-evidence-${index}`">
                  {{ item }}
                </li>
              </ul>
            </div>
            <div v-if="diagnosisMissingData.length" class="diagnosis-detail-block">
              <h3>仍需补充</h3>
              <ul class="diagnosis-list compact">
                <li v-for="(item, index) in diagnosisMissingData" :key="`diag-missing-${index}`">
                  {{ item }}
                </li>
              </ul>
            </div>
          </div>

          <p class="safety-note">本结论不等于判废或停线指令，仍需结合原图、人工复核和现场工艺记录确认。</p>
        </section>

        <section v-if="knowledgeEvidence.length" class="evidence-section">
          <h2>RAG 参考知识</h2>
          <ol class="evidence-list">
            <li v-for="item in knowledgeEvidence" :key="item.doc_id || item.rank">
              <div class="evidence-title">
                <strong>{{ item.title || item.doc_id }}</strong>
                <span>rerank={{ formatScore(item.rerank_score ?? item.score) }}</span>
              </div>
              <div class="evidence-meta">
                <span>{{ item.source || "knowledge_base.md" }}</span>
                <span>{{ item.retriever || "-" }}</span>
                <span>{{ item.embedding_model || "-" }}</span>
                <span v-if="item.fusion_score !== undefined">fusion={{ formatScore(item.fusion_score) }}</span>
                <span v-if="item.dense_score !== undefined">dense={{ formatScore(item.dense_score) }}</span>
                <span v-if="item.bm25_score !== undefined">bm25={{ formatScore(item.bm25_score) }}</span>
                <span v-if="item.bm25_raw_score !== undefined">bm25_raw={{ formatScore(item.bm25_raw_score) }}</span>
                <span v-if="item.keyword_score !== undefined">keyword={{ formatScore(item.keyword_score) }}</span>
                <span>metadata={{ formatScore(item.metadata_score) }}</span>
                <span>{{ item.included_in_answer_context === false ? "预算外" : "进入回答" }}</span>
              </div>
              <div v-if="item.rerank_reason?.length" class="reason">
                {{ item.rerank_reason.join("；") }}
              </div>
              <p>{{ item.content }}</p>
            </li>
          </ol>
        </section>

        <section v-if="ragTrace.length" class="evidence-section">
          <h2>RAG Trace</h2>
          <ul class="trace-list">
            <li v-for="trace in ragTrace" :key="trace.trace_id">
              <div class="trace-title">
                <strong>{{ trace.trace_id }}</strong>
                <span>{{ trace.retriever || "-" }}</span>
                <span>top_k={{ trace.top_k || "-" }}</span>
                <span v-if="trace.fusion_strategy">{{ trace.fusion_strategy }}</span>
              </div>
              <div class="evidence-meta">
                <span>answer={{ trace.answer_mode || "-" }}</span>
                <span>model={{ trace.embedding_model || "-" }}</span>
                <span>sufficient={{ trace.evidence_sufficient === false ? "否" : "是" }}</span>
                <span>coverage={{ formatRatio(trace.coverage_rate) }}</span>
                <span>context={{ trace.context_evidence_sufficient === false ? "不足" : "充足" }}</span>
                <span>context_coverage={{ formatRatio(trace.context_coverage_rate) }}</span>
                <span>docs={{ (trace.selected_doc_ids || []).join(", ") }}</span>
                <span>included={{ trace.evidence_budget?.included_doc_ids?.join(", ") || "-" }}</span>
                <span>omitted={{ trace.evidence_budget?.omitted_doc_ids?.join(", ") || "-" }}</span>
              </div>
              <div v-if="trace.rewritten_query" class="trace-detail">
                rewrite={{ trace.rewritten_query }}
              </div>
              <div v-if="trace.sub_queries?.length" class="trace-detail">
                sub_queries={{ trace.sub_queries.map((item) => item.query).join(" | ") }}
              </div>
              <div v-if="trace.required_evidence_types?.length" class="trace-detail">
                required={{ trace.required_evidence_types.join(", ") }}
                covered={{ (trace.covered_evidence_types || []).join(", ") || "-" }}
                context_covered={{ (trace.covered_context_evidence_types || []).join(", ") || "-" }}
              </div>
              <div v-if="trace.missing_aspects?.length" class="trace-detail warning">
                missing={{ trace.missing_aspects.join("；") }}
              </div>
              <div v-if="trace.context_missing_aspects?.length" class="trace-detail warning">
                context_missing={{ trace.context_missing_aspects.join("；") }}
              </div>
              <div v-if="trace.second_round_queries?.length" class="trace-detail">
                second_round={{ trace.second_round_queries.map((item) => item.query).join(" | ") }}
              </div>
            </li>
          </ul>
        </section>

        <section v-if="toolCalls.length" class="evidence-section">
          <h2>工具调用</h2>
          <ul class="tool-list">
            <li v-for="(tool, index) in toolCalls" :key="`${tool.name}-${index}`">
              <strong>{{ tool.name }}</strong>
              <span>{{ tool.ok ? "ok" : "failed" }}</span>
              <span v-if="tool.summary">{{ tool.summary }}</span>
            </li>
          </ul>
        </section>
      </section>
      <p v-if="error" class="error">{{ error }}</p>
    </section>
  </main>
</template>

<script setup>
import { computed, ref } from "vue";

const question = ref("最近一小时检测出了哪些缺陷？哪类最多？");
const response = ref(null);
const error = ref("");
const loading = ref(false);
const apiBase = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const knowledgeEvidence = computed(() => response.value?.kb_evidence || []);
const toolCalls = computed(() => response.value?.tool_calls || []);
const ragTrace = computed(() => response.value?.rag_trace || []);
const diagnosis = computed(() => response.value?.diagnosis || null);
const diagnosisMetrics = computed(() => diagnosis.value?.key_metrics || {});
const displayAnswer = computed(() =>
  normalizeCameraText(response.value?.answer || "后端没有返回分析结果。"),
);
const diagnosticEvidenceSufficient = computed(() => {
  const value = diagnosis.value?.evidence_sufficient;
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (typeof value === "string") {
    return value;
  }
  return diagnosis.value && diagnosis.value.root_cause !== "insufficient_evidence" ? "yes" : "no";
});
const diagnosisStatusTone = computed(() =>
  diagnosticEvidenceSufficient.value === "yes" ? "tone-good" : "tone-warning",
);
const diagnosisStatusCards = computed(() => [
  {
    label: "根因判断",
    value: labelRootCause(diagnosis.value?.root_cause),
    tone: rootCauseTone(diagnosis.value?.root_cause),
  },
  {
    label: "误检风险",
    value: labelRisk(diagnosis.value?.false_positive_risk),
    tone: riskTone(diagnosis.value?.false_positive_risk),
  },
  {
    label: "证据状态",
    value: diagnosticEvidenceSufficient.value === "yes" ? "充分" : "不足",
    tone: diagnosticEvidenceSufficient.value === "yes" ? "good" : "warning",
  },
]);
const diagnosisEvidenceLines = computed(() =>
  (diagnosis.value?.evidence || []).map((item) => normalizeCameraText(item)).filter(Boolean),
);
const diagnosisMissingData = computed(() =>
  (diagnosis.value?.missing_data || []).map((item) => normalizeCameraText(item)).filter(Boolean),
);
const diagnosisMetricCards = computed(() => {
  const metrics = diagnosisMetrics.value || {};
  const spike = metrics.spike || {};
  const cards = [];
  const targetCount = pickNumber(spike.target_count, metrics.target_count);
  const spikeRatio = pickNumber(spike.spike_ratio);
  const topCamera = metrics.target_camera || metrics.top_camera || "-";
  const topRatio = pickNumber(metrics.top_camera_ratio_pct);
  const affectedCameras = pickNumber(metrics.affected_cameras);
  const affectedBillets = pickNumber(metrics.affected_billets);

  cards.push({ label: "时间窗口", value: normalizedTimeWindow.value });
  if (targetCount !== null) {
    const ratioText = spikeRatio !== null ? ` / ${formatCompactNumber(spikeRatio)} 倍` : "";
    cards.push({ label: "目标缺陷", value: `${targetCount} 条${ratioText}` });
  }
  if (topCamera !== "-") {
    const ratioText = topRatio !== null ? ` / ${formatPercent(topRatio)}` : "";
    cards.push({ label: "Top 相机", value: `${normalizeCameraText(topCamera)}${ratioText}` });
  }
  if (affectedCameras !== null || affectedBillets !== null) {
    cards.push({
      label: "覆盖范围",
      value: `${affectedCameras ?? "-"} 台相机 / ${affectedBillets ?? "-"} 支方坯`,
    });
  }
  if (metrics.camera_status) {
    cards.push({ label: "相机状态", value: labelHealthStatus(metrics.camera_status) });
  }
  if (metrics.image_quality_status) {
    cards.push({ label: "图像质量", value: labelHealthStatus(metrics.image_quality_status) });
  }

  return cards.filter((item) => item.value && item.value !== "-");
});
const normalizedTimeWindow = computed(() => {
  const spike = diagnosisMetrics.value?.spike || {};
  const start = spike.analysis_start || response.value?.time_window?.start_time;
  const end = spike.target_end || response.value?.time_window?.end_time;
  if (!start && !end) {
    return "-";
  }
  return `${start || "-"} ~ ${end || "-"}`;
});

function pickNumber(...values) {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function normalizeCameraText(value) {
  if (typeof value !== "string") {
    return value || "";
  }
  return value.replace(/\/camera\d+/gi, "");
}

function formatScore(score) {
  if (typeof score !== "number") {
    return "-";
  }
  return score.toFixed(4);
}

function formatRatio(value) {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toFixed(2);
}

function formatCompactNumber(value) {
  if (typeof value !== "number") {
    return "-";
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatPercent(value) {
  if (typeof value !== "number") {
    return "-";
  }
  return `${formatCompactNumber(value)}%`;
}

function labelRootCause(value) {
  const labels = {
    camera_imaging_abnormal: "相机成像异常",
    quality_wave: "真实质量波动",
    insufficient_evidence: "证据不足",
    ambiguous: "仍有不确定性",
  };
  return labels[value] || value || "-";
}

function rootCauseTone(value) {
  if (value === "camera_imaging_abnormal") {
    return "danger";
  }
  if (value === "quality_wave") {
    return "warning";
  }
  if (value === "insufficient_evidence" || value === "ambiguous") {
    return "neutral";
  }
  return "neutral";
}

function labelRisk(value) {
  const labels = {
    high: "高",
    medium: "中",
    low: "低",
    unknown: "未知",
  };
  return labels[value] || value || "-";
}

function riskTone(value) {
  const tones = {
    high: "danger",
    medium: "warning",
    low: "good",
    unknown: "neutral",
  };
  return tones[value] || "neutral";
}

function labelHealthStatus(value) {
  const labels = {
    abnormal: "异常",
    normal: "正常",
    no_data: "无数据",
  };
  return labels[value] || value || "-";
}

async function ask() {
  loading.value = true;
  response.value = null;
  error.value = "";

  try {
    const res = await fetch(`${apiBase}/api/agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question.value }),
    });

    if (!res.ok) {
      throw new Error(`后端接口返回 ${res.status}`);
    }

    const data = await res.json();
    response.value = data;
  } catch (err) {
    error.value = `请求失败：${err.message}`;
  } finally {
    loading.value = false;
  }
}
</script>

<style>
body {
  margin: 0;
  font-family: Arial, "Microsoft YaHei", sans-serif;
  background: #f4f6f8;
  color: #1f2933;
}

.page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px;
}

.panel {
  width: min(920px, 100%);
  background: #fff;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  padding: 24px;
}

h1 {
  margin: 0 0 8px;
  font-size: 28px;
}

textarea {
  width: 100%;
  box-sizing: border-box;
  margin: 16px 0;
  padding: 12px;
  border: 1px solid #bcccdc;
  border-radius: 6px;
  font-size: 16px;
}

button {
  padding: 10px 16px;
  border: 0;
  border-radius: 6px;
  background: #0b5cad;
  color: #fff;
  cursor: pointer;
}

button:disabled {
  opacity: 0.6;
  cursor: wait;
}

.result {
  margin-top: 18px;
}

.answer {
  white-space: pre-wrap;
  line-height: 1.6;
  background: #102a43;
  color: #f0f4f8;
  padding: 16px;
  border-radius: 6px;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 4px;
  background: #edf2f7;
  color: #334e68;
  font-size: 13px;
}

.badge.active {
  background: #d9f2e6;
  color: #0b6b47;
}

.evidence-section {
  margin-top: 18px;
  border-top: 1px solid #d9e2ec;
  padding-top: 16px;
}

.evidence-section h2 {
  margin: 0 0 10px;
  font-size: 18px;
}

.evidence-list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding-left: 24px;
}

.evidence-list li {
  padding: 0 0 12px;
  border-bottom: 1px solid #edf2f7;
}

.evidence-list li:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.evidence-title {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: space-between;
  color: #102a43;
}

.evidence-title span,
.evidence-meta {
  color: #627d98;
  font-size: 13px;
}

.evidence-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 4px;
}

.reason {
  margin-top: 6px;
  color: #486581;
  font-size: 13px;
}

.evidence-list p {
  margin: 8px 0 0;
  line-height: 1.6;
  color: #243b53;
}

.tool-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.trace-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.trace-list li {
  padding: 10px 12px;
  border: 1px solid #d9e2ec;
  border-radius: 6px;
  background: #f8fafc;
}

.trace-title {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  color: #102a43;
}

.trace-title span {
  color: #627d98;
  font-size: 13px;
}

.trace-detail {
  margin-top: 6px;
  color: #486581;
  font-size: 13px;
  line-height: 1.5;
}

.trace-detail.warning {
  color: #9f580a;
}

.tool-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: #334e68;
}

.tool-list span {
  color: #627d98;
}

.diagnosis-section {
  border-top-color: #bcccdc;
}

.diagnosis-header {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.diagnosis-header h2 {
  margin-bottom: 4px;
}

.diagnosis-source {
  margin: 0;
  line-height: 1.5;
  color: #486581;
  font-size: 13px;
}

.diagnosis-status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}

.diagnosis-status-pill.tone-good {
  background: #d9f2e6;
  color: #0b6b47;
}

.diagnosis-status-pill.tone-warning {
  background: #fff3cd;
  color: #8a4b08;
}

.diagnosis-overview {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(260px, 0.9fr);
  gap: 12px;
  align-items: stretch;
}

.diagnosis-conclusion {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid #bcccdc;
  border-radius: 8px;
  background: #f8fafc;
}

.diagnosis-conclusion span,
.diagnosis-state-card span,
.diagnosis-metric span {
  color: #627d98;
  font-size: 12px;
}

.diagnosis-conclusion strong {
  color: #102a43;
  font-size: 16px;
  line-height: 1.6;
}

.diagnosis-state-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.diagnosis-state-card {
  display: grid;
  gap: 8px;
  align-content: center;
  min-height: 86px;
  padding: 12px;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #fff;
}

.diagnosis-state-card strong {
  font-size: 17px;
  line-height: 1.35;
}

.diagnosis-state-card.tone-danger {
  border-color: #f1b8b5;
  background: #fff7f7;
}

.diagnosis-state-card.tone-danger strong {
  color: #b42318;
}

.diagnosis-state-card.tone-warning {
  border-color: #f5d48a;
  background: #fffaf0;
}

.diagnosis-state-card.tone-warning strong {
  color: #8a4b08;
}

.diagnosis-state-card.tone-good {
  border-color: #9ddfc5;
  background: #f3fbf7;
}

.diagnosis-state-card.tone-good strong {
  color: #0b6b47;
}

.diagnosis-state-card.tone-neutral strong {
  color: #334e68;
}

.diagnosis-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.diagnosis-metric {
  display: grid;
  gap: 4px;
  min-height: 56px;
  padding: 10px 12px;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #fbfdff;
}

.diagnosis-metric strong {
  color: #243b53;
  font-size: 14px;
  line-height: 1.35;
}

.diagnosis-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(240px, 0.8fr);
  gap: 12px;
  margin-top: 12px;
}

.diagnosis-detail-block {
  padding: 12px 14px;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: #fff;
}

.diagnosis-detail-block h3 {
  margin: 0 0 8px;
  color: #102a43;
  font-size: 15px;
}

.diagnosis-list {
  display: grid;
  gap: 7px;
  margin: 0;
  padding-left: 18px;
  color: #334e68;
  line-height: 1.55;
}

.diagnosis-list.compact {
  font-size: 14px;
}

.safety-note {
  margin: 10px 0 0;
  line-height: 1.5;
  color: #8a4b08;
  font-size: 13px;
}

.diagnosis-summary {
  margin: 10px 0;
  line-height: 1.6;
  color: #243b53;
}

.error {
  margin-top: 14px;
  color: #b42318;
}

@media (max-width: 780px) {
  .page {
    padding: 16px;
  }

  .panel {
    padding: 18px;
  }

  .diagnosis-overview,
  .diagnosis-detail-grid {
    grid-template-columns: 1fr;
  }

  .diagnosis-state-grid {
    grid-template-columns: 1fr;
  }
}
</style>
