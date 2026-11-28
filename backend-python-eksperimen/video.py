"""Perintah video di browser untuk Pillow Island: "fullscreen" / "layar penuh" dan "keluar fullscreen" / "kecilkan video".

Cara kerja: cari jendela browser yang paling terakhir dipakai (Brave, Chrome, Edge, Firefox, Opera), munculkan dan
fokuskan, lalu tekan F (tombol layar penuh di YouTube dan banyak pemutar video lain) atau Esc (keluar layar penuh,
berlaku di semua situs). Status layar penuh: jendela tanpa bilah judul (WS_CAPTION) DAN menutupi seluruh monitor.
"""
import re

import jendela

BROWSER = {"brave.exe": "Brave", "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
           "opera.exe": "Opera"}
VK_F, VK_ESC = 0x46, 0x1B

_POLA_KELUAR = (r"\b(?:keluar|exit|keluarkan)\s+(?:dari\s+)?(?:fullscreen|full screen|layar penuh)\b"
                r"|\b(?:kecilkan|perkecil|kembalikan)\s+(?:youtube|video|videonya|youtubenya)\b"
                r"|\b(?:fullscreen|full screen|layar penuh)\w*\s+(?:off|mati|dimatikan|keluar)\b"
                r"|\b(?:matikan|tutup)\s+(?:fullscreen|full screen|layar penuh)\b")
_POLA_MASUK = (r"\b(?:fullscreen|full screen|layar penuh)\b"
               r"|\b(?:besarkan|perbesar|penuhkan)\s+(?:youtube|video|videonya|youtubenya)\b")


def kenali(teks):
    """'masuk' (jadikan layar penuh), 'keluar', atau None."""
    t = re.sub(r"[^\w\s]", " ", teks.lower())
    t = re.sub(r"\s+", " ", t).strip()
    if re.search(_POLA_KELUAR, t):
        return "keluar"
    if re.search(_POLA_MASUK, t):
        return "masuk"
    return None


# ------------------------------------------------------------------ akses Windows (bisa diganti saat pengujian)
def _daftar_jendela():
    w = jendela._w()
    return w.daftar() if w else []


def _penuh(gaya, r, m):
    """r dan m = (kiri, atas, kanan, bawah) jendela dan monitor."""
    # jendela maximize juga bisa menutupi monitor (mis. taskbar disembunyikan otomatis), tapi masih punya WS_CAPTION;
    # browser membuang WS_CAPTION saat benar-benar layar penuh
    if gaya & 0x00C00000 == 0x00C00000:
        return False
    return r[0] <= m[0] and r[1] <= m[1] and r[2] >= m[2] and r[3] >= m[3]


def _layar_penuh(hwnd):
    """True kalau jendela sedang benar-benar layar penuh."""
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    u = ctypes.windll.user32
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    u.MonitorFromWindow.restype = wintypes.HANDLE
    u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    r = wintypes.RECT()
    if not u.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)):   # 2 = MONITOR_DEFAULTTONEAREST
        return False
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    m = mi.rcMonitor
    gaya = u.GetWindowLongW(hwnd, -16)   # -16 = GWL_STYLE
    jendela_, monitor = (r.left, r.top, r.right, r.bottom), (m.left, m.top, m.right, m.bottom)
    hasil = _penuh(gaya, jendela_, monitor)
    print(f"[video] gaya={gaya & 0xFFFFFFFF:#010x} jendela={jendela_} monitor={monitor} penuh={hasil}", flush=True)
    return hasil


def _di_depan(hwnd):
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.GetForegroundWindow.restype = wintypes.HWND
    return u.GetForegroundWindow() == hwnd


def _fokus(hwnd):
    # jendela.fokus() mengetuk Alt untuk merebut fokus. Kalau browser SUDAH di depan, ketukan itu masuk ke browser,
    # fokus pindah ke menunya, dan tombol F tidak sampai ke video
    if di_depan(hwnd):
        return
    w = jendela._w()
    w.pulihkan(hwnd)
    w.fokus(hwnd)


def _tekan(vk):
    import ctypes
    u = ctypes.windll.user32
    u.keybd_event(vk, 0, 0, 0)
    u.keybd_event(vk, 0, 0x0002, 0)   # KEYEVENTF_KEYUP


daftar_jendela, layar_penuh, fokus, tekan = _daftar_jendela, _layar_penuh, _fokus, _tekan
di_depan = _di_depan
jeda_fokus = 0.35   # detik menunggu jendela benar-benar di depan sebelum menekan tombol
jeda_cek = 0.2      # jeda antar pengecekan hasil sesudah menekan F


def _browser_terakhir():
    """Jendela browser teratas (paling baru dipakai): (hwnd, nama browser, judul) atau None."""
    for j in daftar_jendela():
        if j["exe"] in BROWSER:
            return j["hwnd"], BROWSER[j["exe"]], j["judul"]
    return None


def jalankan(aksi):
    """Kembalikan kalimat balasan."""
    import time
    b = _browser_terakhir()
    if not b:
        return "Aku tidak menemukan browser yang terbuka."
    hwnd, nama, _judul = b
    penuh = layar_penuh(hwnd)
    if aksi == "masuk":
        if penuh:
            return "Videonya sudah layar penuh."
        fokus(hwnd)
        time.sleep(jeda_fokus)
        if not di_depan(hwnd):
            return f"Aku tidak bisa pindah ke jendela {nama}. Klik jendelanya, lalu coba lagi."
        tekan(VK_F)
        for _ in range(8):          # animasi layar penuh butuh waktu sebentar
            time.sleep(jeda_cek)
            if layar_penuh(hwnd):
                return f"Oke, video di {nama} aku buat layar penuh."
        return "Aku sudah tekan F, tapi videonya belum jadi layar penuh. Klik area videonya, lalu coba lagi."
    if not penuh:
        return "Videonya sedang tidak layar penuh."
    fokus(hwnd)
    time.sleep(jeda_fokus)
    if not di_depan(hwnd):
        return f"Aku tidak bisa pindah ke jendela {nama}. Klik jendelanya, lalu coba lagi."
    tekan(VK_ESC)
    return "Oke, keluar dari layar penuh."
