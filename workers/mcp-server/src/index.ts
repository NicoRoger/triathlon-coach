/**
 * MCP Server — Cloudflare Worker
 *
 * Esposto come custom connector in Claude.ai. Fornisce all'agente coach accesso
 * ai dati operativi (metriche, attività, log soggettivi) e la capacità di
 * PROPORRE modifiche al piano (mai scriverle senza conferma esplicita).
 *
 * Implementazione MCP minimal compliant: JSON-RPC 2.0 su HTTP POST.
 * Endpoint: POST /mcp
 *
 * Tool esposti:
 *   - get_weekly_context(days)
 *   - get_race_context(days_ahead)
 *   - get_session_review_context(activity_id)
 *   - get_upcoming_plan(days)
 *   - get_recent_metrics(days)
 *   - get_planned_session(date)
 *   - get_activity_history(sport, days)
 *   - query_subjective_log(days, kind)
 *   - propose_plan_change(date, change) — restituisce proposta, NON scrive
 *
 * Auth: Bearer token (semplice, single-user).
 */

interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_KEY: string;
  MCP_BEARER_TOKEN: string;
  GH_PAT_TRIGGER: string;
}

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number | string | null;
  method: string;
  params?: any;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number | string | null;
  result?: any;
  error?: { code: number; message: string; data?: any };
}

