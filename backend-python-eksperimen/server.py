import os
import sys
import re
import json
import uuid
import time
import difflib
import threading
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
from werkzeug.exceptions import HTTPException

import engineio.async_drivers.threading  # noqa: F401

import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

import asisten
from asisten import (
    ngomong, dengerin, buka_aplikasi, tutup_aplikasi, putar_youtube,
    tanya_ai, cari_file, cleanup_laptop, ringkas_dokumen, kirim_file,
    buka_tab_brave,
    atur_volume, mute_volume, atur_kecerahan,
    analisis_market, lihat_layar,
)
import lirik
import wa   # gerbang WhatsApp (WAHA)
import jendela   # kontrol jendela aplikasi
import dokumen   # pencarian dokumen: nama file di seluruh D: dan folder pribadi
import musik     # kontrol musik: jeda, lanjut, lagu berikutnya, lagu apa ini
import obrolan   # mode ngobrol: teman ngobrol + konteks layar
import video     # fullscreen / kecilkan video di browser
import tab_brave # tutup tab Brave

BUILD_ID = "2026-11-29-tab-fokus"
PORT = 8008

app = Flask(__name__)
app.config["SECRET_KEY"] = "rahasia"
CORS(app)
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

_kunci = threading.Lock()

AMBANG_TIDUR = 800
MULAI_BANGUN = False
AMBANG_BANGUN = 500
BATAS_IZIN_DETIK = 30
BATAS_IZIN_WA_DETIK = 90     # lewat WA butuh waktu lebih lama untuk membaca dan membalas
SUARA_WA = False             # True = perintah dari WhatsApp juga diucapkan lewat speaker laptop

KATA_BANGUN = ("mulai", "bangun", "halo", "asisten", "start", "wake up")
KATA_TIDUR = ("tidur", "istirahat", "sleep", "dibur", "tidor", "tiduh", "tidu", "tiur")
# "berhenti" saja tidak lagi mematikan mode suara: kata itu sekarang untuk menghentikan Pillow yang sedang bicara
KATA_KELUAR = ("keluar", "exit", "quit", "berhenti mendengarkan", "matikan mode suara")

# --- menghentikan Pillow yang sedang bicara ("berhenti", "stop", "diam", "cukup") ---
HENTI_SAAT_BICARA = True      # False = matikan fitur ini (hemat kuota Whisper)
AMBANG_HENTI = 900            # lebih tinggi dari AMBANG_BANGUN supaya gema speaker tidak terus terkirim
_KATA_HENTI_INTI = {"berhenti", "stop", "diam", "cukup", "hentikan", "sst", "ssst", "shh", "stopp"}
_KATA_HENTI_PELENGKAP = {"oke", "ok", "pillow", "dong", "ya", "sudah", "udah", "deh", "aja", "please", "tolong"}

def _ucapan_henti(p):
    """True kalau ucapannya HANYA kata henti (maks 3 kata). Gema kalimat Pillow sendiri hampir selalu lebih panjang."""
    kata = re.sub(r"[^\w\s]", " ", (p or "").lower()).split()
    if not kata or len(kata) > 3:
        return False
    return any(k in _KATA_HENTI_INTI for k in kata) and all(k in _KATA_HENTI_INTI | _KATA_HENTI_PELENGKAP for k in kata)


def _pantau_henti(selesai):
    """Selama perintah diproses: tiap kali Pillow bicara, dengarkan potongan pendek; hentikan TTS kalau dengar kata henti."""
    while not selesai.is_set():
        if not asisten.sedang_bicara["event"].wait(0.2):
            continue
        p = dengerin(3, ambang=AMBANG_HENTI, saring=False)
        if selesai.is_set() and not asisten.sedang_bicara["event"].is_set():
            break
        if _ucapan_henti(p):
            print(f"[henti] '{p}' -> suara dihentikan", flush=True)
            asisten.hentikan_suara()
            update_ui("memproses", "Oke, berhenti.")
            break

