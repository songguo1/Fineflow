export function runScopedEvents(events, runId) {
  const normalizedRunId = String(runId || "").trim();
  const items = Array.isArray(events) ? events : [];
  if (!normalizedRunId) return [];
  return items.filter((event) => String(event?.run_id || "").trim() === normalizedRunId);
}

export function canApplyActiveRunEvent({
  event,
  activeSessionId,
  activeRunId,
  expectedSessionId = "",
  expectedRunId = "",
  startedInBlankSession = false,
}) {
  const eventSessionId = String(event?.session_id || "").trim();
  const eventRunId = String(event?.run_id || "").trim();
  const visibleSessionId = String(activeSessionId || "").trim();
  const visibleRunId = String(activeRunId || "").trim();
  const targetSessionId = String(expectedSessionId || "").trim();
  const targetRunId = String(expectedRunId || "").trim();

  if (!eventRunId) return false;
  if (startedInBlankSession && !visibleSessionId && !visibleRunId && targetRunId && eventRunId === targetRunId) {
    return true;
  }
  if (visibleRunId) {
    if (eventRunId !== visibleRunId) return false;
    if (visibleSessionId && eventSessionId && eventSessionId !== visibleSessionId) return false;
    return true;
  }
  if (!visibleSessionId || !targetSessionId || visibleSessionId !== targetSessionId) return false;
  if (!targetRunId || eventRunId !== targetRunId) return false;
  if (eventSessionId && eventSessionId !== targetSessionId) return false;
  return true;
}

export function canApplyActiveRunSnapshot({ snapshot, activeSessionId, activeRunId }) {
  const snapshotRunId = String(snapshot?.run_id || "").trim();
  const snapshotSessionId = String(snapshot?.session_id || "").trim();
  const visibleRunId = String(activeRunId || "").trim();
  const visibleSessionId = String(activeSessionId || "").trim();
  if (!snapshotRunId) return false;
  if (visibleRunId) {
    if (snapshotRunId !== visibleRunId) return false;
    if (visibleSessionId && snapshotSessionId && snapshotSessionId !== visibleSessionId) return false;
    return true;
  }
  if (!visibleSessionId) return true;
  return Boolean(snapshotSessionId && snapshotSessionId === visibleSessionId);
}
