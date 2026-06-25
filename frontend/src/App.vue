<template>
  <main class="page">
    <section class="panel">
      <h1>InspectPilot</h1>
      <p>方坯表面缺陷检测结果分析 Agent</p>
      <textarea v-model="question" rows="4" />
      <button :disabled="loading" @click="ask">
        {{ loading ? "分析中..." : "开始分析" }}
      </button>
      <section v-if="response" class="result">
        <div class="answer">{{ response.answer || "后端没有返回分析结果。" }}</div>

        <div class="meta-row">
          <span class="badge" :class="{ active: response.need_rag }">
            RAG：{{ response.need_rag ? "已触发" : "未触发" }}
          </span>
          <span class="badge">planner：{{ response.planner_mode || "-" }}</span>
          <span class="badge">answer：{{ response.answer_mode || "-" }}</span>
          <span class="badge">LLM：{{ response.llm_used ? "是" : "否" }}</span>
        </div>

        <section v-if="knowledgeEvidence.length" class="evidence-section">
          <h2>参考知识</h2>
          <ol class="evidence-list">
            <li v-for="item in knowledgeEvidence" :key="item.doc_id || item.rank">
              <div class="evidence-title">
                <strong>{{ item.title || item.doc_id }}</strong>
                <span>score={{ formatScore(item.score) }}</span>
              </div>
              <div class="evidence-meta">
                <span>{{ item.source || "knowledge_base.md" }}</span>
                <span>{{ item.retriever || "-" }}</span>
                <span>{{ item.embedding_model || "-" }}</span>
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
              </div>
              <div class="evidence-meta">
                <span>answer={{ trace.answer_mode || "-" }}</span>
                <span>model={{ trace.embedding_model || "-" }}</span>
                <span>docs={{ (trace.selected_doc_ids || []).join(", ") }}</span>
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

function formatScore(score) {
  if (typeof score !== "number") {
    return "-";
  }
  return score.toFixed(4);
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

.error {
  margin-top: 14px;
  color: #b42318;
}
</style>
