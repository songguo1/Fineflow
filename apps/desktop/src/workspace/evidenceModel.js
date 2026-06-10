export function buildEvidenceModel({ result, toolStateView, artifactView, visibleRunSnapshot, events }) {
  const snapshot = objectFrom(visibleRunSnapshot);
  const normalizedResult = objectFrom(result);
  const eventList = listFrom(events);
  const priorSteps = listFrom(snapshot.prior_steps);
  const stateTree = firstObject(toolStateView?.stateTree, snapshot.tool_state?.state_tree, normalizedResult.state_tree);
  const outputs = firstList(artifactView?.outputs, snapshot.tool_state?.outputs, normalizedResult.outputs);
  const layers = listFrom(stateTree.layers).map(projectLayerEvidence);
  const artifacts = outputs.map(projectArtifactEvidence);
  const latestActionPlan = latestActionPlanEvidence(priorSteps, eventList, normalizedResult);
  const observations = observationEvidence(priorSteps, eventList);
  const latestObservation = observations[observations.length - 1] || null;
  const skillEvidence = skillEvidenceFrom(priorSteps, eventList, normalizedResult);
  const validation = validationEvidenceFrom(normalizedResult, snapshot, eventList, observations);
  const writeback = writebackEvidenceFrom({ latestObservation, layers, artifacts, eventList });

  return {
    hasEvidence: Boolean(
      latestActionPlan || layers.length || artifacts.length || skillEvidence.items.length || validation.items.length || latestObservation
    ),
    snapshotSource: snapshot.run_id ? "run_snapshot" : "session_result",
    actionPlan: latestActionPlan,
    workspace: {
      layers,
      artifacts,
      aliases: objectFrom(stateTree.aliases),
    },
    skills: skillEvidence,
    validation,
    observation: latestObservation,
    observations,
    writeback,
    raw: {
      action_plan: latestActionPlan?.raw || null,
      latest_observation: latestObservation?.raw || null,
      validation: validation.raw,
      workspace_layers: listFrom(stateTree.layers),
      artifacts: outputs,
    },
  };
}

function latestActionPlanEvidence(priorSteps, events, result) {
  const step = latestActionStep(priorSteps);
  if (step) {
    return {
      source: "prior_steps",
      stepIndex: numberOrNull(step.index),
      thought: stringFrom(step.thought),
      action: stringFrom(step.action),
      actionInput: objectFrom(step.action_input),
      raw: step,
    };
  }
  const event = latestEventWithAction(events);
  if (event) {
    return {
      source: "run_events",
      stepIndex: numberOrNull(event.step_index ?? event.index),
      thought: stringFrom(event.thought),
      action: stringFrom(event.action || event.tool),
      actionInput: objectFrom(event.action_input || event.parameters),
      raw: event,
    };
  }
  const timelineStep = latestWorkflowTimelineStep(result);
  if (timelineStep) {
    return {
      source: "transcript.timeline",
      stepIndex: numberOrNull(timelineStep.index),
      thought: "",
      action: stringFrom(timelineStep.tool || timelineStep.action),
      actionInput: objectFrom(timelineStep.parameters),
      raw: timelineStep,
    };
  }
  return null;
}

function latestActionStep(priorSteps) {
  const candidates = priorSteps.filter((step) => step && typeof step === "object" && stringFrom(step.action));
  if (!candidates.length) return null;
  const nonFinal = candidates.filter((step) => stringFrom(step.action) !== "final_answer");
  return (nonFinal.length ? nonFinal : candidates)[(nonFinal.length ? nonFinal : candidates).length - 1];
}

function latestEventWithAction(events) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = objectFrom(events[i]);
    const action = stringFrom(event.action || event.tool);
    if (action) return event;
  }
  return null;
}

function latestWorkflowTimelineStep(result) {
  const timeline = listFrom(result?.transcript?.timeline);
  for (let i = timeline.length - 1; i >= 0; i -= 1) {
    const item = objectFrom(timeline[i]);
    if (stringFrom(item.type) === "workflow_step" && stringFrom(item.tool || item.action)) return item;
  }
  return null;
}

