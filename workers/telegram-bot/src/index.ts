/**
 * Telegram Bot — Cloudflare Worker (Step 6.6)
 *
 * Feature:
 *  - Reply threading: bot legge reply_to_message e instrada al parser corretto
 *  - Conferma azioni rischiose: injury/illness chiedono conferma prima di salvare
 *  - /undo: annulla ultimo log (30 min)
 *  - /history: lista log recenti con filtri
 *  - Help contestuale: se parser non capisce, chiede classificazione
 *  - Idempotenza: dedup su update_id e callback_query_id via KV
 *  - Proactive question buttons: Rispondo dopo / Salta / Disabilita oggi
 *
 * Comandi: /brief /log /rpe /debrief /status /budget /undo /history /help
 */

// ============================================================================
// Tipi
// ============================================================================

interface Env {
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_ALLOWED_CHAT_ID: string;
  SUPABASE_URL: string;
  SUPABASE_SERVICE_KEY: string;
  PROCESSED_UPDATES: KVNamespace;
}

interface TelegramMessage {
  message_id: number;
  chat: { id: number };
  from: { id: number; first_name: string };
  text?: string;
  voice?: { file_id: string; duration: number };
  date: number;
  reply_to_message?: {
    message_id: number;
    text?: string;
  };
}

interface CallbackQuery {
  id: string;
  data: string;
  message?: {
    message_id: number;
    chat: { id: number };
    text?: string;
  };
  from: { id: number };
}

interface TelegramUpdate {
  update_id: number;
  message?: TelegramMessage;
  callback_query?: CallbackQuery;
}

interface BotMessage {
  id: number;
  telegram_message_id: number;
  chat_id: number;
  sent_at: string;
  purpose: string;
  context_data: any;
  parent_workflow: string | null;
  expires_at: string | null;
}

interface PendingConfirmation {
  id: string;
  chat_id: number;
  original_message_id: number;
  confirmation_message_id: number;
  parsed_action: string;
  parsed_data: any;
  status: string;
  expires_at: string | null;
}

// ============================================================================
// Testi statici
// ============================================================================

const HELP = `<b>Comandi</b>:
/brief — brief on-demand
/log &lt;testo&gt; — log libero (RPE, sensazioni, malattia, dolori)
/rpe &lt;1-10&gt; — RPE rapido ultima sessione
/debrief — avvia debrief serale
/undo — annulla ultimo log (ultimi 30 min)
/history [7d|rpe|injury] — lista log recenti
/budget — stato budget API AI
/status — stato sync e dati recenti
/help — questo messaggio

<b>Reply threading</b>: rispondi direttamente ai messaggi del bot (brief, reminder debrief, domande) per dare contesto automatico.

<i>Vocali: usa il microfono della tastiera iOS per trascrivere prima di mandare.</i>`;

// ============================================================================
// Entry point
// ============================================================================

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST") return new Response("OK", { status: 200 });

    const update = (await req.json()) as TelegramUpdate;

    // Dedup update (Telegram retry)
    const seenKey = `upd:${update.update_id}`;
    if (await env.PROCESSED_UPDATES.get(seenKey)) {
      return new Response("OK");
    }
    await env.PROCESSED_UPDATES.put(seenKey, "1", { expirationTtl: 86400 });

    // Callback query (bottoni inline)
    if (update.callback_query) {
      const cbChatId = update.callback_query.message?.chat.id ?? update.callback_query.from.id;
      if (String(cbChatId) !== env.TELEGRAM_ALLOWED_CHAT_ID) return new Response("OK");

      // Dedup callback (doppio click)
      const cbKey = `cbq:${update.callback_query.id}`;
      if (await env.PROCESSED_UPDATES.get(cbKey)) {
        await answerCallback(env, update.callback_query.id);
        return new Response("OK");
      }
      await env.PROCESSED_UPDATES.put(cbKey, "1", { expirationTtl: 300 });

      try {
        await handleCallbackQuery(env, update.callback_query);
      } catch (e: any) {
        await sendMessage(env, cbChatId, `Errore callback: ${e.message || e}`);
      }
      return new Response("OK");
    }

    if (!update.message) return new Response("OK");

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
    if (!text) return new Response("OK");

    try {
      await handleMessage(env, update.message);
    } catch (e: any) {
      await sendMessage(env, chatId, `Errore: ${e.message || e}`);
    }
    return new Response("OK");
  },
};

