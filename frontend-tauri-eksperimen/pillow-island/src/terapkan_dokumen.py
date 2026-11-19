#!/usr/bin/env python3
"""Menerapkan fitur pencarian dokumen ke file-file milikmu TANPA menimpa perubahanmu.

Cara pakai (di PowerShell):
    python terapkan_dokumen.py "D:\\asisten\\backend-python" "D:\\asisten\\frontend-tauri-eksperimen\\pillow-island\\src"

  - folder pertama = tempat server.py dan asisten.py
  - folder kedua   = folder src milik Tauri (tempat main.js, index.html, styles.css)

Yang dilakukan:
  1. Mencadangkan tiap file menjadi <nama>.bak-dokumen (hanya sekali).
  2. Menyalin dokumen.py ke folder backend.
  3. Menyisipkan potongan kode di tempat yang tepat. Kalau ada tempat yang tidak ditemukan, skrip
     berhenti dan TIDAK mengubah apa pun.
  4. Memeriksa sintaks (Python, dan JavaScript kalau node ada). Kalau gagal, semua dikembalikan.
Aman dijalankan berulang kali: bagian yang sudah terpasang dilewati.
"""
import os
import sys
import shutil
import subprocess

AMAN = "--longgar" not in sys.argv     # --longgar: hanya untuk pengujian internal
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]   # opsi: --ulang (pasang ulang dari cadangan)
SUFFIX = ".bak-dokumen"

# ======================================================================
#  POTONGAN KODE
# ======================================================================
SERVER_IMPOR = "import dokumen   # pencarian dokumen: nama file di seluruh D: dan folder pribadi\n"

SERVER_KEJADIAN = r'''# ---------- antrean kejadian untuk tampilan (dibaca main.js lewat /status?sejak=<id>) ----------
_kejadian = []
_kejadian_id = [0]
_kejadian_kunci = threading.Lock()

def kirim_kejadian(jenis, data):
    with _kejadian_kunci:
        _kejadian_id[0] += 1
        _kejadian.append({"id": _kejadian_id[0], "jenis": jenis, "data": data})
        del _kejadian[:-30]

def _kejadian_sejak(sejak):
    if sejak is None:
        return []
    with _kejadian_kunci:
        return [k for k in _kejadian if k["id"] > sejak]


'''

SERVER_STATUS_LAMA = '        hasil=dict(_hasil_terakhir),\n    )'
SERVER_STATUS_BARU = ('        hasil=dict(_hasil_terakhir),\n'
                      '        kejadian_id=_kejadian_id[0],\n'
                      '        kejadian=_kejadian_sejak(request.args.get("sejak", type=int)),\n    )')

