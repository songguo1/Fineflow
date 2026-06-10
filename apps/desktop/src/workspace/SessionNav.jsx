import { Archive, ChevronLeft, ChevronRight, History, Plus, Trash2 } from "lucide-react";

import { displayStatusFromSession } from "../session/sessionStatus.js";

export function SessionNav({ ui, sessions, activeSessionId, navCollapsed, onToggle, onNewSession, onSwitchSession, onArchive, onDelete }) {
  return (
    <aside className={`session-nav ${navCollapsed ? "collapsed" : ""}`}>
      <div className="sidebar-head">
        {!navCollapsed ? <PanelTitle icon={History} text={ui.sessionNav.title} /> : null}
        <button
          className="collapse-button"
          type="button"
          onClick={onToggle}
          aria-label={navCollapsed ? ui.sessionNav.expandNav : ui.sessionNav.collapseNav}
          title={navCollapsed ? ui.sessionNav.expandNav : ui.sessionNav.collapseNav}
        >
          {navCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
      {navCollapsed ? (
        <CollapsedRail icon={History} text={ui.sessionNav.title} />
      ) : (
        <>
          <button className="new-session-btn" onClick={onNewSession}><Plus size={15} /> {ui.sessionNav.newSession}</button>
          <div className="session-list">
            {sessions.map((session) => {
              const displayStatus = displayStatusFromSession(session);
              return (
                <div
                  className={`session-card ${session.session_id === activeSessionId ? "active" : ""}`}
                  key={session.session_id}
                  onClick={() => onSwitchSession(session.session_id)}
                >
                  <div className="session-card-head">
                    <span className="session-id-tag">{session.session_id ? session.session_id.slice(0, 8) : "--------"}</span>
                    <span className={`session-status-pill ${displayStatus}`}>{ui.statuses[displayStatus] || displayStatus || "unknown"}</span>
                  </div>
                  {session.first_message ? <div className="session-preview">{session.first_message}</div> : null}
                  <div className="session-time">{formatRelativeTime(session.updated_at)}</div>
                  <div className="session-card-actions" onClick={(event) => event.stopPropagation()}>
                    <button onClick={() => onArchive(session.session_id)} title={ui.sessionNav.archive}><Archive size={11} /></button>
                    <button className="danger" onClick={() => onDelete(session.session_id)} title={ui.sessionNav.deleteSession || ui.actions.delete}><Trash2 size={11} /></button>
                  </div>
                </div>
              );
            })}
            {!sessions.length ? <Empty text={ui.session.noSession} /> : null}
          </div>
        </>
      )}
    </aside>
  );
}

function PanelTitle({ icon: Icon, text }) {
  return <div className="panel-title"><Icon size={16} /><strong>{text}</strong></div>;
}

function CollapsedRail({ icon: Icon, text }) {
  return <div className="collapsed-rail"><Icon size={16} /><span>{text}</span></div>;
}

function Empty({ text }) {
  return <div className="empty">{text}</div>;
}

function formatRelativeTime(isoString) {
  if (!isoString) return "";
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 7) return `${diffDay}d ago`;
    return date.toLocaleDateString();
  } catch {
    return "";
  }
}
