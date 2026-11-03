"use strict";
const $ = (id) => document.getElementById(id);
const statuses = {normal:"平常運転",delayed:"遅延",suspended:"運転見合わせ",partial_suspension:"一部運休",alert:"運行案内",unknown:"不明・未取得"};
const timings = {active:"現在有効",unknown:"適用時期不明"};
const escape = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const stamp = (s) => s ? new Date(s).toLocaleString("ja-JP", {hour12:false}) : "公開なし";
const shortTime = (s) => new Date(s).toLocaleTimeString("ja-JP", {hour12:false});
const affected = (line) => !["normal","unknown"].includes(line.status);
const keyOf = (line) => `${line.provider_id}/${line.line_id}`;
let state = null, mode = "live", view = "attention", selected = null;
let pollBusy = false, lastPayload = "", switching = 0, lastAuto = Date.now();

function providerLabel(provider) {
  const operators = [...new Set(provider.lines.map(line => line.operator.name))];
  return operators.length === 1 ? operators[0] : provider.metadata.name;
}
function needsAttention(record) {
  return Boolean(record.provider.error) || record.line.status !== "normal" || record.line.alerts.length > 0;
}
function priority(record) {
  if (record.provider.error) return 4;
  return ({suspended:0,partial_suspension:0,delayed:1,alert:2,unknown:5,normal:6})[record.line.status] ?? 5;
}

