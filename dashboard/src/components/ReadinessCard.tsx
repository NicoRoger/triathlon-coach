import type { Metric, Race } from "../api";

interface Props {
  latest: Metric | null;
  nextRace: Race | null;
  today: string;
}

function readinessColor(score: number | null): string {
  if (score === null) return "#a0aec0";
  if (score >= 70) return "#38a169";
  if (score >= 40) return "#d69e2e";
  return "#e53e3e";
}

function tsbColor(tsb: number | null): string {
  if (tsb === null) return "#a0aec0";
  if (tsb >= 5) return "#38a169";
  if (tsb >= -10) return "#d69e2e";
  return "#e53e3e";
}

function daysUntil(today: string, raceDate: string): number {
  const t = new Date(today + "T00:00:00Z").getTime();
  const r = new Date(raceDate + "T00:00:00Z").getTime();
  return Math.ceil((r - t) / 86400000);
}

export function ReadinessCard({ latest, nextRace, today }: Props) {
  const score = latest?.readiness_score ?? null;
  const label = latest?.readiness_label ?? "—";
  const tsb = latest?.tsb != null ? Math.round(latest.tsb * 10) / 10 : null;
  const ctl = latest?.ctl != null ? Math.round(latest.ctl * 10) / 10 : null;
  const flags = latest?.flags ?? [];
  const days = nextRace ? daysUntil(today, nextRace.race_date) : null;

  return (
    <div style={styles.grid}>
      {/* Readiness */}
      <div style={{ ...styles.card, borderTop: `4px solid ${readinessColor(score)}` }}>
        <div style={styles.value(readinessColor(score))}>{score ?? "—"}</div>
        <div style={styles.unit}>/100</div>
        <div style={styles.label}>Readiness</div>
        <div style={styles.sub}>{label.toUpperCase()}</div>
        {flags.length > 0 && (
          <div style={styles.flags}>
            {flags.map((f) => <span key={f} style={styles.flag}>{f.replace(/_/g, " ")}</span>)}
          </div>
        )}
      </div>

      {/* CTL / TSB */}
      <div style={{ ...styles.card, borderTop: `4px solid ${tsbColor(tsb)}` }}>
        <div style={styles.value("#2b6cb0")}>{ctl ?? "—"}</div>
        <div style={styles.unit}>CTL</div>
        <div style={styles.label}>Forma</div>
        <div style={{ ...styles.sub, color: tsbColor(tsb) }}>
          TSB {tsb != null ? (tsb >= 0 ? `+${tsb}` : `${tsb}`) : "—"}
        </div>
      </div>

      {/* Next race */}
      <div style={{ ...styles.card, borderTop: "4px solid #e53e3e" }}>
        <div style={styles.value("#e53e3e")}>{days ?? "—"}</div>
        <div style={styles.unit}>giorni</div>
        <div style={styles.label}>Prossima gara</div>
        <div style={styles.sub}>{nextRace?.name ?? "nessuna"}</div>
        {nextRace && (
          <div style={{ ...styles.sub, color: "#718096", fontSize: 11 }}>
            {nextRace.priority}• {nextRace.race_date}
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 12,
  } as React.CSSProperties,
  card: {
    background: "#fff",
    borderRadius: 12,
    padding: "16px 12px",
    textAlign: "center",
    boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
  } as React.CSSProperties,
  value: (color: string): React.CSSProperties => ({
    fontSize: 32,
    fontWeight: 700,
    color,
    lineHeight: 1,
  }),
  unit: { fontSize: 11, color: "#a0aec0", marginTop: 2 } as React.CSSProperties,
  label: { fontSize: 13, color: "#4a5568", fontWeight: 600, marginTop: 8 } as React.CSSProperties,
  sub: { fontSize: 12, color: "#718096", marginTop: 2 } as React.CSSProperties,
  flags: { marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4, justifyContent: "center" } as React.CSSProperties,
  flag: {
    fontSize: 9,
    background: "#fed7d7",
    color: "#c53030",
    borderRadius: 4,
    padding: "2px 4px",
  } as React.CSSProperties,
};
