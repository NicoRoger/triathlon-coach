import type { Mesocycle, PlannedSession, Race } from "./api";

// Scale: 7px per day
const PX_PER_DAY = 7;
const ORIGIN_X = 160; // x position of "today"
const WINDOW_PAST_DAYS = 56; // 8 weeks back
const WINDOW_FUTURE_DAYS = 140; // 20 weeks forward

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

const SPORT_COLORS: Record<string, string> = {
  swim: "#0984e3",
  bike: "#e17055",
  run: "#00b894",
  brick: "#6c5ce7",
  strength: "#636e72",
};

const KEY_SESSION_TYPES = new Set(["fitness_test", "race_pace", "vo2max", "tempo", "threshold"]);

function daysBetween(a: string, b: string): number {
  const da = new Date(a + "T00:00:00Z").getTime();
  const db = new Date(b + "T00:00:00Z").getTime();
  return Math.round((db - da) / 86400000);
}

function dateToX(today: string, date: string): number {
  return ORIGIN_X + daysBetween(today, date) * PX_PER_DAY;
}

let _idCounter = 0;
function uid(): string {
  return `gen_${++_idCounter}_${Math.random().toString(36).slice(2, 8)}`;
}

function makeRect(
  x: number, y: number, width: number, height: number,
  backgroundColor: string, label: string, roughness = 1
): any[] {
  const rectId = uid();
  const rect = {
    type: "rectangle",
    id: rectId,
    x, y, width, height,
    strokeColor: "#343a40",
    backgroundColor,
    fillStyle: "solid",
    strokeWidth: 1,
    roughness,
    opacity: 90,
    angle: 0,
    groupIds: [],
    frameId: null,
    boundElements: [],
    locked: false,
    link: null,
    customData: null,
  };
  if (!label) return [rect];
  const text = {
    type: "text",
    id: uid(),
    x: x + 4,
    y: y + 4,
    width: Math.max(width - 8, 20),
    height: 20,
    text: label,
    fontSize: 11,
    fontFamily: 1,
    textAlign: "left",
    verticalAlign: "top",
    strokeColor: "#2d3436",
    backgroundColor: "transparent",
    fillStyle: "solid",
    strokeWidth: 1,
    roughness: 0,
    opacity: 100,
    angle: 0,
    groupIds: [],
    frameId: null,
    boundElements: [],
    locked: false,
    link: null,
    customData: null,
    containerId: null,
    originalText: label,
    lineHeight: 1.2,
  };
  return [rect, text];
}

function makeDiamond(
  cx: number, cy: number, size: number,
  backgroundColor: string, label: string
): any[] {
  const diamond = {
    type: "diamond",
    id: uid(),
    x: cx - size / 2,
    y: cy - size / 2,
    width: size,
    height: size,
    strokeColor: "#2d3436",
    backgroundColor,
    fillStyle: "solid",
    strokeWidth: 2,
    roughness: 1,
    opacity: 100,
    angle: 0,
    groupIds: [],
    frameId: null,
    boundElements: [],
    locked: false,
    link: null,
    customData: null,
  };
  if (!label) return [diamond];
  const text = {
    type: "text",
    id: uid(),
    x: cx - 40,
    y: cy + size / 2 + 4,
    width: 80,
    height: 16,
    text: label,
    fontSize: 10,
    fontFamily: 1,
    textAlign: "center",
    verticalAlign: "top",
    strokeColor: "#2d3436",
    backgroundColor: "transparent",
    fillStyle: "solid",
    strokeWidth: 1,
    roughness: 0,
    opacity: 100,
    angle: 0,
    groupIds: [],
    frameId: null,
    boundElements: [],
    locked: false,
    link: null,
    customData: null,
    containerId: null,
    originalText: label,
    lineHeight: 1.2,
  };
  return [diamond, text];
}

function makeLine(
  x1: number, y1: number, x2: number, y2: number,
  strokeColor: string, strokeWidth = 1, roughness = 0
): any {
  return {
    type: "line",
    id: uid(),
    x: x1, y: y1,
    width: x2 - x1, height: y2 - y1,
    points: [[0, 0], [x2 - x1, y2 - y1]],
    strokeColor,
    backgroundColor: "transparent",
    fillStyle: "solid",
    strokeWidth,
    roughness,
    opacity: 100,
    angle: 0,
    groupIds: [],
    frameId: null,
    boundElements: [],
    locked: false,
    link: null,
    customData: null,
    lastCommittedPoint: null,
    startBinding: null,
    endBinding: null,
    startArrowhead: null,
    endArrowhead: null,
  };
}

function makeText(x: number, y: number, text: string, fontSize = 12, color = "#2d3436"): any {
  return {
    type: "text",
    id: uid(),
    x, y,
    width: text.length * fontSize * 0.6 + 8,
    height: fontSize + 4,
    text,
    fontSize,
    fontFamily: 1,
    textAlign: "center",
    verticalAlign: "top",
    strokeColor: color,
    backgroundColor: "transparent",
    fillStyle: "solid",
    strokeWidth: 1,
    roughness: 0,
    opacity: 100,
    angle: 0,
    groupIds: [],
    frameId: null,
    boundElements: [],
    locked: false,
    link: null,
    customData: null,
    containerId: null,
    originalText: text,
    lineHeight: 1.2,
  };
}

