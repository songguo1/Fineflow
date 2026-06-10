import { CheckCircle2, ClipboardList, Play, XCircle } from "lucide-react";

export function PlanDraftCard({ plan, busy, onApprove, onReject, onRun }) {
  if (!plan) return null;
  const assumptions = Array.isArray(plan.assumptions) ? plan.assumptions : [];
  const risks = Array.isArray(plan.risk_preview) ? plan.risk_preview : [];
  const outputs = Array.isArray(plan.expected_outputs) ? plan.expected_outputs : [];
  const approved = plan.status === "approved";
  const rejected = plan.status === "rejected";
  return (
    <section className={`plan-draft ${plan.status || "draft"}`}>
      <div className="plan-draft-head">
        <ClipboardList size={17} />
        <div>
          <span>Plan Mode</span>
          <h2>{plan.user_request || "GIS task plan"}</h2>
        </div>
        <code>{plan.status || "draft"}</code>
      </div>
      <PlanList title="Assumptions" items={assumptions} />
      <PlanList title="Risk preview" items={risks.map((item) => item.message || item.code || "risk")} />
      <PlanList title="Expected outputs" items={outputs.length ? outputs : ["runtime-determined GIS output"]} />
      <div className="plan-draft-actions">
        {!approved && !rejected ? (
          <button onClick={onApprove} disabled={busy}><CheckCircle2 size={14} /> 批准</button>
        ) : null}
        {!rejected ? (
          <button className="primary" onClick={onRun} disabled={busy}><Play size={14} /> 执行</button>
        ) : null}
        {!approved && !rejected ? (
          <button onClick={onReject} disabled={busy}><XCircle size={14} /> 拒绝</button>
        ) : null}
      </div>
    </section>
  );
}

function PlanList({ title, items }) {
  const visible = items.filter((item) => String(item || "").trim());
  if (!visible.length) return null;
  return (
    <div className="plan-draft-section">
      <span>{title}</span>
      <ul>
        {visible.map((item, index) => <li key={`${title}-${index}`}>{String(item)}</li>)}
      </ul>
    </div>
  );
}
