/**
 * Telegram Bot — Cloudflare Worker
 *
 * Funzioni:
 *  - Webhook handler per messaggi Telegram
 *  - Allow-list su chat_id (single user)
 *  - Comandi: /brief /log /rpe /debrief /status /help
 *  - Parsing testo libero → subjective_log
 *  - Trascrizione vocali: NON usa Whisper API (costo €). Suggerisce dictation iOS.
 *
 * Idempotenza: dedup via update_id.
 */

interface Env {
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_ALLOWED_CHAT_ID: string;
  SUPABASE_URL: string;
  SUPABASE_SERVICE_KEY: string;
  PROCESSED_UPDATES: KVNamespace; // for dedup
}

interface TelegramUpdate {
  update_id: number;
  message?: {
    message_id: number;
    chat: { id: number };
    from: { id: number; first_name: string };
    text?: string;
    voice?: { file_id: string; duration: number };
    date: number;
  };
  callback_query?: {
    id: string;
    data: string;
    message?: {
      message_id: number;
      chat: { id: number };
      text?: string;
    };
    from: { id: number };
  };
}

const HELP = `<b>Comandi</b>:
/brief — brief on-demand
/log &lt;testo&gt; — log libero (RPE, sensazioni, malattia, dolori)
/rpe &lt;1-10&gt; — RPE rapido ultima sessione
/debrief — avvia debrief serale
/budget — stato budget API Anthropic
/status — stato sync e dati recenti
/help — questo messaggio

<i>Vocali: usa il microfono della tastiera iOS per trascrivere prima di mandare.</i>`;

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST") return new Response("OK", { status: 200 });

    const update = (await req.json()) as TelegramUpdate;

    // Dedup
    const seenKey = `upd:${update.update_id}`;
    if (await env.PROCESSED_UPDATES.get(seenKey)) {
      return new Response("OK");
    }
    await env.PROCESSED_UPDATES.put(seenKey, "1", { expirationTtl: 86400 });

    if (!update.message) return new Response("OK");

    // Allow-list
    const chatId = update.message.chat.id;
    if (String(chatId) !== env.TELEGRAM_ALLOWED_CHAT_ID) {
      console.log("Rejected chat_id", chatId);
      return new Response("OK");
    }

    if (update.message.voice) {
      await sendMessage(env, chatId,
        "🎤 Vocali non supportati (per restare a costo €0).\n\nUsa il microfono della tastiera iOS: tieni premuto sulla barra spaziatrice → dettatura → manda il testo.");
      return new Response("OK");
    }

    if (update.callback_query) {
      const chatId = update.callback_query.message?.chat.id || update.callback_query.from.id;
      if (String(chatId) !== env.TELEGRAM_ALLOWED_CHAT_ID) {
        return new Response("OK");
      }
      try {
        await handleCallbackQuery(env, update.callback_query);
      } catch (e: any) {
        await sendMessage(env, chatId, `Errore callback: ${e.message || e}`);
      }
      return new Response("OK");
    }

    const text = update.message?.text || "";
    if (text) {
      try {
        await handleCommand(env, chatId, text);
      } catch (e: any) {
        await sendMessage(env, chatId, `Errore: ${e.message || e}`);
      }
    }
    return new Response("OK");
  },
};

async function handleCallbackQuery(env: Env, query: any): Promise<void> {
  const data = query.data;
  const chatId = query.message?.chat.id || query.from.id;
  const messageId = query.message?.message_id;

  // Answer callback query
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_query_id: query.id }),
  });

  if (data.startsWith("accept_mod_") || data.startsWith("reject_mod_") || data.startsWith("discuss_mod_")) {
    const parts = data.split("_");
    const action = parts[0];
    const modId = parts.slice(2).join("_");

    let status = "proposed";
    let msg = "";

    if (action === "accept") {
      status = "accepted";
      msg = "✅ Modulazione accettata. È stata registrata su DB. (Esegui lo script python di apply_modulation per finalizzare, o chiedi a Claude Code)";
    } else if (action === "reject") {
      status = "rejected";
      msg = "❌ Modulazione rifiutata. Il piano rimane invariato.";
    } else if (action === "discuss") {
      status = "discussing";
      msg = "💬 D'accordo. Apri Claude Code quando vuoi e discuteremo le alternative.";
    }
    
    // Aggiorna DB
    await fetch(`${env.SUPABASE_URL}/rest/v1/plan_modulations?id=eq.${modId}`, {
      method: "PATCH",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
      },
      body: JSON.stringify({ status: status, resolved_at: new Date().toISOString() }),
    });

    await sendMessage(env, chatId, msg);
    
    // Rimuovi bottoni
    if (messageId) {
       await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, message_id: messageId, reply_markup: { inline_keyboard: [] } }),
      });
    }
  }
}

