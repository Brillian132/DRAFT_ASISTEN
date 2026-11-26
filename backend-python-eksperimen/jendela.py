"""Kontrol jendela aplikasi di Windows untuk Pillow Island.

  minimize chrome        -> semua jendela Chrome diminimize
  maksimalkan opera      -> jendela Opera dimaksimalkan
  tampilkan chrome       -> jendela Chrome dimunculkan lagi dan diberi fokus
  buka opera (saat Opera sudah berjalan) -> jendela Opera yang SUDAH ADA dimunculkan,
                            bukan membuka aplikasi atau tab baru

Hanya memakai ctypes bawaan Python (tanpa library tambahan). Semua panggilan Windows terkumpul di
kelas _Win supaya logika di atasnya bisa diuji tanpa Windows.
"""
import os
import re

SW_MAXIMIZE, SW_MINIMIZE, SW_SHOW, SW_RESTORE = 3, 6, 5, 9

# kunci -> (nama untuk diucapkan, nama file program, kata pengenal dalam perintah)
APP = {
    "opera": ("Opera", {"opera.exe"}, ["opera gx", "opera"]),
    "chrome": ("Chrome", {"chrome.exe"}, ["google chrome", "chrome", "krom"]),
    "word": ("Word", {"winword.exe"}, ["word"]),
    "excel": ("Excel", {"excel.exe"}, ["excel"]),
    "powerpoint": ("PowerPoint", {"powerpnt.exe"}, ["powerpoint"]),
    "discord": ("Discord", {"discord.exe"}, ["discord"]),
    "steam": ("Steam", {"steam.exe"}, ["steam"]),
    "spotify": ("Spotify", {"spotify.exe"}, ["spotify"]),
    "notepad": ("Notepad", {"notepad.exe"}, ["notepad"]),
}

# "buka X" saat X sudah berjalan = munculkan jendela yang ada. Notepad sengaja tidak masuk:
# membuka beberapa Notepad itu wajar. Hapus/tambah nama di sini sesuai selera.
SATU_JENDELA = {"opera", "chrome", "word", "excel", "powerpoint", "discord", "steam", "spotify"}

_POLA_AKSI = {
    "minimize": r"\b(?:minimi[sz]e|minimais|minimalkan|kecilkan|sembunyikan)\b",
    "maximize": r"\b(?:maxim[iz]e|maksimalkan|besarkan|perbesar)\b",
    "tampilkan": r"\b(?:tampilkan|munculkan|kembalikan|pulihkan|restore|fokus)\b",
}


# ------------------------------------------------------------------ mengenali perintah
def kenali_app(teks):
    """Kembalikan kunci aplikasi (mis. 'opera') yang disebut dalam teks, atau None."""
    t = teks.lower()
    for kunci, (_nama, _exe, kata) in APP.items():
        for k in kata:
            if re.search(r"\b" + re.escape(k) + r"\b", t):
                return kunci
    return None


def kenali_aksi(teks):
    t = teks.lower()
    for aksi, pola in _POLA_AKSI.items():
        if re.search(pola, t):
            return aksi
    return None


def nama_tampil(app):
    return APP[app][0]


