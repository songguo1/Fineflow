import { LayoutSplitter } from "../layout/LayoutPrimitives.jsx";
import { SessionNav } from "./SessionNav.jsx";

export function WorkspaceLayout({
  ui,
  layoutRef,
  layoutStyle,
  isLayoutDragging,
  resizingPanel,
  navCollapsed,
  leftCollapsed,
  contextCollapsed,
  sessions,
  activeSessionId,
  onToggleNav,
  onNewSession,
  onSwitchSession,
  onArchiveSession,
  onDeleteSession,
  onStartResize,
  onToggleSplitterPanel,
  left,
  center,
  right,
}) {
  return (
    <div
      className={`layout ${navCollapsed ? "nav-collapsed" : ""} ${leftCollapsed ? "left-collapsed" : ""} ${contextCollapsed ? "context-collapsed" : ""} ${isLayoutDragging ? "resizing" : ""}`}
      ref={layoutRef}
      style={layoutStyle}
    >
      <LayoutSplitter
        panel="nav"
        label={navCollapsed ? ui.sessionNav.expandNav : ui.sessionNav.collapseNav}
        active={resizingPanel === "nav"}
        onMouseDown={(event) => onStartResize("nav", event)}
        onDoubleClick={() => onToggleSplitterPanel("nav")}
      />
      <LayoutSplitter
        panel="left"
        label={leftCollapsed ? ui.actions.expandLeft : ui.actions.collapseLeft}
        active={resizingPanel === "left"}
        onMouseDown={(event) => onStartResize("left", event)}
        onDoubleClick={() => onToggleSplitterPanel("left")}
      />
      <LayoutSplitter
        panel="context"
        label={contextCollapsed ? ui.actions.expandRight : ui.actions.collapseRight}
        active={resizingPanel === "context"}
        onMouseDown={(event) => onStartResize("context", event)}
        onDoubleClick={() => onToggleSplitterPanel("context")}
      />
      <SessionNav
        ui={ui}
        sessions={sessions}
        activeSessionId={activeSessionId}
        navCollapsed={navCollapsed}
        onToggle={onToggleNav}
        onNewSession={onNewSession}
        onSwitchSession={onSwitchSession}
        onArchive={onArchiveSession}
        onDelete={onDeleteSession}
      />
      {left}
      {center}
      {right}
    </div>
  );
}
