import { useEffect, useMemo, useRef } from "react";
import { MarkdownText } from "../shared/MarkdownText.jsx";
import { isLikelyTauri, openPath } from "../shared/tauriBridge.js";
import { RiskDiagnosisCard, RiskMessage } from "../risk/RiskDiagnosisCard.jsx";
import { buildRunNarrative } from "./runNarrativeModel.js";
import { Database, FileText, FolderOpen, Loader2 } from "lucide-react";
import { formatDisplayPath } from "../workflow/workflowFormatters.js";

export function ChatTranscript({
  transcript,
  runState,
  ui,
}) {
  const narrative = buildRunNarrative({ transcript, runState, ui });
  const scrollRef = useRef(null);
  const stickToBottomRef = useRef(true);
  const wasRunningRef = useRef(false);
  const narrativeKey = useMemo(
    () => narrative.map((item, index) => item.key || `${item.type}-${index}`).join("|"),
    [narrative]
  );

  useEffect(() => {
    const isRunning = Boolean(runState?.isRunning);
    if (isRunning && !wasRunningRef.current) stickToBottomRef.current = true;
    wasRunningRef.current = isRunning;
  }, [runState?.isRunning]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || !stickToBottomRef.current) return;
    element.scrollTop = element.scrollHeight;
  }, [narrativeKey, runState?.isRunning]);

  function handleScroll(event) {
    const element = event.currentTarget;
    const distanceToBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    stickToBottomRef.current = distanceToBottom < 96;
  }

  return (
    <section className="messages" ref={scrollRef} onScroll={handleScroll}>
      <NarrativeTurns items={narrative} ui={ui} />
      {runState?.isRunning ? <ThinkingMessage ui={ui} /> : null}
    </section>
  );
}

function NarrativeTurns({ items, ui }) {
  return groupNarrativeTurns(items).map((group, index) => (
    <div className={`narrative-turn ${group.hasUser ? "with-user" : "system"}`} key={group.key || `turn-${index}`}>
      <NarrativeItems items={group.items} ui={ui} />
    </div>
  ));
}

function NarrativeItems({ items, ui }) {
  return items.map((item, index) => renderNarrativeItem(item, item.key || `${item.type}-${index}`, ui));
}

function renderNarrativeItem(item, key, ui) {
  if (item.type === "user_request") return <Bubble role="user" text={item.text} key={key} />;
  if (item.type === "assistant_answer") return <Bubble role="assistant" text={item.text} key={key} />;
  if (item.type === "progress_update") return <ProgressLine item={item} key={key} />;
  if (item.type === "artifact_summary") return <ArtifactBubble item={item} ui={ui} key={key} />;
  if (item.type === "run_start") return <RunStartCard item={item} ui={ui} key={key} />;
  if (item.type === "resume_transition") return <ResumeTransitionCard item={item} ui={ui} key={key} />;
  if (item.type === "completion_delivery") return <CompletionCard item={item} ui={ui} key={key} />;
  if (item.type === "notice") return <NoticeCard card={item.card} ui={ui} key={key} />;
  return null;
}

function groupNarrativeTurns(items) {
  const groups = [];
  let current = null;

  function startGroup(item) {
    current = {
      key: item?.key || `turn-${groups.length}`,
      hasUser: item?.type === "user_request",
      items: [],
    };
    groups.push(current);
  }

  for (const item of items) {
    if (!item) continue;
    if (!current || item.type === "user_request") startGroup(item);
    current.items.push(item);
  }
  return groups;
}

function Bubble({ role, text }) {
  return (
    <div className={`bubble ${role}`}>
      <MarkdownText value={text} />
    </div>
  );
}

