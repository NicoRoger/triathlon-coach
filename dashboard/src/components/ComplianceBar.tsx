import type { PlannedSession, Activity } from "../api";

interface Props {
  plannedSessions: PlannedSession[];
  activities: Activity[];
  today: string;
}

function mondayOf(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00Z");
  const day = d.getUTCDay();
  d.setUTCDate(d.getUTCDate() - ((day + 6) % 7));
  return d.toISOString().split("T")[0];
}

function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().split("T")[0];
}

export function ComplianceBar({ plannedSessions, activities, today }: Props) {
  const weeks: { start: string; end: string }[] = [];
  for (let w = 4; w >= 1; w--) {
    const mon = mondayOf(addDays(today, -7 * w));
    weeks.push({ start: mon, end: addDays(mon, 6) });
  }

  const rows = weeks.map(({ start, end }) => {
    const planned = plannedSessions.filter(
      (s) => s.planned_date >= start && s.planned_date <= end
    ).length;
    const completed = activities.filter((a) => {
      const d = a.started_at.slice(0, 10);
      return d >= start && d <= end;
    }).length;
    const pct = planned > 0 ? Math.min(Math.round((completed / planned) * 100), 100) : null;
    const label = new Date(start + "T00:00:00Z")
      .toLocaleDateString("it-IT", { day: "2-digit", month: "short", timeZone: "UTC" });
    return { label, planned, completed, pct };
  });

  return (
    <div style={styles.container}>
      <div style={styles.title}>Compliance piano — ultime 4 settimane</div>
      <div style={styles.rows}>
        {rows.map((r, i) => (
          <div key={i} style={styles.row}>
            <div style={styles.weekLabel}>{r.label}</div>
            <div style={styles.barWrap}>
              <div
                style={{
                  ...styles.bar,
                  width: `${r.pct ?? 0}%`,
                  background: r.pct === null ? "#e2e8f0"
                    : r.pct >= 80 ? "#38a169"
                    : r.pct >= 50 ? "#d69e2e"
                    : "#e53e3e",
                }}
              />
            </div>
            <div style={styles.pctLabel}>
              {r.pct !== null ? `${r.pct}%` : "—"}{" "}
              <span style={{ color: "#a0aec0", fontSize: 11 }}>({r.completed}/{r.planned})</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { background: "#fff", borderRadius: 12, padding: 16, boxShadow: "0 1px 4px rgba(0,0,0,0.08)" },
  title: { fontSize: 13, fontWeight: 600, color: "#2d3748", marginBottom: 12 },
  rows: { display: "flex", flexDirection: "column", gap: 8 },
  row: { display: "flex", alignItems: "center", gap: 10 },
  weekLabel: { width: 60, fontSize: 12, color: "#4a5568", flexShrink: 0 },
  barWrap: { flex: 1, height: 16, background: "#edf2f7", borderRadius: 8, overflow: "hidden" },
  bar: { height: "100%", borderRadius: 8, transition: "width 0.4s ease" },
  pctLabel: { width: 80, fontSize: 12, color: "#4a5568", textAlign: "right", flexShrink: 0 },
};