const TOOLS = [
  {
    name: "get_weekly_context",
    description: "Contesto aggregato per weekly review da Claude web/mobile: health sync, metriche, wellness, attivitÃ , piano, debrief, analisi e modulazioni. Usalo come primo tool per 'fai la weekly review'.",
    inputSchema: {
      type: "object",
      properties: {
        days: { type: "integer", default: 7, minimum: 1, maximum: 28 },
        include_next_days: { type: "integer", default: 7, minimum: 1, maximum: 21 },
      },
    },
  },
  {
    name: "get_race_context",
    description: "Contesto aggregato per race briefing: prossima gara pianificata, metriche recenti, attivitÃ , wellness, piano e log soggettivi. Usalo solo in race week o su richiesta gara.",
    inputSchema: {
      type: "object",
      properties: {
        race_date: { type: "string", format: "date" },
        days_ahead: { type: "integer", default: 21, minimum: 1, maximum: 180 },
      },
    },
  },
  {
    name: "get_session_review_context",
    description: "Contesto per analizzare una singola sessione su richiesta: attivitÃ , sessione pianificata, metriche del giorno, storico sport e debrief recenti. Non consuma API LLM lato backend.",
    inputSchema: {
      type: "object",
      properties: {
        activity_id: { type: "string", description: "ID interno o external_id attivitÃ . Se omesso usa l'ultima attivitÃ ." },
        history_days: { type: "integer", default: 21, minimum: 1, maximum: 90 },
      },
    },
  },
  {
    name: "get_upcoming_plan",
    description: "Restituisce le sessioni pianificate dei prossimi N giorni. Utile da smartphone per controllare il piano senza weekly review completa.",
    inputSchema: {
      type: "object",
      properties: {
        days: { type: "integer", default: 7, minimum: 1, maximum: 60 },
      },
    },
  },
  {
    name: "get_recent_metrics",
    description: "Restituisce daily_metrics (CTL/ATL/TSB/HRV z-score/readiness) ultimi N giorni",
    inputSchema: {
      type: "object",
      properties: { days: { type: "integer", default: 14, minimum: 1, maximum: 90 } },
    },
  },
  {
    name: "get_planned_session",
    description: "Sessione pianificata per una data specifica (default: oggi)",
    inputSchema: {
      type: "object",
      properties: { date: { type: "string", format: "date" } },
    },
  },
  {
    name: "get_activity_history",
    description: "Attività completate, opzionalmente filtrate per sport, ultimi N giorni",
    inputSchema: {
      type: "object",
      properties: {
        sport: { type: "string", enum: ["swim", "bike", "run", "brick", "strength", "all"] },
        days: { type: "integer", default: 14, minimum: 1, maximum: 365 },
      },
    },
  },
  {
    name: "query_subjective_log",
    description: "Log soggettivi (RPE, malattia, infortuni, note libere) ultimi N giorni",
    inputSchema: {
      type: "object",
      properties: {
        days: { type: "integer", default: 7, minimum: 1, maximum: 90 },
        kind: { type: "string", enum: ["all", "post_session", "illness", "injury", "evening_debrief", "free_note"] },
      },
    },
  },
  {
    name: "propose_plan_change",
    description: "PROPONE una modifica al piano. NON scrive su DB. L'atleta deve confermare esplicitamente prima di applicarla con commit_plan_change.",
    inputSchema: {
      type: "object",
      required: ["target_date", "rationale", "change"],
      properties: {
        target_date: { type: "string", format: "date" },
        rationale: { type: "string" },
        change: {
          type: "object",
          description: "Nuovo contenuto sessione: sport, session_type, duration_s, target_tss, description",
        },
      },
    },
  },
  {
    name: "commit_plan_change",
    description: "Scrive una sessione pianificata nel DB. Da chiamare SOLO dopo conferma esplicita dell'atleta su una proposta. Idempotente: se esiste già una sessione per quella data e sport, viene aggiornata.",
    inputSchema: {
      type: "object",
      required: ["planned_date", "sport", "session_type", "duration_s", "description"],
      properties: {
        planned_date: { type: "string", format: "date" },
        sport: { type: "string", enum: ["swim", "bike", "run", "brick", "strength"] },
        session_type: { type: "string", description: "Tipo sessione: Z2_endurance, threshold, vo2max, recovery, race_pace, technique, brick, ecc." },
        duration_s: { type: "integer", minimum: 60 },
        target_tss: { type: "number" },
        target_zones: {
          type: "object",
          description: "Distribuzione zone, es. {z1: 0.2, z2: 0.7, z4: 0.1}",
        },
        description: { type: "string", description: "Descrizione human-readable della sessione, con razionali" },
        structured: {
          type: "object",
          description: "Opzionale: workout strutturato per esportazione futura su Garmin",
        },
        mesocycle_id: { type: "string", description: "Opzionale: UUID mesociclo associato" },
        calendar_event_id: { type: "string", description: "Opzionale: ID evento Google Calendar associato" },
      },
    },
  },
  {
    name: "force_garmin_sync",
    description: "Forza un sync Garmin triggerando il workflow ingest via GitHub Actions. Se l'ultimo sync è < 1 ora fa, restituisce 'skipped'. Altrimenti triggera e attende fino a 90s. Usato dalla weekly review per garantire dati freschi.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
];

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Auth
    const auth = req.headers.get("authorization");
    if (auth !== `Bearer ${env.MCP_BEARER_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    if (req.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const rpc = (await req.json()) as JsonRpcRequest;
    const resp = await handleRpc(rpc, env);
    return new Response(JSON.stringify(resp), {
      headers: { "Content-Type": "application/json" },
    });
  },
};

async function handleRpc(rpc: JsonRpcRequest, env: Env): Promise<JsonRpcResponse> {
  try {
    if (rpc.method === "initialize") {
      return ok(rpc.id, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "triathlon-coach-mcp", version: "0.1.0" },
      });
    }
    if (rpc.method === "tools/list") {
      return ok(rpc.id, { tools: TOOLS });
    }
    if (rpc.method === "tools/call") {
      const { name, arguments: args } = rpc.params;
      const out = await callTool(name, args || {}, env);
      return ok(rpc.id, { content: [{ type: "text", text: JSON.stringify(out, null, 2) }] });
    }
    return err(rpc.id, -32601, `Method not found: ${rpc.method}`);
  } catch (e: any) {
    return err(rpc.id, -32603, e.message || String(e));
  }
}

function ok(id: any, result: any): JsonRpcResponse {
  return { jsonrpc: "2.0", id, result };
}
function err(id: any, code: number, message: string): JsonRpcResponse {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

// ============================================================================
// Tool implementations
// ============================================================================
async function callTool(name: string, args: any, env: Env): Promise<any> {
  switch (name) {
    case "get_weekly_context":
      return getWeeklyContext(args.days || 7, args.include_next_days || 7, env);
    case "get_race_context":
      return getRaceContext(args.race_date, args.days_ahead || 21, env);
    case "get_session_review_context":
      return getSessionReviewContext(args.activity_id, args.history_days || 21, env);
    case "get_upcoming_plan":
      return getUpcomingPlan(args.days || 7, env);
    case "get_recent_metrics":
      return getRecentMetrics(args.days || 14, env);
    case "get_planned_session":
      return getPlannedSession(args.date || todayISO(), env);
    case "get_activity_history":
      return getActivityHistory(args.sport || "all", args.days || 14, env);
    case "query_subjective_log":
      return queryLog(args.days || 7, args.kind || "all", env);
    case "propose_plan_change":
      return proposePlan(args, env);
    case "commit_plan_change":
      return commitPlanChange(args, env);
    case "force_garmin_sync":
      return forceGarminSync(env);
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

async function sb(env: Env, path: string): Promise<any> {
  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/${path}`, {
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    },
  });
  if (!resp.ok) throw new Error(`Supabase ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

function todayISO(): string {
  return new Date().toISOString().split("T")[0];
}

function todayRomeISO(): string {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: "Europe/Rome",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function daysAgoISO(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().split("T")[0];
}

function daysFromISO(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().split("T")[0];
}

function clampInt(value: number, min: number, max: number): number {
  const n = Number.isFinite(value) ? Math.trunc(value) : min;
  return Math.min(Math.max(n, min), max);
}

function coachProtocol() {
  return {
    interface: "Claude web/mobile via remote MCP",
    llm_billing: "Usa l'abbonamento Claude dell'atleta; il backend non fa chiamate LLM API.",
    safety_rules: [
      "Numeri prima delle parole: TSB/HRV/readiness/sessione.",
      "Le decisioni safety restano rule-based: HRV crash, illness_flag, injury_flag.",
      "Non scrivere su planned_sessions senza conferma esplicita dell'atleta.",
      "Per applicare modifiche usa commit_plan_change solo dopo 'ok', 'approvo' o equivalente.",
      "Se dati insufficienti o vecchi, dichiaralo e proponi il minimo intervento sicuro.",
    ],
    recommended_flow: [
      "Weekly review: get_weekly_context -> eventuale force_garmin_sync se dati vecchi -> proposta -> conferma -> commit_plan_change.",
      "Session analysis: get_session_review_context solo su richiesta o sessione anomala.",
      "Race briefing: get_race_context solo in race week o su richiesta.",
    ],
  };
}

async function getWeeklyContext(days: number, includeNextDays: number, env: Env) {
  days = clampInt(days, 1, 28);
  includeNextDays = clampInt(includeNextDays, 1, 21);

  const today = todayRomeISO();
  const since = daysAgoISO(days);
  const metricsSince = daysAgoISO(Math.max(days * 2, 14));
  const until = daysFromISO(includeNextDays);

  const [
    health,
    metrics,
    wellness,
    activities,
    subjective,
    plannedPast,
    plannedUpcoming,
    sessionAnalyses,
    modulations,
  ] = await Promise.all([
    getHealth(env),
    sb(env, `daily_metrics?date=gte.${metricsSince}&order=date.asc`),
    sb(env, `daily_wellness?date=gte.${metricsSince}&order=date.asc&select=date,hrv_rmssd,sleep_score,body_battery_min,body_battery_max,resting_hr,training_readiness_score,avg_sleep_stress`),
    sb(env, `activities?started_at=gte.${since}T00:00:00Z&order=started_at.desc&select=id,external_id,started_at,sport,duration_s,distance_m,avg_hr,max_hr,avg_power_w,np_w,avg_pace_s_per_km,tss,splits,weather`),
    sb(env, `subjective_log?logged_at=gte.${since}T00:00:00Z&order=logged_at.desc`),
    sb(env, `planned_sessions?planned_date=gte.${since}&planned_date=lt.${today}&order=planned_date.asc`),
    sb(env, `planned_sessions?planned_date=gte.${today}&planned_date=lte.${until}&order=planned_date.asc`),
    sb(env, `session_analyses?created_at=gte.${since}T00:00:00Z&order=created_at.desc&select=activity_id,analysis_text,suggested_actions,created_at,model_used,cost_usd`),
    sb(env, `plan_modulations?status=eq.proposed&order=proposed_at.desc&select=id,trigger_event,trigger_data,proposed_changes,status,proposed_at`),
  ]);

  return {
    generated_at: new Date().toISOString(),
    timezone: "Europe/Rome",
    period: { today, completed_since: since, upcoming_until: until },
    coach_protocol: coachProtocol(),
    sync_status: summarizeSync(health),
    health,
    daily_metrics: metrics,
    daily_wellness: wellness,
    completed_activities: activities,
    subjective_log: subjective,
    planned_past: plannedPast,
    planned_upcoming: plannedUpcoming,
    session_analyses: sessionAnalyses,
    open_modulations: modulations,
    review_instructions: [
      "Confronta planned_past vs completed_activities.",
      "Apri con TSB/CTL/HRV/readiness e dati soggettivi rilevanti.",
      "Formula diagnosi e proposta prossima settimana.",
      "Chiedi conferma prima di ogni commit_plan_change.",
    ],
  };
}

async function getRaceContext(raceDate: string | undefined, daysAhead: number, env: Env) {
  daysAhead = clampInt(daysAhead, 1, 180);
  const today = todayRomeISO();
  const until = raceDate || daysFromISO(daysAhead);
  const since28 = daysAgoISO(28);
  const since14 = daysAgoISO(14);

  let raceQuery = `planned_sessions?session_type=eq.race&planned_date=gte.${today}&planned_date=lte.${until}&order=planned_date.asc&limit=1`;
  if (raceDate) {
    raceQuery = `planned_sessions?session_type=eq.race&planned_date=eq.${raceDate}&limit=1`;
  }

  const raceRows = await sb(env, raceQuery);
  const race = raceRows?.[0] || null;
  const targetDate = race?.planned_date || raceDate || until;

  const [metrics, wellness, activities, subjective, planWindow] = await Promise.all([
    sb(env, `daily_metrics?date=gte.${since28}&order=date.asc`),
    sb(env, `daily_wellness?date=gte.${since28}&order=date.asc&select=date,hrv_rmssd,sleep_score,body_battery_min,body_battery_max,resting_hr,training_readiness_score,avg_sleep_stress`),
    sb(env, `activities?started_at=gte.${since28}T00:00:00Z&order=started_at.desc&select=id,external_id,started_at,sport,duration_s,distance_m,avg_hr,max_hr,avg_power_w,np_w,avg_pace_s_per_km,tss,splits,weather`),
    sb(env, `subjective_log?logged_at=gte.${since14}T00:00:00Z&order=logged_at.desc`),
    sb(env, `planned_sessions?planned_date=gte.${today}&planned_date=lte.${targetDate}&order=planned_date.asc`),
  ]);

  return {
    generated_at: new Date().toISOString(),
    timezone: "Europe/Rome",
    coach_protocol: coachProtocol(),
    race,
    target_date: targetDate,
    daily_metrics: metrics,
    daily_wellness: wellness,
    recent_activities: activities,
    subjective_log: subjective,
    plan_until_race: planWindow,
    race_briefing_instructions: [
      "Usa solo se race week o richiesta esplicita.",
      "Non dare diagnosi mediche o nutrizione specifica in grammi/calorie.",
      "Produci timeline, warm-up, pacing qualitativo, checklist, contingency e mental checkpoints.",
    ],
  };
}

async function getSessionReviewContext(activityId: string | undefined, historyDays: number, env: Env) {
  historyDays = clampInt(historyDays, 1, 90);
  const since = daysAgoISO(historyDays);

  let activityRows: any[];
  if (activityId) {
    const encoded = encodeURIComponent(activityId);
    activityRows = await sb(env, `activities?external_id=eq.${encoded}&limit=1`);
    if (activityRows.length === 0 && isUuid(activityId)) {
      activityRows = await sb(env, `activities?id=eq.${encoded}&limit=1`);
    }
  } else {
    activityRows = await sb(
      env,
      `activities?order=started_at.desc&limit=1&select=id,external_id,started_at,sport,duration_s,distance_m,avg_hr,max_hr,avg_power_w,np_w,avg_pace_s_per_km,tss,splits,weather`
    );
  }

  const activity = activityRows?.[0] || null;
  if (!activity) {
    return { status: "not_found", activity_id: activityId || null };
  }

  const activityDate = String(activity.started_at || "").slice(0, 10);
  const sport = activity.sport || "all";

  const [planned, metrics, subjective, sportHistory, analyses] = await Promise.all([
    sb(env, `planned_sessions?planned_date=eq.${activityDate}&sport=eq.${sport}`),
    sb(env, `daily_metrics?date=eq.${activityDate}&limit=1`),
    sb(env, `subjective_log?logged_at=gte.${daysAgoISO(3)}T00:00:00Z&order=logged_at.desc`),
    getActivityHistory(sport, historyDays, env),
    sb(env, `session_analyses?activity_id=eq.${encodeURIComponent(activity.external_id || activity.id)}&limit=1`),
  ]);

  return {
    generated_at: new Date().toISOString(),
    timezone: "Europe/Rome",
    coach_protocol: coachProtocol(),
    activity,
    planned_session: planned?.[0] || null,
    daily_metrics: metrics?.[0] || null,
    recent_subjective_log: subjective,
    same_sport_history: sportHistory,
    existing_analysis: analyses?.[0] || null,
    analysis_instructions: [
      "Analizza solo su richiesta esplicita o sessione anomala.",
      "Confronta attività con planned_session e storico stesso sport.",
      "Output breve: cosa è successo, segnale positivo/negativo, azione pratica.",
    ],
  };
}

async function getUpcomingPlan(days: number, env: Env) {
  days = clampInt(days, 1, 60);
  const today = todayRomeISO();
  const until = daysFromISO(days);
  return sb(env, `planned_sessions?planned_date=gte.${today}&planned_date=lte.${until}&order=planned_date.asc`);
}

async function getHealth(env: Env) {
  return sb(env, `health?select=component,last_success_at,failure_count,last_error&order=component.asc`);
}

function summarizeSync(health: any[]) {
  const garmin = health.find((row: any) => row.component === "garmin_sync");
  const last = garmin?.last_success_at ? new Date(garmin.last_success_at) : null;
  const ageMinutes = last ? Math.round((Date.now() - last.getTime()) / 60000) : null;
  return {
    garmin_last_success_at: garmin?.last_success_at || null,
    garmin_age_minutes: ageMinutes,
    is_fresh_for_weekly_review: ageMinutes !== null && ageMinutes < 60,
    recommendation: ageMinutes === null
      ? "unknown_sync_state"
      : ageMinutes > 60
        ? "call_force_garmin_sync_before_review"
        : "sync_fresh_proceed",
  };
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

async function getRecentMetrics(days: number, env: Env) {
  const since = daysAgoISO(days);
  return sb(env, `daily_metrics?date=gte.${since}&order=date.desc`);
}

async function getPlannedSession(date: string, env: Env) {
  return sb(env, `planned_sessions?planned_date=eq.${date}`);
}

async function getActivityHistory(sport: string, days: number, env: Env) {
  const since = daysAgoISO(days);
  let q = `activities?started_at=gte.${since}T00:00:00Z&order=started_at.desc&select=id,started_at,sport,duration_s,distance_m,avg_hr,avg_power_w,np_w,tss,rpe,notes`;
  if (sport !== "all") q += `&sport=eq.${sport}`;
  return sb(env, q);
}

async function queryLog(days: number, kind: string, env: Env) {
  const since = daysAgoISO(days);
  let q = `subjective_log?logged_at=gte.${since}T00:00:00Z&order=logged_at.desc`;
  if (kind !== "all") q += `&kind=eq.${kind}`;
  return sb(env, q);
}

async function proposePlan(args: any, env: Env) {
  // Importante: NON scrive. Restituisce proposta strutturata che l'atleta può
  // poi confermare via comando esplicito (es. via Telegram /commit o tramite
  // un altro tool dedicato `commit_plan_change` che richiede un proposal_id).
  return {
    status: "proposal",
    requires_confirmation: true,
    target_date: args.target_date,
    rationale: args.rationale,
    proposed_change: args.change,
    instructions:
      "Per applicare questa modifica, l'atleta deve confermare esplicitamente. " +
      "Modificare la tabella `planned_sessions` richiede un secondo passaggio.",
  };
}
async function commitPlanChange(args: any, env: Env): Promise<any> {
  const required = ["planned_date", "sport", "session_type", "duration_s", "description"];
  for (const k of required) {
    if (args[k] === undefined || args[k] === null) {
      throw new Error(`Missing required field: ${k}`);
    }
  }

  const validSports = ["swim", "bike", "run", "brick", "strength"];
  if (!validSports.includes(args.sport)) {
    throw new Error(`Invalid sport: ${args.sport}. Must be one of ${validSports.join(", ")}`);
  }

  // Upsert su (planned_date, sport): se esiste già una sessione per quel giorno/sport, viene aggiornata
  const payload: any = {
    planned_date: args.planned_date,
    sport: args.sport,
    session_type: args.session_type,
    duration_s: args.duration_s,
    description: args.description,
    status: "planned",
  };
  if (args.target_tss !== undefined) payload.target_tss = args.target_tss;
  if (args.target_zones !== undefined) payload.target_zones = args.target_zones;
  if (args.structured !== undefined) payload.structured = args.structured;
  if (args.mesocycle_id !== undefined) payload.mesocycle_id = args.mesocycle_id;
  if (args.calendar_event_id !== undefined) payload.calendar_event_id = args.calendar_event_id;

  // Cerca sessione esistente
  const existingResp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/planned_sessions?planned_date=eq.${args.planned_date}&sport=eq.${args.sport}`,
    {
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      },
    }
  );
  const existing = (await existingResp.json()) as any[];

  if (existing.length > 0) {
    // Update
    const id = existing[0].id;
    const updateResp = await fetch(
      `${env.SUPABASE_URL}/rest/v1/planned_sessions?id=eq.${id}`,
      {
        method: "PATCH",
        headers: {
          "apikey": env.SUPABASE_SERVICE_KEY,
          "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          "Content-Type": "application/json",
          "Prefer": "return=representation",
        },
        body: JSON.stringify(payload),
      }
    );
    if (!updateResp.ok) {
      throw new Error(`Update failed: ${updateResp.status} ${await updateResp.text()}`);
    }
    return {
      status: "updated",
      action: "Updated existing session",
      session_id: id,
      payload,
    };
  } else {
    // Insert
    const insertResp = await fetch(
      `${env.SUPABASE_URL}/rest/v1/planned_sessions`,
      {
        method: "POST",
        headers: {
          "apikey": env.SUPABASE_SERVICE_KEY,
          "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          "Content-Type": "application/json",
          "Prefer": "return=representation",
        },
        body: JSON.stringify(payload),
      }
    );
    if (!insertResp.ok) {
      throw new Error(`Insert failed: ${insertResp.status} ${await insertResp.text()}`);
    }
    const result = (await insertResp.json()) as any[];
    return {
      status: "created",
      action: "Created new planned session",
      session_id: result[0]?.id,
      payload,
    };
  }
}

