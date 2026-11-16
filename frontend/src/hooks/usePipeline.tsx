import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../services/api";
import type { PipelineStatus } from "../types/api";

interface PipelineCtx {
  status: PipelineStatus | null;
  refresh: () => void;
  /** Increments every time a pipeline run finishes -> pages reload their data. */
  dataVersion: number;
  backendOnline: boolean;
}

const Ctx = createContext<PipelineCtx>({ status: null, refresh: () => {}, dataVersion: 0, backendOnline: true });

export function PipelineProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [backendOnline, setOnline] = useState(true);
  const prevState = useRef<string | null>(null);

  const refresh = useCallback(() => {
    api
      .pipelineStatus()
      .then((s) => {
        setOnline(true);
        if (prevState.current === "running" && s.state !== "running") setDataVersion((v) => v + 1);
        prevState.current = s.state;
        setStatus(s);
      })
      .catch(() => setOnline(false));
  }, []);

  useEffect(() => {
    refresh();
    const running = status?.state === "running";
    const id = window.setInterval(refresh, running ? 3000 : 20000);
    return () => window.clearInterval(id);
  }, [refresh, status?.state]);

  return <Ctx.Provider value={{ status, refresh, dataVersion, backendOnline }}>{children}</Ctx.Provider>;
}

export const usePipeline = () => useContext(Ctx);
