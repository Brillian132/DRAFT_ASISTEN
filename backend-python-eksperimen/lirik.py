"""Pengambil lirik bersinkron dari LRCLIB (https://lrclib.net).

LRCLIB gratis dan tidak butuh API key. Lirik diambil saat dibutuhkan lalu disimpan di
cache lokal (%APPDATA%\\PillowIsland\\lirik) supaya lagu yang sama tidak dicari ulang.
Hasilnya berupa daftar baris [waktu_ms, teks] yang dipakai pill untuk menampilkan lirik berjalan.
"""
import os
import re
import json
import time
import hashlib
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://lrclib.net/api"
UA = "PillowIsland/0.2 (asisten pribadi di desktop)"
TOLERANSI_DURASI = 15      # detik; versi lagu yang durasinya terlalu beda (live/remix) dilewati
BATAS_WAKTU_TOTAL = 14     # detik; batas seluruh pencarian untuk satu lagu
TTL_GAGAL = 600            # detik; lagu yang tidak ketemu tidak dicari ulang selama ini

_gagal = {}                # kunci -> waktu gagal terakhir (hanya di memori)


# ---------------------------------------------------------------- cache
def _folder_cache():
    try:
        import asisten   # impor ditunda supaya modul ini bisa diuji sendiri
        dasar = asisten._folder_appdata()
    except Exception:
        dasar = ""
    dasar = dasar or os.path.expanduser("~")
    return os.path.join(dasar, "PillowIsland", "lirik")


def _file_cache(kunci):
    nama = hashlib.md5(kunci.encode("utf-8")).hexdigest() + ".json"
    return os.path.join(_folder_cache(), nama)


def _baca_cache(kunci):
    try:
        with open(_file_cache(kunci), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _simpan_cache(kunci, data):
    try:
        os.makedirs(_folder_cache(), exist_ok=True)
        with open(_file_cache(kunci), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"[lirik] gagal menyimpan cache: {e}", flush=True)


# ---------------------------------------------------------------- HTTP
def _get(jalur, params, timeout=8):
    url = f"{BASE}/{jalur}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# ---------------------------------------------------------------- pembersih judul
_BUANG = re.compile(r"\s*[\(\[\{【（].*?[\)\]\}】）]")        # isi dalam kurung: (Official Video), [Lyrics]
_EKOR = re.compile(r"\s*[|｜].*$")                            # "| Official Music Video"
_FEAT = re.compile(r"\s+(feat\.?|ft\.?|featuring)\s+.*$", re.I)
_ARTIS_SAMPAH = re.compile(r"\s*(-\s*topic|vevo|official)\s*$", re.I)


def kandidat(judul, artis):
    """Buat beberapa kemungkinan pasangan (artis, judul) yang layak dicari, urut dari yang paling mungkin."""
    j = _BUANG.sub("", judul or "")
    j = _EKOR.sub("", j).strip()
    a = _ARTIS_SAMPAH.sub("", artis or "").strip()

    hasil = []

    def tambah(x, y):
        x = (x or "").strip()
        y = _FEAT.sub("", (y or "").strip()).strip()
        if y and (x, y) not in hasil:
            hasil.append((x, y))

    bagian = re.split(r"\s[-–—]\s", j, maxsplit=1)
    if len(bagian) == 2:
        p1, p2 = bagian[0].strip(), bagian[1].strip()
        if a and (a.lower() in p1.lower() or p1.lower() in a.lower()):
            tambah(p1, p2)       # format "Artis - Judul"
            tambah(a, p2)
        else:
            tambah(a, j)         # judul apa adanya
            tambah(p1, p2)       # mungkin "Artis - Judul" dan kolom artis cuma nama channel
            tambah(a, p1)        # mungkin "Judul - Keterangan"
    else:
        tambah(a, j)

    if not hasil and judul:
        tambah(a, judul)
    return hasil[:4]


# ---------------------------------------------------------------- pencarian
def _pilih(daftar, durasi):
    layak = [x for x in (daftar or []) if x.get("syncedLyrics")]
    if not layak:
        return None
    if durasi:
        layak.sort(key=lambda x: abs((x.get("duration") or 0) - durasi))
        if abs((layak[0].get("duration") or 0) - durasi) <= TOLERANSI_DURASI:
            return layak[0]
        return None
    return layak[0]


def _cari(artis, judul, durasi):
    # 1. pencarian tepat (LRCLIB meminta durasi cocok sekitar +-2 detik)
    if artis:
        params = {"track_name": judul, "artist_name": artis}
        if durasi:
            params["duration"] = int(durasi)
        try:
            d = _get("get", params)
            if d and d.get("syncedLyrics"):
                return d
        except Exception as e:
            print(f"[lirik] /get gagal: {e}", flush=True)

    # 2. pencarian umum, ambil yang durasinya paling dekat
    q = {"track_name": judul}
    if artis:
        q["artist_name"] = artis
    return _pilih(_get("search", q), durasi)


_WAKTU = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


def parse_lrc(teks):
    """Ubah teks format LRC menjadi daftar [waktu_ms, teks] yang terurut."""
    baris = []
    for mentah in (teks or "").splitlines():
        cocok = list(_WAKTU.finditer(mentah))
        if not cocok:
            continue
        isi = _WAKTU.sub("", mentah).strip()
        for m in cocok:
            menit, detik = int(m.group(1)), int(m.group(2))
            pecahan = (m.group(3) or "0").ljust(3, "0")[:3]
            baris.append([(menit * 60 + detik) * 1000 + int(pecahan), isi])
    baris.sort(key=lambda x: x[0])
    return baris


def ambil(judul, artis, durasi):
    """Titik masuk: kembalikan {"ok": bool, "baris": [[ms, teks], ...]}."""
    kunci = f"{artis}|{judul}|{int(durasi or 0)}".lower()

    tersimpan = _baca_cache(kunci)
    if tersimpan and tersimpan.get("baris"):
        return {"ok": True, "baris": tersimpan["baris"], "dari_cache": True}

    if time.time() - _gagal.get(kunci, 0) < TTL_GAGAL:
        return {"ok": False, "baris": []}

    batas = time.time() + BATAS_WAKTU_TOTAL
    for a, j in kandidat(judul, artis):
        if time.time() > batas:
            break
        try:
            d = _cari(a, j, durasi)
        except Exception as e:
            print(f"[lirik] pencarian gagal ({a} / {j}): {e}", flush=True)
            continue
        if d:
            baris = parse_lrc(d.get("syncedLyrics"))
            if baris:
                _simpan_cache(kunci, {"baris": baris})
                return {"ok": True, "baris": baris, "dari_cache": False}

    _gagal[kunci] = time.time()
    return {"ok": False, "baris": []}