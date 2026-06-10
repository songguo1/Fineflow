import { useMemo, useState } from "react";
import { BadgeCheck, BookOpen, ChevronLeft, Copy, FileDown, FolderOpen, ListTree } from "lucide-react";

import { getSessionReport } from "../api/apiClient.js";
import { openPath } from "../shared/tauriBridge.js";
import { MarkdownText } from "../shared/MarkdownText.jsx";
import { buildWorkflowModel } from "../workflow/workflowModel.js";
import {
  formatDisplayPath,
  formatJson,
  formatStructuredWorkflowText,
  friendlyActionTitle,
  parameterEntries,
} from "../workflow/workflowFormatters.js";
import { RiskDiagnosisCard } from "../risk/RiskDiagnosisCard.jsx";
import { projectDecisionRows } from "./decisionRows.js";

const CONTEXT_TABS = [
  ["workflow", ListTree, "workflow"],
  ["layers", ListTree, "layers"],
  ["outputs", FileDown, "outputs"],
  ["decisions", BadgeCheck, "decisions"],
  ["memory", BookOpen, "memory"],
];

export function ContextPanel({
  ui,
  apiBaseUrl,
  result,
  toolStateView,
  artifactView,
  sessionMemory,
  memoryDraft,
  memoryEditing,
  onMemoryEdit,
  onMemoryChange,
  onMemorySave,
}) {
  const [tab, setTab] = useState("workflow");
  const workflowModel = useMemo(() => buildWorkflowModel(result), [result]);

  const tabLabels = {
    workflow: ui.workflow?.title || ui.sections.workflow || "处理过程",
    layers: ui.tabs.state || "Layers",
    outputs: ui.tabs.outputs || "Outputs",
    decisions: ui.tabs.decisions || "Decisions",
    memory: ui.tabs.memory || "Memory",
  };

  return (
    <div className="context-panel">
      <div className="context-tabs">
        {CONTEXT_TABS.map(([key, Icon, labelKey]) => (
          <button className={tab === key ? "active" : ""} onClick={() => setTab(key)} key={key}>
            <Icon size={13} /> {tabLabels[key] || labelKey}
          </button>
        ))}
      </div>
      <div className="context-panel-body">
        {tab === "workflow" ? <WorkflowTimelineView model={workflowModel} ui={ui} /> : null}
        {tab === "layers" ? <LayersView toolStateView={toolStateView} result={result} ui={ui} /> : null}
        {tab === "outputs" ? <OutputsView apiBaseUrl={apiBaseUrl} artifactView={artifactView} result={result} ui={ui} /> : null}
        {tab === "decisions" ? <DecisionAuditView result={result} ui={ui} /> : null}
        {tab === "memory" ? (
          <MemoryViewInline
            ui={ui}
            content={sessionMemory}
            draft={memoryDraft}
            editing={memoryEditing}
            onEdit={onMemoryEdit}
            onChange={onMemoryChange}
            onSave={onMemorySave}
          />
        ) : null}
      </div>
    </div>
  );
}

function LayersView({ toolStateView, result, ui }) {
  const layers = toolStateView?.stateTree?.layers || result?.state_tree?.layers || [];
  return (
    <div className="context-scroll">
      {layers.length ? layers.map((layer, i) => (
        <LayerCard layer={layer} index={i} ui={ui} key={layer.layer_id || i} />
      )) : <Empty text={ui.empty.noStateTree} />}
    </div>
  );
}

function listFrom(value) {
  return Array.isArray(value) ? value : [];
}

function WorkflowTimelineView({ model, ui }) {
  const steps = Array.isArray(model?.steps) ? model.steps : [];
  return (
    <div className="context-scroll workflow-timeline">
      {steps.length ? steps.map((step, index) => (
        <WorkflowStepCard
          step={step}
          index={index}
          defaultOpen={shouldOpenWorkflowStep(step, index, steps)}
          ui={ui}
          key={step.id || index}
        />
      )) : <Empty text={ui.workflow?.noPlan || "暂无流程事件。"} />}
    </div>
  );
}