// ============================================================================
// Force Garmin Sync — triggera ingest.yml via GitHub Actions API
// ============================================================================
async function forceGarminSync(env: Env): Promise<any> {
  // 1. Controlla freshness ultimo sync
  const healthRows = await sb(env, `health?component=eq.garmin_sync&select=last_success_at`);
  const lastSync = healthRows?.[0]?.last_success_at;
  const lastSyncDate = lastSync ? new Date(lastSync) : null;

  if (lastSyncDate) {
    const minutesAgo = Math.round((Date.now() - lastSyncDate.getTime()) / 60000);
    if (minutesAgo < 60) {
      return {
        status: "skipped",
        reason: `sync recent (${minutesAgo} minutes ago)`,
        last_sync: lastSync,
      };
    }
  }

  // 2. Triggera workflow via GitHub Actions API
  // Setup richiesto: PAT GitHub con scope `repo` + `workflow`
  // Configurare come secret Cloudflare Worker: wrangler secret put GH_PAT_TRIGGER
  const dispatchResp = await fetch(
    "https://api.github.com/repos/NicoRoger/triathlon-coach/actions/workflows/ingest.yml/dispatches",
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GH_PAT_TRIGGER}`,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "triathlon-coach-mcp",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );

  if (!dispatchResp.ok) {
    const errText = await dispatchResp.text();
    throw new Error(`GitHub dispatch failed: ${dispatchResp.status} ${errText}`);
  }

  // 3. Polling: attendi fino a 90s che health.last_success_at venga aggiornato
  const startTime = Date.now();
  const timeoutMs = 90_000;
  const pollIntervalMs = 10_000;
  const baselineSync = lastSync || "";

  while (Date.now() - startTime < timeoutMs) {
    await sleep(pollIntervalMs);
    const updated = await sb(env, `health?component=eq.garmin_sync&select=last_success_at`);
    const newSync = updated?.[0]?.last_success_at;
    if (newSync && newSync !== baselineSync) {
      return {
        status: "completed",
        duration_s: Math.round((Date.now() - startTime) / 1000),
        last_sync: newSync,
      };
    }
  }

  return {
    status: "timeout",
    warning: "sync triggered but not yet visible",
    duration_s: Math.round((Date.now() - startTime) / 1000),
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
