// 서비 홈 — 캐릭터 하나, 검색창 하나. 모든 기능이 이 화면 안에서 끝납니다.
(() => {
  const $ = (id) => document.getElementById(id);
  const bot = $("bot"), q = $("q"), feed = $("feed"), proc = $("proc");
  const form = $("searchForm"), sendBtn = $("sendBtn"), bubble = $("bubble");
  const tagline = $("tagline"), quick = $("quick");
  const orgSel = $("h_org"), userSel = $("h_user");
  const pill = $("todoPill"), pillText = $("todoPillText");
  const drawer = $("todoDrawer"), drawerBody = $("todoBody"), scrim = $("scrim");

  let history = [];
  let busy = false;

  // ---------- 데스크톱 위젯 모드 ----------
  // Electron 껍데기로 열리면 캐릭터만 떠 있다가, 누르면 검색창이 열립니다.
  const shell = window.seobiShell || null;
  const isWidget = new URLSearchParams(location.search).get("shell") === "desktop";
  const body = document.body;

  function collapse() {
    if (!isWidget) return;
    body.classList.add("collapsed");
    body.classList.remove("opened", "large");
    shell && shell.collapse();
    mood("idle");
  }
  // 캐릭터를 누르면 곧장 큰 화면이 뜹니다.
  // 중간 크기 패널은 글을 읽기에도 좁고 한 번 더 눌러야 해서 없앴습니다.
  function expand() {
    if (!isWidget) return false;
    if (body.classList.contains("opened")) return false;
    body.classList.remove("collapsed");
    body.classList.add("opened", "large");
    shell && shell.large();
    setTimeout(() => q.focus(), 200);
    return true;
  }

  if (isWidget) {
    body.classList.add("shell-desktop", "collapsed");
    // 패널 머리에 작은 캐릭터 복제
    const mini = $("mini");
    if (mini) {
      const svg = bot.querySelector("svg").cloneNode(true);
      // 복제본의 <defs>는 반드시 지웁니다. 그대로 두면 그라디언트·필터 id가 문서에
      // 두 벌 생기고, 먼저 오는 쪽(숨겨진 패널 머리 안)이 잡혀서 원본 캐릭터의
      // 얼굴 채움과 링이 통째로 사라집니다. 복제본은 원본의 defs를 그냥 참조합니다.
      svg.querySelectorAll("defs").forEach((d) => d.remove());
      svg.removeAttribute("class"); svg.classList.add("h-bot-svg");
      mini.appendChild(svg);
      mini.dataset.mood = "idle";
    }
    $("barCollapse").onclick = collapse;
    $("barHide").onclick = () => shell && shell.hide();
    $("barTodo").onclick = () => openDrawer(true);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && body.classList.contains("opened") && drawer.hidden) collapse();
    });
    shell && shell.onGo && shell.onGo((which) => {
      if (which === "idle") collapse();
      else expand();              // open·large 모두 큰 화면 하나로
    });

    // 처음 켠 사람은 캐릭터가 눌리는 물건인지 모릅니다. 한 번만 알려 줍니다.
    try {
      if (!localStorage.getItem("seomu.widgetHinted")) {
        const hint = document.createElement("div");
        hint.className = "h-firsthint";
        hint.textContent = "눌러서 물어보세요";
        $("hero").appendChild(hint);
        const drop = () => { hint.remove(); try { localStorage.setItem("seomu.widgetHinted", "1"); } catch {} };
        bot.addEventListener("click", drop, { once: true });
        setTimeout(drop, 12000);
      }
    } catch {}
  }

  // ---------- 캐릭터 표정 ----------
  let moodTimer = null;
  function mood(m, say, holdMs) {
    clearTimeout(moodTimer);
    bot.dataset.mood = m;
    const mini = $("mini");
    if (mini) mini.dataset.mood = m;
    if (say) { bubble.textContent = say; bubble.hidden = false; }
    else bubble.hidden = true;
    if (holdMs) moodTimer = setTimeout(() => mood("idle"), holdMs);
  }
  mood("idle");

  // ==================================================================
  // 생동감 — 시선 따라보기, 가끔 쉬는 동작, 오래 두면 잠들기
  // ==================================================================
  let lastSeen = Date.now();          // 마지막으로 사람이 건드린 시각
  let asleep = false;
  let actTimer = null;

  function act(name, ms = 1000) {     // 한 번만 재생되는 동작
    if (asleep || busy) return;
    bot.dataset.act = name;
    clearTimeout(actTimer);
    actTimer = setTimeout(() => { if (bot.dataset.act === name) bot.dataset.act = ""; }, ms);
  }

  // 시선: 얼굴을 아주 조금만 움직입니다(과하면 불쾌해져요)
  function gaze(dx, dy) {
    const max = 7;
    const gx = Math.max(-max, Math.min(max, dx * max));
    const gy = Math.max(-max, Math.min(max, dy * max));
    bot.style.setProperty("--gx", gx.toFixed(1) + "px");
    bot.style.setProperty("--gy", gy.toFixed(1) + "px");
  }

  function lookFromPoint(px, py) {
    const r = bot.getBoundingClientRect();
    if (!r.width) return;
    const cx = r.left + r.width / 2, cy = r.top + r.height * 0.42;
    gaze((px - cx) / Math.max(260, r.width * 2), (py - cy) / Math.max(220, r.height * 2));
  }

  // 브라우저에서는 창 안의 마우스를, 위젯에서는 화면 전체의 마우스를 따라봅니다
  window.addEventListener("mousemove", (e) => { wake(); lookFromPoint(e.clientX, e.clientY); });
  if (shell && shell.onCursor) {
    shell.onCursor(({ dx, dy, near }) => {
      if (near) wake();
      if (!asleep) gaze(dx, dy);
    });
  }

  function wake() {
    lastSeen = Date.now();
    clearPose();
    if (!asleep) return;
    asleep = false;
    mood("idle");
    act("stretch", 1000);             // 깨면 기지개
  }

  function sleep() {
    if (asleep || busy) return;
    asleep = true;
    bot.dataset.act = "";
    clearPose();
    bot.style.setProperty("--gx", "0px");
    bot.style.setProperty("--gy", "0px");
    mood("sleep");
  }

  // 가끔 혼자 움직입니다
  const IDLE_ACTS = [
    { name: "tilt", ms: 1300, weight: 3 },
    { name: "sprout", ms: 800, weight: 3 },
    { name: "hop", ms: 560, weight: 2 },
    { name: "stretch", ms: 1000, weight: 2 },
    { name: "yawn", ms: 1500, weight: 1 },
  ];
  function pickAct() {
    const pool = IDLE_ACTS.flatMap((a) => Array(a.weight).fill(a));
    return pool[Math.floor(Math.random() * pool.length)];
  }
  function idleBeat() {
    const quiet = Date.now() - lastSeen;
    if (!busy && !asleep) {
      if (quiet > 3 * 60 * 1000) sleep();                 // 3분 넘게 조용하면 잠
      else if (!bot.dataset.pose && !bot.dataset.walk && Math.random() < 0.3) {
        const a = pickActivity();                         // 가끔 제 일을 시작합니다
        pose(a.name, a.ms);
        if (a.say) mood("happy", a.say, 2600);
      }
      else if (!bot.dataset.pose && Math.random() < 0.55) {
        const a = pickAct();
        // 조용할수록 하품·기지개 쪽이 어울립니다
        if (quiet > 60000 && Math.random() < 0.5) act("yawn", 1500);
        else act(a.name, a.ms);
      }
      // 가만히 있을 때 가끔 두리번
      if (!shell && Math.random() < 0.35) {
        gaze((Math.random() * 2 - 1) * 0.8, (Math.random() * 2 - 1) * 0.4);
        setTimeout(() => gaze(0, 0), 1400);
      }
    }
    setTimeout(idleBeat, 4200 + Math.random() * 4200);
  }
  setTimeout(idleBeat, 3000);

  // ---------- 활동: 일하기 / 책 읽기 / 아이디어 ----------
  // 가만히 떠 있기만 하면 인형 같아서, 가끔 자기 일을 하게 둡니다.
  let poseTimer = null;
  function pose(name, ms) {
    if (asleep || busy) return;
    bot.dataset.pose = name;
    clearTimeout(poseTimer);
    poseTimer = setTimeout(() => {
      if (bot.dataset.pose === name) bot.dataset.pose = "";
    }, ms);
  }
  function clearPose() { clearTimeout(poseTimer); bot.dataset.pose = ""; }

  const ACTIVITIES = [
    { name: "work", ms: 26000, weight: 4, say: null },
    { name: "read", ms: 22000, weight: 3, say: null },
    { name: "idea", ms: 4200, weight: 1, say: "아, 그러고 보니" },
  ];
  function pickActivity() {
    const pool = ACTIVITIES.flatMap((a) => Array(a.weight).fill(a));
    return pool[Math.floor(Math.random() * pool.length)];
  }

  // 걷기 신호를 창에서 받습니다
  if (shell && shell.onWalk) {
    shell.onWalk(({ walking, dir }) => {
      if (walking) {
        clearPose();
        bot.dataset.walk = "1";
        if (dir) bot.dataset.dir = String(dir);
        if (asleep) { asleep = false; mood("idle"); }
      } else {
        bot.dataset.walk = "";
        bot.dataset.dir = "";
        // 걷기를 마치면 자리를 잡고 제 일을 시작합니다
        if (!busy && Math.random() < 0.7) {
          const a = pickActivity();
          setTimeout(() => { pose(a.name, a.ms); if (a.say) mood("happy", a.say, 2600); }, 600);
        }
      }
    });
  }

  // 사람이 건드리면 깨어납니다 (자세도 풉니다)
  ["click", "keydown", "focusin", "wheel"].forEach((ev) =>
    window.addEventListener(ev, wake, { passive: true }));

  bot.addEventListener("mouseenter", () => { wake(); act("wave", 1300); });
  bot.addEventListener("mousedown", () => act("press", 320));

  // 접혀 있을 때, 투명한 빈 구석에서는 클릭이 뒤쪽 앱으로 지나가게 합니다.
  // 캐릭터(또는 말풍선·뱃지) 위일 때만 창이 마우스를 받습니다.
  if (shell && shell.setInteractive) {
    let lastHit = null;
    const HIT = ".h-bot, .h-bubble, .h-badge";
    const check = (x, y) => {
      if (!body.classList.contains("collapsed")) {       // 펼친 패널은 전체가 불투명
        if (lastHit !== true) { lastHit = true; shell.setInteractive(true); }
        return;
      }
      const el = document.elementFromPoint(x, y);
      const hit = !!(el && el.closest(HIT));
      if (hit !== lastHit) { lastHit = hit; shell.setInteractive(hit); }
    };
    window.addEventListener("mousemove", (e) => check(e.clientX, e.clientY));
    // 접힘/펼침이 바뀌면 즉시 다시 판정
    new MutationObserver(() => { lastHit = null; shell.setInteractive(true); })
      .observe(body, { attributes: true, attributeFilter: ["class"] });
  }

  // ---------- 기관 / 담당자 ----------
  async function loadWho() {
    try {
      await fillOrgSelect(orgSel);
      rememberOrg(orgSel.value);
      await fillUserSelect(userSel, orgSel.value);
      rememberUser(userSel.value);
    } catch (e) { toast(e.message); }
  }
  orgSel.onchange = async () => {
    rememberOrg(orgSel.value);
    await fillUserSelect(userSel, orgSel.value);
    rememberUser(userSel.value);
    history = []; feed.innerHTML = ""; proc.hidden = true;
    document.body.classList.remove("has-answer");
    loadQuick(); loadTodo();
  };
  userSel.onchange = () => { rememberUser(userSel.value); loadTodo(); };

  // ---------- 빠른 질문 ----------
  const QUICK_HINT = {
    travel_request: "출장 신청하려고 합니다",
    travel_settlement: "출장 다녀와서 정산해야 해요",
    annual_leave: "연가 신청 절차 알려주세요",
    sick_leave: "병가를 내려고 합니다",
    purchase: "물품 구매 300만원 진행하려고 합니다",
    event_hosting: "행사를 개최하려고 합니다",
    general_approval: "일반 기안을 올리려고 합니다",
  };
  async function loadQuick() {
    try {
      const d = await api("/api/tasks");
      const tasks = (d.tasks || d || []).slice(0, 6);
      quick.innerHTML = "";
      tasks.forEach((t) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = t.name;
        b.onclick = () => { q.value = QUICK_HINT[t.id] || `${t.name} 절차 알려주세요`; ask(); };
        quick.appendChild(b);
      });
    } catch { /* 없으면 조용히 넘어갑니다 */ }
  }

  // ---------- 프로세스 바 ----------
  function renderProc(r) {
    if (!r.task || !Array.isArray(r.steps) || !r.steps.length) { proc.hidden = true; return; }
    const steps = r.steps.slice(0, 6);
    proc.innerHTML = `
      <div class="h-proc-head">
        <b>${esc(r.task.name)} 진행 순서</b>
        <span class="muted">지금은 <b>1단계</b>부터 시작이에요</span>
      </div>
      <div class="h-proc-track">
        ${steps.map((s, i) => `
          <div class="h-step ${i === 0 ? "now" : ""}">
            <i>${i + 1}</i><span>${esc(s.length > 34 ? s.slice(0, 33) + "…" : s)}</span>
          </div>`).join("")}
      </div>`;
    proc.hidden = false;
  }

  // ==================================================================
  // 인트라넷 기안 올리기
  // 흐름: 결재 패키지 생성 → 사람이 확인·보정 → 인트라넷 등록(임시저장)
  //       → 사람이 눈으로 검증 → 상신
  // 서비는 스스로 상신하지 않습니다. 마지막 한 걸음은 늘 사람입니다.
  // ==================================================================
  function field(label, value, id, multiline) {
    const v = esc(value || "");
    return multiline
      ? `<label class="dr-f"><span>${label}</span><textarea id="${id}" rows="7">${v}</textarea></label>`
      : `<label class="dr-f"><span>${label}</span><input id="${id}" value="${v}"></label>`;
  }

  async function startDraft(r) {
    const box = document.createElement("section");
    box.className = "card dr";
    box.innerHTML = '<span class="spinner"></span> <span class="muted">기안 초안을 꾸리는 중…</span>';
    feed.appendChild(box);
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    mood("think", "기안을 꾸리는 중…");

    let m;
    try {
      m = await api("/api/packages", { method: "POST",
        body: { org_id: orgSel.value, message: r.message, user_id: userSel.value || null } });
    } catch (e) {
      box.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`;
      mood("sad", "기안을 못 만들었어요", 4000);
      return;
    }
    renderConfirm(box, m);
    mood("happy", "확인하고 올려 주세요", 3600);
  }

  // 1단계 — 올리기 전에 사람이 확인하고 고칩니다
  function renderConfirm(box, m) {
    const atts = (m.attachments || []).filter((a) => a.file);
    box.innerHTML = `
      <div class="dr-head"><b>인트라넷에 올릴 기안</b>
        <span class="badge b-note">올리기 전 확인</span></div>
      ${field("제목", m.title, "dr_title")}
      ${field("본문", m.body, "dr_body", true)}
      <div class="dr-meta">
        <div><span>전결권자</span><b>${esc((m.approval || {}).approver || "금액에 따라 다름")}</b></div>
        <div><span>근거 조문</span><b>${(m.evidence || []).length}건</b></div>
      </div>
      <div class="dr-att">
        <div class="dr-att-head"><span>붙임</span>
          <button type="button" class="ghost dr-pick">파일 넣기</button>
          <input type="file" class="dr-file" multiple hidden
                 accept="image/*,.pdf,.docx,.hwp,.hwpx,.xlsx,.txt,.csv">
        </div>
        <div class="dr-att-list"></div>
        <p class="muted" style="margin:0;font-size:11.5px">영수증·증빙을 여기에 끌어다 놓으면 기안에 함께 올라갑니다. 영수증 사진은 읽어서 금액을 본문에 넣어 드릴 수 있어요.</p>
      </div>
      ${(m.warnings || []).map((w) => `<div class="warnbox">${esc(w)}</div>`).join("")}
      <div class="dr-act">
        <button type="button" class="ghost dr-cancel">그만두기</button>
        <button type="button" class="primary dr-send">인트라넷에 올리기</button>
      </div>
      <p class="muted dr-note">올려도 바로 상신되지 않습니다. 임시저장 상태로 들어가고, 내용을 확인하신 뒤 직접 상신하시면 됩니다.</p>`;

    // ----- 붙임 -----
    const listEl = box.querySelector(".dr-att-list");
    const fileEl = box.querySelector(".dr-file");

    function drawAtts(cur) {
      const items = (cur.attachments || []).filter((a) => a.file);
      listEl.innerHTML = items.length ? "" :
        '<span class="muted" style="font-size:12px">아직 없습니다</span>';
      items.forEach((a) => {
        const row = document.createElement("div");
        row.className = "dr-att-row";
        row.innerHTML = `<span class="dr-att-name">${a.kind === "image" ? "🧾" : "📄"} ${esc(a.name)}<i>${esc(a.ext || "")}</i></span>`;
        if (a.kind === "image") {
          const rb = document.createElement("button");
          rb.type = "button"; rb.className = "ghost"; rb.textContent = "영수증 읽기";
          rb.onclick = () => readReceipt(rb, a);
          row.appendChild(rb);
        }
        const db = document.createElement("button");
        db.type = "button"; db.className = "ghost dr-x"; db.textContent = "✕"; db.title = "빼기";
        db.onclick = async () => {
          try { drawAtts(await api(`/api/orgs/${m.org_id}/packages/${m.id}/attachments`,
                  { method: "DELETE", body: { file: a.file } })); }
          catch (e) { toast(e.message); }
        };
        row.appendChild(db);
        listEl.appendChild(row);
      });
    }
    drawAtts(m);

    async function upload(files) {
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        try {
          const res = await fetch(`/api/orgs/${m.org_id}/packages/${m.id}/attachments`,
                                  { method: "POST", body: fd });
          const d = await res.json();
          if (!res.ok) throw new Error(d.detail || "올리지 못했어요");
          drawAtts(d);
          toast(`${f.name} 넣었어요`);
        } catch (e) { toast(e.message); }
      }
    }

    box.querySelector(".dr-pick").onclick = () => fileEl.click();
    fileEl.onchange = () => { if (fileEl.files.length) upload([...fileEl.files]); fileEl.value = ""; };
    box.addEventListener("dragover", (e) => { e.preventDefault(); box.classList.add("dr-over"); });
    box.addEventListener("dragleave", () => box.classList.remove("dr-over"));
    box.addEventListener("drop", (e) => {
      e.preventDefault(); box.classList.remove("dr-over");
      if (e.dataTransfer.files.length) upload([...e.dataTransfer.files]);
    });

    // 영수증을 읽어 본문에 넣을지 사람이 정합니다
    async function readReceipt(btn, a) {
      btn.disabled = true;
      const old = btn.textContent;
      btn.innerHTML = '<span class="spinner"></span> 읽는 중';
      mood("think", "영수증을 읽는 중…");
      try {
        const out = await api(`/api/orgs/${m.org_id}/packages/${m.id}/read-receipt`,
                              { method: "POST", body: { file: a.file } });
        if (!out.ok) throw new Error(out.error || "읽지 못했어요");
        const d = out.data || {};
        const line = [
          d.store && `지급처 ${d.store}`,
          (d.amount || d.amount === 0) && `금액 ${Number(d.amount).toLocaleString()}원`,
          d.date && `일자 ${d.date}`,
          d.approval_no && `승인번호 ${d.approval_no}`,
        ].filter(Boolean).join(" · ");
        if (!line) throw new Error("영수증에서 값을 찾지 못했어요");
        if (confirm(`읽은 내용을 본문에 넣을까요?\n\n${line}`)) {
          const ta = $("dr_body");
          ta.value = ta.value.replace(/\n*끝\.$/, "") + `\n  · ${line}\n\n끝.`;
        }
        mood("happy", "읽었어요", 3000);
      } catch (e) {
        toast(e.message); mood("sad", "못 읽었어요", 3000);
      }
      btn.disabled = false; btn.textContent = old;
    }

    box.querySelector(".dr-cancel").onclick = () => box.remove();
    box.querySelector(".dr-send").onclick = async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> 올리는 중';
      try {
        const changes = { title: $("dr_title").value.trim(), body: $("dr_body").value };
        await api(`/api/orgs/${m.org_id}/packages/${m.id}`, { method: "PUT", body: { changes } });
        const out = await api(`/api/orgs/${m.org_id}/packages/${m.id}/send`, { method: "POST" });
        renderSent(box, out.package, out.result);
        mood("happy", "올렸어요", 4000);
        act("hop", 560);
        loadTodo();
      } catch (err) {
        btn.disabled = false; btn.textContent = "인트라넷에 올리기";
        const w = document.createElement("div");
        w.className = "warnbox"; w.textContent = err.message;
        box.insertBefore(w, box.querySelector(".dr-act"));
        mood("sad", "올리지 못했어요", 4000);
      }
    };
  }

  // 2단계 — 올라갔습니다. 상신은 사람이 누릅니다.
  function renderSent(box, m, res) {
    const info = m.intranet || res || {};
    box.className = "card dr dr-done";
    box.innerHTML = `
      <div class="dr-head"><b>인트라넷에 올라갔습니다</b>
        <span class="badge b-ok">임시저장</span></div>
      <div class="dr-meta">
        <div><span>문서번호</span><b>${esc(info.doc_no || "-")}</b></div>
        <div><span>연결</span><b>${esc(info.provider || "-")}</b></div>
        <div><span>제목</span><b>${esc(m.title || "")}</b></div>
      </div>
      <p class="muted dr-note">${esc((info.meta || {}).note || "인트라넷에서 내용을 확인하신 뒤 상신해 주세요.")}</p>
      <div class="dr-act">
        <button type="button" class="ghost dr-view">올라간 내용 보기</button>
        <button type="button" class="primary dr-submit">확인했습니다 · 상신</button>
      </div>`;

    box.querySelector(".dr-view").onclick = async (e) => {
      const btn = e.currentTarget;
      try {
        const doc = await api(`/api/approval/mock/${encodeURIComponent(info.doc_no)}`);
        const pre = document.createElement("pre");
        pre.className = "dr-pre";
        pre.textContent = `제목: ${doc.title}\n문서번호: ${doc.doc_no}\n상태: ${doc.state}\n붙임: ${(doc.attachments || []).join(", ") || "없음"}\n\n${doc.contents}`;
        btn.replaceWith(pre);
      } catch (err) { toast(err.message); }
    };

    box.querySelector(".dr-submit").onclick = async (e) => {
      if (!confirm("상신하면 결재선을 따라 올라갑니다. 내용을 확인하셨나요?")) return;
      const btn = e.currentTarget;
      btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> 상신 중';
      try {
        const out = await api(`/api/orgs/${m.org_id}/packages/${m.id}/submit`, { method: "POST" });
        box.querySelector(".badge").className = "badge b-ok";
        box.querySelector(".badge").textContent = "상신됨";
        box.querySelector(".dr-act").innerHTML =
          '<span class="muted">상신했습니다. 후속 업무는 작업 내역에 올려 두었어요.</span>';
        mood("happy", "상신 완료", 4000);
        loadTodo();
      } catch (err) {
        btn.disabled = false; btn.textContent = "확인했습니다 · 상신";
        toast(err.message);
      }
    };
  }

  // ---------- 질문 ----------
  async function ask(text) {
    const message = (text ?? q.value).trim();
    if (!message || busy) return;
    busy = true; sendBtn.disabled = true;
    clearPose();
    document.body.classList.add("has-answer");
    if (resetBtn) resetBtn.hidden = false;

    const mine = document.createElement("div");
    mine.className = "h-ask";
    mine.textContent = message;
    feed.appendChild(mine);
    q.value = "";
    mine.scrollIntoView({ behavior: "smooth", block: "nearest" });

    const wait = document.createElement("div");
    wait.className = "card";
    wait.innerHTML = '<span class="spinner"></span> <span class="muted">규정을 찾아보고 있어요…</span>';
    feed.appendChild(wait);
    mood("think", "찾는 중이에요…");
    tagline.textContent = "찾아보고 있어요";

    try {
      // 2단계 응답: 규칙 기반 답을 먼저 띄우고(거의 즉시), AI가 다듬은 문장은
      // 뒤이어 받아서 갈아 끼웁니다. 담당자를 30초씩 기다리게 하지 않기 위해서예요.
      const r = await api("/api/chat", {
        method: "POST",
        body: { org_id: orgSel.value, message, user_id: userSel.value || null,
                fast: true, history: history.slice(-4) },
      });
      wait.remove();
      const card = renderAnswer(r, {
        onSuggest: (s) => ask(`${s.name} 절차 알려주세요`),
        onNextAction: (a) => ask(a),
      });
      feed.appendChild(card);
      // 서식 초안 버튼은 뺍니다. 기안을 올리면 서식이 붙임으로 함께 들어가므로
      // 따로 문서만 받는 단계는 한 번 더 누르게 만들 뿐입니다.
      card.querySelectorAll(".formbox").forEach((el) => {
        if (el.querySelector(".make-form")) el.remove();
      });
      renderProc(r);

      // 분류가 된 건이면 바로 기안으로 넘어갈 수 있게 합니다
      if (r.task) {
        const bar = document.createElement("div");
        bar.className = "dr-cta";
        const b = document.createElement("button");
        b.type = "button"; b.className = "primary";
        b.textContent = "📨 인트라넷에 기안 올리기";
        b.onclick = () => { b.disabled = true; startDraft(r); };
        bar.appendChild(b);
        const hint = document.createElement("span");
        hint.className = "muted";
        hint.textContent = "올리기 전에 내용을 확인하고 고칠 수 있어요";
        bar.appendChild(hint);
        card.appendChild(bar);
      }
      history.push({ q: message, a: r.summary || "" });

      mood("happy", "먼저 규정에서 찾은 내용이에요", 3200);
      act("hop", 560);
      tagline.textContent = r.task ? r.task.name : "더 물어보셔도 돼요";
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      loadTodo();

      // 여기서부터는 기다리지 않습니다. 화면은 이미 쓸 수 있는 상태입니다.
      if (r.summary_pending) {
        mood("think", "문장을 다듬는 중…");
        refineSummary(card, r).finally(() => {
          mood("happy", "다듬었어요", 2600);
          const p = card.querySelector(".ans-summary");
          if (p) history[history.length - 1].a = p.textContent || history[history.length - 1].a;
        });
      }
    } catch (e) {
      wait.remove();
      const err = document.createElement("div");
      err.className = "card";
      err.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`;
      feed.appendChild(err);
      mood("sad", "잘 안 됐어요", 5000);
      tagline.textContent = "다시 한 번 물어봐 주세요";
    }
    busy = false; sendBtn.disabled = false; q.focus();
  }

  function reset() {
    history = []; feed.innerHTML = ""; proc.hidden = true;
    body.classList.remove("has-answer");
    tagline.textContent = "무엇을 도와드릴까요?";
    q.value = ""; q.focus(); mood("idle");
  }
  const resetBtn = $("resetBtn");
  if (resetBtn) resetBtn.onclick = reset;

  form.onsubmit = (e) => { e.preventDefault(); ask(); };
  bot.onclick = () => {
    if (expand()) return;                 // 위젯이 접혀 있었다면 펼치기만 합니다
    q.focus(); mood("listen", "말씀하세요", 2200);
  };
  q.onfocus = () => { if (!busy && bot.dataset.mood === "idle") mood("listen"); };
  q.onblur = () => { if (!busy && bot.dataset.mood === "listen") mood("idle"); };

  // 아무 키나 누르면 입력창으로
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (document.activeElement === q) return;
    if (document.body.classList.contains("collapsed")) return;
    if (/^[\w가-힣ㄱ-ㅎㅏ-ㅣ]$/.test(e.key)) q.focus();
  });

  // ---------- 말로 입력 ----------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const micBtn = $("micBtn");
  if (!SR) micBtn.hidden = true;
  else {
    let rec = null;
    micBtn.onclick = () => {
      if (rec) { rec.stop(); return; }
      rec = new SR();
      rec.lang = "ko-KR"; rec.interimResults = true;
      micBtn.classList.add("on"); mood("listen", "듣고 있어요");
      rec.onresult = (ev) => {
        q.value = Array.from(ev.results).map((x) => x[0].transcript).join("");
      };
      rec.onend = () => {
        micBtn.classList.remove("on"); rec = null;
        if (bot.dataset.mood === "listen") mood("idle");
        if (q.value.trim()) ask();
      };
      rec.onerror = () => { micBtn.classList.remove("on"); rec = null; mood("idle"); };
      rec.start();
    };
  }

  // ---------- 작업 내역 ----------
  async function loadTodo() {
    if (!orgSel.value) return;
    try {
      const u = userSel.value ? `?user_id=${encodeURIComponent(userSel.value)}` : "";
      const d = await api(`/api/orgs/${orgSel.value}/dashboard${u}`);
      const n = d.total_open || 0;
      pill.hidden = false;
      pill.classList.toggle("quiet", !d.overdue);
      pillText.textContent = n
        ? (d.overdue ? `기한 지난 건 ${d.overdue} · 할 일 ${n}` : `할 일 ${n}`)
        : "작업 내역";
      const badge = $("badge");
      if (badge) {
        const show = d.overdue || n;
        badge.textContent = String(show);
        badge.hidden = !show;
        badge.title = d.overdue ? `기한 지난 건 ${d.overdue}건` : `할 일 ${n}건`;
      }
      drawTodo(d);
    } catch { pill.hidden = true; }
  }

  function drawTodo(d) {
    const items = d.open || [];
    if (!items.length) {
      drawerBody.innerHTML = `<div class="h-empty">열려 있는 작업이 없어요.<br>질문을 하면 처리할 일이 여기에 쌓입니다.</div>`;
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    drawerBody.innerHTML = "";
    items.forEach((it) => {
      const over = (it.deadline_due || "") < today;
      const box = document.createElement("div");
      box.className = "h-todo" + (over ? " over" : "");
      box.innerHTML = `
        <div class="h-todo-top">
          <b>${esc(it.task_name || it.task || "작업")}</b>
          <span class="due">${esc(it.deadline_label || "기한")} ${esc(it.deadline_due || "")}${over ? " · 지남" : ""}</span>
        </div>
        ${it.message ? `<div class="muted">${esc(it.message)}</div>` : ""}`;
      const b = document.createElement("button");
      b.type = "button"; b.className = "ghost"; b.textContent = "처리 완료";
      b.onclick = async () => {
        b.disabled = true;
        try {
          await api(`/api/orgs/${orgSel.value}/history/${it.id}/done`, { method: "POST" });
          box.remove(); loadTodo(); toast("처리 완료로 표시했어요");
        } catch (e) { toast(e.message); b.disabled = false; }
      };
      box.appendChild(b);
      drawerBody.appendChild(box);
    });
  }

  function openDrawer(on) {
    drawer.hidden = !on; scrim.hidden = !on;
  }
  pill.onclick = () => openDrawer(true);
  $("todoClose").onclick = () => openDrawer(false);
  scrim.onclick = () => openDrawer(false);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") openDrawer(false); });

  // ---------- 개발용 실시간 새로고침 (?dev=1) ----------
  // 파일이 바뀌면 바로 반영됩니다. 서버가 Last-Modified를 주는 점만 이용해서
  // 추가 도구 없이 동작합니다. 평소에는 꺼져 있어요.
  if (new URLSearchParams(location.search).get("dev") === "1") {
    const files = ["home.html", "home.css", "home.js", "app.css", "answer.js", "common.js"];
    const seen = {};
    const stamp = async (f) => {
      try {
        const r = await fetch(f + "?_=" + Date.now(), { method: "HEAD", cache: "no-store" });
        return r.headers.get("last-modified") || r.headers.get("etag") || "";
      } catch { return ""; }
    };
    (async () => {
      for (const f of files) seen[f] = await stamp(f);
      const tag = document.createElement("div");
      tag.textContent = "실시간 반영 중";
      tag.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:999;background:#245344;color:#fff;" +
        "font-size:11px;padding:4px 10px;border-radius:999px;opacity:.75;pointer-events:none";
      document.body.appendChild(tag);
      setInterval(async () => {
        for (const f of files) {
          const now = await stamp(f);
          if (now && seen[f] && now !== seen[f]) {
            tag.textContent = "바뀜 — 새로고침";
            return location.reload();
          }
          seen[f] = now || seen[f];
        }
      }, 1000);
    })();
  }

  // ---------- 시작 ----------
  (async () => {
    await loadWho();
    loadQuick();
    loadTodo();
    q.focus();
  })();
})();
