"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, DemoState } from "@/lib/api";
import { useLiveSocket, TickMessage, StageMessage } from "@/lib/useLiveSocket";
import { DEMO_STAGES } from "@/lib/demoStages";

interface DemoContextValue {
  running: boolean;
  currentStageKey: string | null;
  currentStageLabel: string | null;
  eventId: string | null;
  lastTick: TickMessage | null;
  lastStage: StageMessage | null;
  connected: boolean;
  runDemo: () => Promise<void>;
  resetDemo: () => Promise<void>;
  /** bumped every time a stage completes — pages subscribe to this to refetch */
  version: number;
}

const DemoContext = createContext<DemoContextValue | null>(null);

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const { lastTick, lastStage, connected } = useLiveSocket();
  const [running, setRunning] = useState(false);
  const [eventId, setEventId] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    api.get<DemoState>("/api/demo/state").then((s) => {
      setRunning(s.running);
      setEventId(s.event_id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!lastStage) return;
    if (lastStage.event_id) setEventId(lastStage.event_id);
    setVersion((v) => v + 1);
    if (lastStage.key === "recommended" || lastStage.key === "avoided" || lastStage.key === "error") {
      setRunning(false);
    }
  }, [lastStage]);

  const runDemo = useCallback(async () => {
    setRunning(true);
    setEventId(null);
    await api.post("/api/demo/reset");
    await api.post("/api/demo/run", { speed: 6 });
  }, []);

  const resetDemo = useCallback(async () => {
    await api.post("/api/demo/reset");
    setRunning(false);
    setEventId(null);
    setVersion((v) => v + 1);
  }, []);

  const stageMeta = lastStage ? DEMO_STAGES.find((s) => s.key === lastStage.key) : null;

  return (
    <DemoContext.Provider
      value={{
        running,
        currentStageKey: lastStage?.key ?? null,
        currentStageLabel: stageMeta?.label ?? lastStage?.label ?? null,
        eventId,
        lastTick,
        lastStage,
        connected,
        runDemo,
        resetDemo,
        version,
      }}
    >
      {children}
    </DemoContext.Provider>
  );
}

export function useDemo(): DemoContextValue {
  const ctx = useContext(DemoContext);
  if (!ctx) throw new Error("useDemo must be used within DemoProvider");
  return ctx;
}
