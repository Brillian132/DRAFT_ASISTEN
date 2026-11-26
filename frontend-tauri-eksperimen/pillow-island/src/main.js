const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

// Penanda versi: ketik window.versiTampilan di Console untuk memastikan main.js terbaru yang terbaca
window.versiTampilan = "media-halaman-2+paket-a";
console.log("[Pillow Island] main.js versi", window.versiTampilan);

const pill = document.getElementById("pill");
const $ = (id) => document.getElementById(id);

const PAUSE = '<path d="M6 5h4v14H6zM14 5h4v14h-4z"/>';
const PLAY = '<path d="M7 5v14l12-7z"/>';
const DEFAULT_COVER = "linear-gradient(135deg, #a78bfa, #4c1d95 70%)";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

const SIZES = {
  hidden: { w: 156, h: 56 },
  small: { w: 156, h: 56 },
  media: { w: 652, h: 192 },
  timer: { w: 372, h: 108 },
  add: { w: 452, h: 192 },
  reminder: { w: 442, h: 132 },
  card: { w: 452, h: 144 },
  toast: { w: 294, h: 72 },
  power: { w: 336, h: 92 },
  dokumen: { w: 492, h: 140 },
};

/* ---------- penyimpanan ---------- */
function load(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; } }
function save(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
function loadJSON(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; } }
function saveJSON(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {} }

let idle = load("idle_mode", "pinned");
let anchor = load("anchor", "center");
let monitorMode = load("monitor_mode", "primary");
let lastMon = -1;
let settings = { fs_hide: true, cover_accent: true };
let fsHidden = false;

/* ---------- state & ukuran jendela ---------- */
let state = "small";
let cur = { w: 0, h: 0 };
let shrinkTimer = null;
let collapseTimer = null;

const idleState = () => (idle === "pinned" ? "small" : idle);

function isClickable(s) {
  if (s === "hidden") return false;
  if (s === "small" && idle === "small") return false;
  return true;
}

function applyClickthrough() {
  invoke("set_clickthrough", { ignore: fsHidden || !isClickable(state) }).catch((e) => console.error("set_clickthrough gagal:", e));
}

async function resize(w, h) {
  if (cur.w === w && cur.h === h) return;
  cur = { w, h };
  try { await invoke("resize_island", { width: w, height: h, anchor, monitor: monitorMode }); } catch (e) { console.error("resize gagal:", e); }
}

async function reposition() {
  cur = { w: 0, h: 0 };
  await resize(SIZES[state].w, SIZES[state].h);
}

async function setState(next) {
  clearTimeout(shrinkTimer);
  const sebelumnya = state;
  const t = SIZES[next];
  await resize(Math.max(cur.w, t.w), Math.max(cur.h, t.h));
  state = next;
  if (next === "media" && sebelumnya !== "media") resetHalaman();   // selalu mulai dari halaman Media
  pill.dataset.state = next;
  pill.classList.toggle("passive", !isClickable(next));
  applyClickthrough();
  shrinkTimer = setTimeout(() => resize(t.w, t.h), 650);
}

const goIdle = () => setState(idleState());

function armCollapse(ms) {
  clearTimeout(collapseTimer);
  if (idle === "pinned") return;
  collapseTimer = setTimeout(() => {
    if ((state === "media" || state === "timer") && !sedangMengetik()) goIdle();
  }, ms);
}

pill.addEventListener("mouseenter", () => { clearTimeout(collapseTimer); clearTimeout(kartuTimer); });
pill.addEventListener("mouseleave", () => {
  armCollapse(2500);
  if (kartu && kartu.tipe === "status") kartuTimer = setTimeout(tutupKartu, 2000);
});

pill.addEventListener("click", (e) => {
  if (blokirKlik) return;                                               // klik yang menyusul setelah menggeser halaman
  if (state === "media" && e.target.closest("button, input")) return;   // tombol dan kolom isian mengurus dirinya sendiri
  clearTimeout(collapseTimer);
  if (state === "small" && idle === "pinned") setState(timer ? "timer" : "media");
  else if (state === "media") { if (halaman === 0 && !sedangMengetik()) goIdle(); }   // halaman lain: tutup dengan Esc atau pintasan
  else if (state === "timer") goIdle();
  else if (state === "card" && kartu && kartu.tipe === "status") tutupKartu();
  else if (sedangToast()) tutupToast();
});

const stop = (id, fn) =>
  $(id).addEventListener("click", (e) => {
    e.stopPropagation();
    fn();
  });

/* ---------- hotkey & menu tray ---------- */
listen("toggle-island", () => {
  if (idle === "pinned") setState(state === "small" ? "media" : "small");
  else if (state === "hidden" || state === "small") { setState("media"); armCollapse(6000); }
  else goIdle();
});

listen("set-idle", (e) => { idle = e.payload; save("idle_mode", idle); clearTimeout(collapseTimer); goIdle(); });
listen("set-anchor", async (e) => { anchor = e.payload; save("anchor", anchor); await reposition(); });
listen("set-monitor", async (e) => {
  if (e.payload === "next") {
    let count = 1;
    try { count = await invoke("monitor_count"); } catch (err) {}
    const idx = monitorMode.startsWith("fixed:") ? parseInt(monitorMode.slice(6), 10) : -1;
    monitorMode = "fixed:" + ((idx + 1) % Math.max(count, 1));
  } else { monitorMode = e.payload; }
  save("monitor_mode", monitorMode);
  lastMon = -1;
  await reposition();
});

setInterval(async () => {
  if (monitorMode !== "cursor" || state === "add" || state === "reminder") return;
  try {
    const i = await invoke("cursor_monitor");
    if (i !== lastMon) { lastMon = i; await reposition(); }
  } catch (err) {}
}, 800);

listen("fullscreen", (e) => { fsHidden = !!e.payload; pill.classList.toggle("fs-hidden", fsHidden); applyClickthrough(); });
listen("settings-changed", (e) => { settings = e.payload; applyAccent(); });

/* ---------- warna aksen dari cover album ---------- */
let lastCover = null;
function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  let h = 0, s = 0;
  if (d > 0) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
  }
  return [h, s, l];
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function extractAccent(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const S = 24;
        const c = document.createElement("canvas");
        c.width = S; c.height = S;
        const ctx = c.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(img, 0, 0, S, S);
        const px = ctx.getImageData(0, 0, S, S).data;
        const buckets = Array.from({ length: 12 }, () => ({ w: 0, h: 0, s: 0, l: 0 }));
        for (let i = 0; i < px.length; i += 4) {
          if (px[i + 3] < 128) continue;
          const [h, s, l] = rgbToHsl(px[i], px[i + 1], px[i + 2]);
          if (s < 0.25 || l < 0.15 || l > 0.88) continue;
          const w = s * (1 - Math.abs(2 * l - 1));
          const b = buckets[Math.floor(h / 30) % 12];
          b.w += w; b.h += h * w; b.s += s * w; b.l += l * w;
        }
        const best = buckets.reduce((a, b) => (b.w > a.w ? b : a));
        if (best.w < 2) return resolve(null);
        const h = Math.round(best.h / best.w);
        const s = Math.round(clamp(best.s / best.w, 0.55, 0.9) * 100);
        const l = clamp(best.l / best.w, 0.45, 0.58);
        const l2 = Math.round(clamp(l + 0.22, 0.65, 0.82) * 100);
        const lp = Math.round(l * 100);
        resolve({
          accent: `hsl(${h}, ${s}%, ${lp}%)`,
          accent2: `hsl(${h}, ${s}%, ${l2}%)`,
          glow: `hsla(${h}, ${s}%, ${lp}%, 0.7)`,
          glow0: `hsla(${h}, ${s}%, ${lp}%, 0)`,
          stroke: `hsla(${h}, ${s}%, ${l2}%, 0.65)`,
        });
      } catch (e) { resolve(null); }
    };
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

function setAccent(c) {
  const root = document.documentElement.style;
  const map = { "--accent": "accent", "--accent2": "accent2", "--glow": "glow", "--glow0": "glow0", "--stroke": "stroke" };
  for (const [prop, key] of Object.entries(map)) {
    if (c) root.setProperty(prop, c[key]);
    else root.removeProperty(prop);
  }
}

async function applyAccent() {
  if (!settings.cover_accent || !lastCover) return setAccent(null);
  setAccent(await extractAccent(lastCover));
}

/* ---------- media ---------- */
let mediaActive = false, playing = false, basePos = 0, baseAt = performance.now(), duration = 0, lastKey = "";

/* ---------- jam pemutaran ---------- */
// Browser sering melaporkan posisi lagu ke Windows hanya saat lagu mulai, dijeda, atau digeser,
// bukan terus-menerus. Jadi posisi diperkirakan sendiri: jam berjalan selama lagu diputar, dan
// hanya disesuaikan kalau posisi dari Windows memang berubah (artinya pemutar memperbaruinya).
let jamKunci = "";
let jamPosisiTerakhir = null;