async function handleCommand(env: Env, chatId: number, text: string | undefined): Promise<void> {
  // Security P0: Reject unauthorized users
  if (chatId.toString() !== env.TELEGRAM_CHAT_ID) {
    console.warn(`Unauthorized access attempt from chatId: ${chatId}`);
    return;
  }

  // Graceful failure for audio/photo messages
  if (!text) {
    await sendMessage(env, chatId, "Invia solo testo, non accetto media o audio per ora.");
    return;
  }

  const t = text.trim();

  // Stato conversazionale: se siamo in attesa di debrief, il prossimo messaggio
  // non-comando viene parsato come evening_debrief (non come free_note)
  const debriefKey = `debrief:${chatId}`;
  const awaitingDebrief = await env.PROCESSED_UPDATES.get(debriefKey);

  if (awaitingDebrief && !t.startsWith("/")) {
    // Risposta al debrief — parsa come evening_debrief
    await env.PROCESSED_UPDATES.delete(debriefKey);
    const parsed = parseDebrief(t);
    await insertSubjective(env, { kind: "evening_debrief", ...parsed.fields, raw_text: t });
    return sendMessage(env, chatId, `✅ Debrief salvato${parsed.summary ? ` (${parsed.summary})` : ""}.`);
  }

  // Se manda un comando mentre è in attesa debrief, cancella lo stato e processa il comando
  if (awaitingDebrief && t.startsWith("/")) {
    await env.PROCESSED_UPDATES.delete(debriefKey);
  }

  if (t === "/help" || t === "/start") {
    return sendMessage(env, chatId, HELP);
  }

  if (t === "/brief") {
    // Trigger workflow brief manuale via repository_dispatch (futuro) o fallback diretto
    return sendMessage(env, chatId, "Brief richiesto. Sarà generato dal prossimo cron — per ora apri Claude.ai per analisi on-demand.");
  }

  if (t === "/status") {
    const status = await getStatus(env);
    return sendMessage(env, chatId, status);
  }

  if (t === "/budget") {
    const budgetStats = await getBudgetStats(env);
    return sendMessage(env, chatId, budgetStats);
  }

  if (t.startsWith("/rpe ")) {
    const n = parseInt(t.split(" ")[1], 10);
    if (isNaN(n) || n < 1 || n > 10) {
      return sendMessage(env, chatId, "Uso: /rpe &lt;1-10&gt;");
    }
    await insertSubjective(env, { kind: "post_session", rpe: n, raw_text: t });
    return sendMessage(env, chatId, `✅ RPE ${n} registrato.`);
  }

  if (t.startsWith("/log ")) {
    const body = t.substring(5).trim();
    const parsed = parseLog(body);
    await insertSubjective(env, { kind: parsed.kind, ...parsed.fields, raw_text: body });
    return sendMessage(env, chatId, `✅ Log salvato${parsed.summary ? ` (${parsed.summary})` : ""}.`);
  }

  if (t === "/debrief") {
    // Setta stato conversazionale: il prossimo messaggio sarà parsato come debrief
    await env.PROCESSED_UPDATES.put(debriefKey, "1", { expirationTtl: 3600 }); // scade dopo 1h
    return sendMessage(env, chatId,
      `<b>Debrief serale</b>\n\nRispondi in un solo messaggio con:\n` +
      `1. RPE sessione principale (1-10)\n` +
      `2. Sensazioni (libero)\n` +
      `3. Dolori? (no / dove)\n` +
      `4. Energia residua e sonno previsto\n\n` +
      `<i>Esempio: "RPE 7, gambe pesanti seconda metà, no dolori, energia bassa, dormo presto"</i>`);
  }

  // Se il testo libero sembra un debrief (contiene RPE), parsa automaticamente
  if (/rpe\s*\d{1,2}/i.test(t)) {
    const parsed = parseDebrief(t);
    await insertSubjective(env, { kind: "evening_debrief", ...parsed.fields, raw_text: t });
    return sendMessage(env, chatId, `✅ Riconosciuto debrief e salvato${parsed.summary ? ` (${parsed.summary})` : ""}.`);
  }

  // Testo libero → free_note
  await insertSubjective(env, { kind: "free_note", raw_text: t });
  await sendMessage(env, chatId, "📝 Salvato come nota libera. Comandi: /help");
}

