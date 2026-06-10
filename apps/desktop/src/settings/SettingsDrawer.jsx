import { useEffect, useRef, useState } from "react";

import { Check, ChevronDown, FolderOpen, KeyRound, Settings } from "lucide-react";

import { PROVIDER_OPTIONS, normalizeProviderValue, providerOptionFor } from "../providers/providerCatalog.js";
import { isLikelyTauri, pickDirectory } from "../shared/tauriBridge.js";

export function SettingsDrawer({ ui, open, settings, apiKey, onChange, onApiKeyChange, onClose, onError }) {
  const [providerMenuOpen, setProviderMenuOpen] = useState(false);
  const providerMenuRef = useRef(null);
  const activeProvider = providerOptionFor(settings.provider);

  useEffect(() => {
    if (!providerMenuOpen) return undefined;
    function handlePointerDown(event) {
      if (!providerMenuRef.current?.contains(event.target)) setProviderMenuOpen(false);
    }
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [providerMenuOpen]);

  useEffect(() => {
    if (!open) setProviderMenuOpen(false);
  }, [open]);

  async function chooseOutputDirectory() {
    onError?.("");
    if (!isLikelyTauri()) { onError?.(ui.errors.filePickerDesktopOnly); return; }
    try {
      const directory = await pickDirectory();
      if (directory) onChange("outputDirectory", directory);
    } catch (err) { onError?.(err.message || ui.errors.directoryPickerFailed); }
  }

  function selectProvider(value) {
    onChange("provider", normalizeProviderValue(value));
    setProviderMenuOpen(false);
  }

  return (
    <div className={`drawer ${open ? "open" : ""}`}>
      <div className="shade" onClick={onClose} />
      <section>
        <h2><Settings size={16} /> {ui.sections.settings}</h2>
        <label>{ui.settings.apiBaseUrl}<input value={settings.apiBaseUrl} onChange={(event) => onChange("apiBaseUrl", event.target.value)} /></label>
        <label>{ui.settings.provider}
          <div className="provider-select" ref={providerMenuRef}>
            <button
              type="button"
              className={`provider-select-trigger ${providerMenuOpen ? "open" : ""}`}
              onClick={() => setProviderMenuOpen((current) => !current)}
              aria-haspopup="listbox"
              aria-expanded={providerMenuOpen}
            >
              <span className="provider-select-value">
                <span className="provider-icon" aria-hidden="true">
                  <img src={activeProvider.iconSrc} alt="" />
                </span>
                <strong>{ui.settings.providers[activeProvider.labelKey] || activeProvider.value}</strong>
              </span>
              <ChevronDown size={16} aria-hidden="true" />
            </button>
            {providerMenuOpen ? (
              <div className="provider-select-menu" role="listbox" aria-label={ui.settings.provider}>
                {PROVIDER_OPTIONS.map(({ value, labelKey, iconSrc }) => {
                  const active = activeProvider.value === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      className={`provider-option ${active ? "active" : ""}`}
                      onClick={() => selectProvider(value)}
                      role="option"
                      aria-selected={active}
                      title={ui.settings.providers[labelKey] || value}
                    >
                      <span className="provider-select-value">
                        <span className="provider-icon" aria-hidden="true">
                          <img src={iconSrc} alt="" />
                        </span>
                        <strong>{ui.settings.providers[labelKey] || value}</strong>
                      </span>
                      {active ? <Check size={16} aria-hidden="true" /> : null}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
        </label>
        <label>{ui.settings.apiKey}<div className="key"><KeyRound size={13} /><input type="password" value={apiKey} onChange={(event) => onApiKeyChange(event.target.value)} /></div></label>
        <label>{ui.settings.llmBaseUrl}<input value={settings.baseUrl} onChange={(event) => onChange("baseUrl", event.target.value)} /></label>
        <label>{ui.settings.model}<input value={settings.model} onChange={(event) => onChange("model", event.target.value)} /></label>
        <div className="settings-grid">
          <label>{ui.settings.llmMaxTokens}<input type="number" min="1" max="8192" value={settings.llmMaxTokens} onChange={(event) => onChange("llmMaxTokens", event.target.value)} /></label>
          <label>{ui.settings.llmTopP}<input type="number" min="0.01" max="1" step="0.01" value={settings.llmTopP} onChange={(event) => onChange("llmTopP", event.target.value)} /></label>
        </div>
        <label className="check">{ui.settings.llmJsonMode}<input type="checkbox" checked={Boolean(settings.llmJsonMode)} onChange={(event) => onChange("llmJsonMode", event.target.checked)} /></label>
        <label>{ui.settings.qgisLauncher}<input value={settings.qgisLauncher} onChange={(event) => onChange("qgisLauncher", event.target.value)} /></label>
        <label>{ui.settings.qgisPrefixPath}<input value={settings.qgisPrefixPath} onChange={(event) => onChange("qgisPrefixPath", event.target.value)} /></label>
        <label>{ui.settings.language}
          <select value={settings.locale || "zh-CN"} onChange={(event) => onChange("locale", event.target.value)}>
            <option value="zh-CN">{ui.settings.languages.zh}</option>
            <option value="en-US">{ui.settings.languages.en}</option>
          </select>
        </label>
        <label>{ui.settings.outputDirectory}
          <div className="path-picker">
            <input value={settings.outputDirectory} onChange={(event) => onChange("outputDirectory", event.target.value)} />
            <button type="button" onClick={chooseOutputDirectory} title={ui.settings.chooseDirectory}><FolderOpen size={14} /> {ui.actions.choose}</button>
          </div>
        </label>
        <label>{ui.settings.outputFormat}
          <select value={settings.outputFormat} onChange={(event) => onChange("outputFormat", event.target.value)}>
            <option value="geojson">geojson</option>
            <option value="gpkg">gpkg</option>
            <option value="shp">shp</option>
          </select>
        </label>
        <button className="primary" onClick={onClose}>{ui.actions.save}</button>
      </section>
    </div>
  );
}