async function api(path, options = {}) {
  const response = await fetch(path, {cache:"no-store", ...options});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
function notice(message) { $("notice").textContent = message; $("notice").hidden = !message; }
function records() {
  return (state?.providers || []).flatMap(p => p.lines.map(line => ({line, provider:p})));
}
function safeLink(url, title) {
  try {
    const parsed = new URL(url);
    if (["http:","https:"].includes(parsed.protocol)) return `<a href="${escape(parsed.href)}" target="_blank" rel="noopener noreferrer">${escape(title)} ↗</a>`;
  } catch { /* Invalid source URLs stay plain text. */ }
  return escape(title);
}
function core(name, tone) {
  $(name + "-shape").setAttribute("class", tone);
}
function overview() {
  const all = records(), lines = all.map(r => r.line), providers = state.providers;
  const failed = providers.filter(p => p.error).length;
  const received = providers.filter(p => !p.error && p.lines.some(l => l.fetched_at)).length;
  const normal = all.filter(r => !r.provider.error && r.line.status === "normal").length;
  const impact = lines.filter(affected).length;
  const suspended = lines.filter(l => ["suspended","partial_suspension"].includes(l.status)).length;
  const unknown = lines.filter(l => l.status === "unknown").length;
  const attention = all.filter(needsAttention).length;
  $("source-value").textContent = `${received}/${providers.length}`;
  $("service-value").textContent = `${normal}/${lines.length}`;
  $("alert-value").textContent = state.checked_at ? String(attention) : "—";
  $("source-summary").textContent = `${received} / ${providers.length} 応答`;
  $("line-summary").textContent = `${lines.length} 路線`;
  $("source-verdict").textContent = state.refreshing ? "取得中" : failed ? `${failed}取得元で失敗` : state.checked_at ? "取得失敗なし" : "取得待機";
  $("service-verdict").textContent = state.checked_at ? "クリックで平常路線" : "取得待機";
  $("alert-verdict").textContent = state.checked_at ? "クリックで要確認路線" : "取得待機";
  core("source", failed ? "danger" : !state.checked_at ? "neutral" : "");
  core("service", !state.checked_at ? "neutral" : "");
  core("alert", !state.checked_at ? "neutral" : suspended || impact ? "danger" : attention ? "warn" : "");
  $("suspended-count").textContent = String(suspended);
  $("delayed-count").textContent = String(impact - suspended);
  $("unknown-count").textContent = String(unknown);
  $("attention-count").textContent = state.checked_at ? String(attention) : "—";
  $("all-count").textContent = String(lines.length);
  $("error-count").textContent = `${failed}取得元`;
  let verdict, description, tone = "";
  if (!state.checked_at) {
    verdict = state.refreshing ? "取得中" : "未取得";
    description = state.refreshing ? "取得元からの応答を待っています" : "情報更新で取得を開始します";
  } else if (failed) {
    verdict = "取得異常"; tone = "danger";
    description = `${failed}取得元で失敗。通信エラーを確認`;
  } else if (suspended) {
    verdict = "運休あり"; tone = "danger";
    description = `${suspended}路線で運休・見合わせの案内`;
  } else if (impact) {
    verdict = "要確認"; tone = "danger";
    description = `${impact}路線で遅延・運行案内`;
  } else if (unknown) {
    verdict = "判定保留";
    description = `${unknown}路線の状態を確認できません`;
  } else if (attention) {
    verdict = "案内あり";
    description = "将来予告などの運行案内を確認";
  } else {
    verdict = "平常"; tone = "normal";
    description = "取得した範囲では影響情報なし";
  }
  $("overall-verdict").textContent = verdict;
  $("overall-verdict").className = "verdict-stamp " + tone;
  $("verdict-description").textContent = description;
  $("coverage").textContent = "路線数は取得元別に集計。同じ路線の重複を含みます。";
  $("last-checked").textContent = `最終取得 ${state.checked_at ? stamp(state.checked_at) : "未実行"}`;
  $("latency").textContent = state.elapsed_ms === null ? "取得待機" : `取得時間 ${state.elapsed_ms} ms`;
  $("refresh").disabled = state.refreshing;
  $("refresh").textContent = state.refreshing ? "取得中…" : mode === "demo" ? "演習を再読込" : "情報更新";
  $("mode-indicator").textContent = mode === "demo" ? "演習データ" : "実データ";
}
function providerOptions() {
  const current = $("provider-filter").value;
  $("provider-filter").innerHTML = '<option value="">すべての取得元</option>' + state.providers.map(p => `<option value="${escape(p.metadata.provider_id)}">${escape(providerLabel(p))}</option>`).join("");
  if (state.providers.some(p => p.metadata.provider_id === current)) $("provider-filter").value = current;
}
function renderLines() {
  if (!state) return;
  const query = $("search").value.trim().toLocaleLowerCase();
  const providerID = $("provider-filter").value, filter = $("status-filter").value;
  let count = 0;
  const groups = state.providers.map(provider => {
    if (providerID && provider.metadata.provider_id !== providerID) return "";
    const lines = provider.lines.filter(line => {
      if (view === "attention" && !needsAttention({line, provider})) return false;
      if (view === "errors" && !provider.error) return false;
      if (query && ![line.name,line.operator.name,line.line_id,line.provider_id].join(" ").toLocaleLowerCase().includes(query)) return false;
      if (filter === "affected") return affected(line);
      if (filter === "error") return Boolean(provider.error);
      return !filter || line.status === filter;
    }).sort((a,b) => priority({line:a,provider}) - priority({line:b,provider}) || a.name.localeCompare(b.name,"ja"));
    count += lines.length;
    if (!lines.length) return "";
    return {provider, lines, rank:Math.min(...lines.map(line => priority({line,provider})))};
  }).filter(Boolean).sort((a,b) => a.rank - b.rank);
  const shown = groups.flatMap(group => group.lines.map(line => ({line,provider:group.provider})));
  // Keep the inspector tied to a visible row when filters or data change.
  if (!state.checked_at) selected = null;
  else if (!shown.some(record => keyOf(record.line) === selected)) selected = shown[0] ? keyOf(shown[0].line) : null;
  document.querySelectorAll("button[data-view]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.view === view)));
  const html = groups.map(({provider,lines}) => `<section class="provider-group"><h3 class="provider-heading ${provider.error ? "has-error" : ""}"><span>${escape(providerLabel(provider))}${provider.error ? " / 取得失敗" : ""}</span><small>${lines.length}路線</small></h3>${lines.map(line => {
    const preview = provider.error ? "取得失敗。詳細で原因を確認" : line.alerts[0]?.description || (line.status === "unknown" ? "状態を確認できません" : "運行案内なし");
    const stateLabel = provider.error ? `${line.fetched_at ? "前回：" : ""}${statuses[line.status]}` : statuses[line.status];
    return `<button class="line-row" data-key="${escape(keyOf(line))}" aria-pressed="${selected === keyOf(line)}"><span><span class="line-name">${escape(line.name)}</span><span class="line-operator">${escape(line.operator.name)}</span></span><span class="line-state ${provider.error ? "error" : escape(line.status)}">${escape(stateLabel)}</span><span class="line-preview">${escape(preview)}</span><time class="line-time">${line.fetched_at ? escape(shortTime(line.fetched_at).slice(0,5)) : "未取得"}</time></button>`;
  }).join("")}</section>`).join("");
  let empty = '<p class="empty">条件に一致する路線はありません。検索や絞り込みを変更してください。</p>';
  if (!state.checked_at) {
    empty = `<p class="empty">${state.refreshing ? "運行情報を取得しています。しばらくお待ちください。" : "「情報更新」で運行情報を取得してください。"}</p>`;
  } else if (!query && !providerID && !filter && !count) {
    empty = view === "errors" ? '<p class="empty"><strong>通信エラーはありません。</strong>すべての取得元から応答しています。</p>' : '<div class="empty"><strong>確認が必要な路線はありません。</strong>取得した範囲では、すべて平常です。<button id="show-all">全路線を見る</button></div>';
  }
  $("lines").innerHTML = state.checked_at ? html || empty : empty;
  $("visible-count").textContent = state.checked_at ? `${count}路線を表示` : "取得待機";
  $("show-all")?.addEventListener("click", () => activateView("all"));
  $("service-core").setAttribute("aria-pressed", String(view === "all" && filter === "normal"));
  $("alert-core").setAttribute("aria-pressed", String(view === "attention"));
  $("source-core").setAttribute("aria-pressed", String(view === "errors"));
  renderDetail();
}
function renderDetail() {
  const match = records().find(r => keyOf(r.line) === selected);
  if (!match) {
    $("detail").innerHTML = '<p class="empty">一覧の路線を選択してください。<br>運行案内の本文と公式ページを確認できます。</p>';
    $("detail").dataset.key = "";
    return;
  }
  const {line, provider} = match;
  const sameRow = $("detail").dataset.key === selected;
  const expanded = sameRow && $("debug-detail")?.open;
  const rawExpanded = sameRow && $("raw-detail")?.open;
  const sourceExpanded = sameRow && $("source-detail")?.open;
  const comparisons = records().filter(r => r.line.line_id === line.line_id && r.line.provider_id !== line.provider_id);
  $("detail").dataset.key = selected;
  $("detail").innerHTML = `<div class="detail-kicker">${escape(line.operator.name)}</div><h3 class="detail-name">${escape(line.name)}</h3><span class="status-stamp ${escape(line.status)}">${provider.error && line.fetched_at ? "前回の状態：" : ""}${escape(statuses[line.status])}</span>
  ${provider.error ? `<div class="error-box">この取得元の情報を更新できませんでした。\n${line.fetched_at ? `${stamp(line.fetched_at)} の前回値を表示中です。` : "現在の状態は未取得です。"}\n詳しい原因は下のデバッグ情報で確認できます。</div>` : ""}
  <p class="detail-operator">取得元：${escape(providerLabel(provider))}<br>取得：${line.fetched_at ? stamp(line.fetched_at) : "未取得"}</p>
  <div class="detail-actions">${safeLink(line.source_url,"公式の運行案内を開く")}</div>
  <h4 class="detail-section">運行案内 ${line.alerts.length}件</h4>
  ${line.alerts.length ? line.alerts.map(a => `<article class="alert-item"><h4>${escape(a.title)}</h4><p>${escape(a.description)}</p><div class="tags"><span>${escape(timings[a.timing])}</span></div>${a.active_from || a.active_until ? `<p>適用期間 ${stamp(a.active_from)} 〜 ${stamp(a.active_until)}</p>` : ""}</article>`).join("") : `<p class="empty">${provider.error || line.status === "unknown" ? "運行状態を確認できません。公式案内を確認してください。" : "この取得元には運行案内がありません。"}</p>`}
  ${comparisons.length ? `<h4 class="detail-section">同じ路線の別取得元</h4>${comparisons.map(r => `<p class="detail-operator">${escape(providerLabel(r.provider))}：${escape(statuses[r.line.status])}${r.provider.error ? " / 取得失敗" : ""}<br>${r.line.fetched_at ? stamp(r.line.fetched_at) : "未取得"}</p>`).join("")}` : ""}
  <details id="debug-detail" class="debug-details" ${expanded ? "open" : ""}><summary>デバッグ情報（ID・取得日時・JSON）</summary>
  ${provider.error ? `<pre class="error">${escape(provider.error)}</pre>` : ""}
  <dl class="detail-meta"><dt>共通ID</dt><dd>${escape(line.line_id)}</dd><dt>取得元ID</dt><dd>${escape(line.provider_id)}</dd><dt>取得元の表記</dt><dd>${escape(line.source_status ?? "未取得")}</dd><dt>取得日時</dt><dd>${line.fetched_at ? stamp(line.fetched_at) : "未取得"}</dd><dt>情報更新日時</dt><dd>${stamp(line.updated_at)}</dd><dt>対象範囲</dt><dd>${line.scope === "group" ? "路線群・系統全体" : "路線"}</dd></dl>
  <div class="detail-actions"><button id="copy-line">路線JSONをコピー</button></div>
  <details id="raw-detail" ${rawExpanded ? "open" : ""}><summary>解析後の生JSON</summary><pre>${escape(JSON.stringify(line,null,2))}</pre></details>
  <details id="source-detail" ${sourceExpanded ? "open" : ""}><summary>取得元・エンドポイント情報</summary><p class="detail-operator">${escape(provider.metadata.usage_note)}</p><pre>${escape(JSON.stringify(provider.metadata,null,2))}</pre></details></details>`;
  $("copy-line").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(line,null,2)); $("copy-line").textContent = "コピー済み"; }
    catch { notice("コピーできませんでした。「解析後の生JSONを表示」から選択してコピーできます。"); }
  });
}
function renderLog() {
  $("events").innerHTML = state.log.length ? state.log.map(e => `<div class="log-line ${e.level === "error" ? "error" : ""}"><time>${shortTime(e.time)}</time><span>${escape(e.message)}</span></div>`).join("") : '<p class="empty">まだ取得記録がありません。「情報更新」で取得を開始します。</p>';
  $("log-status").textContent = state.log.length ? `直近${state.log.length}件` : "取得待機";
}
function render() {
  const oldFocus = document.activeElement?.dataset?.key;
  overview(); providerOptions(); renderLines(); renderLog();
  if (oldFocus) Array.from($("lines").querySelectorAll("button")).find(b => b.dataset.key === oldFocus)?.focus({preventScroll:true});
}
async function poll() {
  if (pollBusy || mode !== "live") return;
  const version = switching;
  pollBusy = true;
  try {
    const data = await api("/api/state");
    if (version !== switching || mode !== "live") return;
    const serialized = JSON.stringify(data);
    if (serialized !== lastPayload) { state = data; lastPayload = serialized; render(); }
    notice("");
  } catch (error) { if (version === switching) notice(`ローカルサーバーに接続できません (${error.message})。ターミナルで python -m examples.visualizer を起動してください。`); }
  finally { pollBusy = false; }
}
async function refresh() {
  if (mode === "demo") { await setMode("demo"); return; }
  try {
    const response = await fetch("/api/refresh", {method:"POST"});
    if (response.status === 429) { notice("取得中、または前回の取得開始から10秒以内です。少し待ってから更新してください。"); return; }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    lastAuto = Date.now();
    await poll();
  } catch (error) { notice(`更新を開始できません (${error.message})。ローカルサーバーの起動状況を確認してください。`); }
}
async function setMode(next) {
  const version = ++switching;
  mode = next; lastPayload = "";
  $("live").setAttribute("aria-pressed", String(mode === "live"));
  $("demo").setAttribute("aria-pressed", String(mode === "demo"));
  $("auto").disabled = mode === "demo";
  $("mode-description").textContent = mode === "demo" ? "架空の障害を表示する演習です" : "公開されている運行情報";
  try {
    const data = await api(mode === "demo" ? "/api/demo" : "/api/state");
    if (version !== switching) return;
    state = data; lastPayload = JSON.stringify(data); render();
    notice(mode === "demo" ? "演習中：表示している障害はすべて架空です。実際の運行状況を示していません。" : "");
    if (mode === "live" && !state.checked_at && !state.refreshing) await refresh();
  } catch (error) { notice(`データを読み込めません (${error.message})。サーバーを確認して、実データまたは演習を選び直してください。`); }
}
$("live").addEventListener("click", () => setMode("live"));
$("demo").addEventListener("click", () => setMode("demo"));
$("refresh").addEventListener("click", refresh);
function activateView(next, status = "", clear = false) {
  view = next;
  $("status-filter").value = status;
  if (clear) { $("search").value = ""; $("provider-filter").value = ""; }
  renderLines();
}
document.querySelectorAll("button[data-view]").forEach(button => button.addEventListener("click", () => activateView(button.dataset.view)));
$("service-core").addEventListener("click", () => activateView("all", "normal", true));
$("alert-core").addEventListener("click", () => activateView("attention", "", true));
$("source-core").addEventListener("click", () => activateView("errors", "", true));
$("search").addEventListener("input", () => {
  if ($("search").value.trim()) view = "all";
  renderLines();
});
$("provider-filter").addEventListener("change", renderLines);
$("status-filter").addEventListener("change", () => {
  if ($("status-filter").value) view = "all";
  renderLines();
});
$("auto").addEventListener("change", () => { lastAuto = Date.now(); });
$("lines").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-key]");
  if (!button) return;
  selected = button.dataset.key;
  $("lines").querySelectorAll("button[data-key]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.key === selected)));
  renderDetail();
  if (window.matchMedia("(max-width: 760px)").matches) {
    $("inspector-title").scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block:"start"});
  }
});
$("export").addEventListener("click", () => {
  if (!state) return;
  const blob = new Blob([JSON.stringify(state,null,2)], {type:"application/json"});
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = `rail-monitor-${mode}-${new Date().toISOString().replace(/[:.]/g,"-")}.json`;
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
});
function tick() { const now = new Date(); $("clock").textContent = shortTime(now); $("date").textContent = now.toLocaleDateString("ja-JP", {year:"numeric",month:"2-digit",day:"2-digit",weekday:"short"}); }
tick(); setInterval(tick,1000);
setInterval(() => {
  if (mode !== "live") return;
  if ($("auto").checked && Date.now()-lastAuto >= 60000 && !state?.refreshing) { lastAuto = Date.now(); refresh(); }
  else poll();
},1500);
api("/api/config").then(config => setMode(config.initial_mode)).catch(error => notice(`初期接続に失敗しました (${error.message})。サーバーを確認して、実データまたは演習を選び直してください。`));