function selaraskanJam(m) {
  const sekarang = performance.now();
  const kunci = m.title + "|" + m.artist;
  const estimasi = basePos + (playing ? sekarang - baseAt : 0);   // perkiraan dari jam sendiri (sebelum diubah)
  const p = m.position_ms || 0;

  if (kunci !== jamKunci) {                 // lagu baru: percaya posisi dari Windows
    jamKunci = kunci;
    basePos = p;
    jamPosisiTerakhir = p;
  } else if (p !== jamPosisiTerakhir) {     // Windows melaporkan posisi baru (diperbarui atau digeser)
    basePos = p;
    jamPosisiTerakhir = p;
  } else {                                  // posisi tidak berubah: lanjutkan jam sendiri
    basePos = estimasi;
  }
  if (m.duration_ms > 0) basePos = Math.min(basePos, m.duration_ms);
  baseAt = sekarang;
  playing = m.playing;
}

// Alat bantu diagnosa: ketik debugMedia() di Console, putar lagu, lalu lihat angka mentah dari Windows selama 8 detik
window.debugMedia = async () => {
  for (let i = 0; i < 8; i++) {
    try {
      const m = await invoke("get_media");
      console.log(`#${i + 1}`, "posisi_ms:", m.position_ms, "| durasi_ms:", m.duration_ms, "| diputar:", m.playing,
        "| jam pill:", Math.round(basePos + (playing ? performance.now() - baseAt : 0)));
    } catch (e) { console.log("get_media gagal:", e); }
    await new Promise((r) => setTimeout(r, 1000));
  }
};

async function loadCover() {
  let url = null;
  try { url = await invoke("get_media_thumbnail"); } catch (e) {}
  lastCover = url || null;
  const bg = url ? `url("${url}")` : DEFAULT_COVER;
  $("cover").style.backgroundImage = bg;
  await applyAccent();
}

function announce() {
  if (idle === "pinned") return;
  if (state !== "hidden" && state !== "small") return;
  setState("media");
  armCollapse(4000);
}

async function pollMedia() {
  try {
    const m = await invoke("get_media");
    mediaActive = m.active; duration = m.duration_ms;
    selaraskanJam(m);   // memperbarui basePos, baseAt, dan playing
    $("ppi").innerHTML = playing ? PAUSE : PLAY;
    if (m.active) {
      $("m-title").textContent = m.title || "Tanpa judul";
      artistTeks = m.artist || "Sedang diputar";
      perbaruiTampilanLirik(true);   // kolom kanan: lirik, atau nama artis kalau liriknya tidak ada
    } else {
      $("m-title").textContent = "Putar lagu untuk mulai";
      artistTeks = "Tidak ada media";
      $("cover").style.backgroundImage = DEFAULT_COVER;
      if (lastCover) { lastCover = null; setAccent(null); }
      resetLirik();
      perbaruiTampilanLirik(true);
    }
    const key = m.title + "|" + m.artist;
    if (key !== lastKey) {
      lastKey = key;
      if (m.active) { muatLirik(m); await loadCover(); announce(); }
    }
  } catch (e) { console.error("get_media gagal:", e); }
}

async function control(action) {
  try { await invoke("media_control", { action }); } catch (e) { console.error("media_control gagal:", e); }
  setTimeout(pollMedia, 300);
}

stop("pp", () => control("play_pause"));
stop("prev", () => control("prev"));
stop("next", () => control("next"));

setInterval(() => {
  if (!mediaActive || duration <= 0) { $("mp").style.width = "0%"; return; }
  const pos = basePos + (playing ? performance.now() - baseAt : 0);
  $("mp").style.width = Math.min(100, (pos / duration) * 100) + "%";
}, 250);

setInterval(pollMedia, 1000);

/* ---------- timer & pengingat ---------- */
let timer = loadJSON("timer", null);
let reminders = loadJSON("reminders", []);
let pending = [];
let alertNow = null;

const pad = (n) => String(n).padStart(2, "0");
const hhmm = (d) => pad(d.getHours()) + ":" + pad(d.getMinutes());

function fmt(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function fmtWhen(ts) {
  const d = new Date(ts);
  const now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate());
  const diff = Math.round((day(d) - day(now)) / 86400000);
  if (diff === 0) return hhmm(d);
  if (diff === 1) return "Besok " + hhmm(d);
  return d.getDate() + " " + MONTHS[d.getMonth()] + " " + hhmm(d);
}

function timerRemaining() { return timer ? (timer.paused ? timer.remaining : Math.max(0, timer.end - Date.now())) : 0; }

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.2].forEach((t) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = 880; g.gain.value = 0.08;
      o.connect(g); g.connect(ctx.destination);
      o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.12);
    });
    setTimeout(() => ctx.close(), 900);
  } catch (e) {}
}

function startTimer(minutes, label) {
  const total = minutes * 60000;
  timer = { total, end: Date.now() + total, label: label || "", paused: false, remaining: total };
  saveJSON("timer", timer);
  $("tpi").innerHTML = PAUSE;
  setState("timer");
}

stop("tp", () => {
  if (!timer) return;
  if (timer.paused) { timer.end = Date.now() + timer.remaining; timer.paused = false; }
  else { timer.remaining = Math.max(0, timer.end - Date.now()); timer.paused = true; }
  saveJSON("timer", timer);
  $("tpi").innerHTML = timer.paused ? PLAY : PAUSE;
});

stop("tc", () => { timer = null; saveJSON("timer", null); goIdle(); });

function showNext() {
  if (alertNow || !pending.length || state === "add") return;
  alertNow = pending.shift();
  if (alertNow.kind === "reminder") {
    const r = reminders.find((x) => x.id === alertNow.id);
    if (!r) { alertNow = null; showNext(); return; }
    $("al-kind").textContent = "Pengingat";
    $("al-title").textContent = r.text;
    $("al-sub").textContent = "Pukul " + hhmm(new Date(r.at));
    $("snooze").textContent = "Tunda 10 menit";
  } else {
    $("al-kind").textContent = "Timer selesai";
    $("al-title").textContent = alertNow.label || "Waktu habis";
    $("al-sub").textContent = Math.round(alertNow.total / 60000) + " menit";
    $("snooze").textContent = "+5 menit";
  }
  setState("reminder");
  kirimWA(`${$("al-kind").textContent}: ${$("al-title").textContent}`);   // teruskan ke WhatsApp
  beep();
}

function closeAlert() { alertNow = null; if (pending.length) showNext(); else goIdle(); }

stop("done", () => {
  if (alertNow && alertNow.kind === "reminder") {
    const id = alertNow.id;
    reminders = reminders.filter((r) => r.id !== id);
    saveJSON("reminders", reminders);
  }
  closeAlert();
});

stop("snooze", () => {
  if (!alertNow) return;
  if (alertNow.kind === "reminder") {
    const r = reminders.find((x) => x.id === alertNow.id);
    if (r) { r.at = Date.now() + 10 * 60000; r.fired = false; saveJSON("reminders", reminders); }
    closeAlert();
  } else {
    const label = alertNow.label;
    alertNow = null;
    startTimer(5, label);
  }
});

let mode = "timer";

function updateCount() {
  const n = reminders.length;
  $("seg-list").textContent = n ? `Daftar (${n})` : "Daftar";
}

function removeReminder(id) {
  reminders = reminders.filter((r) => r.id !== id);
  saveJSON("reminders", reminders);
  updateCount();
  renderList();
  renderDaftarPengingat();
  perbaruiPengingatBerikut();
}

function renderList() {
  const box = $("f-list");
  box.replaceChildren();
  const items = [...reminders].sort((a, b) => a.at - b.at);
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "rem-empty"; empty.textContent = "Belum ada pengingat";
    box.appendChild(empty); return;
  }
  for (const r of items) {
    const row = document.createElement("div");
    row.className = "rem-item" + (r.fired ? " past" : "");
    const txt = document.createElement("span"); txt.className = "txt"; txt.textContent = r.text;
    const when = document.createElement("span"); when.className = "when"; when.textContent = fmtWhen(r.at);
    const del = document.createElement("button");
    del.setAttribute("aria-label", "Hapus pengingat");
    del.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19 12 13.4 17.6 19 19 17.6 13.4 12 19 6.4 17.6 5 12 10.6z"/></svg>';
    del.addEventListener("click", (e) => { e.stopPropagation(); removeReminder(r.id); });
    row.append(txt, when, del); box.appendChild(row);
  }
}

