"use strict";
// Plan Labeler — frontend sem framework (SPEC §6). Todo texto vindo da API entra por textContent.

const CATEGORIES = [
  { value: "energy", label: "Energia", key: "E" },
  { value: "not_energy", label: "Não energia", key: "N" },
];
const SUBCATEGORIES = [
  { value: "hybrid", label: "hybrid", category: "energy" },
  { value: "wind", label: "wind", category: "energy" },
  { value: "solar", label: "solar", category: "energy" },
  { value: "bess", label: "bess", category: "energy" },
  { value: "hydro", label: "hydro", category: "energy" },
  { value: "substation", label: "substation", category: "energy" },
  { value: "energy_support", label: "energy support", category: "energy" },
  { value: "leu", label: "leu", category: "energy" },
  { value: "data_centre", label: "data centre", category: "energy" },
  { value: "not_energy", label: "não energia", category: "not_energy" },
  { value: "low_energy", label: "baixa energia", category: "not_energy" },
];
const CATEGORY_OF = Object.fromEntries(SUBCATEGORIES.map((s) => [s.value, s.category]));
const CATEGORY_LABEL = { energy: "energia", not_energy: "não energia" };
const SUB_LABEL = Object.fromEntries(SUBCATEGORIES.map((s) => [s.value, s.label]));
const REASON_LABEL = {
  rpm: "limite de requisições por minuto",
  tpm: "limite de tokens por minuto",
  rpd: "limite diário",
  rate_limited: "o Google pediu para esperar",
  disabled: "sem chave do Gemini",
};

const $ = (id) => document.getElementById(id);
const fmt = (n) => Number(n).toLocaleString("pt-BR");

const state = {
  token: null,
  app: null,
  category: null,
  subcategory: null,
  touched: false, // usuário já escolheu algo nesta aplicação
  prefill: null, // {category, subcategory|null} vindo dos dois modelos
  decisions: {},
  quotas: {},
  advisor: null,
  translated: null,
  showingTranslation: false,
  busy: false,
  ended: false,
  advisorTimer: null,
};

// ---------------------------------------------------------------- utilidades

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child == null) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

async function api(method, path, body) {
  const resp = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = resp.status === 204 ? null : await resp.json();
  } catch (_) {
    data = null;
  }
  return { status: resp.status, data };
}

function show(section) {
  for (const id of ["loading", "error", "ended", "work"]) $(id).hidden = id !== section;
}

function shortModel(name) {
  if (!name) return "";
  return name.split("/").pop().replace(/-\d{8}$/, "");
}

function localTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

// ---------------------------------------------------------------- cabeçalho

function renderStats(stats) {
  if (!stats) return;
  $("stats").textContent = `${fmt(stats.total)} rotulados · ${fmt(stats.energy)} energia`;
}

function quotaSpan(text, used, limit) {
  const span = el("span", { text });
  if (limit && used / limit >= 0.8) span.className = "high";
  return span;
}

function renderQuotas() {
  const box = $("quotas");
  box.replaceChildren();
  const parts = [];
  for (const slot of [1, 2]) {
    const q = state.quotas[slot];
    if (!q) continue;
    const limit = q.limit_day ? `/${fmt(q.limit_day)}` : "";
    parts.push(quotaSpan(`${shortModel(q.model)} hoje ${fmt(q.used_today)}${limit}`,
      q.used_today, q.limit_day));
  }
  const a = state.advisor;
  if (a && a.model) {
    const limit = a.rpd_limit ? `/${fmt(a.rpd_limit)}` : "";
    parts.push(quotaSpan(`Dúvida ${fmt(a.rpd_used)}${limit}`, a.rpd_used, a.rpd_limit));
  }
  parts.forEach((p, i) => {
    if (i) box.append(" · ");
    box.append(p);
  });
}

// ---------------------------------------------------------------- painéis dos modelos

function renderPanel(slot) {
  const panel = $(`panel-${slot}`);
  const res = state.decisions[slot];
  const model = (res && res.model) || (state.quotas[slot] && state.quotas[slot].model) || "";
  panel.replaceChildren(el("h2", { text: `Modelo ${slot} · ${model}` }));
  if (!res) {
    panel.append(el("div", { class: "state", text: "analisando…" }));
    return;
  }
  const d = res.decision;
  if (!d) {
    const text = res.reason === "quota_exhausted" ? "limite diário atingido" : "sem sugestão";
    panel.append(el("div", { class: "state", text }));
    return;
  }
  const cats = el("div", { class: "cats" });
  for (const c of CATEGORIES) {
    const pct = d.category_distribution[c.value];
    const span = el("span", { text: `${CATEGORY_LABEL[c.value]} ${pct} %` });
    if (c.value === d.category) span.className = "max";
    cats.append(span);
  }
  if (!d.consistent) cats.append(el("span", { class: "contradiction", text: "⚠ contradição" }));
  const subs = el("div", { class: "subs" });
  for (const s of SUBCATEGORIES) {
    const span = el("span", { text: `${s.label} ${d.subcategory_distribution[s.value]}` });
    if (s.value === d.subcategory) span.className = "max";
    subs.append(span);
  }
  panel.dataset.category = d.category;
  panel.dataset.subcategory = d.subcategory;
  panel.append(cats, subs);
}

