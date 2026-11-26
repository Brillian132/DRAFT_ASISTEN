"""Pencarian dokumen untuk Pillow Island.

Cara kerja:
  1. Saat server menyala, nama file di folder pilihan (bawaan: seluruh D:\\, Dokumen, Unduhan, Desktop)
     dipindai di latar belakang dan disimpan sebagai indeks (cache di %APPDATA%\\PillowIsland).
  2. Pencarian memakai kata-kata dari judul yang diucapkan: cocok persis, awalan kata, atau salah
     ketik ringan. Nama folder ikut membantu, dan file yang baru diubah sedikit diutamakan.
  3. Hasil teratas disimpan supaya bisa dipilih lewat suara ("buka yang kedua").

Pengaturan ada di %APPDATA%\\PillowIsland\\dokumen.json (dibuat otomatis, boleh diedit).
Hanya nama file yang diindeks, bukan isi dokumen.
"""
import os
import re
import json
import time
import gzip
import math
import difflib
import threading
import subprocess
import unicodedata
from collections import defaultdict

NAMA_APP = "PillowIsland"

CONFIG_BAWAAN = {
    # "@Dokumen", "@Unduhan", "@Desktop" = folder khusus Windows milik pengguna
    "folder": ["D:\\", "@Dokumen", "@Unduhan", "@Desktop"],
    "abaikan": [
        "node_modules", ".git", ".svn", ".hg", "target", "__pycache__", "$recycle.bin",
        "system volume information", "site-packages", ".venv", "venv", "appdata", "windows",
        "program files", "program files (x86)", "programdata", ".next", ".gradle", ".idea",
        ".vscode", ".cache", "cache", "caches",
    ],
    "ekstensi": [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".txt", ".md",
        ".rtf", ".odt", ".ods", ".odp", ".csv", ".epub",
    ],
    "perbarui_tiap_jam": 6,
}

# nama file yang hampir selalu hanya "sampah" proyek program
NAMA_DIABAIKAN = {"readme", "license", "licence", "changelog", "notice", "copying", "authors", "contributing", "version"}

KATA_EKSTENSI = {
    "pdf": (".pdf",), "word": (".doc", ".docx"), "docx": (".docx",), "doc": (".doc", ".docx"),
    "excel": (".xls", ".xlsx", ".xlsm", ".csv"), "xlsx": (".xlsx",), "xls": (".xls", ".xlsx"), "csv": (".csv",),
    "powerpoint": (".ppt", ".pptx"), "ppt": (".ppt", ".pptx"), "pptx": (".pptx",), "txt": (".txt",),
}

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# ------------------------------------------------------------------ lokasi & pengaturan
def _csidl(kode):
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, kode, None, 0, buf)
        return buf.value
    except Exception:
        return ""


def _appdata():
    return _csidl(0x001A) or os.environ.get("APPDATA", "") or os.path.expanduser("~")


def _file_config():
    return os.path.join(_appdata(), NAMA_APP, "dokumen.json")


def _file_cache():
    return os.path.join(_appdata(), NAMA_APP, "indeks-dokumen.json.gz")


