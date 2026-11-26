#!/usr/bin/env python3
"""Menambahkan kontrol jendela (minimize / maksimalkan / tampilkan) dan logika "buka aplikasi yang sudah
berjalan = munculkan jendela yang ada" ke asisten.py dan server.py milikmu TANPA menimpa perubahanmu.

Cara pakai (PowerShell):
    python terapkan_jendela.py "D:\\asisten\\backend-python"

  - argumen = folder tempat server.py dan asisten.py berada
  - jendela.py harus satu folder dengan skrip ini (akan disalin ke folder backend)
  - cadangan: <nama>.bak-jendela ; opsi --ulang mengembalikan dari cadangan dulu lalu memasang ulang
Kalau ada bagian yang tidak cocok, skrip berhenti tanpa mengubah apa pun. Kalau pemeriksaan sintaks gagal,
semua dikembalikan.
"""
import os
import sys
import shutil
import subprocess

SUFFIX = ".bak-jendela"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]

ASISTEN_IMPOR = "import jendela   # kontrol jendela aplikasi (minimize, munculkan yang sudah terbuka)\n"

ASISTEN_FOKUS = '''        # aplikasi yang sudah berjalan: munculkan jendelanya, jangan buka yang baru
        if jendela.tampilkan_bila_sudah_jalan(nama_app):
            ngomong(f"{jendela.nama_tampil(jendela.kenali_app(nama_app))} sudah terbuka, aku tampilkan lagi.")
            return
'''

ASISTEN_PERINTAH_LAMA = '"pengingat", "hitung"'
ASISTEN_PERINTAH_BARU = ('"pengingat", "hitung", "minimize", "minimalkan", "kecilkan", "sembunyikan", "maksimalkan", '
                         '"munculkan", "kembalikan", "chrome", "opera"')

ASISTEN_KAMUS = '''        "chrome": ["krom", "krome", "kroum", "kroom", "crome", "chrom", "khrom"],
        "minimize": ["minimais", "minimaiz", "minimise", "minimaise", "minimais"],
'''

SERVER_IMPOR = "import jendela   # kontrol jendela aplikasi\n"

SERVER_BLOK = r'''# ---------- perintah kontrol jendela: minimize / maksimalkan / tampilkan ----------
def _perintah_jendela(p, suara):
    """Tangani 'minimize chrome', 'maksimalkan opera', 'tampilkan chrome'. True kalau sudah ditangani.
    'buka opera' sengaja TIDAK ditangani di sini: itu diurus buka_aplikasi() (munculkan jendela yang sudah ada)."""
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


'''

SERVER_CABANG_LAMA = '        elif "buka tab" in p:'
SERVER_CABANG_BARU = '        elif _perintah_jendela(p, suara):\n            pass\n        elif "buka tab" in p:'

# (berkas, nama, jenis, jangkar, teks, penanda)
PERUBAHAN = [
    ("asisten.py", "impor jendela", "sesudah", "\nimport mss\n", ASISTEN_IMPOR, "import jendela"),
    ("asisten.py", "buka aplikasi yang sudah berjalan = munculkan", "sesudah", "    if is_aplikasi:\n", ASISTEN_FOKUS, "jendela.tampilkan_bila_sudah_jalan"),
    ("asisten.py", "kata perintah minimize dll", "ganti", ASISTEN_PERINTAH_LAMA, ASISTEN_PERINTAH_BARU, '"minimize", "minimalkan"'),
    ("asisten.py", "koreksi ucapan chrome/minimize", "sesudah", '        "gold": ["emas", "gol"],\n', ASISTEN_KAMUS, '"minimize": ['),
    ("server.py", "impor jendela", "sesudah", "\nimport lirik\n", SERVER_IMPOR, "import jendela"),
    ("server.py", "perintah jendela", "sebelum", "def proses_perintah(perintah, suara=False):", SERVER_BLOK, "def _perintah_jendela"),
    ("server.py", "cabang perintah jendela", "ganti", SERVER_CABANG_LAMA, SERVER_CABANG_BARU, "elif _perintah_jendela(p, suara):"),
]


def terapkan(isi, jenis, jangkar, teks, penanda):
    if penanda in isi:
        return isi, "sudah"
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
    return isi.replace(jangkar, teks, 1), "ok"


def main():
    try:
        backend = (ARGS[0] if ARGS else input("Folder backend (tempat server.py dan asisten.py): ")).strip().strip('"')
    except EOFError:
        backend = ""
    jalur = {b: os.path.join(backend, b) for b in ("asisten.py", "server.py")}
    hilang = [j for j in jalur.values() if not os.path.isfile(j)]
    if hilang:
        print("Berkas ini tidak ditemukan, periksa nama folder:\n  " + "\n  ".join(hilang))
        return 1
    sumber = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jendela.py")
    tujuan = os.path.join(backend, "jendela.py")
    if not os.path.isfile(sumber) and not os.path.isfile(tujuan):
        print("jendela.py tidak ditemukan. Taruh jendela.py satu folder dengan skrip ini.")
        return 1

    if "--ulang" in sys.argv:
        for b, j in jalur.items():
            if os.path.isfile(j + SUFFIX):
                shutil.copy2(j + SUFFIX, j)
                print(f"  [dikembalikan] {b} dari cadangan")

    isi = {b: open(j, encoding="utf-8").read() for b, j in jalur.items()}
    asli = dict(isi)
    laporan, gagal = [], []
    for berkas, nama, jenis, jangkar, teks, penanda in PERUBAHAN:
        baru, status = terapkan(isi[berkas], jenis, jangkar, teks, penanda)
        if status == "ok":
            isi[berkas] = baru
            laporan.append(f"  [terpasang] {berkas}: {nama}")
        elif status == "sudah":
            laporan.append(f"  [sudah ada] {berkas}: {nama}")
        else:
            gagal.append(f"{berkas}: {nama} ({'jangkar tidak ditemukan' if status == 'tidak-ketemu' else 'jangkar muncul lebih dari sekali'})")
    print("\n".join(laporan))
    if gagal:
        print("\nTIDAK ADA FILE YANG DIUBAH. Bagian berikut tidak cocok dengan file-mu:\n  " + "\n  ".join(gagal))
        print("Kirim bagian file di sekitar itu ke saya, nanti saya sesuaikan.")
        return 2

    diubah = [b for b in jalur if isi[b] != asli[b]]
    for b in diubah:
        if not os.path.exists(jalur[b] + SUFFIX):
            shutil.copy2(jalur[b], jalur[b] + SUFFIX)
        with open(jalur[b], "w", encoding="utf-8") as f:
            f.write(isi[b])
    if os.path.isfile(sumber) and os.path.abspath(sumber) != os.path.abspath(tujuan):
        shutil.copy2(sumber, tujuan)
        print("  [disalin]   jendela.py -> " + backend)

    masalah = []
    for b in diubah:
        r = subprocess.run([sys.executable, "-m", "py_compile", jalur[b]], capture_output=True, text=True)
        if r.returncode != 0:
            masalah.append(f"{b}: {r.stderr.strip()[-300:]}")
    if masalah:
        for b in diubah:
            shutil.copy2(jalur[b] + SUFFIX, jalur[b])
        print("\nPemeriksaan sintaks GAGAL, semua file sudah dikembalikan seperti semula:\n  " + "\n  ".join(masalah))
        return 3

    print(f"\nSelesai. {len(diubah)} file diperbarui (cadangan: *{SUFFIX}).")
    print("Langkah berikut: build ulang Python (jendela.py ikut terbawa), lalu jalankan aplikasi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())