// ============================================================================
// Routing principale
// ============================================================================

async function handleMessage(env: Env, message: TelegramMessage): Promise<void> {
  const chatId = message.chat.id;
  const text = message.text || "";

  // Reply threading: se l'utente fa swipe-reply su un messaggio del bot
  if (message.reply_to_message) {
    const botMsg = await getBotMessage(env, message.reply_to_message.message_id);
    if (botMsg) {
      return handleContextualReply(env, message, botMsg);
    }
    // Il messaggio a cui si risponde non è del bot (o è stato pulito dal cleanup)
    // Fallthrough al parser standalone
  }

  return handleStandalone(env, message);
}

// ============================================================================
// Reply threading: parser contestuale
// ============================================================================

async function handleContextualReply(
  env: Env,
  message: TelegramMessage,
  botMsg: BotMessage,
): Promise<void> {
  const chatId = message.chat.id;
  const text = message.text || "";

  switch (botMsg.purpose) {
    case "debrief_reminder": {
      // Risposta al reminder → parser debrief
      const parsed = parseDebrief(text);
      if (parsed.fields.injury_flag || parsed.fields.illness_flag) {
        return createPendingAndAsk(env, chatId, message.message_id, parsed.fields.injury_flag ? "log_injury" : "log_illness", {
          kind: "evening_debrief",
          ...parsed.fields,
          raw_text: text,
        });
      }
      await insertSubjective(env, { kind: "evening_debrief", ...parsed.fields, raw_text: text });
      await sendAndLogMessage(env, chatId,
        `✅ Debrief salvato${parsed.summary ? ` (${parsed.summary})` : ""}.`,
        "generic");
      return;
    }

    case "morning_brief": {
      // Risposta al brief → salva come brief_response (commento, non debrief)
      await insertSubjective(env, { kind: "brief_response", raw_text: text });
      await sendAndLogMessage(env, chatId, "📝 Commento al brief salvato.", "generic");
      return;
    }

    case "proactive_question": {
      // Risposta a domanda proattiva → proactive_response con contesto categoria
      const category = botMsg.context_data?.category || "general";
      const question = botMsg.context_data?.question || "";
      await insertSubjective(env, {
        kind: "proactive_response",
        raw_text: text,
        parsed_data: { category, question, response: text.slice(0, 500) },
      });
      await sendAndLogMessage(env, chatId, `✅ Risposta registrata (${category}).`, "generic");
      return;
    }

    case "modulation_proposal":
      // Le risposte alle modulazioni vanno via bottoni inline, non testo
      await sendMessage(env, chatId, "Per le proposte di modulazione usa i bottoni ✅/❌/💬 sotto il messaggio.");
      return;

    case "pattern_observation": {
      // L'utente corregge/conferma un pattern
      await insertSubjective(env, {
        kind: "pattern_correction",
        raw_text: text,
        parsed_data: { original_pattern: botMsg.context_data },
      });
      await sendAndLogMessage(env, chatId, "✅ Correzione pattern registrata.", "generic");
      return;
    }

    default:
      // Fallback: parser standalone
      return handleStandalone(env, message);
  }
}

// ============================================================================
// Parser standalone (senza contesto reply)
// ============================================================================

