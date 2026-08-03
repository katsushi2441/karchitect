const state = { projects: [], current: null, busy: false };
const stages = [
  ["discover", "目的と利用者"],
  ["clarify", "曖昧さの解消"],
  ["specify", "機能要件"],
  ["plan", "非機能・制約"],
  ["design", "構成・データ"],
  ["review", "整合性レビュー"],
  ["ready", "設計準備完了"],
];

const $ = (selector) => document.querySelector(selector);
// 会話1発話の上限。ドキュメントを丸ごと貼る場所ではない。
const MESSAGE_MAX = 256;
const escapeHtml = (value = "") => String(value).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
}[c]));

function apiUrl(path) {
  const gateway = window.KARCHITECT_GATEWAY || "";
  return gateway ? `${gateway}?api=${encodeURIComponent(path)}` : path;
}

async function api(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(window.KARCHITECT_CSRF ? { "X-CSRF-Token": window.KARCHITECT_CSRF } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try { message = (await response.json()).detail || message; } catch (_) {}
    const err = new Error(message);
    err.status = response.status;
    throw err;
  }
  return response.json();
}

async function checkHealth() {
  try {
    const health = await api("/health");
    const badge = $("#modelBadge");
    if (health.ollama?.ok && health.ollama.models.includes(health.default_model)) {
      badge.classList.add("online");
      badge.innerHTML = `<i></i> ${escapeHtml(health.default_model)}`;
    } else {
      badge.innerHTML = `<i></i> Gemma未接続`;
    }
  } catch (_) {
    $("#modelBadge").innerHTML = "<i></i> API未接続";
  }
}

async function loadProjects(selectFirst = true) {
  state.projects = await api("/api/projects");
  renderProjects();
  if (selectFirst && !state.current && state.projects.length) {
    await selectProject(state.projects[0].id);
  }
}

function renderProjects() {
  const list = $("#projectList");
  if (!state.projects.length) {
    list.innerHTML = `<button class="project-item" id="emptyProjectButton"><strong>最初の設計を作る</strong><span>NEW PROJECT</span></button>`;
    $("#emptyProjectButton")?.addEventListener("click", openDialog);
    return;
  }
  list.innerHTML = state.projects.map((project) => `
    <button class="project-item ${state.current?.id === project.id ? "active" : ""}" data-id="${project.id}">
      <strong>${escapeHtml(project.name)}</strong>
      <span>${escapeHtml(project.stage)} · ${project.completeness}%</span>
    </button>
  `).join("");
  list.querySelectorAll("[data-id]").forEach((button) => {
    button.addEventListener("click", () => selectProject(button.dataset.id));
  });
}

async function selectProject(id) {
  state.current = await api(`/api/projects/${id}`);
  renderCurrent();
  renderProjects();
}

