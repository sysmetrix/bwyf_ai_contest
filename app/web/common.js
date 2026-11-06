// 화면 공통: API 호출, 상단 메뉴, 기관 선택, 글자 이스케이프
// 매일 쓰는 "서비" 화면만 메인 메뉴로 두고, 가끔 손보는 설정들은 "⚙ 설정" 하나로 접어 둡니다.
const MAIN_PAGE = ["index.html", "서비"];
const CONFIG_PAGES = [
  ["docs.html", "규정·매뉴얼"],
  ["forms.html", "서식 보관함"],
  ["profile.html", "기관 프로필"],
  ["models.html", "로컬 모델"],
  ["settings.html", "설정"],
];
const PAGES = [MAIN_PAGE, ...CONFIG_PAGES];

async function api(path, options = {}) {
  const opts = { headers: { "Content-Type": "application/json" }, ...options };
  if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `요청 실패 (${res.status})`);
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(text) {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.textContent = text; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 2600);
}

function renderHeader(extraHtml = "") {
  const here = location.pathname.split("/").pop() || "index.html";
  const onMain = here === MAIN_PAGE[0];
  const onConfig = CONFIG_PAGES.some(([href]) => href === here);
  const mainLink = `<a href="${MAIN_PAGE[0]}" class="${onMain ? "on" : ""}" ${onMain ? 'aria-current="page"' : ""}>${MAIN_PAGE[1]}</a>`;
  const configLinks = CONFIG_PAGES.map(([href, name]) =>
    `<a href="${href}" class="${href === here ? "on" : ""}" ${href === here ? 'aria-current="page"' : ""}>${esc(name)}</a>`).join("");
  document.querySelector("header.top").innerHTML =
    `<div class="brand"><span class="logo" aria-hidden="true">서</span><span class="brand-text"><strong>서비</strong><small>서무 업무 비서</small></span></div>
     <nav class="tabs" aria-label="화면">${mainLink}</nav>
     <details class="settings-menu" ${onConfig ? "open" : ""}>
       <summary class="${onConfig ? "on" : ""}"><span aria-hidden="true">⚙</span> 설정</summary>
       <nav class="tabs" aria-label="설정 화면">${configLinks}<a href="index.html?intro=1">▶ 소개 영상</a></nav>
     </details>
     <div class="toolbar">${extraHtml}</div>`;
  setupSidebarToggle();
  watchForUpdate();
}