function ProgressLine({ item }) {
  const text = progressText(item);
  if (!text) return null;
  const state = progressLineState(item);
  return (
    <div className={`progress-line ${state}`}>
      <span className={`progress-line-mark ${state}`} aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

function progressText(item) {
  const summary = item?.summary && typeof item.summary === "object" ? item.summary : {};
  if (summary.doing) return String(summary.doing).trim();
  if (summary.done) return String(summary.done).trim();
  const rows = Array.isArray(item?.rows) ? item.rows : [];
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const row = rows[index] || {};
    const progress = row.progressSummary && typeof row.progressSummary === "object" ? row.progressSummary : {};
    const text = progress.doing || progress.done || row.summary || row.title;
    if (text) return String(text).trim();
  }
  return String(item?.title || "").trim();
}

function progressLineState(item) {
  const summary = item?.summary && typeof item.summary === "object" ? item.summary : {};
  if (summary.doing) return "current";
  const rows = Array.isArray(item?.rows) ? item.rows : [];
  if (rows.some((row) => row?.state === "error")) return "error";
  if (rows.some((row) => row?.state === "current")) return "current";
  return "done";
}

function ArtifactBubble({ item, ui }) {
  const artifacts = Array.isArray(item.artifacts) ? item.artifacts.filter((artifact) => artifact && typeof artifact === "object") : [];
  const title = String(item.title || ui.outputs?.outputFallback || ui.workflow?.output || "输出").trim();
  const summary = String(item.text || "").trim();
  const sectionLabel = artifacts.some((artifact) => String(artifact.role || artifact.kind || "").toLowerCase() === "report")
    ? ui.outputs?.reportTitle || "分析报告"
    : ui.outputs?.dataTitle || "数据结果";
  return (
    <div className="bubble assistant artifact-bubble">
      <div className="artifact-bubble-head">
        <strong>{title}</strong>
        <span>{sectionLabel}</span>
      </div>
      {summary ? <MarkdownText value={summary} /> : null}
      {artifacts.length ? (
        <div className="artifact-bubble-list">
          {artifacts.map((artifact, index) => (
            <ArtifactRow artifact={artifact} ui={ui} key={artifact.artifact_id || artifact.path || index} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ArtifactRow({ artifact, ui }) {
  const path = String(artifact.path || artifact.source || "").trim();
  const label = String(artifact.name || artifact.artifact_id || ui.outputs?.outputFallback || "输出").trim();
  const meta = uniqueText([artifact.role, artifact.kind, artifact.display_summary]).join(" · ");
  const isReport = String(artifact.role || artifact.kind || "").toLowerCase() === "report";
  const Icon = isReport ? FileText : Database;
  const canOpen = isLikelyTauri();

  async function handleOpen() {
    if (!path) return;
    await openPath(path);
  }

  return (
    <article className="artifact-bubble-row">
      <span className={`artifact-bubble-row-icon ${isReport ? "report" : "data"}`} aria-hidden="true">
        <Icon size={14} />
      </span>
      <div className="artifact-bubble-row-main">
        <strong>{label}</strong>
        {meta ? <span>{meta}</span> : null}
      </div>
      {path ? <code title={path}>{formatDisplayPath(path, ui)}</code> : null}
      {path ? (
        <button
          type="button"
          disabled={!canOpen}
          onClick={() => handleOpen().catch(() => {})}
          title={canOpen ? ui.actions.open : (ui.errors?.filePickerDesktopOnly || "Desktop only")}
        >
          <FolderOpen size={13} /> {ui.actions.open}
        </button>
      ) : null}
    </article>
  );
}

function uniqueText(values) {
  const seen = new Set();
  return values
    .map((value) => String(value || "").trim())
    .filter((value) => {
      const key = value.toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function ThinkingMessage({ ui }) {
  return (
    <section className="agent-thinking" role="status" aria-live="polite">
      <span className="agent-thinking-mark">
        <Loader2 className="spin" size={14} />
      </span>
      <div className="agent-thinking-copy">
        <strong>{ui.workflow?.thinking || "正在思考"}</strong>
      </div>
    </section>
  );
}

function RunStartCard({ item, ui }) {
  return (
    <section className="narrative-card">
      <div className="narrative-card-head">
        <span>{ui.narrative?.runLabel || "任务"}</span>
        <strong>{item.title}</strong>
      </div>
      {item.checklist.length ? (
        <ol className="narrative-checklist">
          {item.checklist.map((text) => <li key={text}>{text}</li>)}
        </ol>
      ) : null}
    </section>
  );
}

function ResumeTransitionCard({ item, ui }) {
  return (
    <section className="narrative-card narrative-transition">
      <div className="narrative-card-head">
        <span>{ui.narrative?.resumeLabel || "恢复"}</span>
        <strong>{item.title || ui.narrative?.resumeTitle || "继续任务"}</strong>
      </div>
      {item.text ? <MarkdownText value={item.text} /> : null}
      {!item.text && item.continueWith ? (
        <p className="narrative-process">{formatContinueSentence(item.continueWith, ui)}</p>
      ) : null}
    </section>
  );
}

function formatContinueSentence(continueWith, ui) {
  return (ui.resume?.continueSentence || "处理后会继续{continueWith}。").replace("{continueWith}", continueWith);
}

function CompletionCard({ item, ui }) {
  return (
    <section className="narrative-card narrative-completion">
      <div className="narrative-card-head">
        <span>{ui.narrative?.deliveryLabel || "交付"}</span>
        <strong>{item.title}</strong>
      </div>
      {item.message ? <MarkdownText value={item.message} /> : null}
      {item.output ? <p className="narrative-output"><b>{ui.workflow?.outputFile || "输出文件"}</b><span>{item.outputPath || item.output}</span></p> : null}
      {item.metrics.length ? (
        <div className="narrative-metrics">
          {item.metrics.map(([label, value]) => <span key={label}><b>{label}</b>{value}</span>)}
        </div>
      ) : null}
      {item.process ? <p className="narrative-process"><b>{ui.narrative?.process || "过程"}</b>{item.process}</p> : null}
    </section>
  );
}

function NoticeCard({ card, ui }) {
  return (
    <div className="timeline-card">
      <strong>{card.title}</strong>
      <RiskMessage risk={card.risk} text={card.text} ui={ui} />
      <RiskDiagnosisCard risk={card.risk} ui={ui} />
    </div>
  );
}