// ---------------------------------------------------------------- escolha do usuário

function renderChoice() {
  const cats = $("categories");
  cats.replaceChildren();
  for (const c of CATEGORIES) {
    const input = el("input", { type: "radio", name: "category", value: c.value });
    input.checked = state.category === c.value;
    input.addEventListener("change", () => chooseCategory(c.value, true));
    cats.append(el("label", {}, input, ` ${c.label} `, el("kbd", { text: c.key })));
  }
  const subs = $("subcategories");
  subs.replaceChildren();
  if (!state.category) {
    subs.append(el("span", { class: "hint", text: "escolha a categoria primeiro" }));
  } else {
    SUBCATEGORIES.filter((s) => s.category === state.category).forEach((s, i) => {
      const input = el("input", { type: "radio", name: "subcategory", value: s.value });
      input.checked = state.subcategory === s.value;
      input.addEventListener("change", () => chooseSubcategory(s.value, true));
      subs.append(el("label", {}, input, ` ${s.label} `, el("kbd", { text: String(i + 1) })));
    });
  }
  renderBadge();
  $("confirm").disabled = state.busy || !(state.category && state.subcategory);
}

function renderBadge() {
  const badge = $("badge");
  if (!state.prefill) badge.textContent = "";
  else if (state.prefill.changed) badge.textContent = "alterado por você";
  else if (state.prefill.subcategory) badge.textContent = "sugestão dos dois modelos";
  else badge.textContent = "categoria sugerida pelos dois modelos";
}

function markChanged() {
  if (!state.prefill) return;
  const p = state.prefill;
  if (state.category !== p.category || (p.subcategory && state.subcategory !== p.subcategory)) {
    p.changed = true;
  }
}

function chooseCategory(value, byUser) {
  if (state.category !== value) state.subcategory = null;
  state.category = value;
  if (byUser) {
    state.touched = true;
    markChanged();
  }
  renderChoice();
}

function chooseSubcategory(value, byUser) {
  if (CATEGORY_OF[value] !== state.category) return;
  state.subcategory = value;
  if (byUser) {
    state.touched = true;
    markChanged();
  }
  renderChoice();
}

function applyPrefill() {
  // Só com os dois modelos respondendo, e nunca por cima de uma escolha do usuário.
  const d1 = state.decisions[1] && state.decisions[1].decision;
  const d2 = state.decisions[2] && state.decisions[2].decision;
  if (state.touched || !d1 || !d2 || d1.category !== d2.category) return;
  const sameSub = d1.subcategory === d2.subcategory && CATEGORY_OF[d1.subcategory] === d1.category;
  state.prefill = { category: d1.category, subcategory: sameSub ? d1.subcategory : null };
  chooseCategory(d1.category, false);
  if (sameSub) chooseSubcategory(d1.subcategory, false);
}

// ---------------------------------------------------------------- Dúvida

function renderAdvisor() {
  const btn = $("doubt");
  const a = state.advisor;
  clearTimeout(state.advisorTimer);
  if (!a || !a.available) {
    btn.disabled = true;
    const why = a ? REASON_LABEL[a.reason] || "indisponível" : "indisponível";
    btn.title = a && a.retry_at ? `${why}; volta às ${localTime(a.retry_at)}` : why;
    if (a && a.reason !== "disabled") {
      const wait = a.retry_at ? Math.max(500, new Date(a.retry_at) - Date.now()) : 10000;
      state.advisorTimer = setTimeout(pollAdvisor, Math.min(wait, 10000));
    }
  } else {
    btn.disabled = state.busy;
    btn.title = "Atalho: D";
  }
  renderQuotas();
}

async function pollAdvisor() {
  const { status, data } = await api("GET", "/api/advisor");
  if (status === 200) {
    state.advisor = data;
    renderAdvisor();
  }
}

async function doubt() {
  if ($("doubt").disabled || !state.token) return;
  const token = state.token;
  $("doubt").disabled = true;
  const box = $("opinion");
  box.hidden = false;
  box.textContent = "consultando…";
  const { status, data } = await api("POST", "/api/doubt", { token });
  if (token !== state.token) return;
  if (data && data.advisor) state.advisor = data.advisor;
  if (status === 200) {
    const o = data.opinion;
    box.replaceChildren(
      el("strong", { text: `Opinião do ${o.model}: ` }),
      `${CATEGORY_LABEL[o.category]} / ${SUB_LABEL[o.subcategory]} — `,
      o.text,
    );
  } else if (status === 429) {
    box.textContent = "Dúvida indisponível agora (limite atingido).";
  } else {
    box.textContent = "o conselheiro não respondeu";
  }
  renderAdvisor();
}

// ---------------------------------------------------------------- ciclo da aplicação

function resetForApplication(body) {
  state.token = body.token;
  state.app = body.application;
  state.category = null;
  state.subcategory = null;
  state.touched = false;
  state.prefill = null;
  state.decisions = {};
  state.translated = null;
  state.showingTranslation = false;
  for (const m of body.models) state.quotas[m.slot] = m.quota || { model: m.model };
  state.advisor = body.advisor;
}