export function generateTimelineElements(
  today: string,
  mesocycles: Mesocycle[],
  races: Race[],
  plannedSessions: PlannedSession[]
): any[] {
  _idCounter = 0;
  const elements: any[] = [];

  const startDate = addDays(today, -WINDOW_PAST_DAYS);
  const endDate = addDays(today, WINDOW_FUTURE_DAYS);
  const totalWidth = (WINDOW_PAST_DAYS + WINDOW_FUTURE_DAYS) * PX_PER_DAY;
  const axisX = ORIGIN_X - WINDOW_PAST_DAYS * PX_PER_DAY;
  const axisY = 80;

  // ── Timeline axis ──────────────────────────────────────────────────────────
  elements.push(makeLine(axisX, axisY, axisX + totalWidth, axisY, "#adb5bd", 2));

  // ── Month labels + tick marks ──────────────────────────────────────────────
  {
    let d = new Date(startDate + "T00:00:00Z");
    d.setUTCDate(1);
    if (d.toISOString().split("T")[0] < startDate) d.setUTCMonth(d.getUTCMonth() + 1);
    while (d.toISOString().split("T")[0] <= endDate) {
      const ds = d.toISOString().split("T")[0];
      const x = dateToX(today, ds);
      const label = d.toLocaleDateString("it-IT", { month: "short", year: "2-digit", timeZone: "UTC" });
      elements.push(makeText(x - 20, axisY - 22, label, 11, "#636e72"));
      elements.push(makeLine(x, axisY - 6, x, axisY + 6, "#adb5bd", 1));
      d.setUTCMonth(d.getUTCMonth() + 1);
    }
  }

  // ── "Oggi" marker ──────────────────────────────────────────────────────────
  elements.push(makeLine(ORIGIN_X, axisY - 30, ORIGIN_X, 290, "#e84393", 2, 0));
  elements.push(makeText(ORIGIN_X - 16, axisY - 44, "oggi", 11, "#e84393"));

  // ── Mesocycle blocks (y=95, h=40) ─────────────────────────────────────────
  for (const m of mesocycles) {
    if (m.end_date < startDate || m.start_date > endDate) continue;
    const x = dateToX(today, m.start_date);
    const xEnd = dateToX(today, m.end_date);
    const width = Math.max(xEnd - x, 20);
    const color = PHASE_COLORS[m.phase] ?? "#b2bec3";
    const label = width > 60 ? `${m.name}\n${m.phase}` : m.phase;
    elements.push(...makeRect(x, 95, width, 40, color, label));
  }

  // ── Weekly volume bars (y=148, max h=28) ──────────────────────────────────
  {
    const weeklyDuration: Record<string, number> = {};
    for (const s of plannedSessions) {
      if (s.planned_date < startDate || s.planned_date > endDate) continue;
      const d = new Date(s.planned_date + "T00:00:00Z");
      const dayOfWeek = d.getUTCDay();
      const monday = new Date(d);
      monday.setUTCDate(d.getUTCDate() - ((dayOfWeek + 6) % 7));
      const weekKey = monday.toISOString().split("T")[0];
      weeklyDuration[weekKey] = (weeklyDuration[weekKey] ?? 0) + (s.duration_s ?? 0);
    }
    const maxDuration = Math.max(...Object.values(weeklyDuration), 1);
    for (const [weekStart, durS] of Object.entries(weeklyDuration)) {
      const x = dateToX(today, weekStart);
      const barH = Math.round((durS / maxDuration) * 28);
      const hours = Math.round(durS / 3600 * 10) / 10;
      const barWidth = 7 * PX_PER_DAY - 3;
      elements.push(...makeRect(x, 148 + (28 - barH), barWidth, barH, "#dfe6e9", hours >= 1 ? `${hours}h` : "", 0));
    }
  }

  // ── Key session diamonds (y=185) ──────────────────────────────────────────
  for (const s of plannedSessions) {
    if (s.planned_date < startDate || s.planned_date > endDate) continue;
    const isKey = (s.target_tss !== null && s.target_tss >= 70) ||
      (s.session_type !== null && KEY_SESSION_TYPES.has(s.session_type));
    if (!isKey) continue;
    const x = dateToX(today, s.planned_date);
    const color = SPORT_COLORS[s.sport] ?? "#636e72";
    const label = s.session_type?.slice(0, 6) ?? s.sport.slice(0, 3);
    elements.push(...makeDiamond(x, 185, 16, color, label));
  }

  // ── Race markers (y=220) ──────────────────────────────────────────────────
  for (const r of races) {
    if (r.race_date < startDate || r.race_date > endDate) continue;
    const x = dateToX(today, r.race_date);
    const color = PRIORITY_COLORS[r.priority] ?? "#fdcb6e";
    const label = r.name.length > 14 ? r.name.slice(0, 12) + "…" : r.name;
    elements.push(...makeDiamond(x, 220, 22, color, label));
  }

  // ── Row labels (left side) ─────────────────────────────────────────────────
  elements.push(makeText(axisX - 10, 105, "Fase", 10, "#636e72"));
  elements.push(makeText(axisX - 10, 155, "Vol.", 10, "#636e72"));
  elements.push(makeText(axisX - 10, 182, "Key", 10, "#636e72"));
  elements.push(makeText(axisX - 10, 218, "Gare", 10, "#636e72"));

  return elements;
}

function addDays(dateStr: string, n: number): string {
  const d = new Date(dateStr + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().split("T")[0];
}
