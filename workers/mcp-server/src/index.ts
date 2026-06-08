/**
 * MCP Server — Cloudflare Worker
 *
 * Esposto come custom connector in Claude.ai. Fornisce all'agente coach accesso
 * ai dati operativi (metriche, attività, log soggettivi) e la capacità di
 * PROPORRE modifiche al piano (mai scriverle senza conferma esplicita).
 *
 * Auth: OAuth 2.0 minimal (single-user) per compatibilità Claude.ai web.
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

// ============================================================================
// CORS
// ============================================================================
function corsHeaders(): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };
}

function jsonResponse(data: any, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

// ============================================================================
// Tools
// ============================================================================
const TOOLS = [
  {
    name: "get_weekly_context",
    description: "Contesto aggregato per weekly review da Claude web/mobile: health sync, metriche, wellness, attività, piano, debrief, analisi e modulazioni. Usalo come primo tool per 'fai la weekly review'.",
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
    description: "Contesto aggregato per race briefing: prossima gara pianificata, metriche recenti, attività, wellness, piano e log soggettivi. Usalo solo in race week o su richiesta gara.",
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
    description: "Contesto per analizzare una singola sessione su richiesta: attività, sessione pianificata, metriche del giorno, storico sport e debrief recenti.",
    inputSchema: {
      type: "object",
      properties: {
        activity_id: { type: "string", description: "ID interno o external_id attività. Se omesso usa l'ultima attività." },
        history_days: { type: "integer", default: 21, minimum: 1, maximum: 90 },
      },
    },
  },
  {
    name: "get_upcoming_plan",
    description: "Restituisce le sessioni pianificate dei prossimi N giorni.",
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
        change: { type: "object" },
      },
    },
  },
  {
    name: "commit_plan_change",
    description: "Scrive una sessione pianificata nel DB. Da chiamare SOLO dopo conferma esplicita dell'atleta.",
    inputSchema: {
      type: "object",
      required: ["planned_date", "sport", "session_type", "duration_s", "description"],
      properties: {
        planned_date: { type: "string", format: "date" },
        sport: { type: "string", enum: ["swim", "bike", "run", "brick", "strength"] },
        session_type: { type: "string" },
        duration_s: { type: "integer", minimum: 60 },
        target_tss: { type: "number" },
        target_zones: { type: "object" },
        description: { type: "string" },
        structured: { type: "object" },
        mesocycle_id: { type: "string" },
        calendar_event_id: { type: "string" },
      },
    },
  },
  {
    name: "get_physiology_zones",
    description: "Restituisce le zone fisiologiche attuali (FTP, soglia, CSS, LTHR, HRmax) per disciplina. Usalo per calibrare intensità e target nelle sessioni.",
    inputSchema: {
      type: "object",
      properties: {
        discipline: { type: "string", enum: ["swim", "bike", "run", "all"], default: "all" },
      },
    },
  },
  {
    name: "get_technique_history",
    description: "Storico analisi video tecniche per disciplina. Restituisce gli ultimi video caricati con analisi, sport, punti chiave e drill suggeriti.",
    inputSchema: {
      type: "object",
      properties: {
        sport: { type: "string", enum: ["swim", "bike", "run", "all"], default: "all" },
        days: { type: "integer", default: 90, minimum: 1, maximum: 365 },
      },
    },
  },
  {
    name: "force_garmin_sync",
    description: "Forza un sync Garmin triggerando il workflow ingest via GitHub Actions. Se l'ultimo sync è < 1 ora fa, restituisce 'skipped'.",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "commit_mesocycle",
    description: "Crea o aggiorna un mesociclo nel DB. Upsert per start_date: se esiste già un mesociclo con quella data di inizio, lo aggiorna. Da chiamare SOLO dopo conferma esplicita dell'atleta.",
    inputSchema: {
      type: "object",
      required: ["name", "phase", "start_date", "end_date"],
      properties: {
        name: { type: "string" },
        phase: { type: "string", enum: ["base", "build", "specific", "peak", "taper", "recovery"] },
        start_date: { type: "string", format: "date" },
        end_date: { type: "string", format: "date" },
        target_race_id: { type: "string" },
        weekly_pattern: { type: "object" },
        notes: { type: "string" },
        progression_plan: { type: "object", description: "JSONB: {run_threshold: {week1: '4x6min', week2: '5x6min', week3: '6x6min'}, ...}" },
      },
    },
  },
  {
    name: "update_constraint",
    description: "Marca un vincolo medico come risolto (resolved_at = now). Chiamare dopo valutazione clinica.",
    inputSchema: {
      type: "object",
      required: ["id"],
      properties: {
        id: { type: "string", description: "UUID del vincolo da risolvere" },
        resolved_at: { type: "string", format: "date-time", description: "Timestamp risoluzione (default: now)" },
      },
    },
  },
];

// ============================================================================
// OAuth helpers
// ============================================================================
function htmlPage(title: string, body: string): Response {
  return new Response(
    `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title>
    <style>
      body{font-family:sans-serif;max-width:480px;margin:60px auto;padding:20px;text-align:center}
      button{background:#0ea5e9;color:white;border:none;padding:12px 32px;border-radius:8px;font-size:16px;cursor:pointer}
      button:hover{background:#0284c7}
      h1{color:#1e293b}p{color:#64748b}
    </style>
    </head><body>${body}</body></html>`,
    { headers: { "Content-Type": "text/html", ...corsHeaders() } }
  );
}

// ============================================================================
// Main fetch handler
// ============================================================================
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // CORS preflight
    if (req.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    // ── OAuth: metadata discovery ──────────────────────────────────────────
    if (
      url.pathname === "/.well-known/oauth-authorization-server" ||
      url.pathname === "/.well-known/openid-configuration"
    ) {
      return jsonResponse({
        issuer: url.origin,
        authorization_endpoint: `${url.origin}/oauth/authorize`,
        token_endpoint: `${url.origin}/oauth/token`,
        response_types_supported: ["code"],
        grant_types_supported: ["authorization_code"],
        code_challenge_methods_supported: ["S256"],
      });
    }

    // ── OAuth: protected resource metadata (RFC 9396) ──────────────────────
    if (url.pathname === "/.well-known/oauth-protected-resource") {
      return jsonResponse({
        resource: url.origin,
        authorization_servers: [url.origin],
        bearer_methods_supported: ["header"],
        resource_documentation: `${url.origin}/`,
      });
    }

    // ── OAuth: authorization endpoint ─────────────────────────────────────
    if (url.pathname === "/oauth/authorize") {
      const redirectUri = url.searchParams.get("redirect_uri") || "";
      const state = url.searchParams.get("state") || "";
      const codeChallenge = url.searchParams.get("code_challenge") || "";

      const params = new URLSearchParams({
        redirect_uri: redirectUri,
        state,
        code_challenge: codeChallenge,
      }).toString();

      return htmlPage("Triathlon Coach — Autorizzazione", `
        <h1>🏊🚴🏃 Triathlon Coach AI</h1>
        <p>Claude.ai vuole accedere ai tuoi dati di allenamento.</p>
        <br>
        <form method="GET" action="/oauth/callback?${params}">
          <button type="submit">✅ Autorizza accesso</button>
        </form>
      `);
    }

    // ── OAuth: callback ────────────────────────────────────────────────────
    if (url.pathname === "/oauth/callback") {
      const redirectUri = url.searchParams.get("redirect_uri") || "";
      const state = url.searchParams.get("state") || "";

      // SECURITY: generate a short-lived HMAC-signed code so the token endpoint
      // can verify it was issued by this server (no KV storage required).
      const ts = Date.now().toString();
      const hmacKey = await crypto.subtle.importKey(
        "raw", new TextEncoder().encode(env.MCP_BEARER_TOKEN),
        { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
      );
      const sig = await crypto.subtle.sign("HMAC", hmacKey, new TextEncoder().encode(ts));
      const sigHex = Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, "0")).join("");
      const code = `${ts}.${sigHex}`;

      // Se redirect_uri è vuota o invalida, mostra pagina di successo
      if (!redirectUri) {
        return htmlPage("Autorizzazione completata", `
          <h1>✅ Autorizzazione completata</h1>
          <p>Puoi chiudere questa finestra e tornare su Claude.ai.</p>
        `);
      }

      try {
        const callbackUrl = new URL(redirectUri);
        callbackUrl.searchParams.set("code", code);
        if (state) callbackUrl.searchParams.set("state", state);
        return Response.redirect(callbackUrl.toString(), 302);
      } catch {
        return htmlPage("Autorizzazione completata", `
          <h1>✅ Autorizzazione completata</h1>
          <p>Puoi chiudere questa finestra e tornare su Claude.ai.</p>
          <p style="font-size:12px;color:#94a3b8">Redirect non disponibile: ${redirectUri}</p>
        `);
      }
    }

    // ── OAuth: token endpoint ──────────────────────────────────────────────
    if (url.pathname === "/oauth/token" && req.method === "POST") {
      // SECURITY: verify the code was signed by this server (HMAC-SHA256 via MCP_BEARER_TOKEN).
      // Codes expire after 5 minutes to limit the replay window.
      let body: Record<string, string> = {};
      try { body = Object.fromEntries(await req.formData()); } catch { /* empty body */ }
      const code = (body["code"] as string) || "";
      const dotIdx = code.indexOf(".");
      if (dotIdx < 1) {
        return new Response(JSON.stringify({ error: "invalid_grant" }), {
          status: 400, headers: { "Content-Type": "application/json", ...corsHeaders() },
        });
      }
      const ts = code.slice(0, dotIdx);
      const receivedSig = code.slice(dotIdx + 1);
      const tsNum = parseInt(ts, 10);
      if (!tsNum || Date.now() - tsNum > 5 * 60 * 1000) {
        return new Response(JSON.stringify({ error: "invalid_grant", error_description: "code expired or invalid" }), {
          status: 400, headers: { "Content-Type": "application/json", ...corsHeaders() },
        });
      }
      const hmacKey = await crypto.subtle.importKey(
        "raw", new TextEncoder().encode(env.MCP_BEARER_TOKEN),
        { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
      );
      const sig = await crypto.subtle.sign("HMAC", hmacKey, new TextEncoder().encode(ts));
      const expectedSig = Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, "0")).join("");
      if (receivedSig !== expectedSig) {
        return new Response(JSON.stringify({ error: "invalid_grant" }), {
          status: 400, headers: { "Content-Type": "application/json", ...corsHeaders() },
        });
      }
      return jsonResponse({ access_token: env.MCP_BEARER_TOKEN, token_type: "bearer", expires_in: 3600, scope: "mcp" });
    }

    // ── Dashboard data endpoint ────────────────────────────────────────────
    if (url.pathname === "/dashboard-data" && req.method === "GET") {
      const auth = req.headers.get("authorization") || "";
      if (auth !== `Bearer ${env.MCP_BEARER_TOKEN}`) {
        return new Response("Unauthorized", { status: 401, headers: corsHeaders() });
      }
      const data = await getDashboardData(env);
      return jsonResponse(data);
    }

    // ── MCP endpoint (root / oppure /mcp) ─────────────────────────────────
    const isMcpPath = url.pathname === "/" || url.pathname === "/mcp" || url.pathname === "";

    if (!isMcpPath) {
      return new Response("Not found", { status: 404, headers: corsHeaders() });
    }

    // GET sulla root: rispondi con info server (health check)
    if (req.method === "GET") {
      return jsonResponse({
        name: "triathlon-coach-mcp",
        version: "0.3.0",
        protocol: "MCP/2024-11-05",
        status: "ok",
      });
    }

    // Auth: bearer token obbligatorio per tutte le richieste MCP.
    // Claude.ai ottiene il token via /oauth/token dopo il flusso OAuth (callback HMAC-signed).
    // Claude Code usa il token diretto configurato come secret.
    const auth = req.headers.get("authorization") || "";
    const isBearerValid = auth === `Bearer ${env.MCP_BEARER_TOKEN}`;

    if (!isBearerValid) {
      return new Response("Unauthorized", { status: 401, headers: { ...corsHeaders(), "WWW-Authenticate": `Bearer realm="triathlon-coach", resource_metadata="${url.origin}/.well-known/oauth-protected-resource"` } });
    }

    if (req.method !== "POST") {
      return new Response("Method not allowed", { status: 405, headers: corsHeaders() });
    }

    let rpc: JsonRpcRequest;
    try {
      rpc = (await req.json()) as JsonRpcRequest;
    } catch {
      return new Response(
        JSON.stringify({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }),
        { status: 400, headers: { "Content-Type": "application/json", ...corsHeaders() } }
      );
    }
    const resp = await handleRpc(rpc, env);
    return new Response(JSON.stringify(resp), {
      headers: { "Content-Type": "application/json", ...corsHeaders() },
    });
  },
};

