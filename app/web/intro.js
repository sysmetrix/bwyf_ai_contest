// 첫 방문 소개 모션(약 15초). 한 번 본 뒤엔 다시 뜨지 않고, 설정 메뉴에서 다시 볼 수 있어요.
const INTRO_KEY = "seomu.introSeen";

function playIntro({ force = false } = {}) {
  let seen; try { seen = localStorage.getItem(INTRO_KEY); } catch { seen = "1"; }
  if (seen && !force) return;

  const SPRING = "cubic-bezier(.34,1.56,.64,1)";
  const OUT = "cubic-bezier(.16,1,.3,1)";
  const IN = "cubic-bezier(.7,0,.84,0)";
  const timers = [];
  const root = document.createElement("div");
  root.className = "intro";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-label", "서비 소개");

  const feats = [["💬", "업무 안내"], ["📄", "서식 초안"], ["📚", "규정 근거"], ["🧾", "전결 판정"], ["🏢", "기관 맞춤"], ["🤖", "AI 연결"],
    ["🗂", "서식 보관함"], ["📖", "규정 원문"], ["🔔", "변경 알림"], ["📝", "개인 보충"], ["📧", "메일 안내"], ["✅", "다음 할 일"]];
  const chips = ["제12조(여비 정산)", "전결 기준", "결재선", "복귀 후 5일", "견적서 2부", "연가 3일 전", "별표 1", "일비 25,000원"];

  root.innerHTML = `
    <div class="grain"></div><div class="glow"></div>
    <div class="layer s1"><div class="sweep"></div>
      ${Array.from({ length: 3 }, () => '<div class="ring"></div>').join("")}
      ${Array.from({ length: 18 }, () => '<div class="spark"></div>').join("")}
      <div class="logo-tile">서</div>
      <div class="brand-word">${[..."서비"].map((c) => `<span>${c}</span>`).join("")}</div>
      <div class="brand-sub">SEOMU · AI · SECRETARY</div></div>
    <div class="layer s2">
      ${chips.map((c) => `<div class="chipfloat">${c}</div>`).join("")}
      <div class="slot"><div class="slot-inner">
        <span>출장 정산</span><span>연가 신청</span><span>물품 구매</span><span>행사 개최</span><span>결재선은?</span><span class="hl">규정은 어디?</span>
      </div></div></div>
    <div class="layer s3"><div class="stage">
      <div class="bubble"><span class="typed"></span><span class="caret"></span></div>
      <div class="acard"><span class="tag">출장 › 여비 정산</span>
        <ol><li><i>✓</i>영수증 모으기</li><li><i>✓</i>여비 정산서 작성</li><li><i>✓</i>팀장 전결로 상신</li><li><i>✓</i>회계 담당 지급</li></ol>
        <div class="pills"><span class="pill p1">⏰ 복귀일부터 5일 이내</span><span class="pill p2">근거 · 여비규정 제12조</span><span class="pill p3">💡 서식 자동 작성</span></div>
      </div></div></div>
    <div class="layer s4"><div class="doc"><h4>여비정산서</h4><div class="rows">
      ${[["출장지", "세종"], ["출장 기간", "11.3 ~ 11.4 (2일)"], ["일비", "50,000원"], ["제출 기한", "복귀일부터 5일 이내"], ["결재선", "담당 → 팀장"]]
        .map(([k, v]) => `<div class="row"><b>${k}</b><span data-v="${v}"></span></div>`).join("")}
      </div><div class="stamp">초안<br>완성</div></div></div>
    <div class="layer s5"><div class="count"><b>0</b>SMART TOOLS</div>
      <div class="feats">${feats.map(([i, t]) => `<div class="feat"><i>${i}</i><span>${t}</span></div>`).join("")}</div></div>
    <div class="wipe"></div>
    <div class="layer s6"><div class="final">
      <div class="logo-mini">서</div>
      <h2><span class="ln"><span>복잡한 서무 업무,</span></span><span class="ln"><span>이제 서비에게.</span></span></h2>
      <p>기관 규정 · 결재선 · 서식까지, 말 한마디로 안내해 드려요</p>
      <button type="button" class="go">시작하기</button></div></div>
    <button type="button" class="skip">건너뛰기 ›</button>
    <div class="bar"></div>`;
  document.body.appendChild(root);

  const $ = (s) => root.querySelector(s);
  const $$ = (s) => [...root.querySelectorAll(s)];
  const A = (el, kf, o) => el && el.animate(kf, { fill: "forwards", easing: OUT, ...o });
  const at = (ms, fn) => timers.push(setTimeout(fn, ms));
  const clear = (...ns) => ns.forEach((n) => ($(`.s${n}`).style.display = "none"));

  function close() {
    timers.forEach(clearTimeout);
    try { localStorage.setItem(INTRO_KEY, "1"); } catch {}
    root.classList.add("out");
    setTimeout(() => root.remove(), 520);
    document.removeEventListener("keydown", onKey);
  }
  function onKey(e) { if (e.key === "Escape") close(); }
  document.addEventListener("keydown", onKey);
  $(".skip").onclick = close;
  $(".go").onclick = close;

  if (!force && matchMedia("(prefers-reduced-motion: reduce)").matches) {
    $$(".layer").forEach((l) => (l.style.display = "none"));
    $(".s6").style.display = "grid";
    $(".wipe").style.transform = "scaleY(1)";
    [".logo-mini", ".final p", ".go"].forEach((s) => ($(s).style.opacity = 1));
    $$(".final .ln > span").forEach((s) => (s.style.transform = "none"));
    const replay = document.createElement("button");
    replay.type = "button";
    replay.className = "replay";
    replay.textContent = "▶ 소개 영상 보기";
    replay.onclick = () => {
      document.removeEventListener("keydown", onKey);
      root.remove();
      playIntro({ force: true });
    };
    $(".go").after(replay);
    return;
  }

  A($(".bar"), [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], { duration: 15000, easing: "linear" });
  A($(".grain"), [{ transform: "translate(0,0)" }, { transform: "translate(-3%,2%)" }], { duration: 15000, easing: "linear" });

  // ── 1. 로고 등장 (0 ~ 2.3s)
  A($(".sweep"), [{ transform: "scaleX(0)", opacity: 1 }, { transform: "scaleX(1)", opacity: 1, offset: .55 }, { transform: "scaleX(0)", opacity: 0 }],
    { duration: 700, easing: "cubic-bezier(.65,0,.35,1)" });
  at(560, () => {
    A($(".logo-tile"), [{ opacity: 0, transform: "scale(0) rotate(-35deg)" }, { opacity: 1, transform: "scale(1.18) rotate(6deg)", offset: .6 },
      { opacity: 1, transform: "scale(1) rotate(0)" }], { duration: 700, easing: SPRING });
    A($(".glow"), [{ opacity: 0, transform: "scale(.4)" }, { opacity: 1, transform: "scale(1)" }], { duration: 1200 });
    $$(".ring").forEach((r, i) => A(r, [{ opacity: .9, transform: "scale(1)" }, { opacity: 0, transform: `scale(${3.2 + i})` }],
      { duration: 1100, delay: i * 140 }));
    $$(".spark").forEach((s, i) => {
      const a = (i / 18) * Math.PI * 2 + Math.random() * .3, d = 130 + Math.random() * 140;
      A(s, [{ opacity: 1, transform: "translate(0,0) scale(1)" }, { opacity: 0, transform: `translate(${Math.cos(a) * d}px,${Math.sin(a) * d}px) scale(.2)` }],
        { duration: 900 + Math.random() * 400 });
    });
  });
  at(950, () => {
    $$(".brand-word span").forEach((s, i) => A(s, [{ opacity: 0, transform: "translateY(40px) rotate(12deg)" }, { opacity: 1, transform: "none" }],
      { duration: 600, delay: i * 90, easing: SPRING }));
    A($(".brand-sub"), [{ opacity: 0, letterSpacing: "1.2em" }, { opacity: 1, letterSpacing: ".4em" }], { duration: 900, delay: 200 });
  });
  at(1750, () => {
    A($(".s1"), [{ opacity: 1, transform: "scale(1)", filter: "blur(0)" }, { opacity: 0, transform: "scale(.6)", filter: "blur(8px)" }],
      { duration: 450, easing: IN });
  });

  // ── 2. 키네틱 타이포 (2.3 ~ 4.7s)
  at(2300, () => {
    clear(1);
    const inner = $(".slot-inner");
    const stops = [0, 1, 2, 3, 4, 5].map((n) => ({ transform: `translateY(-${n * 1.2}em)` }));
    A($(".slot"), [{ opacity: 0, transform: "scale(1.4)" }, { opacity: 1, transform: "scale(1)" }], { duration: 300 });
    A(inner, stops.flatMap((s, i) => (i === 0 ? [s] : [{ ...stops[i - 1], offset: i / 6 - .06 }, { ...s, offset: i / 6 }]))
      .concat([{ ...stops[5], offset: 1 }]), { duration: 1700, easing: "linear" });
    const pos = [[-34, -30], [30, -34], [-40, 4], [36, 8], [-28, 32], [26, 34], [-6, -40], [4, 40]];
    $$(".chipfloat").forEach((c, i) => {
      const [x, y] = pos[i];
      A(c, [{ opacity: 0, transform: `translate(${x * .4}vw,${y * .4}vh) scale(.6)` },
        { opacity: 1, transform: `translate(${x}vw,${y}vh) scale(1)`, offset: .35 },
        { opacity: .85, transform: `translate(${x * 1.08}vw,${y * 1.08}vh) scale(1)` }], { duration: 2300, delay: i * 70, easing: "ease-out" });
    });
  });
  at(4200, () => {
    A($(".slot"), [{ transform: "scale(1)", opacity: 1 }, { transform: "scale(1.08)", opacity: 1, offset: .3 }, { transform: "scale(.2)", opacity: 0 }],
      { duration: 500, easing: IN });
    $$(".chipfloat").forEach((c) => A(c, [{}, { opacity: 0, transform: "translate(0,0) scale(.2)" }], { duration: 500, easing: IN }));
  });

  // ── 3. 대화 → 답변 카드 (4.7 ~ 8.0s)
  at(4700, () => {
    clear(1,2);
    A($(".bubble"), [{ opacity: 0, transform: "translateX(60px) scale(.8)" }, { opacity: 1, transform: "none" }], { duration: 450, easing: SPRING });
    const msg = "다음 주 세종 출장 다녀와서 정산해야 해요", el = $(".typed");
    let i = 0;
    const iv = setInterval(() => { el.textContent = msg.slice(0, ++i); if (i >= msg.length) clearInterval(iv); }, 38);
    timers.push(iv);
  });
  at(6000, () => {
    $(".caret").style.display = "none";
    A($(".acard"), [{ opacity: 0, transform: "scale(.3) translateY(-40px)" }, { opacity: 1, transform: "none" }], { duration: 600, easing: SPRING });
    $$(".acard li").forEach((li, i) => {
      A(li, [{ opacity: 0, transform: "translateX(-24px)" }, { opacity: 1, transform: "none" }], { duration: 400, delay: 250 + i * 160 });
      A(li.querySelector("i"), [{ transform: "scale(0) rotate(-90deg)" }, { transform: "scale(1) rotate(0)" }], { duration: 420, delay: 380 + i * 160, easing: SPRING });
    });
    $$(".acard .pill").forEach((p, i) => A(p, [{ opacity: 0, transform: "translateY(12px) scale(.8)" }, { opacity: 1, transform: "none" }],
      { duration: 450, delay: 1000 + i * 130, easing: SPRING }));
  });
  at(7550, () => {
    A($(".stage"), [{ transform: "perspective(900px) rotateY(0)", opacity: 1 }, { transform: "perspective(900px) rotateY(80deg) scale(.9)", opacity: 0 }],
      { duration: 450, easing: IN });
  });

  // ── 4. 서식 자동 작성 (8.0 ~ 10.6s)
  at(8000, () => {
    clear(1,2,3);
    A($(".doc"), [{ opacity: 0, transform: "perspective(900px) rotateY(-80deg) scale(.9)" }, { opacity: 1, transform: "perspective(900px) rotateY(0) scale(1)" }],
      { duration: 600, easing: OUT });
    $$(".doc .row").forEach((r, i) => {
      at(350 + i * 120, () => r.style.setProperty("--line", 1));
      A(r.querySelector("b"), [{ opacity: 0 }, { opacity: 1 }], { duration: 300, delay: 420 + i * 120 });
      const span = r.querySelector("span"), v = span.dataset.v;
      at(900 + i * 230, () => {
        let k = 0;
        const iv = setInterval(() => { span.textContent = v.slice(0, ++k); if (k >= v.length) clearInterval(iv); }, 28);
        timers.push(iv);
      });
    });
  });
  at(9950, () => {
    A($(".stamp"), [{ opacity: 0, transform: "scale(2.6) rotate(-40deg)" }, { opacity: 1, transform: "scale(.92) rotate(-14deg)", offset: .7 },
      { opacity: 1, transform: "scale(1) rotate(-12deg)" }], { duration: 380, easing: IN });
    at(300, () => A($(".doc"), [{ transform: "translate(0,0)" }, { transform: "translate(-4px,3px)" }, { transform: "translate(3px,-2px)" }, { transform: "translate(0,0)" }],
      { duration: 220, easing: "linear", fill: "none" }));
  });
  at(10250, () => A($(".s4"), [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-60px) scale(.85)" }], { duration: 400, easing: IN }));

  // ── 5. 12가지 기능 (10.6 ~ 12.8s)
  at(10650, () => {
    clear(1,2,3,4);
    A($(".count"), [{ opacity: 0, transform: "translateY(20px)" }, { opacity: 1, transform: "none" }], { duration: 500 });
    let n = 0;
    const iv = setInterval(() => { $(".count b").textContent = ++n; if (n >= 12) clearInterval(iv); }, 70);
    timers.push(iv);
    $$(".feat").forEach((f, i) => {
      const a = i * 0.9, d = 340;
      A(f, [{ opacity: 0, transform: `translate(${Math.cos(a) * d}px,${Math.sin(a) * d}px) rotate(${i * 50}deg) scale(.3)` },
        { opacity: 1, transform: "translate(0,0) rotate(0) scale(1)" }], { duration: 800, delay: i * 55, easing: SPRING });
    });
  });
  at(11900, () => $$(".feat i").forEach((f, i) => A(f, [{ background: "rgba(255,255,255,.08)" }, { background: "rgba(205,96,64,.85)", offset: .4 },
    { background: "rgba(255,255,255,.08)" }], { duration: 500, delay: i * 40, easing: "ease" })));

  // ── 6. 엔딩 (12.8 ~ 15s)
  at(12650, () => {
    A($(".s5"), [{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(1.3)" }], { duration: 400, easing: IN });
    A($(".wipe"), [{ transform: "scaleY(0)" }, { transform: "scaleY(1)" }], { duration: 600, easing: "cubic-bezier(.83,0,.17,1)" });
  });
  at(13200, () => {
    clear(1,2,3,4,5);
    A($(".logo-mini"), [{ opacity: 0, transform: "scale(0) rotate(-20deg)" }, { opacity: 1, transform: "none" }], { duration: 600, easing: SPRING });
    $$(".final .ln > span").forEach((s, i) => A(s, [{ transform: "translateY(110%)" }, { transform: "translateY(0)" }], { duration: 750, delay: 180 + i * 160 }));
    A($(".final p"), [{ opacity: 0, transform: "translateY(10px)" }, { opacity: 1, transform: "none" }], { duration: 600, delay: 750 });
    A($(".go"), [{ opacity: 0, transform: "translateY(16px) scale(.9)" }, { opacity: 1, transform: "none" }], { duration: 600, delay: 1000, easing: SPRING });
  });
  at(14600, () => { $(".skip").textContent = "닫기 ✕"; $(".go").focus({ preventScroll: true }); });
}

firstRunReady.then(() => playIntro({ force: new URLSearchParams(location.search).has("intro") }));
