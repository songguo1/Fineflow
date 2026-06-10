import { AlertTriangle, Lightbulb } from "lucide-react";

import { MarkdownText } from "../shared/MarkdownText.jsx";
import { diagnosisDisplayModel, formatStructuredWorkflowText } from "../workflow/workflowFormatters.js";

export function RiskDiagnosisCard({ risk, ui, compact = false }) {
  const diagnosis = risk?.diagnosis && typeof risk.diagnosis === "object" ? risk.diagnosis : {};
  const { causes, actions: nextActions } = diagnosisDisplayModel(diagnosis, ui);
  if (!causes.length && !nextActions.length) return null;

  return (
    <div className={`risk-diagnosis-card ${compact ? "compact" : ""}`}>
      {causes.length ? (
        <section>
          <strong><AlertTriangle size={13} /> {ui.diagnosis?.possibleCauses || "Possible causes"}</strong>
          <ul>
            {causes.map((cause, index) => <li key={`${cause}-${index}`}>{cause}</li>)}
          </ul>
        </section>
      ) : null}
      {nextActions.length ? (
        <section>
          <strong><Lightbulb size={13} /> {ui.diagnosis?.nextActions || "Suggested next steps"}</strong>
          <div className="diagnosis-actions">
            {nextActions.map((action) => <span key={action.key || action.label}>{action.label}</span>)}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export function RiskMessage({ risk, text, ui }) {
  return <MarkdownText value={formatStructuredWorkflowText(risk?.message || text || "-", ui)} />;
}