SERVER_PERINTAH = r'''# ---------- perintah pencarian dokumen ----------
_STOP_DOK = {"cari", "carikan", "cariin", "temukan", "tolong", "buka", "bukakan", "tampilkan", "lihat", "dokumen",
             "dokumennya", "file", "filenya", "berkas", "yang", "judul", "judulnya", "bernama", "namanya", "nama",
             "tentang", "soal", "dong", "ya", "saya", "aku", "untuk", "di", "komputer", "laptop", "mohon", "coba",
             "pillow", "pencarian"}
_NOMOR_DOK = {"pertama": 1, "satu": 1, "kesatu": 1, "kedua": 2, "dua": 2, "ketiga": 3, "tiga": 3,
              "keempat": 4, "empat": 4, "kelima": 5, "lima": 5, "keenam": 6, "enam": 6, "ketujuh": 7, "tujuh": 7,
              "kedelapan": 8, "delapan": 8, "kesembilan": 9, "sembilan": 9, "kesepuluh": 10, "sepuluh": 10}


def _nomor_pilihan(p):
    m = re.search(r"\b(?:ke|nomor|nomer|no)\s*-?\s*(\d{1,2})\b", p)
    if m:
        return int(m.group(1))
    for kata, n in _NOMOR_DOK.items():
        if re.search(r"\b" + kata + r"\b", p):
            return n
    return None


def _buka_atau_folder(nomor, mode):
    hasil = dokumen.terakhir_segar(30)
    if not hasil or not (1 <= nomor <= len(hasil)):
        ngomong("Aku belum punya daftar dokumen terbaru. Coba cari dulu, misalnya: cari dokumen laporan keuangan.")
        return
    nama = dokumen.nama_ucapan(hasil[nomor - 1]["path"])
    ok, pesan = dokumen.aksi(nomor - 1, mode)
    if ok:
        ngomong(f"Menampilkan {nama} di folder." if mode == "folder" else f"Membuka {nama}.")
    else:
        ngomong(pesan)


def _perintah_dokumen(p, suara):
    """Tangani perintah dokumen. True kalau perintahnya sudah ditangani di sini."""
    if "ringkas dokumen" in p or "kirim file" in p or "tab" in p.split() or p.startswith("tutup"):
        return False

    if "indeks" in p and any(k in p for k in ("perbarui", "segarkan", "update", "muat ulang")):
        dokumen.perbarui_indeks()
        ngomong("Oke, aku perbarui indeks dokumen di latar belakang.")
        return True

    cari_baru = ("dokumen" in p) or bool(re.search(r"\b(cari|carikan|temukan|buka|bukakan)\s+(file|berkas)\b", p))
    if not cari_baru:
        # lanjutan dari hasil sebelumnya: "buka yang kedua", "tampilkan yang pertama di folder"
        nomor = _nomor_pilihan(p)
        if nomor and (re.search(r"\b(buka|bukakan|tampilkan|lihat)\b", p) or "folder" in p
                      or p.startswith("yang") or "nomor" in p):
            if dokumen.terakhir_segar():
                _buka_atau_folder(nomor, "folder" if "folder" in p else "buka")
                return True
            if re.search(r"\byang\s+(?:pertama|kedua|ketiga|keempat|kelima|keenam|ketujuh|kedelapan|kesembilan|kesepuluh|satu|dua|tiga|ke\s*-?\s*\d{1,2})\b", p):
                ngomong("Aku belum punya daftar dokumen terbaru. Coba cari dulu, misalnya: cari dokumen laporan keuangan.")
                return True
        return False

    status = dokumen.status_indeks()
    qt = [w for w in dokumen.token(p) if w not in _STOP_DOK]
    if not qt:
        ngomong("Sebutkan judul dokumennya. Contoh: cari dokumen laporan keuangan.")
        return True
    if not status["siap"]:
        ngomong("Indeks dokumen masih disiapkan, tunggu sekitar satu sampai dua menit lalu coba lagi.")
        return True

    query = " ".join(qt)
    hasil, total = dokumen.cari(query, 10)
    dokumen.simpan_terakhir(hasil, query)
    if not hasil:
        kirim_kejadian("dokumen", {"q": query, "total": 0, "hasil": [], "siap": True, "jumlah": status["jumlah"]})
        ngomong(f"Maaf, aku tidak menemukan dokumen yang cocok dengan {query}.")
        return True

    mau_buka = bool(re.search(r"\b(buka|bukakan)\b", p)) and "cari" not in p
    if mau_buka and dokumen.jelas_unggul(hasil):
        ok, pesan = dokumen.aksi(0, "buka")
        ngomong(f"Membuka {dokumen.nama_ucapan(hasil[0]['path'])}." if ok else pesan)
        return True

    kirim_kejadian("dokumen", {"q": query, "total": total, "hasil": dokumen.format_hasil(hasil),
                               "siap": True, "jumlah": status["jumlah"]})
    nama1 = dokumen.nama_ucapan(hasil[0]["path"])
    if len(hasil) == 1:
        ngomong(f"Aku menemukan satu dokumen: {nama1}. Katakan buka yang pertama, atau tampilkan di folder.")
    else:
        ngomong(f"Aku menemukan {total} dokumen. Yang paling cocok: {nama1}. Katakan buka yang pertama, atau gulir untuk melihat yang lain.")
    return True


'''