# ------------------------------------------------------------------ panggilan Windows
class _Win:
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    DWMWA_CLOAKED = 14
    VK_MENU = 0x12
    KEYEVENTF_KEYUP = 0x0002

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        self.u = ctypes.windll.user32
        self.k = ctypes.windll.kernel32
        self.dwm = getattr(ctypes.windll, "dwmapi", None)
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        u, k = self.u, self.k
        u.EnumWindows.argtypes = [self.WNDENUMPROC, wintypes.LPARAM]
        for nama in ("IsWindowVisible", "IsIconic", "GetWindowTextLengthW", "SetForegroundWindow", "BringWindowToTop"):
            getattr(u, nama).argtypes = [wintypes.HWND]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        u.GetWindow.restype = wintypes.HWND
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
        u.GetForegroundWindow.restype = wintypes.HWND
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]

    def _exe(self, pid):
        ct, wt = self.ct, self.wt
        h = self.k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ct.create_unicode_buffer(1024)
            n = wt.DWORD(1024)
            if self.k.QueryFullProcessImageNameW(h, 0, buf, ct.byref(n)):
                return os.path.basename(buf.value).lower()
            return ""
        finally:
            self.k.CloseHandle(h)

    def _tersembunyi(self, hwnd):
        """Jendela 'hantu' milik aplikasi Store yang tidak benar-benar tampil."""
        if not self.dwm:
            return False
        try:
            nilai = self.ct.c_int(0)
            self.dwm.DwmGetWindowAttribute(self.wt.HWND(hwnd), self.DWMWA_CLOAKED, self.ct.byref(nilai), self.ct.sizeof(nilai))
            return nilai.value != 0
        except Exception:
            return False

    def daftar(self):
        """Jendela utama yang tampil di bilah tugas, dari yang paling atas (terakhir dipakai) ke bawah."""
        u, ct, wt = self.u, self.ct, self.wt
        hasil, cache = [], {}

        def cb(hwnd, _lparam):
            try:
                if not u.IsWindowVisible(hwnd) or u.GetWindow(hwnd, self.GW_OWNER):
                    return True
                n = u.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return True
                ex = u.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
                if (ex & self.WS_EX_TOOLWINDOW) and not (ex & self.WS_EX_APPWINDOW):
                    return True
                if self._tersembunyi(hwnd):
                    return True
                judul = ct.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, judul, n + 1)
                pid = wt.DWORD(0)
                u.GetWindowThreadProcessId(hwnd, ct.byref(pid))
                if pid.value not in cache:
                    cache[pid.value] = self._exe(pid.value)
                hasil.append({"hwnd": hwnd, "exe": cache[pid.value], "judul": judul.value, "minimized": bool(u.IsIconic(hwnd))})
            except Exception:
                pass
            return True

        u.EnumWindows(self.WNDENUMPROC(cb), 0)
        return hasil

    def minimize(self, hwnd):
        self.u.ShowWindow(hwnd, SW_MINIMIZE)

    def maksimalkan(self, hwnd):
        self.u.ShowWindow(hwnd, SW_MAXIMIZE)

    def pulihkan(self, hwnd):
        self.u.ShowWindow(hwnd, SW_RESTORE if self.u.IsIconic(hwnd) else SW_SHOW)

    def fokus(self, hwnd):
        """Bawa jendela ke depan. Windows membatasi proses latar belakang merebut fokus; menekan Alt
        sebentar membuat proses ini berhak, dan SwitchToThisWindow menjadi cadangan."""
        u = self.u
        u.keybd_event(self.VK_MENU, 0, 0, 0)
        u.keybd_event(self.VK_MENU, 0, self.KEYEVENTF_KEYUP, 0)
        u.BringWindowToTop(hwnd)
        if not u.SetForegroundWindow(hwnd):
            u.SwitchToThisWindow(hwnd, True)
        return u.GetForegroundWindow() == hwnd


_win = None


def _w():
    global _win
    if _win is None and os.name == "nt":
        try:
            _win = _Win()
        except Exception as e:
            print(f"[jendela] tidak bisa memakai API Windows: {e}", flush=True)
    return _win


# ------------------------------------------------------------------ fungsi untuk perintah
def jendela_app(app):
    w = _w()
    if not w or app not in APP:
        return []
    exe = APP[app][1]
    return [j for j in w.daftar() if j["exe"] in exe]


def sedang_jalan(app):
    return bool(jendela_app(app))


def minimize_app(app):
    """Minimize semua jendela aplikasi. Mengembalikan jumlah jendela yang diminimize."""
    js = [j for j in jendela_app(app) if not j["minimized"]]
    for j in js:
        _w().minimize(j["hwnd"])
    return len(js)


def maksimalkan_app(app):
    js = jendela_app(app)
    if not js:
        return False
    _w().maksimalkan(js[0]["hwnd"])
    _w().fokus(js[0]["hwnd"])
    return True


def tampilkan_app(app):
    """Munculkan jendela yang paling baru dipakai (dan kembalikan dari minimize)."""
    js = jendela_app(app)
    if not js:
        return False
    _w().pulihkan(js[0]["hwnd"])
    _w().fokus(js[0]["hwnd"])
    return True


def tampilkan_bila_sudah_jalan(nama_app):
    """Dipakai buka_aplikasi(): True kalau aplikasi sudah berjalan dan jendelanya sudah dimunculkan,
    jadi tidak perlu membuka aplikasi baru."""
    app = kenali_app(nama_app)
    if not app or app not in SATU_JENDELA:
        return False
    return tampilkan_app(app)