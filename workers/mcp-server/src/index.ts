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

function daysAgoISO(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().split("T")[0];
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