function observationEvidence(priorSteps, events) {
  const items = [];
  for (const step of priorSteps) {
    const observation = objectFrom(step?.observation);
    if (!Object.keys(observation).length) continue;
    items.push(projectObservation({
      observation,
      source: "prior_steps",
      action: stringFrom(step.action),
      actionInput: objectFrom(step.action_input),
      stepIndex: numberOrNull(step.index),
      event: null,
    }));
  }
  for (const event of events) {
    const payload = objectFrom(event);
    const observation = objectFrom(payload.observation);
    if (!Object.keys(observation).length) continue;
    items.push(projectObservation({
      observation,
      source: "run_events",
      action: stringFrom(payload.action || payload.tool),
      actionInput: objectFrom(payload.action_input || payload.parameters),
      stepIndex: numberOrNull(payload.step_index ?? payload.index),
      event: payload,
    }));
  }
  return dedupeObservations(items);
}

function projectObservation({ observation, source, action, actionInput, stepIndex, event }) {
  const data = objectFrom(observation.data);
  const layer = objectFrom(data.layer);
  const metadata = objectFrom(layer.metadata);
  const outputArtifact = firstObject(data.output_artifact, data.artifact, event?.output_artifact);
  return {
    source,
    stepIndex,
    action,
    actionInput,
    status: stringFrom(observation.status),
    message: stringFrom(observation.message),
    outputLayerId: stringFrom(observation.output_layer_id || layer.layer_id),
    outputPath: stringFrom(observation.output_path || layer.source || outputArtifact.path),
    featureCount: valueOr(metadata.feature_count, outputArtifact.feature_count, data.feature_count),
    geometryType: stringFrom(metadata.geometry_type || outputArtifact.geometry_type),
    crs: stringFrom(metadata.crs || outputArtifact.crs),
    timing: objectFrom(data.timing || event?.timing),
    preflightWarnings: listFrom(data.preflight_warnings),
    postflightWarnings: listFrom(data.postflight_warnings),
    outputArtifact,
    raw: observation,
  };
}

function skillEvidenceFrom(priorSteps, events, result) {
  const items = [];
  for (const step of priorSteps) collectSkillFromStep(items, step, "prior_steps");
  for (const event of events) collectSkillFromStep(items, event, "run_events");
  for (const risk of listFrom(result.risks)) {
    const suggested = listFrom(risk?.diagnosis?.suggested_skills);
    for (const name of suggested) {
      items.push({
        kind: "risk_suggestion",
        name: stringFrom(name),
        source: "risk.diagnosis",
        summary: stringFrom(risk.message || risk.code),
        raw: risk,
      });
    }
  }
  return {
    items: dedupeBy(items, (item) => `${item.kind}:${item.name}:${item.source}`),
    note: "skill 是认知指导，不直接执行 GIS 工具，也不作为执行许可。",
  };
}

function collectSkillFromStep(items, sourceItem, source) {
  const item = objectFrom(sourceItem);
  const action = stringFrom(item.action || item.tool);
  if (action !== "load_skill" && action !== "suggest_skill") return;
  const observation = objectFrom(item.observation);
  const data = objectFrom(observation.data);
  if (action === "load_skill") {
    const input = objectFrom(item.action_input || item.parameters);
    items.push({
      kind: "loaded",
      name: stringFrom(data.skill_name || input.name),
      source,
      summary: stringFrom(observation.message),
      toolkits: listFrom(data.auto_activated_toolkits),
      raw: data,
    });
    return;
  }
  const suggestions = listFrom(data.suggested_skills);
  if (!suggestions.length) {
    for (const name of listFrom(data.skill_hints)) {
      items.push({ kind: "suggested", name: stringFrom(name), source, summary: stringFrom(observation.message), raw: data });
    }
    return;
  }
  for (const skill of suggestions) {
    const payload = objectFrom(skill);
    items.push({
      kind: "suggested",
      name: stringFrom(payload.name),
      source,
      summary: stringFrom(payload.description || observation.message),
      workspaceAttention: listFrom(payload.workspace_attention),
      riskAwareness: listFrom(payload.risk_awareness),
      raw: payload,
    });
  }
}