// ============================================================================
// RPC handler
// ============================================================================
async function handleRpc(rpc: JsonRpcRequest, env: Env): Promise<JsonRpcResponse> {
  try {
    if (rpc.method === "initialize") {
      return ok(rpc.id, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "triathlon-coach-mcp", version: "0.3.0" },
      });
    }
    if (rpc.method === "tools/list") {
      return ok(rpc.id, { tools: TOOLS });
    }
    if (rpc.method === "tools/call") {
      const params = rpc.params ?? {};
      const { name, arguments: args } = params;
      if (!name) return err(rpc.id, -32602, "Missing required field: params.name");
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
// Tool router
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
      return getPlannedSession(args.date || todayRomeISO(), env);
    case "get_activity_history":
      return getActivityHistory(args.sport || "all", args.days || 14, env);
    case "query_subjective_log":
      return queryLog(args.days || 7, args.kind || "all", env);
    case "propose_plan_change":
      return proposePlan(args);
    case "commit_plan_change":
      return commitPlanChange(args, env);
    case "get_physiology_zones":
      return getPhysiologyZones(args.discipline || "all", env);
    case "get_technique_history":
      return getTechniqueHistory(args.sport || "all", args.days || 90, env);
    case "force_garmin_sync":
      return forceGarminSync(env);
    case "commit_mesocycle":
      return commitMesocycle(args, env);
    case "update_constraint":
      return updateConstraint(args || {}, env);
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// ============================================================================
// Helpers
// ============================================================================
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

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

/** Validates that a value is a well-formed ISO date string (YYYY-MM-DD). */
function isDateString(v: unknown): v is string {
  return typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
}

const VALID_SPORTS = new Set(["swim", "bike", "run", "brick", "strength", "all"]);
const VALID_KINDS  = new Set(["all", "post_session", "illness", "injury", "evening_debrief", "free_note"]);

function deriveProgressionStep(mesocycle: any, today: string): any {
  if (!mesocycle || !mesocycle.progression_plan || !mesocycle.start_date) return null;
  const startDate = new Date(mesocycle.start_date);
  const todayDate = new Date(today);
  const weekNumber = Math.floor((todayDate.getTime() - startDate.getTime()) / (7 * 24 * 60 * 60 * 1000)) + 1;
  const plan = mesocycle.progression_plan;
  const result: any = {};
  for (const [sessionType, weeks] of Object.entries(plan as Record<string, any>)) {
    result[sessionType] = (weeks as any)[`week${weekNumber}`] || null;
  }
  return { week_number: weekNumber, steps: result };
}

function coachProtocol() {
  return {
    interface: "Claude web/mobile via remote MCP",
    llm_billing: "Usa l'abbonamento Claude dell'atleta; il backend non fa chiamate LLM API.",
    safety_rules: [
      "Numeri prima delle parole: TSB/HRV/readiness/sessione.",
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

function summarizeSync(health: any[]) {
  const garmin = health.find((row: any) => row.component === "garmin_sync");
  const last = garmin?.last_success_at ? new Date(garmin.last_success_at) : null;
  const ageMinutes = last ? Math.round((Date.now() - last.getTime()) / 60000) : null;
  return {
    garmin_last_success_at: garmin?.last_success_at || null,
    garmin_age_minutes: ageMinutes,
    is_fresh_for_weekly_review: ageMinutes !== null && ageMinutes < 60,
    recommendation:
      ageMinutes === null
        ? "unknown_sync_state"
        : ageMinutes > 60
          ? "call_force_garmin_sync_before_review"
          : "sync_fresh_proceed",
  };
}

// ============================================================================
// Tool implementations — aggregated contexts
// ============================================================================
async function getWeeklyContext(days: number, includeNextDays: number, env: Env) {
  days = clampInt(days, 1, 28);
  includeNextDays = clampInt(includeNextDays, 1, 21);

  const today = todayRomeISO();
  const since = daysAgoISO(days);
  const metricsSince = daysAgoISO(Math.max(days * 2, 14));
  const until = daysFromISO(includeNextDays);

  const [health, metrics, wellness, activities, subjective, plannedPast, plannedUpcoming, sessionAnalyses, modulations, mesocycles, races, constraints] =
    await Promise.all([
      getHealth(env),
      sb(env, `daily_metrics?date=gte.${metricsSince}&order=date.asc&select=date,ctl,atl,tsb,daily_tss,hrv_z_score,readiness_score,readiness_label,flags,garmin_training_readiness`),
      sb(env, `daily_wellness?date=gte.${metricsSince}&order=date.asc&select=date,hrv_rmssd,sleep_score,body_battery_min,body_battery_max,resting_hr,training_readiness_score,avg_sleep_stress`),
      sb(env, `activities?started_at=gte.${since}T00:00:00Z&order=started_at.desc&select=external_id,started_at,sport,duration_s,distance_m,avg_hr,max_hr,avg_power_w,np_w,avg_pace_s_per_km,tss`),
      sb(env, `subjective_log?logged_at=gte.${since}T00:00:00Z&order=logged_at.desc&select=logged_at,kind,rpe,sleep_quality,motivation,soreness,illness_flag,injury_flag,injury_details,raw_text`),
      sb(env, `planned_sessions?planned_date=gte.${since}&planned_date=lt.${today}&order=planned_date.asc`),
      sb(env, `planned_sessions?planned_date=gte.${today}&planned_date=lte.${until}&order=planned_date.asc`),
      sb(env, `session_analyses?created_at=gte.${since}T00:00:00Z&order=created_at.desc&select=activity_id,analysis_text,created_at`),
      sb(env, `plan_modulations?status=eq.proposed&order=proposed_at.desc&select=id,trigger_event,proposed_changes,status,proposed_at`),
      sb(env, `mesocycles?start_date=lte.${today}&end_date=gte.${today}&order=start_date.desc&limit=1`),
      sb(env, `races?race_date=gte.${today}&order=race_date.asc&select=id,name,race_date,priority,distance,location`),
      sb(env, `active_constraints?resolved_at=is.null&order=created_at.asc`).catch(() => []),
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
    active_mesocycle: mesocycles?.[0] || null,
    upcoming_races: races || [],
    active_constraints: constraints || [],
    current_progression_step: deriveProgressionStep(mesocycles?.[0] || null, today),
    review_instructions: [
      "Confronta planned_past vs completed_activities.",
      "Apri con HRV/readiness/carico e dati soggettivi rilevanti.",
      "Formula diagnosi e proposta prossima settimana.",
      "Chiedi conferma prima di ogni commit_plan_change.",
    ],
  };
}

async function getRaceContext(raceDate: string | undefined, daysAhead: number, env: Env) {
  if (raceDate !== undefined && !isDateString(raceDate)) {
    throw new Error(`Invalid race_date format: ${raceDate}. Expected YYYY-MM-DD.`);
  }
  daysAhead = clampInt(daysAhead, 1, 180);
  const today = todayRomeISO();
  const until = raceDate || daysFromISO(daysAhead);
  const since28 = daysAgoISO(28);
  const since14 = daysAgoISO(14);

  let raceQuery = `races?race_date=gte.${today}&race_date=lte.${until}&order=race_date.asc&limit=1`;
  if (raceDate) raceQuery = `races?race_date=eq.${raceDate}&limit=1`;

  const raceRows = await sb(env, raceQuery);
  const race = raceRows?.[0] || null;
  const targetDate = race?.race_date || raceDate || until;

  const [metrics, wellness, activities, subjective, planWindow] = await Promise.all([
    sb(env, `daily_metrics?date=gte.${since28}&order=date.asc`),
    sb(env, `daily_wellness?date=gte.${since28}&order=date.asc&select=date,hrv_rmssd,sleep_score,body_battery_min,body_battery_max,resting_hr,training_readiness_score`),
    sb(env, `activities?started_at=gte.${since28}T00:00:00Z&order=started_at.desc&select=id,external_id,started_at,sport,duration_s,distance_m,avg_hr,tss`),
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
  };
}

async function getSessionReviewContext(activityId: string | undefined, historyDays: number, env: Env) {
  historyDays = clampInt(historyDays, 1, 90);

  let activityRows: any[];
  if (activityId) {
    const encoded = encodeURIComponent(activityId);
    activityRows = await sb(env, `activities?external_id=eq.${encoded}&limit=1`);
    if (activityRows.length === 0 && isUuid(activityId)) {
      activityRows = await sb(env, `activities?id=eq.${encoded}&limit=1`);
    }
  } else {
    activityRows = await sb(env, `activities?order=started_at.desc&limit=1`);
  }

  const activity = activityRows?.[0] || null;
  if (!activity) return { status: "not_found", activity_id: activityId || null };

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
    coach_protocol: coachProtocol(),
    activity,
    planned_session: planned?.[0] || null,
    daily_metrics: metrics?.[0] || null,
    recent_subjective_log: subjective,
    same_sport_history: sportHistory,
    existing_analysis: analyses?.[0] || null,
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

async function getRecentMetrics(days: number, env: Env) {
  const since = daysAgoISO(days);
  return sb(env, `daily_metrics?date=gte.${since}&order=date.desc`);
}

async function getPlannedSession(date: string, env: Env) {
  if (!isDateString(date)) throw new Error(`Invalid date format: ${date}. Expected YYYY-MM-DD.`);
  return sb(env, `planned_sessions?planned_date=eq.${date}`);
}

async function getActivityHistory(sport: string, days: number, env: Env) {
  if (!VALID_SPORTS.has(sport)) throw new Error(`Invalid sport: ${sport}`);
  const since = daysAgoISO(days);
  let q = `activities?started_at=gte.${since}T00:00:00Z&order=started_at.desc&select=id,started_at,sport,duration_s,distance_m,avg_hr,avg_power_w,np_w,tss,rpe,notes`;
  if (sport !== "all") q += `&sport=eq.${sport}`;
  return sb(env, q);
}

async function queryLog(days: number, kind: string, env: Env) {
  if (!VALID_KINDS.has(kind)) throw new Error(`Invalid log kind: ${kind}`);
  const since = daysAgoISO(days);
  let q = `subjective_log?logged_at=gte.${since}T00:00:00Z&order=logged_at.desc`;
  if (kind !== "all") q += `&kind=eq.${kind}`;
  return sb(env, q);
}

function proposePlan(args: any) {
  return {
    status: "proposal",
    requires_confirmation: true,
    target_date: args.target_date,
    rationale: args.rationale,
    proposed_change: args.change,
    instructions: "Per applicare questa modifica, l'atleta deve confermare esplicitamente con commit_plan_change.",
  };
}

async function commitPlanChange(args: any, env: Env): Promise<any> {
  const required = ["planned_date", "sport", "session_type", "duration_s", "description"];
  for (const k of required) {
    if (args[k] === undefined || args[k] === null) throw new Error(`Missing required field: ${k}`);
  }

  const validSports = ["swim", "bike", "run", "brick", "strength"];
  if (!validSports.includes(args.sport)) {
    throw new Error(`Invalid sport: ${args.sport}. Must be one of ${validSports.join(", ")}`);
  }
  if (!isDateString(args.planned_date)) {
    throw new Error(`Invalid planned_date format: ${args.planned_date}. Expected YYYY-MM-DD.`);
  }

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

  const existingResp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/planned_sessions?planned_date=eq.${args.planned_date}&sport=eq.${args.sport}`,
    { headers: { "apikey": env.SUPABASE_SERVICE_KEY, "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}` } }
  );
  if (!existingResp.ok) throw new Error(`Supabase lookup failed: ${existingResp.status} ${await existingResp.text()}`);
  const existing = (await existingResp.json()) as any[];

  if (existing.length > 0) {
    const id = existing[0].id;
    const updateResp = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions?id=eq.${id}`, {
      method: "PATCH",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
      },
      body: JSON.stringify(payload),
    });
    if (!updateResp.ok) throw new Error(`Update failed: ${updateResp.status} ${await updateResp.text()}`);
    return { status: "updated", session_id: id, payload };
  } else {
    const insertResp = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions`, {
      method: "POST",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
      },
      body: JSON.stringify(payload),
    });
    if (!insertResp.ok) throw new Error(`Insert failed: ${insertResp.status} ${await insertResp.text()}`);
    const result = (await insertResp.json()) as any[];
    return { status: "created", session_id: result[0]?.id, payload };
  }
}

// ============================================================================
// Physiology Zones
// ============================================================================
async function getPhysiologyZones(discipline: string, env: Env) {
  const today = todayRomeISO();
  let q = `physiology_zones?or=(valid_to.is.null,valid_to.gte.${today})&valid_from=lte.${today}&order=valid_from.desc`;
  if (discipline !== "all") q += `&discipline=eq.${discipline}`;
  const rows = await sb(env, q);

  const seen = new Set<string>();
  const current: any[] = [];
  for (const row of rows) {
    if (!seen.has(row.discipline)) {
      seen.add(row.discipline);
      current.push(row);
    }
  }

  // Force both dates to UTC midnight so age_days is never off by 1 due to
  // Rome timezone offset (UTC+1/+2). todayRomeISO() returns "YYYY-MM-DD" in
  // local Rome time; appending "T00:00:00Z" pins it to UTC midnight consistently.
  const todayUTC = new Date(todayRomeISO() + "T00:00:00Z");
  for (const zone of current) {
    if (zone.valid_from) {
      const validFromUTC = new Date(zone.valid_from + "T00:00:00Z");
      const diffMs = todayUTC.getTime() - validFromUTC.getTime();
      zone.age_days = Math.max(0, Math.floor(diffMs / 86400000));
    } else {
      zone.age_days = null;
    }
  }

  return {
    generated_at: new Date().toISOString(),
    zones: current,
    note: current.length === 0
      ? "Nessuna zona fisiologica registrata. Suggerisci un test FTP/soglia/CSS."
      : undefined,
  };
}

// ============================================================================
// Technique History (Blocco 2.3)
// ============================================================================
async function getTechniqueHistory(sport: string, days: number, env: Env) {
  const since = daysAgoISO(days);
  let q = `subjective_log?kind=eq.video_analysis&logged_at=gte.${since}&order=logged_at.desc&limit=20`;
  const rows = await sb(env, q);

  let filtered = rows;
  if (sport !== "all") {
    filtered = rows.filter((r: any) => r.parsed_data?.sport === sport);
  }

  return {
    generated_at: new Date().toISOString(),
    sport_filter: sport,
    days,
    analyses: filtered.map((r: any) => ({
      date: r.logged_at?.slice(0, 10),
      sport: r.parsed_data?.sport || "unknown",
      raw_text: r.raw_text?.slice(0, 500),
      file_id: r.parsed_data?.file_id,
      analysis: r.parsed_data?.analysis,
      drill_suggestions: r.parsed_data?.drill_suggestions,
    })),
    count: filtered.length,
    note: filtered.length === 0
      ? `Nessuna analisi video trovata${sport !== "all" ? ` per ${sport}` : ""} negli ultimi ${days} giorni.`
      : undefined,
  };
}

// ============================================================================
// Mesocycles
// ============================================================================
async function commitMesocycle(args: any, env: Env): Promise<any> {
  const required = ["name", "phase", "start_date", "end_date"];
  for (const k of required) {
    if (args[k] === undefined || args[k] === null) throw new Error(`Missing required field: ${k}`);
  }

  const validPhases = ["base", "build", "specific", "peak", "taper", "recovery"];
  if (!validPhases.includes(args.phase)) {
    throw new Error(`Invalid phase: ${args.phase}. Must be one of ${validPhases.join(", ")}`);
  }
  if (!isDateString(args.start_date)) {
    throw new Error(`Invalid start_date format: ${args.start_date}. Expected YYYY-MM-DD.`);
  }
  if (!isDateString(args.end_date)) {
    throw new Error(`Invalid end_date format: ${args.end_date}. Expected YYYY-MM-DD.`);
  }

  const payload: any = {
    name: args.name,
    phase: args.phase,
    start_date: args.start_date,
    end_date: args.end_date,
  };
  if (args.target_race_id !== undefined) payload.target_race_id = args.target_race_id;
  if (args.weekly_pattern !== undefined) payload.weekly_pattern = args.weekly_pattern;
  if (args.notes !== undefined) payload.notes = args.notes;
  if (args.progression_plan !== undefined) payload.progression_plan = args.progression_plan;

  const existingResp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/mesocycles?start_date=eq.${args.start_date}`,
    { headers: { "apikey": env.SUPABASE_SERVICE_KEY, "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}` } }
  );
  if (!existingResp.ok) throw new Error(`Supabase lookup failed: ${existingResp.status} ${await existingResp.text()}`);
  const existing = (await existingResp.json()) as any[];

  if (existing.length > 1) {
    throw new Error(`Ambiguous: ${existing.length} mesocycles found for start_date ${args.start_date}. Resolve duplicates before updating.`);
  }

  if (existing.length > 0) {
    const id = existing[0].id;
    const updateResp = await fetch(`${env.SUPABASE_URL}/rest/v1/mesocycles?id=eq.${id}`, {
      method: "PATCH",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
      },
      body: JSON.stringify(payload),
    });
    if (!updateResp.ok) throw new Error(`Update failed: ${updateResp.status} ${await updateResp.text()}`);
    return { status: "updated", mesocycle_id: id, payload };
  } else {
    const insertResp = await fetch(`${env.SUPABASE_URL}/rest/v1/mesocycles`, {
      method: "POST",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
      },
      body: JSON.stringify(payload),
    });
    if (!insertResp.ok) throw new Error(`Insert failed: ${insertResp.status} ${await insertResp.text()}`);
    const result = (await insertResp.json()) as any[];
    return { status: "created", mesocycle_id: result[0]?.id, payload };
  }
}

