export async function pickGisFiles() {
  if (!isLikelyTauri()) return [];
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    multiple: true,
    filters: [
      {
        name: "GIS data",
        extensions: ["shp", "geojson", "gpkg", "csv", "tif", "tiff"],
      },
    ],
  });
  if (!selected) return [];
  return Array.isArray(selected) ? selected : [selected];
}

export async function pickDirectory() {
  if (!isLikelyTauri()) return "";
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    directory: true,
    multiple: false,
  });
  return typeof selected === "string" ? selected : "";
}

export async function openPath(path) {
  if (!isLikelyTauri()) return undefined;
  const { openPath: openNativePath } = await import("@tauri-apps/plugin-opener");
  return openNativePath(path);
}

export async function getApiKeySecret() {
  if (!isLikelyTauri()) return "";
  const { invoke } = await import("@tauri-apps/api/core");
  return String((await invoke("get_api_key_secret")) || "");
}

export async function setApiKeySecret(value) {
  if (!isLikelyTauri()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_api_key_secret", { value: String(value || "") });
}

export async function clearApiKeySecret() {
  if (!isLikelyTauri()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("clear_api_key_secret");
}

export function isLikelyTauri() {
  return Boolean(window.__TAURI_INTERNALS__ || window.__TAURI__);
}

export function aliasFromPath(path) {
  const fileName = String(path || "").split(/[\\/]/).pop() || "layer";
  const stem = fileName.replace(/\.[^.]+$/, "");
  const clean = stem.replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  return clean || "layer";
}

export function sourceTypeFromPath(path) {
  const lower = String(path || "").toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (lower.endsWith(".tif") || lower.endsWith(".tiff")) return "raster";
  return "vector";
}
