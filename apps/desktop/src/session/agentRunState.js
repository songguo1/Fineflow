import { eventLabel } from "./resultState.js";

const AWAITING_STATUSES = new Set(["awaiting_user", "awaiting_confirmation"]);
const ACTIVE_TRANSPORT_STATUSES = new Set(["created", "initializing", "running", "pause_requested", "cancel_requested"]);

export function deriveAgentRunState({ status, sessionResult, visibleRunSnapshot, events, error = "" }) {
  const hasVisibleRun = Boolean(visibleRunSnapshot && Object.keys(visibleRunSnapshot).length);
  const executionResult = hasVisibleRun
    && visibleRunSnapshot?.result
    && typeof visibleRunSnapshot.result === "object"
    && Object.keys(visibleRunSnapshot.result).length
    ? visibleRunSnapshot.result
    : sessionResult;
  const resultStatus = String(executionResult?.status || visibleRunSnapshot?.status || sessionResult?.status || "").trim();
  const baseStatus = String(status || resultStatus || "idle").trim() || "idle";
  const latestEvent = latestMeaningfulEvent(events);
  const latestLabel = eventLabel(latestEvent);
  const eventResultStatus = String(latestEvent?.result?.status || "").trim();
  const statusFromPauseEvent = AWAITING_STATUSES.has(eventResultStatus)
    ? eventResultStatus
    : latestLabel === "question" && latestEvent?.result
        ? "awaiting_user"
        : "";

  let phase = statusFromPauseEvent || resultStatus || baseStatus;
  if (ACTIVE_TRANSPORT_STATUSES.has(baseStatus)) {
    if (statusFromPauseEvent) phase = statusFromPauseEvent;
    else if (latestLabel === "repair") phase = "repairing";
    else if (latestLabel === "retry") phase = "retrying";
    else phase = baseStatus === "running" ? "running" : baseStatus;
  }
  if (latestLabel === "failed") phase = "failed";
  if (latestLabel === "cancelled") phase = "cancelled";
  if (latestLabel === "completed" && latestEvent?.result?.status) phase = String(latestEvent.result.status);
  if (error && phase === "running") phase = "failed";

  const isAwaiting = AWAITING_STATUSES.has(phase);
  const pendingTask = isAwaiting
    ? firstObject(
        executionResult?.pending_task,
        visibleRunSnapshot?.pending_task,
        latestEvent?.result?.pending_task,
        latestEvent?.pending_task
      )
    : hasVisibleRun
        ? firstObject(executionResult?.pending_task, visibleRunSnapshot?.pending_task)
        : firstObject(executionResult?.pending_task);
  const missingSlots = Array.isArray(pendingTask.missing_slots) ? pendingTask.missing_slots : [];
  const allowedActions = Array.isArray(pendingTask.allowed_actions) ? pendingTask.allowed_actions : [];
  const issues = firstArray(executionResult?.issues, latestEvent?.result?.issues, latestEvent?.issues);
  const risks = firstArray(executionResult?.risks, latestEvent?.result?.risks, latestEvent?.risks);
  const pendingRisk = firstObject(pendingTask.risk);
  const repair = isAwaiting || phase === "repairing"
    ? firstObject(executionResult?.repair, latestEvent?.result?.repair, latestEvent?.repair)
    : hasVisibleRun
        ? firstObject(executionResult?.repair)
        : firstObject(executionResult?.repair, visibleRunSnapshot?.repair);

  return {
    status: phase,
    transportStatus: baseStatus,
    latestEvent,
    latestEventLabel: latestLabel,
    pendingTask,
    missingSlots,
    allowedActions,
    issues,
    risks,
    activeIssue: issues[0] || null,
    activeRisk: pendingRisk || firstObject(risks[0]) || null,
    repair,
    isRunning: ACTIVE_TRANSPORT_STATUSES.has(baseStatus) && !AWAITING_STATUSES.has(phase),
    isPauseRequested: phase === "pause_requested",
    isCancelRequested: phase === "cancel_requested",
    isRepairing: phase === "repairing",
    isRetrying: phase === "retrying",
    isAwaitingUser: phase === "awaiting_user",
    isAwaitingConfirmation: phase === "awaiting_confirmation",
    isCompleted: phase === "completed",
    isFailed: phase === "failed",
    isPaused: phase === "paused",
    isCancelled: phase === "cancelled",
    hasPendingInteraction: isAwaiting,
    canPatch: allowedActions.includes("patch") && missingSlots.length > 0,
    canReplan: allowedActions.includes("replan"),
    canCancel: allowedActions.includes("cancel"),
    canConfirm: allowedActions.includes("confirm"),
    canReject: allowedActions.includes("reject"),
    latestError: latestLabel === "failed"
      ? latestEvent?.message || executionResult?.final_message || sessionResult?.final_message || error
      : error,
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

function firstArray(...values) {
  for (const value of values) {
    if (Array.isArray(value) && value.length) return value;
  }
  return [];
}

function latestMeaningfulEvent(events) {
  if (!Array.isArray(events)) return null;
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    const label = eventLabel(event);
    if (label && label !== "session") return event;
  }
  return null;
}
