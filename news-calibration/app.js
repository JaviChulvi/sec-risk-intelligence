"use strict";
const $ = id => document.getElementById(id);
const prefix = "sec-news-review-v2:";
let state = null;
let busy = false;

function notify(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = error ? "" : "success";
  $("notice").hidden = false;
}

function draftKey(value = state) {
  return prefix + value.id + ":" + value.reviewer;
}

function remember() {
  try {
    localStorage.setItem(draftKey(), JSON.stringify(state));
    localStorage.setItem(prefix + "selection", JSON.stringify({filename: state.filename, reviewer: state.reviewer}));
  } catch {
    $("saved").textContent = "Sin copia en el navegador. Pulsa Guardar para escribir en disco.";
  }
}

function setBusy(value) {
  busy = value;
  $("reviewer").disabled = value;
  $("samples").disabled = value || !$("samples").options.length;
  $("csv").disabled = value;
  $("annotation-fields").disabled = value || !state;
  $("export").disabled = value || !state;
  $("jump").disabled = value || !state;
  $("previous").disabled = value || !state || state.index === 0;
  $("next").disabled = value || !state || state.index === state.rows.length - 1;
  $("pending").disabled = value || !state || state.rows.every(row => row.review_status === "reviewed");
  $("reload").disabled = value;
}

async function api(path, data) {
  const response = await fetch(path, data === undefined ? undefined : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data),
  });
  if (!(response.headers.get("content-type") || "").includes("application/json")) {
    throw new Error("El servidor no responde. Inicia server.py y vuelve a cargar la página.");
  }
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 409 && state) $("reload").hidden = false;
    throw new Error(result.error || "No se pudo completar la operación.");
  }
  return result;
}

async function save() {
  if (!state?.dirty) return;
  setBusy(true);
  $("saved").textContent = "Guardando…";
  try {
    const result = await api("/api/annotations", state);
    state.revision = result.revision;
    state.dirty = false;
    remember();
    $("saved").textContent = "Guardado en disco · " + state.reviewer;
    $("notice").hidden = true;
    $("reload").hidden = true;
  } catch (error) {
    $("saved").textContent = "Cambios sin guardar en disco";
    notify(error.message, true);
    throw error;
  } finally { setBusy(false); }
}

function visibility() {
  const decision = document.querySelector('[name="relevant_risk_news"]:checked')?.value;
  $("positive").hidden = decision !== "true";
  $("negative").hidden = decision !== "false";
}

function updateProgress() {
  const done = state.rows.filter(row => row.review_status === "reviewed").length;
  $("progress-label").textContent = done + " de " + state.rows.length + " revisadas";
  $("jump").replaceChildren(...state.rows.map((row, index) =>
    new Option((index + 1) + "/" + state.rows.length + " · " + row.company + " · " + (row.review_status === "reviewed" ? "Revisada" : "Pendiente") + " · " + row.title, index)));
  $("jump").value = state.index;
  setBusy(busy);
}

function setSelect(id, value) {
  const select = $(id);
  if (value && !Array.from(select.options).some(option => option.value === value)) select.add(new Option("Valor importado: " + value, value));
  select.value = value;
}

