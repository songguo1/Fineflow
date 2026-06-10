import { Ban, CheckCircle2, RotateCcw, XCircle } from "lucide-react";

export function ResumePanel({ ui, status, pendingTask, issue, risk, repair, allowedActions, resumeMode, onModeChange, onConfirm, onReject, onCancel, onChoiceSelect }) {
  const filledSlots = pendingTask.filled_slots && typeof pendingTask.filled_slots === "object" ? pendingTask.filled_slots : {};
  const missingSlots = Array.isArray(pendingTask.missing_slots) ? pendingTask.missing_slots : [];
  const slotPatchSchema = pendingTask.slot_patch_schema && typeof pendingTask.slot_patch_schema === "object" ? pendingTask.slot_patch_schema : {};
  const editableMissingSlots = missingSlots.filter((slot) => !slotPatchSchema?.[slot]?.source_required);
  const activeRisk = usableRisk(risk) || usableRisk(pendingTask.risk);
  const choices = Array.isArray(pendingTask.choices) && pendingTask.choices.length
    ? pendingTask.choices
    : Array.isArray(activeRisk?.suggested_choices) ? activeRisk.suggested_choices : [];
  const hasStructuredChoiceContract = hasChoiceContract(choices, slotPatchSchema);
  const isConfirmation = status === "awaiting_confirmation";
  const canSelectChoice = status === "awaiting_user" && allowedActions.includes("patch") && typeof onChoiceSelect === "function";
  const filledSlotEntries = compactSlotEntries(filledSlots, isConfirmation ? 3 : 8);
  const title = isConfirmation ? ui.resume.confirmationTitle : pendingTask.active_intent || ui.resume.pendingTask;
  const summaryMessage = pendingTask.ux_explanation || activeRisk?.message || issue?.message || repair?.message || pendingTask.question || pendingTask.last_question || ui.resume.waiting;

  return (
    <section className={`resume-panel ${status}`}>
      <div className="resume-panel-head">
        <div>
          <span className="resume-kicker">{isConfirmation ? ui.resume.reviewNeeded : ui.resume.inputNeeded}</span>
          <h2>{title}</h2>
          {pendingTask.pending_id ? <code className="pending-id">{pendingTask.pending_id}</code> : null}
        </div>
        <StatusPill status={status} ui={ui} />
      </div>
      <div className="resume-message"><p>{summaryMessage}</p></div>
      <div className="resume-details">
        {isConfirmation ? null : (
          <>
            {filledSlotEntries.length ? (
              <MiniSection title={ui.resume.filledSlots} emptyText={ui.resume.noFilled}>
                {filledSlotEntries.map(([key, value]) => <SlotChip key={key} name={key} value={value} ui={ui} />)}
              </MiniSection>
            ) : null}
            {editableMissingSlots.length ? (
              <MiniSection title={ui.resume.missingSlots} emptyText={ui.resume.noMissing}>
                {editableMissingSlots.map((slot) => <span className="missing-chip" key={slot}>{humanizeSlot(slot, ui)}</span>)}
              </MiniSection>
            ) : null}
            {choices.length ? (
              <MiniSection title={ui.resume.suggestedChoices || "Suggested choices"} emptyText="">
                {choices.map((choice, index) => (
                  <ChoiceChip
                    key={`${choice.slot || ""}-${choice.value || choice.label || index}`}
                    choice={choice}
                    ui={ui}
                    selectable={canSelectChoice && canBuildChoicePatch(choice, missingSlots, slotPatchSchema, hasStructuredChoiceContract)}
                    onSelect={() => onChoiceSelect(buildChoicePatch(choice, missingSlots, slotPatchSchema, hasStructuredChoiceContract), summarizeChoice(choice, ui))}
                  />
                ))}
              </MiniSection>
            ) : null}
          </>
        )}
      </div>
      <div className="resume-action-row">
        {status === "awaiting_user" && allowedActions.includes("patch") && editableMissingSlots.length ? (
          <button className={resumeMode === "patch" ? "active" : ""} onClick={() => onModeChange("patch")}><CheckCircle2 size={14} /> {ui.resume.fillParameters}</button>
        ) : null}
        {status === "awaiting_user" && allowedActions.includes("replan") ? (
          <button className={resumeMode === "replan" ? "active" : ""} onClick={() => onModeChange("replan")}><RotateCcw size={14} /> {ui.resume.changeTask}</button>
        ) : null}
        {status === "awaiting_confirmation" && allowedActions.includes("confirm") ? (
          <button className="primary" onClick={onConfirm}><CheckCircle2 size={14} /> {ui.resume.confirmRepair}</button>
        ) : null}
        {status === "awaiting_confirmation" && allowedActions.includes("reject") ? (
          <button onClick={onReject}><XCircle size={14} /> {ui.resume.reject}</button>
        ) : null}
        {allowedActions.includes("cancel") ? (
          <button onClick={onCancel}><Ban size={14} /> {isConfirmation ? ui.resume.cancelTask : ui.actions.cancel}</button>
        ) : null}
      </div>
    </section>
  );
}

function usableRisk(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value.code || value.message || value.category ? value : null;
}

function compactSlotEntries(slots, limit) {
  return Object.entries(slots || {})
    .filter(([key, value]) => !isInternalSlot(key, value))
    .slice(0, limit);
}

