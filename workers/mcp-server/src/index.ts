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
  GH_REPO?: string;
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
        status: { type: "string", enum: ["planned", "completed", "skipped", "modified", "cancelled"], description: "Default 'planned'. Per cancellare preferisci il tool delete_session." },
        mesocycle_id: { type: "string", description: "Opzionale: se omesso viene agganciato automaticamente il mesociclo attivo per quella data." },
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
    description: "Aggiorna un vincolo medico attivo. Può marcare come risolto (resolved_at), aggiornare description, severity, symptom_status (symptomatic→asymptomatic→recovering) o aggiungere una nota. Ogni modifica è loggata in history.",
    inputSchema: {
      type: "object",
      required: ["id"],
      properties: {
        id: { type: "string", description: "UUID del vincolo" },
        resolved_at: { type: "string", format: "date-time", description: "Timestamp risoluzione. Imposta per chiudere il vincolo." },
        description: { type: "string", description: "Aggiorna la descrizione del vincolo (es. cambia da 'sintomatica' ad 'asintomatica')" },
        severity: { type: "string", enum: ["low", "medium", "high", "critical"], description: "Aggiorna la severità" },
        symptom_status: { type: "string", enum: ["symptomatic", "asymptomatic", "recovering"], description: "Stato sintomatologico corrente" },
        note: { type: "string", description: "Nota libera sull'aggiornamento (es. 'RM di controllo ok')" },
      },
    },
  },
  {
    name: "create_constraint",
    description: "Crea un nuovo vincolo medico/tattico attivo. Da usare quando emerge un nuovo infortunio, limitazione o vincolo contestuale. Da chiamare SOLO dopo conferma dell'atleta.",
    inputSchema: {
      type: "object",
      required: ["type", "discipline", "description", "severity"],
      properties: {
        type: { type: "string", enum: ["injury", "medical", "tactical"] },
        discipline: { type: "string", enum: ["swim", "bike", "run", "all", "strength"] },
        description: { type: "string", description: "Descrizione dettagliata del vincolo e delle sue implicazioni pratiche" },
        severity: { type: "string", enum: ["low", "medium", "high", "critical"] },
        symptom_status: { type: "string", enum: ["symptomatic", "asymptomatic", "recovering"] },
        note: { type: "string" },
      },
    },
  },
  {
    name: "delete_planned_session",
    description: "Soft-cancella una sessione pianificata (status→'cancelled'). Restituisce calendar_event_id se presente per cleanup GCal separato. Da chiamare SOLO dopo conferma esplicita dell'atleta.",
    inputSchema: {
      type: "object",
      required: ["id"],
      properties: {
        id: { type: "string", description: "UUID della sessione in planned_sessions" },
      },
    },
  },
  {
    name: "update_planned_session",
    description: "Aggiorna campi di una sessione pianificata esistente (PATCH parziale). Usa per spostare data, modificare intensità/descrizione. Vietato: id, created_at, source. Da chiamare SOLO dopo conferma esplicita dell'atleta.",
    inputSchema: {
      type: "object",
      required: ["id", "fields"],
      properties: {
        id: { type: "string", description: "UUID della sessione" },
        fields: {
          type: "object",
          description: "Campi da aggiornare (parziale). Vietati: id, created_at, source.",
          properties: {
            planned_date: { type: "string", format: "date" },
            sport: { type: "string", enum: ["swim", "bike", "run", "brick", "strength"] },
            session_type: { type: "string" },
            description: { type: "string" },
            duration_s: { type: "integer" },
            target_tss: { type: "number" },
            structured: { type: "object" },
            status: { type: "string", enum: ["planned", "completed", "skipped", "cancelled"] },
            calendar_event_id: { type: "string" },
          },
        },
      },
    },
  },
  {
    name: "list_pending_modulations",
    description: "Lista le modulazioni in attesa (status='proposed'), raggruppate per source (auto=pipeline vs coach=decisione esplicita). Default: solo non scadute/future.",
    inputSchema: {
      type: "object",
      properties: {
        include_past: { type: "boolean", default: false, description: "Se true, include anche modulazioni con session_date nel passato" },
      },
    },
  },
  {
    name: "dismiss_modulations",
    description: "Rigetta in blocco modulazioni obsolete (status→'dismissed'). Usa dismiss_all_past=true per pulire tutte le stantie. source_filter filtra per origine: 'auto' (pipeline), 'coach', 'all'.",
    inputSchema: {
      type: "object",
      properties: {
        ids: { type: "array", items: { type: "string" }, description: "Lista di UUID specifici da rigettare" },
        dismiss_all_past: { type: "boolean", description: "Se true, rigetta tutte le 'proposed' con session_date < oggi" },
        source_filter: { type: "string", enum: ["auto", "coach", "all"], default: "all" },
      },
    },
  },
  {
    name: "accept_modulation",
    description: "Accetta una modulazione e la applica al piano (scrive su planned_sessions). Da chiamare SOLO dopo conferma esplicita dell'atleta.",
    inputSchema: {
      type: "object",
      required: ["id"],
      properties: {
        id: { type: "string", description: "UUID della modulazione da accettare" },
      },
    },
  },
  {
    name: "refute_belief",
    description: "Refuta una belief dell'atleta: riduce la confidence, la flagga come inaffidabile con una motivazione. Usare quando una belief è costruita su dati noti come falsati (es. HR nuoto, warm-down mal classificato).",
    inputSchema: {
      type: "object",
      required: ["belief_key", "reason"],
      properties: {
        belief_key: { type: "string", description: "Chiave univoca della belief (es. 'swim_hr_compliance')" },
        reason: { type: "string", description: "Motivazione della refutazione (es. 'HR pool inaffidabile: dati senza fascia toracica')" },
        evidence_source: { type: "string", description: "Fonte dell'evidenza contraddittoria (default: 'coach_refutation')" },
      },
    },
  },
  {
    name: "list_beliefs",
    description: "Lista le belief attive dell'atleta con confidence, status e metadati fonte. Mostra separatamente le belief flaggate come inaffidabili.",
    inputSchema: {
      type: "object",
      properties: {
        min_status: { type: "string", enum: ["hypothesis", "weak_belief", "validated_belief", "strong_belief"], default: "weak_belief" },
        include_flagged: { type: "boolean", default: true, description: "Se true, include anche le belief flaggate (inaffidabili)" },
        category: { type: "string", description: "Filtra per categoria (es. 'swim', 'bike', 'recovery')" },
      },
    },
  },
  {
    name: "commit_physiology_zones",
    description: "Salva/aggiorna le zone fisiologiche di una disciplina (FTP bici, soglia corsa, CSS nuoto, LTHR). Da chiamare SOLO dopo conferma dell'atleta. IMPORTANTE: l'atleta NON ha wattmetro -> per la bici usa 'lthr' (soglia a frequenza cardiaca), non 'ftp_w'. Fornisci almeno uno tra ftp_w / threshold_pace_s_per_km / css_pace_s_per_100m / lthr, piu' l'oggetto 'zones' gia' calcolato. Tipicamente preceduto da get_session_review_context per leggere gli split del test.",
    inputSchema: {
      type: "object",
      required: ["discipline", "method"],
      properties: {
        discipline: { type: "string", enum: ["swim", "bike", "run"] },
        valid_from: { type: "string", format: "date" },
        ftp_w: { type: "number" },
        threshold_pace_s_per_km: { type: "number" },
        css_pace_s_per_100m: { type: "number" },
        lthr: { type: "integer" },
        hr_max: { type: "integer" },
        zones: { type: "object" },
        method: { type: "string" },
        test_activity_id: { type: "string" },
        notes: { type: "string" },
      },
    },
  },
  {
    name: "delete_session",
    description: "Cancella una sessione pianificata. Identifica la sessione per session_id (preferito) oppure per date+sport. Default: cancellazione soft (status='cancelled', resta nello storico ma sparisce dal piano). Usa hard=true SOLO per duplicati/errori da rimuovere davvero (es. una sessione fantasma creata per sbaglio). Restituisce il calendar_event_id della sessione: se presente, rimuovi tu l'evento da Google Calendar con gcal:delete_event. Da chiamare SOLO dopo conferma esplicita dell'atleta.",
    inputSchema: {
      type: "object",
      properties: {
        session_id: { type: "string", description: "ID della sessione (preferito se lo conosci)" },
        date: { type: "string", format: "date", description: "Data della sessione (usa con sport se non hai session_id)" },
        sport: { type: "string", enum: ["swim", "bike", "run", "brick", "strength"] },
        hard: { type: "boolean", default: false, description: "true = elimina la riga dal DB (per duplicati/errori); false = soft-cancel" },
      },
    },
  },
  {
    name: "reschedule_session",
    description: "Sposta una sessione pianificata esistente a una nuova data (e opzionalmente nuovo sport), mantenendo descrizione, TSS, zone, struttura e calendar_event_id. Identifica la sessione per session_id (preferito) o date+sport. Se la data/sport di destinazione e' gia' occupata da un'altra sessione attiva, restituisce status='conflict' senza modificare nulla: in quel caso decidi con l'atleta se cancellarla prima. Restituisce il calendar_event_id: se presente, aggiorna tu l'evento su Google Calendar con la nuova data. Da chiamare SOLO dopo conferma esplicita dell'atleta.",
    inputSchema: {
      type: "object",
      required: ["new_date"],
      properties: {
        session_id: { type: "string", description: "ID della sessione da spostare (preferito)" },
        date: { type: "string", format: "date", description: "Data attuale (usa con sport se non hai session_id)" },
        sport: { type: "string", enum: ["swim", "bike", "run", "brick", "strength"] },
        new_date: { type: "string", format: "date", description: "Nuova data di destinazione" },
        new_sport: { type: "string", enum: ["swim", "bike", "run", "brick", "strength"], description: "Opzionale: nuovo sport se cambia" },
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

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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
        registration_endpoint: `${url.origin}/oauth/register`,
        response_types_supported: ["code"],
        grant_types_supported: ["authorization_code"],
        code_challenge_methods_supported: [],
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
    // FIX: auto-submit the form via JS so Claude.ai's OAuth popup completes
    // without requiring manual user interaction. The button remains as fallback
    // if JS is disabled.
    if (url.pathname === "/oauth/authorize") {
      const redirectUri = url.searchParams.get("redirect_uri") || "";
      const state = url.searchParams.get("state") || "";
      const codeChallenge = url.searchParams.get("code_challenge") || "";

      return htmlPage("Triathlon Coach — Autorizzazione", `
        <h1>🏊🚴🏃 Triathlon Coach AI</h1>
        <p>Autorizzazione in corso...</p>
        <form id="f" method="GET" action="/oauth/callback">
          <input type="hidden" name="redirect_uri" value="${escapeHtml(redirectUri)}">
          <input type="hidden" name="state" value="${escapeHtml(state)}">
          <input type="hidden" name="code_challenge" value="${escapeHtml(codeChallenge)}">
          <button type="submit">✅ Autorizza accesso</button>
        </form>
        <script>document.getElementById('f').submit();</script>
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
          <p style="font-size:12px;color:#94a3b8">Redirect non disponibile: ${escapeHtml(redirectUri)}</p>
        `);
      }
    }

    // ── OAuth: dynamic client registration (RFC 7591) ─────────────────────
    // Single-athlete system: accept any registration, return a stable client_id.
    // We don't validate client_id during the auth flow (PKCE-only), so no KV needed.
    if (url.pathname === "/oauth/register" && req.method === "POST") {
      let body: Record<string, unknown> = {};
      try { body = await req.json(); } catch { /* empty body */ }
      const redirectUris: string[] = Array.isArray(body["redirect_uris"])
        ? (body["redirect_uris"] as string[])
        : [];
      return new Response(JSON.stringify({
        client_id: "claude-ai",
        client_id_issued_at: Math.floor(Date.now() / 1000),
        redirect_uris: redirectUris,
        grant_types: ["authorization_code"],
        response_types: ["code"],
        token_endpoint_auth_method: "none",
      }), { status: 201, headers: { "Content-Type": "application/json", ...corsHeaders() } });
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
      const tsNum = Number(ts);
      if (!Number.isFinite(tsNum) || tsNum <= 0 || Date.now() - tsNum > 5 * 60 * 1000) {
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
    case "delete_session":
      return deleteSession(args, env);
    case "reschedule_session":
      return rescheduleSession(args, env);
    case "get_physiology_zones":
      return getPhysiologyZones(args.discipline || "all", env);
    case "get_technique_history":
      return getTechniqueHistory(args.sport || "all", args.days || 90, env);
    case "force_garmin_sync":
      return forceGarminSync(env);
    case "commit_mesocycle":
      return commitMesocycle(args, env);
    case "commit_physiology_zones":
      return commitPhysiologyZones(args, env);
    case "update_constraint":
      return updateConstraint(args || {}, env);
    case "delete_planned_session":
      return deletePlannedSession(args.id, env);
    case "update_planned_session":
      return updatePlannedSession(args.id, args.fields, env);
    case "list_pending_modulations":
      return listPendingModulations(args.include_past ?? false, env);
    case "dismiss_modulations":
      return dismissModulations(args, env);
    case "accept_modulation":
      return acceptModulation(args.id, env);
    case "create_constraint":
      return createConstraint(args, env);
    case "refute_belief":
      return refuteBelief(args, env);
    case "list_beliefs":
      return listBeliefs(args, env);
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

// ── Data freshness helpers (Fix: temporal staleness) ─────────────────────────
function oldestDateFromRecords(records: any[]): string | null {
  const dates: string[] = [];
  for (const r of records) {
    if (!r) continue;
    for (const c of [r.date, r.planned_date, r.started_at, r.logged_at, r.created_at, r.proposed_at]) {
      if (c && typeof c === "string") dates.push(c.slice(0, 10));
    }
  }
  return dates.length > 0 ? dates.sort()[0] : null;
}

function dataFreshness(recordGroups: any[][]): Record<string, any> {
  const now = new Date();
  const serverDateRome = todayRomeISO();
  const oldest = oldestDateFromRecords(recordGroups.flat().filter(Boolean));
  const ageHours = oldest ? Math.round((now.getTime() - new Date(oldest).getTime()) / 3600000) : null;
  const isStale = ageHours !== null && ageHours > 6;
  return {
    server_date_utc: now.toISOString(),
    server_date_rome: serverDateRome,
    oldest_data_point: oldest,
    data_age_hours: ageHours,
    staleness_warning: isStale,
    notice: isStale
      ? `⚠️ DATI VECCHI: server_date=${serverDateRome}, record_più_vecchio=${oldest}, età=${ageHours}h — USA server_date_rome COME DATA ODIERNA, non inferire "oggi" dai record`
      : `✅ server_date=${serverDateRome} — usa questa come data odierna`,
  };
}

const VALID_SPORTS = new Set(["swim", "bike", "run", "brick", "strength", "all"]);
const VALID_KINDS  = new Set(["all", "post_session", "illness", "injury", "evening_debrief", "free_note"]);

function deriveProgressionStep(mesocycle: any, today: string): any {
  if (!mesocycle || !mesocycle.progression_plan || !mesocycle.start_date) return null;
  const startDate = new Date(mesocycle.start_date);
  const todayDate = new Date(today);
  // Use UTC-midnight arithmetic to avoid DST transitions skewing week boundaries.
  const utcStart = Date.UTC(startDate.getUTCFullYear(), startDate.getUTCMonth(), startDate.getUTCDate());
  const utcToday = Date.UTC(todayDate.getUTCFullYear(), todayDate.getUTCMonth(), todayDate.getUTCDate());
  const weekNumber = Math.floor((utcToday - utcStart) / (7 * 24 * 60 * 60 * 1000)) + 1;
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

  const [health, metrics, wellness, activities, subjective, plannedPast, plannedUpcoming, sessionAnalyses, modulations, mesocycles, races, constraints, beliefs, fatigueBySport] =
    await Promise.all([
      getHealth(env),
      sb(env, `daily_metrics?date=gte.${metricsSince}&order=date.asc&select=date,ctl,atl,tsb,daily_tss,hrv_z_score,readiness_score,readiness_label,flags,garmin_training_readiness`),
      sb(env, `daily_wellness?date=gte.${metricsSince}&order=date.asc&select=date,hrv_rmssd,sleep_score,body_battery_min,body_battery_max,resting_hr,training_readiness_score,avg_sleep_stress`),
      sb(env, `activities?started_at=gte.${since}T00:00:00Z&order=started_at.desc&select=external_id,started_at,sport,duration_s,distance_m,avg_hr,max_hr,avg_power_w,np_w,avg_pace_s_per_km,tss`),
      sb(env, `subjective_log?logged_at=gte.${since}T00:00:00Z&order=logged_at.desc&select=logged_at,kind,rpe,sleep_quality,motivation,soreness,illness_flag,injury_flag,injury_details,raw_text`),
      sb(env, `planned_sessions?planned_date=gte.${since}&planned_date=lt.${today}&status=neq.cancelled&order=planned_date.asc&select=id,planned_date,sport,session_type,duration_s,target_tss,description,status,completed_activity_id`),
      sb(env, `planned_sessions?planned_date=gte.${today}&planned_date=lte.${until}&status=neq.cancelled&order=planned_date.asc&select=id,planned_date,sport,session_type,duration_s,target_tss,description,status,completed_activity_id`),
      sb(env, `session_analyses?created_at=gte.${since}T00:00:00Z&order=created_at.desc&select=activity_id,analysis_text,created_at&limit=8`),
      // limit=5: le proposte aperte si accumulano (se non risolte). Per la review
      // bastano le piu' recenti; il JSONB proposed_changes e' grosso.
      sb(env, `plan_modulations?status=eq.proposed&order=proposed_at.desc&select=id,trigger_event,proposed_changes,status,proposed_at&limit=5`),
      sb(env, `mesocycles?start_date=lte.${today}&end_date=gte.${today}&order=start_date.desc&limit=1`),
      sb(env, `races?race_date=gte.${today}&order=race_date.asc&select=id,name,race_date,priority,distance,location`),
      sb(env, `active_constraints?resolved_at=is.null&order=created_at.asc`).catch(() => []),
      sb(env, `beliefs?status=neq.retired&confidence=gte.0.55&order=confidence.desc&select=belief_key,belief_text,status,confidence`).catch(() => []),
      getLastFatigueBySport(env, since),
    ]);

  // Compute weekly TSS aggregates for coach summary (last 7 days).
  const week7ago = daysAgoISO(7);
  const tssWeek = (metrics as any[])
    .filter((m: any) => m.date >= week7ago)
    .reduce((sum: number, m: any) => sum + (m.daily_tss || 0), 0);
  const plannedTssWeek = (plannedPast as any[])
    .filter((s: any) => s.planned_date >= week7ago)
    .reduce((sum: number, s: any) => sum + (s.target_tss || 0), 0);

  return {
    generated_at: new Date().toISOString(),
    timezone: "Europe/Rome",
    data_freshness: dataFreshness([metrics, wellness, activities, subjective, plannedPast, plannedUpcoming]),
    period: { today, completed_since: since, upcoming_until: until },
    coach_protocol: coachProtocol(),
    sync_status: summarizeSync(health),
    health,
    tss_week: Math.round(tssWeek),
    planned_tss_week: Math.round(plannedTssWeek),
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
    active_beliefs: beliefs || [],
    last_fatigue_by_sport: fatigueBySport,
    review_instructions: [
      "PRIMO: leggi data_freshness.notice e usa server_date_rome come data odierna — NON inferire 'oggi' dal record più recente.",
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

  // Cap plan window to 42 days from today — requesting 180-day plans can produce
  // thousands of rows that add no coaching value and bloat the LLM context.
  const planUntil = targetDate < daysFromISO(42) ? targetDate : daysFromISO(42);

  const [metrics, wellness, activities, subjective, planWindow] = await Promise.all([
    sb(env, `daily_metrics?date=gte.${since28}&order=date.asc`),
    sb(env, `daily_wellness?date=gte.${since28}&order=date.asc&select=date,hrv_rmssd,sleep_score,body_battery_min,body_battery_max,resting_hr,training_readiness_score`),
    sb(env, `activities?started_at=gte.${since28}T00:00:00Z&order=started_at.desc&select=id,external_id,started_at,sport,duration_s,distance_m,avg_hr,tss`),
    sb(env, `subjective_log?logged_at=gte.${since14}T00:00:00Z&order=logged_at.desc`),
    sb(env, `planned_sessions?planned_date=gte.${today}&planned_date=lte.${planUntil}&order=planned_date.asc`),
  ]);

  return {
    generated_at: new Date().toISOString(),
    timezone: "Europe/Rome",
    data_freshness: dataFreshness([metrics, wellness, activities, subjective, planWindow]),
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
  const sport = VALID_SPORTS.has(activity.sport) ? activity.sport : "all";

  const [planned, metrics, subjective, sportHistory, analyses] = await Promise.all([
    sb(env, `planned_sessions?planned_date=eq.${activityDate}&sport=eq.${sport}`),
    sb(env, `daily_metrics?date=eq.${activityDate}&limit=1`),
    sb(env, `subjective_log?logged_at=gte.${daysAgoISO(3)}T00:00:00Z&order=logged_at.desc`),
    getActivityHistory(sport, historyDays, env),
    sb(env, `session_analyses?activity_id=eq.${encodeURIComponent(activity.external_id || activity.id)}&limit=1`),
  ]);

  return {
    generated_at: new Date().toISOString(),
    data_freshness: dataFreshness([[activity], subjective]),
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
  const sessions = await sb(env, `planned_sessions?planned_date=gte.${today}&planned_date=lte.${until}&status=neq.cancelled&order=planned_date.asc`);
  return {
    generated_at: new Date().toISOString(),
    data_freshness: dataFreshness([sessions]),
    today,
    sessions,
  };
}

async function getHealth(env: Env) {
  return sb(env, `health?select=component,last_success_at,failure_count,last_error&order=component.asc`);
}

/**
 * Ritorna l'ultima classificazione di fatica per ogni disciplina (run/swim/bike).
 * Legge `session_analyses.fatigue_type` filtrato per colonna `sport` (D-05, evita JOIN problematico).
 * Formato return: `{run: {type, confidence, date} | null, swim: ..., bike: ...}`.
 */
async function getLastFatigueBySport(env: Env, since: string): Promise<Record<string, any>> {
  const sports = ["run", "swim", "bike"];
  const result: Record<string, any> = { run: null, swim: null, bike: null };
  for (const sport of sports) {
    const rows = await sb(
      env,
      `session_analyses?sport=eq.${sport}&fatigue_type=not.is.null&created_at=gte.${since}T00:00:00Z&order=created_at.desc&limit=1&select=fatigue_type,fatigue_confidence,created_at`
    ).catch(() => []);
    if (rows?.[0]) {
      result[sport] = {
        type: rows[0].fatigue_type,
        confidence: rows[0].fatigue_confidence,
        date: rows[0].created_at?.split("T")[0],
      };
    }
  }
  return result;
}

async function getRecentMetrics(days: number, env: Env) {
  const since = daysAgoISO(days);
  const metrics = await sb(env, `daily_metrics?date=gte.${since}&order=date.desc`);
  return {
    generated_at: new Date().toISOString(),
    data_freshness: dataFreshness([metrics]),
    metrics,
  };
}

async function getPlannedSession(date: string, env: Env) {
  if (!isDateString(date)) throw new Error(`Invalid date format: ${date}. Expected YYYY-MM-DD.`);
  return sb(env, `planned_sessions?planned_date=eq.${date}&status=neq.cancelled`);
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
  if (!Number.isInteger(args.duration_s) || args.duration_s < 60) {
    throw new Error(`Invalid duration_s: must be an integer >= 60 (got ${args.duration_s}).`);
  }

  const validStatuses = ["planned", "completed", "skipped", "modified", "cancelled"];
  const status = args.status ?? "planned";
  if (!validStatuses.includes(status)) {
    throw new Error(`Invalid status: ${status}. Must be one of ${validStatuses.join(", ")}`);
  }

  const payload: any = {
    planned_date: args.planned_date,
    sport: args.sport,
    session_type: args.session_type,
    duration_s: args.duration_s,
    description: args.description,
    status,
  };
  if (args.target_tss !== undefined) payload.target_tss = args.target_tss;
  if (args.target_zones !== undefined) payload.target_zones = args.target_zones;
  if (args.calendar_event_id !== undefined) payload.calendar_event_id = args.calendar_event_id;

  // mesocycle_id: usa quello fornito, altrimenti aggancia automaticamente il
  // mesociclo attivo per quella data (evita le sessioni con mesocycle_id=null
  // che il coach segnalava come "non catalogate").
  if (args.mesocycle_id !== undefined) {
    payload.mesocycle_id = args.mesocycle_id;
  } else {
    const meso = await activeMesocycleId(args.planned_date, env);
    if (meso) payload.mesocycle_id = meso;
  }

  // Fix #5: auto-derive absolute zone ranges from active physiology_zones.
  // Merged into structured.zones_derived so coach and compliance engine share the same baseline.
  const zonesRow = await getActiveZoneForDiscipline(args.sport, env).catch(() => null);
  const absoluteZones = computeAbsoluteZones(args.sport, zonesRow);
  const structuredBase = args.structured || {};
  payload.structured = absoluteZones
    ? { ...structuredBase, zones_derived: absoluteZones }
    : (Object.keys(structuredBase).length > 0 ? structuredBase : undefined);
  if (payload.structured === undefined) delete payload.structured;

  const existingResp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/planned_sessions?planned_date=eq.${args.planned_date}&sport=eq.${args.sport}&session_type=eq.${encodeURIComponent(args.session_type)}`,
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

/** ID del mesociclo che copre la data indicata (start <= date <= end), o null. */
async function activeMesocycleId(dateISO: string, env: Env): Promise<string | null> {
  const rows = await sb(
    env,
    `mesocycles?start_date=lte.${dateISO}&end_date=gte.${dateISO}&order=start_date.desc&limit=1&select=id`
  );
  return rows?.[0]?.id ?? null;
}

/** Risolve una sessione da session_id oppure da date+sport. Esclude le cancelled. */
async function resolveSession(args: any, env: Env): Promise<any | null> {
  let rows: any[];
  if (args.session_id) {
    rows = await sb(env, `planned_sessions?id=eq.${args.session_id}&limit=1`);
  } else if (args.date && args.sport) {
    rows = await sb(env, `planned_sessions?planned_date=eq.${args.date}&sport=eq.${args.sport}&status=neq.cancelled&limit=1`);
  } else {
    throw new Error("Indica session_id, oppure date + sport.");
  }
  return rows?.[0] ?? null;
}

async function deleteSession(args: any, env: Env): Promise<any> {
  const session = await resolveSession(args, env);
  if (!session) {
    return { status: "not_found", message: "Nessuna sessione corrispondente (session_id o date+sport)." };
  }

  const id = session.id;
  const calendarEventId = session.calendar_event_id ?? null;
  const headers = {
    "apikey": env.SUPABASE_SERVICE_KEY,
    "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    "Content-Type": "application/json",
  };

  if (args.hard === true) {
    const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions?id=eq.${id}`, {
      method: "DELETE",
      headers,
    });
    if (!resp.ok) throw new Error(`Delete failed: ${resp.status} ${await resp.text()}`);
    return {
      status: "deleted_hard",
      session_id: id,
      deleted: { planned_date: session.planned_date, sport: session.sport, session_type: session.session_type },
      calendar_event_id: calendarEventId,
    };
  }

  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions?id=eq.${id}`, {
    method: "PATCH",
    headers: { ...headers, "Prefer": "return=representation" },
    body: JSON.stringify({ status: "cancelled" }),
  });
  if (!resp.ok) throw new Error(`Cancel failed: ${resp.status} ${await resp.text()}`);
  return {
    status: "cancelled",
    session_id: id,
    cancelled: { planned_date: session.planned_date, sport: session.sport, session_type: session.session_type },
    calendar_event_id: calendarEventId,
  };
}

async function rescheduleSession(args: any, env: Env): Promise<any> {
  if (!args.new_date) throw new Error("new_date è obbligatorio.");

  const session = await resolveSession(args, env);
  if (!session) {
    return { status: "not_found", message: "Nessuna sessione corrispondente (session_id o date+sport)." };
  }

  const targetSport = args.new_sport ?? session.sport;
  const targetDate = args.new_date;

  if (targetDate === session.planned_date && targetSport === session.sport) {
    return { status: "noop", message: "La destinazione coincide con la posizione attuale.", session_id: session.id };
  }

  // La UNIQUE (planned_date, sport) impedisce due righe sullo stesso slot.
  // Verifica l'occupazione della destinazione.
  const occupants = await sb(
    env,
    `planned_sessions?planned_date=eq.${targetDate}&sport=eq.${targetSport}&select=id,status,session_type`
  );
  const blocking = (occupants || []).filter((o: any) => o.id !== session.id);

  const headers = {
    "apikey": env.SUPABASE_SERVICE_KEY,
    "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    "Content-Type": "application/json",
  };

  if (blocking.length > 0) {
    const cancelledOccupant = blocking.find((o: any) => o.status === "cancelled");
    const activeOccupant = blocking.find((o: any) => o.status !== "cancelled");
    if (activeOccupant) {
      return {
        status: "conflict",
        message: `La destinazione ${targetDate} (${targetSport}) è già occupata da una sessione attiva (${activeOccupant.session_type || "?"}). Cancellala o scegli un'altra data prima di spostare.`,
        conflicting_session_id: activeOccupant.id,
      };
    }
    // Solo una sessione cancelled occupa lo slot: liberalo (hard delete) per non
    // violare la UNIQUE, poi sposta.
    if (cancelledOccupant) {
      const del = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions?id=eq.${cancelledOccupant.id}`, {
        method: "DELETE",
        headers,
      });
      if (!del.ok) throw new Error(`Slot cleanup failed: ${del.status} ${await del.text()}`);
    }
  }

  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions?id=eq.${session.id}`, {
    method: "PATCH",
    headers: { ...headers, "Prefer": "return=representation" },
    body: JSON.stringify({ planned_date: targetDate, sport: targetSport }),
  });
  if (!resp.ok) throw new Error(`Reschedule failed: ${resp.status} ${await resp.text()}`);

  return {
    status: "rescheduled",
    session_id: session.id,
    from: { planned_date: session.planned_date, sport: session.sport },
    to: { planned_date: targetDate, sport: targetSport },
    calendar_event_id: session.calendar_event_id ?? null,
  };
}

// ============================================================================
// Physiology Zones
// ============================================================================

/** Recupera la riga physiology_zones attiva per la disciplina specificata. */
async function getActiveZoneForDiscipline(discipline: string, env: Env): Promise<any | null> {
  const today = todayRomeISO();
  const rows = await sb(env, `physiology_zones?discipline=eq.${discipline}&or=(valid_to.is.null,valid_to.gte.${today})&valid_from=lte.${today}&order=valid_from.desc&limit=1`).catch(() => null);
  return rows?.[0] || null;
}

/** Calcola zone fisiologiche assolute da una riga physiology_zones.
 *  Usate in commit_plan_change per iniettare zone_derived in structured. */
function computeAbsoluteZones(discipline: string, z: any): any | null {
  if (!z) return null;

  if (discipline === "bike" && z.ftp_w) {
    const ftp: number = z.ftp_w;
    const fmt = (w: number) => `${Math.round(w)}W`;
    return {
      discipline: "bike",
      ftp_w: ftp,
      lthr: z.lthr || null,
      zones: {
        z1: { label: "Recovery",   range: `<${fmt(ftp * 0.55)}` },
        z2: { label: "Endurance",  range: `${fmt(ftp * 0.55)}–${fmt(ftp * 0.75)}` },
        z3: { label: "Tempo",      range: `${fmt(ftp * 0.75)}–${fmt(ftp * 0.90)}` },
        z4: { label: "Threshold",  range: `${fmt(ftp * 0.90)}–${fmt(ftp * 1.05)}` },
        z5: { label: "VO2max",     range: `${fmt(ftp * 1.05)}–${fmt(ftp * 1.20)}` },
        z6: { label: "Anaerobic",  range: `>${fmt(ftp * 1.20)}` },
      },
    };
  }

  // Bici senza wattmetro: zone HR da LTHR (stesse % di _compute_lthr_5zone in Python).
  if (discipline === "bike" && z.lthr) {
    const lthr: number = z.lthr;
    const fmt = (h: number) => `${Math.round(h)} bpm`;
    return {
      discipline: "bike",
      lthr,
      zones: {
        z1: { label: "Recovery",  hr_below: fmt(lthr * 0.81) },
        z2: { label: "Aerobic",   hr_range: `${fmt(lthr * 0.81)}–${fmt(lthr * 0.89)}` },
        z3: { label: "Tempo",     hr_range: `${fmt(lthr * 0.90)}–${fmt(lthr * 0.95)}` },
        z4: { label: "Threshold", hr_range: `${fmt(lthr * 0.96)}–${fmt(lthr)}` },
        z5: { label: "Above",     hr_above: fmt(lthr) },
      },
    };
  }

  if (discipline === "run" && z.threshold_pace_s_per_km) {
    const tp: number = z.threshold_pace_s_per_km;
    const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}/km`;
    // Formula moltiplicativa (Friel), identica a _compute_pace_5zone in Python:
    // unica fonte di verità, altrimenti il coach prescrive su zone diverse dal brief.
    return {
      discipline: "run",
      threshold_s_per_km: tp,
      threshold_pace: fmt(tp),
      lthr: z.lthr || null,
      zones: {
        z1: { label: "Recovery",  pace_slower_than: fmt(tp * 1.25) },
        z2: { label: "Endurance", pace_range: `${fmt(tp * 1.25)}–${fmt(tp * 1.15)}` },
        z3: { label: "Tempo",     pace_range: `${fmt(tp * 1.15)}–${fmt(tp * 1.05)}` },
        z4: { label: "Threshold", pace_range: `${fmt(tp * 1.05)}–${fmt(tp * 0.97)}` },
        z5: { label: "VO2max",    pace_faster_than: fmt(tp * 0.97) },
      },
    };
  }

  if (discipline === "swim" && z.css_pace_s_per_100m) {
    const css: number = z.css_pace_s_per_100m;
    const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}/100m`;
    return {
      discipline: "swim",
      css_s_per_100m: css,
      css_pace: fmt(css),
      zones: {
        z1: { label: "Recovery",      pace_slower_than: fmt(css + 25) },
        z2: { label: "Endurance",     pace_range: `${fmt(css + 25)}–${fmt(css + 10)}` },
        z3: { label: "Threshold-ish", pace_range: `${fmt(css + 10)}–${fmt(css)}` },
        z4: { label: "CSS/Threshold", pace_range: `${fmt(css)}–${fmt(css - 5)}` },
        z5: { label: "VO2max",        pace_faster_than: fmt(css - 5) },
      },
    };
  }

  return null;
}

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
      // Slice to date part before appending T00:00:00Z — valid_from may already
      // be a full datetime string (e.g. "2026-06-04T10:00:00+00:00").
      const validFromUTC = new Date(String(zone.valid_from).slice(0, 10) + "T00:00:00Z");
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
// Technique History
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
async function commitPhysiologyZones(args: any, env: Env): Promise<any> {
  const validDisc = ["swim", "bike", "run"];
  if (!validDisc.includes(args.discipline)) {
    throw new Error(`Invalid discipline: ${args.discipline}. Must be one of ${validDisc.join(", ")}`);
  }
  if (!args.method) throw new Error("Missing required field: method");
  const valueFields = ["ftp_w", "threshold_pace_s_per_km", "css_pace_s_per_100m", "lthr"];
  if (!valueFields.some((k) => args[k] !== undefined && args[k] !== null)) {
    throw new Error(`Provide at least one value field: ${valueFields.join(", ")}`);
  }

  const validFrom = args.valid_from || todayRomeISO();
  const payload: any = { discipline: args.discipline, valid_from: validFrom, method: args.method };
  for (const k of ["ftp_w", "threshold_pace_s_per_km", "css_pace_s_per_100m", "lthr", "hr_max", "test_activity_id"]) {
    if (args[k] !== undefined && args[k] !== null) payload[k] = args[k];
  }
  payload.notes = args.notes || (args.zones ? JSON.stringify({ zones: args.zones }) : null);

  const headers = {
    "apikey": env.SUPABASE_SERVICE_KEY,
    "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    "Content-Type": "application/json",
    "Prefer": "return=representation",
  };

  const existingResp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/physiology_zones?discipline=eq.${args.discipline}&valid_from=eq.${validFrom}`,
    { headers: { "apikey": env.SUPABASE_SERVICE_KEY, "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}` } }
  );
  const existing = (await existingResp.json()) as any[];

  if (existing.length > 0) {
    const id = existing[0].id;
    const upd = await fetch(`${env.SUPABASE_URL}/rest/v1/physiology_zones?id=eq.${id}`, {
      method: "PATCH", headers, body: JSON.stringify(payload),
    });
    if (!upd.ok) throw new Error(`Update failed: ${upd.status} ${await upd.text()}`);
    return { status: "updated", zone_id: id, payload };
  }
  const ins = await fetch(`${env.SUPABASE_URL}/rest/v1/physiology_zones`, {
    method: "POST", headers, body: JSON.stringify(payload),
  });
  if (!ins.ok) throw new Error(`Insert failed: ${ins.status} ${await ins.text()}`);
  const result = (await ins.json()) as any[];
  return { status: "created", zone_id: result[0]?.id, payload };
}

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
// Constraint management (Fix #4)
// ============================================================================
async function updateConstraint(args: any, env: Env): Promise<any> {
  if (!args.id || !isUuid(args.id)) {
    throw new Error(`Invalid constraint id: must be a valid UUID`);
  }

  const existing = await sb(env, `active_constraints?id=eq.${args.id}&limit=1`);
  if (!existing || existing.length === 0) return { error: "Constraint not found", id: args.id };
  const current = existing[0];

  const patch: any = {};
  if (args.resolved_at !== undefined) patch.resolved_at = args.resolved_at;
  else if (args.resolve === true) patch.resolved_at = new Date().toISOString();
  if (args.description !== undefined) patch.description = args.description;
  if (args.severity !== undefined) {
    if (!["low", "medium", "high", "critical"].includes(args.severity)) throw new Error(`Invalid severity: ${args.severity}`);
    patch.severity = args.severity;
  }
  if (args.symptom_status !== undefined) {
    if (!["symptomatic", "asymptomatic", "recovering"].includes(args.symptom_status)) throw new Error(`Invalid symptom_status: ${args.symptom_status}`);
    patch.symptom_status = args.symptom_status;
  }
  if (args.note !== undefined) patch.note = args.note;

  if (Object.keys(patch).length === 0) {
    throw new Error("Nessun campo da aggiornare. Specifica resolved_at, description, severity, symptom_status o note.");
  }

  // Append to history audit trail
  const historyEntry = {
    timestamp: new Date().toISOString(),
    changes: patch,
    previous: Object.fromEntries(Object.keys(patch).map((k) => [k, (current as any)[k] ?? null])),
  };
  const prevHistory: any[] = Array.isArray(current.history) ? current.history : [];
  patch.history = [...prevHistory, historyEntry];

  const updateResp = await fetch(`${env.SUPABASE_URL}/rest/v1/active_constraints?id=eq.${args.id}`, {
    method: "PATCH",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=representation",
    },
    body: JSON.stringify(patch),
  });
  if (!updateResp.ok) throw new Error(`Update failed: ${updateResp.status} ${await updateResp.text()}`);
  const result = (await updateResp.json()) as any[];
  return { status: patch.resolved_at ? "resolved" : "updated", constraint: result[0] };
}

