import { useEffect, useMemo, useState } from "react";

export function useResumeInteraction({ pendingTask, missingSlots, status, isAwaitingUser, allowedActions }) {
  const [resumePatch, setResumePatch] = useState({});
  const [resumeMode, setResumeMode] = useState("patch");
  const patchSchema = pendingTask?.slot_patch_schema && typeof pendingTask.slot_patch_schema === "object" ? pendingTask.slot_patch_schema : {};
  const patchSchemaKey = JSON.stringify(patchSchema);
  const pendingKey = pendingTask?.pending_id || patchSchemaKey;
  const resumeFields = useMemo(
    () =>
      Object.entries(patchSchema)
        .filter(([slot, schema]) => String(slot || "").trim() && schema && typeof schema === "object")
        .map(([slot, schema]) => ({
          slot,
          schema,
          required: schema.required !== false,
          sourceRequired: Boolean(schema.source_required),
        })),
    [patchSchemaKey]
  );

  useEffect(() => {
    const nextPatch = {};
    for (const field of resumeFields) {
      const slot = field.slot;
      const current = pendingTask?.filled_slots?.[slot];
      nextPatch[slot] = current == null ? "" : Array.isArray(current) ? current.join(", ") : String(current);
    }
    setResumePatch(nextPatch);
  }, [pendingKey, resumeFields]);

  useEffect(() => {
    if (isAwaitingUser && missingSlots.length && allowedActions.includes("patch")) {
      setResumeMode("patch");
      return;
    }
    if (isAwaitingUser && allowedActions.includes("replan")) {
      setResumeMode("replan");
    }
  }, [isAwaitingUser, missingSlots.length, allowedActions]);

  function updateResumePatch(slot, value) {
    setResumePatch((current) => ({ ...current, [slot]: value }));
  }

  return {
    resumePatch,
    resumeMode,
    setResumeMode,
    updateResumePatch,
    resumeFields,
  };
}