function isInternalSlot(key, value) {
  const name = String(key || "").toLowerCase();
  const text = String(value ?? "");
  if (name === "output" && text === "TEMPORARY_OUTPUT") return true;
  if (name === "output_path" && !text) return true;
  return false;
}

function friendlyRiskCategory(category, ui) {
  if (!category) return ui.resume.riskFallback || "risk";
  return ui.resume.riskCategories?.[category] || category.replace(/_/g, " ");
}

function StatusPill({ status, ui }) {
  return <span className={`status-pill ${status}`}>{ui.statuses[status] || status}</span>;
}

function MiniSection({ title, emptyText, children }) {
  const items = Array.isArray(children) ? children.filter(Boolean) : children ? [children] : [];
  return <div className="mini-section"><strong>{title}</strong><div>{items.length ? items : <em>{emptyText}</em>}</div></div>;
}

function SlotChip({ name, value, ui }) {
  return <span className="slot-chip"><b>{humanizeSlot(name, ui)}</b><span>{formatSlotValue(value, ui)}</span></span>;
}

function ChoiceChip({ choice, ui, selectable = false, onSelect }) {
  const label = choice.label || choice.value || choice.field || choice.layer_id || "";
  const details = [
    choice.slot ? humanizeSlot(choice.slot, ui) : "",
    choice.kind,
    choice.type,
    choice.crs,
    choice.geometry_type,
    choice.feature_count != null ? `${ui.layers?.features || "features"}=${choice.feature_count}` : "",
  ].filter(Boolean).join(" / ");
  const content = (
    <>
      <b>{label}</b>
      <span>{details || choice.value || ui.common.auto}</span>
      {selectable ? <em>{ui.resume.selectChoice || "Use this"}</em> : null}
    </>
  );
  if (!selectable) return <span className="slot-chip choice-chip">{content}</span>;
  return <button className="slot-chip choice-chip selectable" type="button" onClick={onSelect}>{content}</button>;
}

function buildChoicePatch(choice, missingSlots, slotPatchSchema, hasStructuredChoiceContract) {
  const slot = choice.slot || (hasStructuredChoiceContract ? "" : inferLegacyChoiceSlot(choice, missingSlots));
  const value = hasChoiceValue(choice?.value)
    ? choice.value
    : hasStructuredChoiceContract ? "" : legacyChoiceValue(choice);
  const outputPathPatch = buildOutputPathPatch(slot, value, slotPatchSchema);
  if (Object.keys(outputPathPatch).length) return outputPathPatch;
  if (!slot || value === "") return {};
  return { [slot]: slot.endsWith("_refs") && !Array.isArray(value) ? [value] : value };
}

function canBuildChoicePatch(choice, missingSlots, slotPatchSchema, hasStructuredChoiceContract) {
  const patch = buildChoicePatch(choice, missingSlots, slotPatchSchema, hasStructuredChoiceContract);
  return Object.keys(patch).length > 0;
}

function buildOutputPathPatch(slot, value, slotPatchSchema) {
  if (slot !== "output_path") return {};
  const path = String(value || "").trim();
  const schema = slotPatchSchema && typeof slotPatchSchema === "object" ? slotPatchSchema : {};
  if (!path || schema.output_path || !schema.output_dir || !schema.output_format) return {};
  const splitAt = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  if (splitAt <= 0 || splitAt >= path.length - 1) return {};
  const directory = path.slice(0, splitAt);
  const filename = path.slice(splitAt + 1);
  const dotAt = filename.lastIndexOf(".");
  const extension = dotAt >= 0 ? filename.slice(dotAt).toLowerCase() : "";
  const outputName = dotAt > 0 ? filename.slice(0, dotAt) : filename;
  const patch = { output_dir: directory, output_format: extension };
  if (schema.output_name && outputName) patch.output_name = outputName;
  return patch;
}

function hasChoiceContract(choices, slotPatchSchema) {
  if (Object.keys(slotPatchSchema || {}).length > 0) return true;
  return (Array.isArray(choices) ? choices : []).some((choice) => choice?.slot && hasChoiceValue(choice?.value));
}

function inferLegacyChoiceSlot(choice, missingSlots) {
  const slots = Array.isArray(missingSlots) ? missingSlots : [];
  if (slots.length === 1) return slots[0];
  if (choice.field) return slots.find((slot) => slot.includes("field")) || slots[0] || "";
  if (choice.layer_id || choice.kind || choice.geometry_type) {
    return slots.find((slot) => slot.endsWith("_ref") || slot.endsWith("_refs") || slot === "layer_ref") || slots[0] || "";
  }
  return slots[0] || "";
}

function legacyChoiceValue(choice) {
  if (hasChoiceValue(choice?.field)) return choice.field;
  if (hasChoiceValue(choice?.layer_id)) return choice.layer_id;
  if (hasChoiceValue(choice?.label)) return choice.label;
  return "";
}

function hasChoiceValue(value) {
  if (value == null) return false;
  if (typeof value === "string") return value.trim() !== "";
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

function summarizeChoice(choice, ui) {
  const label = choice.label || choice.value || choice.field || choice.layer_id || "";
  return (ui.resume.selectChoiceMessage || "Use candidate: {choice}").replace("{choice}", label);
}

function formatSlotValue(value, ui) {
  if (Array.isArray(value)) return value.join(", ");
  if (value == null) return ui.common.auto;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function humanizeSlot(slot, ui) {
  return ui.slots?.[slot] || slot;
}
