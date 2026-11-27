"""Kontrol musik untuk Pillow Island: jeda, lanjutkan, lagu berikutnya/sebelumnya, dan "lagu apa ini".

- Jeda/lanjut/pindah lagu memakai tombol media Windows (sama seperti tombol di keyboard), jadi bekerja di
  Spotify, YouTube di Brave, dan pemutar lain yang muncul di kontrol media Windows.
- Judul lagu dan status (diputar/dijeda) dikirim oleh pill lewat POST /media (pill membacanya dari kontrol
  media Windows). Kalau pill tidak berjalan, perintah tetap jalan, hanya tanpa menyebut judul lagu.
"""
import re
import time

VK = {"play_pause": 0xB3, "next": 0xB0, "prev": 0xB1}
KEYEVENTF_KEYUP = 0x0002

# ------------------------------------------------------------------ info lagu dari pill
# Pill (pillow-island) sudah membaca lagu yang sedang diputar lewat Rust setiap detik dan mengirimnya ke
# server (POST /media). Di sini cukup disimpan. Kalau pill tidak berjalan, info lagu tidak tersedia,
# tapi jeda/lanjut/pindah lagu tetap bekerja lewat tombol media.
SEGAR_DETIK = 12
_terakhir = {"data": None, "waktu": 0.0}


def lapor(data):
    """Dipanggil server.py saat pill mengirim info media."""
    _terakhir["data"] = {
        "aktif": bool(data.get("aktif")),
        "judul": str(data.get("judul") or "").strip()[:200],
        "artis": str(data.get("artis") or "").strip()[:200],
        "diputar": bool(data.get("diputar")),
        "app": nama_app(str(data.get("app") or "")),
    }
    _terakhir["waktu"] = time.time()


def _tekan(aksi):
    import ctypes
    u = ctypes.windll.user32
    vk = VK[aksi]
    u.keybd_event(vk, 0, 0, 0)
    u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


# Bisa diganti saat pengujian
tekan = _tekan
jeda_pindah = 1.8   # detik menunggu pemutar berganti lagu dan pill melaporkan judul baru


def info():
    """{'judul', 'artis', 'diputar': bool, 'app'} atau None kalau tidak ada media / pill tidak berjalan."""
    d = _terakhir["data"]
    if not d or time.time() - _terakhir["waktu"] > SEGAR_DETIK:
        return None
    if not d["aktif"] or not (d["judul"] or d["artis"]):
        return None
    return {k: d[k] for k in ("judul", "artis", "diputar", "app")}


def nama_app(aumid):
    """'Spotify.exe' -> 'Spotify', 'Brave' -> 'Brave', 'SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify' -> 'Spotify'."""
    a = aumid.lower()
    for kunci, nama in (("spotify", "Spotify"), ("brave", "Brave"), ("chrome", "Chrome"), ("msedge", "Edge"),
                        ("opera", "Opera"), ("firefox", "Firefox"), ("zunemusic", "Media Player"),
                        ("youtube", "YouTube Music"), ("vlc", "VLC")):
        if kunci in a:
            return nama
    nama = re.split(r"[!\\/]", aumid)[-1]
    return nama[:-4] if nama.lower().endswith(".exe") else nama


def gambarkan(m):
    """Kalimat untuk diucapkan: 'Hati-Hati di Jalan oleh Tulus, di Spotify'."""
    teks = m["judul"] or "Tanpa judul"
    if m["artis"]:
        teks += f" oleh {m['artis']}"
    if m["app"]:
        teks += f", di {m['app']}"
    return teks


# ------------------------------------------------------------------ mengenali perintah
_POLA = [
    ("info", r"\blagu apa\b|\bjudul lagu\w*\b|\blagu (?:ini|sekarang) (?:apa|judulnya)\b|\bapa judul\w* lagu\w*\b"
             r"|\b(?:sedang|lagi) (?:diputar|memutar|main) apa\b|\bapa yang (?:sedang |lagi )?diputar\b"),
    ("next", r"\b(?:lagu|musik)\s+(?:berikutnya|selanjutnya|lain|lainnya)\b|\bganti lagu\b|\blewati\b|\bskip\b|\bnext\b"),
    ("prev", r"\b(?:lagu|musik)\s+(?:sebelumnya|tadi)\b|\bprevious\b|\bprev\b|\bkembali ke lagu\b"),
    ("jeda", r"^(?:jeda|pause|stop)\b|\b(?:jeda|jedakan|pause|hentikan|berhentikan|stop|matikan)\s+(?:lagu|musik|musiknya|lagunya)\b"
             r"|\b(?:lagu|musik)\w*\s+(?:dijeda|di jeda|dihentikan|di pause)\b"),
    ("lanjut", r"^(?:lanjutkan|lanjut|resume|play)(?:\s+(?:lagu|musik)\w*)?$|\b(?:putar|mainkan|lanjutkan|nyalakan)\s+lagi\b"
               r"|\b(?:lanjutkan|nyalakan|mainkan)\s+(?:lagu|musik)\w*$"),
]


def kenali(teks):
    """Kembalikan 'info' / 'next' / 'prev' / 'jeda' / 'lanjut', atau None kalau bukan perintah musik."""
    t = re.sub(r"[^\w\s]", " ", teks.lower())
    t = re.sub(r"\s+", " ", t).strip()
    for aksi, pola in _POLA:
        if re.search(pola, t):
            return aksi
    return None


# ------------------------------------------------------------------ menjalankan perintah
def jalankan(aksi):
    """Jalankan perintah musik, kembalikan kalimat balasan."""
    if aksi == "info":
        m = info()
        if not m:
            return "Sepertinya tidak ada lagu yang sedang diputar (atau pill sedang tidak berjalan)."
        return ("Sedang diputar: " if m["diputar"] else "Sedang dijeda: ") + gambarkan(m) + "."

    if aksi in ("jeda", "lanjut"):
        m = info()
        if m is None:
            tekan("play_pause")                       # status tidak terbaca: cukup tekan play/pause
            return "Oke, musik dijeda." if aksi == "jeda" else "Oke, musik dilanjutkan."
        if aksi == "jeda" and not m["diputar"]:
            return "Musiknya sudah dijeda."
        if aksi == "lanjut" and m["diputar"]:
            return f"Musik sudah diputar: {gambarkan(m)}."
        tekan("play_pause")
        return f"Musik dijeda: {m['judul']}." if aksi == "jeda" else f"Melanjutkan {gambarkan(m)}."

    if aksi in ("next", "prev"):
        sebelum = info()
        tekan(aksi)
        time.sleep(jeda_pindah)
        sesudah = info()
        label = "Lagu berikutnya" if aksi == "next" else "Lagu sebelumnya"
        if sesudah and (not sebelum or sesudah["judul"] != sebelum["judul"]):
            return f"{label}: {gambarkan(sesudah)}."
        if aksi == "prev" and sesudah and sebelum and sesudah["judul"] == sebelum["judul"]:
            return "Lagu diulang dari awal."           # pemutar biasanya mengulang lagu dulu kalau sudah lewat beberapa detik
        return f"Oke, {label.lower()}."

    return "Perintah musik tidak dikenal."
