import { workflowStepContract, timelineCardModel } from "../workflow/workflowFormatters.js";

const SYSTEM_TOOLS = new Set(["select_toolkit", "load_skill", "inspect_workspace", "suggest_skill"]);
const ACTIVE_RUN_STATUSES = new Set([
  "running",
  "awaiting_user",
  "awaiting_confirmation",
  "repairing",
  "retrying",
  "pause_requested",
  "cancel_requested",
]);

export function buildRunNarrative({ transcript, runState, ui }) {
  const conversationTimeline = timelineFrom(transcript) || [];
  const items = [];
  const workflowGroups = collectWorkflowGroups(conversationTimeline);
  const workflowGroupMap = new Map(workflowGroups.map((group) => [group.startIndex, group]));
  const activeWorkflowStartIndex = activeGroupStartIndex(workflowGroups, runState);
  for (let index = 0; index < conversationTimeline.length; index += 1) {
    const item = conversationTimeline[index];
    if (item?.type === "user_message") {
      items.push({
        type: "user_request",
        runId: runIdOf(item),
        text: String(item.text || ""),
        key: itemKey(item, items.length),
      });
      continue;
    }
    if (item?.type === "assistant_answer") {
      items.push({
        type: "assistant_answer",
        runId: runIdOf(item),
        text: String(item.text || ""),
        key: itemKey(item, items.length),
      });
      continue;
    }
    if (item?.type === "resume_transition") {
      items.push({
        type: "resume_transition",
        runId: runIdOf(item),
        title: String(item.title || "").trim(),
        text: String(item.text || "").trim(),
        continueWith: String(item.continue_with || item.continueWith || "").trim(),
        resumeAction: String(item.resume_action || item.resumeAction || "").trim(),
        key: itemKey(item, items.length),
      });
      continue;
    }
    if (item?.type === "artifact_summary") {
      items.push({
        type: "artifact_summary",
        runId: runIdOf(item),
        title: String(item.title || item.display_title || "").trim(),
        text: String(item.text || item.display_summary || "").trim(),
        artifacts: Array.isArray(item.artifacts) ? item.artifacts.filter((artifact) => artifact && typeof artifact === "object") : [],
        key: itemKey(item, items.length),
      });
      continue;
    }
    if (item?.type === "workflow_step") {
      const group = workflowGroupMap.get(index);
      if (!group) continue;
      const narrative = buildWorkflowGroupNarrative(group, {
        isActiveGroup: group.startIndex === activeWorkflowStartIndex,
        runState,
        ui,
      });
      if (narrative) items.push(narrative);
      index = group.endIndex;
      continue;
    }
    if (item?.type) {
      const card = timelineCardModel(item, ui);
      if (card.title || card.text) {
        items.push({
          type: "notice",
          runId: runIdOf(item),
          card,
          key: itemKey(item, items.length),
        });
      }
    }
  }

  return normalizeNarrativeOrder(items);
}

function workflowStepNarrative(item, index) {
  const contract = workflowStepContract(item);
  return {
    id: String(item?.event_key || item?.id || `step-${index + 1}`),
    tool: contract.tool,
    title: contract.displayTitle,
    summary: contract.displaySummary || contract.summary,
    progressSummary: normalizeProgressSummary(contract.progressSummary),
    status: String(contract.status || item?.status || "").toLowerCase(),
  };
}

function collectWorkflowGroups(timeline) {
  const groups = [];
  for (let index = 0; index < timeline.length; index += 1) {
    const item = timeline[index];
    if (item?.type !== "workflow_step") continue;
    const startIndex = index;
    const items = [];
    while (index < timeline.length && timeline[index]?.type === "workflow_step") {
      items.push(timeline[index]);
      index += 1;
    }
    const endIndex = index - 1;
    groups.push({
      startIndex,
      endIndex,
      items,
    });
  }
  return groups;
}