async function createConstraint(args: any, env: Env): Promise<any> {
  const required = ["type", "discipline", "description", "severity"];
  for (const k of required) {
    if (!args[k]) throw new Error(`Missing required field: ${k}`);
  }
  if (!["injury", "medical", "tactical"].includes(args.type)) throw new Error(`Invalid type: ${args.type}`);
  if (!["swim", "bike", "run", "all", "strength"].includes(args.discipline)) throw new Error(`Invalid discipline: ${args.discipline}`);
  if (!["low", "medium", "high", "critical"].includes(args.severity)) throw new Error(`Invalid severity: ${args.severity}`);

  const payload: any = {
    type: args.type,
    discipline: args.discipline,
    description: args.description,
    severity: args.severity,
  };
  if (args.symptom_status) payload.symptom_status = args.symptom_status;
  if (args.note) payload.note = args.note;

  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/active_constraints`, {
    method: "POST",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=representation",
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`Insert failed: ${resp.status} ${await resp.text()}`);
  const result = (await resp.json()) as any[];
  return { status: "created", constraint: result[0] };
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

  const ghRepo = env.GH_REPO || "NicoRoger/triathlon-coach";
  const dispatchResp = await fetch(
    `https://api.github.com/repos/${ghRepo}/actions/workflows/ingest.yml/dispatches`,
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

// ============================================================================
// Plan session management (Fix #2)
// ============================================================================
async function deletePlannedSession(id: string, env: Env): Promise<any> {
  if (!id || !isUuid(id)) throw new Error(`Invalid session id: ${id}`);

  const rows = await sb(env, `planned_sessions?id=eq.${id}&select=id,planned_date,sport,status,calendar_event_id`);
  if (!rows || rows.length === 0) return { error: "Session not found", id };

  const session = rows[0];
  const today = todayRomeISO();
  const isPast = session.planned_date < today;

  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions?id=eq.${id}`, {
    method: "PATCH",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=minimal",
    },
    body: JSON.stringify({ status: "cancelled" }),
  });
  if (!resp.ok) throw new Error(`Delete failed: ${resp.status} ${await resp.text()}`);

  return {
    success: true,
    id,
    planned_date: session.planned_date,
    sport: session.sport,
    calendar_event_id: session.calendar_event_id || null,
    gcal_action_needed: !!session.calendar_event_id,
    ...(isPast ? { warning: "Cancellazione di una sessione passata" } : {}),
  };
}

async function updatePlannedSession(id: string, fields: any, env: Env): Promise<any> {
  if (!id || !isUuid(id)) throw new Error(`Invalid session id: ${id}`);
  if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
    throw new Error("fields deve essere un oggetto");
  }

  const FORBIDDEN = ["id", "created_at", "source"];
  for (const f of FORBIDDEN) {
    if (f in fields) throw new Error(`Campo vietato: ${f}`);
  }
  if (Object.keys(fields).length === 0) throw new Error("Nessun campo da aggiornare");

  const rows = await sb(env, `planned_sessions?id=eq.${id}&select=id,planned_date,sport,calendar_event_id`);
  if (!rows || rows.length === 0) return { error: "Session not found", id };

  const session = rows[0];

  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions?id=eq.${id}`, {
    method: "PATCH",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=representation",
    },
    body: JSON.stringify(fields),
  });
  if (!resp.ok) throw new Error(`Update failed: ${resp.status} ${await resp.text()}`);

  const updated = (await resp.json()) as any[];
  const calendarNeedsUpdate = ("planned_date" in fields || "description" in fields || "session_type" in fields) && !!session.calendar_event_id;

  return {
    success: true,
    session: updated[0] || null,
    ...(calendarNeedsUpdate ? {
      gcal_action_needed: true,
      calendar_event_id: session.calendar_event_id,
      note: "Data o descrizione cambiata — aggiorna anche Google Calendar con calendar_event_id",
    } : {}),
  };
}

