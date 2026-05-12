import React, { Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { DashboardData } from "../api";
import { generateTimelineElements } from "../excalidraw-generator";

const ExcalidrawLazy = React.lazy(() =>
  import("@excalidraw/excalidraw").then((m) => ({ default: m.Excalidraw }))
);

interface Props {
  data: DashboardData;
}

export function GoalBoard({ data }: Props) {
  const apiRef = useRef<any>(null);
  const [key, setKey] = useState(0);

  const elements = useMemo(
    () => generateTimelineElements(data.today, data.mesocycles, data.races, data.planned_sessions),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, data.today]
  );

  // When data changes, update existing scene (if API is ready)
  useEffect(() => {
    if (apiRef.current) {
      apiRef.current.updateScene({ elements });
    }
  }, [elements]);

  function handleRegenerate() {
    setKey((k) => k + 1);
  }

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <span style={styles.title}>🎯 Goal Board</span>
        <div style={styles.legend}>
          {[
            ["base", "#74b9ff"], ["build", "#fdcb6e"], ["specific", "#e17055"],
            ["peak", "#d63031"], ["taper", "#a29bfe"], ["recovery", "#00b894"],
          ].map(([phase, color]) => (
            <span key={phase} style={{ ...styles.chip, background: color }}>{phase}</span>
          ))}
        </div>
        <button onClick={handleRegenerate} style={styles.regenBtn} title="Rigenera dal piano">
          ↺ Rigenera
        </button>
      </div>
      <div style={styles.board}>
        <Suspense fallback={<div style={styles.loading}>Caricamento Excalidraw…</div>}>
          <ExcalidrawLazy
            excalidrawAPI={(api: any) => { apiRef.current = api; }}
            initialData={{ elements, appState: { viewBackgroundColor: "#fafafa", gridSize: null } }}
            viewModeEnabled={false}
            zenModeEnabled={false}
            gridModeEnabled={false}
            theme="light"
          />
        </Suspense>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: { background: "#fff", borderRadius: 12, overflow: "hidden", boxShadow: "0 1px 4px rgba(0,0,0,0.08)" },
  header: {
    display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
    padding: "12px 16px", borderBottom: "1px solid #f0f4f8",
  },
  title: { fontSize: 14, fontWeight: 700, color: "#1a202c", marginRight: 4 },
  legend: { display: "flex", gap: 4, flexWrap: "wrap", flex: 1 },
  chip: {
    fontSize: 10, color: "#2d3436", borderRadius: 4,
    padding: "2px 6px", fontWeight: 500,
  },
  regenBtn: {
    padding: "6px 12px", borderRadius: 8, border: "1.5px solid #e2e8f0",
    background: "#fff", fontSize: 12, cursor: "pointer", color: "#4a5568", fontWeight: 600,
  },
  board: { height: 360 },
  loading: { height: 360, display: "flex", alignItems: "center", justifyContent: "center", color: "#a0aec0" },
};
