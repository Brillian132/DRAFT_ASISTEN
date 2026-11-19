mod media;
mod perangkat;

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, Manager};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use windows::Win32::UI::Shell::{
    SHQueryUserNotificationState, QUNS_BUSY, QUNS_PRESENTATION_MODE, QUNS_RUNNING_D3D_FULL_SCREEN,
};

/* ---------- pengaturan yang disimpan di settings.json ---------- */

#[derive(Serialize, Deserialize, Clone)]
struct Settings {
    fs_hide: bool,      // sembunyi otomatis saat ada aplikasi fullscreen
    cover_accent: bool, // warna aksen mengikuti cover album
}

impl Default for Settings {
    fn default() -> Self {
        Self { fs_hide: true, cover_accent: true }
    }
}

struct AppState {
    settings: Mutex<Settings>,
}

fn settings_path(app: &tauri::AppHandle) -> Option<PathBuf> {
    app.path().app_config_dir().ok().map(|d| d.join("settings.json"))
}

fn load_settings(app: &tauri::AppHandle) -> Settings {
    settings_path(app)
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_settings(app: &tauri::AppHandle, s: &Settings) {
    if let Some(p) = settings_path(app) {
        if let Some(dir) = p.parent() {
            let _ = std::fs::create_dir_all(dir);
        }
        if let Ok(json) = serde_json::to_string_pretty(s) {
            let _ = std::fs::write(p, json);
        }
    }
}

fn toggle_setting(app: &tauri::AppHandle, key: &str) {
    let state = app.state::<AppState>();
    let snapshot = {
        let mut s = state.settings.lock().unwrap();
        match key {
            "fs_hide" => s.fs_hide = !s.fs_hide,
            "cover_accent" => s.cover_accent = !s.cover_accent,
            _ => {}
        }
        s.clone()
    };
    save_settings(app, &snapshot);
    let _ = app.emit("settings-changed", snapshot);
}

/* ---------- monitor ---------- */

fn monitor_contains(m: &tauri::Monitor, x: f64, y: f64) -> bool {
    let pos = m.position();
    let size = m.size();
    x >= pos.x as f64
        && x < pos.x as f64 + size.width as f64
        && y >= pos.y as f64
        && y < pos.y as f64 + size.height as f64
}

// mode: "primary" | "cursor" | "fixed:<nomor>"
fn pick_monitor(window: &tauri::WebviewWindow, mode: &str) -> Result<tauri::Monitor, String> {
    let monitors = window.available_monitors().map_err(|e| e.to_string())?;
    if monitors.is_empty() {
        return Err("monitor tidak ditemukan".into());
    }

    if mode == "cursor" {
        if let Ok(p) = window.cursor_position() {
            if let Some(m) = monitors.iter().find(|m| monitor_contains(m, p.x, p.y)) {
                return Ok(m.clone());
            }
        }
    }

    if let Some(rest) = mode.strip_prefix("fixed:") {
        if let Ok(i) = rest.parse::<usize>() {
            if let Some(m) = monitors.get(i) {
                return Ok(m.clone());
            }
        }
    }

    if let Some(m) = window.primary_monitor().map_err(|e| e.to_string())? {
        return Ok(m);
    }
    Ok(monitors[0].clone())
}

#[tauri::command]
fn monitor_count(window: tauri::WebviewWindow) -> usize {
    window.available_monitors().map(|m| m.len()).unwrap_or(1)
}

#[tauri::command]
fn cursor_monitor(window: tauri::WebviewWindow) -> usize {
    let monitors = window.available_monitors().unwrap_or_default();
    if let Ok(p) = window.cursor_position() {
        if let Some(i) = monitors.iter().position(|m| monitor_contains(m, p.x, p.y)) {
            return i;
        }
    }
    0
}

#[tauri::command]
fn get_settings(state: tauri::State<'_, AppState>) -> Settings {
    state.settings.lock().unwrap().clone()
}

#[tauri::command]
fn resize_island(
    window: tauri::WebviewWindow,
    width: f64,
    height: f64,
    anchor: String,
    monitor: String,
) -> Result<(), String> {
    let mon = pick_monitor(&window, &monitor)?;

    let scale = mon.scale_factor();
    let screen_w = mon.size().width as f64;
    let origin_x = mon.position().x as f64;
    let origin_y = mon.position().y as f64;

    let w_px = width * scale;
    let margin = 16.0 * scale;

    let x = match anchor.as_str() {
        "left" => origin_x + margin,
        "right" => origin_x + screen_w - w_px - margin,
        _ => origin_x + (screen_w - w_px) / 2.0,
    };
    let y = origin_y + 8.0 * scale;
    let pos = tauri::PhysicalPosition::new(x as i32, y as i32);

    // Pindah ke monitor tujuan dulu supaya skala DPI-nya dipakai saat mengubah ukuran,
    // lalu posisikan ulang agar tepat di tengah/kiri/kanan.
    window.set_position(pos).map_err(|e| e.to_string())?;
    window
        .set_size(tauri::LogicalSize::new(width, height))
        .map_err(|e| e.to_string())?;
    window.set_position(pos).map_err(|e| e.to_string())?;

    Ok(())
}

#[tauri::command]
fn set_clickthrough(window: tauri::WebviewWindow, ignore: bool) -> Result<(), String> {
    window
        .set_ignore_cursor_events(ignore)
        .map_err(|e| e.to_string())
}

/* ---------- media ---------- */

#[tauri::command]
async fn get_media() -> Result<media::MediaInfo, String> {
    tauri::async_runtime::spawn_blocking(|| media::get_info().map_err(|e| e.to_string()))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn get_media_thumbnail() -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(|| media::get_thumbnail().map_err(|e| e.to_string()))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn media_control(action: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || media::control(&action).map_err(|e| e.to_string()))
        .await
        .map_err(|e| e.to_string())?
}

/* ---------- matikan sidecar Python saat aplikasi keluar ---------- */

fn matikan_python() {
    use std::io::Write;
    use std::net::{SocketAddr, TcpStream};

    let addr: SocketAddr = "127.0.0.1:8008".parse().unwrap();
    if let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(500)) {
        let _ = s.write_all(
            b"POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
        );
    }
}

