import { createContext, useContext } from "react";
import type { Health } from "./api/client";

export type Appearance = {
  workspaceName: string;
  theme: "light" | "dark" | "system";
  accent: "forest" | "blue" | "plum";
  density: "comfortable" | "compact";
};

export const defaultAppearance: Appearance = {
  workspaceName: "Church Office",
  theme: "light",
  accent: "forest",
  density: "comfortable",
};

export function readAppearance(): Appearance {
  try {
    const saved = JSON.parse(localStorage.getItem("loa-appearance") ?? "{}");
    return {
      workspaceName: typeof saved.workspaceName === "string" && saved.workspaceName.trim()
        ? saved.workspaceName.slice(0, 48) : defaultAppearance.workspaceName,
      theme: ["light", "dark", "system"].includes(saved.theme) ? saved.theme : defaultAppearance.theme,
      accent: ["forest", "blue", "plum"].includes(saved.accent) ? saved.accent : defaultAppearance.accent,
      density: saved.density === "compact" ? "compact" : "comfortable",
    };
  } catch {
    return defaultAppearance;
  }
}

export const Workspace = createContext<{
  appearance: Appearance;
  setAppearance: (value: Appearance) => void;
  health: Health | null;
  models: string[];
  modelError: string;
  refresh: () => Promise<void>;
} | null>(null);

export function useWorkspace() {
  const workspace = useContext(Workspace);
  if (!workspace) throw new Error("Workspace provider is missing.");
  return workspace;
}

export function transcriptDate(date: string) {
  const timestamp = new Date(date.includes("T") ? date : date.replace(" ", "T") + "Z");
  return Number.isNaN(timestamp.getTime()) ? date : timestamp.toLocaleString(undefined, {
    dateStyle: "medium", timeStyle: "short",
  });
}