function renderCurrent() {
  const project = state.current;
  if (!project) return;
  $("#projectTitle").textContent = project.name;
  $("#stageBadge").textContent = project.stage.toUpperCase();
  $("#messageInput").disabled = false;
  $("#sendButton").disabled = false;
  $("#exportButton").disabled = false;
  $("#progressCard").classList.remove("hidden");
  $("#progressValue").textContent = `${project.completeness}%`;
  $("#progressBar").style.width = `${project.completeness}%`;
  renderStages(project.stage);
  renderMessages(project.messages);
  renderRequirements(project.requirements);
  renderQuestions(project.requirements.open_questions || []);
  setExportLinks(project.id);
  const warning = $("#warning");
  if (project.llm_warning) {
    warning.textContent = `LLM警告: ${project.llm_warning}`;
    warning.classList.remove("hidden");
  } else {
    warning.classList.add("hidden");
  }
  if (project.document_markdown) {
    $("#emptyDocument").classList.add("hidden");
    $("#documentFrame").classList.remove("hidden");
    const previewUrl = apiUrl(`/api/projects/${project.id}/document.html`);
    $("#documentFrame").src = `${previewUrl}${previewUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
  } else {
    $("#documentFrame").classList.add("hidden");
    $("#emptyDocument").classList.remove("hidden");
  }
}

function renderStages(current) {
  const currentIndex = stages.findIndex(([key]) => key === current);
  $("#stageList").innerHTML = stages.map(([key, label], index) => `
    <li class="${index < currentIndex ? "done" : index === currentIndex ? "current" : ""}">${label}</li>
  `).join("");
}

function renderMessages(messages) {
  const target = $("#messages");
  if (!messages.length) return;
  target.innerHTML = messages.filter((message) => message.role !== "system").map((message) => {
    const user = message.role === "user";
    return `<div class="message ${user ? "user" : "assistant"}">
      <div class="message-avatar">${user ? "YOU" : '<img src="images/kurage_avatar_face.webp" alt="Kurage">'}</div>
      <div class="message-body">
        <div class="message-label">${user ? "YOU" : "KURAGE ARCHITECT"}</div>
        <div class="message-bubble">${escapeHtml(message.content)}</div>
      </div>
    </div>`;
  }).join("");
  target.scrollTop = target.scrollHeight;
}

function renderRequirements(req) {
  const section = (title, items, empty = "未設定") => `
    <section class="req-section"><h3>${title}</h3>${items || `<span class="tag">${empty}</span>`}</section>`;
  const tags = (items = []) => `<div class="tag-list">${items.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>`;
  const functions = (req.functional_requirements || []).map((item) => `
    <div class="requirement-row"><strong><span class="priority">${item.priority}</span>${escapeHtml(item.title)}</strong>
    <span>${escapeHtml(item.description || "説明未設定")}</span></div>`).join("");
  const nfr = (req.non_functional_requirements || []).map((item) => `
    <div class="requirement-row"><strong><span class="priority">${item.priority}</span>${escapeHtml(item.category)}</strong>
    <span>${escapeHtml(item.requirement)} ${item.target ? `— ${escapeHtml(item.target)}` : ""}</span></div>`).join("");
  $("#requirementsView").innerHTML =
    section("目的", `<div class="requirement-row">${escapeHtml(req.purpose || req.summary || "未設定")}</div>`) +
    section("対象利用者", tags(req.target_users)) +
    section("スコープ", tags(req.in_scope)) +
    section("機能要件", functions) +
    section("非機能要件", nfr) +
    section("制約", tags(req.constraints));
}

function renderQuestions(questions) {
  const open = questions.filter((item) => item.status === "open");
  $("#questionsView").innerHTML = open.length ? open.map((item) => `
    <div class="question-card ${item.importance === "blocking" ? "blocking" : ""}">
      <span>${escapeHtml(item.id)} · ${escapeHtml(item.importance)} · ${escapeHtml(item.category)}</span>
      <p>${escapeHtml(item.question)}</p>
    </div>`).join("") : `<div class="question-card"><p>現在、未回答の質問はありません。</p></div>`;
}

function setExportLinks(id) {
  // 出力は課金ゲート(1回目無料・2回目から都度100円 or 10,000 URLAI)経由でダウンロード
  $("#downloadMarkdown").dataset.path = `/api/projects/${id}/document.md`;
  $("#downloadMarkdown").dataset.fname = `${state.current.name || "design"}.md`;
  $("#downloadJson").dataset.path = `/api/projects/${id}/requirements.json`;
  $("#downloadJson").dataset.fname = "requirements.json";
  $("#downloadPdf").dataset.path = `/api/projects/${id}/document.pdf`;
  $("#downloadPdf").dataset.fname = `${state.current.name || "design"}.pdf`;
  $("#downloadMermaid").dataset.path = `/api/projects/${id}/mermaid/architecture`;
  $("#downloadMermaid").dataset.fname = "architecture.mmd";
}

function setBusy(busy) {
  state.busy = busy;
  $("#sendButton").disabled = busy || !state.current;
  $("#messageInput").disabled = busy || !state.current;
  if (busy) {
    $("#messages").insertAdjacentHTML("beforeend", `<div id="typing" class="message assistant"><div class="message-avatar"><img src="images/kurage_avatar_face.webp" alt="Kurage"></div><div class="typing"><i></i><i></i><i></i></div></div>`);
    $("#messages").scrollTop = $("#messages").scrollHeight;
  } else {
    $("#typing")?.remove();
  }
}

async function submitMessage(event) {
  event.preventDefault();
  const input = $("#messageInput");
  const content = input.value.trim();
  if (!content || !state.current || state.busy) return;
  if (content.length > MESSAGE_MAX) {
    alert(`1回の発話は${MESSAGE_MAX}文字までです（現在${content.length}文字）。\n設計書や仕様書の貼り付けではなく、会話として要点を分けて送ってください。`);
    return;
  }
  input.value = "";
  state.current.messages.push({ role: "user", content, id: Date.now(), created_at: "" });
  renderMessages(state.current.messages);
  setBusy(true);
  try {
    state.current = await api(`/api/projects/${state.current.id}/messages`, {
      method: "POST", body: JSON.stringify({ content }),
    });
    renderCurrent();
    await loadProjects(false);
  } catch (error) {
    input.value = content;
    alert(`送信に失敗しました: ${error.message}`);
  } finally {
    setBusy(false);
  }
}

function openDialog() {
  $("#projectDialog").showModal();
  setTimeout(() => $("#newProjectName").focus(), 30);
}

async function createProject(event) {
  event.preventDefault();
  const name = $("#newProjectName").value.trim();
  const initial_idea = $("#newProjectIdea").value.trim();
  if (!name) return;
  try {
    const project = await api("/api/projects", {
      method: "POST", body: JSON.stringify({ name, initial_idea }),
    });
    $("#projectDialog").close();
    $("#projectForm").reset();
    state.current = project;
    await loadProjects(false);
    renderCurrent();
  } catch (error) {
    if (error.status === 402) {
      // 2個目以降は有料(1個=500円 or 50,000 URLAI)。決済ダイアログへ。
      $("#projectDialog").close();
      openBilling();
      return;
    }
    alert(`プロジェクトを作成できませんでした: ${error.message}`);
  }
}

// ---- 課金(1個目無料・2個目以降 クレジット制。決済はKurageブログの有料記事と同方式) ----
let billingInfo = null;

async function openBilling() {
  const dlg = $("#billingDialog");
  dlg.showModal();
  $("#billingMsg").textContent = "";
  try {
    billingInfo = await api("/billing/status");
  } catch (error) {
    $("#billingMsg").textContent = "課金情報を取得できませんでした: " + error.message;
    return;
  }
  $("#billingCredits").textContent = String(billingInfo.credits);
  $("#billingReceiver").textContent = billingInfo.urlai_receiver;
  mountPaypal();
}

function billingSay(message, ok) {
  const el = $("#billingMsg");
  el.textContent = message;
  el.style.color = ok ? "var(--up)" : "var(--down)";
}

async function billingGranted(data) {
  $("#billingCredits").textContent = String(data.credits);
  billingSay(data.message + " このままプロジェクトを作成できます。", true);
  setTimeout(() => { $("#billingDialog").close(); openDialog(); }, 1200);
}

function mountPaypal() {
  const box = $("#karPaypalButtons");
  if (!billingInfo || box.dataset.mounted) return;
  const boot = () => {
    if (!window.paypal || !window.paypal.Buttons) return;
    box.dataset.mounted = "1";
    window.paypal.Buttons({
      style: { layout: "horizontal", height: 38, tagline: false },
      createOrder: (d, actions) => actions.order.create({
        purchase_units: [{ description: "Kurage Architect プロジェクト追加",
          amount: { currency_code: "JPY", value: String(billingInfo.price_jpy) } }],
      }),
      onApprove: (d, actions) => actions.order.capture().then(async (order) => {
        try {
          const res = await api("/billing/paypal", { method: "POST", body: JSON.stringify({ order_id: order.id }) });
          if (res.ok) { billingGranted(res); } else { billingSay(res.message || "確認に失敗しました", false); }
        } catch (error) { billingSay("確認に失敗しました: " + error.message, false); }
      }),
      onError: () => billingSay("PayPal決済でエラーが発生しました。時間をおいて再試行してください", false),
    }).render("#karPaypalButtons");
  };
  if (window.paypal) { boot(); return; }
  const s = document.createElement("script");
  s.src = "https://www.paypal.com/sdk/js?client-id=" + encodeURIComponent(billingInfo.paypal_client_id) + "&currency=JPY";
  s.onload = boot;
  document.head.appendChild(s);
}

// ---- 設計書出力の課金(1回目無料・2回目から都度100円 or 10,000 URLAI) ----
let pendingExport = null;

async function gatedExport(path, fname) {
  try {
    const response = await fetch(apiUrl(path), {
      headers: window.KARCHITECT_CSRF ? { "X-CSRF-Token": window.KARCHITECT_CSRF } : {},
    });
    if (response.status === 402) { pendingExport = { path, fname }; openExportBilling(); return; }
    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try { message = (await response.json()).detail || message; } catch (_) {}
      alert(`出力に失敗しました: ${message}`);
      return;
    }
    const blob = await response.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 800);
  } catch (error) {
    alert(`出力に失敗しました: ${error.message}`);
  }
}

async function openExportBilling() {
  const dlg = $("#exportBillingDialog");
  dlg.showModal();
  $("#exportBillingMsg").textContent = "";
  try {
    billingInfo = await api("/billing/status");
  } catch (error) {
    $("#exportBillingMsg").textContent = "課金情報を取得できませんでした: " + error.message;
    return;
  }
  $("#exportCredits").textContent = String(billingInfo.export_credits);
  $("#exportReceiver").textContent = billingInfo.urlai_receiver;
  mountExportPaypal();
}

function exportBillingSay(message, ok) {
  const el = $("#exportBillingMsg");
  el.textContent = message;
  el.style.color = ok ? "var(--up)" : "var(--down)";
}

async function exportGranted(data) {
  $("#exportCredits").textContent = String(data.export_credits);
  exportBillingSay(data.message + " ダウンロードを再開します…", true);
  setTimeout(() => {
    $("#exportBillingDialog").close();
    if (pendingExport) { const p = pendingExport; pendingExport = null; gatedExport(p.path, p.fname); }
  }, 1000);
}

function mountExportPaypal() {
  const box = $("#exportPaypalButtons");
  if (!billingInfo || box.dataset.mounted) return;
  const boot = () => {
    if (!window.paypal || !window.paypal.Buttons) return;
    box.dataset.mounted = "1";
    window.paypal.Buttons({
      style: { layout: "horizontal", height: 38, tagline: false },
      createOrder: (d, actions) => actions.order.create({
        purchase_units: [{ description: "Kurage Architect 設計書出力",
          amount: { currency_code: "JPY", value: String(billingInfo.export_price_jpy) } }],
      }),
      onApprove: (d, actions) => actions.order.capture().then(async (order) => {
        try {
          const res = await api("/billing/export/paypal", { method: "POST", body: JSON.stringify({ order_id: order.id }) });
          if (res.ok) { exportGranted(res); } else { exportBillingSay(res.message || "確認に失敗しました", false); }
        } catch (error) { exportBillingSay("確認に失敗しました: " + error.message, false); }
      }),
      onError: () => exportBillingSay("PayPal決済でエラーが発生しました。時間をおいて再試行してください", false),
    }).render("#exportPaypalButtons");
  };
  if (window.paypal) { boot(); return; }
  const s = document.createElement("script");
  s.src = "https://www.paypal.com/sdk/js?client-id=" + encodeURIComponent(billingInfo.paypal_client_id) + "&currency=JPY";
  s.onload = boot;
  document.head.appendChild(s);
}

async function verifyExportUrlai() {
  const wallet = $("#exportWallet").value.trim();
  if (!wallet) { exportBillingSay("送金元ウォレットアドレスを入力してください", false); return; }
  exportBillingSay("オンチェーンで確認中…（数秒かかります）", true);
  try {
    const res = await api("/billing/export/urlai", { method: "POST", body: JSON.stringify({ wallet }) });
    if (res.ok) { exportGranted(res); } else { exportBillingSay(res.message || "確認できませんでした", false); }
  } catch (error) { exportBillingSay("確認に失敗しました: " + error.message, false); }
}

async function verifyUrlai() {
  const wallet = $("#billingWallet").value.trim();
  if (!wallet) { billingSay("送金元ウォレットアドレスを入力してください", false); return; }
  billingSay("オンチェーンで確認中…（数秒かかります）", true);
  try {
    const res = await api("/billing/urlai", { method: "POST", body: JSON.stringify({ wallet }) });
    if (res.ok) { billingGranted(res); } else { billingSay(res.message || "確認できませんでした", false); }
  } catch (error) { billingSay("確認に失敗しました: " + error.message, false); }
}

document.addEventListener("DOMContentLoaded", async () => {
  $("#newProjectButton").addEventListener("click", openDialog);
  $("#cancelDialog").addEventListener("click", () => $("#projectDialog").close());
  $("#projectForm").addEventListener("submit", createProject);
  $("#billingClose").addEventListener("click", () => $("#billingDialog").close());
  $("#billingVerifyUrlai").addEventListener("click", verifyUrlai);
  $("#exportBillingClose").addEventListener("click", () => $("#exportBillingDialog").close());
  $("#exportVerifyUrlai").addEventListener("click", verifyExportUrlai);
  for (const id of ["downloadMarkdown", "downloadJson", "downloadPdf", "downloadMermaid"]) {
    $("#" + id).addEventListener("click", (event) => {
      event.preventDefault();
      const el = event.currentTarget;
      if (el.dataset.path) { gatedExport(el.dataset.path, el.dataset.fname || "export"); }
      $("#exportOptions").classList.add("hidden");
    });
  }
  $("#messageForm").addEventListener("submit", submitMessage);
  $("#messageInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("#messageForm").requestSubmit();
    }
  });
  $("#exportButton").addEventListener("click", () => $("#exportOptions").classList.toggle("hidden"));
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".export-menu")) $("#exportOptions").classList.add("hidden");
  });
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
      document.querySelectorAll(".tab-content").forEach((item) => item.classList.remove("active"));
      $(`#${tab.dataset.tab}Tab`).classList.add("active");
    });
  });
  await Promise.all([checkHealth(), loadProjects()]);
  if (!state.projects.length) openDialog();
});


// 入力中の残り文字数を出す。上限に達したことが分かるようにする。
(function initCharCount() {
  const input = document.querySelector("#messageInput");
  const counter = document.querySelector("#charCount");
  if (!input || !counter) return;
  const update = () => {
    const n = input.value.length;
    counter.textContent = `${n} / ${MESSAGE_MAX}`;
    counter.classList.toggle("over", n >= MESSAGE_MAX);
  };
  input.addEventListener("input", update);
  update();
})();
