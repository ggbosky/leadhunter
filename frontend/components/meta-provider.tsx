"use client";
import { createContext, useContext } from "react";
import { useApi } from "@/lib/api";
import type { Meta } from "@/lib/types";

const MetaContext = createContext<Meta | null>(null);

export function MetaProvider({ children }: { children: React.ReactNode }) {
  const { data } = useApi<Meta>("/meta", { revalidateIfStale: false });
  return <MetaContext.Provider value={data ?? null}>{children}</MetaContext.Provider>;
}

export function useMeta() {
  return useContext(MetaContext);
}