KATA_YA = ("ya", "iya", "yes", "izinkan", "boleh", "oke", "ok", "lanjut", "yup")
KATA_TOLAK = ("tidak", "jangan", "batal", "tolak", "no", "nggak", "enggak", "gak")
KATA_SELALU = ("selalu", "always")
KATA_NGOBROL = ("ngobrol", "ayo ngobrol", "ngobrol yuk", "ayo cerita", "temani aku", "temenin aku")
KATA_UDAHAN = ("udahan", "udah dulu", "sudah dulu", "sudahan", "selesai ngobrol", "stop ngobrol", "cukup ngobrolnya")
DIAM_NGOBROL_DETIK = 90       # mode ngobrol suara mati sendiri setelah diam selama ini

# Kata awal yang menandai perintah. Saat ngobrol (dan di WA/ketikan), ucapan yang tidak tampak seperti perintah
# langsung jadi obrolan, supaya "aku suka suara hujan" tidak dianggap perintah volume.
_AWAL_PERINTAH = ("buka", "bukakan", "tutup", "putar", "cari", "carikan", "temukan", "ringkas", "kirim", "bersihkan",
                  "cleanup", "lihat layar", "baca layar", "minimize", "minimalkan", "maksimalkan", "munculkan",
                  "tampilkan", "sembunyikan", "naikkan", "turunkan", "mute", "volume", "kecerahan", "brightness",
                  "perbarui indeks", "segarkan indeks", "hai pillow", "halo pillow", "hi pillow")

_PERINTAH_AWAL = ("buka", "tutup", "putar", "cari", "ringkas", "kirim", "bersihkan", "cleanup", "tutup tab")

def _cocok(p, kata, ambang=0.7, maks=5):
    p = re.sub(r"[^\w\s]", " ", p.lower()).strip()
    if not p or p.startswith(_PERINTAH_AWAL):
        return False
    kata_p = p.split()
    if len(kata_p) > maks:
        return False
    for k in kata:
        if " " in k:
            if k in p:
                return True
            continue
        for w in kata_p:
            if w == k:
                return True
            if (len(k) >= 4 and len(w) >= 4 and abs(len(w) - len(k)) <= 1
                    and difflib.SequenceMatcher(None, w, k).ratio() >= ambang):
                return True
    return False

_status_sekarang = {"status": "idle", "teks": ""}
_hasil_terakhir = {"seq": 0, "nada": None, "teks": ""}

_PETA_UI = {
    "mendengarkan": "listening",
    "memproses": "thinking",
}

# ---------- antrean kejadian untuk tampilan (dibaca main.js lewat /status?sejak=<id>) ----------
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


@app.errorhandler(Exception)
def semua_error(e):
    if isinstance(e, HTTPException):
        return e
    traceback.print_exc()
    sys.stderr.flush()
    return jsonify(ok=False, message=f"Error server: {type(e).__name__}: {e}"), 500

def update_ui(status, teks="", nada=None):
    _status_sekarang["status"] = status
    _status_sekarang["teks"] = teks
    if status in ("selesai", "galat", "error"):
        _hasil_terakhir["seq"] += 1
        _hasil_terakhir["nada"] = nada or ("ok" if status == "selesai" else "bad")
        _hasil_terakhir["teks"] = teks
    socketio.emit("status_asisten", {"status": status, "teks": teks})
    print(f"[UI Update] {status}: {teks}", flush=True)

def _lapor_hasil(ucapan):
    pesan = " ".join(ucapan) if ucapan else "Selesai."
    if asisten.ambil_galat():
        update_ui("galat", pesan, nada="bad")
    else:
        update_ui("selesai", pesan, nada="ok")
    return pesan

_izin_aktif = {"req": None}

def _file_izin():
    try:
        folder = asisten._folder_appdata()
    except Exception:
        folder = ""
    folder = folder or os.path.expanduser("~")
    return os.path.join(folder, "PillowIsland", "izin.json")

