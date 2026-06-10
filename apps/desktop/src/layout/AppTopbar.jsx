import { Settings } from "lucide-react";

import wordmarkUrl from "../assets/pineflow-wordmark.png";

export function AppTopbar({ ui, health, runState, onOpenSettings, onResetSession }) {
  const healthText = topbarHealthText(ui, health);
  return (
    <header className="topbar">
      <div className="brand">
        <img className="brand-wordmark" src={wordmarkUrl} alt="PineFlow" />
        <div>
          <span>{healthText}</span>
        </div>
      </div>
      <div className="top-actions">
        <button onClick={onOpenSettings}><Settings size={15} /> {ui.actions.settings}</button>
        <button onClick={onResetSession} disabled={runState.isRunning}>{ui.actions.reset}</button>
      </div>
    </header>
  );
}

function topbarHealthText(ui, health) {
  const state = String(health?.state || "").toLowerCase();
  const detail = String(health?.detail || "").trim();
  if (state === "online") return ui.health.ready || "GIS 引擎已就绪";
  const label = ui.statuses?.[state] || health?.state || ui.statuses?.offline || "离线";
  return detail ? `${label}: ${detail}` : label;
}
