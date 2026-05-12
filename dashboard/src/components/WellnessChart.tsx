import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { Wellness } from "../api";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

interface Props {
  wellness: Wellness[];
}

export function WellnessChart({ wellness }: Props) {
  if (wellness.length === 0) {
    return <div style={styles.empty}>Nessun dato wellness disponibile</div>;
  }

  const labels = wellness.map((w) => w.date.slice(5));
  const data = {
    labels,
    datasets: [
      {
        label: "HRV rmssd",
        data: wellness.map((w) => w.hrv_rmssd),
        borderColor: "#805ad5",
        backgroundColor: "rgba(128,90,213,0.08)",
        borderWidth: 2,
        pointRadius: 2,
        fill: false,
        tension: 0.3,
        spanGaps: true,
        yAxisID: "hrv",
      },
      {
        label: "Sleep score",
        data: wellness.map((w) => w.sleep_score),
        borderColor: "#dd6b20",
        borderWidth: 2,
        pointRadius: 2,
        fill: false,
        tension: 0.3,
        spanGaps: true,
        yAxisID: "sleep",
      },
      {
        label: "Body battery",
        data: wellness.map((w) => w.body_battery_max),
        borderColor: "#38a169",
        borderWidth: 1.5,
        borderDash: [4, 3],
        pointRadius: 0,
        fill: false,
        tension: 0.3,
        spanGaps: true,
        yAxisID: "sleep",
      },
    ],
  };

  const options: any = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "top", labels: { boxWidth: 12, font: { size: 11 } } },
      title: { display: true, text: "Wellness — HRV / Sleep / Body Battery (30gg)", font: { size: 13 } },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, maxTicksLimit: 10 }, grid: { display: false } },
      hrv: {
        position: "left",
        title: { display: true, text: "HRV (ms)", font: { size: 10 } },
        ticks: { font: { size: 10 } },
      },
      sleep: {
        position: "right",
        min: 0,
        max: 100,
        title: { display: true, text: "Score / Battery", font: { size: 10 } },
        ticks: { font: { size: 10 } },
        grid: { drawOnChartArea: false },
      },
    },
  };

  return (
    <div style={styles.container}>
      <Line data={data} options={options} />
    </div>
  );
}

const styles = {
  container: { height: 240, background: "#fff", borderRadius: 12, padding: "12px 8px", boxShadow: "0 1px 4px rgba(0,0,0,0.08)" } as React.CSSProperties,
  empty: { padding: 20, textAlign: "center", color: "#a0aec0", background: "#fff", borderRadius: 12 } as React.CSSProperties,
};
