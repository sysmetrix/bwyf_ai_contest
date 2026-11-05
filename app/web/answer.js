// 비서 답변 카드 그리기
function renderAnswer(r, { compact = false, onSuggest, onNextAction } = {}) {
  const el = document.createElement("section");
  el.className = "card answer";
  const u = r.understanding || {};
  const slots = u.slots || {};
  const slotText = [
    slots.destination && `출장지 ${slots.destination}`,
    slots.start_date && (slots.end_date && slots.end_date !== slots.start_date ? `${slots.start_date} ~ ${slots.end_date}` : slots.start_date),
    slots.days && `${slots.days}일`,
    slots.amount_won && won(slots.amount_won),
    slots.item && `품목 ${slots.item}`,
  ].filter(Boolean).join(" · ");

  if (!r.task) {
    const docsHtml = (r.docs || []).length ? `<div><div class="muted" style="margin-bottom:4px">참고하는 문서 (눌러서 원문 보기)</div>
        ${r.docs.slice(0, 8).map((d) => `<a class="chip b-note" href="${docOpenUrl(r.org.id, d.file)}" target="_blank" rel="noopener">${esc(d.layer_label)} · ${esc(d.name)}</a>`).join("")}
        ${r.docs.length > 8 ? `<span class="muted" style="font-size:12px">외 ${r.docs.length - 8}개</span>` : ""}</div>` : "";
    const linksHtml = (r.links || []).map((l) => `<a class="btn" href="${esc(l.href)}">${esc(l.label)} →</a>`).join(" ");
    const isAi = (r.summary_by || "").startsWith("AI");
    el.innerHTML = `<div class="ans-text">${isAi ? richText(r.summary) : `<p style="margin:0;white-space:pre-line">${esc(r.summary)}</p>`}</div>
      ${isAi ? `<div class="ans-meta"><span class="muted">${esc(r.summary_by)}${r.related_task ? ` · ${esc(r.related_task.name)} 기준` : ""}</span>
        <button type="button" class="ghost copy-ans">복사</button></div>` : ""}
      ${isAi && r.kind === "chat" && !r.grounded && !r.related_task ? `<div class="muted" style="font-size:12px">AI가 쓴 내용이에요. 기한·금액처럼 기관 기준이 필요한 부분은 규정이나 담당 부서로 한 번 더 확인해 주세요.</div>` : ""}
      ${docsHtml}
      ${linksHtml ? `<div>${linksHtml}</div>` : ""}
      ${r.evidence?.length ? `<div><div class="muted">관련 있어 보이는 조문 (누르면 내용 보기)</div>${evidenceChips(r.evidence, r.org.id)}</div>` : ""}
      ${(r.suggestions || []).length ? `<div class="muted" style="font-size:12px">업무 절차를 안내받으려면:</div>` : ""}
      <div class="sugg"></div>`;
    const box = el.querySelector(".sugg");
    (r.suggestions || []).forEach((s) => {
      const b = document.createElement("button");
      b.textContent = s.name; b.style.margin = "0 6px 6px 0";
      b.onclick = () => onSuggest && onSuggest(s);
      box.appendChild(b);
    });
    const copy = el.querySelector(".copy-ans");
    if (copy) copy.onclick = async () => {
      try { await navigator.clipboard.writeText(r.summary); copy.textContent = "복사했어요 ✓"; }
      catch { copy.textContent = "복사 안 됨 — 직접 선택해 주세요"; }
      setTimeout(() => (copy.textContent = "복사"), 2000);
    };
    wireEvidence(el);
    return el;
  }

  const dl = !r.deadline ? "" : r.deadline.text
    ? `<dt>${esc(r.deadline.label)}</dt><dd><b>${esc(r.deadline.text)}</b></dd>`
    : `<dt>${esc(r.deadline.label)}</dt><dd class="muted">규정에서 찾지 못했어요 · <a href="profile.html">기관 프로필에서 정하기</a></dd>`;
  const ap = r.approval || {};
  const apText = ap.approver ? `${esc(ap.approver)} 전결 (${won(ap.amount_won)})` : "금액에 따라 다름";
  el.innerHTML = `
    <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
      <span class="badge b-accent">${esc(r.task.category)} › ${esc(r.task.name)}</span>
      <span class="muted">${esc(r.org.name)} 프로필 기준 · 분류: ${esc(u.method)}${slotText ? " · " + esc(slotText) : ""}</span>
    </div>
    <p class="ans-summary" style="margin:0">${esc(r.summary)} ${r.summary_pending ? "" : `<span class="muted">(${esc(r.summary_by)})</span>`}</p>
    ${(r.warnings || []).map((w) => `<div class="warnbox">${esc(w)}</div>`).join("")}
    ${(r.tips || []).map((t) => `<div class="tipbox">💡 ${esc(t)}</div>`).join("")}
    <div><h3>처리 절차 ${r.steps_custom ? `<span class="badge b-accent">기관 맞춤</span>` : `<span class="badge b-note">공통 절차</span>`}</h3><ol>${r.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol></div>
    <dl class="kv">${dl}<dt>전결권자</dt><dd>${apText}</dd><dt>전결 기준</dt><dd>${esc(ap.basis)}</dd>
      <dt>필요 서류</dt><dd>${r.required_docs.map(esc).join(", ")}</dd></dl>
    <div><div class="muted">근거 (누르면 조문 보기)</div>${evidenceChips(r.evidence, r.org.id)}
      ${(r.practice || []).map((p) => `<span class="chip ${p.conflict ? "b-warn" : "b-note"}" title="${esc(p.conflict || "")}">개인 보충 · ${esc(p.text)}${p.conflict ? " ⚠" : ""}</span>`).join("")}
    </div>
    ${!compact && r.form?.available ? `<div class="formbox"><div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between">
        <b>${esc(r.form.name || "서식")} 초안</b><button class="primary make-form">${esc(r.form.name || "서식")} 초안 만들기 (${esc(r.form.ext || "문서")})</button></div>
        <div class="form-result muted" style="margin-top:8px">${(r.form.fills || []).length
          ? `${r.form.fills.map(esc).join("·")}을(를) 이 질문과 기관 기준으로 채워 드려요.` : "질문에서 알아낸 값을 서식에 채워 드려요."} 원본 서식은 그대로 두고 새 파일로 만들어요.</div></div>` : ""}
    ${!compact && r.form && !r.form.available ? `<div class="formbox muted" style="font-size:13px">
        이 기관에는 아직 <b>${esc(r.form.name || "서식")}</b> 서식이 없어요. <a href="forms.html">서식 보관함</a>에 올려 두면 ${(r.form.fills || []).map(esc).join("·")}까지 채운 초안을 만들어 드려요.</div>` : ""}
    ${!compact ? `<div><h3>다음 할 일</h3><p class="muted" style="margin:0 0 8px;font-size:12px">눌러서 바로 이어서 물어볼 수 있어요</p>
        ${r.next_actions.map((a, i) => `<button type="button" class="chip chip-action" data-i="${i}">${esc(a)}</button>`).join("")}</div>` : ""}
    ${!compact && r.user_id && r.history_id ? `<div class="notify-box" style="margin-top:4px">
        <button type="button" class="notify-mail">이 안내 메일로 받기</button>
        <span class="muted notify-msg"></span></div>` : ""}
  `;
  wireEvidence(el);
  el.querySelectorAll(".chip-action").forEach((b) => {
    b.onclick = () => onNextAction && onNextAction(r.next_actions[Number(b.dataset.i)]);
  });
  const mailBtn = el.querySelector(".notify-mail");
  if (mailBtn) mailBtn.onclick = async () => {
    mailBtn.disabled = true;
    const msg = el.querySelector(".notify-msg");
    try {
      await api("/api/notify", { method: "POST",
        body: { org_id: r.org.id, user_id: r.user_id, history_id: r.history_id } });
      msg.textContent = "메일로 보냈어요";
    } catch (e) { msg.textContent = e.message; }
    mailBtn.disabled = false;
  };
  const btn = el.querySelector(".make-form");
  if (btn) btn.onclick = async () => {
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> 만드는 중';
    const box = el.querySelector(".form-result");
    try {
      const f = await api("/api/forms/draft", { method: "POST", body: { org_id: r.org.id, form_id: r.form.id, message: r.message } });
      box.innerHTML = renderFormPreview(f);
    } catch (e) { box.textContent = e.message; }
    btn.disabled = false; btn.textContent = "다시 만들기";
  };
  return el;
}

