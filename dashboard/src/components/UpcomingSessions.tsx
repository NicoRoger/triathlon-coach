import type { PlannedSession } from "../api";

interface Props {
  sessions: PlannedSession[];
  today: string;
}

const SPORT_EMOJI: Record<string, string> = {
  swim: "🏊", bike: "🚴", run: "🏃", brick: "🏋️+🚴", strength: "💪",
};

const SESSION_TYPE_LABELS: Record<string, string> = {
  Z2_endurance: "Z2 endurance",
  LSD: "Lungo lento",
  threshold: "Soglia",
  vo2max: "VO₂max",
  tempo: "Tempo",
  race_pace: "Ritmo gara",
  fitness_test: "Test fitness",
  recovery: "Recupero",
  technique: "Tecnica",
};

function formatDuration(s: number | null): string {
  if (!s) return "—";
  const m = Math.round(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h${m % 60 > 0 ? String(m % 60).padStart(2, "0") : ""}` : `${m}min`;
}

function dayLabel(dateStr: string, today: string): string {
  const diff = Math.round(
    (new Date(dateStr + "T00:00:00Z").getTime() - new Date(today + "T00:00:00Z").getTime()) / 86400000
  );
  if (diff === 0) return "oggi";
  if (diff === 1) return "domani";
  return new Date(dateStr + "T00:00:00Z")
    .toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

export function UpcomingSessions({ sessions, today }: Props) {
  const upcoming = sessions
    .filter((s) => s.planned_date >= today)
    .slice(0, 7);

  return (
    <div style={styles.container}>
      <div style={styles.title}>Prossime sessioni</div>
      {upcoming.length === 0 ? (
        <div style={styles.empty}>Nessuna sessione pianificata</div>
      ) : (
        <div style={styles.list}>
          {upcoming.map((s, i) => (
            <div key={i} style={styles.row}>
              <div style={styles.emoji}>{SPORT_EMOJI[s.sport] ?? "🏅"}</div>
              <div style={styles.info}>
                <div style={styles.day}>{dayLabel(s.planned_date, today)}</div>
                <div style={styles.type}>
                  {SESSION_TYPE_LABELS[s.session_type ?? ""] ?? (s.session_type ?? s.sport)}
                </div>
                {s.description && (
                  <div style={styles.desc}>{s.description.slice(0, 80)}</div>
                )}
              </div>
              <div style={styles.meta}>
                <div style={styles.duration}>{formatDuration(s.duration_s)}</div>
                {s.target_tss !== null && (
                  <div style={styles.tss}>{s.target_tss} TSS</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { background: "#fff", borderRadius: 12, padding: 16, boxShadow: "0 1px 4px rgba(0,0,0,0.08)" },
  title: { fontSize: 13, fontWeight: 600, color: "#2d3748", marginBottom: 12 },
  empty: { color: "#a0aec0", fontSize: 13, padding: "8px 0" },
  list: { display: "flex", flexDirection: "column", gap: 8 },
  row: { display: "flex", alignItems: "flex-start", gap: 10, padding: "8px 0", borderBottom: "1px solid #f7fafc" },
  emoji: { fontSize: 22, width: 32, textAlign: "center", flexShrink: 0 },
  info: { flex: 1, minWidth: 0 },
  day: { fontSize: 12, color: "#4a5568", fontWeight: 600 },
  type: { fontSize: 13, color: "#1a202c", fontWeight: 500, marginTop: 1 },
  desc: { fontSize: 11, color: "#718096", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
  meta: { textAlign: "right", flexShrink: 0 },
  duration: { fontSize: 13, fontWeight: 600, color: "#2b6cb0" },
  tss: { fontSize: 11, color: "#718096", marginTop: 2 },
};
