import { workflowStepContract, workflowWarningContract } from "./workflowFormatters.js";

export function buildWorkflowModel(result) {
  const transcript = result?.transcript && typeof result.transcript === "object" ? result.transcript : {};
  const timeline = Array.isArray(transcript.timeline) ? transcript.timeline : [];
  const workflowItems = timeline.filter((item) => item?.type === "workflow_step");
  const resultStatus = String(result?.status || "").toLowerCase();
  const runCompleted = resultStatus === "completed";
  const steps = workflowItems.map((item, index) => workflowStepFromTranscriptItem(item, index, resultStatus, runCompleted));
  return {
    steps,
    nodeCount: steps.reduce((total, step) => total + step.nodes.length, 0),
    summary: result?.final_message || "",
  };
}

function workflowStepFromTranscriptItem(item, index, resultStatus, runCompleted) {
  const contract = workflowStepContract(item);
  const tool = contract.tool;
  const status = contract.status;
  const eventType = contract.eventType;
  const displayTitle = contract.displayTitle;
  const displaySummary = contract.displaySummary;
  const nodes = [];
  if (tool) {
    nodes.push({
      type: "action",
      eventType,
      action: tool,
      command: displayTitle,
      displayTitle,
      parameters: contract.parameters,
      parameterLabels: contract.parameterLabels,
    });
  }
  if (displaySummary || contract.summary || contract.outputPath || status) {
    nodes.push({
      type: "observation",
      eventType,
      text: displaySummary || contract.summary,
      displaySummary,
      observation: {
        status: status || "success",
        message: displaySummary || contract.summary,
        output_path: contract.outputPath,
        data: contract.data,
      },
    });
  }
  for (const warning of Array.isArray(item.warnings) ? item.warnings : []) {
    if (!warning || typeof warning !== "object") continue;
    const warningContract = workflowWarningContract(warning);
    nodes.push({
      type: "warning",
      text: warningContract.displaySummary,
      displayTitle: warningContract.displayTitle,
      displaySummary: warningContract.displaySummary,
      risk: warningContract.risk,
    });
  }
  return {
    id: String(item.event_key || item.id || `transcript-step-${item.index || index + 1}`),
    title: displayTitle,
    eventType,
    objective: "",
    sourceStatus: status || resultStatus || "completed",
    displayStatus: workflowDisplayStatus(status, resultStatus, runCompleted),
    artifactRefs: Array.isArray(item.artifact_refs) ? item.artifact_refs : [],
    nodes,
  };
}

function workflowDisplayStatus(stepStatus, resultStatus, runCompleted) {
  const normalized = String(stepStatus || "").toLowerCase();
  if (normalized === "error" || normalized === "failed") return "error";
  if (runCompleted || normalized === "success" || normalized === "completed") return "done";
  if (resultStatus === "awaiting_user" || resultStatus === "awaiting_confirmation") return "awaiting";
  if (resultStatus === "running") return "current";
  return "done";
}
