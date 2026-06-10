import { ArrowRightCircle, Database, FileDown, FolderOpen, Plus, Trash2 } from "lucide-react";

import { aliasFromPath, isLikelyTauri, pickGisFiles, sourceTypeFromPath } from "../shared/tauriBridge.js";

export function DataSourcesPanel({ ui, sources, recentOutputs, pendingTask, onSourcesChange, onResolveSourceRequest, onError }) {
  const sourceRequests = Array.isArray(pendingTask?.source_requests) ? pendingTask.source_requests : [];

  async function chooseFiles() {
    onError?.("");
    if (!isLikelyTauri()) {
      onError?.(ui.errors.filePickerDesktopOnly);
      return;
    }
    try {
      const paths = await pickGisFiles();
      if (!paths.length) return;
      onSourcesChange((current) => [...current, ...buildSourcesFromPaths(paths, current)]);
    } catch (err) {
      onError?.(err.message || ui.errors.filePickerFailed);
    }
  }

  function addRecentOutput(item, index) {
    onSourcesChange((current) => [
      ...current,
      {
        alias: item.name || `output_${index}`,
        path: item.path,
        type: item.kind === "raster" ? "raster" : "vector",
        crs: "",
      },
    ]);
  }

  async function fulfillSourceRequest(request) {
    onError?.("");
    if (!isLikelyTauri()) {
      onError?.(ui.errors.filePickerDesktopOnly);
      return;
    }
    try {
      const paths = await pickGisFiles();
      if (!paths.length) return;
      const selected = buildSourcesFromPaths(paths, sources);
      const mismatch = selected.find((item) => !matchesAcceptedType(item, request?.accepted_source_types));
      if (mismatch) {
        onError?.(
          (ui.errors.sourceTypeMismatch || "所选文件类型不符合当前待补数据要求。")
            .replace("{file}", mismatch.alias || mismatch.path || "")
            .replace("{types}", formatAcceptedTypes(request?.accepted_source_types, ui))
        );
        return;
      }
      if (!String(request?.slot || "").endsWith("_refs") && selected.length > 1) {
        onError?.(ui.errors.singleSourceRequired || "当前待补数据只需要一个文件。");
        return;
      }
      const nextSources = [...sources, ...selected];
      await onResolveSourceRequest?.(request, selected, nextSources);
    } catch (err) {
      onError?.(err.message || ui.errors.filePickerFailed);
    }
  }

  return (
    <div className="sidebar-content">
      <div className="source-actions">
        <button className="primary" onClick={chooseFiles}><FolderOpen size={15} /> {ui.actions.addFiles}</button>
        <button onClick={() => onSourcesChange([])}><Trash2 size={14} /> {ui.actions.clear}</button>
      </div>
      {sourceRequests.length ? (
        <section className="sidebar-section source-request-section">
          <div className="panel-title"><ArrowRightCircle size={14} /><strong>{ui.resume.sourceRequestsTitle || "待补数据"}</strong></div>
          <div className="sources source-request-list">
            {sourceRequests.map((request, index) => (
              <div className="source-request-card" key={`${request.slot || "source"}-${index}`}>
                <div className="source-request-head">
                  <strong>{request.slot_label || humanizeSlot(request.slot, ui)}</strong>
                  <em>{formatAcceptedTypes(request.accepted_source_types, ui)}</em>
                </div>
                <p>{request.question || request.reason || ui.resume.sourceRequiredHint}</p>
                <button className="primary" onClick={() => fulfillSourceRequest(request)}>
                  <FolderOpen size={14} /> {ui.resume.attachSourceAndContinue || "补充文件并继续"}
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <div className="sources source-section source-section-main">
        {sources.map((source, index) => (
          <SourceCard
            key={`${source.alias}-${source.path}-${index}`}
            icon={Database}
            title={source.alias}
            kind={source.type}
            path={source.path}
            actionIcon={Trash2}
            actionLabel={ui.actions.remove}
            onAction={() => onSourcesChange((items) => items.filter((_, i) => i !== index))}
          />
        ))}
        {!sources.length ? <Empty text={ui.empty.noFilesSelected} /> : null}
      </div>
      {recentOutputs.length > 0 ? (
        <section className="sidebar-section source-section-history" style={{ marginTop: 10 }}>
          <div className="panel-title"><FileDown size={14} /><strong>历史产物</strong></div>
          <div className="sources">
            {recentOutputs.map((item, index) => (
              <SourceCard
                key={`hist-${index}`}
                icon={FileDown}
                title={item.name || "output"}
                kind={item.kind}
                path={item.path}
                actionIcon={Plus}
                actionLabel="添加"
                onAction={() => addRecentOutput(item, index)}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function SourceCard({ icon: Icon, title, kind, path, actionIcon: ActionIcon, actionLabel, onAction }) {
  return (
    <div className="source-card">
      <div className="source-card-head">
        <span className="source-icon"><Icon size={15} /></span>
        <strong>{title}</strong>
        <em>{kind}</em>
      </div>
      <p className="source-path">{path}</p>
      <button className="source-remove" onClick={onAction}>
        <ActionIcon size={13} /> {actionLabel}
      </button>
    </div>
  );
}

function Empty({ text }) {
  return <div className="empty">{text}</div>;
}

function buildSourcesFromPaths(paths, current) {
  const next = Array.isArray(current) ? [...current] : [];
  const created = [];
  for (const path of paths) {
    const item = {
      alias: uniqueAlias(aliasFromPath(path), [...next, ...created]),
      path,
      type: sourceTypeFromPath(path),
      crs: "",
    };
    created.push(item);
  }
  return created;
}

function uniqueAlias(alias, existing) {
  const used = new Set(existing.map((item) => item.alias));
  if (!used.has(alias)) return alias;
  let index = 2;
  while (used.has(`${alias}_${index}`)) index += 1;
  return `${alias}_${index}`;
}

function matchesAcceptedType(source, acceptedTypes) {
  const expected = Array.isArray(acceptedTypes) ? acceptedTypes.map((item) => String(item || "").toLowerCase()).filter(Boolean) : [];
  if (!expected.length) return true;
  const sourceType = String(source?.type || "").toLowerCase();
  return expected.includes(sourceType);
}

function formatAcceptedTypes(acceptedTypes, ui) {
  const labels = {
    vector: ui.resume.sourceTypes?.vector || "矢量",
    raster: ui.resume.sourceTypes?.raster || "栅格",
    csv: ui.resume.sourceTypes?.csv || "CSV",
  };
  const values = Array.isArray(acceptedTypes) ? acceptedTypes.map((item) => labels[String(item || "").toLowerCase()] || item).filter(Boolean) : [];
  return values.join(" / ") || (ui.resume.sourceTypeFallback || "数据文件");
}

function humanizeSlot(slot, ui) {
  return ui.slots?.[slot] || slot;
}
