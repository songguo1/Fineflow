import { useEffect, useRef, useState } from "react";

import { createRunProtocolClient } from "./runProtocolClient.js";
import { createSessionProtocolClient } from "./sessionProtocolClient.js";
import {
  activeRunResumePayload,
  emptySessionSnapshot,
  mergeRunSnapshotIntoSessionSnapshot,
  sessionSnapshotFromResponse,
} from "./sessionSnapshotProjection.js";

export function useSessionStore({
  apiBaseUrl,
  ui,
  currentSession,
  onApplySession,
  onResetSession,
  onError,
  onResumeRunPolling,
}) {
  const [sessions, setSessions] = useState([]);
  const switchTokenRef = useRef(0);
  const runProtocol = createRunProtocolClient(apiBaseUrl);
  const sessionProtocol = createSessionProtocolClient(apiBaseUrl);

  useEffect(() => {
    let cancelled = false;
    sessionProtocol.listSessionSummaries()
      .then((list) => { if (!cancelled) setSessions(list); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [apiBaseUrl, currentSession.sessionId, currentSession.status]);

  async function switchSession(sid) {
    onError?.("");
    const token = ++switchTokenRef.current;

    try {
      const data = await sessionProtocol.loadSession(sid);
      const snapshot = await withLatestRunSnapshot(sessionSnapshotFromResponse(sid, data));
      if (token !== switchTokenRef.current) return;
      onApplySession(snapshot);
      resumeActiveRunIfNeeded(snapshot);
    } catch {
      if (token !== switchTokenRef.current) return;
      onApplySession(emptySessionSnapshot(sid));
    }
  }

  function handleNewSession() {
    onResetSession();
  }

  function updateSessionSummary(sid, updater) {
    const sessionId = String(sid || "").trim();
    if (!sessionId || typeof updater !== "function") return;
    const next = updater(emptySessionSnapshot(sessionId));
    setSessions((items) => mergeSessionSummary(items, sessionId, next));
  }

  async function withLatestRunSnapshot(snapshot) {
    const runId = String(snapshot?.runId || snapshot?.latest_run?.run_id || "").trim();
    const sessionId = String(snapshot?.sessionId || "").trim();
    if (!runId) return snapshot;
    try {
      const runSnapshot = await runProtocol.loadRunSnapshot(runId);
      if (String(runSnapshot?.run_id || "").trim() && String(runSnapshot.run_id || "").trim() !== runId) {
        return snapshot;
      }
      const snapshotSessionId = String(runSnapshot?.session_id || "").trim();
      if (sessionId && snapshotSessionId && snapshotSessionId !== sessionId) {
        return snapshot;
      }
      return mergeRunSnapshotIntoSessionSnapshot(snapshot, runSnapshot);
    } catch {
      return snapshot;
    }
  }

  function resumeActiveRunIfNeeded(snapshot) {
    const payload = activeRunResumePayload(snapshot);
    if (payload) onResumeRunPolling?.(payload);
  }

  async function archiveSession(sid) {
    if (!window.confirm(ui.sessionNav.confirmArchive)) return;
    try {
      await sessionProtocol.archiveSession(sid);
      setSessions((current) => current.filter((s) => s.session_id !== sid));
      if (currentSession.sessionId === sid) onResetSession();
    } catch (err) {
      onError?.(err.message || "Archive failed");
    }
  }

  async function deleteSession(sid) {
    if (!window.confirm(ui.sessionNav.confirmDelete)) return;
    try {
      await sessionProtocol.deleteSession(sid);
      setSessions((current) => current.filter((s) => s.session_id !== sid));
      if (currentSession.sessionId === sid) onResetSession();
    } catch (err) {
      onError?.(err.message || "Delete failed");
    }
  }

  return {
    sessions,
    updateSessionSummary,
    switchSession,
    handleNewSession,
    archiveSession,
    deleteSession,
  };
}

function mergeSessionSummary(items, sessionId, snapshot) {
  let found = false;
  const nextItems = (Array.isArray(items) ? items : []).map((item) => {
    if (item.session_id !== sessionId) return item;
    found = true;
    return {
      ...item,
      status: snapshot.status || item.status,
      updated_at: snapshot.updated_at || item.updated_at,
      event_count: Array.isArray(snapshot.events) ? snapshot.events.length : item.event_count,
      latest_run: snapshot.latest_run || item.latest_run || {},
    };
  });
  if (found) return nextItems;
  return [
    {
      session_id: sessionId,
      status: snapshot.status || "running",
      first_message: firstUserMessage(snapshot.result) || "",
      updated_at: snapshot.updated_at || new Date().toISOString(),
      event_count: Array.isArray(snapshot.events) ? snapshot.events.length : 0,
      message_count: 0,
      latest_run: snapshot.latest_run || {},
    },
    ...nextItems,
  ];
}

function firstUserMessage(result) {
  const timeline = Array.isArray(result?.transcript?.timeline) ? result.transcript.timeline : [];
  const item = timeline.find((entry) => entry?.type === "user_message" && String(entry.text || "").trim());
  return String(item?.text || "").slice(0, 120);
}
