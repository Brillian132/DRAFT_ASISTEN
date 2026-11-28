"""Perintah tutup tab Brave lewat port debugging.

  tutup tab youtube        -> menutup SATU tab; kalau yang cocok lebih dari satu, tidak ada yang ditutup
  tutup semua tab youtube  -> menutup semua tab yang cocok
"""
import re

import requests

import asisten

_BUANG = {"tolong", "coba", "dong", "ya", "deh", "aja", "saja", "pillow", "yang", "di", "dari", "brave", "browser",
          "itu", "ini", "sekarang", "tersebut"}
_AWAL = r"^(?:(?:tolong|coba|pillow|dong|ayo)\s+)*(?:tutup|tutupkan|close)\b"


def kenali(teks):
    """(semua: bool, nama tab: str) kalau ini perintah tutup tab, selain itu None."""
    kata = [k.strip(".,!?;:\"'") for k in teks.lower().split()]
    t = " ".join(k for k in kata if k)
    m = re.search(_AWAL, t)
    if not m or not re.search(r"\btab(?:nya)?\b", t):
        return None
    sisa = t[m.end():].split()
    semua = "semua" in sisa[:2]
    if semua:
        sisa.remove("semua")
    for i, k in enumerate(sisa):          # buang kata "tab" pertama saja: judul boleh memuat kata "tab"
        if k in ("tab", "tabnya"):
            del sisa[i]
            break
    # kata pengisi hanya dibuang dari ujung, supaya judul seperti "belajar di rumah" tetap utuh
    while sisa and sisa[0] in _BUANG:
        sisa.pop(0)
    while sisa and sisa[-1] in _BUANG | {"tab"}:
        sisa.pop()
    return semua, " ".join(sisa)


def jalankan(semua, nama):
    ucap = asisten.ngomong
    if len(nama) < 2:   # nama kosong/1 huruf akan cocok dengan hampir semua tab
        ucap("Sebutkan nama tab yang mau ditutup. Contoh: tutup tab youtube.")
        return
    ditutup = 0
    try:
        r = requests.get(f"{asisten.CDP}/json", timeout=3)
        r.raise_for_status()
        cocok = [t for t in r.json() if t.get("type") == "page" and nama in t.get("title", "").lower()]
        if not cocok:
            ucap(f"Maaf, tab dengan nama {nama} tidak ditemukan.")
            return
        if len(cocok) > 1 and not semua:
            persis = [t for t in cocok if t.get("title", "").lower() == nama]
            if len(persis) != 1:
                judul = "; ".join(t.get("title", "")[:60] for t in cocok[:3])
                ucap(f"Ada {len(cocok)} tab yang cocok, jadi belum aku tutup. Contohnya: {judul}. "
                     f"Sebutkan judul yang lebih jelas, atau katakan tutup semua tab {nama}.")
                return
            cocok = persis
        for t in cocok:
            if requests.get(f"{asisten.CDP}/json/close/{t['id']}", timeout=3).status_code == 200:
                ditutup += 1
        if ditutup == len(cocok):
            ucap(f"Berhasil menutup {ditutup} tab {nama}.")
        else:
            ucap(f"Hanya {ditutup} dari {len(cocok)} tab {nama} yang berhasil ditutup.")
    except requests.exceptions.ConnectionError:
        ucap(f"Brave tidak terhubung ke port debugging, {ditutup} tab sempat ditutup. Buka Brave lewat asisten ya.")
    except Exception as e:
        ucap(f"Terjadi error saat menutup tab. {ditutup} tab sempat ditutup.")
        print(f"[Tutup Tab Error] {e}", flush=True)
