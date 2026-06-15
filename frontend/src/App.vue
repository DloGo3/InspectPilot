<template>
  <main class="page">
    <section class="panel">
      <h1>InspectPilot</h1>
      <p>方坯表面缺陷检测结果分析 Agent</p>
      <textarea v-model="question" rows="4" />
      <button :disabled="loading" @click="ask">
        {{ loading ? "分析中..." : "开始分析" }}
      </button>
      <pre v-if="answer">{{ answer }}</pre>
      <p v-if="error" class="error">{{ error }}</p>
    </section>
  </main>
</template>

<script setup>
import { ref } from "vue";

const question = ref("最近一小时检测出了哪些缺陷？哪类最多？");
const answer = ref("");
const error = ref("");
const loading = ref(false);
const apiBase = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

async function ask() {
  loading.value = true;
  answer.value = "";
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
    answer.value = data.answer || "后端没有返回分析结果。";
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

pre {
  margin-top: 18px;
  white-space: pre-wrap;
  line-height: 1.6;
  background: #102a43;
  color: #f0f4f8;
  padding: 16px;
  border-radius: 6px;
}

.error {
  margin-top: 14px;
  color: #b42318;
}
</style>

