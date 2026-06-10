import { useEffect, useRef, useState } from "react";

const LAYOUT_WIDTHS_KEY = "pineflow.desktop.layout.widths.v1";
const COLLAPSED_PANEL_WIDTH = 54;
const CENTER_MIN_WIDTH = 360;
const PANEL_WIDTHS = {
  nav: { default: 248, min: 180, max: 360 },
  left: { default: 264, min: 210, max: 340 },
  context: { default: 386, min: 280, max: 520 },
};

export function useResizableLayout() {
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [contextCollapsed, setContextCollapsed] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [panelWidths, setPanelWidths] = useState(loadLayoutWidths);
  const [dragState, setDragState] = useState(null);
  const layoutRef = useRef(null);

  const effectivePanelWidths = {
    nav: navCollapsed ? COLLAPSED_PANEL_WIDTH : panelWidths.nav,
    left: leftCollapsed ? COLLAPSED_PANEL_WIDTH : panelWidths.left,
    context: contextCollapsed ? COLLAPSED_PANEL_WIDTH : panelWidths.context,
  };
  const layoutStyle = {
    "--nav-width": `${effectivePanelWidths.nav}px`,
    "--left-width": `${effectivePanelWidths.left}px`,
    "--context-width": `${effectivePanelWidths.context}px`,
  };

  useEffect(() => {
    localStorage.setItem(LAYOUT_WIDTHS_KEY, JSON.stringify(panelWidths));
  }, [panelWidths]);

  useEffect(() => {
    if (!dragState) return undefined;
    const previousCursor = document.body.style.cursor;
    const previousSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function handleMouseMove(event) {
      const dx = event.clientX - dragState.startX;
      const next = resizePanelWidths(dragState, dx);
      setPanelWidths(next);
    }

    function handleMouseUp() {
      setDragState(null);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousSelect;
    };
  }, [dragState]);

  function startLayoutResize(panel, event) {
    event.preventDefault();
    const containerWidth = layoutRef.current?.getBoundingClientRect().width || window.innerWidth || 1280;
    const collapsed = {
      nav: panel === "nav" ? false : navCollapsed,
      left: panel === "left" ? false : leftCollapsed,
      context: panel === "context" ? false : contextCollapsed,
    };
    if (panel === "nav" && navCollapsed) setNavCollapsed(false);
    if (panel === "left" && leftCollapsed) setLeftCollapsed(false);
    if (panel === "context" && contextCollapsed) setContextCollapsed(false);
    setDragState({
      panel,
      startX: event.clientX,
      widths: { ...panelWidths },
      collapsed,
      containerWidth,
    });
  }

  function toggleSplitterPanel(panel) {
    if (panel === "nav") setNavCollapsed((value) => !value);
    if (panel === "left") setLeftCollapsed((value) => !value);
    if (panel === "context") setContextCollapsed((value) => !value);
  }

  return {
    layoutRef,
    layoutStyle,
    isLayoutDragging: Boolean(dragState),
    resizingPanel: dragState?.panel || "",
    navCollapsed,
    leftCollapsed,
    contextCollapsed,
    setNavCollapsed,
    setLeftCollapsed,
    setContextCollapsed,
    startLayoutResize,
    toggleSplitterPanel,
  };
}

function loadLayoutWidths() {
  try {
    const stored = JSON.parse(localStorage.getItem(LAYOUT_WIDTHS_KEY) || "{}");
    return {
      nav: clampPanelWidth("nav", stored.nav),
      left: clampPanelWidth("left", stored.left),
      context: clampPanelWidth("context", stored.context),
    };
  } catch {
    return defaultPanelWidths();
  }
}

function defaultPanelWidths() {
  return {
    nav: PANEL_WIDTHS.nav.default,
    left: PANEL_WIDTHS.left.default,
    context: PANEL_WIDTHS.context.default,
  };
}

function resizePanelWidths(dragState, dx) {
  const { panel, widths, collapsed, containerWidth } = dragState;
  const next = { ...widths };
  const direction = panel === "context" ? -1 : 1;
  const maxWidth = maxPanelWidth(panel, widths, collapsed, containerWidth);
  next[panel] = clampPanelWidth(panel, widths[panel] + dx * direction, maxWidth);
  return next;
}

function maxPanelWidth(panel, widths, collapsed, containerWidth) {
  const nav = panel === "nav" ? 0 : effectivePanelWidth("nav", widths, collapsed);
  const left = panel === "left" ? 0 : effectivePanelWidth("left", widths, collapsed);
  const context = panel === "context" ? 0 : effectivePanelWidth("context", widths, collapsed);
  const available = Number(containerWidth || 0) - nav - left - context - CENTER_MIN_WIDTH;
  const hardMax = PANEL_WIDTHS[panel]?.max || available;
  return Math.max(PANEL_WIDTHS[panel].min, Math.min(hardMax, available));
}

function effectivePanelWidth(panel, widths, collapsed) {
  return collapsed?.[panel] ? COLLAPSED_PANEL_WIDTH : clampPanelWidth(panel, widths?.[panel]);
}

function clampPanelWidth(panel, value, max = PANEL_WIDTHS[panel]?.max) {
  const spec = PANEL_WIDTHS[panel];
  const numeric = Number(value);
  const fallback = spec.default;
  const width = Number.isFinite(numeric) ? numeric : fallback;
  return Math.round(Math.min(Math.max(width, spec.min), max || spec.max));
}