def _muat_selalu():
    try:
        with open(_file_izin(), "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def _simpan_selalu():
    try:
        path = _file_izin()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(_selalu), f)
    except Exception as e:
        print(f"[izin] gagal menyimpan: {e}", flush=True)

_selalu = _muat_selalu()

def _jawaban_suara(p):
    if _cocok(p, KATA_SELALU, 0.8, maks=4):
        return "selalu"
    if _cocok(p, KATA_TOLAK, 0.8, maks=3):
        return "tolak"
    if _cocok(p, KATA_YA, 0.8, maks=3):
        return "izinkan"
    return None

def _ucapkan_tanpa_catat(teks):
    pend = asisten._pendengar
    asisten.set_pendengar(None)
    try:
        ngomong(teks)
    finally:
        asisten.set_pendengar(pend)

def minta_izin(kunci, teks, suara=False, wa_=False):
    if kunci in _selalu:
        return True

    req = {
        "id": uuid.uuid4().hex[:8],
        "kunci": kunci,
        "teks": teks,
        "suara": suara,
        "wa": wa_,
        "event": threading.Event(),
        "jawab": None,
    }
    _izin_aktif["req"] = req
    update_ui("izin", teks, nada="warn")
    if suara:
        _ucapkan_tanpa_catat(f"{teks}. Katakan ya atau tidak.")
    batas = BATAS_IZIN_DETIK
    if wa_:
        batas = BATAS_IZIN_WA_DETIK
        wa.kirim(f"Izin dibutuhkan: {teks}. Balas ya, tidak, atau selalu (dalam {batas} detik).")

    try:
        mulai = time.time()
        while time.time() - mulai < batas and not req["event"].is_set():
            if suara:
                p = dengerin(3, ambang=AMBANG_BANGUN)
                j = _jawaban_suara(p) if p else None
                if j and not req["event"].is_set():
                    req["jawab"] = j
                    req["event"].set()
            else:
                req["event"].wait(0.5)
        jawab = req["jawab"] or "tolak"
    finally:
        _izin_aktif["req"] = None
        update_ui("memproses", "Memproses...")

    if jawab == "selalu":
        _selalu.add(kunci)
        _simpan_selalu()
    return jawab in ("izinkan", "selalu")

# ---------- perintah pencarian dokumen ----------
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


# ---------- perintah kontrol jendela: minimize / maksimalkan / tampilkan ----------
def _perintah_jendela(p, suara):
    """Tangani 'minimize brave', 'maksimalkan brave', 'tampilkan brave'. True kalau sudah ditangani.
    'buka brave' sengaja TIDAK ditangani di sini: itu diurus buka_aplikasi() (munculkan jendela yang sudah ada)."""
    if any(k in p for k in ("volume", "suara", "kecerahan", "brightness", "layar")) or "tab" in p.split():
        return False
    app = jendela.kenali_app(p)
    aksi = jendela.kenali_aksi(p)
    if not app or not aksi:
        return False
    nama = jendela.nama_tampil(app)
    if not jendela.sedang_jalan(app):
        ngomong(f"{nama} belum terbuka. Katakan buka {nama.lower()} kalau mau membukanya.")
        return True
    if aksi == "minimize":
        n = jendela.minimize_app(app)
        ngomong(f"{nama} diminimize." if n else f"{nama} sudah dalam keadaan minimize.")
    elif aksi == "maximize":
        jendela.maksimalkan_app(app)
        ngomong(f"{nama} dimaksimalkan.")
    else:
        jendela.tampilkan_app(app)
        ngomong(f"{nama} ditampilkan.")
    return True


