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
}

const HELP = `<b>Comandi</b>:
/brief — brief on-demand
/log &lt;testo&gt; — log libero (RPE, sensazioni, malattia, dolori)
/rpe &lt;1-10&gt; — RPE rapido ultima sessione
/debrief — avvia debrief serale
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

    const text = update.message.text || "";
    try {
      await handleCommand(env, chatId, text);
    } catch (e: any) {
      await sendMessage(env, chatId, `Errore: ${e.message || e}`);
    }
    return new Response("OK");
  },
};

async function handleCommand(env: Env, chatId: number, text: string): Promise<void> {
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
  if (/\b(dolore|infortunio|tendine|stiramento|contrattura|gonfio)\b/i.test(lower)) {
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
// ============================================================================
function parseDebrief(body: string): { fields: any; summary: string } {
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

  // Dolori
  const lower = body.toLowerCase();
  if (/\b(no dolori|nessun dolore|no pain|niente dolori)\b/i.test(lower)) {
    fields.pain_reported = false;
  } else if (/\b(dolore|dolori|male|fastidio)\b/i.test(lower)) {
    fields.pain_reported = true;
    const locMatch = body.match(/\b(ginocchio|caviglia|polpaccio|tendine d'achille|achille|coscia|adduttore|spalla|schiena|lombare|piede|tallone|anca|quadricipite|gluteo)\b/i);
    if (locMatch) fields.pain_location = locMatch[1];
  }

  // Energia
  if (/\b(energia alta|fresco|riposato)\b/i.test(lower)) {
    fields.energy = "high";
  } else if (/\b(energia media|normale)\b/i.test(lower)) {
    fields.energy = "medium";
  } else if (/\b(energia bassa|stanco|scarico|distrutto|cotto)\b/i.test(lower)) {
    fields.energy = "low";
  }

  // Sensazioni (tutto il testo va come campo sensations)
  fields.sensations = body.slice(0, 500);

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
