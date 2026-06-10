const AGENT_AUTO_REPAIR = true;
const AGENT_TOOL_PROTOCOL = "native_tools";

export function useAgentActions({
  settings,
  apiKey,
  qgis,
  sources,
  sessionId,
  runId,
  message,
  resumeMode,
  allowedActions,
  isAwaitingUser,
  isAwaitingConfirmation,
  hasPendingInteraction,
  runState,
  ui,
  performRunRequest,
  performRunAction,
  resetLocalSession,
  setError,
  setStatus,
  setSettingsOpen,
}) {
  async function send() {
    if (runState.isRunning) return;
    const text = message.trim();
    if (!text) return;
    if (isAwaitingUser && resumeMode === "replan" && allowedActions.includes("replan")) {
      await submitStructuredResume("replan", { messageText: text, userMessage: text });
      return;
    }
    await submitMessage(text);
  }

  async function submitPatch(slotPatch, userMessage) {
    await submitStructuredResume("patch", { slotPatch, userMessage });
  }

  async function submitSourceRequest(sourceRequest, selectedSources, nextSources) {
    if (!validateSettings()) return;
    if (!runId) {
      setError(ui.errors.requestFailed);
      return;
    }
    const slotPatch = buildSourceRequestSlotPatch(sourceRequest, selectedSources);
    const displayMessage = summarizeSourceRequest(sourceRequest, selectedSources, ui);
    await submitStructuredResume("patch", {
      slotPatch,
      userMessage: displayMessage,
      messageText: displayMessage,
      sourceOverride: nextSources,
    });
  }

  async function resetSessionFromUi() {
    if (runState.isRunning) return;
    if (!window.confirm(ui.composer.confirmReset)) return;
    if (!sessionId || hasPendingInteraction) { resetLocalSession(); return; }
    await submitCommand("/reset", { alreadyConfirmed: true });
  }

  async function submitCommand(command, { alreadyConfirmed = false } = {}) {
    if (runState.isRunning) return;
    const normalizedCommand = String(command || "").trim();
    if (!normalizedCommand) return;
    if (normalizedCommand === "/reset") {
      if (!alreadyConfirmed && !window.confirm(ui.composer.confirmReset)) return;
      if (!sessionId || hasPendingInteraction) { resetLocalSession(); return; }
    }
    const request = buildExecutionRequest({ text: normalizedCommand, settings, apiKey, qgis, sources, sessionId });
    await performRunRequest(request, normalizedCommand, { clearInput: true, preserveEvents: false });
  }

  async function confirmRepair() {
    if (!isAwaitingConfirmation || runState.isRunning) return;
    await submitStructuredResume("confirm", { userMessage: ui.resume.confirmRepairMessage });
  }

  async function rejectRepair() {
    if (!isAwaitingConfirmation || runState.isRunning) return;
    await submitStructuredResume("reject", { userMessage: ui.resume.rejectRepairMessage });
  }

  async function cancelPendingTask() {
    if (!(isAwaitingUser || isAwaitingConfirmation) || runState.isRunning) return;
    await submitStructuredResume("cancel", { userMessage: ui.resume.cancelTaskMessage });
  }

  async function handlePause() {
    if (!runState.isRunning) return;
    if (!runId) return;
    try {
      await performRunAction({ action_type: "run.pause" }, "", {
        clearInput: false,
        preserveEvents: true,
        showUserMessage: false,
      });
    } catch (err) {
      setStatus?.("running");
      setError(err.message || ui.errors.requestFailed);
      throw err;
    }
  }

  async function handleCancelRun() {
    if (!runState.isRunning) return;
    if (!runId) return;
    try {
      await performRunAction({ action_type: "run.cancel" }, "", {
        clearInput: false,
        preserveEvents: true,
        showUserMessage: false,
      });
    } catch (err) {
      setStatus?.("running");
      setError(err.message || ui.errors.requestFailed);
      throw err;
    }
  }

  async function submitMessage(text) {
    if (!validateSettings()) return;
    const request = buildExecutionRequest({ text, settings, apiKey, qgis, sources, sessionId });
    await performRunRequest(request, text, { clearInput: true, preserveEvents: runState.hasPendingInteraction });
  }

  async function submitStructuredResume(action, { slotPatch = {}, messageText = "", userMessage = "", sourceOverride = null } = {}) {
    if (!validateSettings()) return;
    if (!runId) {
      setError(ui.errors.requestFailed);
      return;
    }
    const displayMessage = userMessage || messageText || `[${action}]`;
    const resumeMessage = messageText || displayMessage;
    const request = buildExecutionRequest({
      text: resumeMessage,
      settings,
      apiKey,
      qgis,
      sources: Array.isArray(sourceOverride) ? sourceOverride : sources,
      sessionId,
    });
    await performRunAction(
      buildRunControlAction(action, { slotPatch, message: resumeMessage, request, pendingTask: runState.pendingTask }),
      displayMessage,
      {
        clearInput: action !== "patch",
        preserveEvents: true,
        showUserMessage: !["confirm", "reject", "cancel"].includes(action),
      }
    );
  }

  function validateSettings() {
    if (!String(apiKey || "").trim()) {
      setError(ui.errors.apiKeyRequired);
      setSettingsOpen(true);
      return false;
    }
    if (!settings.baseUrl.trim() || !settings.model.trim()) {
      setError(ui.errors.baseUrlAndModelRequired);
      setSettingsOpen(true);
      return false;
    }
    return true;
  }

  return {
    send,
    submitPatch,
    resetSessionFromUi,
    submitCommand,
    confirmRepair,
    rejectRepair,
    cancelPendingTask,
    handlePause,
    handleCancelRun,
    submitSourceRequest,
  };
}

