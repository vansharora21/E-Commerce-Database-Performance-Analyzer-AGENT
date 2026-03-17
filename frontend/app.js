/* ══════════════════════════════════════════════════════════════
   InsightAI — Frontend Application Logic
   Handles: API calls, rendering, sidebar, loading states
═══════════════════════════════════════════════════════════════ */

const API_BASE = window.location.origin;
let sidebarOpen = true;
let isLoading = false;

// Generate a stable session ID for this browser tab
const SESSION_ID = `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

// ── Init ──────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  loadSampleQuestions();
  // Mobile: sidebar starts closed
  if (window.innerWidth < 768) {
    sidebarOpen = false;
    document.getElementById("sidebar").classList.add("collapsed");
    document.getElementById("main").classList.add("full-width");
  }
});

// ── Sidebar toggle ─────────────────────────────────────────────
function toggleSidebar() {
  sidebarOpen = !sidebarOpen;
  const sidebar = document.getElementById("sidebar");
  const main = document.getElementById("main");
  sidebar.classList.toggle("collapsed", !sidebarOpen);
  main.classList.toggle("full-width", !sidebarOpen);
}

// ── Health check ───────────────────────────────────────────────
async function checkHealth() {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");
  try {
    const res = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    if (data.status === "ok") {
      dot.className = "status-dot online";
      text.textContent = "MongoDB connected";
    } else {
      dot.className = "status-dot offline";
      text.textContent = "DB degraded";
    }
  } catch {
    dot.className = "status-dot offline";
    text.textContent = "Server offline";
  }
}

// ── Load sample questions ──────────────────────────────────────
async function loadSampleQuestions() {
  const container = document.getElementById("sample-questions");
  try {
    const key = document.getElementById("api-key-input").value;
    const res = await fetch(`${API_BASE}/api/sample-questions`, {
      headers: { "X-Admin-Key": key }
    });
    const data = await res.json();
    container.innerHTML = "";
    data.questions.slice(0, 10).forEach(q => {
      const btn = document.createElement("button");
      btn.className = "sample-q-btn";
      btn.textContent = q;
      btn.onclick = () => fillQuestion(q);
      container.appendChild(btn);
    });
  } catch {
    container.innerHTML = "<p class='empty-state-small'>Could not load samples</p>";
  }
}

function fillQuestion(q) {
  const input = document.getElementById("question-input");
  input.value = q;
  autoResize(input);
  input.focus();
  if (window.innerWidth < 768) toggleSidebar();
}

function useQuestion(el) {
  fillQuestion(el.textContent);
}

// ── Input handling ─────────────────────────────────────────────
function handleKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitQuestion();
  }
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

// ── Main submit ────────────────────────────────────────────────
async function submitQuestion() {
  if (isLoading) return;

  const input = document.getElementById("question-input");
  const question = input.value.trim();
  if (!question) return;

  const apiKey = document.getElementById("api-key-input").value.trim();
  if (!apiKey) {
    alert("Please enter your Admin API Key in the top-right field.");
    return;
  }

  // Hide hero
  const hero = document.getElementById("hero");
  if (hero) hero.classList.add("hidden");

  // Clear + reset input
  input.value = "";
  autoResize(input);

  const resultsArea = document.getElementById("results-area");
  const cardId = `card-${Date.now()}`;

  // Render question bubble
  const bubble = `
    <div class="query-card" id="${cardId}">
      <div class="q-bubble">
        <div class="q-bubble-inner">${escapeHtml(question)}</div>
      </div>
      ${renderLoadingCard()}
    </div>
  `;
  resultsArea.insertAdjacentHTML("beforeend", bubble);
  scrollToBottom();

  // Animate loading stages
  isLoading = true;
  disableSend(true);
  animateLoadingStages(cardId);

  try {
    const res = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Admin-Key": apiKey,
      },
      body: JSON.stringify({ question, session_id: SESSION_ID }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const msg = err.detail || err.error || res.statusText;

      // Quota error — show with countdown
      if (res.status === 429) {
        replaceLoadingWithQuota(cardId, msg);
        isLoading = false;
        disableSend(false);
        scrollToBottom();
        return;
      }
      throw new Error(msg);
    }

    const data = await res.json();
    if (data.is_conversational) {
      replaceLoadingWithChat(cardId, data.plain_response || data.insight?.summary || "");
    } else {
      replaceLoadingWithInsight(cardId, data);
    }
    updateHistory(question, data);

  } catch (err) {
    replaceLoadingWithError(cardId, err.message);
  } finally {
    isLoading = false;
    disableSend(false);
    scrollToBottom();
  }
}

// ── Render functions ───────────────────────────────────────────

function renderLoadingCard(isChat = false) {
  if (isChat) {
    return `
      <div class="loading-card" id="loading-inner">
        <div class="chat-typing">
          <span></span><span></span><span></span>
        </div>
      </div>`;
  }
  return `
    <div class="loading-card" id="loading-inner">
      <div class="spinner"></div>
      <div class="loading-text">
        <div style="font-weight:600;margin-bottom:8px">Running AI pipeline…</div>
        <div class="loading-stages">
          <div class="loading-stage" id="stage-1">⬡ Intent detection</div>
          <div class="loading-stage" id="stage-2">⬡ Query planning</div>
          <div class="loading-stage" id="stage-3">⬡ Database execution</div>
          <div class="loading-stage" id="stage-4">⬡ Insight generation</div>
        </div>
      </div>
    </div>
  `;
}

function animateLoadingStages(cardId) {
  const delays = [200, 1200, 2400, 3800];
  const stages = ["stage-1", "stage-2", "stage-3", "stage-4"];
  stages.forEach((id, i) => {
    setTimeout(() => {
      const el = document.getElementById(id);
      if (el) {
        // Mark previous as done
        if (i > 0) {
          const prev = document.getElementById(stages[i - 1]);
          if (prev) { prev.classList.remove("active"); prev.classList.add("done"); prev.textContent = prev.textContent.replace("⬡", "✓"); }
        }
        el.classList.add("active");
        el.textContent = el.textContent.replace("⬡", "⟳");
      }
    }, delays[i]);
  });
}

function replaceLoadingWithInsight(cardId, data) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const loading = card.querySelector(".loading-card");
  if (loading) loading.outerHTML = renderInsightCard(data);
}

function replaceLoadingWithChat(cardId, text) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const loading = card.querySelector(".loading-card");
  if (loading) {
    loading.outerHTML = `
      <div class="chat-bubble-ai">
        <div class="chat-avatar">AI</div>
        <div class="chat-text">${escapeHtml(text)}</div>
      </div>`;
  }
}

function renderInsightCard(data) {
  const { insight, intent, time_period, pipeline_steps, index_suggestions, execution_time_ms, raw_results_preview } = data;

  const badgeClass = `badge-${intent}`;
  const chartIcon = { bar: "📊", line: "📈", pie: "🥧", table: "📋", number: "🔢" }[insight.chart_hint] || "💡";

  // Metrics
  const metricsHtml = insight.key_metrics?.length
    ? `<div class="metrics-grid">${insight.key_metrics.map(m => {
      const delta = m.change_pct != null
        ? `<div class="metric-delta ${m.change_pct >= 0 ? 'delta-up' : 'delta-down'}">
               ${m.change_pct >= 0 ? '▲' : '▼'} ${Math.abs(m.change_pct).toFixed(1)}%
             </div>` : "";
      const valStr = typeof m.value === "number"
        ? m.value.toLocaleString("en-IN")
        : escapeHtml(String(m.value));
      return `
          <div class="metric-card">
            <div class="metric-label">${escapeHtml(m.label || "")}</div>
            <div class="metric-value">${valStr}</div>
            <div class="metric-unit">${escapeHtml(m.unit || "")}</div>
            ${delta}
          </div>`;
    }).join("")}</div>` : "";

  // Trend
  const trendHtml = insight.trend?.direction
    ? (() => {
      const d = insight.trend;
      const icon = { up: "📈", down: "📉", flat: "➡️" }[d.direction] || "📊";
      const cls = { up: "trend-up", down: "trend-down", flat: "trend-flat" }[d.direction];
      const pct = d.change_pct != null
        ? `<div class="trend-change ${cls}">${d.change_pct >= 0 ? '+' : ''}${(+d.change_pct).toFixed(1)}%</div>`
        : "";
      return `
          <div class="trend-bar">
            <div class="trend-icon">${icon}</div>
            <div class="trend-content">
              <div class="trend-label">${escapeHtml(d.period_label || "")}</div>
              <div class="trend-narrative">${escapeHtml(d.narrative || "")}</div>
            </div>
            ${pct}
          </div>`;
    })() : "";

  // Recommendations
  const recoHtml = insight.recommendations?.length
    ? `<div class="reco-list">
         <div class="reco-title">Recommendations</div>
         ${insight.recommendations.map(r =>
      `<div class="reco-item">${escapeHtml(r)}</div>`
    ).join("")}
       </div>` : "";

  // Data quality notes
  const dqHtml = insight.data_quality_notes?.filter(Boolean).map(n =>
    `<div class="dq-note">${escapeHtml(n)}</div>`
  ).join("") || "";

  // Index hints
  const indexHtml = index_suggestions?.length
    ? `<div class="index-box">${index_suggestions.map(escapeHtml).join(", ")}</div>` : "";

  // Pipeline steps collapsible
  const stepsHtml = pipeline_steps?.length
    ? `
      <button class="pipeline-toggle" onclick="togglePipeline(this)">
        <span class="caret">▶</span>
        Pipeline trace · ${execution_time_ms.toFixed(0)}ms total
      </button>
      <div class="pipeline-steps">
        ${pipeline_steps.map(s =>
      `<div class="pipeline-step">${escapeHtml(s)}</div>`
    ).join("")}
      </div>` : "";

  return `
    <div class="insight-card">
      <div class="insight-header">
        <span class="intent-badge ${badgeClass}">${intent.replace("_", " ")}</span>
        <div class="insight-headline">${chartIcon} ${escapeHtml(insight.headline)}</div>
      </div>
      <div class="insight-body">
        <p class="insight-summary">${escapeHtml(insight.summary)}</p>
        ${dqHtml}
        ${metricsHtml}
        ${trendHtml}
        ${recoHtml}
        ${indexHtml}
      </div>
      ${stepsHtml}
    </div>`;
}

function replaceLoadingWithError(cardId, message) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const loading = card.querySelector(".loading-card");
  if (loading) {
    loading.outerHTML = `
      <div class="error-card">
        <div class="error-title">⚠ Agent Error</div>
        <div class="error-detail">${escapeHtml(message)}</div>
      </div>`;
  }
}

function replaceLoadingWithQuota(cardId, message) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const loading = card.querySelector(".loading-card");
  if (loading) {
    loading.outerHTML = `
      <div class="error-card" style="border-color:rgba(245,158,11,0.4);background:rgba(245,158,11,0.07)">
        <div class="error-title" style="color:#f59e0b">⏳ Gemini Rate Limit</div>
        <div class="error-detail">${escapeHtml(message)}</div>
        <div style="margin-top:12px;font-size:13px;color:#94a3b8">
          Retrying automatically in <span id="quota-countdown" style="color:#f59e0b;font-weight:700">60</span>s…
        </div>
      </div>`;
  }
  // Countdown + auto-enable
  let secs = 60;
  const interval = setInterval(() => {
    secs--;
    const el = document.getElementById("quota-countdown");
    if (el) el.textContent = secs;
    if (secs <= 0) {
      clearInterval(interval);
      disableSend(false);
    }
  }, 1000);
}

// ── Pipeline toggle ────────────────────────────────────────────
function togglePipeline(btn) {
  btn.classList.toggle("open");
  const steps = btn.nextElementSibling;
  steps.classList.toggle("open");
}

// ── History ────────────────────────────────────────────────────
function updateHistory(question, data) {
  const list = document.getElementById("history-list");
  const item = document.createElement("div");
  item.className = "history-item";
  item.title = question;
  item.textContent = question;
  item.onclick = () => fillQuestion(question);
  if (list.firstChild?.className === "empty-state-small") {
    list.innerHTML = "";
  }
  list.insertBefore(item, list.firstChild);
  // Keep max 10
  while (list.children.length > 10) list.removeChild(list.lastChild);
}

// ── Helpers ────────────────────────────────────────────────────
function scrollToBottom() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function disableSend(disabled) {
  const btn = document.getElementById("send-btn");
  const icon = document.getElementById("send-icon");
  btn.disabled = disabled;
  icon.textContent = disabled ? "⟳" : "➤";
  if (disabled) {
    icon.style.animation = "spin 0.8s linear infinite";
  } else {
    icon.style.animation = "";
  }
}

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Spin animation for send icon while loading
const style = document.createElement("style");
style.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(style);
