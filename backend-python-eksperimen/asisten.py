import os
import sys
import glob
import json
import time
import wave
import tempfile
import threading
import smtplib
import difflib
import re
import io
import base64
import subprocess
import sounddevice as sd
import numpy as np
import speech_recognition as sr
import pyttsx3
from groq import Groq
from email.message import EmailMessage
import webbrowser
import pyautogui
import requests
import mss
import jendela   # kontrol jendela aplikasi (minimize, munculkan yang sudah terbuka)
from PIL import Image

# Library untuk Volume & Kecerahan
from pycaw.pycaw import AudioUtilities
import screen_brightness_control as sbc

# Library untuk Gemini (Fallback Vision)
import google.generativeai as genai

# Supaya print tidak error saat stdout berupa pipe (dijalankan Tauri)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ==========================================
# --- KONFIGURASI ---
# ==========================================
def _folder_appdata():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x001A, None, 0, buf)
        return buf.value
    except Exception:
        return os.environ.get("APPDATA", "")

def _lokasi_rahasia():
    lokasi = []
    ad = _folder_appdata()
    if ad:
        lokasi.append(os.path.join(ad, "PillowIsland", "rahasia.json"))
    lokasi.append(os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "PillowIsland", "rahasia.json"))
    return lokasi

def _rahasia(nama, default="", wajib=False):
    nilai = os.environ.get(nama)
    if nilai:
        return nilai
    dicek = []
    for path in _lokasi_rahasia():
        dicek.append(path)
        for enc in ("utf-8-sig", "utf-16"):
            try:
                with open(path, "r", encoding=enc) as f:
                    nilai = json.load(f).get(nama, default)
                    if nilai or not wajib:
                        return nilai
                    break
            except FileNotFoundError:
                break
            except Exception:
                continue
    if wajib:
        print(f"[rahasia] {nama} tidak ditemukan atau kosong. Lokasi yang dicek: {dicek}", flush=True)
    return default

API_KEY_GROQ = _rahasia("GROQ_API_KEY", wajib=True)
GEMINI_API_KEY = _rahasia("GEMINI_API_KEY", default="")
EMAIL_PENGIRIM = _rahasia("EMAIL_PENGIRIM")
EMAIL_PASSWORD = _rahasia("EMAIL_PASSWORD")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

_client = None
def _get_client():
    global _client
    if _client is None:
        if not API_KEY_GROQ:
            raise RuntimeError("GROQ_API_KEY belum diisi")
        _client = Groq(api_key=API_KEY_GROQ)
    return _client

# --- BRAVE ---
PORT_DEBUG = 9222
CDP = f"http://localhost:{PORT_DEBUG}"
# Brave (berbasis Chromium 136+) mengabaikan --remote-debugging-port kalau memakai profil bawaan.
# Karena itu Brave dibuka dengan profil khusus asisten, supaya fitur buka/tutup tab bisa jalan.
# Set ke False kalau mau profil biasa (bookmark & login tetap), tapi fitur tab tidak akan bekerja.
BRAVE_PROFIL_KHUSUS = True

def _path_brave():
    kandidat = [
        os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ]
    for p in kandidat:
        if p and os.path.exists(p):
            return p
    return None

def _profil_brave():
    folder = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "PillowIsland", "brave-profil")
    os.makedirs(folder, exist_ok=True)
    return folder

def jalankan_brave(url=None):
    """Jalankan Brave dengan port debugging. Kalau Brave (profil yang sama) sudah jalan, url dibuka di tab baru."""
    path = _path_brave()
    if not path:
        return False
    args = [path, f"--remote-debugging-port={PORT_DEBUG}"]
    if BRAVE_PROFIL_KHUSUS:
        args.append(f"--user-data-dir={_profil_brave()}")
    if url:
        args.append(url)
    subprocess.Popen(args, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return True

def _tunggu_cdp(detik=8):
    batas = time.time() + detik
    while time.time() < batas:
        try:
            if requests.get(f"{CDP}/json", timeout=1).status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(0.5)
    return False

def ke_brave(teks):
    """Ucapan/ketikan 'chrome' atau 'opera' diarahkan ke Brave."""
    return re.sub(r"\b(?:google\s+)?chrome\b|\bopera(?:\s+gx)?\b", "brave", teks)

# --- TTS ---
_pendengar = None
_tts_lock = threading.Lock()
_stop_suara = threading.Event()

def set_pendengar(fn):
    global _pendengar
    _pendengar = fn

def hentikan_suara():
    _stop_suara.set()

def reset_stop():
    _stop_suara.clear()

_galat_terakhir = None

def ambil_galat():
    global _galat_terakhir
    g, _galat_terakhir = _galat_terakhir, None
    return g

def _apakah_limit(e):
    s = str(e).lower()
    return "429" in s or "rate limit" in s or "rate_limit" in s

def _ucapkan_sapi(teks):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.Rate = 1
        voices = voice.GetVoices()
        for i in range(voices.Count):
            v = voices.Item(i)
            d = v.GetDescription().lower()
            if "indonesia" in d or "id-id" in d:
                voice.Voice = v
                break
        voice.Speak(teks, 1)
        while not voice.WaitUntilDone(100):
            if _stop_suara.is_set():
                voice.Speak("", 3)
                break
    finally:
        pythoncom.CoUninitialize()

def _ucapkan_pyttsx3(teks):
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    engine = pyttsx3.init()
    engine.setProperty("rate", 170)
    for voice in engine.getProperty("voices"):
        if "indonesia" in voice.name.lower() or "id-id" in voice.id.lower():
            engine.setProperty("voice", voice.id)
            break
    engine.say(teks)
    engine.runAndWait()
    engine.stop()

def ngomong(teks):
    print(f"Asisten: {teks}", flush=True)
    if _pendengar:
        try:
            _pendengar(teks)
        except Exception:
            pass
    if _stop_suara.is_set():
        return
    with _tts_lock:
        try:
            _ucapkan_sapi(teks)
        except Exception as e:
            print(f"[TTS SAPI error] {e}", flush=True)
            try:
                _ucapkan_pyttsx3(teks)
            except Exception as e2:
                print(f"[TTS error] {e2}", flush=True)

AMBANG_HENING = 250

HALUSINASI = {
    "terima kasih", "terima kasih telah menonton", "terima kasih sudah menonton",
    "sampai jumpa", "sampai jumpa lagi", "thank you", "thanks for watching",
    "terima kasih kembali", "subtitle by", "subtitles by", "amara.org",
    "terima kasih telah menonton video ini", "like dan subscribe",
}

def _transkrip_groq(path):
    with open(path, "rb") as f:
        data = f.read()
    hasil = _get_client().audio.transcriptions.create(
        file=("suara.wav", data),
        model="whisper-large-v3-turbo",
        language="id",
        temperature=0.0,
        timeout=15,
    )
    return getattr(hasil, "text", None) or str(hasil)

# CATATAN: fungsi ini tidak dipakai lagi. recognize_google selalu butuh program FLAC,
# yang gagal di dalam .exe (WinError 50), jadi transkripsi sekarang hanya lewat Groq.
def _transkrip_google(path):
    import wave
    recognizer = sr.Recognizer()
    
    # Baca file WAV secara manual
    with wave.open(path, "rb") as wf:
        # Ambil parameter audio
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        
        # Baca semua frame
        frames = wf.readframes(n_frames)
        
        # Buat AudioData langsung (tanpa flac)
        audio = sr.AudioData(frames, framerate, sampwidth)
    
    # Kirim ke Google
    return recognizer.recognize_google(audio, language="id-ID")

def koreksi_kata_asing(teks):
    kamus_koreksi = {
        "claude": ["claudy", "clode", "klaud", "claud", "cloud"],
        "deepseek": ["dipsik", "deep sick", "dipsick", "dipsik", "deep sek", "dipsek"],
        "youtube": ["yu tub", "you tube", "yutub", "yutube"],
        "github": ["git hub", "githab", "githup"],
        "google": ["gugel", "gogel", "googel"],
        "discord": ["diskor", "diskod", "dis cord"],
        "steam": ["stim", "setim"],
        "spotify": ["spotifai", "spotifi", "spotipai"],
        "bitcoin": ["btc", "bit coin", "bitkoin"],
        "ethereum": ["eth", "eterium"],
        "gold": ["emas", "gol"],
        "brave": ["breiv", "breif", "brev", "brep", "bref", "breve", "brave"],
        "chrome": ["krom", "krome", "kroum", "kroom", "crome", "chrom", "khrom"],
        "minimize": ["minimais", "minimaiz", "minimise", "minimaise", "minimais"],
        "pillow": ["pilo", "pilou", "pilow", "pilo", "pilow", "pilow"],
    }
    
    kata_teks = teks.split()
    hasil = []
    
    for kata in kata_teks:
        kata_bersih = kata.strip(".,!?;:")
        kata_diganti = kata
        
        for benar, variasi in kamus_koreksi.items():
            if kata_bersih in variasi:
                kata_diganti = benar
                break
            if len(kata_bersih) > 3:
                for var in variasi:
                    kemiripan = difflib.SequenceMatcher(None, kata_bersih, var).ratio()
                    if kemiripan > 0.8:
                        kata_diganti = benar
                        break
            if kata_diganti != kata:
                break
        
        if kata != kata_bersih:
            tanda_baca = kata[len(kata_bersih):]
            hasil.append(kata_diganti + tanda_baca)
        else:
            hasil.append(kata_diganti)
            
    return " ".join(hasil)

def _rekam(durasi, batas, fs):
    """Rekam dari mikrofon, berhenti begitu pembicara diam sebentar (maksimal `durasi` detik).
    Mengembalikan (rekaman int16, jumlah blok 0,1 detik yang berisi suara)."""
    blok = int(fs * 0.1)
    bagian, bicara, hening = [], 0, 0
    with sd.InputStream(samplerate=fs, channels=1, dtype="int16", blocksize=blok) as aliran:
        for _n in range(int(durasi * 10)):
            data, _tumpah = aliran.read(blok)
            bagian.append(data.copy())
            if int(np.abs(data.astype(np.int32)).max()) >= batas:
                bicara += 1
                hening = 0
            elif bicara:
                hening += 1
                if hening >= 6:          # 0,6 detik diam setelah bicara = selesai
                    break
    rec = np.concatenate(bagian) if bagian else np.zeros((0, 1), dtype=np.int16)
    return rec, bicara

def dengerin(durasi=5, ambang=None):
    global _galat_terakhir
    batas = AMBANG_HENING if ambang is None else ambang
    print("\n[Mendengarkan...]", flush=True)
    path = os.path.join(tempfile.gettempdir(), "asisten_temp_audio.wav")
    try:
        fs = 16000
        try:
            rec, bicara = _rekam(durasi, batas, fs)
        except Exception:
            fs = 44100                   # sebagian mikrofon tidak mendukung 16 kHz
            rec, bicara = _rekam(durasi, batas, fs)

        puncak = int(np.abs(rec.astype(np.int32)).max()) if rec.size else 0
        print(f"[Level suara: {puncak}]", flush=True)
        if puncak < batas or bicara < 2:
            print("[Terlalu hening atau terlalu singkat, tidak dikirim ke Groq]", flush=True)
            return ""

        faktor = min(20.0, 20000.0 / puncak)
        if faktor > 1.2:
            rec = np.clip(rec.astype(np.float32) * faktor, -32768, 32767).astype(np.int16)

        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(fs)
            w.writeframes(rec.tobytes())

        print("[Memproses suara...]", flush=True)
        try:
            text = _transkrip_groq(path)
        except Exception as e:
            print(f"[Transkripsi Groq gagal] {e}", flush=True)
            if _apakah_limit(e):
                _galat_terakhir = "limit"
            return ""

        text = (text or "").strip()
        if not text or text.lower().strip(" .!?,") in HALUSINASI:
            print("[Suara masuk, tapi tidak ada kata yang dikenali]", flush=True)
            return ""
            
        text = text.lower().strip(" .,!?;:")
        text = koreksi_kata_asing(text)
        text = ke_brave(text)
        # Bersihkan kata "hai" yang berulang (gema)
        text = re.sub(r'\b(hai\s+)+', 'hai ', text).strip()
        print(f"Kamu (Suara setelah koreksi): {text}", flush=True)
        
        kata_perintah = ["buka", "tutup", "putar", "cari", "ringkas", "kirim", "bersihkan", "cleanup", "mulai", "bangun", "tidur", "istirahat", "keluar", "berhenti", "matikan", "tab", "word", "excel", "powerpoint", "discord", "steam", "semua", "youtube", "github", "google", "claude", "deepseek", "spotify", "volume", "suara", "kecerahan", "layar", "brightness", "mute", "naik", "turun", "pillow", "lihat", "baca", "timer", "ingatkan", "pengingat", "hitung", "minimize", "minimalkan", "kecilkan", "sembunyikan", "maksimalkan", "munculkan", "kembalikan", "brave", "chrome", "opera", "dokumen", "berkas", "folder", "indeks", "pertama", "kedua", "ketiga", "keempat", "kelima", "nomor"]
        if len(text) < 3 or not any(k in text for k in kata_perintah):
            print("[Bukan perintah / obrolan sampah. Diabaikan agar API tidak boros]", flush=True)
            return ""

        return text
    except sr.UnknownValueError:
        print("[Suara masuk, tapi tidak ada kata yang dikenali]", flush=True)
        return ""
    except sr.RequestError as e:
        print(f"[Google Speech tidak bisa dihubungi, cek internet] {e}", flush=True)
        return ""
    except Exception as e:
        print(f"[dengerin error] {e}", flush=True)
        return ""
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

# --- FUNGSI AI MARKET & VISION ---

def analisis_market(pertanyaan):
    print(f"Asisten: Menganalisis market...", flush=True)
    try:
        chat_completion = _get_client().chat.completions.create(
            messages=[
                {"role": "system", "content": "Kamu adalah asisten trading profesional. Jawab hanya pertanyaan seputar market saham, crypto, forex. Berikan angka spesifik (harga, resistance, support) jika memungkinkan. Jawab singkat, maksimal 3 kalimat."},
                {"role": "user", "content": pertanyaan},
            ],
            model="openai/gpt-oss-20b",
            extra_body={"reasoning_effort": "low"},
        )
        jawaban = chat_completion.choices[0].message.content
        jawaban_bersih = jawaban.replace("*", "").replace("#", "").replace("|", "")
        ngomong(jawaban_bersih)
    except Exception as e:
        global _galat_terakhir
        print(f"[analisis_market error] {e}", flush=True)
        if _apakah_limit(e):
            _galat_terakhir = "limit"
            ngomong("Jatah AI sedang habis, coba lagi sebentar lagi.")
        else:
            _galat_terakhir = "ai"
            ngomong("Waduh, ada error pas menganalisis.")

def lihat_layar(pertanyaan=""):
    ngomong("Oke, aku lihat layarmu sebentar ya...")
    path = os.path.join(tempfile.gettempdir(), "screenshot_temp.jpg")
    
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        
        img.thumbnail((1024, 1024))
        img.save(path, format="JPEG", quality=85)
        
        with open(path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        prompt = pertanyaan if pertanyaan else "Jelaskan apa yang ada di layar ini secara singkat. Jika ada chart, sebutkan angka dan pola."
        
        jawaban_bersih = ""
        try:
            jawaban = _get_client().chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                        ]
                    }
                ],
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                max_tokens=300,
            )
            jawaban_bersih = jawaban.choices[0].message.content
        except Exception as e_groq:
            print(f"[Groq Vision gagal, coba Gemini] {e_groq}", flush=True)
            if GEMINI_API_KEY:
                try:
                    model_gemini = genai.GenerativeModel('gemini-3.8-flash')
                    response = model_gemini.generate_content([
                        prompt,
                        {"mime_type": "image/jpeg", "data": img_base64}
                    ])
                    jawaban_bersih = response.text
                except Exception as e_gemini:
                    ngomong("Maaf, kedua AI vision gagal.")
                    print(f"[Gemini Vision Error] {e_gemini}", flush=True)
                    return
            else:
                ngomong("Groq Vision limit dan Gemini API Key tidak ada.")
                return
        
        jawaban_bersih = jawaban_bersih.replace("*", "").replace("#", "").replace("|", "")
        ngomong(jawaban_bersih)
        
    except Exception as e:
        ngomong("Maaf, aku gagal melihat layar.")
        print(f"[Lihat Layar Error] {e}", flush=True)
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
                print("[Screenshot dihapus]", flush=True)
        except OSError:
            pass

def tanya_ai(pertanyaan):
    print("Asisten: Sedang berpikir...", flush=True)
    try:
        chat_completion = _get_client().chat.completions.create(
            messages=[
                {"role": "system", "content": "Jawab dalam bahasa Indonesia, singkat dan padat, maksimal 3 kalimat."},
                {"role": "user", "content": pertanyaan},
            ],
            model="openai/gpt-oss-20b",
            extra_body={"reasoning_effort": "low"},
        )
        jawaban = chat_completion.choices[0].message.content
        jawaban_bersih = jawaban.replace("*", "").replace("#", "").replace("|", "")
        ngomong(jawaban_bersih)
    except Exception as e:
        global _galat_terakhir
        print(f"[tanya_ai error] {e}", flush=True)
        if _apakah_limit(e):
            _galat_terakhir = "limit"
            ngomong("Jatah AI sedang habis, coba lagi sebentar lagi.")
        else:
            _galat_terakhir = "ai"
            ngomong("Waduh, ada error pas mikir.")

# --- FUNGSI VOLUME & KECERAHAN ---
def atur_volume(perubahan):
    try:
        device = AudioUtilities.GetSpeakers()
        volume_sekarang = device.volume_percent
        volume_baru = max(0, min(100, volume_sekarang + perubahan))
        device.volume_percent = volume_baru
        
        if perubahan > 0:
            ngomong(f"Volume dinaikkan {perubahan} persen. Sekarang {volume_baru} persen.")
        else:
            ngomong(f"Volume diturunkan {abs(perubahan)} persen. Sekarang {volume_baru} persen.")
    except Exception as e:
        ngomong("Gagal mengatur volume.")
        print(f"[Volume Error] {e}", flush=True)

def mute_volume():
    try:
        device = AudioUtilities.GetSpeakers()
        is_muted = device.mute
        device.mute = not is_muted
        status = "dimute" if not is_muted else "di-unmute"
        ngomong(f"Volume {status}.")
    except Exception as e:
        ngomong("Gagal mengubah mute.")
        print(f"[Mute Error] {e}", flush=True)

def atur_kecerahan(perubahan):
    try:
        kecerahan_sekarang = sbc.get_brightness()[0]
        kecerahan_baru = max(0, min(100, kecerahan_sekarang + perubahan))
        sbc.set_brightness(kecerahan_baru)
        
        if perubahan > 0:
            ngomong(f"Kecerahan dinaikkan {perubahan}. Sekarang {kecerahan_baru} persen.")
        else:
            ngomong(f"Kecerahan diturunkan {abs(perubahan)}. Sekarang {kecerahan_baru} persen.")
    except Exception as e:
        ngomong("Gagal mengatur kecerahan.")
        print(f"[Brightness Error] {e}", flush=True)

# --- FUNGSI BUKA APLIKASI ---
def buka_aplikasi(nama_app):
    aplikasi_dikenal = ["brave", "notepad", "word", "excel", "powerpoint", "discord", "steam", "spotify"]
    is_aplikasi = any(app in nama_app.lower() for app in aplikasi_dikenal)
    
    if is_aplikasi:
        # aplikasi yang sudah berjalan: munculkan jendelanya, jangan buka yang baru
        if jendela.tampilkan_bila_sudah_jalan(nama_app):
            ngomong(f"{jendela.nama_tampil(jendela.kenali_app(nama_app))} sudah terbuka, aku tampilkan lagi.")
            return
        ngomong(f"Oke, aku coba buka {nama_app}...")
        
        if "brave" in nama_app:
            if not jalankan_brave():
                ngomong("Maaf, Brave tidak ditemukan.")
        elif "notepad" in nama_app:
            os.system("notepad")
        elif "word" in nama_app:
            path_word_1 = r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"
            path_word_2 = r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE"
            if os.path.exists(path_word_1):
                os.startfile(path_word_1)
            elif os.path.exists(path_word_2):
                os.startfile(path_word_2)
            else:
                path_shortcut = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Word.lnk"
                if os.path.exists(path_shortcut):
                    os.startfile(path_shortcut)
                else:
                    ngomong("Maaf, Microsoft Word tidak ditemukan.")
        elif "excel" in nama_app:
            path_excel = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"
            if os.path.exists(path_excel):
                os.startfile(path_excel)
            else:
                ngomong("Maaf, Microsoft Excel tidak ditemukan.")
        elif "powerpoint" in nama_app:
            path_ppt = r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
            if os.path.exists(path_ppt):
                os.startfile(path_ppt)
            else:
                ngomong("Maaf, PowerPoint tidak ditemukan.")
        elif "discord" in nama_app:
            path_discord = os.path.expanduser("~\\AppData\\Local\\Discord\\Update.exe")
            if os.path.exists(path_discord):
                os.system(f'start "" "{path_discord}" --processStart Discord.exe')
            else:
                ngomong("Maaf, Discord tidak ditemukan.")
        elif "steam" in nama_app:
            path_steam = "C:\\Program Files (x86)\\Steam\\steam.exe"
            if os.path.exists(path_steam):
                os.startfile(path_steam)
            else:
                ngomong("Maaf, Steam tidak ditemukan.")
    else:
        buka_tab_brave(nama_app)

def tutup_aplikasi(nama_app):
    ngomong(f"Oke, aku coba tutup {nama_app}...")
    if "brave" in nama_app:
        os.system("taskkill /F /IM brave.exe")
    elif "notepad" in nama_app:
        os.system("taskkill /F /IM notepad.exe")
    elif "word" in nama_app:
        os.system("taskkill /F /IM WINWORD.EXE")
    elif "excel" in nama_app:
        os.system("taskkill /F /IM EXCEL.EXE")
    elif "powerpoint" in nama_app:
        os.system("taskkill /F /IM POWERPNT.EXE")
    elif "discord" in nama_app:
        os.system("taskkill /F /IM Discord.exe")
    elif "steam" in nama_app:
        os.system("taskkill /F /IM steam.exe")
    elif "spotify" in nama_app:
        os.system("taskkill /F /IM Spotify.exe")
    else:
        ngomong(f"Maaf, aku belum tau cara tutup {nama_app}.")

# --- FITUR TUTUP TAB BRAVE ---
def tutup_tab_brave(nama_tab):
    ngomong(f"Oke, aku coba cari tab {nama_tab} di Brave...")
    try:
        response = requests.get(f"{CDP}/json", timeout=3)
        if response.status_code != 200:
            ngomong("Gagal terhubung ke Brave. Pastikan Brave dibuka oleh asisten.")
            return

        tabs = response.json()
        tabs_ditemukan = []

        for tab in tabs:
            if tab.get("type") == "page":
                judul_tab = tab.get("title", "").lower()
                if nama_tab.lower() in judul_tab:
                    tabs_ditemukan.append(tab.get("id"))
        
        if not tabs_ditemukan:
            ngomong(f"Maaf, tab dengan nama {nama_tab} tidak ditemukan.")
            return

        for tab_id in tabs_ditemukan:
            requests.get(f"{CDP}/json/close/{tab_id}", timeout=3)
        
        ngomong(f"Berhasil menutup {len(tabs_ditemukan)} tab {nama_tab}.")
            
    except requests.exceptions.ConnectionError:
        ngomong("Brave tidak terhubung ke port debugging. Tolong buka Brave lewat asisten ya.")
    except Exception as e:
        ngomong("Terjadi error saat mencoba menutup tab.")
        print(f"[Tutup Tab Error] {e}", flush=True)

# --- FUNGSI BUKA TAB BRAVE ---
def _bersihkan_url_untuk_suara(url):
    url = url.replace("https://", "").replace("http://", "")
    url = url.replace("www.", "")
    if url.endswith("/"):
        url = url[:-1]
    return url

def buka_tab_brave(url):
    if "." not in url:
        url = f"{url}.com"
    
    if not url.startswith("http"):
        url = f"https://{url}"
    
    url_suara = _bersihkan_url_untuk_suara(url)
        
    ngomong(f"Oke, aku buka tab baru untuk {url_suara}...")
    try:
        requests.get(f"{CDP}/json", timeout=2)
        requests.put(f"{CDP}/json/new?{url}", timeout=3)
        ngomong(f"Tab {url_suara} berhasil dibuka.")
    except requests.exceptions.ConnectionError:
        ngomong("Brave belum terbuka dengan port debugging. Aku buka Brave dulu ya.")
        # url langsung ikut dibuka saat Brave dijalankan
        if jalankan_brave(url):
            _tunggu_cdp()
            ngomong(f"Tab {url_suara} berhasil dibuka.")
        else:
            ngomong("Maaf, Brave tidak ditemukan.")
    except Exception as e:
        ngomong("Gagal membuka tab baru.")
        print(f"[Buka Tab Error] {e}", flush=True)

# --- FITUR TUTUP SEMUA TAB YANG COCOK ---
def tutup_semua_tab_brave(nama_tab):
    ngomong(f"Oke, aku cari semua tab {nama_tab} di Brave...")
    try:
        response = requests.get(f"{CDP}/json", timeout=3)
        if response.status_code != 200:
            ngomong("Gagal terhubung ke Brave. Pastikan Brave dibuka oleh asisten.")
            return

        tabs = response.json()
        tabs_ditemukan = []

        for tab in tabs:
            if tab.get("type") == "page":
                judul_tab = tab.get("title", "").lower()
                if nama_tab.lower() in judul_tab:
                    tabs_ditemukan.append(tab.get("id"))
        
        if not tabs_ditemukan:
            ngomong(f"Maaf, tab dengan nama {nama_tab} tidak ditemukan.")
            return

        for tab_id in tabs_ditemukan:
            requests.get(f"{CDP}/json/close/{tab_id}", timeout=3)
        
        ngomong(f"Berhasil menutup {len(tabs_ditemukan)} tab {nama_tab}.")
            
    except requests.exceptions.ConnectionError:
        ngomong("Brave tidak terhubung ke port debugging. Tolong buka Brave lewat asisten ya.")
    except Exception as e:
        ngomong("Terjadi error saat mencoba menutup tab.")
        print(f"[Tutup Semua Tab Error] {e}", flush=True)

def putar_youtube(judul, tipe="video"):
    ngomong(f"Oke, aku buka YouTube dan akan memutar {judul}...")
    judul_url = judul.replace(" ", "+")

    if tipe == "live":
        url = f"https://www.youtube.com/results?search_query={judul_url}&sp=EgJAAQ%253D%253D"
    else:
        url = f"https://www.youtube.com/results?search_query={judul_url}&sp=EgIQAQ%253D%253D"

    if jalankan_brave(url):
        ngomong("Menunggu halaman YouTube siap...")
        time.sleep(6)

        print("[Auto-Play] Mengklik video pertama...", flush=True)
        x_asli, y_asli = pyautogui.position()
        pyautogui.click(x=320, y=400)
        pyautogui.moveTo(x_asli, y_asli)
        print("[Auto-Play] Selesai!", flush=True)
    else:
        ngomong("Brave tidak ditemukan, aku buka pakai browser default ya.")
        webbrowser.open(url)

def cari_file(nama_file):
    ngomong(f"Mencari file dengan nama {nama_file}, mohon tunggu...")
    search_paths = [os.path.expanduser("~\\Documents"), os.path.expanduser("~\\Downloads")]
    hasil = []
    for path in search_paths:
        for file in glob.glob(f"{path}\\**\\*{nama_file}*", recursive=True):
            hasil.append(file)

    if hasil:
        ngomong(f"Aku menemukan {len(hasil)} file. Ini yang pertama: {hasil[0]}")
        print(f"Lokasi file: {hasil[0]}", flush=True)
    else:
        ngomong("Maaf, file tidak ditemukan.")

def cleanup_laptop():
    ngomong("Membersihkan file temporary Windows...")
    temp_path = os.getenv('TEMP')
    try:
        os.system(f'del /Q /F /S "{temp_path}\\*.*" >nul 2>&1')
        ngomong("Beres! File temporary sudah dibersihkan.")
    except Exception as e:
        ngomong("Gagal membersihkan file.")

def ringkas_dokumen(nama_file):
    search_paths = [os.path.expanduser("~\\Documents"), os.path.expanduser("~\\Downloads")]
    file_path = None
    for path in search_paths:
        if os.path.exists(os.path.join(path, nama_file)):
            file_path = os.path.join(path, nama_file)
            break

    if not file_path:
        ngomong("Maaf, file tidak ditemukan di folder Documents atau Downloads.")
        return

    ngomong("Membaca dokumen...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            isi = f.read()
        if len(isi) > 3000:
            isi = isi[:3000]
        prompt = f"Tolong ringkas dokumen berikut dalam bahasa Indonesia:\n\n{isi}"
        tanya_ai(prompt)
    except Exception as e:
        ngomong("Gagal membaca dokumen. Pastikan formatnya .txt ya.")

def kirim_file(nama_file, email_tujuan="emailtujuan@gmail.com"):
    ngomong(f"Mencari file {nama_file} untuk dikirim...")
    search_paths = [os.path.expanduser("~\\Documents"), os.path.expanduser("~\\Downloads")]
    file_path = None
    for path in search_paths:
        if os.path.exists(os.path.join(path, nama_file)):
            file_path = os.path.join(path, nama_file)
            break

    if not file_path:
        ngomong("File tidak ditemukan.")
        return

    ngomong("Menyiapkan email...")
    msg = EmailMessage()
    msg['Subject'] = f"Kiriman dari Asisten Laptop: {nama_file}"
    msg['From'] = EMAIL_PENGIRIM
    msg['To'] = email_tujuan
    msg.set_content(f"Halo, ini file {nama_file} yang kamu minta.")

    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
            msg.add_attachment(file_data, maintype='application', subtype='octet-stream', filename=nama_file)

        ngomong("Mengirim email...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_PENGIRIM, EMAIL_PASSWORD)
            smtp.send_message(msg)
        ngomong("Berhasil! File sudah dikirim ke email tujuan.")
    except Exception as e:
        ngomong("Gagal mengirim email. Periksa App Password dan koneksi internet.")

def main():
    is_sleeping = True
    ngomong("Sistem siap. Aku sedang tidur. Ucapkan Mulai untuk membangunkanku.")

    while True:
        if is_sleeping:
            print("\n[Zzz... Mode Tidur. Ucapkan 'Mulai']", flush=True)
            perintah = dengerin(3)

            if "mulai" in perintah or "bangun" in perintah:
                is_sleeping = False
                ngomong("Aku bangun! Ada yang bisa dibantu Brilian?")
            elif "keluar" in perintah or "matikan program" in perintah:
                ngomong("Sampai jumpa Brilian!")
                break
            else:
                continue

        else:
            print("\n[Mendengarkan...] Silakan bicara", flush=True)
            perintah = dengerin()

            if perintah == "":
                continue

            if "tidur" in perintah or "istirahat" in perintah:
                is_sleeping = True
                ngomong("Oke, aku tidur dulu ya. Panggil aku kalau butuh bantuan.")
                continue

            if "pillow" in perintah and ("hi" in perintah or "hai" in perintah or "halo" in perintah):
                pertanyaan = perintah.replace("hi pillow", "").replace("hai pillow", "").replace("halo pillow", "").strip()
                if pertanyaan:
                    analisis_market(pertanyaan)
                else:
                    ngomong("Ya, ada yang bisa saya bantu soal market?")
            elif "lihat layar" in perintah or "baca layar" in perintah:
                pertanyaan = perintah.replace("lihat layar", "").replace("baca layar", "").strip()
                lihat_layar(pertanyaan)
            elif "buka tab" in perintah:
                url = perintah.replace("buka tab ", "").strip()
                buka_tab_brave(url)
            elif "tutup semua tab" in perintah:
                nama = perintah.replace("tutup semua tab ", "").replace(" tab", "").strip()
                if nama:
                    tutup_semua_tab_brave(nama)
                else:
                    ngomong("Sebutkan nama tab yang mau ditutup. Contoh: tutup semua tab youtube.")
            elif "tutup tab" in perintah:
                nama = perintah.replace("tutup tab ", "").replace(" tab", "").strip()
                if nama:
                    tutup_tab_brave(nama)
                else:
                    ngomong("Sebutkan nama tab yang mau ditutup. Contoh: tutup tab youtube.")
            elif "volume" in perintah or "suara" in perintah:
                angka_match = re.search(r'\d+', perintah)
                angka = int(angka_match.group()) if angka_match else 10
                
                if "naik" in perintah or "naikkan" in perintah or "tinggi" in perintah:
                    atur_volume(angka)
                elif "turun" in perintah or "turunkan" in perintah or "rendah" in perintah:
                    atur_volume(-angka)
                elif "mute" in perintah or "bisu" in perintah:
                    mute_volume()
                else:
                    ngomong("Mau naikkan atau turunkan volume?")
            elif "kecerahan" in perintah or "brightness" in perintah or "layar" in perintah:
                angka_match = re.search(r'\d+', perintah)
                angka = int(angka_match.group()) if angka_match else 10
                
                if "naik" in perintah or "naikkan" in perintah or "terang" in perintah:
                    atur_kecerahan(angka)
                elif "turun" in perintah or "turunkan" in perintah or "redup" in perintah:
                    atur_kecerahan(-angka)
                else:
                    ngomong("Mau naikkan atau turunkan kecerahan?")
            elif "buka" in perintah:
                app = perintah.replace("buka ", "").replace(" aplikasi", "")
                buka_aplikasi(app)
            elif "tutup" in perintah:
                app = perintah.replace("tutup ", "").replace(" aplikasi", "")
                tutup_aplikasi(app)
            elif "putar" in perintah:
                if "live" in perintah:
                    judul = perintah.replace("putar live streaming ", "").replace("putar live ", "")
                    putar_youtube(judul, tipe="live")
                else:
                    judul = perintah.replace("putar ", "").replace(" youtube ", "").replace(" lagu ", "")
                    putar_youtube(judul, tipe="video")
            elif "shutdown" in perintah or "matikan laptop" in perintah:
                ngomong("Laptop akan dimatikan dalam 10 detik...")
                os.system("shutdown /s /t 10")
                break
            elif "cari file" in perintah:
                nama = perintah.replace("cari file ", "")
                cari_file(nama)
            elif "bersihkan" in perintah or "cleanup" in perintah:
                cleanup_laptop()
            elif "ringkas dokumen" in perintah:
                nama = perintah.replace("ringkas dokumen ", "")
                ringkas_dokumen(nama)
            elif "kirim file" in perintah:
                nama = perintah.replace("kirim file ", "")
                kirim_file(nama)
            elif "keluar" in perintah or "berhenti" in perintah:
                ngomong("Sampai jumpa Brilian!")
                break
            else:
                tanya_ai(perintah)

if __name__ == "__main__":
    main()