SERVER_CABANG_LAMA = '        if "pillow" in p and ("hi" in p or "hai" in p or "halo" in p):'
SERVER_CABANG_BARU = ('        if _perintah_dokumen(p, suara):\n'
                      '            pass\n'
                      '        elif "pillow" in p and ("hi" in p or "hai" in p or "halo" in p):')

SERVER_RUTE = r'''@app.post("/dokumen/buka")
def dokumen_buka():
    # Dipanggil tombol Buka / Folder di tampilan hasil pencarian dokumen
    data = request.get_json(silent=True) or {}
    try:
        nomor = int(data.get("i"))
    except (TypeError, ValueError):
        return jsonify(ok=False, message="Nomor tidak valid."), 400
    mode = "folder" if data.get("mode") == "folder" else "buka"
    ok, pesan = dokumen.aksi(nomor, mode)
    return jsonify(ok=ok, message=pesan)

@app.get("/dokumen/status")
def dokumen_status():
    return jsonify(dokumen.status_indeks())

'''

SERVER_MULAI = "    dokumen.mulai_indeks()   # pindai nama file di latar belakang\n"

ASISTEN_LAMA = '"timer", "ingatkan", "pengingat", "hitung"]'
ASISTEN_BARU = ('"timer", "ingatkan", "pengingat", "hitung", "dokumen", "berkas", "folder", "indeks", '
                '"pertama", "kedua", "ketiga", "keempat", "kelima", "nomor"]')

JS_UKURAN = "\n  dokumen: { w: 492, h: 140 },"
JS_GUARD = "\n  if (dokumenAktif) return;   // hasil pencarian dokumen sedang tampil"
JS_KEJADIAN_LAMA = '      tampilKartuStatus(d.nada === "bad" ? "bad" : "ok", String(d.teks || ""));'
JS_KEJADIAN_BARU = (JS_KEJADIAN_LAMA + '\n    } else if (k.jenis === "dokumen") {\n      tampilDokumen(d);')

JS_BLOK = r'''/* ---------- hasil pencarian dokumen ---------- */
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

'''

HTML_BLOK = '''<!-- hasil pencarian dokumen: satu kartu, gulir untuk dokumen lain -->
      <div class="v v-dok">
        <div class="dk-kartu" id="dk-kartu" title="Klik untuk membuka">
          <div class="dk-ikon" id="dk-ikon" data-tipe="lain"><span id="dk-ext">PDF</span></div>
          <div class="dk-teks">
            <div class="dk-atas"><small id="dk-label">Dokumen</small><small id="dk-hitung"></small></div>
            <b id="dk-nama">Nama file</b>
            <small id="dk-sub"></small>
          </div>
          <button id="dk-folder" aria-label="Tampilkan di folder" title="Tampilkan di folder"><svg width="14" height="14" viewBox="0 0 24 24" fill="#fff"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg></button>
          <button id="dk-tutup" aria-label="Tutup" title="Tutup"><svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19 12 13.4 17.6 19 19 17.6 13.4 12 19 6.4 17.6 5 12 10.6z"/></svg></button>
        </div>
      </div>

      '''

HTML_TUMPUK = '''<!-- kartu yang mengintip di bawah hasil dokumen (di luar pill) -->
    <div class="dk-tumpuk dk-tumpuk-1" id="dk-t1" aria-hidden="true"></div>
    <div class="dk-tumpuk dk-tumpuk-2" id="dk-t2" aria-hidden="true"></div>
    '''

CSS_DAFTAR_LAMA = '#pill[data-state="power"] .v-power,\n'
CSS_DAFTAR_BARU = CSS_DAFTAR_LAMA + '#pill[data-state="dokumen"] .v-dok,\n'

