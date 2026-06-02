mod tray;
use tauri::Manager;

#[tauri::command]
fn get_backend_url() -> String {
    "http://127.0.0.1:8765".to_string()
}

#[tauri::command]
fn open_accounts_panel(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
        let _ = window.eval("window.__navigateTo && window.__navigateTo('/accounts')");
    }
}

#[tauri::command]
fn set_login_item(enabled: bool) -> bool {
    // Use macOS launchctl / loginitems to register auto-start
    let app_path = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().and_then(|p| p.parent()).map(|p| p.to_path_buf()))
        .unwrap_or_default();
    let path_str = app_path.to_string_lossy().to_string();

    let script = if enabled {
        format!(
            "osascript -e 'tell application \"System Events\" to make login item at end with properties {{path:\"{}\", hidden:false}}'",
            path_str
        )
    } else {
        "osascript -e 'tell application \"System Events\" to delete login item \"Captain\"'".to_string()
    };

    std::process::Command::new("sh")
        .arg("-c")
        .arg(&script)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            tray::setup_tray(app)?;

            // Start minimized to tray if launched at login
            let args: Vec<String> = std::env::args().collect();
            if args.contains(&"--login".to_string()) {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.hide();
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            open_accounts_panel,
            set_login_item,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Captain AI");
}
