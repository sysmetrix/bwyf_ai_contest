// 서비 데스크톱 위젯 — 모든 창 위에 떠 있는 서무 비서
// 파이썬 서버(run.py)는 따로 켜져 있어도 되고, 없으면 여기서 함께 띄웁니다.
const { app, BrowserWindow, ipcMain, screen, shell, Tray, Menu, nativeImage } = require("electron");
const path = require("path");
const http = require("http");
const { spawn } = require("child_process");

const ROOT = path.join(__dirname, "..");           // 서비 폴더
const PORT = Number(process.env.SEOBI_PORT || 8000);
const BASE = `http://127.0.0.1:${PORT}`;

// 두 단계뿐입니다: 접힘(캐릭터만) / 큰 화면.
// 중간 크기 패널은 글을 읽기에 좁고 한 번 더 눌러야 해서 없앴습니다.
const SIZE = { idle: { w: 152, h: 168 }, say: { w: 330, h: 214 },
               large: { w: 1040, h: 760 } };
SIZE.open = SIZE.large;        // 예전 호출이 남아 있어도 큰 화면으로 갑니다
const MARGIN = 28;

let win = null;
let tray = null;
let server = null;
let state = "idle";

// ---------- 파이썬 서버 ----------
function ping() {
  return new Promise((resolve) => {
    const req = http.get(`${BASE}/api/orgs`, { timeout: 1500 }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

function pythonPath() {
  // 설치판(함께 들어 있는 파이썬) → 개발용 venv → 시스템 순서로 찾습니다.
  const candidates = process.platform === "win32"
    ? [path.join(ROOT, "python", "python.exe"), path.join(ROOT, ".venv", "Scripts", "python.exe"), "python"]
    : [path.join(ROOT, ".venv", "bin", "python"), "python3"];
  const fs = require("fs");
  for (const p of candidates) {
    if (p === "python" || p === "python3" || fs.existsSync(p)) return p;
  }
  return "python3";
}

async function ensureServer() {
  if (await ping()) return true;                      // 이미 켜져 있음
  server = spawn(pythonPath(), [path.join(ROOT, "run.py"), "--no-browser", "--port", String(PORT)], {
    cwd: ROOT, stdio: "ignore", detached: false,
  });
  server.on("error", (e) => console.error("서버를 띄우지 못했습니다:", e.message));
  for (let i = 0; i < 40; i++) {                      // 최대 20초 기다립니다
    await new Promise((r) => setTimeout(r, 500));
    if (await ping()) return true;
  }
  return false;
}

// ---------- 창 ----------
function place(w, h) {
  const area = screen.getPrimaryDisplay().workArea;
  return { x: Math.round(area.x + area.width - w - MARGIN), y: Math.round(area.y + area.height - h - MARGIN) };
}

// 인트라넷은 브라우저가 아니라 서비 창으로 엽니다. 위젯만으로 끝까지 쓰기 위해서입니다.
let intranetWin = null;
function openIntranet(docNo) {
  // 위젯에서 열 때는 이미 누구인지 아니까 로그인 화면을 거치지 않습니다.
  const who = process.env.SEOBI_USER || "u-kim";
  const q = [`as=${encodeURIComponent(who)}`];
  if (docNo) q.push(`doc=${encodeURIComponent(docNo)}`);
  const url = `${BASE}/intranet/?${q.join("&")}`;
  if (intranetWin && !intranetWin.isDestroyed()) {
    intranetWin.loadURL(url); intranetWin.show(); intranetWin.focus(); return;
  }
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  intranetWin = new BrowserWindow({
    width: Math.min(1280, Math.round(width * 0.92)),
    height: Math.min(860, Math.round(height * 0.92)),
    title: "인트라넷",
    backgroundColor: "#eef2f7",
    show: false,
    webPreferences: { contextIsolation: true },
  });
  intranetWin.loadURL(url);
  showFront(intranetWin);
  intranetWin.on("closed", () => { intranetWin = null; dockBackIfIdle(); });
}

function createWindow() {
  const { w, h } = SIZE.idle;
  const { x } = place(w, h);
  const area = screen.getPrimaryDisplay().workArea;
  const y = Math.round(area.y + area.height - h + 6);     // 처음부터 바닥을 딛고 섭니다

  win = new BrowserWindow({
    width: w, height: h, x, y,
    frame: false,
    transparent: true,
    hasShadow: false,
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    acceptFirstMouse: true,
    backgroundColor: "#00000000",     // 완전 투명. 뒤쪽 화면이 그대로 비쳐야 합니다.
    roundedCorners: false,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false },
  });

  // 전체화면 앱 위에까지 띄웁니다
  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  win.loadURL(`${BASE}/home.html?shell=desktop`);

  // 인트라넷은 서비 창으로, 그 밖의 바깥 주소만 기본 브라우저로 보냅니다.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(BASE)) { openIntranet(); return { action: "deny" }; }
    shell.openExternal(url);
    return { action: "deny" };
  });

  // 다른 앱이 앞으로 와도 서비는 맨 앞을 유지합니다
  const keepOnTop = () => {
    if (!win || win.isDestroyed()) return;
    if (!win.isAlwaysOnTop()) win.setAlwaysOnTop(true, "screen-saver");
  };
  win.on("blur", keepOnTop);
  win.on("show", keepOnTop);
  setInterval(keepOnTop, 3000);

  win.on("closed", () => { win = null; });
}

// 상태 전환.
// idle·open 은 바탕화면 구석에 붙는 위젯이라 오른쪽 아래 모서리를 기준으로 커집니다.
// large 는 보통 창처럼 가운데에 뜨고, 크기를 바꿀 수 있으며 항상 위에서 내려옵니다.
function setState(next) {
  if (!win || next === state) return;
  stopWalk();                          // 펼치거나 접는 동안에는 멈춥니다
  interactive = true;
  win.setIgnoreMouseEvents(false);     // 전환 중에는 항상 받도록 되돌립니다
  const prev = state;
  state = next;
  const { w, h } = SIZE[next];

  if (next === "large") {
    win.setResizable(true);
    win.setMinimumSize(620, 520);
    // 큰 창에서도 서비는 항상 맨 앞에 있습니다
    win.setAlwaysOnTop(true, "screen-saver");
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    if (process.platform === "darwin" && app.dock) app.dock.show();
    win.setSkipTaskbar(false);
    // 모니터 비율에 맞춰 잡습니다. 고정값으로 두면 작은 노트북에서는 넘치고
    // 큰 모니터에서는 허전합니다. 아래위로 숨 쉴 여백을 남깁니다.
    const area = screen.getPrimaryDisplay().workArea;
    const fw = clamp(Math.round(area.width * 0.58), 620, 1100);
    const fh = clamp(Math.round(area.height * 0.78), 520, 860);
    win.setSize(fw, fh, false);
    win.setPosition(
      Math.round(area.x + (area.width - fw) / 2),
      Math.round(area.y + (area.height - fh) / 2),
    );
    win.focus();
    return;
  }

  // 위젯으로 돌아오기: 큰 창에서 바꿔 놓은 것들을 전부 되돌립니다.
  // 하나라도 남으면 투명 창에 흰 배경이 남는 것처럼 보입니다.
  if (prev === "large") {
    win.setBackgroundColor("#00000000");
    if (process.platform === "darwin" && app.dock) app.dock.hide();
  }
  win.setResizable(false);
  win.setMinimumSize(1, 1);
  win.setSkipTaskbar(true);
  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  if (process.platform === "darwin" && app.dock) app.dock.hide();

  if (prev === "large") {                       // 큰 창에서 내려올 때는 구석으로 돌려보냅니다
    const { x, y } = place(w, h);
    win.setBounds({ x, y, width: w, height: h }, false);
  } else {
    const b = win.getBounds();
    const right = b.x + b.width, bottom = b.y + b.height;
    win.setBounds({ x: Math.round(right - w), y: Math.round(bottom - h), width: w, height: h }, false);
  }
}

ipcMain.on("seobi:state", (_e, next) => setState(next === "idle" ? "idle" : "large"));
ipcMain.on("seobi:hide", () => win && win.hide());

// 창은 네모지만 캐릭터는 동그랗습니다. 빈 구석에서는 클릭이 뒤쪽 앱으로 지나가야
// 바탕화면에 늘 띄워 둘 수 있습니다. forward:true 라야 통과 중에도 마우스 이동이
// 화면으로 전달돼서 다시 캐릭터 위로 왔을 때 되돌릴 수 있습니다.
let interactive = true;
ipcMain.on("seobi:interactive", (_e, on) => {
  if (!win || win.isDestroyed() || on === interactive) return;
  interactive = on;
  win.setIgnoreMouseEvents(!on, { forward: true });
});

// 창 밖에서도 마우스를 따라보게: 화면 전체 커서를 훑어 캐릭터 기준 방향을 보냅니다.
// 위젯(접힘·펼침)일 때만 돌리고, 큰 창에서는 창 안의 mousemove로 충분해 멈춥니다.
let cursorTimer = null;
function startCursorWatch() {
  clearInterval(cursorTimer);
  cursorTimer = setInterval(() => {
    if (!win || win.isDestroyed() || !win.isVisible() || state === "large") return;
    try {
      const pt = screen.getCursorScreenPoint();
      const b = win.getBounds();
      const cx = b.x + b.width / 2, cy = b.y + b.height * 0.42;
      const dx = (pt.x - cx) / 420, dy = (pt.y - cy) / 360;
      const near = Math.abs(pt.x - cx) < 320 && Math.abs(pt.y - cy) < 280;
      win.webContents.send("seobi:cursor", { dx, dy, near });
    } catch { /* 화면 구성이 바뀌는 순간은 건너뜁니다 */ }
  }, 120);
}
ipcMain.on("seobi:quit", () => app.quit());
ipcMain.handle("seobi:info", () => ({ base: BASE, platform: process.platform }));

// ---------- 돌아다니기 ----------
// 창 자체를 조금씩 옮겨서 캐릭터가 바탕화면을 걸어다니게 합니다.
// 접혀 있고, 사람이 끌고 있지 않고, 일하고 있지 않을 때만 움직입니다.
let roamOn = true;
let walking = null;     // 걷는 중 타이머
let roamTimer = null;

function stopWalk() {
  if (walking) { clearInterval(walking); walking = null; }
  if (win && !win.isDestroyed()) win.webContents.send("seobi:walk", { walking: false, dir: 0 });
}

function walkTo(tx, ty, pxPerSec = 46, done) {
  if (!win || win.isDestroyed()) return;
  stopWalk();
  const step = 33;                                   // 30fps 정도면 충분히 부드럽습니다
  const b = win.getBounds();
  const dir = tx === b.x ? 0 : (tx > b.x ? 1 : -1);
  win.webContents.send("seobi:walk", { walking: true, dir });

  walking = setInterval(() => {
    if (!win || win.isDestroyed() || state !== "idle" || !win.isVisible()) return stopWalk();
    const c = win.getBounds();
    const dx = tx - c.x, dy = ty - c.y;
    const dist = Math.hypot(dx, dy);
    const move = (pxPerSec * step) / 1000;
    if (dist <= move) {
      win.setPosition(Math.round(tx), Math.round(ty));
      stopWalk(); done && done(); return;
    }
    // 높이는 바닥선으로 천천히만 맞춥니다(사람이 위로 끌어 둔 경우 걸어 내려옵니다)
    const ny = Math.abs(dy) < 1 ? c.y : c.y + Math.sign(dy) * Math.min(Math.abs(dy), move * 0.45);
    win.setPosition(Math.round(c.x + Math.sign(dx) * Math.min(Math.abs(dx), move)), Math.round(ny));
  }, step);
}

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// 바닥선: 캐릭터가 발을 딛는 높이. 작업 영역 맨 아래에 세워 둡니다.
function floorY() {
  const area = screen.getPrimaryDisplay().workArea;
  return Math.round(area.y + area.height - SIZE.idle.h + 6);
}

function roamOnce() {
  if (!roamOn || !win || win.isDestroyed() || state !== "idle" || !win.isVisible() || walking) return;
  const area = screen.getPrimaryDisplay().workArea;
  const { w } = SIZE.idle;
  // 바닥을 따라 좌우로만 걷습니다. Y 를 흔들면 날아다니는 것처럼 보여요.
  const minX = area.x + 10, maxX = area.x + area.width - w - 10;
  const cur = win.getBounds().x;
  let tx;
  let tries = 0;
  do {                                   // 너무 짧은 걸음은 어색해서 조금 떨어진 곳을 고릅니다
    tx = minX + Math.random() * Math.max(1, maxX - minX);
  } while (Math.abs(tx - cur) < 180 && ++tries < 6);
  walkTo(tx, floorY(), 34 + Math.random() * 26);
}

function scheduleRoam() {
  clearTimeout(roamTimer);
  roamTimer = setTimeout(() => { roamOnce(); scheduleRoam(); }, 18000 + Math.random() * 42000);
}

ipcMain.on("seobi:roam", (_e, on) => {
  roamOn = !!on;
  if (!roamOn) stopWalk();
});

// ---------- 트레이 ----------
ipcMain.on("seobi:intranet", (_e, docNo) => openIntranet(docNo));

// 맥에서는 독을 숨겨 두는데, 그 상태로는 새 창이 앞으로 나오지 못합니다.
// 창을 띄우는 동안만 독을 보이게 했다가, 창을 닫으면 다시 숨깁니다.
function showFront(w) {
  if (process.platform === "darwin" && app.dock) app.dock.show();
  w.once("ready-to-show", () => { w.show(); w.focus(); w.moveTop(); });
  w.show(); w.focus();
}

function dockBackIfIdle() {
  if (process.platform !== "darwin" || !app.dock) return;
  const open = [setupWin, intranetWin].some((w) => w && !w.isDestroyed() && w.isVisible());
  if (!open && state === "idle") app.dock.hide();
}

// ---------- 처음 설정 ----------
// 처음 켜면 캐릭터 대신 설정 창이 먼저 뜹니다. 주소·아이디·비밀번호를 받아
// 서비가 그 시스템을 스스로 읽고 맞추게 하기 위해서입니다.
let setupWin = null;

function needsSetup() {
  // ping 과 같은 방식(http.get)을 씁니다. fetch 는 일렉트론 판에 따라 없을 수 있어,
  // 없으면 조용히 실패해서 설정 창이 안 뜨는 일이 생깁니다.
  return new Promise((resolve) => {
    const req = http.get(`${BASE}/api/setup/state`, { timeout: 4000 }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (c) => { body += c; });
      res.on("end", () => {
        try { resolve(!!JSON.parse(body)["처음인가"]); }
        catch (e) { console.error("설정 상태를 읽지 못했습니다:", e.message); resolve(false); }
      });
    });
    req.on("error", (e) => { console.error("설정 상태 확인 실패:", e.message); resolve(false); });
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

function openSetup() {
  if (setupWin && !setupWin.isDestroyed()) { setupWin.show(); setupWin.focus(); return; }
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  setupWin = new BrowserWindow({
    width: Math.min(820, Math.round(width * 0.9)),
    height: Math.min(760, Math.round(height * 0.9)),
    title: "서비 처음 설정",
    backgroundColor: "#f4f6f8",
    show: false,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true },
  });
  setupWin.loadURL(`${BASE}/setup.html`);
  showFront(setupWin);
  setupWin.on("closed", () => { setupWin = null; dockBackIfIdle(); });
}

ipcMain.on("seobi:setup-done", () => {
  if (setupWin && !setupWin.isDestroyed()) setupWin.close();
  dockBackIfIdle();
  if (win) { win.show(); win.focus(); }
  setTimeout(() => say("설정이 끝났어요. 무엇이든 물어보세요", 6000, { come: false }), 600);
});


// ---------- 마우스 쪽으로 걸어오기 ----------
// 사람이 부르면(트레이 '이리 와') 또는 알릴 일이 있을 때, 지금 마우스가 있는
// 자리 가까이로 걸어갑니다. 커서를 덮지 않도록 조금 옆·아래에 섭니다.
function walkToCursor(done) {
  if (!win || win.isDestroyed() || state !== "idle") { done && done(); return; }
  try {
    const pt = screen.getCursorScreenPoint();
    const area = screen.getPrimaryDisplay().workArea;
    const b = win.getBounds();
    // 커서 왼쪽·아래에 서게 합니다. 화면 왼쪽 끝이면 오른쪽에 섭니다.
    const wantRight = pt.x - area.x < b.width + 60;
    const tx = clamp(wantRight ? pt.x + 40 : pt.x - b.width - 40,
                     area.x + 8, area.x + area.width - b.width - 8);
    const ty = clamp(pt.y - Math.round(b.height * 0.55),
                     area.y + 8, area.y + area.height - b.height - 8);
    walkTo(tx, ty, 150, done);          // 부를 때는 빠르게 옵니다
  } catch { done && done(); }
}


// ---------- 말풍선 ----------
// 역할에 따라 알릴 일이 생기면 캐릭터가 직접 말합니다.
let sayTimer = null;
function say(text, ms = 7000, { come = true } = {}) {
  if (!win || win.isDestroyed() || !text) return;
  const show = () => {
    if (state !== "idle") return;                 // 큰 창일 때는 화면 안에서 봅니다
    const b = win.getBounds();
    const cx = b.x + b.width / 2, bottom = b.y + b.height;
    const { w, h } = SIZE.say;
    const area = screen.getPrimaryDisplay().workArea;
    win.setBounds({
      x: Math.round(clamp(cx - w / 2, area.x + 4, area.x + area.width - w - 4)),
      y: Math.round(clamp(bottom - h, area.y + 4, area.y + area.height - h - 4)),
      width: w, height: h,
    }, false);
    win.webContents.send("seobi:say", { text });
    clearTimeout(sayTimer);
    sayTimer = setTimeout(hush, ms);
  };
  come ? walkToCursor(show) : show();
}

function hush() {
  clearTimeout(sayTimer);
  if (!win || win.isDestroyed() || state !== "idle") return;
  win.webContents.send("seobi:say", { text: "" });
  const b = win.getBounds();
  const cx = b.x + b.width / 2, bottom = b.y + b.height;
  const { w, h } = SIZE.idle;
  win.setBounds({ x: Math.round(cx - w / 2), y: Math.round(bottom - h),
                  width: w, height: h }, false);
}

ipcMain.on("seobi:say", (_e, text) => say(String(text || ""), 7000));
ipcMain.on("seobi:hush", () => hush());
ipcMain.on("seobi:come", () => walkToCursor());


function createTray() {
  // 템플릿 이미지로 두면 알파만 써서 검은 덩어리로 보일 수 있어, 컬러 아이콘 그대로 씁니다.
  const img = nativeImage.createFromPath(path.join(ROOT, "web", "seobi-512.png")).resize({ width: 18, height: 18 });
  tray = new Tray(img);
  tray.setToolTip("서비 — 서무 비서");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "서비 보이기", click: () => { if (win) { win.show(); win.focus(); } } },
    { label: "열기", click: () => { if (win) { win.show(); win.webContents.send("seobi:go", "large"); } } },
    { label: "숨기기", click: () => win && win.hide() },
    { type: "separator" },
    { label: "혼자 돌아다니기", type: "checkbox", checked: roamOn,
      click: (item) => { roamOn = item.checked; if (!roamOn) stopWalk(); } },
    { label: "이리 와", click: () => walkToCursor() },
    { label: "지금 산책", click: () => roamOnce() },
    { type: "separator" },
    { label: "인트라넷 열기", click: () => openIntranet() },
    { label: "처음 설정 다시", click: () => openSetup() },
    { type: "separator" },
    { label: "종료", click: () => app.quit() },
  ]));
  tray.on("click", () => { if (!win) return; win.isVisible() ? win.hide() : (win.show(), win.focus()); });
}