function WorkflowStepCard({ step, index, defaultOpen, ui }) {
  const model = workflowStepDisplayModel(step, ui);
  return (
    <article className={`step-card workflow-step-card ${model.status}`}>
      <details open={defaultOpen}>
        <summary className="step-card-head">
          <span className="step-card-toggle" aria-hidden="true">›</span>
          <span className="step-card-index">{index + 1}</span>
          <div className="step-card-title">
            <strong>{model.title}</strong>
            <WorkflowStepSummary model={model} ui={ui} />
          </div>
          <span className={`step-card-badge ${model.status}`}>{model.statusLabel}</span>
        </summary>
        <div className="workflow-step-body">
          <WorkflowFactList model={model} ui={ui} />
          {model.warnings.length ? (
            <div className="workflow-step-risk-list">
              {model.warnings.map((warning, warningIndex) => (
                <div className="workflow-step-risk" key={`${model.id}-warning-${warningIndex}`}>
                  <strong>{warning.displayTitle || ui.workflow?.warning || "数据质量提示"}</strong>
                  <MarkdownText value={formatStructuredWorkflowText(warning.text || warning.displaySummary, ui)} fallback="-" />
                  <RiskDiagnosisCard risk={warning.risk} ui={ui} compact />
                </div>
              ))}
            </div>
          ) : null}
          <details className="workflow-debug-details">
            <summary>{ui.workflow?.debugDetails || "调试详情"}</summary>
            {model.actionNode ? <CodeBlock label={ui.workflow?.action || "处理操作"} value={model.actionNode} /> : null}
            {model.parameterObject ? <CodeBlock label={ui.workflow?.parameters || "参数"} value={model.parameterObject} /> : null}
            {model.observationNodes.length ? <CodeBlock label={ui.workflow?.observation || "处理结果"} value={model.observationNodes} /> : null}
          </details>
        </div>
      </details>
    </article>
  );
}

function shouldOpenWorkflowStep(step, index, steps) {
  const status = workflowTimelineStatus(step?.displayStatus, Array.isArray(step?.nodes) ? step.nodes.filter((node) => node?.type === "warning").length : 0);
  if (status === "running" || status === "awaiting_user" || status === "failed" || status === "warning") return true;
  return index === steps.length - 1;
}

function WorkflowStepSummary({ model, ui }) {
  const input = model.inputs.length ? model.inputs.map((item) => item.value).join("、") : "";
  const output = model.outputs.length ? model.outputs.map((item) => item.value).join("、") : "";
  if (!input && !output && !model.summary) {
    return <p>{ui.workflow?.waitingStep || "等待该步骤开始。"}</p>;
  }
  return (
    <div className="workflow-step-summary">
      {input ? <span><b>{ui.workflow?.input || "输入"}</b>{input}</span> : null}
      {output ? <span><b>{ui.workflow?.output || "输出"}</b>{output}</span> : null}
      {!input && !output && model.summary ? <span>{model.summary}</span> : null}
    </div>
  );
}

function WorkflowFactList({ model, ui }) {
  return (
    <div className="workflow-fact-list">
      <WorkflowFact label={ui.workflow?.tool || "工具"} value={model.toolLabel} />
      {model.toolId && model.toolId !== model.toolLabel ? <WorkflowFact label={ui.workflow?.toolId || "Tool ID"} value={model.toolId} /> : null}
      <WorkflowFact label={ui.workflow?.input || "输入"} values={model.inputs} />
      <WorkflowFact label={ui.workflow?.output || "输出"} values={model.outputs} />
      <WorkflowFact label={ui.workflow?.parameters || "参数"} values={model.parameters} />
      {model.summary ? <WorkflowFact label={ui.workflow?.observation || "处理结果"} value={model.summary} /> : null}
    </div>
  );
}