export function buildExecutionRequest({ text, settings, apiKey, qgis, sources, sessionId, resume = null }) {
  const request = {
    message: String(text || "resume").trim() || "resume",
    session_id: sessionId,
    sources,
    llm: {
      provider: settings.provider,
      base_url: settings.baseUrl,
      model: settings.model,
      api_key: String(apiKey || ""),
      llm_params: buildLlmParams(settings),
    },
    qgis,
    output: { directory: settings.outputDirectory, format: settings.outputFormat },
    options: { auto_repair: AGENT_AUTO_REPAIR, locale: settings.locale || "zh-CN", tool_protocol: AGENT_TOOL_PROTOCOL },
  };
  if (resume) request.resume = resume;
  return request;
}

function buildRunControlAction(action, { slotPatch = {}, message = "", request, pendingTask = null }) {
  const actionTypeByResumeAction = {
    confirm: "pending.answer",
    reject: "pending.reject",
    patch: "pending.patch_slots",
    cancel: "pending.cancel",
    replan: "pending.replan",
  };
  return {
    action_type: actionTypeByResumeAction[action] || "pending.answer",
    decision: action,
    message,
    slot_patch: slotPatch || {},
    pending_id: pendingTask?.pending_id || "",
    request,
  };
}

function buildLlmParams(settings) {
  const params = {};
  const maxTokens = Number(settings.llmMaxTokens);
  if (Number.isFinite(maxTokens) && maxTokens > 0) params.max_tokens = Math.floor(maxTokens);
  const topP = Number(settings.llmTopP);
  if (Number.isFinite(topP) && topP > 0 && topP <= 1) params.top_p = topP;
  if (settings.llmJsonMode) params.response_format = { type: "json_object" };
  return params;
}

function buildSourceRequestSlotPatch(sourceRequest, selectedSources) {
  const slot = String(sourceRequest?.slot || "").trim();
  const aliases = Array.isArray(selectedSources)
    ? selectedSources.map((item) => String(item?.alias || "").trim()).filter(Boolean)
    : [];
  if (!slot || !aliases.length) return {};
  if (slot.endsWith("_refs")) return { [slot]: aliases };
  return { [slot]: aliases[0] };
}

function summarizeSourceRequest(sourceRequest, selectedSources, ui) {
  const slot = String(sourceRequest?.slot_label || sourceRequest?.slot || "").trim();
  const aliases = Array.isArray(selectedSources)
    ? selectedSources.map((item) => item?.alias || item?.path || "").filter(Boolean)
    : [];
  const files = aliases.join(", ");
  return (ui.resume.sourceAttachedMessage || "已补充 {slot} 所需数据：{files}。继续当前任务。")
    .replace("{slot}", slot || (ui.resume.sourceTypeFallback || "数据"))
    .replace("{files}", files || ui.common.auto);
}