function setMode(m) {
  mode = m;
  $("seg-timer").classList.toggle("on", m === "timer");
  $("seg-rem").classList.toggle("on", m === "rem");
  $("seg-list").classList.toggle("on", m === "list");
  $("f-timer").classList.toggle("hidden", m !== "timer");
  $("f-rem").classList.toggle("hidden", m !== "rem");
  $("f-list").classList.toggle("hidden", m !== "list");
  $("add-acts").classList.toggle("hidden", m === "list");
  $("add-ok").textContent = m === "timer" ? "Mulai" : "Simpan";
  if (m === "list") renderList();
  else setTimeout(() => $(m === "timer" ? "t-min" : "r-text").focus(), 50);
}

function openAdd() {
  const d = new Date(Date.now() + 60 * 60000);
  $("r-time").value = hhmm(d);
  updateCount(); setState("add"); setMode(mode);
}

function flagBad(el) { el.classList.add("bad"); setTimeout(() => el.classList.remove("bad"), 900); }

function submitAdd() {
  if (mode === "timer") {
    const minutes = parseInt($("t-min").value, 10);
    if (!minutes || minutes < 1 || minutes > 999) return flagBad($("t-min"));
    startTimer(minutes, $("t-label").value.trim()); $("t-label").value = "";
  } else if (mode === "rem") {
    const value = $("r-time").value;
    if (!value) return flagBad($("r-time"));
    const [hh, mm] = value.split(":").map(Number);
    const at = new Date(); at.setHours(hh, mm, 0, 0);
    if (at.getTime() <= Date.now()) at.setDate(at.getDate() + 1);
    reminders.push({ id: Date.now(), text: $("r-text").value.trim() || "Pengingat", at: at.getTime(), fired: false });
    saveJSON("reminders", reminders); $("r-text").value = ""; goIdle();
  }
}

stop("seg-timer", () => setMode("timer"));
stop("seg-rem", () => setMode("rem"));
stop("seg-list", () => setMode("list"));
stop("add-ok", submitAdd);
stop("add-cancel", goIdle);

window.addEventListener("keydown", (e) => {
  if (state !== "add") return;
  if (e.key === "Enter" && mode !== "list") submitAdd();
  if (e.key === "Escape") goIdle();
});

function tick() {
  const now = new Date();
  pill.classList.toggle("has-timer", !!timer);
  if (timer) {
    const rem = timerRemaining();
    $("clk").textContent = (timer.paused ? "⏸ " : "") + fmt(rem);
    $("tm").textContent = fmt(rem);
    $("tl").textContent = timer.label || "Timer fokus";
    $("rg").style.strokeDashoffset = 144.5 * (1 - rem / timer.total);
    if (!timer.paused && rem <= 0) {
      pending.push({ kind: "timer", label: timer.label, total: timer.total });
      timer = null; saveJSON("timer", null);
    }
  } else { $("clk").textContent = hhmm(now); }

  let changed = false;
  for (const r of reminders) {
    if (!r.fired && r.at <= now.getTime()) { r.fired = true; changed = true; pending.push({ kind: "reminder", id: r.id }); }
  }
  if (changed) saveJSON("reminders", reminders);
  showNext();
}

setInterval(tick, 250);

/* =========================================
   --- INTEGRASI ASISTEN PYTHON & MATA AI ---
   ========================================= */
const PY_BASE = "http://127.0.0.1:8008";
// Token acak per sesi: diteruskan ke server Python lewat variabel lingkungan sidecar
// dan disertakan di setiap permintaan (header X-Pillow-Token).
const PY_TOKEN = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
function pyFetch(url, opts = {}) {
  return fetch(url, { ...opts, headers: { ...(opts.headers || {}), "X-Pillow-Token": PY_TOKEN } });
}
let pythonChild = null;
const tidurMs = (ms) => new Promise((r) => setTimeout(r, ms));

async function tungguServer(maks = 60) {
  for (let i = 0; i < maks; i++) {
    try {
      const ctrl = new AbortController();
      const batas = setTimeout(() => ctrl.abort(), 3000);
      let r;
      try { r = await pyFetch(`${PY_BASE}/health`, { signal: ctrl.signal }); }
      finally { clearTimeout(batas); }
      if (r.ok) return true;
    } catch (_) {}
    await tidurMs(500);
  }
  return false;
}

async function startPythonServer() {
  nyalakanSuaraOtomatis(); // berjalan sendiri di latar belakang, mencoba sampai server siap
  try {
    const { Command } = window.__TAURI__.shell;
    const command = Command.sidecar("binaries/asisten-server", [], { env: { PILLOW_TOKEN: PY_TOKEN } });
    const logPy = (l) => { if (!String(l).includes("/status")) console.log("[py]", l); };
    command.stdout.on("data", logPy);
    command.stderr.on("data", logPy);
    command.on("error", (e) => console.error("[py error]", e));
    command.on("close", (d) => console.warn("[py] berhenti:", d));
    pythonChild = await command.spawn();
    console.log("Sidecar di-spawn, pid:", pythonChild.pid);
    const siap = await tungguServer();
    console.log(siap ? "Server Python siap di port 8008" : "Server Python GAGAL siap, lihat log [py]");
  } catch (error) {
    console.error("Gagal menjalankan sidecar:", error);
  }
}

// Warna mata sekarang dikendalikan oleh status dari Python (lihat pollStatusAsisten).
// Fungsi ini hanya mengirim perintah dan mengembalikan jawabannya.
async function kirimPerintah(teks) {
  try {
    const response = await pyFetch(`${PY_BASE}/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ perintah: teks }),
    });
    const data = await response.json();
    console.log("Respon dari Python:", data.message);

    const statusTeks = document.getElementById("status-teks");
    if (statusTeks) statusTeks.innerText = data.message;

    return data.message;
  } catch (error) {
    console.error("Gagal menghubungi Python:", error);
    return "Gagal menghubungi Python.";
  }
}

/* ---------- mata AI mengikuti status dari Python ---------- */
// Python melaporkan: "listening" (mikrofon aktif), "thinking" (memproses), atau "idle".
// Mata hanya berubah kalau pill sedang dalam keadaan kecil (small),
// supaya tampilan media, timer, dan pengingat tidak terganggu.
/* ---------- kartu: izin & hasil perintah ---------- */
// Prioritas tampilan: pengingat/timer selesai > kartu izin > kartu hasil > media.
// Kartu izin dan hasil tidak muncul saat form tambah timer terbuka;
// kartu hasil juga tidak muncul saat pengingat tampil.
let kartu = null;            // { tipe: "izin" | "status", id }
let kartuPrev = "small";     // tampilan sebelum kartu, untuk dikembalikan
let kartuTimer = null;
let moodTimer = null;
let izinDijawab = null;      // id izin yang baru dijawab (mencegah kartu muncul lagi sesaat)
let hasilTerakhir = null;

const LABEL_NADA = { ok: "Selesai", warn: "Butuh izin", bad: "Ada masalah", info: "Info" };
const MOOD_NADA = { ok: "happy", warn: "surprised", bad: "worried", info: "" };

// ekspresi mata: "happy", "surprised", "worried", atau "" untuk normal
function setMood(m) {
  clearTimeout(moodTimer);
  if (m) pill.dataset.mood = m; else delete pill.dataset.mood;
}
function lepasMood(ms) {
  clearTimeout(moodTimer);
  moodTimer = setTimeout(() => delete pill.dataset.mood, ms);
}

function bukaKartu(tipe, id, nada, teks, hint) {
  clearTimeout(kartuTimer);
  if (state !== "card") kartuPrev = sedangToast() ? toastPrev : state;
  if (toastAktif) { clearTimeout(toastTimer); toastAktif = false; batalPower(); } // kartu lebih penting daripada toast
  kartu = { tipe, id };
  pill.dataset.tone = nada;
  pill.dataset.kartu = tipe;
  $("kt-label").textContent = LABEL_NADA[nada] || "Info";
  $("kt-text").textContent = teks;
  $("kt-hint").classList.toggle("hidden", !hint);
  $("kt-izin").classList.toggle("hidden", tipe !== "izin");
  setMood(MOOD_NADA[nada] || "");
  setState("card");
}

function tutupKartu() {
  clearTimeout(kartuTimer);
  if (!kartu) return;
  kartu = null;
  lepasMood(1200);
  if (state === "card") setState(kartuPrev && kartuPrev !== "card" ? kartuPrev : idleState());
}

function tampilKartuStatus(nada, teks) {
  if (dokumenAktif) return;   // hasil pencarian dokumen sedang tampil
  if (state === "add" || state === "reminder") return;
  if (kartu && kartu.tipe === "izin") return; // izin lebih penting
  bukaKartu("status", null, nada === "bad" ? "bad" : "ok", teks || "Selesai.", false);
  const ms = Math.min(9000, Math.max(3500, (teks || "").length * 70));
  kartuTimer = setTimeout(tutupKartu, ms);
}

function tampilKartuIzin(izin) {
  if (state === "add" || state === "reminder") return; // tunggu sampai selesai
  bukaKartu("izin", izin.id, "warn", izin.teks, izin.suara);
}

async function jawabIzin(jawab) {
  if (!kartu || kartu.tipe !== "izin") return;
  const id = kartu.id;
  izinDijawab = id;
  tutupKartu();
  try {
    await pyFetch(`${PY_BASE}/izin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, jawab }),
    });
  } catch (e) { console.error("Gagal mengirim jawaban izin:", e); }
}