// ============================================================================
// Modulation management tools (Fix #3)
// ============================================================================
async function listPendingModulations(includePast: boolean, env: Env): Promise<any> {
  const today = todayRomeISO();
  const rows: any[] = await sb(env, `plan_modulations?status=eq.proposed&order=proposed_at.desc&select=id,trigger_event,proposed_changes,source,proposed_at,expires_at`);

  const current = includePast ? rows : rows.filter((r: any) => {
    const changes: any[] = r.proposed_changes || [];
    const dates = changes.filter((c: any) => c?.date).map((c: any) => c.date as string);
    if (dates.length === 0) return true;
    return dates.some((d) => d >= today);
  });

  const fmt = (r: any) => {
    const changes: any[] = r.proposed_changes || [];
    const firstChange = changes[0] || {};
    return {
      id: r.id,
      session_date: firstChange.date || null,
      sport: firstChange.sport || null,
      proposed_change: firstChange.new?.description || null,
      source: r.source || "auto",
      trigger: r.trigger_event,
      proposed_at: r.proposed_at,
      expires_at: r.expires_at,
    };
  };

  const coachItems = current.filter((r: any) => r.source === "coach").map(fmt);
  const autoItems = current.filter((r: any) => r.source !== "coach").map(fmt);

  return {
    generated_at: new Date().toISOString(),
    total: current.length,
    total_all: rows.length,
    include_past: includePast,
    coach: coachItems,
    auto: autoItems,
    tip: rows.length > current.length
      ? `${rows.length - current.length} modulazioni obsolete nascoste. Usa dismiss_modulations({ dismiss_all_past: true }) per pulirle.`
      : current.length === 0 ? "Nessuna modulazione pending." : undefined,
  };
}

