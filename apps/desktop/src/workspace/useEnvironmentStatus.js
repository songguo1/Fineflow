import { useEffect, useState } from "react";

import { healthCheck, listRecentOutputs } from "../api/apiClient.js";

export function useEnvironmentStatus({ apiBaseUrl, qgis, ui, sessionId, status }) {
  const [health, setHealth] = useState({ state: "checking", detail: "" });
  const [recentOutputs, setRecentOutputs] = useState([]);

  useEffect(() => {
    let cancelled = false;
    setHealth({ state: "checking", detail: ui.health.checking });
    healthCheck(apiBaseUrl, qgis, true)
      .then((payload) => {
        if (cancelled) return;
        setHealth({
          state: payload.status === "ok" ? "online" : "error",
          detail: payload.error || (payload.pyqgis === "ok" ? ui.health.pyqgisReady : ui.health.apiReachable),
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setHealth({ state: "offline", detail: err.message });
      });
    return () => { cancelled = true; };
  }, [apiBaseUrl, qgis, ui.health.apiReachable, ui.health.checking, ui.health.pyqgisReady]);

  useEffect(() => {
    let cancelled = false;
    listRecentOutputs(apiBaseUrl)
      .then((list) => { if (!cancelled) setRecentOutputs(list); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [apiBaseUrl, sessionId, status]);

  return { health, recentOutputs };
}