stop("kt-tolak", () => jawabIzin("tolak"));
stop("kt-izinkan", () => jawabIzin("izinkan"));
stop("kt-selalu", () => jawabIzin("selalu"));

/* ---------- kejadian dari Python (timer, pengingat, kartu) ---------- */
// Server Python menaruh perintah untuk tampilan di antrean; /status?sejak=<id> mengembalikan yang baru.
let kejadianTerakhir = null;   // null = belum pernah membaca (kejadian lama diabaikan saat aplikasi dibuka)

function jalankanKejadian(k) {
  const d = k.data || {};
  try {
    if (k.jenis === "timer") {
      const menit = Number(d.menit);
      if (menit > 0 && menit <= 999) startTimer(menit, String(d.label || "").slice(0, 30));
    } else if (k.jenis === "timer_aksi" && timer) {
      if (d.aksi === "batal") { timer = null; saveJSON("timer", null); if (state === "timer") goIdle(); }
      else if (d.aksi === "jeda" && !timer.paused) $("tp").click();
      else if (d.aksi === "lanjut" && timer.paused) $("tp").click();
    } else if (k.jenis === "pengingat") {
      const at = Number(d.at);
      if (at > 0) {
        reminders.push({ id: Date.now() + Math.floor(Math.random() * 1000), text: String(d.teks || "Pengingat").slice(0, 60), at, fired: false });
        saveJSON("reminders", reminders);
        updateCount();
        perbaruiPengingatBerikut();
        if (halaman === 2) renderDaftarPengingat();
      }
    } else if (k.jenis === "kartu") {
      tampilKartuStatus(d.nada === "bad" ? "bad" : "ok", String(d.teks || ""));
    } else if (k.jenis === "dokumen") {
      tampilDokumen(d);
    }
  } catch (e) { console.error("Kejadian dari Python gagal dijalankan:", k, e); }
}

function prosesKejadian(s) {
  if (typeof s.kejadian_id !== "number") return;
  if (kejadianTerakhir === null || s.kejadian_id < kejadianTerakhir) {
    kejadianTerakhir = s.kejadian_id;     // pertama kali, atau server dimulai ulang
    return;
  }
  if (s.kejadian && s.kejadian.length) {
    kejadianTerakhir = s.kejadian_id;
    s.kejadian.forEach(jalankanKejadian);
  }
}

// Dipanggil tiap polling /status: menampilkan kartu izin dan kartu hasil dari Python
function prosesStatus(s) {
  prosesKejadian(s);
  // 1. kartu izin
  if (s.izin) {
    const sudahTampil = kartu && kartu.tipe === "izin" && kartu.id === s.izin.id && state === "card";
    if (!sudahTampil && s.izin.id !== izinDijawab) tampilKartuIzin(s.izin);
  } else if (kartu && kartu.tipe === "izin") {
    tutupKartu(); // sudah dijawab lewat suara, atau waktu habis
  }

  // 2. kartu hasil (hijau / merah)
  const h = s.hasil;
  if (h) {
    if (hasilTerakhir === null) hasilTerakhir = h.seq;       // abaikan hasil lama saat aplikasi baru dibuka
    else if (h.seq !== hasilTerakhir) {
      hasilTerakhir = h.seq;
      tampilKartuStatus(h.nada, h.teks);
    }
  }
}

// Menghapus semua jawaban "Selalu izinkan". Ketik resetIzin() di Console.
window.resetIzin = async () => {
  try { await pyFetch(`${PY_BASE}/izin/reset`, { method: "POST" }); console.log("Izin 'Selalu' dihapus"); }
  catch (e) { console.error(e); }
};

let aiOverride = false;
let gagalBeruntun = 0;

async function pollStatusAsisten() {
  // Satu permintaan pada satu waktu, dengan batas waktu 2 detik,
  // supaya tidak menumpuk kalau server sedang sibuk atau mati.
  const ctrl = new AbortController();
  const batas = setTimeout(() => ctrl.abort(), 2000);
  try {
    const r = await pyFetch(`${PY_BASE}/status` + (kejadianTerakhir === null ? "" : "?sejak=" + kejadianTerakhir), { signal: ctrl.signal });
    if (!r.ok) throw new Error("status " + r.status);
    const s = await r.json();
    gagalBeruntun = 0;
    prosesStatus(s);
    const ui = s.ui;
    const mauTampil = (ui === "listening" || ui === "thinking") && state === "small";
    if (mauTampil) {
      if (pill.dataset.state !== ui) pill.dataset.state = ui;
      aiOverride = true;
    } else if (aiOverride) {
      pill.dataset.state = state; // kembali ke tampilan semula
      aiOverride = false;
    }
  } catch (_) {
    gagalBeruntun++; // server belum siap atau sibuk
  } finally {
    clearTimeout(batas);
  }
}

// Ulangi tiap 0,3 detik; kalau terus gagal, melambat sampai maksimal 5 detik.
(async function loopStatus() {
  while (true) {
    await pollStatusAsisten();
    await tidurMs(Math.min(300 * (1 + gagalBeruntun), 5000));
  }
})();

/* ---------- kontrol mode suara ---------- */
async function mulaiSuara() {
  try { await pyFetch(`${PY_BASE}/suara/mulai`, { method: "POST" }); } catch (e) { console.error(e); }
}
async function hentikanModeSuara() {
  try { await pyFetch(`${PY_BASE}/suara/berhenti`, { method: "POST" }); } catch (e) { console.error(e); }
}
window.mulaiSuara = mulaiSuara;
window.hentikanModeSuara = hentikanModeSuara;

// Dipanggil otomatis saat aplikasi dibuka: mencoba menyalakan mode suara tiap 1 detik
// (maksimal 90 kali) sampai server Python menjawab.
async function nyalakanSuaraOtomatis() {
  for (let i = 0; i < 90; i++) {
    const ctrl = new AbortController();
    const batas = setTimeout(() => ctrl.abort(), 3000);
    try {
      const r = await pyFetch(`${PY_BASE}/suara/mulai`, { method: "POST", signal: ctrl.signal });
      if (r.ok) { console.log("Mode suara menyala otomatis"); return; }
    } catch (_) {
      // server belum siap, coba lagi
    } finally {
      clearTimeout(batas);
    }
    await tidurMs(1000);
  }
  console.warn("Mode suara otomatis gagal menyala. Ketik mulaiSuara() secara manual.");
}

async function hentikanSuara() {
  try { await pyFetch(`${PY_BASE}/stop`, { method: "POST" }); } catch (e) {}
}

// Dua baris ini yang sebelumnya hilang:
window.kirimPerintah = kirimPerintah;
window.hentikanSuara = hentikanSuara;
startPythonServer();

/* ---------- notifikasi singkat (toast): charger, Bluetooth, mikrofon/kamera ---------- */
// Toast muncul 3 detik lalu pill kembali ke tampilan sebelumnya.
// Toast tidak muncul saat form tambah, pengingat, atau kartu sedang tampil;
// kalau pill sedang sibuk, toast antre (maksimal 3) dan muncul begitu pill kosong.
const IKON = {
  bolt: "M11 21h-1l1-7H7.5c-.58 0-.57-.32-.38-.66.19-.34.05-.08.07-.12C8.48 10.94 10.42 7.54 13 3h1l-1 7h3.5c.49 0 .56.33.47.51l-.07.15C12.96 17.55 11 21 11 21z",
  baterai: "M15.67 4H14V2h-4v2H8.33C7.6 4 7 4.6 7 5.33v15.33C7 21.4 7.6 22 8.33 22h7.33c.74 0 1.34-.6 1.34-1.33V5.33C17 4.6 16.4 4 15.67 4z",
  headset: "M12 3a9 9 0 0 0-9 9v7c0 1.1.9 2 2 2h4v-8H5v-1c0-3.87 3.13-7 7-7s7 3.13 7 7v1h-4v8h4c1.1 0 2-.9 2-2v-7a9 9 0 0 0-9-9z",
  bt: "M17.71 7.71L12 2h-1v7.59L6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 11 14.41V22h1l5.71-5.71-4.3-4.29 4.3-4.29zM13 5.83l1.88 1.88L13 9.59V5.83zm1.88 10.46L13 18.17v-3.76l1.88 1.88z",
  mic: "M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z",
  cam: "M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z",
  note: "M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z",
};