function render() {
  const row = state.rows[state.index];
  $("reviewer").value = state.reviewer;
  $("samples").value = state.filename;
  const companyName = {AAPL: "Apple", MSFT: "Microsoft", GOOGL: "Alphabet / Google", NVDA: "NVIDIA"}[row.company] || row.company;
  $("company").textContent = companyName === row.company ? row.company : companyName + " · " + row.company;
  $("risk-company").textContent = companyName;
  $("relevance-company").textContent = companyName;
  $("date").textContent = (row.published_at_utc || "Sin fecha").slice(0, 10);
  $("content-state").textContent = {full: "Texto completo en origen", partial: "Texto parcial en origen", summary_only: "Solo resumen en origen"}[row.content_available] || "";
  $("title").textContent = row.title;
  $("reading-help").textContent = "Si el medio bloquea la vista integrada, usa Ver original. Si no puedes leerla, déjala pendiente.";
  $("source").hidden = true;
  $("source").removeAttribute("href");
  let articleUrl = "about:blank";
  try {
    const url = new URL(row.link);
    if (["https:", "http:"].includes(url.protocol)) { articleUrl = url.href; $("source").href = url.href; $("source").hidden = false; }
  } catch { /* Invalid links leave the row available for a pending decision. */ }
  const reader = ["finance.yahoo.com", "uk.finance.yahoo.com"].includes(new URL(articleUrl).hostname);
  if (reader) articleUrl = "/article?" + new URLSearchParams({name: state.filename, index: state.index});
  $("article-frame").setAttribute("sandbox", reader ? "allow-popups allow-popups-to-escape-sandbox" : "allow-scripts allow-same-origin allow-forms allow-popups");
  if (reader) $("reading-help").textContent = "Vista de lectura: texto público disponible en Yahoo. Si falta información, deja la noticia pendiente.";
  $("article-frame").hidden = $("source").hidden;
  $("article-frame").title = "Noticia: " + row.title;
  if ($("article-frame").getAttribute("src") !== articleUrl) $("article-frame").src = articleUrl;
  $("no-source").hidden = !$("source").hidden;
  document.querySelectorAll('[name="relevant_risk_news"]').forEach(input => { input.checked = input.value === row.relevant_risk_news; });
  document.querySelectorAll('[name="family"]').forEach(input => { input.checked = row.confirmed_risk_families.split("|").includes(input.value); });
  for (const id of ["company_relevance", "event_status", "noise_type"]) setSelect(id, row[id]);
  $("notes").value = row.notes;
  $("form-error").hidden = true;
  $("saved").textContent = state.dirty ? "Borrador pendiente de guardar · " + state.reviewer : (state.revision ? "Guardado en disco · " : "Sin anotaciones · ") + state.reviewer;
  visibility();
  updateProgress();
}

function draft() {
  const row = state.rows[state.index];
  row.relevant_risk_news = document.querySelector('[name="relevant_risk_news"]:checked')?.value || "";
  row.company_relevance = $("company_relevance").value;
  row.event_status = row.relevant_risk_news === "true" ? $("event_status").value : "";
  row.confirmed_risk_families = row.relevant_risk_news === "true" ? Array.from(document.querySelectorAll('[name="family"]:checked'), input => input.value).join("|") : "";
  row.noise_type = row.relevant_risk_news === "false" ? $("noise_type").value : "";
  row.reviewer = state.reviewer;
  row.notes = $("notes").value;
  row.review_status = "pending";
  state.dirty = true;
  $("form-error").hidden = true;
  $("saved").textContent = "Borrador pendiente de guardar · " + state.reviewer;
  visibility(); updateProgress(); remember();
}

function validationError(row) {
  if (!["true", "false"].includes(row.relevant_risk_news)) return "Si tienes dudas, usa Dejar pendiente.";
  if (!row.notes.trim()) return "Escribe una nota con el motivo de tu decisión.";
  if (row.relevant_risk_news === "true") {
    if (row.company_relevance !== "true") return "Confirma que el hecho afecta a la empresa; si no está claro, guarda un borrador o déjala pendiente.";
    if (!row.confirmed_risk_families) return "Selecciona al menos una familia.";
    if (!["materialized", "exposure", "emerging"].includes(row.event_status)) return "Selecciona el estado del riesgo.";
  } else {
    if (!["true", "false", "unclear"].includes(row.company_relevance)) return "Indica si el hecho afecta a la empresa.";
    if (!row.noise_type.trim()) return "Selecciona el motivo por el que no es relevante.";
  }
  return "";
}

async function loadSample(filename, reviewer, discard = false) {
  const result = await api("/api/sample?" + new URLSearchParams({name: filename, reviewer}));
  let cached = null;
  try {
    if (discard) localStorage.removeItem(draftKey(result));
    else cached = JSON.parse(localStorage.getItem(draftKey(result)));
  } catch { /* The saved server CSV remains available without browser storage. */ }
  state = {...result, index: 0, dirty: false};
  $("notice").hidden = true;
  $("reload").hidden = true;
  if (cached?.id === result.id && cached.reviewer === reviewer) {
    state.index = Math.min(Math.max(cached.index || 0, 0), result.rows.length - 1);
    if (cached.dirty) {
      state = cached;
      if (cached.revision !== result.revision) {
        notify("Hay cambios más recientes en disco. Descarga tu borrador antes de recargar lo guardado.", true);
        $("reload").hidden = false;
      }
    }
  }
  render(); remember();
}

