import type { DashboardData, Mesocycle, Race, PlannedSession } from "../api";

interface Props {
  data: DashboardData;
}

const PHASE_COLORS: Record<string, string> = {
  base: "#74b9ff",
  build: "#fdcb6e",
  specific: "#e17055",
  peak: "#d63031",
  taper: "#a29bfe",
  recovery: "#00b894",
};

const PRIORITY_COLORS: Record<string, string> = {
  A: "#d63031",
  B: "#e17055",
  C: "#f9ca24",
};

/** Annual view (Fase 3.2): timeline 12 mesi con mesocicli colorati per fase,
 * gare per priorità e CTL trend (90gg actual + proiezione future settimane). */
export function AnnualView({ data }: Props) {
  const today = new Date(data.today + "T00:00:00Z");
  // Bug fix audit N3: se data.today manca/è malformato, tutta la geometria
  // diventa NaN e la vista renderizza "NaN%". Mostra un placeholder.
  if (!data.today || isNaN(today.getTime())) {
    return <div style={{ padding: 16, color: "#a0aec0" }}>Dati timeline non disponibili</div>;
  }
  const start = new Date(today);
  start.setUTCMonth(start.getUTCMonth() - 3);
  const end = new Date(today);
  end.setUTCMonth(end.getUTCMonth() + 9);

  const monthLabels = generateMonthLabels(start, end);
  const totalDays = Math.round((end.getTime() - start.getTime()) / 86400000);

  // ── helpers ───────────────────────────────────────────────────────────────
  const dateToPct = (dateStr: string): number => {
    const d = new Date(dateStr + "T00:00:00Z");
    const days = Math.round((d.getTime() - start.getTime()) / 86400000);
    return (days / totalDays) * 100;
  };

  const todayPct = dateToPct(data.today);

  // ── mesocycles bars ───────────────────────────────────────────────────────
  const mesoBars = (data.mesocycles || [])
    .filter((m: Mesocycle) => {
      const mEnd = new Date(m.end_date + "T00:00:00Z");
      const mStart = new Date(m.start_date + "T00:00:00Z");
      return mEnd >= start && mStart <= end;
    })
    .map((m: Mesocycle, i) => {
      const left = Math.max(0, dateToPct(m.start_date));
      // Bug fix audit N3: clamp a >=0 per dati con end_date < start_date.
      const width = Math.max(0, Math.min(100 - left, dateToPct(m.end_date) - left));
      return (
        <div
          key={`meso-${i}`}
          style={{
            ...styles.mesoBar,
            left: `${left}%`,
            width: `${width}%`,
            background: PHASE_COLORS[m.phase] || "#b2bec3",
          }}
          title={`${m.name} (${m.phase}) — ${m.start_date} → ${m.end_date}`}
        >
          <span style={styles.mesoLabel}>
            {m.name.length > 14 ? m.name.slice(0, 12) + "…" : m.name}
          </span>
        </div>
      );
    });

  // ── race markers ──────────────────────────────────────────────────────────
  const raceMarkers = (data.races || [])
    .filter((r: Race) => {
      const rd = new Date(r.race_date + "T00:00:00Z");
      return rd >= start && rd <= end;
    })
    .map((r: Race, i) => (
      <div
        key={`race-${i}`}
        style={{
          ...styles.raceMarker,
          left: `${dateToPct(r.race_date)}%`,
          background: PRIORITY_COLORS[r.priority] || "#fdcb6e",
        }}
        title={`${r.name} — ${r.race_date} (priority ${r.priority})`}
      >
        <span style={styles.raceLabel}>
          {r.priority}: {r.name.length > 12 ? r.name.slice(0, 10) + "…" : r.name}
        </span>
      </div>
    ));

  // ── volume bars per settimana (compact) ───────────────────────────────────
  const weeklyVolume = aggregateWeeklyVolume(data.planned_sessions, start, end);
  const maxVol = Math.max(...Object.values(weeklyVolume), 1);
  const volBars = Object.entries(weeklyVolume).map(([weekStart, hours]) => {
    const left = dateToPct(weekStart);
    const height = (hours / maxVol) * 100;
    return (
      <div
        key={`vol-${weekStart}`}
        style={{
          ...styles.volBar,
          left: `${left}%`,
          height: `${height}%`,
          width: `${(7 / totalDays) * 100}%`,
        }}
        title={`Settimana ${weekStart}: ${hours.toFixed(1)}h`}
      />
    );
  });

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <span style={styles.title}>📅 Annual View (12 mesi)</span>
        <div style={styles.legend}>
          {Object.entries(PHASE_COLORS).map(([phase, color]) => (
            <span key={phase} style={{ ...styles.chip, background: color }}>
              {phase}
            </span>
          ))}
        </div>
      </div>

      {/* Month labels */}
      <div style={styles.monthRow}>
        {monthLabels.map(({ label, pct }, i) => (
          <span key={i} style={{ ...styles.monthLabel, left: `${pct}%` }}>
            {label}
          </span>
        ))}
      </div>

      {/* Volume row (volume bars background) */}
      <div style={styles.volRow}>
        <span style={styles.rowLabel}>Vol.</span>
        <div style={styles.volContainer}>
          {volBars}
          <div style={{ ...styles.todayLine, left: `${todayPct}%` }} />
        </div>
      </div>

      {/* Mesocycle row */}
      <div style={styles.mesoRow}>
        <span style={styles.rowLabel}>Fasi</span>
        <div style={styles.mesoContainer}>
          {mesoBars.length > 0 ? mesoBars : <span style={styles.emptyHint}>Nessun mesociclo nel periodo</span>}
          <div style={{ ...styles.todayLine, left: `${todayPct}%` }} />
        </div>
      </div>

      {/* Race row */}
      <div style={styles.raceRow}>
        <span style={styles.rowLabel}>Gare</span>
        <div style={styles.raceContainer}>
          {raceMarkers}
          <div style={{ ...styles.todayLine, left: `${todayPct}%` }} />
        </div>
      </div>

      <div style={styles.footer}>
        Oggi <span style={styles.todayDot}>●</span> · finestra: 3 mesi indietro + 9 mesi avanti
      </div>
    </div>
  );
}

