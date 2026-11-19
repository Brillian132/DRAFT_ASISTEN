const { invoke } = window.__TAURI__.core;
const $ = (id) => document.getElementById(id);

const APPS = [
  {
    id: "chrome",
    n: "Chrome",
    i: '<span style="display:block;width:100%;height:100%;border-radius:50%;position:relative;background:conic-gradient(from -60deg,#ea4335 0 120deg,#fbbc05 0 240deg,#34a853 0)"><span style="position:absolute;inset:27%;border-radius:50%;background:#4285f4;border:2px solid #fff"></span></span>',
  },
  {
    id: "steam",
    n: "Steam",
    i: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#1b2838"/><circle cx="15" cy="9.5" r="3" fill="none" stroke="#fff" stroke-width="1.6"/><circle cx="9" cy="15.5" r="2.2" fill="#fff"/><path d="M9.6 14 14 11.5" stroke="#fff" stroke-width="1.4"/></svg>',
  },
  {
    id: "vscode",
    n: "Visual Studio Code",
    i: '<svg viewBox="0 0 24 24"><path fill="#2489ca" d="M17.5 2.5 9 10.3 4.8 7.2 3 8.1v7.8l1.8.9L9 13.7l8.5 7.8 3.5-1.7V4.2z"/><path fill="#0b5a96" opacity=".55" d="M9 10.3 4.8 7.2 3 8.1v7.8l1.8.9L9 13.7z"/></svg>',
  },
  {
    id: "opera",
    n: "Opera",
    i: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#ff1b2d"/><ellipse cx="12" cy="12" rx="3.4" ry="6.4" fill="none" stroke="#fff" stroke-width="2.2"/></svg>',
  },
];

/* ---------- notifikasi kecil ---------- */

let toastTimer;
function toast(title, body) {
  $("tt").textContent = title;
  $("tb").textContent = body;
  $("toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), 3500);
}

/* ---------- ikon aplikasi ---------- */

$("apps").innerHTML = APPS.map(
  (a) => `<button data-id="${a.id}" aria-label="${a.n}" title="${a.n}">${a.i}</button>`
).join("");

$("apps").addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const app = APPS.find((a) => a.id === btn.dataset.id);

  btn.classList.add("on");
  setTimeout(() => btn.classList.remove("on"), 700);

  try {
    await invoke("launch_app", { name: app.id });
  } catch (err) {
    toast("Gagal membuka " + app.n, String(err));
  }
});

$("pw").addEventListener("click", () => toast("Menu daya", "Hadir di tahap 3."));

/* ---------- area yang bisa diklik (sisanya klik tembus) ---------- */

function syncRegions() {
  const d = window.devicePixelRatio || 1;
  const r = $("bar").getBoundingClientRect();
  invoke("set_regions", {
    rects: [{ x: r.left * d, y: r.top * d, w: r.width * d, h: r.height * d }],
  }).catch((e) => console.error("set_regions gagal:", e));
}

addEventListener("resize", syncRegions);
syncRegions();
setTimeout(syncRegions, 500);

/* ---------- jam ---------- */

function clock() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  $("ck").innerHTML = p(d.getHours()) + "<br>" + p(d.getMinutes());
}
clock();
setInterval(clock, 1000);