function WorkflowFact({ label, value, values }) {
  const items = Array.isArray(values) ? values : [];
  if (!value && !items.length) return null;
  return (
    <div className="workflow-fact">
      <b>{label}</b>
      {items.length ? (
        <div className="workflow-fact-chips">
          {items.map((item) => (
            <span title={item.title || item.value} key={`${item.label}-${item.value}`}>
              {item.label ? <em>{item.label}</em> : null}
              {item.value}
            </span>
          ))}
        </div>
      ) : <span>{value}</span>}
    </div>
  );
}

function workflowStepDisplayModel(step, ui) {
  const nodes = Array.isArray(step?.nodes) ? step.nodes : [];
  const actionNode = nodes.find((node) => node?.type === "action" || node?.type === "command") || null;
  const observationNodes = nodes.filter((node) => node?.type === "observation");
  const warnings = nodes.filter((node) => node?.type === "warning");
  const parameterObject = actionNode?.parameters && typeof actionNode.parameters === "object" ? actionNode.parameters : null;
  const parameterLabels = actionNode?.parameterLabels && typeof actionNode.parameterLabels === "object" ? actionNode.parameterLabels : {};
  const parameters = parameterEntries(parameterObject, ui, parameterLabels);
  const status = workflowTimelineStatus(step?.displayStatus, warnings.length);
  const action = actionNode?.action || actionNode?.command || "";
  const toolId = String(actionNode?.action || "").trim();
  return {
    id: step?.id || "",
    title: step?.title || friendlyActionTitle(action, ui, actionNode?.displayTitle) || ui.workflow?.stepFallback || "处理步骤",
    status,
    statusLabel: workflowStatusLabel(status, ui),
    toolLabel: friendlyActionTitle(action, ui, actionNode?.displayTitle),
    toolId,
    summary: workflowObservationSummary(observationNodes, ui),
    inputs: workflowFactItems(parameters, "input"),
    outputs: workflowOutputItems(parameters, observationNodes, step, ui),
    parameters: workflowParameterItems(parameters).slice(0, 8),
    warnings,
    actionNode,
    parameterObject,
    observationNodes,
  };
}

function workflowTimelineStatus(displayStatus, warningCount) {
  const status = String(displayStatus || "").toLowerCase();
  if (status === "error" || status === "failed") return "failed";
  if (status === "awaiting" || status === "awaiting_user" || status === "awaiting_confirmation") return "awaiting_user";
  if (status === "current" || status === "running") return "running";
  if (warningCount) return "warning";
  return "completed";
}

function workflowStatusLabel(status, ui) {
  const labels = ui.workflow?.statuses || {};
  return labels[status] || labels[status === "completed" ? "done" : status] || status;
}

function workflowFactItems(parameters, kind) {
  const keys = kind === "input" ? INPUT_SLOT_KEYS : OUTPUT_SLOT_KEYS;
  return uniqueWorkflowItems(parameters.filter((entry) => {
    const key = String(entry.key || "").toLowerCase();
    return keys.has(key);
  }));
}

function workflowParameterItems(parameters) {
  return uniqueWorkflowItems(parameters.filter((entry) => {
    const key = String(entry.key || "").toLowerCase();
    return !INPUT_SLOT_KEYS.has(key) && !OUTPUT_SLOT_KEYS.has(key);
  }));
}