/* ---------- deteksi aplikasi fullscreen ---------- */

fn fullscreen_app_running() -> bool {
    match unsafe { SHQueryUserNotificationState() } {
        Ok(s) => s == QUNS_BUSY || s == QUNS_RUNNING_D3D_FULL_SCREEN || s == QUNS_PRESENTATION_MODE,
        Err(_) => false,
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Tombol hotkey didaftarkan di setup() supaya bentrok dengan program lain tidak membuat app gagal start.
    let shortcut_plugin = tauri_plugin_global_shortcut::Builder::new()
        .with_handler(|app, _shortcut, event| {
            if event.state() == ShortcutState::Pressed {
                let _ = app.emit("toggle-island", ());
            }
        })
        .build();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(shortcut_plugin)
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            resize_island,
            set_clickthrough,
            get_media,
            get_media_thumbnail,
            media_control,
            get_settings,
            monitor_count,
            cursor_monitor
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();

            // Pengaturan tersimpan
            let settings = load_settings(app.handle());
            app.manage(AppState { settings: Mutex::new(settings.clone()) });

            // Posisi awal: tengah atas monitor utama (JS akan menyesuaikan setelah dimuat)
            if let Some(monitor) = window.primary_monitor()? {
                let scale = monitor.scale_factor();
                let screen_w = monitor.size().width as i32;
                let win_w = window.outer_size()?.width as i32;
                let x = monitor.position().x + (screen_w - win_w) / 2;
                let y = monitor.position().y + (8.0 * scale) as i32;
                window.set_position(tauri::PhysicalPosition::new(x, y))?;
            }

            // ---------- hotkey Ctrl+Alt+I ----------
            let hotkey = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::ALT), Code::KeyI);
            if let Err(e) = app.global_shortcut().register(hotkey) {
                eprintln!("Hotkey Ctrl+Alt+I tidak bisa didaftarkan: {e}");
            }

            // ---------- menu system tray ----------
            let toggle = MenuItem::with_id(app, "toggle", "Tampilkan / sembunyikan (Ctrl+Alt+I)", true, None::<&str>)?;

            let idle_pinned = MenuItem::with_id(app, "idle_pinned", "Selalu tampil & bisa diklik", true, None::<&str>)?;
            let idle_hidden = MenuItem::with_id(app, "idle_hidden", "Tersembunyi", true, None::<&str>)?;
            let idle_small = MenuItem::with_id(app, "idle_small", "Kecil (klik tembus)", true, None::<&str>)?;
            let idle_menu = Submenu::with_items(app, "Mode idle", true, &[&idle_pinned, &idle_hidden, &idle_small])?;

            let pos_center = MenuItem::with_id(app, "pos_center", "Tengah atas", true, None::<&str>)?;
            let pos_left = MenuItem::with_id(app, "pos_left", "Kiri atas", true, None::<&str>)?;
            let pos_right = MenuItem::with_id(app, "pos_right", "Kanan atas", true, None::<&str>)?;
            let pos_menu = Submenu::with_items(app, "Posisi", true, &[&pos_center, &pos_left, &pos_right])?;

            let mon_primary = MenuItem::with_id(app, "mon_primary", "Monitor utama", true, None::<&str>)?;
            let mon_cursor = MenuItem::with_id(app, "mon_cursor", "Ikuti kursor", true, None::<&str>)?;
            let mon_next = MenuItem::with_id(app, "mon_next", "Pindah ke monitor berikutnya", true, None::<&str>)?;
            let mon_menu = Submenu::with_items(app, "Monitor", true, &[&mon_primary, &mon_cursor, &mon_next])?;

            let fs_item = CheckMenuItem::with_id(
                app, "fs_hide", "Sembunyi otomatis saat fullscreen", true, settings.fs_hide, None::<&str>,
            )?;
            let accent_item = CheckMenuItem::with_id(
                app, "cover_accent", "Warna aksen ikut cover album", true, settings.cover_accent, None::<&str>,
            )?;

            // Centang = auto-start aktif. Status awal dibaca dari Windows.
            let autostart_on = app.autolaunch().is_enabled().unwrap_or(false);
            let autostart_item = CheckMenuItem::with_id(
                app, "autostart", "Mulai otomatis saat Windows menyala", true, autostart_on, None::<&str>,
            )?;

            let quit = MenuItem::with_id(app, "quit", "Keluar", true, None::<&str>)?;
            let sep1 = PredefinedMenuItem::separator(app)?;
            let sep2 = PredefinedMenuItem::separator(app)?;
            let sep3 = PredefinedMenuItem::separator(app)?;

            let menu = Menu::with_items(
                app,
                &[
                    &toggle, &sep1, &idle_menu, &pos_menu, &mon_menu, &sep2,
                    &fs_item, &accent_item, &autostart_item, &sep3, &quit,
                ],
            )?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Pillow Island")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        matikan_python();
                        app.exit(0);
                    }
                    "toggle" => { let _ = app.emit("toggle-island", ()); }
                    "idle_pinned" => { let _ = app.emit("set-idle", "pinned"); }
                    "idle_hidden" => { let _ = app.emit("set-idle", "hidden"); }
                    "idle_small" => { let _ = app.emit("set-idle", "small"); }
                    "pos_center" => { let _ = app.emit("set-anchor", "center"); }
                    "pos_left" => { let _ = app.emit("set-anchor", "left"); }
                    "pos_right" => { let _ = app.emit("set-anchor", "right"); }
                    "mon_primary" => { let _ = app.emit("set-monitor", "primary"); }
                    "mon_cursor" => { let _ = app.emit("set-monitor", "cursor"); }
                    "mon_next" => { let _ = app.emit("set-monitor", "next"); }
                    "fs_hide" => toggle_setting(app, "fs_hide"),
                    "cover_accent" => toggle_setting(app, "cover_accent"),
                    "autostart" => {
                        let manager = app.autolaunch();
                        let _ = if manager.is_enabled().unwrap_or(false) {
                            manager.disable()
                        } else {
                            manager.enable()
                        };
                    }
                    _ => {}
                })
                .build(app)?;

            // ---------- pantau aplikasi fullscreen tiap 1 detik ----------
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let mut last = false;
                loop {
                    std::thread::sleep(Duration::from_millis(1000));
                    let enabled = {
                        let state = handle.state::<AppState>();
                        let guard = state.settings.lock();
                        guard.map(|s| s.fs_hide).unwrap_or(true)
                    };
                    let now = enabled && fullscreen_app_running();
                    if now != last {
                        last = now;
                        let _ = handle.emit("fullscreen", now);
                    }
                }
            });

            // ---------- pantau charger, Bluetooth, dan pemakaian mikrofon/kamera ----------
            perangkat::mulai(app.handle().clone());

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}