async function dismissModulations(args: any, env: Env): Promise<any> {
  if (!args.ids?.length && !args.dismiss_all_past) {
    throw new Error("Specifica ids[] oppure dismiss_all_past=true");
  }

  const today = todayRomeISO();
  const sourceFilter: string = args.source_filter || "all";
  const now = new Date().toISOString();
  let targetIds: string[] = [];

  if (args.dismiss_all_past) {
    const rows: any[] = await sb(env, `plan_modulations?status=eq.proposed&select=id,proposed_changes,source`);
    for (const r of rows) {
      if (sourceFilter !== "all" && (r.source || "auto") !== sourceFilter) continue;
      const changes: any[] = r.proposed_changes || [];
      const dates = changes.filter((c: any) => c?.date).map((c: any) => c.date as string);
      if (dates.length === 0 || dates.every((d) => d < today)) {
        targetIds.push(r.id);
      }
    }
  }

  if (args.ids?.length) {
    let idsToAdd: string[] = args.ids;
    if (sourceFilter !== "all") {
      const rows: any[] = await sb(env, `plan_modulations?id=in.(${idsToAdd.join(",")})&select=id,source`);
      idsToAdd = rows.filter((r: any) => (r.source || "auto") === sourceFilter).map((r: any) => r.id);
    }
    for (const id of idsToAdd) {
      if (!targetIds.includes(id)) targetIds.push(id);
    }
  }

  if (targetIds.length === 0) {
    return { dismissed_count: 0, ids: [], message: "Nessuna modulazione da rigettare con i criteri specificati" };
  }

  const patchResp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/plan_modulations?id=in.(${targetIds.join(",")})`,
    {
      method: "PATCH",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
      },
      body: JSON.stringify({ status: "dismissed", resolved_at: now }),
    }
  );
  if (!patchResp.ok) throw new Error(`dismiss PATCH failed: ${patchResp.status} ${await patchResp.text()}`);

  return {
    dismissed_count: targetIds.length,
    ids: targetIds,
    message: `${targetIds.length} modulazioni rigettate (status='dismissed').`,
  };
}

async function acceptModulation(id: string, env: Env): Promise<any> {
  if (!id) throw new Error("id is required");

  const rows: any[] = await sb(env, `plan_modulations?id=eq.${encodeURIComponent(id)}&limit=1`);
  const mod = rows?.[0];
  if (!mod) return { error: "Modulation not found", id };
  if (mod.status !== "proposed") {
    return { success: false, message: `Modulazione già in status '${mod.status}', non accettabile.` };
  }

  const changes: any[] = mod.proposed_changes || [];
  const applied: string[] = [];
  const skipped: string[] = [];

  for (const change of changes) {
    const targetDate = change?.date;
    const sport = change?.sport;
    const newSession = change?.new || {};
    if (!targetDate || !sport) { skipped.push(JSON.stringify(change)); continue; }

    const existingRows: any[] = await sb(env, `planned_sessions?planned_date=eq.${targetDate}&sport=eq.${sport}&limit=1`);
    const base: any = existingRows?.[0] || {};
    if (base.status === "completed") { skipped.push(`${targetDate}/${sport}: già completata`); continue; }

    const pick = (key: string, def: any) => newSession[key] != null ? newSession[key] : (base[key] != null ? base[key] : def);
    const payload = {
      planned_date: targetDate,
      sport,
      session_type: pick("session_type", "recovery"),
      duration_s: pick("duration_s", 3600),
      description: pick("description", "Sessione modificata per recupero"),
      status: "planned",
    };

    // on_conflict sulla chiave UNIQUE reale: senza, la POST collide con
    // (planned_date,sport,session_type) e va in 409 → la modifica a una
    // sessione esistente veniva skippata. Match con _apply_single_change (Python).
    const upsertResp = await fetch(`${env.SUPABASE_URL}/rest/v1/planned_sessions?on_conflict=planned_date,sport,session_type`, {
      method: "POST",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
      },
      body: JSON.stringify(payload),
    });
    if (!upsertResp.ok) {
      skipped.push(`${targetDate}/${sport}: ${upsertResp.status}`);
    } else {
      const result = (await upsertResp.json()) as any[];
      applied.push(result?.[0]?.id || `${targetDate}/${sport}`);
    }
  }

  const newStatus = skipped.length === 0 && applied.length > 0 ? "applied" : applied.length > 0 ? "partial" : "failed";
  await fetch(`${env.SUPABASE_URL}/rest/v1/plan_modulations?id=eq.${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=minimal",
    },
    body: JSON.stringify({ status: newStatus, resolved_at: new Date().toISOString() }),
  });

  return {
    success: newStatus !== "failed",
    modulation_id: id,
    final_status: newStatus,
    planned_session_ids: applied,
    skipped,
  };
}

