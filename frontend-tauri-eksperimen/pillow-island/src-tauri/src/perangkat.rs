//! Pemantau perangkat dan aktivitas Windows untuk Pillow Island.
//!
//! - charger dicolok / dicabut / baterai rendah  -> event "power"
//! - perangkat Bluetooth baru tersambung          -> event "bluetooth"
//! - aplikasi memakai mikrofon / kamera           -> event "privasi"
//!
//! Semua pemantauan berjalan di thread sendiri-sendiri dan hanya mengirim event
//! ke tampilan (main.js) saat ada perubahan, jadi ringan dan tidak mengganggu.

use std::collections::{HashMap, HashSet};
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter};
use windows::Devices::Bluetooth::{BluetoothConnectionStatus, BluetoothDevice};
use windows::Devices::Enumeration::DeviceInformation;
use windows::Win32::System::Power::{GetSystemPowerStatus, SYSTEM_POWER_STATUS};
use winreg::enums::HKEY_CURRENT_USER;
use winreg::RegKey;

/// Dipanggil sekali dari setup() di lib.rs.
pub fn mulai(app: AppHandle) {
    jalankan_power(app.clone());
    jalankan_bluetooth(app.clone());
    jalankan_privasi(app);
}

/* ======================================================
   BATERAI & CHARGER
   ====================================================== */

#[derive(Serialize, Clone)]
struct PowerEvent {
    kind: &'static str, // "plug" | "unplug" | "low"
    plugged: bool,
    percent: u8,
    charging: bool,
}

// (charger terpasang, persen baterai, sedang mengisi). None = komputer tanpa baterai.
fn baca_power() -> Option<(bool, u8, bool)> {
    let mut s: SYSTEM_POWER_STATUS = unsafe { std::mem::zeroed() };
    unsafe { GetSystemPowerStatus(&mut s) }.ok()?;
    if s.BatteryFlag & 128 != 0 {
        return None; // tidak ada baterai (PC desktop)
    }
    let plugged = s.ACLineStatus == 1;
    let percent = if s.BatteryLifePercent == 255 { 0 } else { s.BatteryLifePercent };
    let charging = s.BatteryFlag & 8 != 0;
    Some((plugged, percent, charging))
}

fn jalankan_power(app: AppHandle) {
    std::thread::spawn(move || {
        let mut terakhir: Option<bool> = None; // status charger pembacaan sebelumnya
        let mut sudah_peringatan_rendah = false;

        loop {
            if let Some((plugged, percent, charging)) = baca_power() {
                // pembacaan pertama hanya dicatat, tidak dikirim (supaya tidak ada notifikasi palsu)
                if let Some(sebelumnya) = terakhir {
                    if sebelumnya != plugged {
                        let _ = app.emit(
                            "power",
                            PowerEvent {
                                kind: if plugged { "plug" } else { "unplug" },
                                plugged,
                                percent,
                                charging,
                            },
                        );
                    }
                }
                terakhir = Some(plugged);

                // peringatan baterai rendah: sekali saja, sampai baterai naik lagi
                if !plugged && percent > 0 && percent <= 20 {
                    if !sudah_peringatan_rendah {
                        sudah_peringatan_rendah = true;
                        let _ = app.emit(
                            "power",
                            PowerEvent { kind: "low", plugged, percent, charging },
                        );
                    }
                } else if plugged || percent > 25 {
                    sudah_peringatan_rendah = false;
                }
            }
            std::thread::sleep(Duration::from_secs(2));
        }
    });
}

/* ======================================================
   PERANGKAT BLUETOOTH
   ====================================================== */

#[derive(Serialize, Clone)]
struct BluetoothEvent {
    name: String,
}

// Daftar perangkat Bluetooth yang sedang tersambung: id -> nama
fn bt_terhubung() -> windows::core::Result<HashMap<String, String>> {
    let selector =
        BluetoothDevice::GetDeviceSelectorFromConnectionStatus(BluetoothConnectionStatus::Connected)?;
    let koleksi = DeviceInformation::FindAllAsyncAqsFilter(&selector)?.get()?;

    let mut hasil = HashMap::new();
    for i in 0..koleksi.Size()? {
        let info = koleksi.GetAt(i)?;
        hasil.insert(info.Id()?.to_string(), info.Name()?.to_string());
    }
    Ok(hasil)
}

