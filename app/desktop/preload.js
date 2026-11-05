// 화면(home.js)과 창(main.js) 사이의 좁은 통로. 필요한 것만 열어 둡니다.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("seobiShell", {
  open: () => ipcRenderer.send("seobi:state", "open"),
  large: () => ipcRenderer.send("seobi:state", "large"),
  collapse: () => ipcRenderer.send("seobi:state", "idle"),
  hide: () => ipcRenderer.send("seobi:hide"),
  quit: () => ipcRenderer.send("seobi:quit"),
  info: () => ipcRenderer.invoke("seobi:info"),
  // 트레이 메뉴 등 창 쪽에서 보내는 전환 요청
  onGo: (fn) => ipcRenderer.on("seobi:go", (_e, which) => fn(which)),
  // 창 밖 화면 전체의 마우스 위치(캐릭터 기준 방향)를 받아 시선을 돌립니다
  onCursor: (fn) => ipcRenderer.on("seobi:cursor", (_e, p) => fn(p)),
  // 투명한 빈 영역에서는 클릭이 뒤쪽 앱으로 통과하게 합니다
  setInteractive: (on) => ipcRenderer.send("seobi:interactive", !!on),
  // 걷는 중인지, 어느 쪽으로 가는지
  onWalk: (fn) => ipcRenderer.on("seobi:walk", (_e, p) => fn(p)),
  setRoam: (on) => ipcRenderer.send("seobi:roam", !!on),
});
