import { useState } from "react";
import { Activity, Brain, ClipboardCheck, Copy, Database, FileJson, ShieldCheck } from "lucide-react";

import { formatDisplayPath, formatJson, friendlyActionTitle } from "../workflow/workflowFormatters.js";

export function EvidencePanel({ evidence, ui }) {
  const [copied, setCopied] = useState(false);
  const labels = evidenceLabels(ui);

  async function copyEvidenceJson() {
    try {
      await navigator.clipboard?.writeText(formatJson(evidence?.raw || evidence || {}));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="context-scroll evidence-panel">
      <div className="evidence-head">
        <div>
          <span>{labels.kicker}</span>
          <strong>{labels.title}</strong>
          <p>{labels.subtitle}</p>
        </div>
        <button className="evidence-copy" onClick={copyEvidenceJson} title={labels.copyTitle}>
          <Copy size={13} /> {copied ? labels.copied : labels.copy}
        </button>
      </div>
      <ActionPlanSection actionPlan={evidence?.actionPlan} labels={labels} ui={ui} />
      <WorkspaceSection workspace={evidence?.workspace} labels={labels} />
      <SkillSection skills={evidence?.skills} labels={labels} />
      <ValidationSection validation={evidence?.validation} labels={labels} />
      <ObservationSection observation={evidence?.observation} writeback={evidence?.writeback} labels={labels} />
      <EvidenceSection icon={FileJson} title={labels.rawEvidence} note={labels.rawNote}>
        <JsonBlock label={labels.expandJson} value={evidence?.raw || {}} />
      </EvidenceSection>
    </div>
  );
}

function ActionPlanSection({ actionPlan, labels, ui }) {
  return (
    <EvidenceSection icon={ClipboardCheck} title={labels.actionPlan} note={labels.actionPlanNote}>
      {actionPlan ? (
        <div className="evidence-card">
          <div className="evidence-card-head">
            <strong>{friendlyActionTitle(actionPlan.action, ui)}</strong>
            <code>{actionPlan.source}{actionPlan.stepIndex != null ? ` #${actionPlan.stepIndex}` : ""}</code>
          </div>
          <EvidenceKV label="s / thought" value={actionPlan.thought || labels.notRecorded} />
          <EvidenceKV label="a / action" value={actionPlan.action || "-"} code />
          <JsonBlock label="p / action_input" value={actionPlan.actionInput || {}} />
        </div>
      ) : <EvidenceEmpty text={labels.noActionPlan} />}
    </EvidenceSection>
  );
}

function WorkspaceSection({ workspace, labels }) {
  const layers = Array.isArray(workspace?.layers) ? workspace.layers : [];
  const artifacts = Array.isArray(workspace?.artifacts) ? workspace.artifacts : [];
  return (
    <EvidenceSection icon={Database} title={labels.workspace} note={labels.workspaceNote}>
      <div className="evidence-stats">
        <span><b>{layers.length}</b>{labels.layers}</span>
        <span><b>{artifacts.length}</b>{labels.artifacts}</span>
      </div>
      {layers.length ? layers.slice(-8).map((layer, index) => (
        <div className="evidence-card compact" key={layer.layerId || `${layer.name}-${index}`}>
          <div className="evidence-card-head">
            <strong>{layer.name || layer.layerId || labels.layerFallback}</strong>
            <code>{layer.kind || "layer"}</code>
          </div>
          <div className="evidence-chip-row">
            <span>CRS {layer.crs || "-"}</span>
            <span>{labels.geometry} {layer.geometryType || "-"}</span>
            <span>{labels.features} {layer.featureCount ?? "-"}</span>
            {layer.role ? <span>{labels.role} {layer.role}</span> : null}
          </div>
          <EvidenceKV label="layer_id" value={layer.layerId || "-"} code />
          <EvidenceKV label={labels.lineage} value={lineageText(layer)} />
          <EvidenceKV label={labels.source} value={formatDisplayPath(layer.source || "", null) || "-"} title={layer.source || ""} />
        </div>
      )) : <EvidenceEmpty text={labels.noWorkspace} />}
      {artifacts.length ? (
        <details className="evidence-subdetails">
          <summary>{labels.artifactDetails}</summary>
          {artifacts.slice(-8).map((artifact, index) => (
            <div className="evidence-card compact" key={artifact.artifactId || artifact.path || index}>
              <div className="evidence-card-head">
                <strong>{artifact.name || artifact.artifactId || labels.artifactFallback}</strong>
                <code>{artifact.role || artifact.kind || "artifact"}</code>
              </div>
              <EvidenceKV label="artifact_id" value={artifact.artifactId || "-"} code />
              <EvidenceKV label="source_action" value={artifact.sourceAction || artifact.algorithmId || "-"} code />
              <EvidenceKV label={labels.outputPath} value={formatDisplayPath(artifact.path || "", null) || "-"} title={artifact.path || ""} />
            </div>
          ))}
        </details>
      ) : null}
    </EvidenceSection>
  );
}

function SkillSection({ skills, labels }) {
  const items = Array.isArray(skills?.items) ? skills.items : [];
  return (
    <EvidenceSection icon={Brain} title={labels.skills} note={skills?.note || labels.skillNote}>
      {items.length ? items.map((skill, index) => (
        <div className="evidence-card compact" key={`${skill.kind}-${skill.name}-${index}`}>
          <div className="evidence-card-head">
            <strong>{skill.name || labels.skillFallback}</strong>
            <code>{skill.kind || "skill"}</code>
          </div>
          <EvidenceKV label={labels.sourceField} value={skill.source || "-"} />
          <EvidenceKV label={labels.summary} value={skill.summary || "-"} />
          {skill.workspaceAttention?.length ? <EvidenceKV label="workspace_attention" value={skill.workspaceAttention.join(", ")} /> : null}
          {skill.riskAwareness?.length ? <EvidenceKV label="risk_awareness" value={skill.riskAwareness.join(", ")} /> : null}
        </div>
      )) : <EvidenceEmpty text={labels.noSkills} />}
    </EvidenceSection>
  );
}

function ValidationSection({ validation, labels }) {
  const items = Array.isArray(validation?.items) ? validation.items : [];
  return (
    <EvidenceSection icon={ShieldCheck} title={labels.validation} note={labels.validationNote}>
      {items.length ? items.slice(-10).map((item, index) => (
        <div className={`evidence-card compact validation ${item.severity || "warning"}`} key={`${item.kind}-${item.code}-${index}`}>
          <div className="evidence-card-head">
            <strong>{item.code || item.kind || labels.validationItem}</strong>
            <code>{item.stage || item.source || "validation"}</code>
          </div>
          <EvidenceKV label={labels.kind} value={item.kind || "-"} />
          <EvidenceKV label={labels.severity} value={item.severity || "-"} />
          <EvidenceKV label={labels.message} value={item.message || "-"} />
        </div>
      )) : <EvidenceEmpty text={labels.noValidationItems} />}
    </EvidenceSection>
  );
}

function ObservationSection({ observation, writeback, labels }) {
  return (
    <EvidenceSection icon={Activity} title={labels.observation} note={labels.observationNote}>
      {observation ? (
        <div className={`evidence-card ${observation.status || ""}`}>
          <div className="evidence-card-head">
            <strong>{observation.action || labels.observationFallback}</strong>
            <code>{observation.status || "-"}</code>
          </div>
          <EvidenceKV label="output_layer_id" value={observation.outputLayerId || "-"} code />
          <EvidenceKV label="output_path" value={formatDisplayPath(observation.outputPath || "", null) || "-"} title={observation.outputPath || ""} />
          <div className="evidence-chip-row">
            <span>{labels.features} {observation.featureCount ?? "-"}</span>
            <span>{labels.geometry} {observation.geometryType || "-"}</span>
            <span>CRS {observation.crs || "-"}</span>
          </div>
          <EvidenceKV label={labels.message} value={observation.message || "-"} />
          <EvidenceKV label={labels.writeback} value={writeback?.writtenToWorkspace ? labels.writebackYes : labels.writebackUnknown} />
          <JsonBlock label={labels.observationJson} value={observation.raw || {}} />
        </div>
      ) : <EvidenceEmpty text={labels.noObservation} />}
    </EvidenceSection>
  );
}

function EvidenceSection({ icon: Icon, title, note, children }) {
  return (
    <section className="evidence-section">
      <div className="evidence-section-head">
        <Icon size={15} />
        <div>
          <strong>{title}</strong>
          {note ? <p>{note}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function EvidenceKV({ label, value, title, code = false }) {
  if (value == null || value === "") return null;
  return (
    <div className="evidence-kv">
      <b>{label}</b>
      {code ? <code title={title || String(value)}>{String(value)}</code> : <span title={title || String(value)}>{String(value)}</span>}
    </div>
  );
}

function JsonBlock({ label, value }) {
  return (
    <details className="evidence-json">
      <summary>{label}</summary>
      <pre>{formatJson(value)}</pre>
    </details>
  );
}

function EvidenceEmpty({ text }) {
  return <div className="evidence-empty">{text}</div>;
}

function lineageText(layer) {
  const parts = [];
  if (layer.sourceAction) parts.push(`source_action=${layer.sourceAction}`);
  if (layer.parentIds?.length) parts.push(`parent_ids=${layer.parentIds.join(", ")}`);
  return parts.join("; ") || "-";
}

function evidenceLabels(ui) {
  return {
    kicker: ui?.evidence?.kicker || "Method View",
    title: ui?.evidence?.title || "论文方法展示面板",
    subtitle: ui?.evidence?.subtitle || "只读展示当前运行中的结构化行动计划、工作区状态、校验记录和执行观察。",
    copy: ui?.evidence?.copy || "复制机制数据",
    copied: ui?.evidence?.copied || "已复制",
    copyTitle: ui?.evidence?.copyTitle || "复制当前方法视图 JSON",
    actionPlan: ui?.evidence?.actionPlan || "ActionPlan 映射",
    actionPlanNote: ui?.evidence?.actionPlanNote || "论文抽象 A={s,a,p} 对应代码字段 thought/action/action_input。",
    noActionPlan: ui?.evidence?.noActionPlan || "当前快照未记录可展示的 ActionPlan。",
    notRecorded: ui?.evidence?.notRecorded || "未记录",
    workspace: ui?.evidence?.workspace || "工作区状态",
    workspaceNote: ui?.evidence?.workspaceNote || "来自 state_tree layers 与 artifact outputs。",
    layers: ui?.evidence?.layers || "图层",
    artifacts: ui?.evidence?.artifacts || "产物",
    layerFallback: ui?.evidence?.layerFallback || "图层",
    artifactFallback: ui?.evidence?.artifactFallback || "产物",
    geometry: ui?.layers?.geometry || "几何",
    features: ui?.layers?.features || "要素",
    role: ui?.evidence?.role || "角色",
    lineage: ui?.evidence?.lineage || "来源关系",
    source: ui?.layers?.source || "来源",
    outputPath: ui?.evidence?.outputPath || "输出路径",
    artifactDetails: ui?.evidence?.artifactDetails || "查看 artifact 写回详情",
    noWorkspace: ui?.evidence?.noWorkspace || "当前快照暂无工作区图层。",
    skills: ui?.evidence?.skills || "领域知识指导",
    skillNote: ui?.evidence?.skillNote || "skill 是认知指导，不直接执行 GIS 工具，也不作为执行许可。",
    skillFallback: ui?.evidence?.skillFallback || "skill",
    noSkills: ui?.evidence?.noSkills || "当前快照未记录显式 suggest_skill/load_skill；未持久化的自动提示不会在此伪造。",
    sourceField: ui?.evidence?.sourceField || "来源",
    summary: ui?.evidence?.summary || "摘要",
    validation: ui?.evidence?.validation || "规则校验",
    validationNote: ui?.evidence?.validationNote || "展示已记录的 issues、risks、pending_task 和 warnings；不伪造完整 pass 清单。",
    validationItem: ui?.evidence?.validationItem || "校验记录",
    kind: ui?.evidence?.kind || "类型",
    severity: ui?.evidence?.severity || "级别",
    message: ui?.evidence?.message || "消息",
    noValidationItems: ui?.evidence?.noValidationItems || "当前快照未记录阻断 issue/warning；系统未持久化完整 pass 清单。",
    observation: ui?.evidence?.observation || "执行观察与写回",
    observationNote: ui?.evidence?.observationNote || "来自最近 Observation、output_artifact、state_tree 或 artifact 事件。",
    observationFallback: ui?.evidence?.observationFallback || "最近执行观察",
    writeback: ui?.evidence?.writeback || "写回状态",
    writebackYes: ui?.evidence?.writebackYes || "已在工作区或 artifact 中找到对应结果",
    writebackUnknown: ui?.evidence?.writebackUnknown || "当前快照未确认写回记录",
    observationJson: ui?.evidence?.observationJson || "Observation JSON",
    noObservation: ui?.evidence?.noObservation || "当前快照暂无 Observation。",
    rawEvidence: ui?.evidence?.rawEvidence || "原始运行数据 JSON",
    rawNote: ui?.evidence?.rawNote || "用于截图之外的核验，默认折叠。",
    expandJson: ui?.evidence?.expandJson || "展开 JSON",
  };
}
