"""Gerbang WhatsApp (WAHA) untuk Pillow Island: kirim notifikasi ke pemilik dan terima perintah darinya.

Perintah bawaan (status, kunci, matikan, batal, bantuan) ditangani di sini. Pesan lain dari pemilik diteruskan ke
pemroses perintah asisten (sama seperti perintah suara), misalnya "buka youtube" atau "volume naik 20".

Rahasia di rahasia.json: WA_API_KEY (kunci WAHA) dan WA_HMAC_KEY (kunci tanda tangan webhook). Tanpa keduanya fitur mati.
Di dashboard WAHA, webhook: http://host.docker.internal:8009/wa/webhook , event: message , HMAC key = WA_HMAC_KEY.
"""
import os
import re
import json
import hmac
import time
import hashlib
import secrets
import threading
import subprocess
import traceback
from collections import deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import requests

WAHA = "http://127.0.0.1:3000"
SESI = "default"
PORT = 8009
HOST = "127.0.0.1"  # shortcut: hanya loopback; kalau webhook tidak sampai dari kontainer, pakai 0.0.0.0 (tetap aman karena HMAC)
MAKS_BODY = 256 * 1024
KONFIRMASI_DETIK = 60
BATAS_KIRIM = (60, 600)  # maks 60 pesan per 10 menit (dinaikkan dari 20 karena WA sekarang dipakai ngobrol)
MAKS_SALAH_PASANG = 5
BANTUAN = "Perintah: status, kunci, matikan, batal, bantuan"
BANTUAN_ASISTEN = ("Selain itu, ketik perintah seperti ke asisten suara. Contoh: buka youtube, "
                   "putar lofi, volume naik 20, tutup tab youtube, lihat layar, cari dokumen laporan. "
                   "Pesan lain dianggap obrolan, jadi ngobrol santai saja.")


class _Teruskan:
    """Penanda dari _proses(): teks ini diteruskan ke pemroses perintah asisten, di luar kunci gerbang."""
    def __init__(self, teks):
        self.teks = teks


def _file_pemilik():
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PillowIsland", "wa.json")


def _status():
    try:
        import ctypes

        class S(ctypes.Structure):
            _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("persen", ctypes.c_ubyte),
                        ("sys", ctypes.c_ubyte), ("sisa", ctypes.c_ulong), ("penuh", ctypes.c_ulong)]
        s = S()
        ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))
        persen = "tidak diketahui" if s.persen == 255 else f"{s.persen}%"
        return f"Laptop menyala. Baterai {persen}, {'sedang dicas' if s.ac == 1 else 'memakai baterai'}."
    except Exception:
        return "Laptop menyala."