// ============================================================================
// Parsing log testo libero (deterministico, no LLM)
// ============================================================================
function parseLog(body: string): { kind: string; fields: any; summary: string } {
  const lower = body.toLowerCase();
  const fields: any = {};
  const summary: string[] = [];

  // RPE
  const rpeMatch = body.match(/rpe\s*(\d{1,2})/i);
  if (rpeMatch) {
    const v = parseInt(rpeMatch[1], 10);
    if (v >= 1 && v <= 10) {
      fields.rpe = v;
      summary.push(`RPE ${v}`);
    }
  }

  // Soreness
  const sorMatch = body.match(/(soreness|dolore muscolare)\s*(\d{1,2})/i);
  if (sorMatch) {
    const v = parseInt(sorMatch[2], 10);
    if (v >= 0 && v <= 10) {
      fields.soreness = v;
      summary.push(`soreness ${v}`);
    }
  }

  // Illness
  if (/\b(malato|malata|febbre|raffreddore|influenza|mal di gola|tosse|covid)\b/i.test(lower)) {
    fields.illness_flag = true;
    fields.illness_details = body.slice(0, 200);
    summary.push("malattia");
    return { kind: "illness", fields, summary: summary.join(", ") };
  }

  // Injury
  const noPainRegex = /\b(no dolori|nessun dolore|no pain|niente dolori|no dolore|zero dolori)\b/i;
  if (!noPainRegex.test(lower) && /\b(dolore|infortunio|tendine|stiramento|contrattura|gonfio|male)\b/i.test(lower)) {
    fields.injury_flag = true;
    fields.injury_details = body.slice(0, 200);
    // Try locate
    const locMatch = body.match(/\b(ginocchio|caviglia|polpaccio|tendine d'achille|achille|coscia|adduttore|spalla|schiena|lombare|piede|tallone)\b/i);
    if (locMatch) fields.injury_location = locMatch[1];
    summary.push("infortunio");
    return { kind: "injury", fields, summary: summary.join(", ") };
  }

  // Motivation
  const motMatch = body.match(/motivazione\s*(\d{1,2})/i);
  if (motMatch) {
    const v = parseInt(motMatch[1], 10);
    if (v >= 1 && v <= 10) {
      fields.motivation = v;
      summary.push(`motivation ${v}`);
    }
  }

  // Default
  return {
    kind: fields.rpe !== undefined ? "post_session" : "free_note",
    fields,
    summary: summary.join(", "),
  };
}

// ============================================================================
// Parsing debrief serale (deterministico, no LLM)
// Colonne esistenti in subjective_log: rpe, soreness, motivation,
//   illness_flag, illness_details, injury_flag, injury_details, injury_location,
//   raw_text, parsed_data (JSONB)
// Tutto ciò che non è una colonna nativa va in parsed_data.
// ============================================================================
function parseDebrief(body: string): { fields: any; summary: string } {
  const fields: any = {};
  const parsed: any = {};
  const summary: string[] = [];
  const lower = body.toLowerCase();

  // RPE → colonna nativa
  const rpeMatch = body.match(/rpe\s*(\d{1,2})/i);
  if (rpeMatch) {
    const v = parseInt(rpeMatch[1], 10);
    if (v >= 1 && v <= 10) {
      fields.rpe = v;
      summary.push(`RPE ${v}`);
    }
  }

  // Soreness → colonna nativa
  const sorMatch = body.match(/(soreness|dolore muscolare)\s*(\d{1,2})/i);
  if (sorMatch) {
    const v = parseInt(sorMatch[2], 10);
    if (v >= 0 && v <= 10) {
      fields.soreness = v;
    }
  }

  // Motivation → colonna nativa
  const motMatch = body.match(/motivazione\s*(\d{1,2})/i);
  if (motMatch) {
    const v = parseInt(motMatch[1], 10);
    if (v >= 1 && v <= 10) {
      fields.motivation = v;
      summary.push(`motivation ${v}`);
    }
  }

  // Illness → colonna nativa (stessa logica di parseLog)
  if (/\b(malato|malata|febbre|raffreddore|influenza|mal di gola|tosse|covid)\b/i.test(lower)) {
    fields.illness_flag = true;
    fields.illness_details = body.slice(0, 200);
    summary.push("malattia");
  }

  // Injury → colonna nativa (stessa logica di parseLog)
  const noPainRegex = /\b(no dolori|nessun dolore|no pain|niente dolori|no dolore|zero dolori)\b/i;
  if (!noPainRegex.test(lower) && /\b(dolore|infortunio|tendine|stiramento|contrattura|gonfio|male)\b/i.test(lower)) {
    fields.injury_flag = true;
    fields.injury_details = body.slice(0, 200);
    const locMatch = body.match(/\b(ginocchio|caviglia|polpaccio|tendine d'achille|achille|coscia|adduttore|spalla|schiena|lombare|piede|tallone)\b/i);
    if (locMatch) fields.injury_location = locMatch[1];
    summary.push("infortunio");
  }

  // Dolori → parsed_data (pain_reported, pain_location non sono colonne native)
  if (/\b(no dolori|nessun dolore|no pain|niente dolori)\b/i.test(lower)) {
    parsed.pain_reported = false;
  } else if (/\b(dolore|dolori|male|fastidio)\b/i.test(lower)) {
    parsed.pain_reported = true;
    const locMatch = body.match(/\b(ginocchio|caviglia|polpaccio|tendine d'achille|achille|coscia|adduttore|spalla|schiena|lombare|piede|tallone|anca|quadricipite|gluteo)\b/i);
    if (locMatch) parsed.pain_location = locMatch[1];
  }

  // Energia → parsed_data
  if (/\b(energia alta|fresco|riposato)\b/i.test(lower)) {
    parsed.energy = "high";
  } else if (/\b(energia media|normale)\b/i.test(lower)) {
    parsed.energy = "medium";
  } else if (/\b(energia bassa|stanco|scarico|distrutto|cotto)\b/i.test(lower)) {
    parsed.energy = "low";
  }

  // Sensazioni → parsed_data
  parsed.sensations = body.slice(0, 500);

  // Metti tutto il parsing strutturato in parsed_data (colonna JSONB)
  fields.parsed_data = parsed;

  return { fields, summary: summary.join(", ") };
}

// ============================================================================
// Supabase REST
// ============================================================================
async function insertSubjective(env: Env, payload: any): Promise<void> {
  const body = {
    logged_at: new Date().toISOString(),
    ...payload,
  };
  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/subjective_log`, {
    method: "POST",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": "return=minimal",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`Supabase insert failed: ${resp.status} ${await resp.text()}`);
  }
}

async function getStatus(env: Env): Promise<string> {
  const resp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/health?select=component,last_success_at,failure_count`,
    {
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      },
    }
  );
  const rows = (await resp.json()) as any[];
  const lines = ["<b>📡 Status</b>"];
  for (const r of rows) {
    const last = r.last_success_at ? new Date(r.last_success_at) : null;
    const ago = last ? Math.round((Date.now() - last.getTime()) / 3600000) : null;
    const emoji = ago === null ? "⚪" : ago < 6 ? "🟢" : ago < 24 ? "🟡" : "🔴";
    lines.push(`${emoji} ${r.component}: ${ago !== null ? ago + "h fa" : "mai"}${r.failure_count > 0 ? ` (${r.failure_count} fail)` : ""}`);
  }
  return lines.join("\n");
}

async function getBudgetStats(env: Env): Promise<string> {
  const now = new Date();
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString();
  
  const resp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/api_usage?timestamp=gte.${monthStart}&select=cost_usd_estimated,success`,
    {
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      },
    }
  );
  if (!resp.ok) return "Errore nel recupero budget.";
  
  const rows = (await resp.json()) as any[];
  
  let totalCost = 0;
  let successful = 0;
  for (const r of rows) {
    totalCost += parseFloat(r.cost_usd_estimated || "0");
    if (r.success) successful++;
  }
  
  const limit = 5.00;
  const pct = ((totalCost / limit) * 100).toFixed(1);
  const remaining = limit - totalCost;
  
  let level = "🟢 OK";
  if (totalCost > 4.8) level = "🔴 BLOCKED";
  else if (totalCost > 4.5) level = "🟠 DEGRADED";
  else if (totalCost > 4.0) level = "🟡 WARNING";
  
  return `<b>💰 Budget API Mensile</b>
Stato: ${level}
Spesa: $${totalCost.toFixed(2)} / $${limit.toFixed(2)} (${pct}%)
Rimanente: $${remaining.toFixed(2)}
Chiamate totali: ${rows.length} (${successful} OK)`;
}

async function sendMessage(env: Env, chatId: number, text: string): Promise<void> {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
    }),
  });
}