// ---------- 생명주기 ----------
// 두 번째로 실행하면 새 창을 띄우지 않고, 이미 떠 있는 서비에게 명령만 전달합니다.
//   electron . --walk     지금 산책
//   electron . --open     패널 펼치기
//   electron . --large    크게 보기
// 네트워크 포트를 열지 않고 명령을 넘기기 위한 Electron 표준 방식입니다.
function handleArgs(argv) {
  if (!win || win.isDestroyed()) return;
  if (argv.includes("--walk")) { win.show(); setState("idle"); roamOnce(); }
  if (argv.includes("--open")) { win.show(); win.webContents.send("seobi:go", "open"); }
  if (argv.includes("--large")) { win.show(); win.webContents.send("seobi:go", "large"); }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", (_e, argv) => handleArgs(argv));
}

app.whenReady().then(async () => {
  if (process.platform === "darwin" && app.dock) app.dock.hide();  // 독에는 띄우지 않습니다
  await ensureServer();
  createWindow();
  createTray();

  // 처음 켜는 PC 면 설정 창을 먼저 띄웁니다. 두 번째부터는 캐릭터만 나옵니다.
  if (await needsSetup()) {
    if (win) win.hide();
    openSetup();
  }
  startCursorWatch();
  scheduleRoam();
  handleArgs(process.argv);
});

app.on("window-all-closed", () => { /* 트레이로 계속 살아 있습니다 */ });
app.on("activate", () => { if (!win) createWindow(); else win.show(); });
app.on("before-quit", () => { if (server && !server.killed) server.kill(); });