function validationEvidenceFrom(result, snapshot, events, observations) {
  const items = [];
  for (const issue of listFrom(result.issues)) {
    const payload = objectFrom(issue);
    items.push({
      kind: "issue",
      stage: stringFrom(payload.stage || "validation"),
      severity: stringFrom(payload.severity || "error"),
      code: stringFrom(payload.code || payload.message_key),
      message: stringFrom(payload.message || payload.message_key || payload.code),
      source: "result.issues",
      raw: payload,
    });
  }
  for (const risk of listFrom(result.risks || snapshot.tool_state?.risks)) {
    const payload = objectFrom(risk);
    items.push({
      kind: "risk",
      stage: stringFrom(payload.stage || payload.source || "risk"),
      severity: stringFrom(payload.severity || "warning"),
      code: stringFrom(payload.code || payload.risk_code),
      message: stringFrom(payload.message || payload.title || payload.code),
      source: "result.risks",
      raw: payload,
    });
  }
  const pending = firstObject(result.pending_task, snapshot.pending_task);
  if (Object.keys(pending).length) {
    items.push({
      kind: "pending_task",
      stage: stringFrom(pending.stage || pending.active_intent || "pending"),
      severity: "pending",
      code: stringFrom(pending.pending_id || pending.status || pending.active_intent),
      message: stringFrom(pending.ux_explanation || pending.last_question || pending.question),
      source: "pending_task",
      raw: pending,
    });
  }
  for (const observation of observations) {
    for (const warning of [...observation.preflightWarnings, ...observation.postflightWarnings]) {
      const payload = objectFrom(warning);
      const risk = objectFrom(payload.risk);
      items.push({
        kind: "warning",
        stage: stringFrom(payload.stage || risk.stage || "preflight"),
        severity: stringFrom(payload.severity || risk.severity || "warning"),
        code: stringFrom(payload.code || risk.code),
        message: stringFrom(payload.message || risk.message || payload.code),
        source: observation.source,
        raw: payload,
      });
    }
  }
  for (const event of events) {
    const payload = objectFrom(event);
    const eventName = stringFrom(payload.event || payload.event_type);
    if (eventName !== "warning" && eventName !== "empty_result") continue;
    const risk = objectFrom(payload.risk);
    items.push({
      kind: eventName,
      stage: stringFrom(payload.source || risk.stage || "runtime"),
      severity: stringFrom(payload.severity || risk.severity || "warning"),
      code: stringFrom(payload.code || risk.code),
      message: stringFrom(payload.message || payload.warning || risk.message),
      source: "run_events",
      raw: payload,
    });
  }
  const unique = dedupeBy(items, (item) => `${item.kind}:${item.stage}:${item.code}:${item.message}`);
  return {
    items: unique,
    semanticItems: unique.filter((item) => item.stage === "semantic" || String(item.code).startsWith("semantic.")),
    preflightItems: unique.filter((item) => item.stage === "preflight" || String(item.code).startsWith("preflight.")),
    raw: unique.map((item) => item.raw),
  };
}

function writebackEvidenceFrom({ latestObservation, layers, artifacts, eventList }) {
  if (!latestObservation) return null;
  const outputArtifact = objectFrom(latestObservation.outputArtifact);
  let artifact = null;
  if (outputArtifact.artifact_id) {
    artifact = artifacts.find((item) => item.artifactId === outputArtifact.artifact_id) || null;
  }
  if (!artifact && latestObservation.outputLayerId) {
    artifact = artifacts.find((item) => item.layerId === latestObservation.outputLayerId) || null;
  }
  if (!artifact && latestObservation.outputPath) {
    artifact = artifacts.find((item) => item.path === latestObservation.outputPath) || null;
  }
  const layer = latestObservation.outputLayerId
    ? layers.find((item) => item.layerId === latestObservation.outputLayerId) || null
    : null;
  const artifactEvent = latestArtifactEvent(eventList, outputArtifact, latestObservation);
  return {
    outputLayerId: latestObservation.outputLayerId,
    outputPath: latestObservation.outputPath,
    artifact,
    layer,
    artifactEvent,
    writtenToWorkspace: Boolean(layer || artifact || artifactEvent),
    raw: {
      output_artifact: outputArtifact,
      artifact_event: artifactEvent,
      layer,
      artifact,
    },
  };
}