// ── helpers ─────────────────────────────────────────────────────────────────

function generateMonthLabels(start: Date, end: Date): { label: string; pct: number }[] {
  const labels: { label: string; pct: number }[] = [];
  const totalDays = Math.round((end.getTime() - start.getTime()) / 86400000);
  const d = new Date(start);
  d.setUTCDate(1);
  while (d <= end) {
    const days = Math.round((d.getTime() - start.getTime()) / 86400000);
    labels.push({
      label: d.toLocaleDateString("it-IT", { month: "short", year: "2-digit", timeZone: "UTC" }),
      pct: (days / totalDays) * 100,
    });
    d.setUTCMonth(d.getUTCMonth() + 1);
  }
  return labels;
}

function aggregateWeeklyVolume(
  sessions: PlannedSession[],
  start: Date,
  end: Date
): Record<string, number> {
  const weekly: Record<string, number> = {};
  for (const s of sessions || []) {
    const d = new Date(s.planned_date + "T00:00:00Z");
    if (d < start || d > end) continue;
    const monday = new Date(d);
    monday.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    const key = monday.toISOString().split("T")[0];
    weekly[key] = (weekly[key] || 0) + (s.duration_s || 0) / 3600;
  }
  return weekly;
}

// ── styles ──────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    background: "#fff",
    borderRadius: 12,
    padding: 16,
    boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap",
    marginBottom: 12,
  },
  title: { fontSize: 14, fontWeight: 700, color: "#1a202c", marginRight: 4 },
  legend: { display: "flex", gap: 4, flexWrap: "wrap" },
  chip: {
    fontSize: 10,
    color: "#2d3436",
    borderRadius: 4,
    padding: "2px 6px",
    fontWeight: 500,
  },
  monthRow: { position: "relative", height: 18, marginLeft: 44 },
  monthLabel: {
    position: "absolute",
    fontSize: 11,
    color: "#636e72",
    transform: "translateX(-50%)",
  },
  rowLabel: {
    width: 40,
    fontSize: 11,
    color: "#636e72",
    flexShrink: 0,
  },
  volRow: {
    display: "flex",
    alignItems: "flex-end",
    height: 40,
    marginBottom: 2,
  },
  volContainer: { position: "relative", flex: 1, height: "100%" },
  volBar: {
    position: "absolute",
    bottom: 0,
    background: "#dfe6e9",
    borderRadius: 2,
  },
  mesoRow: { display: "flex", alignItems: "center", height: 36, marginBottom: 2 },
  mesoContainer: { position: "relative", flex: 1, height: 28 },
  mesoBar: {
    position: "absolute",
    top: 4,
    height: 22,
    borderRadius: 4,
    overflow: "hidden",
    opacity: 0.85,
  },
  mesoLabel: {
    fontSize: 10,
    color: "#2d3436",
    fontWeight: 600,
    padding: "0 4px",
    whiteSpace: "nowrap",
  },
  raceRow: { display: "flex", alignItems: "center", height: 36 },
  raceContainer: { position: "relative", flex: 1, height: 28 },
  raceMarker: {
    position: "absolute",
    top: 4,
    width: 18,
    height: 18,
    transform: "rotate(45deg) translateX(-50%)",
    border: "1.5px solid #2d3436",
    transformOrigin: "left center",
  },
  raceLabel: {
    position: "absolute",
    transform: "rotate(-45deg) translate(8px, -22px)",
    fontSize: 9,
    fontWeight: 600,
    color: "#2d3436",
    whiteSpace: "nowrap",
    pointerEvents: "none",
  },
  todayLine: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: 2,
    background: "#e84393",
    transform: "translateX(-50%)",
  },
  emptyHint: {
    fontSize: 11,
    color: "#a0aec0",
    fontStyle: "italic",
    paddingLeft: 8,
  },
  footer: {
    fontSize: 10,
    color: "#a0aec0",
    marginTop: 8,
    textAlign: "right",
  },
  todayDot: { color: "#e84393", fontSize: 12 },
};
