import { useEffect, useState } from "react";

import { createSessionProtocolClient } from "../session/sessionProtocolClient.js";

export function useSessionMemory({ apiBaseUrl, sessionId, ui, onError }) {
  const [sessionMemory, setSessionMemory] = useState("");
  const [sessionMemoryDraft, setSessionMemoryDraft] = useState("");
  const [memoryEditing, setMemoryEditing] = useState(false);
  const protocol = createSessionProtocolClient(apiBaseUrl);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!sessionId) {
        resetMemory();
        return;
      }
      try {
        const content = await protocol.loadSessionMemory(sessionId);
        if (cancelled) return;
        setSessionMemory(content);
        setSessionMemoryDraft(content);
        setMemoryEditing(false);
      } catch {
        if (!cancelled) resetMemory();
      }
    }
    load();
    return () => { cancelled = true; };
  }, [apiBaseUrl, sessionId]);

  async function saveMemory() {
    if (!sessionId) return;
    try {
      await protocol.saveSessionMemory(sessionId, sessionMemoryDraft);
      setSessionMemory(sessionMemoryDraft);
      setMemoryEditing(false);
    } catch {
      onError?.(ui.memory.saveFailed);
    }
  }

  function resetMemory() {
    setSessionMemory("");
    setSessionMemoryDraft("");
    setMemoryEditing(false);
  }

  return {
    sessionMemory,
    sessionMemoryDraft,
    memoryEditing,
    setSessionMemoryDraft,
    setMemoryEditing,
    saveMemory,
    resetMemory,
  };
}