let toastAktif = false;
let toastTimer = null;
let toastPrev = "small";
const antrianToast = [];

const toastBolehTampil = () => !toastAktif && ["small", "hidden", "media", "timer"].includes(state);

// t: { ikon, teks, sub?, nilai?, nada?, ms?, pulse? }
function tampilToast(t) {
  if (!toastBolehTampil()) {
    if (antrianToast.length < 3) antrianToast.push({ ...t, at: Date.now() });
    return;
  }
  toastAktif = true;
  clearTimeout(toastTimer);
  toastPrev = state;
  pill.dataset.tone = t.nada || "info";

  if (t.power) {
    // animasi charger: colokan menyatu / cincin persen
    siapkanPower(t);
    setState("power").then(() => {
      // beri waktu pill selesai melebar sebelum animasi dimulai
      powerT.push(setTimeout(() => { if (toastAktif && state === "power") mulaiAnimasiPower(t); }, 180));
    });
  } else {
    $("ts-path").setAttribute("d", IKON[t.ikon] || "");
    $("ts-text").textContent = t.teks;
    $("ts-sub").textContent = t.sub || "";
    $("ts-sub").classList.toggle("hidden", !t.sub);
    $("ts-val").textContent = t.nilai || "";
    $("ts-ic").classList.toggle("pulse", !!t.pulse);
    setState("toast");
  }
  toastTimer = setTimeout(tutupToast, t.ms || 3000);
}

const sedangToast = () => state === "toast" || state === "power";

function tutupToast() {
  clearTimeout(toastTimer);
  if (!toastAktif) return;
  toastAktif = false;
  batalPower();
  if (sedangToast()) setState(toastPrev && toastPrev !== "toast" && toastPrev !== "power" ? toastPrev : idleState());
}

/* ---------- animasi charger ---------- */
let powerRaf = null;
let powerT = [];   // semua timer animasi charger, supaya bisa dibatalkan sekaligus

function batalPower() {
  cancelAnimationFrame(powerRaf);
  powerT.forEach(clearTimeout);
  powerT = [];
  pill.removeAttribute("data-power");
}

// isi teks dan ikon sesuai mode: "plug" (dicolok), "unplug" (dicabut), "low" (baterai rendah)
function siapkanPower(p) {
  batalPower();
  const teks = {
    plug:   ["Mengisi daya",    "Charger terpasang"],
    unplug: ["Charger dicabut", "Memakai baterai"],
    low:    ["Baterai rendah",  "Hubungkan charger"],
  }[p.mode] || ["Daya", ""];
  $("pw-title").textContent = teks[0];
  $("pw-sub").textContent = teks[1];
  $("pw-ic").setAttribute("d", p.mode === "low" ? IKON.baterai : IKON.bolt);
  $("pw-val").textContent = (p.mode === "plug" ? 0 : p.percent) + "%";
}

function mulaiAnimasiPower(p) {
  batalPower();
  const ring = $("pw-ring-fg");
  const pct = Math.max(0, Math.min(100, p.percent));

  // cincin dimulai dari kosong (colok) atau langsung penuh sesuai persen (cabut / rendah), tanpa transisi
  ring.style.transition = "none";
  ring.style.setProperty("--pw", p.mode === "plug" ? "0" : String(pct / 100));
  void ring.getBoundingClientRect();
  ring.style.transition = "";
  $("pw-val").textContent = (p.mode === "plug" ? 0 : pct) + "%";

  void pill.offsetWidth;            // paksa browser memulai animasi CSS dari awal
  pill.dataset.power = p.mode;

  if (p.mode === "plug") {
    // setelah colokan menyatu (0,95 detik): cincin terisi dan angka menghitung naik
    powerT.push(setTimeout(() => {
      ring.style.setProperty("--pw", String(pct / 100));
      const mulai = performance.now();
      const durasi = 1000;
      const langkah = (t) => {
        const k = Math.min(1, (t - mulai) / durasi);
        const lembut = 1 - Math.pow(1 - k, 3);
        $("pw-val").textContent = Math.round(pct * lembut) + "%";
        if (k < 1) powerRaf = requestAnimationFrame(langkah);
      };
      powerRaf = requestAnimationFrame(langkah);
    }, 950));
  }
}

// Toast yang menunggu antrean dicoba lagi tiap 0,7 detik; yang sudah lebih dari 8 detik dibuang
setInterval(() => {
  while (antrianToast.length && Date.now() - antrianToast[0].at > 8000) antrianToast.shift();
  if (antrianToast.length && toastBolehTampil()) tampilToast(antrianToast.shift());
}, 700);

// charger dicolok / dicabut / baterai rendah (dari Rust)
listen("power", (e) => {
  const p = e.payload;
  const persen = Number(p.percent) || 0;
  if (p.kind === "plug") {
    tampilToast({ power: true, mode: "plug", percent: persen, nada: "ok", ms: 3800 });
  } else if (p.kind === "unplug") {
    tampilToast({ power: true, mode: "unplug", percent: persen, nada: "info", ms: 3300 });
  } else if (p.kind === "low") {
    tampilToast({ power: true, mode: "low", percent: persen, nada: "bad", ms: 4500 });
    kirimWA("Baterai rendah: " + persen + "%. Hubungkan charger.");
  }
});

// perangkat Bluetooth baru tersambung (dari Rust)
const POLA_HEADSET = /buds|pods|head(phone|set)|ear(phone|bud)?s?\b|wh-|wf-|jbl|bose|tws|airdopes|soundcore|enco|tune|live\s?\d/i;
listen("bluetooth", (e) => {
  const nama = (e.payload && e.payload.name) || "Perangkat Bluetooth";
  tampilToast({ ikon: POLA_HEADSET.test(nama) ? "headset" : "bt", teks: nama, sub: "Tersambung", nada: "ok" });
});

// aplikasi lain memakai mikrofon / kamera (dari Rust): titik indikator + toast saat mulai dipakai
let privasiAwal = true;
let privasiLama = { mic: [], cam: [] };
listen("privasi", (e) => {
  const p = e.payload || { mic: [], cam: [] };
  const mic = $("ind-mic"), cam = $("ind-cam");
  mic.classList.toggle("hidden", p.mic.length === 0);
  cam.classList.toggle("hidden", p.cam.length === 0);
  mic.title = p.mic.length ? "Mikrofon dipakai: " + p.mic.join(", ") : "";
  cam.title = p.cam.length ? "Kamera dipakai: " + p.cam.join(", ") : "";

  if (!privasiAwal) { // saat aplikasi baru dibuka, yang sudah aktif tidak perlu diumumkan
    const baruCam = p.cam.filter((n) => !privasiLama.cam.includes(n));
    const baruMic = p.mic.filter((n) => !privasiLama.mic.includes(n));
    if (baruCam.length) tampilToast({ ikon: "cam", teks: "Kamera dipakai", sub: baruCam.join(", "), nada: "ok" });
    else if (baruMic.length) tampilToast({ ikon: "mic", teks: "Mikrofon dipakai", sub: baruMic.join(", "), nada: "warn" });
  }
  privasiAwal = false;
  privasiLama = p;
});

/* ---------- halaman slider di tampilan media: Media, Timer, Pengingat ---------- */
// Geser dengan mouse (seret ke kiri/kanan), roda mouse horizontal, titik di bawah, atau tombol panah.
// Esc menutup tampilan media. Halaman selalu mulai dari Media saat tampilan dibuka.
const HALAMAN = 3;
let halaman = 0;
let blokirKlik = false;
let geser = { aktif: false, x0: 0, dx: 0, bergerak: false };
let menitPilihan = 25;

const sedangMengetik = () => {
  const a = document.activeElement;
  return !!a && a.tagName === "INPUT" && pill.contains(a);
};

function pergiKe(i) {
  halaman = Math.max(0, Math.min(HALAMAN - 1, i));
  $("pg-track").style.transform = `translateX(${(-halaman * 100) / HALAMAN}%)`;
  document.querySelectorAll(".pg-dot").forEach((d, k) => d.classList.toggle("on", k === halaman));
  if (halaman === 1) perbaruiHalamanTimer();
  if (halaman === 2) {
    if (!$("pg-r-time").value) $("pg-r-time").value = hhmm(new Date(Date.now() + 60 * 60000));
    renderDaftarPengingat();
  }
}

function resetHalaman() {
  const trek = $("pg-track");
  trek.style.transition = "none";   // kembali ke halaman pertama tanpa efek meluncur
  pergiKe(0);
  void trek.offsetWidth;
  trek.style.transition = "";
}

/* --- halaman Timer --- */
function pilihMenit(m) {
  menitPilihan = m;
  $("pg-t-min").value = String(m);
  perbaruiHalamanTimer();
}

