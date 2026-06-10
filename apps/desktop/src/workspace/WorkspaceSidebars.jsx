import { Database, ListTree } from "lucide-react";

import { CollapsedRail, PanelTitle, SidebarToggle } from "../layout/LayoutPrimitives.jsx";
import { ContextPanel } from "./ContextPanel.jsx";
import { DataSourcesPanel } from "./DataSourcesPanel.jsx";

export function DataSourcesSidebar({
  ui,
  collapsed,
  sources,
  recentOutputs,
  pendingTask,
  onToggle,
  onSourcesChange,
  onResolveSourceRequest,
  onError,
}) {
  return (
    <aside className={`left sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-head">
        {!collapsed ? <PanelTitle icon={Database} text={ui.sections.dataSources} /> : null}
        <SidebarToggle side="left" collapsed={collapsed} onToggle={onToggle} ui={ui} />
      </div>
      {collapsed ? (
        <CollapsedRail icon={Database} text={ui.sections.dataSources} />
      ) : (
        <DataSourcesPanel
          ui={ui}
          sources={sources}
          recentOutputs={recentOutputs}
          pendingTask={pendingTask}
          onSourcesChange={onSourcesChange}
          onResolveSourceRequest={onResolveSourceRequest}
          onError={onError}
        />
      )}
    </aside>
  );
}

export function ContextSidebar({
  ui,
  apiBaseUrl,
  collapsed,
  normalized,
  toolStateView,
  artifactView,
  sessionMemory,
  sessionMemoryDraft,
  memoryEditing,
  onToggle,
  onMemoryEdit,
  onMemoryChange,
  onMemorySave,
}) {
  return (
    <aside className={`right sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-head">
        {!collapsed ? <PanelTitle icon={ListTree} text={ui.sections.workflow} /> : null}
        <SidebarToggle side="right" collapsed={collapsed} onToggle={onToggle} ui={ui} />
      </div>
      {collapsed ? (
        <CollapsedRail icon={ListTree} text={ui.sections.workflow} />
      ) : (
        <ContextPanel
          ui={ui}
          apiBaseUrl={apiBaseUrl}
          result={normalized}
          toolStateView={toolStateView}
	          artifactView={artifactView}
          sessionMemory={sessionMemory}
          memoryDraft={sessionMemoryDraft}
          memoryEditing={memoryEditing}
          onMemoryEdit={onMemoryEdit}
          onMemoryChange={onMemoryChange}
          onMemorySave={onMemorySave}
        />
      )}
    </aside>
  );
}