function renderApplication() {
  const a = state.app;
  const parts = [a.source_label, a.planning_authority, a.application_number].filter(Boolean);
  $("app-meta").textContent = parts.join(" · ");
  const link = $("app-link");
  link.hidden = !a.application_url;
  if (a.application_url) link.href = a.application_url;
  else link.removeAttribute("href");
  $("description").textContent = a.description;
  $("translate").textContent = "Traduzir";
  $("translate-msg").textContent = "";
  $("action-msg").textContent = "";
  $("opinion").hidden = true;
  $("opinion").textContent = "";
  renderPanel(1);
  renderPanel(2);
  renderChoice();
  renderAdvisor();
}

async function decide(slot, token) {
  const { status, data } = await api("POST", "/api/decide", { token, slot });
  if (token !== state.token) return; // resposta atrasada de outra aplicação
  state.decisions[slot] =
    status === 200 ? data : { slot, model: null, decision: null, reason: "error" };
  if (status === 200 && data.quota) state.quotas[slot] = data.quota;
  renderPanel(slot);
  renderQuotas();
}

async function loadNext() {
  state.busy = true;
  show("loading");
  const { status, data } = await api("GET", "/api/next");
  state.busy = false;
  if (status !== 200) {
    $("error-text").textContent = (data && data.detail) || "Não foi possível buscar uma aplicação.";
    show("error");
    return;
  }
  resetForApplication(data);
  renderStats(data.stats);
  show("work");
  renderApplication();
  const token = state.token;
  await Promise.all([decide(1, token), decide(2, token)]);
  if (token === state.token) applyPrefill();
}

async function confirmLabel() {
  if ($("confirm").disabled || state.busy) return;
  state.busy = true;
  renderChoice();
  const { status, data } = await api("POST", "/api/labels", {
    token: state.token,
    category: state.category,
    subcategory: state.subcategory,
  });
  state.busy = false;
  if (status === 201) {
    renderStats(data.stats);
    await loadNext();
  } else if (status === 409 || status === 404) {
    $("action-msg").textContent = "Esta aplicação já foi rotulada ou expirou; buscando outra…";
    await loadNext();
  } else {
    $("action-msg").textContent = "Não foi possível gravar. Confira a escolha.";
    renderChoice();
  }
}

async function skipCurrent() {
  if (state.token) await api("POST", "/api/skip", { token: state.token });
  state.token = null;
}

async function endSession() {
  await skipCurrent();
  state.ended = true;
  clearTimeout(state.advisorTimer);
  const { data } = await api("GET", "/api/stats");
  const total = data ? data.total : 0;
  $("ended-text").textContent = `Sessão encerrada. ${fmt(total)} registros rotulados.`;
  show("ended");
}

function openCancel() {
  if (!state.token || state.busy) return;
  $("cancel-dialog").showModal();
}

async function translate() {
  const btn = $("translate");
  const msg = $("translate-msg");
  if (state.showingTranslation) {
    $("description").textContent = state.app.description;
    btn.textContent = "Traduzir";
    state.showingTranslation = false;
    return;
  }
  if (!state.translated) {
    const token = state.token;
    msg.className = "inline-msg";
    msg.textContent = "traduzindo…";
    const { status, data } = await api("POST", "/api/translate", { text: state.app.description });
    if (token !== state.token) return;
    if (status !== 200) {
      msg.className = "inline-msg error";
      msg.textContent = "tradução indisponível";
      return;
    }
    state.translated = data.translation;
  }
  msg.textContent = "";
  $("description").textContent = state.translated;
  btn.textContent = "Ver original";
  state.showingTranslation = true;
}

// ---------------------------------------------------------------- eventos

$("retry").addEventListener("click", loadNext);
$("restart").addEventListener("click", () => location.reload());
$("confirm").addEventListener("click", confirmLabel);
$("cancel").addEventListener("click", openCancel);
$("doubt").addEventListener("click", doubt);
$("translate").addEventListener("click", translate);
$("cancel-dialog").addEventListener("close", async () => {
  const choice = $("cancel-dialog").returnValue;
  $("cancel-dialog").returnValue = "";
  if (choice === "end") await endSession();
  else if (choice === "next") {
    await skipCurrent();
    await loadNext();
  }
});

document.addEventListener("keydown", (ev) => {
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if ($("cancel-dialog").open || $("work").hidden) return;
  const key = ev.key;
  let handled = true;
  if (key === "e" || key === "E") chooseCategory("energy", true);
  else if (key === "n" || key === "N") chooseCategory("not_energy", true);
  else if (/^[1-9]$/.test(key)) {
    const options = SUBCATEGORIES.filter((s) => s.category === state.category);
    const option = options[Number(key) - 1];
    if (option) chooseSubcategory(option.value, true);
  } else if (key === "d" || key === "D") doubt();
  else if (key === "t" || key === "T") translate();
  else if (key === "Enter") confirmLabel();
  else if (key === "Escape") openCancel();
  else handled = false;
  if (handled) ev.preventDefault();
});

loadNext();