function latestArtifactEvent(events, outputArtifact, observation) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = objectFrom(events[i]);
    const eventName = stringFrom(event.event || event.event_type);
    if (eventName !== "artifact" && eventName !== "artifact.created") continue;
    const artifact = objectFrom(event.artifact || event.output_artifact);
    if (!Object.keys(artifact).length) continue;
    if (outputArtifact.artifact_id && artifact.artifact_id === outputArtifact.artifact_id) return artifact;
    if (observation.outputLayerId && artifact.layer_id === observation.outputLayerId) return artifact;
    if (observation.outputPath && artifact.path === observation.outputPath) return artifact;
  }
  return null;
}

function projectLayerEvidence(layer) {
  const payload = objectFrom(layer);
  const metadata = objectFrom(payload.metadata);
  const artifact = objectFrom(metadata.artifact);
  return {
    layerId: stringFrom(payload.layer_id),
    name: stringFrom(payload.name || payload.layer_id),
    kind: stringFrom(payload.kind),
    source: stringFrom(payload.source || metadata.source_path),
    parentIds: listFrom(payload.parent_ids).map(stringFrom).filter(Boolean),
    algorithmId: stringFrom(payload.algorithm_id || artifact.algorithm_id),
    role: stringFrom(artifact.role || metadata.artifact_role),
    sourceAction: stringFrom(artifact.source_action || payload.algorithm_id),
    crs: stringFrom(metadata.crs),
    geometryType: stringFrom(metadata.geometry_type),
    featureCount: valueOr(metadata.feature_count, metadata.row_count),
    fields: listFrom(metadata.fields),
    extent: valueOr(metadata.extent, metadata.bounds),
    parameters: objectFrom(payload.parameters),
    raw: payload,
  };
}

function projectArtifactEvidence(output) {
  const payload = objectFrom(output);
  return {
    artifactId: stringFrom(payload.artifact_id),
    role: stringFrom(payload.role),
    kind: stringFrom(payload.kind),
    name: stringFrom(payload.name || payload.artifact_id || payload.layer_id),
    path: stringFrom(payload.path || payload.source),
    layerId: stringFrom(payload.layer_id),
    algorithmId: stringFrom(payload.algorithm_id),
    crs: stringFrom(payload.crs),
    geometryType: stringFrom(payload.geometry_type),
    featureCount: valueOr(payload.feature_count),
    sourceAction: stringFrom(payload.source_action),
    sourceStep: numberOrNull(payload.source_step),
    parentIds: listFrom(payload.parent_ids).map(stringFrom).filter(Boolean),
    inputLayerIds: listFrom(payload.input_layer_ids).map(stringFrom).filter(Boolean),
    inputArtifactIds: listFrom(payload.input_artifact_ids).map(stringFrom).filter(Boolean),
    raw: payload,
  };
}

function dedupeObservations(items) {
  return dedupeBy(items, (item) => [
    item.source,
    item.stepIndex ?? "",
    item.action,
    item.status,
    item.outputLayerId,
    item.outputPath,
    item.message,
  ].join(":"));
}

function dedupeBy(items, keyFor) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const key = keyFor(item);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}

function firstObject(...values) {
  for (const value of values) {
    const payload = objectFrom(value);
    if (Object.keys(payload).length) return payload;
  }
  return {};
}

function firstList(...values) {
  for (const value of values) {
    const items = listFrom(value);
    if (items.length) return items;
  }
  return [];
}

function objectFrom(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function listFrom(value) {
  return Array.isArray(value) ? value : [];
}

function stringFrom(value) {
  return String(value ?? "").trim();
}

function valueOr(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return "";
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