// 왼쪽 메뉴(사이드바) 숨기기/보이기 — 넓은 화면에서만. 선택은 기억됩니다.
const SIDEBAR_KEY = "seomu.sidebarHidden";
function setupSidebarToggle() {
  let hidden; try { hidden = localStorage.getItem(SIDEBAR_KEY) === "1"; } catch { hidden = false; }
  document.body.classList.toggle("sidebar-hidden", hidden);
  let btn = document.querySelector(".sidebar-toggle");
  if (!btn) {
    btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sidebar-toggle";
    document.body.appendChild(btn);
  }
  const sync = () => {
    const isHidden = document.body.classList.contains("sidebar-hidden");
    btn.innerHTML = isHidden ? "›" : "‹";
    btn.setAttribute("aria-label", isHidden ? "메뉴 보이기" : "메뉴 숨기기");
  };
  sync();
  btn.onclick = () => {
    const next = !document.body.classList.contains("sidebar-hidden");
    document.body.classList.toggle("sidebar-hidden", next);
    try { localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0"); } catch {}
    sync();
  };
}

// 새로 설치한 서비면(설치 ID가 바뀌면) 이 브라우저에 남은 '이미 봤음' 기록을 지워서
// 소개 영상과 처음 설정이 다시 뜨게 합니다. 같은 주소(localhost)를 예전에 썼던 PC에서도 처음부터 시작돼요.
const FIRST_RUN_KEYS = ["seomu.onboarded", "seomu.introSeen", "seomu.org", "seomu.user", "seomu.aiBannerDismissed"];
const firstRunReady = (async () => {
  try {
    const v = await fetch("/api/version", { cache: "no-store" }).then((r) => r.json());
    if (v.install_id && localStorage.getItem("seomu.installId") !== v.install_id) {
      FIRST_RUN_KEYS.forEach((k) => localStorage.removeItem(k));
      localStorage.setItem("seomu.installId", v.install_id);
    }
  } catch {}
})();

const ORG_KEY = "seomu.org";
function savedOrg() { try { return localStorage.getItem(ORG_KEY); } catch { return null; } }
function rememberOrg(id) { try { localStorage.setItem(ORG_KEY, id); } catch { /* 저장 불가 환경 */ } }

const USER_KEY = "seomu.user";
function savedUser() { try { return localStorage.getItem(USER_KEY); } catch { return null; } }
function rememberUser(id) { try { localStorage.setItem(USER_KEY, id); } catch { /* 저장 불가 환경 */ } }

async function fillOrgSelect(select, preferred) {
  const { orgs } = await api("/api/orgs");
  select.innerHTML = orgs.map((o) => `<option value="${esc(o.id)}">${esc(o.name)} (${esc(o.type)})</option>`).join("");
  const want = preferred || savedOrg();
  if (want && orgs.some((o) => o.id === want)) select.value = want;
  return orgs;
}

async function fillUserSelect(select, orgId, preferred) {
  if (!orgId) { select.innerHTML = '<option value="">담당자 선택 안 함</option>'; return []; }
  const { users } = await api(`/api/orgs/${orgId}/users`);
  select.innerHTML = '<option value="">담당자 선택 안 함</option>' +
    users.map((u) => `<option value="${esc(u.id)}">${esc(u.name)}${u.dept ? ` · ${esc(u.dept)}` : ""}</option>`).join("");
  const want = preferred || savedUser();
  if (want && users.some((u) => u.id === want)) select.value = want;
  return users;
}

function won(n) {
  if (n === null || n === undefined || n === "") return "";
  n = Number(n);
  return n >= 10000 && n % 10000 === 0 ? `${(n / 10000).toLocaleString()}만원` : `${n.toLocaleString()}원`;
}

// ---------- 자동 업데이트 알림 ----------
function showUpdating() {
  if (document.getElementById("updOverlay")) return;
  const o = document.createElement("div");
  o.id = "updOverlay"; o.className = "upd-overlay";
  o.innerHTML = `<div class="card upd-card"><span class="spinner" style="width:26px;height:26px"></span>
    <h3 style="margin:12px 0 6px">서비를 업데이트하는 중이에요</h3>
    <p class="muted" style="margin:0">새 버전을 내려받아 설치하고 다시 켜요. 1~2분쯤 걸리고, 끝나면 이 화면이 저절로 새로고침돼요.</p>
    <p class="muted" id="updProg" style="margin:10px 0 0;font-size:13px"></p></div>`;
  document.body.appendChild(o);
  let before = null, wentDown = false;
  const prog = (t) => { const el = document.getElementById("updProg"); if (el) el.textContent = t; };
  const tick = async () => {
    try {
      const v = await fetch("/api/version", { cache: "no-store" }).then((r) => r.json());
      if (before === null) before = v.version;
      if (v.state === "error") { prog(v.error || "업데이트에 실패했어요"); return; }
      if (v.state === "downloading") prog(`내려받는 중 ${v.progress || 0}%`);
      if (v.state === "restarting") prog("설치하고 다시 켜는 중…");
      if (v.state === "idle" && (wentDown || v.version !== before)) { location.reload(); return; }
    } catch { wentDown = true; prog("설치하고 다시 켜는 중…"); }
    setTimeout(tick, 2000);
  };
  tick();
}

async function watchForUpdate(tries = 0) {
  let v;
  try { v = await fetch("/api/version", { cache: "no-store" }).then((r) => r.json()); } catch { return; }
  if (v.state === "downloading" || v.state === "restarting") { showUpdating(); return; }
  const c = v.checked;
  if (!c) { if (tries < 3) setTimeout(() => watchForUpdate(tries + 1), 4000); return; }
  if (!c.available || !v.installed || document.getElementById("updBanner")) return;
  let dismissed; try { dismissed = sessionStorage.getItem("seomu.updDismissed") === c.latest; } catch { dismissed = false; }
  if (dismissed) return;
  const b = document.createElement("div");
  b.id = "updBanner"; b.className = "upd-banner";
  b.innerHTML = `<span>새 버전 <b>${esc(c.latest)}</b>이 나왔어요. ${esc(c.notes || "")}</span>
    <span style="display:flex;gap:6px"><button type="button" class="primary" id="updNow">지금 업데이트</button>
    <button type="button" class="ghost" id="updLater">나중에</button></span>`;
  document.body.appendChild(b);
  document.getElementById("updNow").onclick = async () => {
    try { await api("/api/update/apply", { method: "POST" }); b.remove(); showUpdating(); } catch (e) { toast(e.message); }
  };
  document.getElementById("updLater").onclick = () => {
    try { sessionStorage.setItem("seomu.updDismissed", c.latest); } catch {}
    b.remove();
  };
}