def _tampak_perintah(p):
    t = re.sub(r"[^\w\s]", " ", p.lower())
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(?:(?:tolong|coba|pillow|dong|ayo)\s+)+", "", t)
    aksi_musik = musik.kenali(t)
    if aksi_musik == "lanjut" and not re.search(r"lagu|musik|putar|mainkan|play|resume", t):
        return False                       # "lanjut" saja saat ngobrol = lanjutkan cerita, bukan musik
    if aksi_musik or video.kenali(t):
        return True
    if t.startswith(_AWAL_PERINTAH):
        return True
    if len(t.split()) <= 6 and re.search(r"\b(?:volume|suara|kecerahan|brightness)\b", t) \
            and re.search(r"\b(?:naik\w*|turun\w*|mute|bisu|terang\w*|redup\w*)\b", t):
        return True
    return bool(jendela.kenali_app(t) and jendela.kenali_aksi(t))


_ngobrol = {"aktif": False, "terakhir": 0.0}

def _mode_ngobrol(nyala, reset=True):
    _ngobrol["aktif"] = nyala
    _ngobrol["terakhir"] = time.time()
    if reset:
        obrolan.reset("suara")


def proses_perintah(perintah, suara=False, wa_=False, saluran=None):
    """saluran ("suara" / "wa" / "ketik"): obrolan aktif di saluran itu; ucapan yang bukan perintah jadi obrolan."""
    ucapan = []
    asisten.set_pendengar(ucapan.append)
    asisten.reset_stop()
    try:
        p = asisten.ke_brave(perintah.lower().strip())   # 'chrome' / 'opera' diarahkan ke Brave
        if saluran and not _tampak_perintah(p):
            ngomong(obrolan.ngobrol(saluran, perintah.strip()))
            return ucapan

        aksi_musik = musik.kenali(p)
        aksi_video = None if aksi_musik else video.kenali(p)
        if aksi_musik:
            ngomong(musik.jalankan(aksi_musik))
        elif aksi_video:
            ngomong(video.jalankan(aksi_video))
        elif _perintah_dokumen(p, suara):
            pass
        elif "pillow" in p and ("hi" in p or "hai" in p or "halo" in p):
            pertanyaan = p.replace("hi pillow", "").replace("hai pillow", "").replace("halo pillow", "").strip()
            if pertanyaan:
                analisis_market(pertanyaan)
            else:
                ngomong("Ya, ada yang bisa saya bantu soal market?")
                
        elif "lihat layar" in p or "baca layar" in p:
            pertanyaan = p.replace("lihat layar", "").replace("baca layar", "").strip()
            pertanyaan = re.sub(r"^(?:lagi|dong|ya|sekarang)\b\s*", "", pertanyaan)
            kanal = saluran or ("suara" if suara else None)
            if kanal:
                # deskripsi rinci disimpan sebagai konteks, jadi pertanyaan lanjutan bisa dibahas tanpa kata perintah
                ngomong(obrolan.lihat_layar(kanal, pertanyaan))
                if kanal == "suara":
                    _mode_ngobrol(True, reset=False)
            else:
                lihat_layar(pertanyaan)
            
        elif _perintah_jendela(p, suara):
            pass
        elif "buka tab" in p:
            url = p.replace("buka tab ", "").strip()
            buka_tab_brave(url)
            
        elif tab_brave.kenali(p):
            tab_brave.jalankan(*tab_brave.kenali(p))

        elif "volume" in p or "suara" in p:
            angka_match = re.search(r'\d+', p)
            angka = int(angka_match.group()) if angka_match else 10
            
            if "naik" in p or "naikkan" in p or "tinggi" in p:
                atur_volume(angka)
            elif "turun" in p or "turunkan" in p or "rendah" in p:
                atur_volume(-angka)
            elif "mute" in p or "bisu" in p:
                mute_volume()
            else:
                ngomong("Mau naikkan atau turunkan volume?")
                
        elif "kecerahan" in p or "brightness" in p or "layar" in p:
            angka_match = re.search(r'\d+', p)
            angka = int(angka_match.group()) if angka_match else 10
            
            if "naik" in p or "naikkan" in p or "terang" in p:
                atur_kecerahan(angka)
            elif "turun" in p or "turunkan" in p or "redup" in p:
                atur_kecerahan(-angka)
            else:
                ngomong("Mau naikkan atau turunkan kecerahan?")
                    
        elif "buka" in p:
            buka_aplikasi(p.replace("buka ", "").replace(" aplikasi", ""))
        elif "tutup" in p:
            nama = p.replace("tutup ", "").replace(" aplikasi", "")
            if minta_izin("tutup", f"Tutup aplikasi: {nama}", suara, wa_):
                tutup_aplikasi(nama)
            else:
                ngomong("Oke, dibatalkan.")
        elif "putar" in p:
            if "live" in p:
                judul = p.replace("putar live streaming ", "").replace("putar live ", "")
                putar_youtube(judul, tipe="live")
            else:
                judul = p.replace("putar ", "").replace(" youtube ", "").replace(" lagu ", "")
                putar_youtube(judul, tipe="video")
        elif "cari file" in p:
            cari_file(p.replace("cari file ", ""))
        elif "bersihkan" in p or "cleanup" in p:
            if minta_izin("bersihkan", "Hapus file sementara Windows", suara, wa_):
                cleanup_laptop()
            else:
                ngomong("Oke, dibatalkan.")
        elif "ringkas dokumen" in p:
            ringkas_dokumen(p.replace("ringkas dokumen ", ""))
        elif "kirim file" in p:
            nama = p.replace("kirim file ", "")
            if minta_izin("kirim_file", f"Kirim file lewat email: {nama}", suara, wa_):
                kirim_file(nama)
            else:
                ngomong("Oke, dibatalkan.")
        else:
            if saluran:
                ngomong(obrolan.ngobrol(saluran, perintah.strip()))
            else:
                tanya_ai(p)
    finally:
        asisten.set_pendengar(None)
        asisten.reset_stop()
    return ucapan

