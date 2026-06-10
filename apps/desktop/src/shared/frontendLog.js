const FRONTEND_LOG_KEY = "qgis.agent.desktop.frontendLogs.v1";
const MAX_LOGS = 80;

export function appendFrontendLog(entry) {
  try {
    const logs = readFrontendLogs();
    logs.push({
      time: new Date().toISOString(),
      ...entry,
    });
    localStorage.setItem(FRONTEND_LOG_KEY, JSON.stringify(logs.slice(-MAX_LOGS)));
  } catch {
    // Logging should never break the app.
  }
}

export function readFrontendLogs() {
  try {
    const value = JSON.parse(localStorage.getItem(FRONTEND_LOG_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