// 서식 초안을 '글로 나열'하지 않고, 원본 서식과 같은 표 모양 그대로 보여줍니다.
function renderFormPreview(f) {
  const p = f.preview;
  let body;
  if (p && p.tables && p.tables.length) {
    body = p.tables.map((rows) => `<table class="form-preview">${rows.map((cells) =>
      `<tr>${cells.map((c, i) => {
        const warn = /^\[.*\]$/.test(c.trim());
        const tag = i === 0 ? "th" : "td";
        return `<${tag}${warn ? ' class="fp-warn"' : ""}>${esc(c)}</${tag}>`;
      }).join("")}</tr>`).join("")}</table>`).join("");
  } else {
    body = `<dl class="kv" style="color:var(--ink)">${Object.entries(f.filled)
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  }
  return `${p && p.title_lines?.length ? `<div class="fp-title">${p.title_lines.map(esc).join("<br>")}</div>` : ""}
    ${body}
    ${f.missing.length ? `<p class="badge b-warn" style="margin:8px 0">빈칸 ${f.missing.length}곳 확인 필요: ${f.missing.map(esc).join(", ")}</p>` : ""}
    <p style="margin:8px 0 0"><a class="btn" href="${esc(f.download)}">내려받기 · ${esc(f.name)}</a></p>`;
}

// AI 답의 간단한 서식(**굵게**, - 목록, # 제목, 빈 줄 문단)만 안전하게 보여 줍니다. 그 밖의 HTML은 모두 글자로 처리.
function richText(text) {
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  const out = [];
  let list = null;
  for (const raw of String(text || "").split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; } out.push("<hr>"); continue; }
    if (/^\s*-\s*다\s*음\s*-?\s*$/.test(line) || /^\s*-\s*아\s*래\s*-?\s*$/.test(line)) {  // 공문의 '- 다 음 -'
      if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; }
      out.push(`<p class="rt-center">${esc(line.trim())}</p>`); continue;
    }
    const li = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (li) { if (!list) { list = []; } list.push(`<li>${inline(li[1])}</li>`); continue; }
    if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; }
    const h = /^#{1,4}\s+(.*)$/.exec(line);
    if (h) out.push(`<p class="rt-h">${inline(h[1])}</p>`);
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push(`<ul>${list.join("")}</ul>`);
  return out.join("");
}

// 빠른 답을 먼저 보여 준 뒤, AI가 다듬은 안내 문장이 오면 그 부분만 바꿉니다.
async function refineSummary(card, r) {
  const p = card.querySelector(".ans-summary");
  if (!p || !r.task) return;
  const note = document.createElement("span");
  note.className = "muted";
  note.style.fontSize = "12px";
  note.innerHTML = ' <span class="spinner" style="width:11px;height:11px"></span> AI가 문장을 다듬는 중';
  p.appendChild(note);
  try {
    const u = r.understanding || {};
    const s = await api("/api/chat/summary", { method: "POST", body: {
      org_id: r.org.id, message: r.message, task_id: r.task.id, slots: u.slots || {}, method: u.method } });
    p.innerHTML = `${esc(s.summary)} <span class="muted">(${esc(s.summary_by)})</span>`;
    p.classList.add("refined");
  } catch { note.remove(); }
}

function docOpenUrl(orgId, file) {
  return `/api/orgs/${encodeURIComponent(orgId)}/docs/open?file=${encodeURIComponent(file)}`;
}

function evidenceChips(list, orgId) {
  return (list || []).map((e, i) =>
    `<button class="chip b-ok ev" data-i="${i}" aria-expanded="false">근거 · ${esc(e.label)} <small>(${esc(e.layer_label)})</small></button>
     <div class="evidence-text" data-for="${i}" hidden>${esc(e.text)}\n\n${orgId && e.file
       ? `<a href="${docOpenUrl(orgId, e.file)}" target="_blank" rel="noopener">원문 열기 · ${esc(e.file.split(/[\\/]/).pop())}</a>`
       : `파일: ${esc(e.file)}`}</div>`).join("");
}

function wireEvidence(root) {
  root.querySelectorAll("button.ev").forEach((b) => {
    b.onclick = () => {
      const t = root.querySelector(`.evidence-text[data-for="${b.dataset.i}"]`);
      t.hidden = !t.hidden; b.setAttribute("aria-expanded", String(!t.hidden));
    };
  });
}