CSS_BLOK = '''
/* =========================================
   --- HASIL PENCARIAN DOKUMEN ---
   satu kartu bergaya notifikasi; kartu lain mengintip di bawahnya
   ========================================= */
#pill[data-state="dokumen"] { width: 460px; height: 96px; border-radius: 30px; cursor: default; z-index: 2; }
.v-dok { padding: 0 16px 0 18px; }
.dk-kartu { width: 100%; display: flex; align-items: center; gap: 14px; min-width: 0; cursor: pointer; }
.dk-ikon {
  flex: none; width: 56px; height: 56px; border-radius: 16px; display: grid; place-items: center;
  background: linear-gradient(135deg, #a78bfa, #6d28d9); box-shadow: 0 4px 14px rgba(109, 40, 217, 0.35);
}
.dk-ikon[data-tipe="pdf"] { background: linear-gradient(135deg, #f87171, #b91c1c); box-shadow: 0 4px 14px rgba(185, 28, 28, 0.35); }
.dk-ikon[data-tipe="word"] { background: linear-gradient(135deg, #60a5fa, #1d4ed8); box-shadow: 0 4px 14px rgba(29, 78, 216, 0.35); }
.dk-ikon[data-tipe="excel"] { background: linear-gradient(135deg, #4ade80, #15803d); box-shadow: 0 4px 14px rgba(21, 128, 61, 0.35); }
.dk-ikon[data-tipe="ppt"] { background: linear-gradient(135deg, #fb923c, #c2410c); box-shadow: 0 4px 14px rgba(194, 65, 12, 0.35); }
.dk-ikon[data-tipe="teks"] { background: linear-gradient(135deg, #94a3b8, #475569); box-shadow: none; }
.dk-ikon[data-tipe="kosong"] { background: #26262e; box-shadow: none; }
.dk-ikon span { font-size: 0.8rem; font-weight: 800; letter-spacing: 0.02em; color: #fff; }
.dk-teks { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.dk-atas { display: flex; justify-content: space-between; gap: 10px; }
.dk-atas small { font-size: 0.7rem; color: #9a9aa6; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#dk-hitung { flex: none; color: var(--accent2); font-weight: 600; font-variant-numeric: tabular-nums; }
#dk-nama { font-size: 0.95rem; font-weight: 800; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#dk-sub { font-size: 0.74rem; color: #9a9aa6; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#dk-sub.galat { color: #fca5a5; }
.dk-kartu button {
  flex: none; border: 0; width: 30px; height: 30px; border-radius: 50%; background: #26262e;
  display: grid; place-items: center; cursor: pointer;
}
.dk-kartu button:hover { background: var(--accent); }
#dk-tutup:hover { background: #ef4444; }

/* efek geser antar dokumen */
.dk-kartu.geser-naik .dk-ikon, .dk-kartu.geser-naik .dk-teks { animation: dk-naik 0.24s ease both; }
.dk-kartu.geser-turun .dk-ikon, .dk-kartu.geser-turun .dk-teks { animation: dk-turun 0.24s ease both; }
@keyframes dk-naik { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
@keyframes dk-turun { from { opacity: 0; transform: translateY(-16px); } to { opacity: 1; transform: none; } }

/* dua kartu tipis yang mengintip di bawah pill (di luar #pill, jadi tidak terpotong) */
.dk-tumpuk {
  position: fixed; left: 50%; transform: translateX(-50%); z-index: 1;
  height: 30px; border-radius: 24px; background: #121218;
  box-shadow: inset 0 0 0 1px rgba(196, 181, 253, 0.2);
  opacity: 0; pointer-events: none; cursor: pointer;
  transition: opacity 0.3s ease 0.3s;
}
.dk-tumpuk-1 { top: 80px; width: 420px; }
.dk-tumpuk-2 { top: 92px; width: 380px; background: #0d0d12; z-index: 0; }   /* di belakang kartu pertama */
body.dok-t1 .dk-tumpuk-1 { opacity: 1; pointer-events: auto; }
body.dok-t2 .dk-tumpuk-2 { opacity: 1; pointer-events: auto; }
body:not(.dok-t1) .dk-tumpuk-1, body:not(.dok-t2) .dk-tumpuk-2 { transition-delay: 0s; }
'''

