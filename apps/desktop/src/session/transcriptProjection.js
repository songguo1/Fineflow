export function normalizeTranscript(value) {
  const transcript = value && typeof value === "object" ? value : {};
  return {
    version: Math.max(Number(transcript.version || 0), 2),
    timeline: Array.isArray(transcript.timeline)
      ? transcript.timeline.filter((item) => item && typeof item === "object")
      : [],
  };
}

export function transcriptForSession(result) {
  const sessionTranscript = normalizeTranscript(result?.transcript);
  if (sessionTranscript.timeline.length) return sessionTranscript;
  return normalizeTranscript(result?.display_transcript);
}

export function stripTranscriptPayload(value) {
  if (!value || typeof value !== "object") return value;
  const payload = { ...value };
  delete payload.transcript;
  delete payload.display_transcript;
  if (payload.result && typeof payload.result === "object") {
    payload.result = stripTranscriptPayload(payload.result);
  }
  return payload;
}

export function stageVisibleRunSnapshot(
  currentSnapshot,
  {
    sessionId = "",
    preserveEvents = false,
    status = "running",
  } = {}
) {
  const snapshot = currentSnapshot && typeof currentSnapshot === "object" ? currentSnapshot : {};
  const hasSnapshot = Object.keys(snapshot).length > 0;
  const baseSnapshot = preserveEvents && hasSnapshot
    ? stripTranscriptPayload(snapshot)
    : {
        session_id: String(sessionId || snapshot.session_id || ""),
        status: String(status || "running"),
        result: { status: String(status || "running") },
      };
  const baseResult = baseSnapshot.result && typeof baseSnapshot.result === "object"
    ? stripTranscriptPayload(baseSnapshot.result)
    : { status: String(baseSnapshot.status || status || "running") };

  return {
    ...baseSnapshot,
    session_id: String(baseSnapshot.session_id || sessionId || ""),
    status: String(status || baseSnapshot.status || "running"),
    result: {
      ...baseResult,
      status: String(status || baseResult.status || baseSnapshot.status || "running"),
    },
  };
}