// ============================================================================
// Belief management (Fix #7)
// ============================================================================
async function refuteBelief(args: any, env: Env): Promise<any> {
  if (!args.belief_key) throw new Error("belief_key is required");
  if (!args.reason) throw new Error("reason is required");

  const rows = await sb(env, `beliefs?belief_key=eq.${encodeURIComponent(args.belief_key)}&limit=1`);
  if (!rows || rows.length === 0) return { error: "Belief not found", belief_key: args.belief_key };
  const belief = rows[0];

  if (belief.status === "retired") {
    return { status: "already_retired", belief_key: args.belief_key, message: "Belief già ritirata." };
  }

  const CONTRADICT_PENALTY = 0.15;
  const confBefore: number = belief.confidence ?? 0.5;
  const confAfter = Math.max(0.05, confBefore - CONTRADICT_PENALTY);
  const nAfter = (belief.evidence_n ?? 0) + 1;

  // Mirror Python _compute_status logic: demote on low confidence
  const STATUS_RANK: Record<string, number> = { hypothesis: 1, weak_belief: 2, validated_belief: 3, strong_belief: 4 };
  let statusAfter = belief.status;
  if (confAfter < 0.15 && nAfter >= 5) statusAfter = "retired";
  else if (confAfter < 0.25 && (STATUS_RANK[statusAfter] || 0) >= 4) statusAfter = "validated_belief";
  else if (confAfter < 0.25 && (STATUS_RANK[statusAfter] || 0) >= 3) statusAfter = "weak_belief";

  const now = new Date().toISOString();
  const patch = {
    confidence: confAfter,
    evidence_n: nAfter,
    status: statusAfter,
    flagged: true,
    flag_reason: args.reason,
    last_contradicted_at: now,
    last_updated_at: now,
  };

  const patchResp = await fetch(`${env.SUPABASE_URL}/rest/v1/beliefs?id=eq.${belief.id}`, {
    method: "PATCH",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=representation",
    },
    body: JSON.stringify(patch),
  });
  if (!patchResp.ok) throw new Error(`Belief update failed: ${patchResp.status} ${await patchResp.text()}`);

  // Log to beliefs_history (non-fatal if table schema differs)
  await fetch(`${env.SUPABASE_URL}/rest/v1/beliefs_history`, {
    method: "POST",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=minimal",
    },
    body: JSON.stringify({
      belief_id: belief.id,
      change_type: "refuted",
      confidence_before: confBefore,
      confidence_after: confAfter,
      evidence_n_before: belief.evidence_n ?? 0,
      evidence_n_after: nAfter,
      status_before: belief.status,
      status_after: statusAfter,
      reason: args.reason,
      metadata: { evidence_source: args.evidence_source || "coach_refutation" },
    }),
  }).catch(() => { /* non-fatal */ });

  return {
    success: true,
    belief_key: args.belief_key,
    previous: { confidence: confBefore, status: belief.status },
    updated: { confidence: confAfter, status: statusAfter, flagged: true },
    message: `Belief refutata: conf ${confBefore.toFixed(2)}→${confAfter.toFixed(2)}, flagged=true. Ragione: ${args.reason}`,
  };
}

