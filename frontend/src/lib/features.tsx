import { createContext, useContext, type ReactNode } from "react";
import type { Features } from "../api/types";

const Ctx = createContext<Features | null>(null);

export function FeaturesProvider({ value, children }: { value: Features; children: ReactNode }) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useFeatures() {
  const f = useContext(Ctx);
  const has = (name: string) => !!f?.modules.some((m) => m.name === name);
  return { features: f, has };
}
