#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

const SECRET_SERVICE: &str = "pineflow-desktop";
const API_KEY_ACCOUNT: &str = "llm-api-key";

#[tauri::command]
fn get_api_key_secret() -> Result<String, String> {
    let entry = keyring::Entry::new(SECRET_SERVICE, API_KEY_ACCOUNT).map_err(|error| error.to_string())?;
    match entry.get_password() {
        Ok(value) => Ok(value),
        Err(keyring::Error::NoEntry) => Ok(String::new()),
        Err(error) => Err(error.to_string()),
    }
}

#[tauri::command]
fn set_api_key_secret(value: String) -> Result<(), String> {
    let entry = keyring::Entry::new(SECRET_SERVICE, API_KEY_ACCOUNT).map_err(|error| error.to_string())?;
    entry.set_password(&value).map_err(|error| error.to_string())
}

#[tauri::command]
fn clear_api_key_secret() -> Result<(), String> {
    let entry = keyring::Entry::new(SECRET_SERVICE, API_KEY_ACCOUNT).map_err(|error| error.to_string())?;
    match entry.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            get_api_key_secret,
            set_api_key_secret,
            clear_api_key_secret
        ])
        .run(tauri::generate_context!())
        .expect("error while running PineFlow desktop");
}
