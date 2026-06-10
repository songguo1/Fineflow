import { useMemo, useState } from "react";

import { deriveAgentRunState } from "../session/agentRunState.js";
import { runScopedEvents } from "../session/activeRunView.js";
import { normalizeResult } from "../session/resultState.js";
import { buildSessionView } from "../session/sessionViewProjection.js";
import { stageVisibleRunSnapshot } from "../session/transcriptProjection.js";

export function useAppSessionState() {
  const [sources, setSources] = useState([]);
  const [message, setMessage] = useState("");
  const [events, setEvents] = useState([]);
  const [result, setResult] = useState(null);
  const [visibleRunSnapshot, setVisibleRunSnapshot] = useState({});
  const [sessionId, setSessionId] = useState("");
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  const normalizedSessionResult = normalizeResult(result);
  const sessionView = useMemo(
    () => buildSessionView({ sessionResult: result, visibleRunSnapshot, status, events, error }),
    [result, visibleRunSnapshot, status, events, error]
  );
  const runState = useMemo(
    () => deriveAgentRunState({ status, sessionResult: normalizedSessionResult, visibleRunSnapshot, events, error }),
    [status, normalizedSessionResult, visibleRunSnapshot, events, error]
  );

  function resetSessionState() {
    setSessionId("");
    setRunId("");
    setStatus("idle");
    setEvents([]);
    setResult(null);
    setVisibleRunSnapshot({});
    setMessage("");
    setError("");
    setSources([]);
  }

  function applySessionSnapshot(snapshot) {
    const nextRunId = String(snapshot.runId || snapshot.latest_run?.run_id || "");
    setSessionId(snapshot.sessionId || "");
    setRunId(nextRunId);
    setStatus(snapshot.status || "idle");
    setResult(snapshot.result || null);
    setVisibleRunSnapshot(snapshot.visibleRunSnapshot || {});
    setEvents(runScopedEvents(snapshot.events || snapshot.sessionEvents || [], nextRunId));
    setMessage("");
    setSources(snapshot.sources || []);
    setError("");
  }

  function adoptActiveRun({ sessionId: nextSessionId = "", runId: nextRunId = "" } = {}) {
    const normalizedSessionId = String(nextSessionId || "").trim();
    const normalizedRunId = String(nextRunId || "").trim();
    if (normalizedSessionId) setSessionId(normalizedSessionId);
    if (normalizedRunId) setRunId(normalizedRunId);
  }

  function beginVisibleRun({ preserveEvents = false, userMessage = "", showUserMessage = true } = {}) {
    setStatus("running");
    setError("");
    if (!preserveEvents) {
      setEvents([]);
    }
    setVisibleRunSnapshot((current) =>
      stageVisibleRunSnapshot(current, {
        sessionId,
        preserveEvents,
        status: "running",
      })
    );
  }

  return {
    sources,
    setSources,
    message,
    setMessage,
    events,
    setEvents,
    result,
    setResult,
    visibleRunSnapshot,
    setVisibleRunSnapshot,
    sessionId,
    setSessionId,
    runId,
    setRunId,
    status,
    setStatus,
    error,
    setError,
    normalized: normalizedSessionResult,
    sessionView,
    runState,
    resetSessionState,
    applySessionSnapshot,
    adoptActiveRun,
    beginVisibleRun,
  };
}
