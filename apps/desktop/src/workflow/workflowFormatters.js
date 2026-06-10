export function formatJson(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function formatStructuredWorkflowText(value, ui = null) {
  if (value == null || value === "") return "-";
  if (typeof value === "string") return hideTempPaths(value).replace(/\bTEMPORARY_OUTPUT\b/g, ui?.workflow?.temporaryResult || "临时结果");
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return formatJson(value);
}

export function riskLikePayload(item) {
  const payload = item && typeof item === "object" ? item : {};
  if (payload.risk && typeof payload.risk === "object") return payload.risk;
  const finding = payload.quality_finding && typeof payload.quality_finding === "object" ? payload.quality_finding : null;
  if (!finding) return null;
  const detail = finding.detail && typeof finding.detail === "object" ? finding.detail : {};
  const nestedRisk = detail.risk && typeof detail.risk === "object" ? detail.risk : {};
  const diagnosis = detail.diagnosis && typeof detail.diagnosis === "object"
    ? detail.diagnosis
    : (nestedRisk.diagnosis && typeof nestedRisk.diagnosis === "object" ? nestedRisk.diagnosis : {});
  return {
    message: finding.message || nestedRisk.message || "",
    diagnosis,
    severity: finding.severity || nestedRisk.severity || "warning",
  };
}

export function timelineCardContract(item) {
  const payload = item && typeof item === "object" ? item : {};
  const type = String(payload.type || payload.kind || "").trim();
  return {
    type,
    title: _timelineCardTitle(payload, type),
    text: _timelineCardText(payload),
    risk: riskLikePayload(payload),
  };
}

export function timelineCardModel(item, ui = null) {
  const payload = item && typeof item === "object" ? item : {};
  const contract = timelineCardContract(item);
  return {
    type: contract.type,
    title: String(payload.display_title || "").trim() || _timelineCardTitle(payload, contract.type, ui),
    text: formatStructuredWorkflowText(contract.text, ui),
    risk: contract.risk,
  };
}

export function friendlyActionTitle(action, ui = null, displayTitle = "") {
  const structured = String(displayTitle || "").trim();
  if (structured) return structured;
  const key = String(action || "").trim();
  const labels = ui?.workflow?.actionLabels || {};
  return labels[key] || LEGACY_ACTION_LABELS[key] || key.replace(/_/g, " ") || "-";
}

export function workflowStepContract(item) {
  const payload = item && typeof item === "object" ? item : {};
  const tool = String(payload.tool || payload.action || "").trim();
  return {
    tool,
    eventType: String(payload.event_type || "").trim(),
    displayTitle: String(payload.display_title || "").trim() || friendlyActionTitle(tool),
    displaySummary: String(payload.display_summary || payload.summary || payload.message || "").trim(),
    parameters: payload.parameters && typeof payload.parameters === "object" ? payload.parameters : null,
    parameterLabels: payload.parameter_labels && typeof payload.parameter_labels === "object" ? payload.parameter_labels : {},
    status: String(payload.status || "").trim(),
    outputPath: String(payload.output_path || "").trim(),
    summary: String(payload.summary || payload.message || "").trim(),
    data: payload.data && typeof payload.data === "object" ? payload.data : {},
    progressSummary: payload.progress_summary && typeof payload.progress_summary === "object" ? payload.progress_summary : {},
    artifactRefs: Array.isArray(payload.artifact_refs) ? payload.artifact_refs : [],
  };
}

export function workflowWarningContract(warning) {
  const contract = timelineCardContract({
    type: "warning_card",
    ...(warning && typeof warning === "object" ? warning : {}),
  });
  return {
    displayTitle: contract.title,
    displaySummary: contract.text,
    risk: contract.risk,
  };
}

export function parameterEntries(parameters, ui = null, parameterLabels = {}) {
  if (!parameters || typeof parameters !== "object" || Array.isArray(parameters)) return [];
  const labels = parameterLabels && typeof parameterLabels === "object" ? parameterLabels : {};
  return Object.entries(parameters)
    .filter(([key]) => key !== "__action")
    .map(([key, value]) => ({
      key,
      label: labels[key] || ui?.slots?.[key] || LEGACY_PARAMETER_LABELS[key] || key.replace(/_/g, " "),
      value: formatParameterValue(value, ui),
      title: typeof value === "string" ? value : formatJson(value),
    }));
}

export function stringList(value) {
  return Array.isArray(value) ? value.map((item) => String(item || "").trim()).filter(Boolean) : [];
}

export function selectedChoiceLabels(decision) {
  return stringList(
    Array.isArray(decision?.selected_choices)
      ? decision.selected_choices.map((item) => (item && typeof item === "object" ? item.label || item.value : item))
      : []
  );
}

export function selectedChoiceText(decision, separator = "; ") {
  return selectedChoiceLabels(decision).join(separator);
}

export function compactObjectText(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  return Object.entries(value)
    .map(([key, item]) => `${key}: ${String(item)}`)
    .join("; ");
}

export function compactDetailEntries(entries) {
  return entries
    .map(([label, value]) => ({ label: String(label || "").trim(), value: String(value ?? "").trim() }))
    .filter((entry) => entry.label && entry.value);
}

export function diagnosisDisplayModel(diagnosis, ui = null) {
  const payload = diagnosis && typeof diagnosis === "object" ? diagnosis : {};
  const causes = stringList(payload.possible_causes).map((cause) => friendlyDiagnosisText(cause, ui));
  const actions = normalizeDiagnosisActions(payload.suggested_actions, payload.suggested_next_actions, ui);
  return { causes, actions };
}

export function compactLayerStats(metadata, ui = null) {
  const payload = metadata && typeof metadata === "object" ? metadata : {};
  const parts = [];
  const features = payload.feature_count ?? payload.row_count;
  if (features != null) parts.push(`${formatCount(features)} ${payload.row_count != null ? (ui?.layers?.rows || "行") : (ui?.layers?.features || "要素")}`);
  if (payload.crs) parts.push(`${ui?.layers?.crs || "CRS"} ${payload.crs}`);
  if (payload.geometry_type) parts.push(`${ui?.layers?.geometry || "几何"} ${payload.geometry_type}`);
  return parts.length ? parts.join(" · ") : "";
}

export function formatDisplayPath(path, ui = null) {
  const text = String(path || "").trim();
  if (!text) return "";
  if (text === "TEMPORARY_OUTPUT") return ui?.workflow?.temporaryResult || "临时结果";
  const filename = fileNameFromPath(text);
  if (isTempPath(text)) return filename ? `${ui?.workflow?.temporaryResult || "临时结果"}：${filename}` : ui?.workflow?.temporaryResult || "临时结果";
  return filename || text;
}

export function hideTempPaths(text) {
  return String(text || "").replace(/[A-Za-z]:[\\/][^\s"'<>]*\.pineflow[\\/][^\s"'<>]*[\\/]temp[\\/][^\s"'<>]+/gi, (path) => fileNameFromPath(path));
}

export function isTempPath(path) {
  const normalized = String(path || "").replaceAll("/", "\\").toLowerCase();
  return normalized.includes("\\.pineflow\\sessions\\") && normalized.includes("\\temp\\");
}

function formatParameterValue(value, ui) {
  if (value == null || value === "") return ui?.common?.auto || "auto";
  if (value === "TEMPORARY_OUTPUT") return ui?.workflow?.temporaryResult || "临时结果";
  if (typeof value === "string") return formatDisplayPath(value, ui) || value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((item) => formatParameterValue(item, ui)).join(", ");
  return formatJson(value);
}

function fileNameFromPath(path) {
  const normalized = String(path || "").replaceAll("/", "\\");
  return normalized.split("\\").filter(Boolean).pop() || normalized;
}

function formatCount(value) {
  const number = Number(value);
  if (Number.isFinite(number)) return new Intl.NumberFormat("en-US").format(number);
  return String(value);
}

function _timelineCardTitle(payload, type, ui) {
  const structured = String(payload.display_title || "").trim();
  if (structured) return structured;
  if (type === "confirmation_card" || type === "confirmation") return ui?.workflow?.confirmation || "需要确认";
  if (type === "question_card" || type === "question") return ui?.workflow?.question || "需要补充输入";
  if ((type === "warning_card" || type === "warning") && payload.quality_finding) {
    return ui?.decisions?.qualityTitle || "质量发现";
  }
  if (type === "warning_card" || type === "warning") return ui?.workflow?.warning || "数据质量提示";
  if (type === "repair") return ui?.workflow?.repair || "修复";
  if (type === "retry") return ui?.workflow?.retry || "重试";
  if (type === "artifact_summary") return ui?.workflow?.output || "输出";
  return ui?.workflow?.output || "输出";
}

function _timelineCardText(payload) {
  if (String(payload.type || payload.kind || "").trim() === "artifact_summary") {
    const artifactText = _artifactSummaryText(payload);
    if (artifactText) return artifactText;
  }
  return String(payload.display_summary || payload.text || payload.message || "").trim();
}

function _artifactSummaryText(payload) {
  const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : [];
  if (!artifacts.length) return "";
  return artifacts
    .map((artifact) => {
      if (!artifact || typeof artifact !== "object") return "";
      const summary = String(artifact.display_summary || "").trim();
      if (summary) return summary;
      const summaryLines = Array.isArray(artifact.summary_lines)
        ? artifact.summary_lines.map((line) => String(line || "").trim()).filter(Boolean)
        : [];
      if (summaryLines.length) return summaryLines.join("\n");
      const name = String(artifact.name || artifact.artifact_id || artifact.layer_id || "输出").trim();
      const path = formatDisplayPath(artifact.path || artifact.source || "");
      if (name && path) return `${name}: ${path}`;
      return name || path;
    })
    .filter(Boolean)
    .join("\n");
}

function normalizeDiagnosisActions(actions, fallbackActions, ui) {
  if (Array.isArray(actions) && actions.length) {
    return actions
      .filter((item) => item && typeof item === "object")
      .map((item) => {
        const key = String(item.key || item.label || "").trim();
        return {
          key,
          label: ui?.diagnosis?.actions?.[key] || String(item.label || key).trim(),
        };
      })
      .filter((item) => item.label);
  }
  return stringList(fallbackActions).map((label, index) => ({
    key: `fallback-${index}`,
    label: friendlyDiagnosisText(label, ui),
  }));
}

function friendlyDiagnosisText(text, ui) {
  const dictionary = ui?.diagnosis?.phrases || {};
  return dictionary[text] || text;
}

// Legacy/debug fallback only. New workflow items must carry backend
// display_title and parameter_labels from ToolDefinition/YAML contracts.
const LEGACY_PARAMETER_LABELS = {};
const LEGACY_ACTION_LABELS = {
  select_toolkit: "准备工具能力",
  inspect_workspace: "检查工作区",
  load_skill: "加载 GIS 知识",
  run_algorithm: "运行处理算法",
  final_answer: "完成任务",
};
