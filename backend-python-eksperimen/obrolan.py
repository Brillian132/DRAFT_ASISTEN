"""Mode obrolan Pillow Island: teman ngobrol santai lewat suara, WhatsApp, dan ketikan.

- Riwayat 8 giliran terakhir per saluran ("suara", "wa", "ketik"), hanya di memori (tidak disimpan ke disk).
  Riwayat suara dibuang saat mode ngobrol selesai; riwayat WA dan ketikan dibuang setelah 30 menit tanpa pesan.
- "Lihat layar": model vision membuat deskripsi rinci satu kali, disimpan sebagai konteks percakapan.
  Pertanyaan lanjutan dijawab dari deskripsi itu (hemat kuota). Untuk detail baru: "lihat layar lagi".
- Semua obrolan dan deskripsi layar dikirim ke Groq (cloud).
"""
import re
import time
import threading
from collections import deque

import asisten

MODEL = "openai/gpt-oss-20b"
MAKS_GILIRAN = 8                                     # 8 giliran = 8 pesan kamu + 8 jawaban Pillow
KEDALUWARSA = {"suara": 90, "wa": 30 * 60, "ketik": 30 * 60}   # detik tanpa pesan sampai riwayat dibuang
MAKS_TOKEN = {"suara": 220, "wa": 450, "ketik": 450}

_GAYA = {
    "suara": "Jawabanmu akan diucapkan dengan suara: 1 sampai 3 kalimat pendek, tanpa simbol, daftar, emoji, atau markdown.",
    "wa": "Jawabanmu dikirim lewat WhatsApp: boleh sampai 6 kalimat, tanpa markdown tebal atau judul; emoji sesekali boleh.",
    "ketik": "Jawabanmu tampil sebagai teks singkat: maksimal 4 kalimat, tanpa markdown.",
}

PERSONA = (
    "Kamu adalah Pillow, asisten laptop milik Brilian yang juga teman ngobrolnya. "
    "Bicara santai dalam bahasa Indonesia sehari-hari, pakai 'aku' dan 'kamu', hangat, jujur, dan sesekali bercanda. "
    "Tanggapi seperti teman: dengarkan, beri pendapat sendiri kalau ditanya, dan sesekali balik bertanya. "
    "Jangan mengaku manusia; kalau ditanya, kamu AI. Kalau tidak tahu sesuatu atau informasinya bisa sudah berubah, katakan terus terang. "
    "Kalau Brilian tampak sangat sedih, putus asa, atau dalam bahaya, tanggapi dengan empati, tanyakan keadaannya, "
    "dan ajak dia bicara dengan orang terdekat atau tenaga profesional. "
    "Kamu tidak bisa menjalankan perintah laptop dari obrolan ini; kalau Brilian ingin sesuatu dijalankan, "
    "sarankan dia mengucapkan perintahnya, misalnya 'buka youtube' atau 'volume naik 20'."
)

PROMPT_LAYAR = (
    "Deskripsikan layar komputer ini serinci mungkin dalam bahasa Indonesia untuk dipakai sebagai konteks percakapan. "
    "Sebutkan aplikasi atau situs yang terbuka, judul, semua teks penting yang terbaca (salin apa adanya), angka, "
    "tabel atau grafik beserta nilainya, kode atau pesan error, dan tata letak (atas, tengah, kiri, kanan). "
    "Jangan menebak hal yang tidak terlihat."
)


class _Saluran:
    def __init__(self):
        self.pesan = deque(maxlen=MAKS_GILIRAN * 2)
        self.layar = None          # (deskripsi, waktu)
        self.terakhir = 0.0


_kunci = threading.Lock()
_saluran = {}
sekarang = time.time            # bisa diganti saat pengujian


def _ambil(nama):
    with _kunci:
        s = _saluran.setdefault(nama, _Saluran())
        batas = KEDALUWARSA.get(nama, 30 * 60)
        if s.terakhir and sekarang() - s.terakhir > batas:
            s.pesan.clear()
            s.layar = None
        return s


def reset(nama):
    with _kunci:
        _saluran.pop(nama, None)


def riwayat(nama):
    """Salinan riwayat (untuk pengujian / diagnosa)."""
    return list(_ambil(nama).pesan)


def set_layar(nama, deskripsi):
    s = _ambil(nama)
    s.layar = (deskripsi, sekarang())
    s.terakhir = sekarang()


def ada_layar(nama):
    return _ambil(nama).layar is not None


def _bersihkan(teks):
    teks = (teks or "").replace("*", "").replace("#", "").replace("|", "").replace("`", "")
    return re.sub(r"\n{3,}", "\n\n", teks).strip()


def _susun(nama, s, teks):
    sistem = PERSONA + " " + _GAYA.get(nama, _GAYA["ketik"])
    jam = time.strftime("%A %d %B %Y, %H:%M", time.localtime(sekarang()))
    sistem += f" Waktu sekarang di laptop: {jam}."
    pesan = [{"role": "system", "content": sistem}]
    if s.layar:
        menit = max(0, int((sekarang() - s.layar[1]) // 60))
        pesan.append({"role": "system", "content":
                      f"Deskripsi layar Brilian ({menit} menit lalu), hasil 'lihat layar'. Pakai untuk menjawab pertanyaan "
                      f"tentang layar. Kalau detail yang ditanya tidak ada di deskripsi, bilang tidak terlihat dan sarankan "
                      f"'lihat layar lagi'.\n\n{s.layar[0]}"})
    pesan.extend(s.pesan)
    pesan.append({"role": "user", "content": teks})
    return pesan


def _panggil_model(pesan, maks_token):
    """Dipisah supaya bisa diganti saat pengujian."""
    hasil = asisten._get_client().chat.completions.create(
        messages=pesan, model=MODEL, max_tokens=maks_token, extra_body={"reasoning_effort": "low"},
    )
    return hasil.choices[0].message.content


def ngobrol(nama, teks):
    """Kirim satu ucapan/pesan ke Pillow, kembalikan jawabannya (sudah bersih dari markdown)."""
    s = _ambil(nama)
    teks = teks.strip()[:1500]
    try:
        jawaban = _bersihkan(_panggil_model(_susun(nama, s, teks), MAKS_TOKEN.get(nama, 400)))
    except Exception as e:
        print(f"[obrolan] gagal: {e}", flush=True)
        if asisten._apakah_limit(e):
            asisten._galat_terakhir = "limit"
            return "Jatah AI-ku lagi habis, ngobrolnya lanjut sebentar lagi ya."
        asisten._galat_terakhir = "ai"
        return "Duh, aku lagi susah mikir. Coba ulangi sebentar lagi ya."
    if not jawaban:
        jawaban = "Hmm, aku bingung mau jawab apa. Coba ceritakan lagi?"
    with _kunci:
        s.pesan.append({"role": "user", "content": teks})
        s.pesan.append({"role": "assistant", "content": jawaban})
        s.terakhir = sekarang()
    return jawaban


def lihat_layar(nama, pertanyaan=""):
    """Tangkap layar -> deskripsi rinci (1 panggilan vision) -> simpan sebagai konteks -> jawab ringkas."""
    deskripsi = asisten.deskripsi_layar(PROMPT_LAYAR)
    if not deskripsi:
        return "Maaf, aku gagal melihat layarmu."
    set_layar(nama, deskripsi)
    tanya = pertanyaan.strip() or "Aku baru saja memintamu melihat layarku. Ceritakan singkat apa yang kamu lihat."
    return ngobrol(nama, tanya)