@app.get("/")
def index():
    return "Server Python Asisten Aktif!"

@app.get("/health")
def health():
    return jsonify(status="ok", build=BUILD_ID)

@app.post("/dokumen/buka")
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

# ---------- gerbang WhatsApp (WAHA): kirim notifikasi dari pill ----------
def _wa_ui(teks):
    try:
        kirim_kejadian("kartu", {"nada": "ok", "teks": teks})   # tampil di pill; hanya ada kalau antrean kejadian terpasang
    except NameError:
        print(f"[wa] {teks}", flush=True)

def _izin_wa_menunggu():
    req = _izin_aktif["req"]
    return bool(req and req.get("wa"))


def perintah_dari_wa(teks):
    """Pesan WhatsApp dari pemilik -> perintah asisten (sama seperti suara). Mengembalikan teks balasan."""
    req = _izin_aktif["req"]
    if req and req.get("wa"):
        jawab = _jawaban_suara(teks) or ("tolak" if teks.lower().strip() == "batal" else None)
        if not jawab:
            return "Asisten menunggu jawaban izin. Balas ya, tidak, atau selalu."
        req["jawab"] = jawab
        req["event"].set()
        return None   # hasil perintahnya dikirim oleh pemanggil minta_izin

    if not _kunci.acquire(blocking=False):
        return "Asisten masih mengerjakan perintah lain. Coba lagi sebentar."
    try:
        print(f"[wa] perintah: {teks}", flush=True)
        update_ui("memproses", f"WA: {teks}")
        asisten.set_diam(not SUARA_WA)
        try:
            ucapan = proses_perintah(teks, suara=False, wa_=True, saluran="wa")
        finally:
            asisten.set_diam(False)
        return _lapor_hasil(ucapan)
    except Exception as e:
        traceback.print_exc()
        update_ui("error", str(e), nada="bad")
        return f"Gagal menjalankan perintah: {e}"
    finally:
        _kunci.release()


@app.post("/wa/kirim")
def wa_kirim():
    if not wa.token_lokal_valid(request.headers.get("X-Pillow-Token", "")):
        return jsonify(ok=False), 403
    teks = str((request.get_json(silent=True) or {}).get("teks") or "")[:500]
    return jsonify(ok=bool(teks) and wa.kirim(teks))

