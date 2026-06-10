import deepseekIcon from "../assets/deepseek.svg";
import glmIcon from "../assets/glm.svg";
import openaiIcon from "../assets/openai.svg";
import qwenIcon from "../assets/qwen.svg";

export const PROVIDER_OPTIONS = [
  { value: "deepseek", labelKey: "deepseek", iconSrc: deepseekIcon },
  { value: "openai", labelKey: "openai", iconSrc: openaiIcon },
  { value: "qwen", labelKey: "qwen", iconSrc: qwenIcon },
  { value: "glm", labelKey: "glm", iconSrc: glmIcon },
  { value: "openai-compatible", labelKey: "openaiCompatible", iconSrc: openaiIcon },
];

export function normalizeProviderValue(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "openrouter") return "openai";
  if (PROVIDER_OPTIONS.some((option) => option.value === normalized)) return normalized;
  return PROVIDER_OPTIONS[0].value;
}

export function providerOptionFor(value) {
  const normalized = normalizeProviderValue(value);
  return PROVIDER_OPTIONS.find((option) => option.value === normalized) || PROVIDER_OPTIONS[0];
}