// ============================================================================
// Update Constraint (D-14)
// ============================================================================
async function updateConstraint(args: any, env: Env): Promise<any> {
  if (!args.id || !isUuid(args.id)) {
    throw new Error(`Invalid constraint id: must be a valid UUID`);
  }
  const resolvedAt = args.resolved_at || new Date().toISOString();
  const updateResp = await fetch(`${env.SUPABASE_URL}/rest/v1/active_constraints?id=eq.${args.id}`, {
    method: "PATCH",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=representation",
    },
    body: JSON.stringify({ resolved_at: resolvedAt }),
  });
  if (!updateResp.ok) throw new Error(`Update failed: ${updateResp.status} ${await updateResp.text()}`);
  return { status: "resolved", id: args.id, resolved_at: resolvedAt };
}

// ============================================================================
// Force Garmin Sync
// ============================================================================
async function forceGarminSync(env: Env): Promise<any> {
  const healthRows = await sb(env, `health?component=eq.garmin_sync&select=last_success_at`);
  const lastSync = healthRows?.[0]?.last_success_at;
  const lastSyncDate = lastSync ? new Date(lastSync) : null;

  if (lastSyncDate) {
    const minutesAgo = Math.round((Date.now() - lastSyncDate.getTime()) / 60000);
    if (minutesAgo < 60) {
      return { status: "skipped", reason: `sync recent (${minutesAgo} minutes ago)`, last_sync: lastSync };
    }
  }

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
    throw new Error(`GitHub dispatch failed: ${dispatchResp.status} ${await dispatchResp.text()}`);
  }

  // IMPORTANT: Do NOT poll here. Cloudflare Workers have a 30-second wall-clock
  // limit (paid) and the GitHub Actions ingest workflow takes 3-5 minutes.
  // A 90-second polling loop would always be terminated by the runtime mid-loop,
  // returning an opaque error to the caller. Instead, return immediately after
  // dispatching. The caller can check sync freshness via get_weekly_context.sync_status.
  return {
    status: "triggered",
    message: "Sync job dispatched. Check sync_status via get_weekly_context after ~3-5 minutes.",
    last_sync_before_trigger: lastSync || null,
  };
}

