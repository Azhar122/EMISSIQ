"use client";

import { useEffect, useRef, useState } from "react";
import { wsUrl } from "./api";

export interface TickMessage {
  type: "tick";
  ts: string;
  run_phase: string;
  weather: { wind_speed_ms: number; wind_dir_deg: number; temperature_c: number };
  sensors: { tag: string; ch4_ppm: number }[];
  equipment_state: string | null;
  pressure_barg: number | null;
  flow_kg_h?: number | null;
}

export interface StageMessage {
  type: "stage";
  key: string;
  label: string;
  detail: string;
  event_id?: string;
  provider?: string;
}

export type LiveMessage = TickMessage | StageMessage;

/** One shared WebSocket connection for the whole app. Reconnects on drop with
 * a short backoff — a demo cannot afford a dead socket mid-run. */
export function useLiveSocket() {
  const [lastTick, setLastTick] = useState<TickMessage | null>(null);
  const [lastStage, setLastStage] = useState<StageMessage | null>(null);
  const [connected, setConnected] = useState(false);
  const retryRef = useRef(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closedByEffect = false;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      ws = new WebSocket(wsUrl("/ws/live"));
      ws.onopen = () => {
        setConnected(true);
        retryRef.current = 0;
      };
      ws.onmessage = (evt) => {
        try {
          const msg: LiveMessage = JSON.parse(evt.data);
          if (msg.type === "tick") setLastTick(msg);
          else if (msg.type === "stage") setLastStage(msg);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (closedByEffect) return;
        const delay = Math.min(5000, 500 * 2 ** retryRef.current);
        retryRef.current += 1;
        retryTimer = setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
    }

    connect();
    return () => {
      closedByEffect = true;
      clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  return { lastTick, lastStage, connected };
}