function perbaruiHalamanTimer() {
  const m = parseInt($("pg-t-min").value, 10);
  const valid = m >= 1 && m <= 999;
  $("pt-time").textContent = fmt((valid ? m : menitPilihan) * 60000);
  document.querySelectorAll(".pt-preset").forEach((b) => b.classList.toggle("on", valid && Number(b.dataset.min) === m));
  perbaruiPengingatBerikut();
}

function mulaiTimerHalaman() {
  const menit = parseInt($("pg-t-min").value, 10);
  if (!menit || menit < 1 || menit > 999) return flagBad($("pg-t-min"));
  startTimer(menit, "");   // timer berjalan tampil di tampilan timer seperti biasa
}

/* --- pengingat (kolom kanan halaman Timer dan seluruh halaman Pengingat) --- */
function pengingatMendatang() {
  return [...reminders].filter((r) => !r.fired).sort((a, b) => a.at - b.at);
}

function perbaruiPengingatBerikut() {
  const r = pengingatMendatang()[0];
  $("pt-next-time").textContent = r ? fmtWhen(r.at) : "Belum ada";
  $("pt-next-text").textContent = r ? r.text : "Tambah di halaman Pengingat";
}

function renderDaftarPengingat() {
  const kotak = $("pg-r-list");
  kotak.replaceChildren();
  const items = pengingatMendatang();

  const judul = document.createElement("small");
  judul.textContent = items.length ? `Terjadwal (${items.length})` : "Terjadwal";
  kotak.appendChild(judul);

  if (!items.length) {
    const kosong = document.createElement("div");
    kosong.className = "rem-empty";
    kosong.textContent = "Belum ada pengingat";
    kotak.appendChild(kosong);
    return;
  }
  for (const r of items.slice(0, 3)) {
    const baris = document.createElement("div");
    baris.className = "rem-item";
    const txt = document.createElement("span"); txt.className = "txt"; txt.textContent = r.text;
    const kapan = document.createElement("span"); kapan.className = "when"; kapan.textContent = fmtWhen(r.at);
    const hapus = document.createElement("button");
    hapus.setAttribute("aria-label", "Hapus pengingat");
    hapus.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19 12 13.4 17.6 19 19 17.6 13.4 12 19 6.4 17.6 5 12 10.6z"/></svg>';
    hapus.addEventListener("click", (e) => { e.stopPropagation(); removeReminder(r.id); });
    baris.append(txt, kapan, hapus);
    kotak.appendChild(baris);
  }
  if (items.length > 3) {
    const lagi = document.createElement("small");
    lagi.textContent = `+${items.length - 3} lagi`;
    kotak.appendChild(lagi);
  }
}

function simpanPengingatHalaman() {
  const nilai = $("pg-r-time").value;
  if (!nilai) return flagBad($("pg-r-time"));
  const [hh, mm] = nilai.split(":").map(Number);
  const at = new Date();
  at.setHours(hh, mm, 0, 0);
  if (at.getTime() <= Date.now()) at.setDate(at.getDate() + 1);   // jam yang sudah lewat = besok
  reminders.push({ id: Date.now(), text: $("pg-r-text").value.trim() || "Pengingat", at: at.getTime(), fired: false });
  saveJSON("reminders", reminders);
  $("pg-r-text").value = "";
  updateCount();
  renderDaftarPengingat();
  perbaruiPengingatBerikut();
}

/* --- pemasangan kontrol --- */
document.querySelectorAll(".pg-dot").forEach((d) =>
  d.addEventListener("click", (e) => { e.stopPropagation(); pergiKe(Number(d.dataset.i)); }));
document.querySelectorAll(".pt-preset").forEach((b) =>
  b.addEventListener("click", (e) => { e.stopPropagation(); pilihMenit(Number(b.dataset.min)); }));
stop("pg-t-go", mulaiTimerHalaman);
stop("pg-r-go", simpanPengingatHalaman);
$("pg-t-min").addEventListener("input", perbaruiHalamanTimer);
$("pg-t-min").addEventListener("keydown", (e) => { if (e.key === "Enter") mulaiTimerHalaman(); });
$("pg-r-text").addEventListener("keydown", (e) => { if (e.key === "Enter") simpanPengingatHalaman(); });
$("pg-r-time").addEventListener("keydown", (e) => { if (e.key === "Enter") simpanPengingatHalaman(); });

// seret ke kiri/kanan untuk berpindah halaman
const pgWrap = $("pg-wrap");
pgWrap.addEventListener("pointerdown", (e) => {
  if (state !== "media" || e.button !== 0 || e.target.closest("button, input")) return;
  geser = { aktif: true, x0: e.clientX, dx: 0, bergerak: false };
  pgWrap.setPointerCapture(e.pointerId);
});
pgWrap.addEventListener("pointermove", (e) => {
  if (!geser.aktif) return;
  geser.dx = e.clientX - geser.x0;
  if (Math.abs(geser.dx) > 6) geser.bergerak = true;
  if (!geser.bergerak) return;
  let dx = geser.dx;
  if ((halaman === 0 && dx > 0) || (halaman === HALAMAN - 1 && dx < 0)) dx *= 0.3;   // tertahan di ujung
  const trek = $("pg-track");
  trek.style.transition = "none";
  trek.style.transform = `translateX(calc(${(-halaman * 100) / HALAMAN}% + ${dx}px))`;
});
function akhiriGeser() {
  if (!geser.aktif) return;
  const { dx, bergerak } = geser;
  geser.aktif = false;
  $("pg-track").style.transition = "";
  if (bergerak) {
    blokirKlik = true;                         // jangan anggap seretan sebagai klik penutup
    setTimeout(() => { blokirKlik = false; }, 120);
    pergiKe(halaman + (dx < -60 ? 1 : dx > 60 ? -1 : 0));
  }
}
pgWrap.addEventListener("pointerup", akhiriGeser);
pgWrap.addEventListener("pointercancel", akhiriGeser);

// roda mouse horizontal (atau Shift + roda)
let rodaTerakhir = 0;
pill.addEventListener("wheel", (e) => {
  if (state !== "media") return;
  const sisi = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : (e.shiftKey ? e.deltaY : 0);
  if (Math.abs(sisi) < 20 || Date.now() - rodaTerakhir < 450) return;
  rodaTerakhir = Date.now();
  pergiKe(halaman + (sisi > 0 ? 1 : -1));
}, { passive: true });

// tombol panah berpindah halaman, Esc menutup
window.addEventListener("keydown", (e) => {
  if (state !== "media") return;
  if (e.key === "Escape") { goIdle(); return; }
  if (sedangMengetik()) return;
  if (e.key === "ArrowRight") pergiKe(halaman + 1);
  if (e.key === "ArrowLeft") pergiKe(halaman - 1);
});

perbaruiPengingatBerikut();

/* ---------- lirik lagu ---------- */
// Lirik diambil server Python dari LRCLIB dan disimpan di cache. Tiap baris: [waktu_ms, teks].
// Lirik tampil di kolom kanan halaman Media. Tombol lirik mengganti mode: besar -> satu baris -> mati.
let artistTeks = "Tidak ada media";
let lirik = { key: "", status: "kosong", baris: [], idx: -2, cur: "" };  // status: kosong | memuat | ada | tidak
// "besar" = baris sekarang + berikutnya, "satu" = baris sekarang saja, "mati" = tanpa lirik
let lirikMode = load("lirik_mode", "besar");
let lirikOffset = 0;                              // geser waktu (ms), tersimpan per lagu

const posisiLagu = () => basePos + (playing ? performance.now() - baseAt : 0);

// indeks baris terakhir yang waktunya sudah lewat (pencarian biner), -1 kalau belum ada
function indeksLirik(ms) {
  const b = lirik.baris;
  let lo = 0, hi = b.length - 1, hasil = -1;
  while (lo <= hi) {
    const tengah = (lo + hi) >> 1;
    if (b[tengah][0] <= ms) { hasil = tengah; lo = tengah + 1; } else { hi = tengah - 1; }
  }
  return hasil;
}

// ganti teks dengan efek naik halus
function setTeksGanti(el, teks) {
  if (el.textContent === teks) return;
  el.textContent = teks;
  el.classList.remove("lirik-ganti");
  void el.offsetWidth;
  el.classList.add("lirik-ganti");
}

// lencana not musik di cover: tampil kalau liriknya ada, terang kalau mode lirik tidak mati
function perbaruiBadge() {
  const b = $("cv-badge");
  b.classList.toggle("hidden", lirik.status !== "ada");
  b.classList.toggle("on", lirikMode !== "mati");
}