async function changeSelection() {
  if (busy) return;
  const filename = $("samples").value, reviewer = $("reviewer").value;
  try {
    await save();
    setBusy(true);
    await loadSample(filename, reviewer);
  } catch (error) {
    if (state) { $("samples").value = state.filename; $("reviewer").value = state.reviewer; }
    notify(error.message, true);
  } finally { setBusy(false); }
}

async function move(index) {
  try {
    await save();
    state.index = index;
    render(); remember();
    $("title").focus({preventScroll: true});
    if (matchMedia("(max-width: 680px)").matches) document.querySelector(".article").scrollIntoView({block: "start"});
  } catch { $("jump").value = state.index; }
}

function serializeCSV(headers, rows) {
  const quote = value => '"' + String(value ?? "").replaceAll('"', '""') + '"';
  return "\uFEFF" + [headers, ...rows.map(row => headers.map(field => row[field]))].map(row => row.map(quote).join(",")).join("\r\n") + "\r\n";
}

$("export").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([serializeCSV(state.headers, state.rows)], {type: "text/csv;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = state.filename.replace(/\.csv$/i, "") + "_" + state.reviewer.toLowerCase() + ".csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("annotation-fields").addEventListener("input", draft);
$("review").addEventListener("submit", async event => {
  event.preventDefault();
  if (busy) return;
  const row = state.rows[state.index];
  const error = validationError(row);
  if (error) { $("form-error").textContent = error; $("form-error").hidden = false; return; }
  row.review_status = "reviewed";
  state.dirty = true; remember();
  try {
    await save();
    const next = state.rows.findIndex((item, index) => index > state.index && item.review_status !== "reviewed");
    const first = state.rows.findIndex(item => item.review_status !== "reviewed");
    if (first === -1) { updateProgress(); notify("Muestra terminada y guardada. Puedes descargar tu CSV."); }
    else await move(next === -1 ? first : next);
  } catch { /* The row and browser draft remain available to retry or download. */ }
});
$("defer").addEventListener("click", () => { draft(); move(Math.min(state.index + 1, state.rows.length - 1)); });
$("save-draft").addEventListener("click", () => { draft(); save().catch(() => {}); });
$("previous").addEventListener("click", () => move(state.index - 1));
$("next").addEventListener("click", () => move(state.index + 1));
$("jump").addEventListener("change", event => move(Number(event.target.value)));
$("pending").addEventListener("click", () => {
  const next = state.rows.findIndex((row, index) => index > state.index && row.review_status === "pending");
  move(next === -1 ? state.rows.findIndex(row => row.review_status === "pending") : next);
});
$("reviewer").addEventListener("change", changeSelection);
$("samples").addEventListener("change", changeSelection);
$("reload").addEventListener("click", async () => {
  setBusy(true);
  try { await loadSample(state.filename, state.reviewer, true); }
  catch (error) { notify(error.message, true); }
  finally { setBusy(false); }
});
$("csv").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    await save(); setBusy(true);
    const result = await api("/api/samples", {filename: file.name, csv: await file.text()});
    await refreshSamples(result.filename);
  } catch (error) { notify(error.message, true); }
  finally { setBusy(false); event.target.value = ""; }
});
window.addEventListener("beforeunload", event => {
  if (state?.dirty) { event.preventDefault(); event.returnValue = ""; }
});
async function refreshSamples(selected) {
  const result = await api("/api/samples");
  let last = {};
  try { last = JSON.parse(localStorage.getItem(prefix + "selection")) || {}; } catch { /* Default profile is Javi. */ }
  const reviewer = result.reviewers.includes($("reviewer").value) ? $("reviewer").value : result.reviewers.includes(last.reviewer) ? last.reviewer : "Javi";
  $("reviewer").replaceChildren(...result.reviewers.map(name => new Option(name, name)));
  $("reviewer").value = reviewer;
  $("samples").replaceChildren(...result.samples.map(name => new Option(name, name)));
  const filename = result.samples.includes(selected) ? selected : result.samples.includes(last.filename) ? last.filename : result.samples[0];
  if (filename) await loadSample(filename, reviewer);
  else notify("Carga un CSV de calibración o colócalo en news-calibration/samples/.");
}
setBusy(true);
refreshSamples().catch(error => notify(error.message, true)).finally(() => setBusy(false));
