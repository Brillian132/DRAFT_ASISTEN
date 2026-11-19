mod media;

use serde::Deserialize;
use std::sync::Mutex;
use std::time::Duration;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, State};

#[derive(Deserialize, Clone, Copy)]
struct Region {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
}

#[derive(Default)]
struct Regions(Mutex<Vec<Region>>);

// area yang bisa diklik (bar kiri), dikirim dari frontend dalam piksel fisik
#[tauri::command]
fn set_regions(rects: Vec<Region>, state: State<Regions>) {
    *state.0.lock().unwrap() = rects;
}

#[tauri::command]
fn launch_app(name: String) -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    use std::process::Command;

    if name == "steam" {
        return Command::new("cmd")
            .args(["/C", "start", "", "steam://open/main"])
            .creation_flags(0x08000000)
            .spawn()
            .map(|_| ())
            .map_err(|e| e.to_string());
    }

    let env = |k: &str| std::env::var(k).unwrap_or_default();
    let local = env("LOCALAPPDATA");
    let pf = env("ProgramFiles");
    let pf86 = env("ProgramFiles(x86)");

    let candidates: Vec<String> = match name.as_str() {
        "chrome" => vec![
            format!(r"{pf}\Google\Chrome\Application\chrome.exe"),
            format!(r"{pf86}\Google\Chrome\Application\chrome.exe"),
            format!(r"{local}\Google\Chrome\Application\chrome.exe"),
        ],
        "vscode" => vec![
            format!(r"{local}\Programs\Microsoft VS Code\Code.exe"),
            format!(r"{pf}\Microsoft VS Code\Code.exe"),
        ],
        "opera" => vec![
            format!(r"{local}\Programs\Opera GX\opera.exe"),
            format!(r"{local}\Programs\Opera\opera.exe"),
            format!(r"{pf}\Opera GX\opera.exe"),
            format!(r"{pf}\Opera\opera.exe"),
        ],
        _ => return Err("aplikasi tidak dikenal".into()),
    };

    for path in &candidates {
        if std::path::Path::new(path).exists() {
            return Command::new(path)
                .spawn()
                .map(|_| ())
                .map_err(|e| e.to_string());
        }
    }
    Err(format!("program {name} tidak ditemukan, cek jalurnya di lib.rs"))
}

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

// jendela klik tembus, kecuali saat kursor berada di atas area interaktif
fn start_hit_testing(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        let mut ignoring = true;
        loop {
            std::thread::sleep(Duration::from_millis(25));
            let Some(window) = app.get_webview_window("main") else { continue };
            let Ok(cursor) = window.cursor_position() else { continue };
            let Ok(origin) = window.outer_position() else { continue };

            let cx = cursor.x - origin.x as f64;
            let cy = cursor.y - origin.y as f64;

            let inside = app
                .state::<Regions>()
                .0
                .lock()
                .unwrap()
                .iter()
                .any(|r| cx >= r.x && cx <= r.x + r.w && cy >= r.y && cy <= r.y + r.h);

            if inside == ignoring {
                ignoring = !inside;
                let _ = window.set_ignore_cursor_events(ignoring);
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(Regions::default())
        .invoke_handler(tauri::generate_handler![
            set_regions,
            launch_app,
            get_media,
            get_media_thumbnail,
            media_control
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();

            if let Some(monitor) = window.primary_monitor()? {
                window.set_position(*monitor.position())?;
                window.set_size(*monitor.size())?;
            }
            window.set_ignore_cursor_events(true)?;
            window.show()?;

            let quit = MenuItem::with_id(app, "quit", "Keluar", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Pillow Shell")
                .menu(&menu)
                .on_menu_event(|app, event| {
                    if event.id.as_ref() == "quit" {
                        app.exit(0);
                    }
                })
                .build(app)?;

            start_hit_testing(app.handle().clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}