// Kolom kanan di halaman Media: lirik (mode besar / satu baris), atau nama artis + keterangan kalau tidak ada lirik
function perbaruiKolomMedia(cur, berikut) {
  const kini = $("m-lyr-now"), nanti = $("m-lyr-next");
  if (lirik.status === "ada" && lirikMode !== "mati") {
    setTeksGanti(kini, cur || "♪");   // jeda instrumental ditandai not musik
    setTeksGanti(nanti, lirikMode === "besar" ? berikut : "");
  } else {
    kini.textContent = artistTeks;
    nanti.textContent = lirikMode === "mati" ? "Lirik dimatikan"
      : lirik.status === "memuat" ? "Mencari lirik…"
      : lirik.status === "tidak" ? "Lirik tidak tersedia" : "";
  }
}

function perbaruiTampilanLirik(paksa) {
  perbaruiBadge();
  if (lirik.status !== "ada") {
    lirik.cur = "";
    lirik.idx = -2;
    perbaruiKolomMedia("", "");
    return;
  }
  // +120 ms: lirik sedikit didahulukan karena mata membaca lebih lambat daripada telinga mendengar
  const idx = indeksLirik(posisiLagu() + lirikOffset + 120);
  if (idx === lirik.idx && !paksa) return;
  lirik.idx = idx;

  const cur = idx >= 0 ? lirik.baris[idx][1] : "";
  const berikut = lirik.baris[idx + 1] ? lirik.baris[idx + 1][1] : "";
  lirik.cur = cur;
  perbaruiKolomMedia(cur, berikut);
}

function resetLirik() {
  if (lirik.status === "kosong" && !lirik.key) return;
  lirik = { key: "", status: "kosong", baris: [], idx: -2, cur: "" };
  lirikOffset = 0;
  perbaruiTampilanLirik(true);
}

// dipanggil saat lagu berganti
async function muatLirik(m) {
  const detik = Math.round((m.duration_ms || 0) / 1000);
  const key = `${m.artist || ""}|${m.title || ""}|${detik}`;
  if (lirik.key === key) return;

  lirik = { key, status: "memuat", baris: [], idx: -2, cur: "" };
  lirikOffset = Number(load("lirik_off:" + key, "0")) || 0;
  perbaruiTampilanLirik(true);

  const ctrl = new AbortController();
  const batas = setTimeout(() => ctrl.abort(), 18000);
  try {
    const url = `${PY_BASE}/lirik?` + new URLSearchParams({ judul: m.title || "", artis: m.artist || "", durasi: detik });
    const r = await pyFetch(url, { signal: ctrl.signal });
    const d = await r.json();
    if (lirik.key !== key) return;                 // lagu sudah berganti, abaikan
    if (d.ok && d.baris && d.baris.length) { lirik.baris = d.baris; lirik.status = "ada"; }
    else { lirik.status = "tidak"; }
  } catch (_) {
    if (lirik.key === key) lirik.status = "tidak";
  } finally {
    clearTimeout(batas);
  }
  if (lirik.key === key) perbaruiTampilanLirik(true);
}

// tombol lirik di halaman Media: besar -> satu baris -> mati -> besar ...
function gantiLirikMode() {
  const urutan = ["besar", "satu", "mati"];
  lirikMode = urutan[(urutan.indexOf(lirikMode) + 1) % urutan.length];
  save("lirik_mode", lirikMode);
  perbaruiTombolLirik();
  perbaruiTampilanLirik(true);
}

function perbaruiTombolLirik() {
  const b = $("lyr");
  const nama = { besar: "Lirik: besar", satu: "Lirik: satu baris", mati: "Lirik: mati" }[lirikMode] || "Lirik";
  b.classList.toggle("off", lirikMode === "mati");
  b.title = nama + " (klik untuk mengganti)";
  b.setAttribute("aria-label", nama);
}

// geser waktu lirik (ms), tersimpan per lagu
function geserLirik(ms) {
  lirikOffset += ms;
  save("lirik_off:" + lirik.key, String(lirikOffset));
  perbaruiTampilanLirik(true);
}

stop("lyr", gantiLirikMode);
perbaruiTombolLirik();
window.lirikGeser = (detik) => geserLirik(detik * 1000);   // contoh di Console: lirikGeser(-1)

// Diagnosa: ketik lirikStatus() di Console untuk melihat keadaan lirik
window.lirikStatus = () => ({
  statusLirik: lirik.status,          // ada = lirik ditemukan, tidak = tidak ditemukan, memuat = sedang dicari
  jumlahBaris: lirik.baris.length,
  modeLirik: lirikMode,               // besar | satu | mati
  geserWaktu_ms: lirikOffset,
  lagiDiputar: playing,
  jamPill_ms: Math.round(posisiLagu()),
});

setInterval(() => perbaruiTampilanLirik(false), 150);

/* ---------- mata hidup: melirik kanan-kiri dan berkedip ---------- */
// Semua angka di bagian ini bisa diubah untuk menyetel "kepribadian" mata.
const kurangGerak = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const acak = (a, b) => a + Math.random() * (b - a);
const batasi = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
let terakhirMouse = 0;

// x, y dalam piksel (x positif = kanan, y positif = bawah); detik = lama pindah
function arahMata(x, y, detik) {
  pill.style.setProperty("--gdur", detik + "s");
  pill.style.setProperty("--gx", x.toFixed(2));
  pill.style.setProperty("--gy", y.toFixed(2));
}

// Mata sedang dalam suasana apa? null = mata tidak terlihat, tidak perlu bergerak
function modeMata() {
  const s = pill.dataset.state;
  if (s === "card") return kartu && kartu.tipe === "izin" ? "izin" : "kartu";
  if (s === "listening") return "dengar";
  if (s === "thinking") return "pikir";
  if (s === "small" && !pill.classList.contains("has-timer")) {
    return pill.dataset.mood === "happy" ? "senang" : "idle";
  }
  return null;
}

// Pilih ke mana mata melirik berikutnya, dan berapa lama menetap
function pilihTarget(mode, sebelumnya) {
  if (mode === "dengar") {   // fokus menatap lurus, dengan getaran halus
    return { x: acak(-0.8, 0.8), y: acak(-0.4, 0.4), tahan: acak(0.8, 1.6), dur: 0.5 };
  }
  if (mode === "pikir") {    // melirik atas ke samping, bergantian kiri-kanan
    return { x: (sebelumnya.x > 0 ? -1 : 1) * acak(4, 6), y: -acak(1.8, 2.8), tahan: acak(0.8, 1.5), dur: 0.28 };
  }
  if (mode === "izin") {     // melirik ke arah tombol (kanan bawah)
    return { x: acak(3, 5), y: acak(1, 2), tahan: acak(0.8, 1.6), dur: 0.3 };
  }
  if (mode === "kartu") {    // membaca teks di sebelah kanan
    return { x: acak(2, 4), y: acak(-0.5, 0.5), tahan: acak(0.9, 1.8), dur: 0.3 };
  }
  if (mode === "senang") {
    return { x: acak(-1, 1), y: 0, tahan: acak(1.2, 2.2), dur: 0.3 };
  }
  // idle: lebih sering menatap tengah, sesekali melirik
  const r = Math.random();
  if (r < 0.40) return { x: acak(-1.5, 1.5), y: acak(-0.6, 0.6), tahan: acak(1.2, 3.5), dur: 0.16 };
  if (r < 0.62) return { x: -acak(5, 8), y: acak(-1, 1), tahan: acak(0.7, 1.8), dur: 0.11 };
  if (r < 0.84) return { x: acak(5, 8), y: acak(-1, 1), tahan: acak(0.7, 1.8), dur: 0.11 };
  if (r < 0.93) return { x: acak(-5, 5), y: -acak(2, 3), tahan: acak(0.6, 1.4), dur: 0.14 };
  return { x: acak(-4, 4), y: acak(1.5, 2.5), tahan: acak(0.5, 1.1), dur: 0.14 };
}

async function kedip() {
  if (pill.dataset.mood === "happy") return; // mata senang berbentuk lengkung, tidak perlu berkedip
  pill.style.setProperty("--blink", "0.08");
  await tidurMs(95);
  pill.style.setProperty("--blink", "1");
}

async function loopMata() {
  let sebelumnya = { x: 0, y: 0 };
  while (true) {
    const mode = modeMata();
    if (!mode) { arahMata(0, 0, 0.3); sebelumnya = { x: 0, y: 0 }; await tidurMs(500); continue; }
    // kalau kursor baru saja bergerak di atas pill, mata sedang mengikuti kursor
    if (mode === "idle" && Date.now() - terakhirMouse < 1500) { await tidurMs(200); continue; }
    const t = pilihTarget(mode, sebelumnya);
    // lirikan besar sering disertai kedipan, seperti mata asli
    if (Math.hypot(t.x - sebelumnya.x, t.y - sebelumnya.y) > 6 && Math.random() < 0.35) kedip();
    arahMata(t.x, t.y, t.dur);
    sebelumnya = t;
    await tidurMs(t.tahan * 1000);
  }
}