@app.post("/media")
def media_dari_pill():
    # pill mengirim lagu yang sedang diputar, dipakai perintah "lagu apa ini", "jeda", "lagu berikutnya"
    if not wa.token_lokal_valid(request.headers.get("X-Pillow-Token", "")):
        return jsonify(ok=False), 403
    musik.lapor(request.get_json(silent=True) or {})
    return jsonify(ok=True)

@app.get("/lirik")
def ambil_lirik():
    judul = (request.args.get("judul") or "").strip()
    artis = (request.args.get("artis") or "").strip()
    try:
        durasi = int(request.args.get("durasi") or 0)
    except ValueError:
        durasi = 0
    if not judul:
        return jsonify(ok=False, baris=[])
    try:
        return jsonify(lirik.ambil(judul, artis, durasi))
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, baris=[], error=str(e))

@app.get("/status")
def status():
    s = _status_sekarang["status"]
    req = _izin_aktif["req"]
    izin = None
    if req:
        izin = {"id": req["id"], "teks": req["teks"], "suara": req["suara"]}
    return jsonify(
        status=s,
        teks=_status_sekarang["teks"],
        ui=_PETA_UI.get(s, "idle"),
        izin=izin,
        hasil=dict(_hasil_terakhir),
        kejadian_id=_kejadian_id[0],
        kejadian=_kejadian_sejak(request.args.get("sejak", type=int)),
    )

@app.post("/izin")
def jawab_izin():
    data = request.get_json(silent=True) or {}
    req = _izin_aktif["req"]
    jawab = data.get("jawab")
    if not req or data.get("id") != req["id"] or jawab not in ("izinkan", "tolak", "selalu"):
        return jsonify(ok=False, message="Tidak ada permintaan izin yang cocok."), 404
    req["jawab"] = jawab
    req["event"].set()
    return jsonify(ok=True)

@app.post("/izin/reset")
def reset_izin():
    _selalu.clear()
    _simpan_selalu()
    return jsonify(ok=True, message="Semua izin 'Selalu' dihapus.")

@app.post("/")
def terima_perintah():
    data = request.get_json(silent=True) or {}
    perintah = (data.get("perintah") or "").strip()
    if not perintah:
        return jsonify(ok=False, message="Perintah kosong."), 400
    if not _kunci.acquire(blocking=False):
        return jsonify(ok=False, message="Asisten masih mengerjakan perintah sebelumnya."), 429
    try:
        update_ui("memproses", f"Memproses: {perintah}")
        ucapan = proses_perintah(perintah, suara=False, saluran="ketik")
        pesan = _lapor_hasil(ucapan)
        return jsonify(ok=True, message=pesan)
    except Exception as e:
        traceback.print_exc()
        sys.stderr.flush()
        update_ui("error", str(e), nada="bad")
        return jsonify(ok=False, message=f"Error: {e}"), 500
    finally:
        _kunci.release()

@app.post("/stop")
def stop_suara():
    if _kunci.locked():
        asisten.hentikan_suara()
    return jsonify(ok=True, message="Suara dihentikan.")

@app.post("/shutdown")
def shutdown():
    threading.Timer(0.3, lambda: os._exit(0)).start()
    return jsonify(ok=True)

_suara = {"jalan": False}
_limit_terakhir = {"waktu": 0.0}

def _jeda_kalau_limit():
    if asisten.ambil_galat() == "limit":
        if time.time() - _limit_terakhir["waktu"] > 60:
            _limit_terakhir["waktu"] = time.time()
            update_ui("galat", "Jatah suara atau AI sedang habis. Coba lagi sebentar lagi.", nada="bad")
        time.sleep(8)
        return True
    return False