function workflowOutputItems(parameters, observationNodes, step, ui) {
  const outputs = workflowFactItems(parameters, "output");
  for (const node of observationNodes) {
    const observation = normalizeObservationValue(node.observation || node.text);
    const layer = observation?.data?.layer && typeof observation.data.layer === "object" ? observation.data.layer : {};
    const metadata = layer.metadata && typeof layer.metadata === "object" ? layer.metadata : {};
    const outputPath = observation?.output_path || layer.source || metadata.source_path || "";
    const layerName = layer.name || layer.layer_id || metadata.name || "";
    if (layerName) outputs.push({ label: "", value: String(layerName), title: String(layerName) });
    if (outputPath) outputs.push({ label: ui.workflow?.outputFile || "输出文件", value: formatDisplayPath(outputPath, ui), title: outputPath });
  }
  for (const artifact of Array.isArray(step?.artifactRefs) ? step.artifactRefs : []) {
    const text = typeof artifact === "string" ? artifact : artifact?.artifact_id || artifact?.name || "";
    if (text) outputs.push({ label: ui.workflow?.artifact || "结果", value: String(text), title: String(text) });
  }
  return uniqueWorkflowItems(outputs);
}

function workflowObservationSummary(observationNodes, ui) {
  for (const node of observationNodes) {
    const text = String(node.displaySummary || node.text || "").trim();
    if (text) return formatStructuredWorkflowText(text, ui);
    const observation = normalizeObservationValue(node.observation);
    const message = String(observation?.message || "").trim();
    if (message) return formatStructuredWorkflowText(message, ui);
  }
  return "";
}

