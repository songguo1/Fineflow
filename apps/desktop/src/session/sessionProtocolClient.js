import {
  archiveSession,
  deleteSession,
  getSession,
  getSessionMemory,
  listSessionEvents,
  listSessionRuns,
  listSessions,
  saveSessionMemory,
} from "../api/apiClient.js";

export function createSessionProtocolClient(baseUrl) {
  return {
    listSessionSummaries() {
      return listSessions(baseUrl);
    },
    loadSession(sessionId) {
      return getSession(baseUrl, sessionId);
    },
    listSessionRuns(sessionId) {
      return listSessionRuns(baseUrl, sessionId);
    },
    pollSessionEvents(sessionId, options) {
      return listSessionEvents(baseUrl, sessionId, options);
    },
    archiveSession(sessionId) {
      return archiveSession(baseUrl, sessionId);
    },
    deleteSession(sessionId) {
      return deleteSession(baseUrl, sessionId);
    },
    loadSessionMemory(sessionId) {
      return getSessionMemory(baseUrl, sessionId);
    },
    saveSessionMemory(sessionId, content) {
      return saveSessionMemory(baseUrl, sessionId, content);
    },
  };
}