function buildWorkflowGroupNarrative(group, { isActiveGroup, runState, ui }) {
  const steps = group.items
    .map((item, index) => workflowStepNarrative(item, index))
    .filter((step) => step.title || step.summary)
    .filter((step) => !SYSTEM_TOOLS.has(step.tool));
  if (!steps.length) return null;
  const status = String(runState?.status || "").toLowerCase();
  const rows = steps.map((step, index) => ({ ...step, state: progressState(step, index, steps, status, isActiveGroup) }));
  return {
    type: "progress_update",
    runId: runIdOf(group.items[0]),
    title: "",
    rows,
    summary: progressSummary(rows),
    key: itemKey(group.items[0], group.startIndex),
  };
}

function progressSummary(rows) {
  const doneRows = rows.filter((row) => row.state === "done" || row.state === "error");
  const current = rows.find((row) => row.state === "current");
  const latestDone = doneRows[doneRows.length - 1] || null;
  return {
    done: latestDone ? (latestDone.progressSummary.done || fallbackProgressText(latestDone)) : "",
    doing: current ? (current.progressSummary.doing || fallbackProgressText(current)) : "",
  };
}

function normalizeProgressSummary(value) {
  const payload = value && typeof value === "object" ? value : {};
  return {
    done: String(payload.done || "").trim(),
    doing: String(payload.doing || "").trim(),
  };
}

function fallbackProgressText(step) {
  const text = String(step.summary || step.title || "").trim();
  if (!text) return "";
  return text.endsWith("。") || text.endsWith(".") ? text : `${text}。`;
}

function progressState(step, index, steps, status, isActiveGroup) {
  if (step.status === "failed" || step.status === "error") return "error";
  if (!isActiveGroup) return "done";
  if (step.status === "running") return "current";
  if (ACTIVE_RUN_STATUSES.has(status) && index === steps.length - 1 && !isCompletedStep(step)) return "current";
  return "done";
}

function isCompletedStep(step) {
  return ["success", "completed", "done"].includes(String(step.status || "").toLowerCase());
}

function timelineFrom(value) {
  return Array.isArray(value?.timeline) ? value.timeline.filter((item) => item && typeof item === "object") : null;
}

function itemKey(item, index) {
  return String(item?.event_key || item?.id || `${item?.type || "item"}-${index}`);
}

function runIdOf(item) {
  const direct = String(item?.run_id || item?.runId || "").trim();
  if (direct) return direct;
  return runIdFromKey(item?.message_id) || runIdFromKey(item?.event_key) || runIdFromKey(item?.id);
}

function activeGroupStartIndex(groups, runState) {
  if (!Array.isArray(groups) || !groups.length) return -1;
  const status = String(runState?.status || "").toLowerCase();
  if (!ACTIVE_RUN_STATUSES.has(status)) return -1;
  return groups[groups.length - 1]?.startIndex ?? -1;
}

function normalizeNarrativeOrder(items) {
  const ordered = [];
  let block = [];
  let currentRunId = "";
  let hasUserAnchor = false;

  function flushBlock() {
    if (!block.length) return;
    const userItems = block.filter((item) => item.type === "user_request");
    const otherItems = block.filter((item) => item.type !== "user_request");
    ordered.push(...userItems, ...otherItems);
    block = [];
    currentRunId = "";
    hasUserAnchor = false;
  }

  for (const item of items) {
    const runId = String(item?.runId || "").trim();
    if (item?.type === "user_request") {
      if (hasUserAnchor) flushBlock();
      block.push(item);
      hasUserAnchor = true;
      if (runId) currentRunId = runId;
      continue;
    }

    if (hasUserAnchor) {
      if (runId && currentRunId && currentRunId !== runId) {
        flushBlock();
        currentRunId = runId;
        block.push(item);
        continue;
      }
      block.push(item);
      if (runId && !currentRunId) currentRunId = runId;
      continue;
    }

    if (!runId) {
      if (block.length) {
        block.push(item);
        continue;
      }
      ordered.push(item);
      continue;
    }

    if (!currentRunId || currentRunId === runId) {
      currentRunId = runId;
      block.push(item);
      continue;
    }
    flushBlock();
    currentRunId = runId;
    block.push(item);
  }

  flushBlock();
  return ordered;
}

function runIdFromKey(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const match = text.match(/^(?:message:)?run:([^:]+):/);
  return match ? match[1] : "";
}