async function handleStandalone(env: Env, message: TelegramMessage): Promise<void> {
  const chatId = message.chat.id;
  const text = message.text || "";
  const t = text.trim();

  // Stato conversazionale: debrief in corso
  const debriefKey = `debrief:${chatId}`;
  const awaitingDebrief = await env.PROCESSED_UPDATES.get(debriefKey);

  if (awaitingDebrief && !t.startsWith("/")) {
    await env.PROCESSED_UPDATES.delete(debriefKey);
    const parsed = parseDebrief(t);
    if (parsed.fields.injury_flag || parsed.fields.illness_flag) {
      return createPendingAndAsk(env, chatId, message.message_id,
        parsed.fields.injury_flag ? "log_injury" : "log_illness",
        { kind: "evening_debrief", ...parsed.fields, raw_text: t });
    }
    await insertSubjective(env, { kind: "evening_debrief", ...parsed.fields, raw_text: t });
    await sendMessage(env, chatId, `✅ Debrief salvato${parsed.summary ? ` (${parsed.summary})` : ""}.`);
    return;
  }

  if (awaitingDebrief && t.startsWith("/")) {
    await env.PROCESSED_UPDATES.delete(debriefKey);
  }

  // Comandi
  if (t === "/help" || t === "/start") {
    return sendAndLogMessage(env, chatId, HELP, "help");
  }

  if (t === "/brief") {
    return sendMessage(env, chatId, "Brief richiesto. Sarà generato dal prossimo cron — per ora apri Claude.ai per analisi on-demand.");
  }

  if (t === "/status") {
    const status = await getStatus(env);
    return sendAndLogMessage(env, chatId, status, "status_response");
  }

  if (t === "/budget") {
    const budgetStats = await getBudgetStats(env);
    return sendAndLogMessage(env, chatId, budgetStats, "budget_response");
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
    if (parsed.fields.injury_flag || parsed.fields.illness_flag) {
      return createPendingAndAsk(env, chatId, message.message_id, parsed.fields.injury_flag ? "log_injury" : "log_illness", {
        kind: parsed.kind,
        ...parsed.fields,
        raw_text: body,
      });
    }
    await insertSubjective(env, { kind: parsed.kind, ...parsed.fields, raw_text: body });
    return sendMessage(env, chatId, `✅ Log salvato${parsed.summary ? ` (${parsed.summary})` : ""}.`);
  }

  if (t === "/debrief") {
    await env.PROCESSED_UPDATES.put(debriefKey, "1", { expirationTtl: 3600 });
    return sendAndLogMessage(env, chatId,
      `<b>Debrief serale</b>\n\nRispondi in un solo messaggio con:\n` +
      `1. RPE sessione principale (1-10)\n` +
      `2. Sensazioni (libero)\n` +
      `3. Dolori? (no / dove)\n` +
      `4. Energia residua e sonno previsto\n\n` +
      `<i>Esempio: "RPE 7, gambe pesanti seconda metà, no dolori, energia bassa, dormo presto"</i>`,
      "debrief_reminder");
  }

  if (t === "/undo") {
    return handleUndo(env, chatId);
  }

  if (t.startsWith("/history")) {
    const args = t.substring(8).trim();
    return handleHistory(env, chatId, args);
  }

  // Auto-riconoscimento debrief: testo che inizia con RPE o contiene "debrief"
  if (/rpe\s*\d{1,2}/i.test(t) || /\bdebrief\b/i.test(t)) {
    const parsed = parseDebrief(t);
    if (parsed.fields.injury_flag || parsed.fields.illness_flag) {
      return createPendingAndAsk(env, chatId, message.message_id,
        parsed.fields.injury_flag ? "log_injury" : "log_illness",
        { kind: "evening_debrief", ...parsed.fields, raw_text: t });
    }
    await insertSubjective(env, { kind: "evening_debrief", ...parsed.fields, raw_text: t });
    return sendMessage(env, chatId, `✅ Riconosciuto debrief e salvato${parsed.summary ? ` (${parsed.summary})` : ""}.`);
  }

  // Parsing testo libero
  const parsed = parseLog(t);
  if (parsed.fields.injury_flag || parsed.fields.illness_flag) {
    return createPendingAndAsk(env, chatId, message.message_id,
      parsed.fields.injury_flag ? "log_injury" : "log_illness",
      { kind: parsed.kind, ...parsed.fields, raw_text: t });
  }

  // Se il parser ha estratto qualcosa, salva
  const hasData = parsed.fields.rpe !== undefined || parsed.fields.soreness !== undefined || parsed.fields.motivation !== undefined;
  if (hasData) {
    await insertSubjective(env, { kind: parsed.kind, ...parsed.fields, raw_text: t });
    await sendMessage(env, chatId, `✅ Log salvato${parsed.summary ? ` (${parsed.summary})` : ""}.`);
    return;
  }

  // Feature 5: help contestuale — il parser non ha capito nulla
  return askClassification(env, chatId, message.message_id, t);
}

// ============================================================================
// Feature 3: /undo
// ============================================================================