function uniqueWorkflowItems(items) {
  const seen = new Set();
  return items
    .map((item) => ({
      label: String(item.label || "").trim(),
      value: String(item.value || "").trim(),
      title: String(item.title || item.value || "").trim(),
    }))
    .filter((item) => {
      const key = `${item.label}:${item.value}`.toLowerCase();
      if (!item.value || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

const INPUT_SLOT_KEYS = new Set([
  "input_ref",
  "input_refs",
  "layer_ref",
  "source_ref",
  "source_layer",
  "source_path",
  "raster_ref",
  "mask_ref",
  "overlay_ref",
  "intersect_ref",
  "join_ref",
  "target_ref",
  "points_ref",
  "polygons_ref",
  "line_ref",
  "boundary_ref",
  "csv_ref",
  "table_ref",
]);

const OUTPUT_SLOT_KEYS = new Set([
  "output",
  "output_ref",
  "output_path",
  "output_layer",
  "output_layer_id",
  "result_ref",
  "result_layer",
  "destination",
]);

function OutputsView({ apiBaseUrl, artifactView, result, ui }) {
  const [reportView, setReportView] = useState(null);
  const outputs = artifactView?.outputs || result?.outputs || [];
  const reports = outputs.filter((output) => String(output?.role || output?.kind || "") === "report");
  const dataOutputs = outputs.filter((output) => String(output?.role || output?.kind || "") !== "report");
  const errors = result?.errors || [];
  const sessionId = String(result?.session_id || "").trim();

  async function viewReport(output) {
    const artifactId = String(output?.artifact_id || "").trim();
    if (!sessionId || !artifactId) return;
    setReportView({ loading: true, title: output.name || ui.outputs.reportFallback || "分析报告", content: "", path: output.path || "" });
    try {
      const report = await getSessionReport(apiBaseUrl, sessionId, artifactId);
      setReportView({
        loading: false,
        title: report.name || output.name || ui.outputs.reportFallback || "分析报告",
        content: report.content || "",
        path: report.path || output.path || "",
      });
    } catch (err) {
      setReportView({
        loading: false,
        title: output.name || ui.outputs.reportFallback || "分析报告",
        content: "",
        path: output.path || "",
        error: err.message || "Report fetch failed",
      });
    }
  }

  if (reportView) {
    return (
      <ReportMarkdownView
        report={reportView}
        ui={ui}
        onBack={() => setReportView(null)}
      />
    );
  }

  return (
    <div className="context-scroll">
      {reports.length ? (
        <div className="file-state-section-title">{ui.outputs.reportTitle || "分析报告"}</div>
      ) : null}
      {reports.map((output, i) => (
        <ReportCard
          output={output}
          ui={ui}
          canView={Boolean(sessionId && output.artifact_id)}
          onView={() => viewReport(output)}
          key={`report-${output.artifact_id || output.path || i}`}
        />
      ))}
      {reports.length && dataOutputs.length ? (
        <div className="file-state-section-title">{ui.outputs.dataTitle || "数据结果"}</div>
      ) : null}
      {dataOutputs.length ? dataOutputs.map((output, i) => (
        <OutputCard output={output} ui={ui} key={i} />
      )) : reports.length ? null : <Empty text={ui.empty.noOutputs} />}
      {errors.length ? <JsonCard title={ui.sections.errors} value={errors} /> : null}
    </div>
  );
}

function ReportMarkdownView({ report, ui, onBack }) {
  return (
    <div className="context-scroll report-viewer">
      <div className="report-viewer-head">
        <button className="context-back-btn" onClick={onBack} title="返回报告列表"><ChevronLeft size={16} /></button>
        <div>
          <span>{ui.outputs.reportTitle || "分析报告"}</span>
          <strong>{report.title || ui.outputs.reportFallback || "分析报告"}</strong>
        </div>
      </div>
      {report.path ? <p className="report-viewer-path" title={report.path}>{formatDisplayPath(report.path, ui)}</p> : null}
      {report.loading ? <Empty text={ui.common?.loading || "Loading..."} /> : null}
      {report.error ? <div className="empty error">{report.error}</div> : null}
      {!report.loading && !report.error ? (
        <div className="report-markdown-page">
          <MarkdownText value={report.content} fallback={ui.empty?.noOutputs || "No report content."} />
        </div>
      ) : null}
    </div>
  );
}

function DecisionAuditView({ result, ui }) {
  const decisions = projectDecisionRows(result, ui);
  return (
    <div className="context-scroll">
      {decisions.length ? decisions.map((item, index) => (
        <article className={`decision-card ${item.severity || "info"}`} key={`${item.kind}-${item.id || index}`}>
          <div className="decision-card-head">
            <strong>{item.title}</strong>
            <code>{item.status || item.kind}</code>
          </div>
          <p>{item.summary || "-"}</p>
          {item.details.length ? (
            <div className="decision-detail-list">
              {item.details.map((detail, i) => (
                <span title={detail.value} key={`${item.kind}-${i}`}>
                  <b>{detail.label}</b>
                  <em>{formatStructuredWorkflowText(detail.value, ui)}</em>
                </span>
              ))}
            </div>
          ) : null}
        </article>
      )) : <Empty text={ui.decisions?.empty || "No key decisions recorded yet."} />}
    </div>
  );
}

function MemoryViewInline({ ui, content, draft, editing, onEdit, onChange, onSave }) {
  if (editing) {
    return (
      <div className="context-scroll">
        <div className="memory-editor">
          <textarea value={draft} onChange={(e) => onChange(e.target.value)} placeholder={ui.memory.placeholder} />
          <div className="memory-editor-actions">
            <button onClick={() => { onChange(content); onEdit(false); }}>{ui.actions.cancel}</button>
            <button className="primary" onClick={onSave}><FolderOpen size={13} /> {ui.memory.saveMemory}</button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="context-scroll">
      {content ? <div className="memory-panel"><MarkdownText value={content} /></div> : <Empty text={ui.memory.placeholder} />}
      <div style={{ marginTop: 8 }}>
        <button onClick={() => { onChange(content || ""); onEdit(true); }}><BookOpen size={13} /> {ui.memory.edit}</button>
      </div>
    </div>
  );
}

function ParameterDetails({ parameters, parameterLabels, ui }) {
  const entries = parameterEntries(parameters, ui, parameterLabels);
  if (!entries.length) return null;
  return (
    <div className="repair-patch">
      {entries.map((entry) => (
        <span className="slot-chip" title={entry.title} key={entry.key}>
          <b>{entry.label}</b><span>{entry.value}</span>
        </span>
      ))}
      <CodeBlock label={ui.workflow.technicalDetails || "技术详情"} value={parameters} />
    </div>
  );
}

function CodeBlock({ label, value, raw = false }) {
  const text = raw ? String(value ?? "") : formatJson(value);
  const canCollapse = text.length > 260 || text.split("\n").length > 6;
  return (
    <details className="code-block" open={!canCollapse}>
      <summary>{label}</summary>
      <JsonSyntax text={text} raw={raw} />
    </details>
  );
}

function JsonSyntax({ text, raw }) {
  if (raw) return <pre className="syntax-json raw">{text}</pre>;
  const tokens = [];
  const pattern = /("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}\[\],:])/g;
  let lastIndex = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) tokens.push(text.slice(lastIndex, match.index));
    const token = match[0];
    const rest = text.slice(match.index + token.length).trimStart();
    let className = "json-punct";
    if (token.startsWith("\"")) className = rest.startsWith(":") ? "json-key" : "json-string";
    else if (/^-?\d/.test(token)) className = "json-number";
    else if (token === "true" || token === "false") className = "json-boolean";
    else if (token === "null") className = "json-null";
    tokens.push(<span className={className} key={`${match.index}-${token}`}>{token}</span>);
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) tokens.push(text.slice(lastIndex));
  return <pre className="syntax-json">{tokens}</pre>;
}

function normalizeObservationValue(value) {
  if (!value) return null;
  if (typeof value === "object") return value;
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text.startsWith("{")) return null;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function LayerCard({ layer, index, ui }) {
  const metadata = layer.metadata && typeof layer.metadata === "object" ? layer.metadata : {};
  const fields = Array.isArray(metadata.fields) ? metadata.fields : [];
  const title = layer.name || layer.layer_id || (ui.state?.layerFallback || "layer {index}").replace("{index}", String(index + 1));
  return (
    <article className="layer-card">
      <div className="layer-card-head">
        <strong>{title}</strong>
        <em>{layer.kind || "layer"}</em>
      </div>
      <div className="layer-meta">
        <span>{ui.layers.crs}: {metadata.crs || "-"}</span>
        <span>{ui.layers.geometry}: {metadata.geometry_type || "-"}</span>
        <span>{ui.layers.features}: {metadata.feature_count ?? metadata.row_count ?? "-"}</span>
      </div>
      {fields.length ? <p>{ui.layers.fields}: {fields.slice(0, 6).join(", ")}{fields.length > 6 ? "..." : ""}</p> : null}
      <p title={layer.source || metadata.source_path || ""}>{ui.layers.source}: {formatDisplayPath(layer.source || metadata.source_path || "", ui) || "-"}</p>
    </article>
  );
}

function OutputCard({ output, ui }) {
  return (
    <div className="output">
      <strong>{output.name || ui.outputs.outputFallback}</strong>
      <p title={output.path}>{formatDisplayPath(output.path, ui)}</p>
      <div>
        <button onClick={() => navigator.clipboard?.writeText(output.path)}><Copy size={13} /> {ui.actions.copy}</button>
        <button onClick={() => openPath(output.path).catch(() => {})}>{ui.actions.open}</button>
      </div>
    </div>
  );
}

function ReportCard({ output, ui, canView, onView }) {
  return (
    <div className="output report-output">
      <strong>{output.name || ui.outputs.reportFallback || "分析报告"}</strong>
      <p title={output.path}>{formatDisplayPath(output.path, ui)}</p>
      <div>
        <button disabled={!canView} onClick={onView}><BookOpen size={13} /> {ui.actions.view || "查看"}</button>
        <button onClick={() => navigator.clipboard?.writeText(output.path)}><Copy size={13} /> {ui.actions.copy}</button>
        <button onClick={() => openPath(output.path).catch(() => {})}>{ui.actions.open}</button>
      </div>
    </div>
  );
}

function JsonCard({ title, value }) {
  return (
    <article className="json-card">
      <h3>{title}</h3>
      <CodeBlock label={title} value={value} />
    </article>
  );
}

function Empty({ text }) {
  return <div className="empty">{text}</div>;
}
