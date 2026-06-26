use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Spawn the frozen FastAPI sidecar. It binds 127.0.0.1 (with a
            // free-port fallback) and prints `MP_SIDECAR_PORT=<n>` on stdout; we
            // then point the main window at it — the sidecar serves BOTH the SPA
            // and /api, so the app's relative API calls resolve against it.
            //
            // The sidecar is a PyInstaller --onedir payload (launcher + _internal/
            // libs) shipped as a Tauri *resource* (not externalBin, which is
            // single-file and can't carry _internal/). Resolve the launcher next to
            // its _internal/ inside the bundle's resource dir, trying the candidate
            // layouts the bundler may produce so a mapping tweak needs no rebuild.
            let res = app.path().resource_dir().expect("resource_dir unavailable");
            let candidates = [
                res.join("mp-sidecar").join("mp-sidecar"),
                res.join("binaries").join("mp-sidecar").join("mp-sidecar"),
                res.join("_up_").join("mp-sidecar").join("mp-sidecar"),
            ];
            let sidecar_path = candidates
                .iter()
                .find(|p| p.exists())
                .cloned()
                .unwrap_or_else(|| panic!("frozen sidecar not found in resources; looked in {candidates:?}"));

            // OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES is mandatory on macOS: once
            // Metal/MPS initializes, a later fork() crashes (the same
            // fork-after-Metal bug that hit the test suite — D-TEST-NATIVE-SEGV).
            let mut child = Command::new(&sidecar_path)
                .env("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
                .env("PYTHONUTF8", "1")
                .stdout(Stdio::piped())
                .spawn()
                .unwrap_or_else(|e| panic!("failed to spawn sidecar {sidecar_path:?}: {e}"));

            let stdout = child.stdout.take().expect("sidecar stdout missing");
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                // Hold the child for the thread (≈ app) lifetime so it isn't
                // dropped (and killed) the moment setup() returns.
                let _child = child;
                let reader = BufReader::new(stdout);
                for line in reader.lines().map_while(Result::ok) {
                    if let Some(port) = line
                        .trim()
                        .strip_prefix("MP_SIDECAR_PORT=")
                        .and_then(|s| s.parse::<u16>().ok())
                    {
                        if let Some(win) = handle.get_webview_window("main") {
                            if let Ok(url) = format!("http://127.0.0.1:{port}/").parse() {
                                let _ = win.navigate(url);
                            }
                        }
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
