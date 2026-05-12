import React, { useCallback, useEffect, useState } from "react";
import { clearToken, fetchDashboard, getToken, projectPMC } from "./api";
import type { DashboardData } from "./api";
import { LoginScreen } from "./components/LoginScreen";
import { ReadinessCard } from "./components/ReadinessCard";
import { PMCChart } from "./components/PMCChart";
import { WellnessChart } from "./components/WellnessChart";
import { ComplianceBar } from "./components/ComplianceBar";
import { UpcomingSessions } from "./components/UpcomingSessions";
import { GoalBoard } from "./components/GoalBoard";

const REFRESH_MS = 5 * 60 * 1000;

export default function App() {
  const [loggedIn, setLoggedIn] = useState(!!getToken());
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await fetchDashboard();
      setData(d);
      setLastUpdated(new Date());
    } catch (e: any) {
      if (e.message === "UNAUTHORIZED") {
        clearToken();
        setLoggedIn(false);
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!loggedIn) return;
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [loggedIn, load]);

  if (!loggedIn) return <LoginScreen onLogin={() => setLoggedIn(true)} />;

  const projection = data ? projectPMC(data.metrics, data.planned_sessions) : [];
  const nextRace = data?.races?.[0] ?? null;

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerTitle}>🏊‍♂️🚴🏃 Triathlon Dashboard</span>
        <div style={styles.headerRight}>
          {loading && <span style={styles.dot}>●</span>}
          {lastUpdated && (
            <span style={styles.updated}>
              {lastUpdated.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            onClick={load}
            style={styles.refreshBtn}
            disabled={loading}
            title="Aggiorna dati"
          >↺</button>
          <button
            onClick={() => { clearToken(); setLoggedIn(false); setData(null); }}
            style={styles.logoutBtn}
            title="Esci"
          >⎋</button>
        </div>
      </div>

      {error && <div style={styles.errorBanner}>⚠ {error}</div>}

      {!data && !loading && (
        <div style={styles.empty}>Caricamento dati…</div>
      )}

      {data && (
        <div style={styles.content}>
          <ReadinessCard latest={data.latest_metrics} nextRace={nextRace} today={data.today} />
          <PMCChart metrics={data.metrics} projection={projection} />
          <WellnessChart wellness={data.wellness} />
          <ComplianceBar plannedSessions={data.planned_sessions} activities={data.activities} today={data.today} />
          <UpcomingSessions sessions={data.planned_sessions} today={data.today} />
          <GoalBoard data={data} />
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#f0f4f8" },
  header: {
    position: "sticky", top: 0, zIndex: 100,
    background: "#1a202c", color: "#fff",
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "10px 16px",
  },
  headerTitle: { fontSize: 15, fontWeight: 700, letterSpacing: 0.3 },
  headerRight: { display: "flex", alignItems: "center", gap: 8 },
  dot: { color: "#68d391", fontSize: 10, animation: "pulse 1s infinite" },
  updated: { fontSize: 11, color: "#a0aec0" },
  refreshBtn: {
    background: "transparent", border: "1px solid #4a5568",
    color: "#e2e8f0", borderRadius: 6, padding: "4px 8px",
    cursor: "pointer", fontSize: 14,
  },
  logoutBtn: {
    background: "transparent", border: "1px solid #4a5568",
    color: "#e2e8f0", borderRadius: 6, padding: "4px 8px",
    cursor: "pointer", fontSize: 14,
  },
  errorBanner: {
    background: "#fff5f5", color: "#c53030",
    padding: "10px 16px", fontSize: 13,
    borderBottom: "1px solid #fed7d7",
  },
  empty: { padding: 40, textAlign: "center", color: "#a0aec0" },
  content: {
    maxWidth: 800,
    margin: "0 auto",
    padding: "16px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
};
