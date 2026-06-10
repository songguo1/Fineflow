import { normalizeResult } from "./resultState.js";
import { transcriptForSession } from "./transcriptProjection.js";

export function buildSessionView({ sessionResult, visibleRunSnapshot, status, events, error }) {
  const normalizedSession = normalizeResult(sessionResult);
  const normalizedVisibleRun = normalizeResult(visibleRunSnapshot?.result);
  const hasVisibleRun = Boolean(visibleRunSnapshot && Object.keys(visibleRunSnapshot).length);
  const transcript = transcriptForSession(normalizedSession);
  const rawResult = hasVisibleRun ? normalizedVisibleRun : normalizedSession;
  const pendingTask = hasVisibleRun
    ? firstObject(normalizedVisibleRun.pending_task, visibleRunSnapshot?.pending_task)
    : firstObject(normalizedSession.pending_task);
  const repair = hasVisibleRun
    ? firstObject(normalizedVisibleRun.repair)
    : firstObject(normalizedSession.repair);
  const issues = hasVisibleRun
    ? listFrom(normalizedVisibleRun.issues)
    : listFrom(normalizedSession.issues);
  const risks = hasVisibleRun
    ? listFrom(normalizedVisibleRun.risks)
    : listFrom(normalizedSession.risks);
  const stateTree = hasVisibleRun
    ? firstObject(normalizedVisibleRun.state_tree, visibleRunSnapshot?.tool_state?.state_tree)
    : firstObject(normalizedSession.state_tree);
  const fileState = hasVisibleRun
    ? firstObject(normalizedVisibleRun.file_state, visibleRunSnapshot?.tool_state?.file_state)
    : firstObject(normalizedSession.file_state);
  const outputs = hasVisibleRun
    ? listFrom(normalizedVisibleRun.outputs)
    : listFrom(normalizedSession.outputs);

  return {
    rawResult,
    transcript,
    runView: {
      status: String(status || visibleRunSnapshot?.status || rawResult.status || "idle"),
      resultStatus: String(rawResult.status || "idle"),
      pendingTask,
      repair,
      issues,
      risks,
      events: Array.isArray(events) ? events : [],
      error: String(error || ""),
    },
    toolState: {
      stateTree,
      fileState,
    },
    artifacts: {
      outputs,
    },
  };
}

function firstObject(...values) {
  for (const value of values) {
    if (value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length) {
      return value;
    }
  }
  return {};
}

function listFrom(value) {
  return Array.isArray(value) ? value : [];
}
