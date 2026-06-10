import { sessionStatusHintFromEvent } from "./runEventProjection.js";

export function applyEventToSnapshot(snapshot, event, ui) {
  void ui;
  const normalizedEvent = normalizeEventRecord(event);
  if (!normalizedEvent) return snapshot;
  const events = appendSessionEvent(snapshot.events, normalizedEvent);
  const statusHint = sessionStatusHintFromEvent(normalizedEvent);
  const runId = String(normalizedEvent?.run_id || snapshot?.latest_run?.run_id || "").trim();
  const next = {
    ...snapshot,
    events,
    lastSeq: Math.max(Number(snapshot.lastSeq || 0), maxEventSeq(events)),
  };
  if (normalizedEvent.session_id) next.sessionId = normalizedEvent.session_id;
  if (statusHint) next.status = statusHint;
  else if (!next.status || next.status === "idle") next.status = "running";
  next.latest_run = latestRunFromEvent(snapshot.latest_run, normalizedEvent, next.status, runId);
  return next;
}

export function eventFromRecord(record) {
  const payload = record && typeof record === "object" ? record.payload : null;
  if (!payload || typeof payload !== "object") return null;
  return {
    ...payload,
    seq: payload.seq || record.seq,
    run_id: payload.run_id || record.run_id,
    session_id: payload.session_id || record.session_id,
  };
}

export function normalizeEventRecord(record) {
  const payloadEvent = eventFromRecord(record);
  if (payloadEvent) return payloadEvent;
  if (!record || typeof record !== "object") return null;
  if (!record.event && !record.event_type && !record.run_id && !record.seq) return null;
  return { ...record };
}

export function normalizeEventRecords(records) {
  return (Array.isArray(records) ? records : [])
    .map((record) => normalizeEventRecord(record))
    .filter(Boolean);
}

export function maxEventSeq(events) {
  let maxSeq = 0;
  for (const event of Array.isArray(events) ? events : []) {
    const seq = Number(event?.seq || 0);
    if (Number.isFinite(seq) && seq > maxSeq) maxSeq = seq;
  }
  return maxSeq;
}

function appendSessionEvent(events, event) {
  const current = normalizeEventRecords(events);
  const seq = Number(event?.seq || 0);
  if (seq > 0 && current.some((item) => Number(item?.seq || 0) === seq)) {
    return current;
  }
  return [...current, event];
}

function latestRunFromEvent(current, event, status, runId = "") {
  const normalizedRunId = String(runId || event?.run_id || current?.run_id || "").trim();
  const sessionId = String(event?.session_id || current?.session_id || "").trim();
  const resultStatus = String(status || current?.result_status || "").trim();
  const updatedAt = String(event?.created_at || current?.updated_at || "").trim();
  const requestedStatus = String(event?.status || "").trim();
  const nextStatus = String(resultStatus || requestedStatus || current?.status || "running");
  if (!normalizedRunId) return current || {};
  return {
    ...(current && typeof current === "object" ? current : {}),
    run_id: normalizedRunId,
    session_id: sessionId,
    status: nextStatus,
    result_status: resultStatus,
    updated_at: updatedAt,
  };
}