def _jalankan(nama):
    perintah = {"kunci": ["rundll32.exe", "user32.dll,LockWorkStation"],
                "matikan": ["shutdown", "/s", "/t", "30"],
                "batal_matikan": ["shutdown", "/a"]}[nama]  # daftar tertutup: tidak ada perintah dari luar yang dijalankan
    subprocess.run(perintah, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class Gerbang:
    def __init__(self, api_key, hmac_key, file_pemilik=None, post=requests.post, jalankan=_jalankan,
                 ke_ui=print, sekarang=time.time, perintah=None, izin_menunggu=None):
        self.api_key, self.hmac_key = api_key, hmac_key
        self.file, self.post, self.jalankan, self.ke_ui, self.sekarang = file_pemilik or _file_pemilik(), post, jalankan, ke_ui, sekarang
        self.pemilik = self._muat()
        self.kode_pasang, self.salah = None, 0
        if not self.pemilik:
            self._kode_baru()
        self.tertunda = None  # (jenis "matikan"/"layar", kode, kedaluwarsa, teks asli)
        self.sudah = deque(maxlen=200)
        self.log_kirim = deque()
        self.kunci = threading.Lock()
        self.perintah = perintah                              # perintah(teks) -> balasan atau None
        self.izin_menunggu = izin_menunggu or (lambda: False)  # True kalau asisten sedang menunggu jawaban izin lewat WA

    def _muat(self):
        try:
            with open(self.file, encoding="utf-8") as f:
                return json.load(f).get("pemilik")
        except (OSError, ValueError):
            return None

    def _simpan(self):
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump({"pemilik": self.pemilik}, f)

    def _kode_baru(self):
        self.kode_pasang, self.salah = f"{secrets.randbelow(10**6):06d}", 0

    def valid(self, body, header):
        """Tanda tangan webhook WAHA: HMAC-SHA512 (hex) dari isi mentah. Tanpa kunci atau header, selalu ditolak."""
        if not self.hmac_key or not header:
            return False
        harapan = hmac.new(self.hmac_key.encode(), body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(harapan.encode(), header.strip().lower().encode())

    def kirim(self, teks):
        if not self.pemilik:
            return False
        with self.kunci:
            now = self.sekarang()
            while self.log_kirim and now - self.log_kirim[0] > BATAS_KIRIM[1]:
                self.log_kirim.popleft()
            if len(self.log_kirim) >= BATAS_KIRIM[0]:
                return False
            self.log_kirim.append(now)
        try:
            r = self.post(f"{WAHA}/api/sendText", headers={"X-Api-Key": self.api_key}, timeout=10,
                          json={"session": SESI, "chatId": self.pemilik, "text": str(teks)[:1000]})
            return bool(r.ok)
        except Exception as e:
            print(f"[wa] gagal mengirim: {e}", flush=True)
            return False

    def _proses(self, env):
        """Kembalikan teks balasan (atau None). Seluruh keputusan kepercayaan ada di sini."""
        if env.get("event") != "message":
            return None
        p = env.get("payload") or {}
        pengirim, teks = p.get("from"), str(p.get("body") or "").strip()[:200]
        if p.get("fromMe") or not isinstance(pengirim, str) or not teks or pengirim.endswith("@g.us"):
            return None
        id_ = p.get("id") or f"{pengirim}|{teks}|{env.get('timestamp')}"
        with self.kunci:
            if id_ in self.sudah:  # WAHA mengirim ulang kalau tidak dijawab cepat
                return None
            self.sudah.append(id_)
            kata = teks.lower().split()

            if not self.pemilik:  # pairing sekali: kode hanya terlihat di layar laptop
                if len(kata) == 2 and kata[0] == "pasang" and hmac.compare_digest(kata[1].encode(), self.kode_pasang.encode()):
                    self.pemilik = pengirim
                    self._simpan()
                    return "Terpasang. " + BANTUAN + (". " + BANTUAN_ASISTEN if self.perintah else "")
                if kata and kata[0] == "pasang":
                    self.salah += 1
                    if self.salah >= MAKS_SALAH_PASANG:
                        self._kode_baru()
                return None
            if pengirim != self.pemilik:
                return None

            # asisten sedang menanyakan izin lewat WA: jawaban (ya / tidak / selalu / batal) untuk asisten
            if self.perintah and self.izin_menunggu():
                return _Teruskan(teks)

            perintah = kata[0]
            if perintah == "ya" and len(kata) == 2 and self.tertunda:
                jenis, kode, habis, teks_asli = self.tertunda
                self.tertunda = None
                if self.sekarang() > habis:
                    return "Konfirmasi kedaluwarsa. Ketik " + ("matikan" if jenis == "matikan" else "lihat layar") + " lagi."
                if not hmac.compare_digest(kata[1].encode(), kode.encode()):
                    return "Kode salah, dibatalkan."
                if jenis == "layar":
                    return _Teruskan(teks_asli)
                self.jalankan("matikan")
                return "Laptop mati 30 detik lagi. Balas batal untuk menghentikan."
            self.tertunda = None
            # isi layar keluar dari laptop (ke Groq lalu ke WhatsApp), jadi minta kode seperti matikan
            if self.perintah and re.match(r"(?:lihat|baca) layar\b", teks.lower()):
                kode = f"{secrets.randbelow(10**4):04d}"
                self.tertunda = ("layar", kode, self.sekarang() + KONFIRMASI_DETIK, teks)
                return (f"Isi layarmu akan dikirim ke Groq lalu diringkas ke sini. "
                        f"Balas: ya {kode} dalam {KONFIRMASI_DETIK} detik untuk lanjut.")
            # perintah bawaan hanya kalau pesannya memang perintah itu saja, supaya obrolan seperti
            # "kunci jawaban soal ini apa" tidak mengunci layar
            inti = re.sub(r"[^\w\s]", "", teks.lower()).strip()
            if inti in ("matikan", "matikan laptop"):
                kode = f"{secrets.randbelow(10**4):04d}"
                self.tertunda = ("matikan", kode, self.sekarang() + KONFIRMASI_DETIK, teks)
                return f"Balas: ya {kode} dalam {KONFIRMASI_DETIK} detik untuk mematikan laptop."
            if inti == "batal":
                self.jalankan("batal_matikan")
                return "Dibatalkan."
            if inti in ("kunci", "kunci layar", "kunci laptop"):
                self.jalankan("kunci")
                return "Layar dikunci."
            if inti in ("status", "status laptop"):
                return _status()
            if inti in ("bantuan", "help"):
                return BANTUAN + (". " + BANTUAN_ASISTEN if self.perintah else "")
            if self.perintah:
                return _Teruskan(teks)
            return "Perintah tidak dikenal. " + BANTUAN

    def tangani(self, env):
        try:
            balasan = self._proses(env)
            if isinstance(balasan, _Teruskan):
                # dijalankan di luar self.kunci: perintah bisa lama dan pesan berikutnya (jawaban izin) harus tetap masuk
                balasan = self.perintah(balasan.teks)
            if balasan:
                self.kirim(balasan)
        except Exception:
            traceback.print_exc()


def buat_handler(g):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _jawab(self, kode):
            self.send_response(kode)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            if self.path != "/wa/webhook":
                return self._jawab(404)
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._jawab(400)
            if not 0 < n <= MAKS_BODY:
                return self._jawab(413)
            body = self.rfile.read(n)
            if not g.valid(body, self.headers.get("X-Webhook-Hmac", "")):
                return self._jawab(401)
            try:
                env = json.loads(body)
            except ValueError:
                return self._jawab(400)
            self._jawab(200)
            threading.Thread(target=g.tangani, args=(env,), daemon=True).start()
    return H


_g = None


def mulai(rahasia, ke_ui=print, host=HOST, port=PORT, perintah=None, izin_menunggu=None):
    """Dipanggil sekali dari server.py. rahasia(nama) -> nilai. Mengembalikan True kalau gerbang berjalan.
    perintah(teks) -> balasan: pemroses perintah asisten untuk pesan selain perintah bawaan."""
    global _g
    api, kunci = rahasia("WA_API_KEY"), rahasia("WA_HMAC_KEY")
    if not api or not kunci:
        print("[wa] WA_API_KEY / WA_HMAC_KEY belum diisi di rahasia.json, fitur WhatsApp mati.", flush=True)
        return False
    g = Gerbang(api, kunci, ke_ui=ke_ui, perintah=perintah, izin_menunggu=izin_menunggu)
    try:
        srv = ThreadingHTTPServer((host, port), buat_handler(g))
    except OSError as e:
        print(f"[wa] port {port} tidak bisa dipakai: {e}", flush=True)
        return False
    _g = g
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def tampilkan_kode():  # tunda dan ulangi: kartu yang muncul sebelum pill siap membaca kejadian akan terlewat
        time.sleep(20)
        while g.pemilik is None:
            ke_ui(f"Kode pasang WhatsApp: {g.kode_pasang}. Kirim: pasang {g.kode_pasang}")
            time.sleep(60)
    if not g.pemilik:
        threading.Thread(target=tampilkan_kode, daemon=True).start()
    print(f"[wa] gerbang aktif di {host}:{port}, pemilik {'terpasang' if g.pemilik else 'belum dipasang'}", flush=True)
    return True


def kirim(teks):
    return bool(_g and _g.kirim(teks))


def token_lokal_valid(token):
    """Rute lokal /wa/kirim: wajib token sesi kalau PILLOW_TOKEN diset (kalau tidak diset, mode pengembangan)."""
    wajib = os.environ.get("PILLOW_TOKEN")
    return not wajib or hmac.compare_digest((token or "").encode(), wajib.encode())
