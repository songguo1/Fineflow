import { CheckCircle2, ClipboardList, FileDown, GitBranch, ListTree, RotateCcw } from "lucide-react";

const COMMAND_SPECS = [
  { command: "/fields", labelKey: "fields", descKey: "fieldsDesc", Icon: ClipboardList },
  { command: "/layers", labelKey: "layers", descKey: "layersDesc", Icon: ListTree },
  { command: "/crs", labelKey: "crs", descKey: "crsDesc", Icon: GitBranch },
  { command: "/outputs", labelKey: "outputs", descKey: "outputsDesc", Icon: FileDown },
  { command: "/last", labelKey: "last", descKey: "lastDesc", Icon: CheckCircle2 },
  { command: "/reset", labelKey: "reset", descKey: "resetDesc", Icon: RotateCcw, danger: true },
];

export function buildCommandItems(ui) {
  return COMMAND_SPECS.map((item) => ({
    ...item,
    label: ui.composer[item.labelKey] || item.command,
    description: ui.composer[item.descKey] || item.command,
  }));
}