async function loopKedip() {
  while (true) {
    await tidurMs(acak(modeMata() === "pikir" ? 3000 : 2200, 6200));
    if (!modeMata()) continue;
    await kedip();
    if (Math.random() < 0.18) { await tidurMs(150); await kedip(); } // kadang berkedip dua kali
  }
}

// mata mengikuti kursor saat kursor berada di atas pill
pill.addEventListener("mousemove", (e) => {
  if (modeMata() !== "idle") return;
  const r = pill.getBoundingClientRect();
  const x = batasi(((e.clientX - (r.left + r.width / 2)) / (r.width / 2)) * 9, -9, 9);
  const y = batasi(((e.clientY - (r.top + r.height / 2)) / (r.height / 2)) * 3, -3, 3);
  terakhirMouse = Date.now();
  arahMata(x, y, 0.12);
});

// Pengguna yang mengaktifkan "kurangi gerakan" di Windows tidak akan melihat mata bergerak sendiri
if (!kurangGerak) { loopMata(); loopKedip(); }

/* ---------- hasil pencarian dokumen ---------- */
// Server Python mengirim kejadian "dokumen". Hasil tampil sebagai SATU kartu bergaya notifikasi; kartu lain
// mengintip di bawahnya. Gulir (roda mouse, panah atas/bawah, atau klik kartu yang mengintip) untuk melihat dokumen lain.
// Klik kartu = buka dokumen, tombol folder = tampilkan di File Explorer.
let dokumenAktif = false;
let dokumenTimer = null;
let dokumenPrev = "small";
let dokData = { q: "", total: 0, hasil: [] };
let dokIdx = 0;
let dokRoda = 0;

const TIPE_DOK = { ".pdf": "pdf", ".doc": "word", ".docx": "word", ".xls": "excel", ".xlsx": "excel", ".xlsm": "excel",
                   ".csv": "excel", ".ppt": "ppt", ".pptx": "ppt", ".txt": "teks", ".md": "teks", ".rtf": "teks" };

function aturTimerDokumen(ms) {
  clearTimeout(dokumenTimer);
  dokumenTimer = setTimeout(tutupDokumen, ms);
}

function lepasFokus() {   // tombol yang baru diklik tidak boleh ikut tertekan oleh Enter/Spasi berikutnya
  const a = document.activeElement;
  if (a && a.blur && a !== document.body) a.blur();
}

function tutupDokumen() {
  clearTimeout(dokumenTimer);
  if (!dokumenAktif) return;
  dokumenAktif = false;
  lepasFokus();
  document.body.classList.remove("dok-t1", "dok-t2");
  if (state === "dokumen") setState(dokumenPrev && dokumenPrev !== "dokumen" ? dokumenPrev : idleState());
}

// Teks kartu ditulis lewat textContent (bukan innerHTML) supaya karakter aneh di nama file tidak menjadi kode.
function renderKartuDokumen(arah) {
  const hasil = dokData.hasil, n = hasil.length;
  const kartu = $("dk-kartu"), ikon = $("dk-ikon");
  $("dk-folder").classList.toggle("hidden", !n);
  $("dk-sub").classList.remove("galat");

  if (!n) {   // tidak ada yang cocok
    ikon.dataset.tipe = "kosong";
    $("dk-ext").textContent = "?";
    $("dk-label").textContent = dokData.q || "Dokumen";
    $("dk-hitung").textContent = "";
    $("dk-nama").textContent = "Tidak ada dokumen yang cocok";
    $("dk-sub").textContent = "Coba sebut kata lain dari judulnya";
    document.body.classList.remove("dok-t1", "dok-t2");
    return;
  }
  const h = hasil[dokIdx];
  ikon.dataset.tipe = TIPE_DOK[h.ext] || "lain";
  $("dk-ext").textContent = String(h.ext || "").replace(".", "").toUpperCase().slice(0, 4) || "FILE";
  $("dk-label").textContent = dokData.total > n ? `${dokData.q} · ${dokData.total} hasil` : (dokData.q || "Dokumen");
  $("dk-hitung").textContent = n > 1 ? `${dokIdx + 1} / ${n}` : "";
  $("dk-nama").textContent = h.nama;
  $("dk-sub").textContent = `${h.folder} · ${h.ukuran} · ${h.diubah}`;
  kartu.title = "Klik untuk membuka " + h.nama;

  // kartu yang mengintip di bawah = sisa dokumen yang belum dilihat
  const sisa = n - dokIdx - 1;
  document.body.classList.toggle("dok-t1", sisa >= 1);
  document.body.classList.toggle("dok-t2", sisa >= 2);

  if (arah) {   // efek geser: dokumen berikutnya naik dari bawah, sebelumnya turun dari atas
    kartu.classList.remove("geser-naik", "geser-turun");
    void kartu.offsetWidth;
    kartu.classList.add(arah === "naik" ? "geser-naik" : "geser-turun");
  }
}

function geserDokumen(delta) {
  const n = dokData.hasil.length;
  const baru = Math.max(0, Math.min(n - 1, dokIdx + delta));
  if (!n || baru === dokIdx) return;
  dokIdx = baru;
  renderKartuDokumen(delta > 0 ? "naik" : "turun");
  aturTimerDokumen(25000);
}

async function aksiDokumen(nomor, mode) {
  try {
    const r = await pyFetch(`${PY_BASE}/dokumen/buka`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ i: nomor, mode }),
    });
    const j = await r.json();
    if (j.ok) {
      aturTimerDokumen(700);   // tutup sebentar setelah file dibuka
    } else {
      $("dk-sub").textContent = j.message || "Gagal membuka file.";
      $("dk-sub").classList.add("galat");
    }
  } catch (e) {
    $("dk-sub").textContent = "Gagal menghubungi asisten.";
    $("dk-sub").classList.add("galat");
  }
}

function bukaDokumenKini(mode) {
  const h = dokData.hasil[dokIdx];
  if (h) aksiDokumen(h.i, mode);
}

function tampilDokumen(d) {
  if (state === "reminder" || state === "add") return;
  dokData = { q: d.q || "", total: d.total || 0, hasil: Array.isArray(d.hasil) ? d.hasil : [] };
  dokIdx = 0;
  lepasFokus();
  renderKartuDokumen(null);

  if (!dokumenAktif) dokumenPrev = sedangToast() ? toastPrev : (state === "card" ? kartuPrev : state);
  if (toastAktif) { clearTimeout(toastTimer); toastAktif = false; batalPower(); }   // hasil dokumen lebih penting daripada toast
  dokumenAktif = true;
  setState("dokumen");
  aturTimerDokumen(25000);
}

$("dk-kartu").addEventListener("click", (e) => { if (!e.target.closest("button") && dokData.hasil.length) bukaDokumenKini("buka"); });
stop("dk-folder", () => bukaDokumenKini("folder"));
stop("dk-tutup", tutupDokumen);
$("dk-t1").addEventListener("click", (e) => { e.stopPropagation(); geserDokumen(1); });
$("dk-t2").addEventListener("click", (e) => { e.stopPropagation(); geserDokumen(2); });
pill.addEventListener("mouseenter", () => { if (dokumenAktif) clearTimeout(dokumenTimer); });
pill.addEventListener("mouseleave", () => { if (dokumenAktif) aturTimerDokumen(8000); });

// roda mouse di mana pun di jendela pill: turun = dokumen berikutnya, naik = sebelumnya
window.addEventListener("wheel", (e) => {
  if (!dokumenAktif || state !== "dokumen" || Math.abs(e.deltaY) < 8) return;
  if (Date.now() - dokRoda < 220) return;
  dokRoda = Date.now();
  geserDokumen(e.deltaY > 0 ? 1 : -1);
}, { passive: true });

window.addEventListener("keydown", (e) => {
  if (!dokumenAktif || state !== "dokumen") return;
  if (e.key === "Escape") tutupDokumen();
  else if (e.key === "ArrowDown" || e.key === "PageDown") { e.preventDefault(); geserDokumen(1); }
  else if (e.key === "ArrowUp" || e.key === "PageUp") { e.preventDefault(); geserDokumen(-1); }
  else if (e.key === "Enter" && dokData.hasil.length) { e.preventDefault(); bukaDokumenKini("buka"); }   // preventDefault: jangan ikut menekan tombol yang masih berfokus
});
window.tampilDokumen = tampilDokumen;   // untuk uji di Console

/* ---------- teruskan pengingat dan baterai rendah ke WhatsApp (lewat server lokal; diam kalau belum diaktifkan) ---------- */
function kirimWA(teks) {
  pyFetch(`${PY_BASE}/wa/kirim`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ teks }) }).catch(() => {});
}

/* ---------- mulai ---------- */
(async () => {
  try { settings = await invoke("get_settings"); } catch (e) {}
  await setState(idleState());
  tick();
  pollMedia();
})();