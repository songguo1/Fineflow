import { ChevronLeft, ChevronRight } from "lucide-react";

export function PanelTitle({ icon: Icon, text }) {
  return <div className="panel-title"><Icon size={16} /><strong>{text}</strong></div>;
}

export function LayoutSplitter({ panel, label, active, onMouseDown, onDoubleClick }) {
  return (
    <div
      className={`layout-splitter nav splitter-${panel} ${active ? "active" : ""}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      title={`${label} · 拖拽调整宽度，双击折叠/展开`}
      onMouseDown={onMouseDown}
      onDoubleClick={onDoubleClick}
    />
  );
}

export function SidebarToggle({ side, collapsed, onToggle, ui }) {
  const Icon = side === "left" ? (collapsed ? ChevronRight : ChevronLeft) : collapsed ? ChevronLeft : ChevronRight;
  const label = side === "left"
    ? collapsed ? ui.actions.expandLeft || "Expand left panel" : ui.actions.collapseLeft || "Collapse left panel"
    : collapsed ? ui.actions.expandRight || "Expand right panel" : ui.actions.collapseRight || "Collapse right panel";
  return (
    <button className="collapse-button" type="button" onClick={onToggle} aria-label={label} title={label}>
      <Icon size={16} />
    </button>
  );
}

export function CollapsedRail({ icon: Icon, text }) {
  return <div className="collapsed-rail"><Icon size={16} /><span>{text}</span></div>;
}
