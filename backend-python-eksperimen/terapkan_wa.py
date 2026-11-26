#!/usr/bin/env python3
"""Memasang gerbang WhatsApp (wa.py) ke server.py dan main.js milikmu TANPA menimpa perubahanmu.

Cara pakai (PowerShell):
    python terapkan_wa.py "D:\\asisten\\backend-python-eksperimen" "D:\\asisten\\frontend-tauri-eksperimen\\pillow-island\\src"

  - argumen 1 = folder server.py ; argumen 2 = folder src Tauri (tempat main.js)
  - wa.py harus satu folder dengan skrip ini (disalin ke folder backend)
  - cadangan: <nama>.bak-wa ; opsi --ulang mengembalikan dari cadangan dulu
Kalau ada bagian yang tidak cocok, skrip berhenti tanpa mengubah apa pun; kalau pemeriksaan sintaks gagal, semua dikembalikan.
"""
import os
import sys
import shutil
import subprocess

SUFFIX = ".bak-wa"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]

SERVER_IMPOR = "import wa   # gerbang WhatsApp (WAHA)\n"

SERVER_RUTE = r'''# ---------- gerbang WhatsApp (WAHA): kirim notifikasi dari pill ----------
def _wa_ui(teks):
    try:
        kirim_kejadian("kartu", {"nada": "ok", "teks": teks})   # tampil di pill; hanya ada kalau antrean kejadian terpasang
    except NameError:
        print(f"[wa] {teks}", flush=True)

@app.post("/wa/kirim")
def wa_kirim():
    if not wa.token_lokal_valid(request.headers.get("X-Pillow-Token", "")):
        return jsonify(ok=False), 403
    teks = str((request.get_json(silent=True) or {}).get("teks") or "")[:500]
    return jsonify(ok=bool(teks) and wa.kirim(teks))

'''

SERVER_MULAI = "    wa.mulai(lambda n: asisten._rahasia(n), ke_ui=_wa_ui)   # gerbang WhatsApp\n"

JS_PENGINGAT = '\n  kirimWA(`${$("al-kind").textContent}: ${$("al-title").textContent}`);   // teruskan ke WhatsApp'
JS_BATERAI = '\n    kirimWA("Baterai rendah: " + persen + "%. Hubungkan charger.");'
JS_BLOK = '''/* ---------- teruskan pengingat dan baterai rendah ke WhatsApp (lewat server lokal; diam kalau belum diaktifkan) ---------- */
function kirimWA(teks) {
  pyFetch(`${PY_BASE}/wa/kirim`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ teks }) }).catch(() => {});
}

'''

# (berkas, nama, jenis, jangkar, teks, penanda)
PERUBAHAN = [
    ("server.py", "impor wa", "sesudah", "\nimport lirik\n", SERVER_IMPOR, "import wa   # gerbang WhatsApp"),
    ("server.py", "rute /wa/kirim", "sebelum", '@app.get("/lirik")', SERVER_RUTE, '"/wa/kirim"'),
    ("server.py", "gerbang dimulai saat server menyala", "sesudah",
     '    print(f"[server] build {BUILD_ID} di http://127.0.0.1:{PORT}", flush=True)\n', SERVER_MULAI, "wa.mulai("),
    ("main.js", "pengingat dan timer diteruskan", "sesudah", '  setState("reminder");', JS_PENGINGAT, 'kirimWA(`${$("al-kind")'),
    ("main.js", "baterai rendah diteruskan", "sesudah",
     '    tampilToast({ power: true, mode: "low", percent: persen, nada: "bad", ms: 4500 });', JS_BATERAI, 'kirimWA("Baterai rendah'),
    ("main.js", "fungsi kirimWA", "sebelum", "/* ---------- mulai ---------- */", JS_BLOK, "function kirimWA("),
]


def terapkan(isi, jenis, jangkar, teks, penanda):
    if penanda in isi:
        return isi, "sudah"
    n = isi.count(jangkar)
    if n != 1:
        return isi, "tidak-ketemu" if n == 0 else "ganda"
    i = isi.index(jangkar)
    if jenis == "sesudah":
        return isi[:i + len(jangkar)] + teks + isi[i + len(jangkar):], "ok"
    return isi[:i] + teks + isi[i:], "ok"


def main():
    try:
        backend = (ARGS[0] if len(ARGS) > 0 else input("Folder backend (tempat server.py): ")).strip().strip('"')
        frontend = (ARGS[1] if len(ARGS) > 1 else input("Folder src Tauri (tempat main.js): ")).strip().strip('"')
    except EOFError:
        backend = frontend = ""
    jalur = {"server.py": os.path.join(backend, "server.py"), "main.js": os.path.join(frontend, "main.js")}
    hilang = [j for j in jalur.values() if not os.path.isfile(j)]
    if hilang:
        print("Berkas ini tidak ditemukan, periksa nama folder:\n  " + "\n  ".join(hilang))
        return 1
    sumber = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wa.py")
    tujuan = os.path.join(backend, "wa.py")
    if not os.path.isfile(sumber) and not os.path.isfile(tujuan):
        print("wa.py tidak ditemukan. Taruh wa.py satu folder dengan skrip ini.")
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
        print("  [disalin]   wa.py -> " + backend)

    masalah = []
    for b in diubah:
        if b.endswith(".py"):
            cmd = [sys.executable, "-m", "py_compile", jalur[b]]
        elif shutil.which("node"):
            cmd = ["node", "--check", jalur[b]]
        else:
            continue
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            masalah.append(f"{b}: {r.stderr.strip()[-300:]}")
    if masalah:
        for b in diubah:
            shutil.copy2(jalur[b] + SUFFIX, jalur[b])
        print("\nPemeriksaan sintaks GAGAL, semua file sudah dikembalikan seperti semula:\n  " + "\n  ".join(masalah))
        return 3

    print(f"\nSelesai. {len(diubah)} file diperbarui (cadangan: *{SUFFIX}).")
    print("Langkah berikut: isi WA_API_KEY dan WA_HMAC_KEY di rahasia.json, atur webhook di WAHA, build ulang Python.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