async function handleUndo(env: Env, chatId: number): Promise<void> {
  const thirtyMinAgo = new Date(Date.now() - 30 * 60 * 1000).toISOString();
  const resp = await supabaseFetch(env, `/rest/v1/subjective_log?logged_at=gte.${thirtyMinAgo}&order=logged_at.desc&limit=1&select=id,kind,rpe,injury_flag,illness_flag,raw_text,logged_at`);
  const rows = await resp.json() as any[];

  if (!rows.length) {
    await sendMessage(env, chatId, "Nessun log negli ultimi 30 minuti da annullare.");
    return;
  }

  const log = rows[0];
  const logDate = new Date(log.logged_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  const flags = [log.injury_flag && "🩹 infortunio", log.illness_flag && "🤒 malattia"].filter(Boolean).join(", ");
  const preview = log.raw_text?.slice(0, 100) || log.kind;

  const msg = `<b>Ultimo log (${logDate})</b>\nTipo: ${log.kind}${log.rpe ? ` · RPE ${log.rpe}` : ""}${flags ? ` · ${flags}` : ""}\nTesto: <i>${preview}</i>\n\nAnnullo?`;
  const keyboard = {
    inline_keyboard: [[
      { text: "✅ Sì, annulla", callback_data: `undo_confirm_${log.id}` },
      { text: "❌ No, mantieni", callback_data: "undo_cancel" },
    ]],
  };

  await sendMessage(env, chatId, msg, keyboard);
}

// ============================================================================
// Feature 4: /history
// ============================================================================

async function handleHistory(env: Env, chatId: number, args: string): Promise<void> {
  let filter = "";
  let label = "ultimi 10 log";

  if (args === "rpe") {
    filter = "&rpe=not.is.null";
    label = "log con RPE";
  } else if (args === "injury") {
    filter = "&injury_flag=eq.true";
    label = "log infortuni";
  } else if (args.match(/^(\d+)d$/)) {
    const days = parseInt(args, 10);
    const since = new Date(Date.now() - days * 86400 * 1000).toISOString();
    filter = `&logged_at=gte.${since}`;
    label = `ultimi ${days} giorni`;
  }

  const resp = await supabaseFetch(env, `/rest/v1/subjective_log?order=logged_at.desc&limit=10${filter}&select=id,kind,rpe,soreness,injury_flag,illness_flag,raw_text,logged_at`);
  const rows = await resp.json() as any[];

  if (!rows.length) {
    await sendMessage(env, chatId, `Nessun log trovato (${label}).`);
    return;
  }

  const lines = [`<b>📋 History — ${label}</b>\n`];
  for (const r of rows) {
    const dt = new Date(r.logged_at).toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" }) +
               " " + new Date(r.logged_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    const flags = [r.injury_flag && "🩹", r.illness_flag && "🤒"].filter(Boolean).join("");
    const rpeStr = r.rpe ? ` RPE${r.rpe}` : "";
    const sor = r.soreness !== null && r.soreness !== undefined ? ` sor${r.soreness}` : "";
    const raw = r.raw_text?.slice(0, 60) || r.kind;
    lines.push(`${dt} <code>${r.kind}</code>${rpeStr}${sor}${flags}\n<i>${raw}</i>`);
  }

  await sendMessage(env, chatId, lines.join("\n"));
}

// ============================================================================
// Feature 2: pending_confirmations — azioni rischiose
// ============================================================================

async function createPendingAndAsk(
  env: Env,
  chatId: number,
  originalMsgId: number,
  action: string,
  parsedData: any,
): Promise<void> {
  const actionLabel = action === "log_injury" ? "infortunio" : "malattia";
  const location = parsedData.injury_location ? ` alla ${parsedData.injury_location}` : "";
  const text = `Ho capito che hai un <b>${actionLabel}${location}</b>.\n\nSalvo con flag attivo e attivo il monitoraggio?`;

  const keyboard = {
    inline_keyboard: [[
      { text: "✅ Sì", callback_data: `confirm_action_PLACEHOLDER` },
      { text: "✏️ Correggi", callback_data: `correct_action_PLACEHOLDER` },
      { text: "❌ Era altro", callback_data: `reject_action_PLACEHOLDER` },
    ]],
  };

  // Prima manda il messaggio per ottenere il message_id
  const confMsgId = await sendMessageGetId(env, chatId, text, keyboard);
  if (!confMsgId) return;

  // Ora salva pending_confirmation con i veri message_id
  const record = {
    chat_id: chatId,
    original_message_id: originalMsgId,
    confirmation_message_id: confMsgId,
    parsed_action: action,
    parsed_data: parsedData,
    status: "pending",
  };

  const res = await supabaseFetch(env, "/rest/v1/pending_confirmations", "POST", record, { Prefer: "return=representation" });
  if (!res.ok) return;
  const data = await res.json() as any[];
  const pendingId = data[0]?.id;
  if (!pendingId) return;

  // Aggiorna i bottoni con il vero pending_id
  const realKeyboard = {
    inline_keyboard: [[
      { text: "✅ Sì", callback_data: `confirm_action_${pendingId}` },
      { text: "✏️ Correggi", callback_data: `correct_action_${pendingId}` },
      { text: "❌ Era altro", callback_data: `reject_action_${pendingId}` },
    ]],
  };

  await editMessageReplyMarkup(env, chatId, confMsgId, realKeyboard);
}

// ============================================================================
// Feature 5: help contestuale
// ============================================================================

async function askClassification(
  env: Env,
  chatId: number,
  originalMsgId: number,
  rawText: string,
): Promise<void> {
  const text = "Non sono sicuro di aver capito. Vuoi che salvi come:";
  const keyboard = {
    inline_keyboard: [[
      { text: "📝 Nota libera", callback_data: "classify_note_PLACEHOLDER" },
      { text: "🩹 Sintomo/dolore", callback_data: "classify_symptom_PLACEHOLDER" },
      { text: "🎯 RPE post-sessione", callback_data: "classify_rpe_PLACEHOLDER" },
    ]],
  };

  const confMsgId = await sendMessageGetId(env, chatId, text, keyboard);
  if (!confMsgId) return;

  const record = {
    chat_id: chatId,
    original_message_id: originalMsgId,
    confirmation_message_id: confMsgId,
    parsed_action: "classify",
    parsed_data: { raw_text: rawText },
    status: "pending",
  };

  const res = await supabaseFetch(env, "/rest/v1/pending_confirmations", "POST", record, { Prefer: "return=representation" });
  if (!res.ok) return;
  const data = await res.json() as any[];
  const pendingId = data[0]?.id;
  if (!pendingId) return;

  const realKeyboard = {
    inline_keyboard: [[
      { text: "📝 Nota libera", callback_data: `classify_note_${pendingId}` },
      { text: "🩹 Sintomo/dolore", callback_data: `classify_symptom_${pendingId}` },
      { text: "🎯 RPE post-sessione", callback_data: `classify_rpe_${pendingId}` },
    ]],
  };

  await editMessageReplyMarkup(env, chatId, confMsgId, realKeyboard);
}

// ============================================================================
// Callback query handler
// ============================================================================

async function handleCallbackQuery(env: Env, query: CallbackQuery): Promise<void> {
  const data = query.data;
  const chatId = query.message?.chat.id ?? query.from.id;
  const messageId = query.message?.message_id;

  await answerCallback(env, query.id);

  // --- Modulazione ---
  if (data.startsWith("accept_mod_") || data.startsWith("reject_mod_") || data.startsWith("discuss_mod_")) {
    const [action, , ...rest] = data.split("_");
    const modId = rest.join("_");
    let status = "proposed";
    let msg = "";

    if (action === "accept") { status = "accepted"; msg = "✅ Modulazione accettata. Applicherò le modifiche al piano."; }
    else if (action === "reject") { status = "rejected"; msg = "❌ Modulazione rifiutata. Piano invariato."; }
    else { status = "discussing"; msg = "💬 D'accordo. Apri Claude da smartphone/web con il connector coach quando vuoi per discutere."; }

    await supabaseFetch(env, `/rest/v1/plan_modulations?id=eq.${modId}`, "PATCH",
      { status, resolved_at: new Date().toISOString() }, { Prefer: "return=minimal" });
    await sendMessage(env, chatId, msg);
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  // --- Conferma azione rischiosa ---
  if (data.startsWith("confirm_action_")) {
    const pendingId = data.replace("confirm_action_", "");
    const pending = await getPendingConfirmation(env, pendingId);
    if (!pending || pending.status !== "pending") {
      await sendMessage(env, chatId, "Conferma già processata o scaduta.");
      return;
    }
    await insertSubjective(env, pending.parsed_data);
    await resolvePendingConfirmation(env, pendingId, "confirmed");
    await sendMessage(env, chatId, "✅ Salvato con flag attivo. Monitoro la situazione.");
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  if (data.startsWith("reject_action_")) {
    const pendingId = data.replace("reject_action_", "");
    const pending = await getPendingConfirmation(env, pendingId);
    if (!pending || pending.status !== "pending") return;
    // Salva senza flag come free_note
    const safeData = { kind: "free_note", raw_text: pending.parsed_data.raw_text };
    await insertSubjective(env, safeData);
    await resolvePendingConfirmation(env, pendingId, "rejected");
    await sendMessage(env, chatId, "📝 Salvato come nota libera (nessun flag attivato).");
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  if (data.startsWith("correct_action_")) {
    const pendingId = data.replace("correct_action_", "");
    await resolvePendingConfirmation(env, pendingId, "corrected");
    await sendMessage(env, chatId, "✏️ Cosa intendevi? Rispondi a questo messaggio con la correzione.");
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  // --- Classificazione help contestuale ---
  if (data.startsWith("classify_")) {
    const parts = data.split("_");
    const classType = parts[1];
    const pendingId = parts.slice(2).join("_");
    const pending = await getPendingConfirmation(env, pendingId);
    if (!pending || pending.status !== "pending") return;

    const rawText = pending.parsed_data.raw_text || "";
    let kind = "free_note";
    let extraFields: any = {};
    let label = "nota libera";

    if (classType === "symptom") {
      kind = "injury";
      extraFields = { injury_flag: true, injury_details: rawText.slice(0, 200) };
      label = "sintomo/dolore";
    } else if (classType === "rpe") {
      kind = "post_session";
      const m = rawText.match(/\d{1,2}/);
      if (m) extraFields = { rpe: parseInt(m[0], 10) };
      label = "RPE post-sessione";
    }

    await insertSubjective(env, { kind, raw_text: rawText, ...extraFields });
    await resolvePendingConfirmation(env, pendingId, "confirmed");
    await sendMessage(env, chatId, `✅ Salvato come <b>${label}</b>.`);
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  // --- Undo ---
  if (data.startsWith("undo_confirm_")) {
    const logId = data.replace("undo_confirm_", "");
    await supabaseFetch(env, `/rest/v1/subjective_log?id=eq.${logId}`, "DELETE");
    await sendMessage(env, chatId, "✅ Log annullato.");
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  if (data === "undo_cancel") {
    await sendMessage(env, chatId, "Ok, log mantenuto.");
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  // --- Proactive question buttons ---
  if (data === "proactive_later") {
    await sendMessage(env, chatId, "👍 Quando vuoi, rispondi al messaggio con la domanda.");
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  if (data === "proactive_skip") {
    await sendMessage(env, chatId, "Domanda saltata. Ci sentiamo prossima volta.");
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }

  if (data === "proactive_disable_today") {
    // Setto flag KV che dura fino a fine giornata
    const endOfDay = new Date();
    endOfDay.setHours(23, 59, 59, 0);
    const ttl = Math.floor((endOfDay.getTime() - Date.now()) / 1000);
    await env.PROCESSED_UPDATES.put(`proactive_disabled:${chatId}`, "1", { expirationTtl: Math.max(ttl, 60) });
    await sendMessage(env, chatId, "🚫 Domande proattive disabilitate per oggi.");
    if (messageId) await editMessageReplyMarkup(env, chatId, messageId, { inline_keyboard: [] });
    return;
  }
}

// ============================================================================
// Parsing (deterministico, no LLM)
// ============================================================================

function parseLog(body: string): { kind: string; fields: any; summary: string } {
  const lower = body.toLowerCase();
  const fields: any = {};
  const summary: string[] = [];

  const rpeMatch = body.match(/rpe\s*(\d{1,2})/i);
  if (rpeMatch) {
    const v = parseInt(rpeMatch[1], 10);
    if (v >= 1 && v <= 10) { fields.rpe = v; summary.push(`RPE ${v}`); }
  }

  const sorMatch = body.match(/(soreness|dolore muscolare)\s*(\d{1,2})/i);
  if (sorMatch) {
    const v = parseInt(sorMatch[2], 10);
    if (v >= 0 && v <= 10) { fields.soreness = v; summary.push(`soreness ${v}`); }
  }

  if (/\b(malato|malata|febbre|raffreddore|influenza|mal di gola|tosse|covid)\b/i.test(lower)) {
    fields.illness_flag = true;
    fields.illness_details = body.slice(0, 200);
    summary.push("malattia");
    return { kind: "illness", fields, summary: summary.join(", ") };
  }

  const noPainRegex = /\b(no dolori|nessun dolore|no pain|niente dolori|no dolore|zero dolori)\b/i;
  if (!noPainRegex.test(lower) && /\b(dolore|infortunio|tendine|stiramento|contrattura|gonfio|male)\b/i.test(lower)) {
    fields.injury_flag = true;
    fields.injury_details = body.slice(0, 200);
    const locMatch = body.match(/\b(ginocchio|caviglia|polpaccio|tendine d'achille|achille|coscia|adduttore|spalla|schiena|lombare|piede|tallone)\b/i);
    if (locMatch) fields.injury_location = locMatch[1];
    summary.push("infortunio");
    return { kind: "injury", fields, summary: summary.join(", ") };
  }

  const motMatch = body.match(/motivazione\s*(\d{1,2})/i);
  if (motMatch) {
    const v = parseInt(motMatch[1], 10);
    if (v >= 1 && v <= 10) { fields.motivation = v; summary.push(`motivation ${v}`); }
  }

  return {
    kind: fields.rpe !== undefined ? "post_session" : "free_note",
    fields,
    summary: summary.join(", "),
  };
}

function parseDebrief(body: string): { fields: any; summary: string } {
  const fields: any = {};
  const parsed: any = {};
  const summary: string[] = [];
  const lower = body.toLowerCase();

  const rpeMatch = body.match(/rpe\s*(\d{1,2})/i);
  if (rpeMatch) {
    const v = parseInt(rpeMatch[1], 10);
    if (v >= 1 && v <= 10) { fields.rpe = v; summary.push(`RPE ${v}`); }
  }

  const sorMatch = body.match(/(soreness|dolore muscolare)\s*(\d{1,2})/i);
  if (sorMatch) {
    const v = parseInt(sorMatch[2], 10);
    if (v >= 0 && v <= 10) fields.soreness = v;
  }

  const motMatch = body.match(/motivazione\s*(\d{1,2})/i);
  if (motMatch) {
    const v = parseInt(motMatch[1], 10);
    if (v >= 1 && v <= 10) { fields.motivation = v; summary.push(`motivation ${v}`); }
  }

  if (/\b(malato|malata|febbre|raffreddore|influenza|mal di gola|tosse|covid)\b/i.test(lower)) {
    fields.illness_flag = true;
    fields.illness_details = body.slice(0, 200);
    summary.push("malattia");
  }

  const noPainRegex = /\b(no dolori|nessun dolore|no pain|niente dolori|no dolore|zero dolori)\b/i;
  if (!noPainRegex.test(lower) && /\b(dolore|infortunio|tendine|stiramento|contrattura|gonfio|male)\b/i.test(lower)) {
    fields.injury_flag = true;
    fields.injury_details = body.slice(0, 200);
    const locMatch = body.match(/\b(ginocchio|caviglia|polpaccio|tendine d'achille|achille|coscia|adduttore|spalla|schiena|lombare|piede|tallone|anca|quadricipite|gluteo)\b/i);
    if (locMatch) fields.injury_location = locMatch[1];
    summary.push("infortunio");
  }

  if (/\b(no dolori|nessun dolore|no pain|niente dolori)\b/i.test(lower)) {
    parsed.pain_reported = false;
  } else if (/\b(dolore|dolori|male|fastidio)\b/i.test(lower)) {
    parsed.pain_reported = true;
    const locMatch = body.match(/\b(ginocchio|caviglia|polpaccio|tendine d'achille|achille|coscia|adduttore|spalla|schiena|lombare|piede|tallone|anca|quadricipite|gluteo)\b/i);
    if (locMatch) parsed.pain_location = locMatch[1];
  }

  if (/\b(energia alta|fresco|riposato)\b/i.test(lower)) parsed.energy = "high";
  else if (/\b(energia media|normale)\b/i.test(lower)) parsed.energy = "medium";
  else if (/\b(energia bassa|stanco|scarico|distrutto|cotto)\b/i.test(lower)) parsed.energy = "low";

  parsed.sensations = body.slice(0, 500);
  fields.parsed_data = parsed;

  return { fields, summary: summary.join(", ") };
}

// ============================================================================
// Supabase helpers
// ============================================================================

async function supabaseFetch(
  env: Env,
  path: string,
  method: string = "GET",
  body?: any,
  extraHeaders?: Record<string, string>,
): Promise<Response> {
  const headers: Record<string, string> = {
    apikey: env.SUPABASE_SERVICE_KEY,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    "Content-Type": "application/json",
    ...extraHeaders,
  };
  return fetch(`${env.SUPABASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

async function getBotMessage(env: Env, telegramMessageId: number): Promise<BotMessage | null> {
  const resp = await supabaseFetch(env, `/rest/v1/bot_messages?telegram_message_id=eq.${telegramMessageId}&limit=1`);
  const rows = await resp.json() as BotMessage[];
  if (!rows.length) return null;
  const msg = rows[0];
  // Verifica che non sia scaduto
  if (msg.expires_at && new Date(msg.expires_at) < new Date()) return null;
  return msg;
}

async function logBotMessage(
  env: Env,
  telegramMessageId: number,
  chatId: number,
  purpose: string,
  contextData?: any,
): Promise<void> {
  const record: any = { telegram_message_id: telegramMessageId, chat_id: chatId, purpose };
  if (contextData) record.context_data = contextData;
  await supabaseFetch(env, "/rest/v1/bot_messages", "POST", record, { Prefer: "return=minimal" });
}

async function insertSubjective(env: Env, payload: any): Promise<void> {
  const body = { logged_at: new Date().toISOString(), ...payload };
  const resp = await supabaseFetch(env, "/rest/v1/subjective_log", "POST", body, { Prefer: "return=minimal" });
  if (!resp.ok) throw new Error(`Supabase insert failed: ${resp.status} ${await resp.text()}`);
}

async function getPendingConfirmation(env: Env, id: string): Promise<PendingConfirmation | null> {
  const resp = await supabaseFetch(env, `/rest/v1/pending_confirmations?id=eq.${id}&limit=1`);
  const rows = await resp.json() as PendingConfirmation[];
  return rows[0] ?? null;
}

async function resolvePendingConfirmation(env: Env, id: string, status: string): Promise<void> {
  await supabaseFetch(env, `/rest/v1/pending_confirmations?id=eq.${id}`, "PATCH",
    { status, resolved_at: new Date().toISOString() }, { Prefer: "return=minimal" });
}

// ============================================================================
// Telegram API helpers
// ============================================================================

async function sendMessage(env: Env, chatId: number, text: string, replyMarkup?: any): Promise<void> {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
      ...(replyMarkup ? { reply_markup: replyMarkup } : {}),
    }),
  });
}

async function sendAndLogMessage(
  env: Env,
  chatId: number,
  text: string,
  purpose: string,
  contextData?: any,
  replyMarkup?: any,
): Promise<void> {
  const msgId = await sendMessageGetId(env, chatId, text, replyMarkup);
  if (msgId) await logBotMessage(env, msgId, chatId, purpose, contextData);
}

async function sendMessageGetId(env: Env, chatId: number, text: string, replyMarkup?: any): Promise<number | null> {
  const resp = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
      ...(replyMarkup ? { reply_markup: replyMarkup } : {}),
    }),
  });
  if (!resp.ok) return null;
  const data = await resp.json() as any;
  return data?.result?.message_id ?? null;
}

async function answerCallback(env: Env, callbackQueryId: string): Promise<void> {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_query_id: callbackQueryId }),
  });
}

async function editMessageReplyMarkup(env: Env, chatId: number, messageId: number, replyMarkup: any): Promise<void> {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, message_id: messageId, reply_markup: replyMarkup }),
  });
}

// ============================================================================
// Status e budget
// ============================================================================

async function getStatus(env: Env): Promise<string> {
  const resp = await supabaseFetch(env, `/rest/v1/health?select=component,last_success_at,failure_count`);
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
  const resp = await supabaseFetch(env, `/rest/v1/api_usage?timestamp=gte.${monthStart}&select=cost_usd_estimated,success`);
  if (!resp.ok) return "Errore nel recupero budget.";
  const rows = (await resp.json()) as any[];
  let totalCost = 0, successful = 0;
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