# ======================================================================
#  DAFTAR PERUBAHAN: (berkas, nama, jenis, jangkar, teks, penanda, wajib)
#  jenis: sesudah | sebelum | ganti | tambah_akhir
# ======================================================================
PERUBAHAN = [
    ("server.py", "impor dokumen", "sesudah", "\nimport lirik\n", SERVER_IMPOR, "import dokumen", True),
    ("server.py", "penanda versi", "ganti", 'BUILD_ID = "2026-11-04-final"', 'BUILD_ID = "2026-11-05-dokumen"', "2026-11-05-dokumen", False),
    ("server.py", "antrean kejadian", "sebelum", "@app.errorhandler(Exception)", SERVER_KEJADIAN, "def kirim_kejadian", True),
    ("server.py", "status mengirim kejadian", "ganti", SERVER_STATUS_LAMA, SERVER_STATUS_BARU, "kejadian_id=_kejadian_id[0]", True),
    ("server.py", "perintah dokumen", "sebelum", "def proses_perintah(perintah, suara=False):", SERVER_PERINTAH, "def _perintah_dokumen", True),
    ("server.py", "cabang perintah dokumen", "ganti", SERVER_CABANG_LAMA, SERVER_CABANG_BARU, "if _perintah_dokumen(p, suara):", True),
    ("server.py", "rute /dokumen/buka", "sebelum", '@app.get("/lirik")', SERVER_RUTE, '"/dokumen/buka"', True),
    ("server.py", "indeks dimulai saat server menyala", "sesudah",
     '    print(f"[server] build {BUILD_ID} di http://127.0.0.1:{PORT}", flush=True)\n', SERVER_MULAI, "dokumen.mulai_indeks()", True),
    ("asisten.py", "kata perintah dokumen", "ganti", ASISTEN_LAMA, ASISTEN_BARU, '"berkas", "folder", "indeks"', True),
    ("main.js", "ukuran tampilan dokumen", "sesudah", "  power: { w: 336, h: 92 },", JS_UKURAN, "dokumen: { w: 492", True),
    ("main.js", "kartu status tidak menimpa hasil dokumen", "sesudah", "function tampilKartuStatus(nada, teks) {", JS_GUARD, "if (dokumenAktif) return;", True),
    ("main.js", "kejadian dokumen", "ganti", JS_KEJADIAN_LAMA, JS_KEJADIAN_BARU, 'k.jenis === "dokumen"', True),
    ("main.js", "tampilan hasil dokumen", "sebelum", "/* ---------- mulai ---------- */", JS_BLOK, "function tampilDokumen(d)", True),
    ("index.html", "blok hasil dokumen", "sebelum", "<!-- animasi charger", HTML_BLOK, 'class="v v-dok"', True),
    ("index.html", "lapisan kartu yang mengintip", "sebelum", '<script type="module" src="main.js">', HTML_TUMPUK, 'id="dk-t1"', True),
    ("styles.css", "daftar tampilan yang terlihat", "ganti", CSS_DAFTAR_LAMA, CSS_DAFTAR_BARU, 'data-state="dokumen"] .v-dok', True),
    ("styles.css", "gaya hasil dokumen", "tambah_akhir", "", CSS_BLOK, "HASIL PENCARIAN DOKUMEN", True),
]


def terapkan(isi, jenis, jangkar, teks, penanda, wajib):
    """Kembalikan (isi_baru, status): ok | sudah | tidak-ketemu | ganda."""
    if penanda in isi:
        return isi, "sudah"
    if jenis == "tambah_akhir":
        return isi.rstrip("\n") + "\n" + teks, "ok"
    n = isi.count(jangkar)
    if n == 0:
        return isi, "tidak-ketemu"
    if n > 1:
        return isi, "ganda"
    i = isi.index(jangkar)
    if jenis == "sesudah":
        return isi[:i + len(jangkar)] + teks + isi[i + len(jangkar):], "ok"
    if jenis == "sebelum":
        return isi[:i] + teks + isi[i:], "ok"
    if jenis == "ganti":
        return isi.replace(jangkar, teks, 1), "ok"
    raise ValueError(jenis)


def tanya(pesan):
    try:
        return input(pesan).strip().strip('"')
    except EOFError:
        return ""