def loop_suara():
    tidur = not MULAI_BANGUN
    if tidur:
        update_ui("tidur", "Ucapkan 'Mulai'")
    else:
        update_ui("bangun", "Aku siap mendengarkan!")
    while _suara["jalan"]:
        if tidur:
            p = dengerin(3, ambang=AMBANG_TIDUR)
            if _jeda_kalau_limit():
                continue
            if _cocok(p, KATA_BANGUN, ambang=0.75):
                tidur = False
                ngomong("Aku bangun! Ada yang bisa dibantu?")
                update_ui("bangun", "Aku siap mendengarkan!")
            continue

        if _ngobrol["aktif"] and time.time() - _ngobrol["terakhir"] > DIAM_NGOBROL_DETIK:
            _mode_ngobrol(False)
            print("[obrolan] mode ngobrol selesai (diam)", flush=True)
        ngobrol_aktif = _ngobrol["aktif"]
        update_ui("mendengarkan", "Ngobrol... (ucapkan 'udahan' untuk selesai)" if ngobrol_aktif else "Mendengarkan...")
        p = dengerin(ambang=AMBANG_BANGUN, saring=not ngobrol_aktif)
        if _jeda_kalau_limit():
            continue
        if not p:
            continue
        if _ucapan_henti(p) and (time.time() - asisten.sedang_bicara["selesai"] < 4 or not musik.kenali(p)):
            continue   # "stop" telat sesudah Pillow selesai bicara: abaikan, jangan sampai menjeda musik
        maks = 2 if ngobrol_aktif else 5   # saat ngobrol, "aku susah tidur" bukan perintah tidur
        if _cocok(p, KATA_TIDUR, maks=maks):
            _mode_ngobrol(False)
            tidur = True
            ngomong("Oke, aku tidur dulu ya.")
            update_ui("tidur", "Aku sedang tidur...")
            continue
        if _cocok(p, KATA_KELUAR, maks=maks):
            ngomong("Sampai jumpa!")
            _suara["jalan"] = False
            break
        if ngobrol_aktif and _cocok(p, KATA_UDAHAN, maks=4):
            _mode_ngobrol(False)
            ngomong("Oke, makasih udah ngobrol. Aku balik ke mode perintah ya.")
            update_ui("bangun", "Aku siap mendengarkan!")
            continue
        if not ngobrol_aktif and _cocok(p, KATA_NGOBROL, maks=5):
            _mode_ngobrol(True)
            ngomong("Ayo! Mau ngobrol soal apa?")
            continue

        with _kunci:
            update_ui("memproses", f"Memproses: {p}")
            selesai = threading.Event()
            if HENTI_SAAT_BICARA:
                threading.Thread(target=_pantau_henti, args=(selesai,), daemon=True).start()
            try:
                ucapan = proses_perintah(p, suara=True, saluran="suara" if ngobrol_aktif else None)
                _lapor_hasil(ucapan)
            except Exception as e:
                traceback.print_exc()
                update_ui("error", str(e), nada="bad")
            finally:
                selesai.set()
        if _ngobrol["aktif"]:
            _ngobrol["terakhir"] = time.time()   # hitung diam 90 detik sejak Pillow selesai menjawab
        time.sleep(1)
    update_ui("berhenti", "Mode suara berhenti")

@app.post("/suara/mulai")
def suara_mulai():
    if not _suara["jalan"]:
        _suara["jalan"] = True
        threading.Thread(target=loop_suara, daemon=True).start()
    return jsonify(ok=True, message="Mode suara aktif.")

@app.post("/suara/berhenti")
def suara_berhenti():
    _suara["jalan"] = False
    return jsonify(ok=True, message="Mode suara dihentikan.")

@socketio.on("connect")
def handle_connect():
    print("Klien Socket.IO terhubung", flush=True)

if __name__ == "__main__":
    print(f"[server] build {BUILD_ID} di http://127.0.0.1:{PORT}", flush=True)
    wa.mulai(lambda n: asisten._rahasia(n), ke_ui=_wa_ui,   # gerbang WhatsApp
             perintah=perintah_dari_wa, izin_menunggu=_izin_wa_menunggu)
    dokumen.mulai_indeks()   # pindai nama file di latar belakang
    socketio.run(
        app,
        host="127.0.0.1",
        port=PORT,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )