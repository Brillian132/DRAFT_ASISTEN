cd D:\asisten\backend-python-eksperimen

# Matikan proses .exe lama jika masih nyangkut
Get-Process | Where-Object { $_.Name -like "asisten*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# Bersihkan folder build lama
Remove-Item -Recurse -Force build, dist, *.spec -ErrorAction SilentlyContinue

# Build ulang dengan semua hidden import (termasuk requests)
python -m PyInstaller --noconfirm --clean --onefile --name asisten-server `
  --hidden-import engineio.async_drivers.threading `
  --hidden-import simple_websocket `
  --hidden-import pyttsx3.drivers `
  --hidden-import pyttsx3.drivers.sapi5 `
  --hidden-import pythoncom `
  --hidden-import win32com.client `
  --hidden-import requests `
  --hidden-import urllib3 `
  --hidden-import charset_normalizer `
  --hidden-import idna `
  --hidden-import certifi `
  --collect-all speech_recognition `
  server.py

# Cari target triple otomatis
$triple = (rustc -vV | Select-String "host:").ToString().Split(" ")[1]

# Tentukan folder tujuan Tauri
$dest = "D:\asisten\frontend-tauri-eksperimen\pillow-island\src-tauri"

# Copy dan rename file .exe ke folder binaries
Copy-Item dist\asisten-server.exe "$dest\binaries\asisten-server-$triple.exe" -Force

# Hapus sisa .exe lama di folder target Tauri
Remove-Item "$dest\target\debug\asisten-server.exe" -ErrorAction SilentlyContinue

Write-Host "Build Selesai dan File .exe sudah dipindahkan!" -ForegroundColor Green