def main():
    backend = (ARGS[0] if len(ARGS) > 0 else tanya("Folder backend (tempat server.py): ")).strip('"')
    frontend = (ARGS[1] if len(ARGS) > 1 else tanya("Folder src Tauri (tempat main.js): ")).strip('"')
    peta = {"server.py": backend, "asisten.py": backend, "main.js": frontend, "index.html": frontend, "styles.css": frontend}
    jalur = {b: os.path.join(f, b) for b, f in peta.items()}

    hilang = [j for j in jalur.values() if not os.path.isfile(j)]
    if hilang:
        print("Berkas ini tidak ditemukan, periksa kembali nama folder:\n  " + "\n  ".join(hilang))
        return 1
    sumber_modul = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dokumen.py")
    if not os.path.isfile(sumber_modul) and not os.path.isfile(os.path.join(backend, "dokumen.py")):
        print("dokumen.py tidak ditemukan. Taruh dokumen.py satu folder dengan skrip ini.")
        return 1

    if "--ulang" in sys.argv:    # kembalikan dari cadangan dulu, lalu terapkan versi terbaru
        for b, j in jalur.items():
            if os.path.isfile(j + SUFFIX):
                shutil.copy2(j + SUFFIX, j)
                print(f"  [dikembalikan] {b} dari cadangan")

    isi = {b: open(j, encoding="utf-8").read() for b, j in jalur.items()}
    asli = dict(isi)
    laporan, gagal = [], []
    for berkas, nama, jenis, jangkar, teks, penanda, wajib in PERUBAHAN:
        baru, status = terapkan(isi[berkas], jenis, jangkar, teks, penanda, wajib)
        if status == "ok":
            isi[berkas] = baru
            laporan.append(f"  [terpasang] {berkas}: {nama}")
        elif status == "sudah":
            laporan.append(f"  [sudah ada] {berkas}: {nama}")
        else:
            pesan = f"{berkas}: {nama} ({'jangkar tidak ditemukan' if status == 'tidak-ketemu' else 'jangkar muncul lebih dari sekali'})"
            if wajib and AMAN:
                gagal.append(pesan)
            else:
                laporan.append(f"  [dilewati]  {pesan}")
    print("\n".join(laporan))
    if gagal:
        print("\nTIDAK ADA FILE YANG DIUBAH. Bagian berikut tidak cocok dengan file-mu:\n  " + "\n  ".join(gagal))
        print("Kirim bagian file di sekitar itu ke saya, nanti saya sesuaikan.")
        return 2

    # tulis (cadangan dulu), lalu periksa sintaks
    diubah = [b for b in jalur if isi[b] != asli[b]]
    for b in diubah:
        if not os.path.exists(jalur[b] + SUFFIX):
            shutil.copy2(jalur[b], jalur[b] + SUFFIX)
        with open(jalur[b], "w", encoding="utf-8") as f:
            f.write(isi[b])
    tujuan_modul = os.path.join(backend, "dokumen.py")
    if os.path.isfile(sumber_modul) and os.path.abspath(sumber_modul) != os.path.abspath(tujuan_modul):
        shutil.copy2(sumber_modul, tujuan_modul)
        print("  [disalin]   dokumen.py -> " + backend)

    masalah = []
    for b in diubah:
        if b.endswith(".py"):
            r = subprocess.run([sys.executable, "-m", "py_compile", jalur[b]], capture_output=True, text=True)
            if r.returncode != 0:
                masalah.append(f"{b}: {r.stderr.strip()[-300:]}")
        elif b.endswith(".js") and shutil.which("node"):
            r = subprocess.run(["node", "--check", jalur[b]], capture_output=True, text=True)
            if r.returncode != 0:
                masalah.append(f"{b}: {r.stderr.strip()[-300:]}")
    if masalah:
        for b in diubah:
            shutil.copy2(jalur[b] + SUFFIX, jalur[b])
        print("\nPemeriksaan sintaks GAGAL, semua file sudah dikembalikan seperti semula:\n  " + "\n  ".join(masalah))
        return 3

    print(f"\nSelesai. {len(diubah)} file diperbarui (cadangan: *{SUFFIX}).")
    print("Langkah berikut: build ulang Python, lalu npm run tauri dev.")
    return 0


if __name__ == "__main__":
    sys.exit(main())