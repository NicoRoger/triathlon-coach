const MCP_URL = "https://mcp-server.nicorugg.workers.dev";

export function getToken(): string | null {
  return localStorage.getItem("dashboard_token");
}

export function setToken(t: string) {
  localStorage.setItem("dashboard_token", t);
}

export function clearToken() {
  localStorage.removeItem("dashboard_token");
}

export interface Metric {
  date: string;
  ctl: number | null;
  atl: number | null;
  tsb: number | null;
  daily_tss: number | null;
  hrv_z_score: number | null;
  readiness_score: number | null;
  readiness_label: string | null;
  flags: string[] | null;
}

export interface Wellness {
  date: string;
  hrv_rmssd: number | null;
  sleep_score: number | null;
  body_battery_max: number | null;
  resting_hr: number | null;
}

export interface PlannedSession {
  planned_date: string;
  sport: string;
  session_type: string | null;
  duration_s: number | null;
  target_tss: number | null;
  description: string | null;
}

export interface Activity {
  started_at: string;
  sport: string;
}

export interface Mesocycle {
  id: string;
  name: string;
  phase: string;
  start_date: string;
  end_date: string;
  notes: string | null;
}

export interface Race {
  name: string;
  race_date: string;
  priority: string;
  distance: string | null;
}

export interface Zone {
  discipline: string;
  ftp_w: number | null;
  threshold_pace_s_per_km: number | null;
  css_pace_s_per_100m: number | null;
  lthr: number | null;
}

export interface DashboardData {
  generated_at: string;
  today: string;
  metrics: Metric[];
  wellness: Wellness[];
  planned_sessions: PlannedSession[];
  activities: Activity[];
  mesocycles: Mesocycle[];
  races: Race[];
  zones: Zone[];
  latest_metrics: Metric | null;
}

export async function fetchDashboard(): Promise<DashboardData> {
  const token = getToken();
  const resp = await fetch(`${MCP_URL}/dashboard-data`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (resp.status === 401) throw new Error("UNAUTHORIZED");
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// Project CTL/ATL/TSB forward 12 weeks from last known values
export interface ProjectedDay {
  date: string;
  ctl: number;
  atl: number;
  tsb: number;
}

function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().split("T")[0];
}

export function projectPMC(metrics: Metric[], plannedSessions: PlannedSession[]): ProjectedDay[] {
  if (metrics.length === 0) return [];

  const last = metrics[metrics.length - 1];
  let ctl = last.ctl ?? 0;
  let atl = last.atl ?? 0;
  const lastDate = last.date;

  // Sum target_tss per date for future planned sessions
  const tssByDate: Record<string, number> = {};
  for (const s of plannedSessions) {
    if (s.planned_date > lastDate && s.target_tss) {
      tssByDate[s.planned_date] = (tssByDate[s.planned_date] ?? 0) + s.target_tss;
    }
  }

  const result: ProjectedDay[] = [];
  let d = addDays(lastDate, 1);
  const end = addDays(lastDate, 84); // 12 weeks
  while (d <= end) {
    const tss = tssByDate[d] ?? 0;
    ctl = ctl + (tss - ctl) / 42;
    atl = atl + (tss - atl) / 7;
    result.push({ date: d, ctl, atl, tsb: ctl - atl });
    d = addDays(d, 1);
  }
  return result;
}
