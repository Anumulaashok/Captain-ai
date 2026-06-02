use tauri::{
    App,
    Manager,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, TrayIconBuilder, TrayIconEvent},
};

pub fn setup_tray(app: &mut App) -> tauri::Result<()> {
    let open        = MenuItem::with_id(app, "open",     "Open Captain",              true, None::<&str>)?;
    let new_chat    = MenuItem::with_id(app, "new_chat", "New Chat",                  true, None::<&str>)?;
    let accounts    = MenuItem::with_id(app, "accounts", "Accounts & Connections",    true, None::<&str>)?;
    let sep1        = PredefinedMenuItem::separator(app)?;
    let toggle_voice = MenuItem::with_id(app, "voice",  "Toggle Voice",               true, None::<&str>)?;
    let sep2        = PredefinedMenuItem::separator(app)?;
    let quit        = MenuItem::with_id(app, "quit",     "Quit Captain",              true, None::<&str>)?;

    let menu = Menu::with_items(app, &[
        &open, &new_chat, &accounts, &sep1, &toggle_voice, &sep2, &quit,
    ])?;

    TrayIconBuilder::new()
        .menu(&menu)
        .tooltip("Captain AI")
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, .. } = event {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.hide();
                    } else {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
            }
        })
        .on_menu_event(|app, event| {
            match event.id.as_ref() {
                "open" => {
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.show();
                        let _ = w.set_focus();
                    }
                }
                "new_chat" => {
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.show();
                        let _ = w.set_focus();
                        let _ = w.eval("window.__navigateTo && window.__navigateTo('/chat?new=1')");
                    }
                }
                "accounts" => {
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.show();
                        let _ = w.set_focus();
                        let _ = w.eval("window.__navigateTo && window.__navigateTo('/accounts')");
                    }
                }
                "voice" => {
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.eval("window.__toggleVoice && window.__toggleVoice()");
                    }
                }
                "quit" => {
                    app.exit(0);
                }
                _ => {}
            }
        })
        .build(app)?;

    Ok(())
}