fn jalankan_bluetooth(app: AppHandle) {
    std::thread::spawn(move || {
        // None = belum ada pembacaan pertama (perangkat yang sudah tersambung saat app dibuka diabaikan)
        let mut dikenal: Option<HashMap<String, String>> = None;

        loop {
            if let Ok(sekarang) = bt_terhubung() {
                if let Some(lama) = &dikenal {
                    let mut sudah_dikirim: HashSet<String> = HashSet::new();
                    for (id, nama) in &sekarang {
                        if !lama.contains_key(id) && sudah_dikirim.insert(nama.clone()) {
                            let _ = app.emit("bluetooth", BluetoothEvent { name: nama.clone() });
                        }
                    }
                }
                dikenal = Some(sekarang);
            }
            std::thread::sleep(Duration::from_secs(3));
        }
    });
}

/* ======================================================
   PEMAKAIAN MIKROFON & KAMERA
   Windows mencatat aplikasi yang memakai mikrofon/kamera di registry.
   Sebuah aplikasi sedang memakainya kalau waktu "mulai pakai" lebih besar
   daripada waktu "berhenti pakai".
   ====================================================== */

#[derive(Serialize, Clone, PartialEq)]
struct PrivasiEvent {
    mic: Vec<String>,
    cam: Vec<String>,
}

const KONSEN: &str = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore";

// Aplikasi kita sendiri (asisten & jendela pill) tidak ikut dihitung,
// kalau tidak indikator mikrofon akan menyala terus.
fn milik_sendiri(mentah: &str) -> bool {
    let n = mentah.to_lowercase();
    n.contains("asisten-server")
        || n.contains("pillow-island")
        || n.contains("pillow_island")
        || n.contains("msedgewebview2")
}

// "C:#Program Files#Google#Chrome#Application#chrome.exe" -> "chrome"
// "Microsoft.WindowsCamera_8wekyb3d8bbwe"                  -> "Microsoft.WindowsCamera"
fn nama_ramah(mentah: &str) -> String {
    if mentah.contains('#') {
        let nama = mentah.rsplit('#').next().unwrap_or(mentah);
        nama.strip_suffix(".exe").unwrap_or(nama).to_string()
    } else {
        mentah.split('_').next().unwrap_or(mentah).to_string()
    }
}

fn sedang_dipakai(kunci: &RegKey) -> bool {
    let mulai: u64 = kunci.get_value("LastUsedTimeStart").unwrap_or(0);
    let henti: u64 = kunci.get_value("LastUsedTimeStop").unwrap_or(0);
    mulai > henti
}

// kemampuan: "microphone" atau "webcam"
fn aplikasi_aktif(kemampuan: &str) -> Vec<String> {
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    let Ok(induk) = hkcu.open_subkey(format!(r"{KONSEN}\{kemampuan}")) else {
        return Vec::new();
    };

    let mut mentah: Vec<String> = Vec::new();
    for nama in induk.enum_keys().filter_map(Result::ok) {
        let Ok(anak) = induk.open_subkey(&nama) else { continue };
        if nama == "NonPackaged" {
            // aplikasi biasa (.exe): satu subkey per aplikasi
            for nama2 in anak.enum_keys().filter_map(Result::ok) {
                if let Ok(k2) = anak.open_subkey(&nama2) {
                    if sedang_dipakai(&k2) {
                        mentah.push(nama2);
                    }
                }
            }
        } else if sedang_dipakai(&anak) {
            mentah.push(nama); // aplikasi dari Microsoft Store
        }
    }

    let mut hasil: Vec<String> = mentah
        .iter()
        .filter(|n| !milik_sendiri(n))
        .map(|n| nama_ramah(n))
        .collect();
    hasil.sort();
    hasil.dedup();
    hasil
}

fn jalankan_privasi(app: AppHandle) {
    std::thread::spawn(move || {
        let mut terakhir: Option<PrivasiEvent> = None;
        loop {
            let sekarang = PrivasiEvent {
                mic: aplikasi_aktif("microphone"),
                cam: aplikasi_aktif("webcam"),
            };
            // kirim hanya kalau ada perubahan (pembacaan pertama juga dikirim agar indikator benar)
            if terakhir.as_ref() != Some(&sekarang) {
                let _ = app.emit("privasi", sekarang.clone());
                terakhir = Some(sekarang);
            }
            std::thread::sleep(Duration::from_millis(1500));
        }
    });
}