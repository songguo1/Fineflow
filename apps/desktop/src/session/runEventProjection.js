const SNAPSHOT_REFRESH_EVENT_NAMES = new Set([
  "observation",
  "warning",
  "empty_result",
  "question",
  "confirmation",
  "repair",
  "repair_success",
  "before_export",
  "completed",
  "failed",
  "paused",
  "cancelled",
]);

const SNAPSHOT_REFRESH_EVENT_TYPES = new Set([
  "tool.completed",
  "tool.failed",
  "artifact.created",
  "warning.emitted",
  "result.empty",
  "user_input.requested",
  "repair.confirmation_requested",
  "repair.started",
  "repair.completed",
  "repair.failed",
  "export.before",
  "run.completed",
  "run.failed",
  "run.paused",
  "run.cancelled",
]);

const SESSION_STATUS_EVENT_NAMES = {
  completed: "completed",
  failed: "failed",
  paused: "paused",
  cancelled: "cancelled",
};

export function eventNeedsSnapshotRefresh(event) {
  const eventName = String(event?.event || "").trim();
  const eventType = String(event?.event_type || "").trim();
  if (SNAPSHOT_REFRESH_EVENT_NAMES.has(eventName)) return true;
  if (SNAPSHOT_REFRESH_EVENT_TYPES.has(eventType)) return true;
  if (event?.pending_task && typeof event.pending_task === "object" && Object.keys(event.pending_task).length) {
    return true;
  }
  return false;
}

export function sessionStatusHintFromEvent(event) {
  const resultStatus = String(event?.result?.status || "").trim();
  if (resultStatus) return resultStatus;
  const eventName = String(event?.event || "").trim();
  return SESSION_STATUS_EVENT_NAMES[eventName] || "";
}