async function listBeliefs(args: any, env: Env): Promise<any> {
  const minStatus = args.min_status || "weak_belief";
  const includeFlagged: boolean = args.include_flagged ?? true;

  let q = `beliefs?status=neq.retired&order=confidence.desc&select=belief_key,belief_text,status,confidence,evidence_n,source,source_metadata,flagged,flag_reason,last_updated_at`;
  if (!includeFlagged) q += `&flagged=eq.false`;
  if (args.category) q += `&category=eq.${encodeURIComponent(args.category)}`;

  const rows = await sb(env, q);
  const STATUS_RANK: Record<string, number> = { hypothesis: 1, weak_belief: 2, validated_belief: 3, strong_belief: 4 };
  const minRank = STATUS_RANK[minStatus] || 1;
  const filtered = (rows || []).filter((r: any) => (STATUS_RANK[r.status] || 0) >= minRank);

  const flagged = filtered.filter((r: any) => r.flagged);
  const active = filtered.filter((r: any) => !r.flagged);

  return {
    generated_at: new Date().toISOString(),
    total: filtered.length,
    flagged: flagged.map((r: any) => ({
      belief_key: r.belief_key,
      text: r.belief_text,
      status: r.status,
      confidence: r.confidence,
      source: r.source,
      flag_reason: r.flag_reason,
    })),
    active: active.map((r: any) => ({
      belief_key: r.belief_key,
      text: r.belief_text,
      status: r.status,
      confidence: r.confidence,
      evidence_n: r.evidence_n,
      source: r.source,
      source_metadata: r.source_metadata,
    })),
    tip: flagged.length > 0
      ? `${flagged.length} beliefs flaggate — usa refute_belief per ridurne la confidence o escludile dalla review.`
      : undefined,
  };
}
