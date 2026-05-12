import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { Metric, ProjectedDay } from "../api";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

interface Props {
  metrics: Metric[];
  projection: ProjectedDay[];
}

export function PMCChart({ metrics, projection }: Props) {
  if (metrics.length === 0) {
    return <div style={styles.empty}>Nessun dato PMC disponibile</div>;
  }

  const histLabels = metrics.map((m) => m.date);
  const projLabels = projection.map((p) => p.date);
  const allLabels = [...histLabels, ...projLabels];

  // Sparse projection arrays (null for historical dates)
  const ctlProj = [
    ...metrics.map(() => null as number | null),
    ...projection.map((p) => Math.round(p.ctl * 10) / 10),
  ];
  const atlProj = [
    ...metrics.map(() => null as number | null),
    ...projection.map((p) => Math.round(p.atl * 10) / 10),
  ];
  const tsbProj = [
    ...metrics.map(() => null as number | null),
    ...projection.map((p) => Math.round(p.tsb * 10) / 10),
  ];

  // Last actual point → first projection point (bridge)
  const lastMetric = metrics[metrics.length - 1];
  if (lastMetric && projection.length > 0) {
    ctlProj[metrics.length - 1] = lastMetric.ctl;
    atlProj[metrics.length - 1] = lastMetric.atl;
    tsbProj[metrics.length - 1] = lastMetric.tsb;
  }

  const data = {
    labels: allLabels,
    datasets: [
      {
        label: "CTL",
        data: [...metrics.map((m) => m.ctl), ...projection.map(() => null)],
        borderColor: "#3182ce",
        backgroundColor: "rgba(49,130,206,0.08)",
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0.3,
        spanGaps: false,
      },
      {
        label: "CTL proj.",
        data: ctlProj,
        borderColor: "#3182ce",
        borderWidth: 2,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false,
        tension: 0.3,
        spanGaps: false,
      },
      {
        label: "ATL",
        data: [...metrics.map((m) => m.atl), ...projection.map(() => null)],
        borderColor: "#e53e3e",
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        tension: 0.3,
        spanGaps: false,
      },
      {
        label: "ATL proj.",
        data: atlProj,
        borderColor: "#e53e3e",
        borderWidth: 2,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false,
        tension: 0.3,
        spanGaps: false,
      },
      {
        label: "TSB",
        data: [...metrics.map((m) => m.tsb), ...projection.map(() => null)],
        borderColor: "#38a169",
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
        tension: 0.3,
        spanGaps: false,
        yAxisID: "tsb",
      },
      {
        label: "TSB proj.",
        data: tsbProj,
        borderColor: "#38a169",
        borderWidth: 1.5,
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false,
        tension: 0.3,
        spanGaps: false,
        yAxisID: "tsb",
      },
    ],
  };

  const options: any = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "top", labels: { boxWidth: 12, font: { size: 11 } } },
      title: { display: true, text: "PMC — CTL / ATL / TSB (90gg + proiezione 12 sett.)", font: { size: 13 } },
      tooltip: {
        callbacks: {
          label: (ctx: any) => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1) ?? "—"}`,
        },
      },
    },
    scales: {
      x: {
        ticks: {
          maxTicksLimit: 10,
          font: { size: 10 },
          callback: (_: any, i: number) => allLabels[i]?.slice(5),
        },
        grid: { display: false },
      },
      y: {
        title: { display: true, text: "CTL / ATL", font: { size: 10 } },
        ticks: { font: { size: 10 } },
      },
      tsb: {
        position: "right",
        title: { display: true, text: "TSB", font: { size: 10 } },
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
  container: { height: 280, background: "#fff", borderRadius: 12, padding: "12px 8px", boxShadow: "0 1px 4px rgba(0,0,0,0.08)" } as React.CSSProperties,
  empty: { padding: 20, textAlign: "center", color: "#a0aec0", background: "#fff", borderRadius: 12 } as React.CSSProperties,
};