// ============================================================================
// Dashboard Data
// ============================================================================
async function getDashboardData(env: Env) {
  const today = todayRomeISO();
  const days30ago = daysAgoISO(30);
  const days90ago = daysAgoISO(90);
  const weeks4ago = daysAgoISO(28);
  const weeks16ahead = daysFromISO(112);

  const [metrics, wellness, plannedSessions, activities, mesocycles, races, zonesRaw] =
    await Promise.all([
      sb(env, `daily_metrics?date=gte.${days90ago}&order=date.asc&select=date,ctl,atl,tsb,daily_tss,hrv_z_score,readiness_score,readiness_label,flags`),
      sb(env, `daily_wellness?date=gte.${days30ago}&order=date.asc&select=date,hrv_rmssd,sleep_score,body_battery_max,resting_hr`),
      sb(env, `planned_sessions?planned_date=gte.${weeks4ago}&planned_date=lte.${weeks16ahead}&order=planned_date.asc&select=planned_date,sport,session_type,duration_s,target_tss,description`),
      sb(env, `activities?started_at=gte.${weeks4ago}T00:00:00Z&order=started_at.asc&select=started_at,sport`),
      sb(env, `mesocycles?order=start_date.asc&select=id,name,phase,start_date,end_date,notes`),
      sb(env, `races?race_date=gte.${today}&order=race_date.asc&select=name,race_date,priority,distance`),
      sb(env, `physiology_zones?or=(valid_to.is.null,valid_to.gte.${today})&valid_from=lte.${today}&order=valid_from.desc&select=discipline,ftp_w,threshold_pace_s_per_km,css_pace_s_per_100m,lthr`),
    ]);

  // Deduplicate zones: one per discipline (most recent)
  const seen = new Set<string>();
  const zones = (zonesRaw || []).filter((z: any) => {
    if (seen.has(z.discipline)) return false;
    seen.add(z.discipline);
    return true;
  });

  return {
    generated_at: new Date().toISOString(),
    today,
    metrics: metrics || [],
    wellness: wellness || [],
    planned_sessions: plannedSessions || [],
    activities: activities || [],
    mesocycles: mesocycles || [],
    races: races || [],
    zones,
    latest_metrics: (metrics || []).at(-1) || null,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}