import React, { useState } from "react";
import { setToken, fetchDashboard } from "../api";

interface Props {
  onLogin: () => void;
}

export function LoginScreen({ onLogin }: Props) {
  const [token, setTokenInput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setToken(token.trim());
    try {
      await fetchDashboard();
      onLogin();
    } catch (err: any) {
      setToken("");
      setError(err.message === "UNAUTHORIZED" ? "Token non valido." : `Errore: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.logo}>🏊‍♂️🚴🏃</div>
        <h1 style={styles.title}>Triathlon Coach</h1>
        <p style={styles.subtitle}>Inserisci il bearer token per accedere alla dashboard</p>
        <form onSubmit={handleSubmit} style={styles.form}>
          <input
            type="password"
            placeholder="Bearer token..."
            value={token}
            onChange={(e) => setTokenInput(e.target.value)}
            style={styles.input}
            autoComplete="current-password"
          />
          {error && <p style={styles.error}>{error}</p>}
          <button type="submit" disabled={loading || !token} style={styles.button}>
            {loading ? "Verifica..." : "Accedi →"}
          </button>
        </form>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    padding: 16,
  },
  card: {
    background: "#fff",
    borderRadius: 16,
    padding: "40px 32px",
    maxWidth: 380,
    width: "100%",
    boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
    textAlign: "center",
  },
  logo: { fontSize: 48, marginBottom: 12 },
  title: { fontSize: 24, fontWeight: 700, color: "#1a202c", marginBottom: 8 },
  subtitle: { fontSize: 14, color: "#718096", marginBottom: 24 },
  form: { display: "flex", flexDirection: "column", gap: 12 },
  input: {
    padding: "12px 16px",
    borderRadius: 8,
    border: "1.5px solid #e2e8f0",
    fontSize: 15,
    outline: "none",
  },
  error: { color: "#e53e3e", fontSize: 13, margin: 0 },
  button: {
    padding: "12px 24px",
    borderRadius: 8,
    border: "none",
    background: "linear-gradient(135deg, #667eea, #764ba2)",
    color: "#fff",
    fontSize: 16,
    fontWeight: 600,
    cursor: "pointer",
    opacity: 1,
  },
};
