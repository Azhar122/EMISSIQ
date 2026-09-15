"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";

interface Turn {
  question: string;
  answer: string;
  provider: string;
}

const SUGGESTED = [
  "Why is Compressor C-03 the probable source?",
  "What happened immediately before the methane event?",
  "Has this equipment produced similar events before?",
  "What should the technician inspect first?",
  "How was methane quantity estimated?",
  "What is the projected financial impact?",
];

export function Copilot({ eventId }: { eventId: string }) {
  const t = useTranslations();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);

  async function ask(question: string) {
    if (!question.trim() || asking) return;
    setAsking(true);
    setInput("");
    try {
      const res = await api.post<{ answer: string; provider: string }>(`/api/events/${eventId}/copilot`, { question });
      setTurns((t) => [...t, { question, answer: res.answer, provider: res.provider }]);
    } catch {
      setTurns((t) => [...t, { question, answer: "Could not reach the copilot service.", provider: "error" }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="panel">
      <div className="panel-title mb-3">{t("workspace.copilot")}</div>

      {turns.length === 0 && (
        <div className="flex flex-col gap-1.5 mb-3">
          {SUGGESTED.map((q) => (
            <button
              key={q}
              onClick={() => ask(q)}
              className="text-left rounded-lg px-3 py-2"
              style={{ background: "var(--cream)", fontSize: 12.5, color: "var(--text-dark)" }}
            >
              {q}
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3 mb-3" style={{ maxHeight: 320, overflowY: "auto" }}>
        {turns.map((turn, i) => (
          <div key={i}>
            <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--green)", marginBottom: 3 }}>{turn.question}</div>
            <div style={{ fontSize: 12.5, color: "var(--text-dark)", lineHeight: 1.6 }}>{turn.answer}</div>
          </div>
        ))}
        {asking && <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{t("common.loading")}</div>}
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); ask(input); }}
        className="flex gap-2"
      >
        <input
          className="text-input"
          style={{ flex: 1 }}
          placeholder={t("workspace.copilotPlaceholder")}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="btn-primary" type="submit" disabled={asking}>→</button>
      </form>
    </div>
  );
}
