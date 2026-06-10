import {
  createRun,
  getRun,
  getRunSnapshot,
  listRunEvents,
  resumeRun,
  sendRunAction,
} from "../api/apiClient.js";

export function createRunProtocolClient(baseUrl) {
  return {
    createExecutionRun(request) {
      return createRun(baseUrl, request);
    },
    resumeExecutionRun(runId, request) {
      return resumeRun(baseUrl, runId, request);
    },
    sendRunControlAction(runId, action) {
      return sendRunAction(baseUrl, runId, action);
    },
    loadRun(runId) {
      return getRun(baseUrl, runId);
    },
    loadRunSnapshot(runId) {
      return getRunSnapshot(baseUrl, runId);
    },
    pollRunEvents(runId, options) {
      return listRunEvents(baseUrl, runId, options);
    },
  };
}

export function nextRunIdFromControlResponse(response, fallbackRunId = "") {
  return String(response?.next_run_id || response?.run_id || response?.run?.run_id || fallbackRunId || "").trim();
}

export function sessionIdFromControlResponse(response, fallbackSessionId = "") {
  return String(response?.session_id || response?.run?.session_id || fallbackSessionId || "").trim();
}