def muat_config():
    cfg = json.loads(json.dumps(CONFIG_BAWAAN))
    path = _file_config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in CONFIG_BAWAAN})
    except FileNotFoundError:
        try:   # tulis pengaturan bawaan supaya mudah diedit
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(CONFIG_BAWAAN, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
    except Exception as e:
        print(f"[dokumen] pengaturan tidak terbaca, memakai bawaan: {e}", flush=True)
    return cfg


def _folder_khusus(nama):
    n = nama.lstrip("@").lower()
    home = os.path.expanduser("~")
    if n == "dokumen":
        return _csidl(0x0005) or os.path.join(home, "Documents")
    if n == "desktop":
        return _csidl(0x0010) or os.path.join(home, "Desktop")
    if n in ("unduhan", "downloads"):
        return os.path.join(home, "Downloads")
    return ""


def lokasi_pindai(cfg):
    hasil, lihat = [], set()
    for f in cfg["folder"]:
        p = _folder_khusus(f) if f.startswith("@") else f
        if p and os.path.isdir(p) and os.path.normcase(os.path.abspath(p)) not in lihat:
            lihat.add(os.path.normcase(os.path.abspath(p)))
            hasil.append(p)
    return hasil


# ------------------------------------------------------------------ pemecah kata
_PISAH = re.compile(r"[^0-9a-z]+")
_HURUF_BESAR = re.compile(r"(?<=[a-z])(?=[A-Z])")


def token(teks):
    t = _HURUF_BESAR.sub(" ", teks)
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [x for x in _PISAH.split(t) if x]


def _unik(daftar):
    lihat, hasil = set(), []
    for x in daftar:
        if x not in lihat:
            lihat.add(x)
            hasil.append(x)
    return hasil


# ------------------------------------------------------------------ pemindaian
def pindai(lokasi, abaikan, ekstensi, berhenti=None, jeda=True):
    """Kembalikan daftar (path, mtime, ukuran) untuk file dokumen di bawah lokasi."""
    abaikan = {a.lower() for a in abaikan}
    ekstensi = {e.lower() for e in ekstensi}
    hasil, lihat, hitung = [], set(), 0
    for akar in lokasi:
        tumpukan = [akar]
        while tumpukan:
            if berhenti is not None and berhenti.is_set():
                return hasil
            d = tumpukan.pop()
            try:
                with os.scandir(d) as it:
                    for e in it:
                        hitung += 1
                        if jeda and hitung % 3000 == 0:
                            time.sleep(0.003)    # jangan menghabiskan disk saat dipakai
                        try:
                            if e.is_dir(follow_symlinks=False):
                                n = e.name.lower()
                                if n in abaikan or n.startswith(("$", ".")):
                                    continue
                                tumpukan.append(e.path)
                            elif e.is_file(follow_symlinks=False):
                                nama, ext = os.path.splitext(e.name)
                                if ext.lower() not in ekstensi or e.name.startswith("~$"):
                                    continue
                                if nama.lower() in NAMA_DIABAIKAN:
                                    continue
                                kunci = os.path.normcase(e.path)
                                if kunci in lihat:
                                    continue
                                lihat.add(kunci)
                                st = e.stat(follow_symlinks=False)
                                hasil.append((e.path, st.st_mtime, st.st_size))
                        except OSError:
                            continue
            except OSError:
                continue
    return hasil


# ------------------------------------------------------------------ indeks
class _Data:
    """Struktur siap cari (tidak diubah setelah dibuat, jadi aman dibaca dari banyak thread)."""
    def __init__(self, daftar):
        self.daftar = daftar
        self.post = defaultdict(list)           # kata -> daftar nomor file
        for i, (path, _mt, _sz) in enumerate(daftar):
            for t in set(token(os.path.splitext(os.path.basename(path))[0])):
                self.post[t].append(i)
        self.kosakata = list(self.post.keys())
        self.per_huruf = defaultdict(list)      # huruf pertama -> kata (untuk salah ketik)
        for t in self.kosakata:
            if len(t) >= 3:
                self.per_huruf[t[0]].append(t)


class Indeks:
    def __init__(self):
        self.data = None
        self.sedang = False
        self.diperbarui = 0.0
        self.berhenti = threading.Event()
        self._kunci = threading.Lock()

    def pasang(self, daftar):
        self.data = _Data(daftar)
        self.diperbarui = time.time()

    def muat_cache(self):
        try:
            with gzip.open(_file_cache(), "rt", encoding="utf-8") as f:
                isi = json.load(f)
            daftar = [(p, float(m), int(s)) for p, m, s in isi["daftar"] if os.path.exists(p)]
            self.pasang(daftar)
            self.diperbarui = float(isi.get("waktu", time.time()))
            print(f"[dokumen] indeks dari cache: {len(daftar)} file", flush=True)
            return True
        except Exception:
            return False

    def simpan_cache(self, daftar):
        try:
            os.makedirs(os.path.dirname(_file_cache()), exist_ok=True)
            with gzip.open(_file_cache(), "wt", encoding="utf-8") as f:
                json.dump({"waktu": time.time(), "daftar": daftar}, f)
        except OSError as e:
            print(f"[dokumen] gagal menyimpan cache: {e}", flush=True)

    def bangun(self):
        if not self._kunci.acquire(blocking=False):
            return          # sudah ada pemindaian yang berjalan
        self.sedang = True
        try:
            cfg = muat_config()
            lokasi = lokasi_pindai(cfg)
            mulai = time.time()
            print(f"[dokumen] memindai: {lokasi}", flush=True)
            daftar = pindai(lokasi, cfg["abaikan"], cfg["ekstensi"], self.berhenti)
            if self.berhenti.is_set():
                return
            self.pasang(daftar)
            self.simpan_cache(daftar)
            print(f"[dokumen] indeks selesai: {len(daftar)} file dalam {time.time() - mulai:.0f} detik", flush=True)
        except Exception as e:
            print(f"[dokumen] pemindaian gagal: {e}", flush=True)
        finally:
            self.sedang = False
            self._kunci.release()


_I = Indeks()
_terakhir = {"hasil": [], "waktu": 0.0, "query": ""}


def mulai_indeks():
    """Dipanggil sekali saat server menyala: muat cache lalu pindai ulang di latar belakang."""
    _I.muat_cache()

    def pekerja():
        while not _I.berhenti.is_set():
            _I.bangun()
            jam = max(1, int(muat_config().get("perbarui_tiap_jam", 6)))
            if _I.berhenti.wait(jam * 3600):
                break
    threading.Thread(target=pekerja, daemon=True).start()


def perbarui_indeks():
    threading.Thread(target=_I.bangun, daemon=True).start()


def status_indeks():
    return {"siap": _I.data is not None, "jumlah": len(_I.data.daftar) if _I.data else 0,
            "sedang": _I.sedang, "diperbarui": _I.diperbarui}


# ------------------------------------------------------------------ pencarian
def _bobot_kata(q, st):
    """Kata di indeks yang cocok dengan kata pencarian q -> bobot (1.0 persis, lebih kecil kalau mirip)."""
    cocok = {}
    if q in st.post:
        cocok[q] = 1.0
    if len(q) >= 3:
        for t in st.kosakata:
            if t == q:
                continue
            if t.startswith(q):
                cocok[t] = 0.85 if len(q) / len(t) >= 0.5 else 0.6
            elif len(t) >= 4 and q.startswith(t):
                cocok[t] = 0.7
    if q not in st.post and len(q) >= 4:    # salah ketik / salah dengar ringan
        for t in st.per_huruf.get(q[0], ()):
            if abs(len(t) - len(q)) > 2 or t in cocok:
                continue
            sm = difflib.SequenceMatcher(None, q, t)
            if sm.real_quick_ratio() >= 0.8 and sm.quick_ratio() >= 0.8:
                r = sm.ratio()
                if r >= 0.8:
                    cocok[t] = r * 0.8
    return cocok


def _pisah_ekstensi(qt):
    ext, sisa = [], []
    for t in qt:
        if t in KATA_EKSTENSI:
            ext.extend(KATA_EKSTENSI[t])
        else:
            sisa.append(t)
    if not sisa:                     # pencarian hanya "pdf": anggap itu bagian dari judul
        return [], qt
    return sorted(set(ext)), sisa


def cari(query, maks=3, st=None):
    """Kembalikan (hasil, total). hasil = daftar dict diurutkan dari yang paling relevan."""
    st = st or _I.data
    qt = _unik(token(query))
    if st is None or not qt:
        return [], 0
    ext, qt = _pisah_ekstensi(qt)

    cand = defaultdict(dict)         # nomor file -> {indeks kata pencarian: bobot}
    for qi, q in enumerate(qt):
        for t, w in _bobot_kata(q, st).items():
            for i in st.post[t]:
                if w > cand[i].get(qi, 0):
                    cand[i][qi] = w

    perlu = len(qt) if len(qt) <= 2 else math.ceil(len(qt) * 0.6)
    awal = sorted(cand.items(), key=lambda kv: (len(kv[1]), sum(kv[1].values())), reverse=True)[:400]
    sekarang = time.time()
    nilai, total = [], 0
    for i, cocok in awal:
        path, mtime, ukuran = st.daftar[i]
        if ext and os.path.splitext(path)[1].lower() not in ext:
            continue
        nama = os.path.splitext(os.path.basename(path))[0]
        nt = token(nama)
        # kata yang tidak ada di nama tetapi ada di nama folder (maksimal 3 tingkat) dihitung setengah
        folder_kata, d = set(), os.path.dirname(path)
        for _ in range(3):
            folder_kata.update(token(os.path.basename(d)))
            d = os.path.dirname(d)
        bobot = dict(cocok)
        for qi, q in enumerate(qt):
            if qi not in bobot and q in folder_kata:
                bobot[qi] = 0.6
        if len(bobot) < perlu:
            continue
        total += 1
        dasar = sum(bobot.values())
        cakupan = len(bobot) / len(qt)
        rapat = len(cocok) / max(len(nt), 1)
        urutan = 0.0
        if len(qt) >= 2:
            pos = [nt.index(q) for qi, q in enumerate(qt) if qi in cocok and q in nt]
            if len(pos) >= 2 and pos == sorted(pos):
                urutan = 0.5
        umur = max(0.0, (sekarang - mtime) / 86400)
        baru = 0.4 / (1 + umur / 60)
        skor = 2.0 * dasar + 2.0 * cakupan + 0.8 * rapat + urutan + baru
        nilai.append((skor, i))
    # skor sama: utamakan folder yang lebih dangkal, lalu yang lebih baru diubah
    nilai.sort(key=lambda t: (-round(t[0], 2), st.daftar[t[1]][0].count(os.sep), -st.daftar[t[1]][1]))

    hasil, lihat = [], set()
    for skor, i in nilai:
        path, mtime, ukuran = st.daftar[i]
        kunci = (os.path.basename(path).lower(), ukuran)
        if kunci in lihat:           # salinan identik di folder lain: tampilkan satu saja
            continue
        lihat.add(kunci)
        hasil.append({"path": path, "skor": round(skor, 2), "mtime": mtime, "ukuran": ukuran})
        if len(hasil) >= maks:
            break
    return hasil, total


# ------------------------------------------------------------------ tampilan hasil
def _ukuran(b):
    for satuan in ("B", "KB", "MB", "GB"):
        if b < 1024 or satuan == "GB":
            return f"{b:.0f} {satuan}" if satuan == "B" else f"{b:.1f} {satuan}"
        b /= 1024


def _pendekkan(path, maks=46):
    if len(path) <= maks:
        return path
    bagian = path.split(os.sep)
    if len(bagian) <= 3:
        return path[:maks - 1] + "…"
    return os.sep.join([bagian[0], "…"] + bagian[-2:])


def format_hasil(hasil):
    """Ubah hasil cari() menjadi data siap tampil (nomor dimulai dari 0)."""
    keluar = []
    for n, h in enumerate(hasil):
        path = h["path"]
        d = time.localtime(h["mtime"])
        keluar.append({
            "i": n,
            "nama": os.path.basename(path),
            "ext": os.path.splitext(path)[1].lower(),
            "folder": _pendekkan(os.path.dirname(path)),
            "ukuran": _ukuran(h["ukuran"]),
            "diubah": f"{d.tm_mday} {BULAN[d.tm_mon - 1]} {d.tm_year}",
        })
    return keluar


def jelas_unggul(hasil):
    """True kalau hasil teratas jauh lebih baik dari yang kedua (aman dibuka langsung)."""
    if not hasil:
        return False
    if len(hasil) == 1:
        return True
    return hasil[0]["skor"] >= hasil[1]["skor"] * 1.35


def nama_ucapan(path, maks=60):
    """Nama file yang enak diucapkan: tanpa ekstensi, garis bawah/strip jadi spasi."""
    n = os.path.splitext(os.path.basename(path))[0]
    n = re.sub(r"[_\-\.]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n if len(n) <= maks else n[:maks].rsplit(" ", 1)[0]


# ------------------------------------------------------------------ hasil terakhir & aksi
def simpan_terakhir(hasil, query):
    _terakhir.update({"hasil": list(hasil), "waktu": time.time(), "query": query})


def terakhir_segar(menit=10):
    if _terakhir["hasil"] and time.time() - _terakhir["waktu"] <= menit * 60:
        return _terakhir["hasil"]
    return None


def aksi(nomor, mode="buka"):
    """Buka file (mode 'buka') atau tampilkan di File Explorer (mode 'folder'). -> (ok, pesan)"""
    hasil = terakhir_segar(30)
    if hasil is None or not (0 <= nomor < len(hasil)):
        return False, "Hasil pencarian itu sudah tidak ada. Cari lagi ya."
    path = hasil[nomor]["path"]
    if not os.path.exists(path):
        return False, "File itu sudah tidak ditemukan di tempatnya."
    try:
        if mode == "folder":
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        else:
            os.startfile(path)
        return True, "OK"
    except Exception as e:
        return False, f"Gagal membuka file: {e}"