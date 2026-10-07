/**
 * Parsing deterministico dei messaggi dell'atleta (no LLM).
 *
 * Modulo puro, senza dipendenze dal runtime Worker: è testato direttamente
 * con `node --test` (test/parse.test.ts). Prima i test reimplementavano il
 * parser in Python, quindi non verificavano il codice che gira davvero.
 *
 * Il caso che conta di più è la spalla destra (borsite + tendinopatia CLB,
 * CLAUDE.md: "Dolore spalla dx: azione immediata"). Il parser riconosceva solo
 * "dolore": "spalla dx un po' dolorante", "fastidio alla spalla", "mi tira la
 * spalla" finivano come nota libera senza flag. Al contrario "non male la
 * sessione" o "niente febbre" chiedevano conferma di infortunio/malattia.
 */

// ============================================================================
// Dolore / infortunio
// ============================================================================

/** Frasi che NEGANO il dolore o in cui "male" non vuol dire dolore fisico.
 *  Vanno tolte PRIMA del match: "no dolori muscolari, ma dolore alla spalla"
 *  deve comunque flaggare (la negazione globale sopprimeva infortuni reali). */
const PAIN_NEGATIONS: RegExp[] = [
  /\b(no|nessun[oa]?|niente|zero|senza)\s+(dolor[ei]|fastidi[oa]?)(\s+muscolar[ei])?\b/gi,
  /\bno\s+pain\b/gi,
  /\bnon\s+(mi\s+)?(fa|faceva|ha\s+fatto)\s+male\b/gi,
  // "non male", "non è andata male", "non era male": = "non è andata maluccio"
  /\bnon\s+(è\s+|e\s+|era\s+|sono\s+)?(andat[oa]\s+|stat[oa]\s+)?male\b/gi,
  // "male" riferito a sonno/giornata/sessione, non al corpo
  /\b(dormit[oa]|dormo|notte|nottata|riposat[oa]|sonno|andat[oa]|giornata|sessione|gara|allenamento)\s+(\w+\s+)?male\b/gi,
  // "sto male" / "mi sento male": malessere generico, non un infortunio
  /\b(sto|stavo|sent[oi]|sentivo)\s+(\w+\s+)?male\b/gi,
];

const PAIN_WORDS =
  /\b(dolor[ei]|dolorant[ei]|doloros[oa]|indolenzit[oaie]|indolenziment[oi]|fastidi[oa]?|male|infortuni[oa]?|infortunat[oa]|tendin[ei]|tendinit[ei]|tendinopatia|stirament[oi]|contrattur[ae]|gonfi[oa]|gonfiore|infiammat[oa]|infiammazione|fitt[ae]|brucia|bruciore|pizzica|zoppic\w*|acciacc\w*)\b|\bmi\s+tira(va|no)?\b/i;

/** Spalla: anche segnali "morbidi" (tira, rigida, bloccata, scricchiola)
 *  aprono la conferma — è la zona vulnerabile n.1 dell'atleta. */
const SHOULDER_SOFT =
  /\bspall[ae]\b[^.!?\n]{0,40}\b(tir[ao]|tirava|rigid\w*|bloccat\w*|scricchiol\w*|strana|sento)\b|\b(tir[ao]|tirava|rigid\w*|bloccat\w*|scricchiol\w*)\b[^.!?\n]{0,25}\bspall[ae]\b/i;

const LOCATION =
  /\b(spall[ae]|ginocchi[ao]|caviglie?|polpacc(?:io|i)|tendine d'achille|achille|cosc[ea]|adduttor[ei]|schiena|lombar[ei]|pied[ei]|tallon[ei]|anc[ah]e?|quadricipiti?|glute[io]|fascite|plantar[ei]|tibi[ae]|gomit[oi]|polso|collo|cervical[ei])\b/i;

const SIDE = /^[^.!?\n]{0,12}?\b(dx|sx|destr[oa]|sinistr[oa])\b/i;

function stripPainNegations(lower: string): string {
  return PAIN_NEGATIONS.reduce((s, re) => s.replace(re, " "), lower);
}

/** True se il testo segnala dolore/fastidio fisico (negazioni escluse). */
export function detectPain(text: string): boolean {
  const cleaned = stripPainNegations(text.toLowerCase());
  return PAIN_WORDS.test(cleaned) || SHOULDER_SOFT.test(cleaned);
}

/** Zona del corpo con il lato se indicato subito dopo: "spalla dx". */
export function detectLocation(text: string): string | null {
  const m = LOCATION.exec(text);
  if (!m) return null;
  const loc = m[1].toLowerCase();
  const side = SIDE.exec(text.slice(m.index + m[0].length));
  if (!side) return loc;
  const s = side[1].toLowerCase();
  return `${loc} ${s.startsWith("d") ? "dx" : "sx"}`;
}

export function detectInjurySeverity(text: string): "mild" | "moderate" | "severe" {
  const t = text.toLowerCase();
  if (/\b(fortissim[oa]|acut[oa]|lancinant[ei]|non riesco|impossibile|blocca|bloccat[oa]|fratt(?:ur|a)\w*|strappo|distorsion[ei] grav\w*|lesione|operazion[ei])\b/.test(t)) {
    return "severe";
  }
  if (/\b(fastidi[oa]?|lieve|legger[oa]|leggermente|piccol[oa]|rigidit[aà]|indolenziment[oi]|indolenzit[oaie]|dolorant[ei]|tens[ia]on[ei] muscolar[ei])\b|\bun\s+po'?\b|\bun\s+pochino\b|\bmi\s+tira\b/.test(t)) {
    return "mild";
  }
  return "moderate";
}

// ============================================================================
// Malattia
// ============================================================================

const ILLNESS_NEGATIONS: RegExp[] = [
  /\b(no|niente|senza|zero|nessuna?)\s+(febbre|tosse|raffreddore|mal di gola|influenza|sintomi)\b/gi,
  /\b(febbre|tosse)\s+(no|zero|assente)\b/gi,
];

const ILLNESS_WORDS =
  /\b(malat[oa]|febbre|febbricola|raffreddore|raffreddat[oa]|influenza|mal di gola|tosse|covid|gastroenterit[ei])\b|\bgola\s+(che\s+gratta|irritata|infiammata|arrossata)\b/i;

export function detectIllness(text: string): boolean {
  const cleaned = ILLNESS_NEGATIONS.reduce((s, re) => s.replace(re, " "), text.toLowerCase());
  return ILLNESS_WORDS.test(cleaned);
}

export function detectIllnessSeverity(text: string): "mild" | "moderate" | "severe" {
  const t = text.toLowerCase();
  // La temperatura conta solo come temperatura: prima "39" o "40" in qualunque
  // contesto ("39 minuti") rendevano la malattia severa.
  if (/\b(febbre alta|polmonit[ei]|ricoverat[oa]|grav[ei]|incapace|delirio)\b/.test(t) ||
      /\b(3[89]|4[0-2])([.,]\d)?\s*(°|gradi)/.test(t) || /\bfebbre\s+(a\s+)?(3[89]|4[0-2])\b/.test(t)) {
    return "severe";
  }
  if (/\b(raffreddore lieve|mal di gola leggero|qualche colp[oi] (di )?tosse|gola che gratta)\b/.test(t)) {
    return "mild";
  }
  if (/\b(influenza|febbre|covid|gastroenterit[ei])\b/.test(t)) {
    return "moderate";
  }
  return "mild";
}

export function detectExpectedDuration(text: string): number | null {
  const t = text.toLowerCase();
  const days = t.match(/(\d+)\s*giorn[oi]/);
  if (days) return parseInt(days[1], 10);
  const weeks = t.match(/(\d+)\s*settiman[ae]/);
  if (weeks) return parseInt(weeks[1], 10) * 7;
  const months = t.match(/(\d+)\s*mes[ie]/);
  if (months) return parseInt(months[1], 10) * 30;
  return null;
}

// ============================================================================
// Parser
// ============================================================================

function illnessFields(body: string, fields: any, summary: string[]): void {
  fields.illness_flag = true;
  fields.illness_details = body.slice(0, 200);
  fields.severity = detectIllnessSeverity(body);
  const dur = detectExpectedDuration(body);
  if (dur !== null) fields.expected_duration_days = dur;
  summary.push(`malattia (${fields.severity})`);
}

function injuryFields(body: string, fields: any, summary: string[]): void {
  fields.injury_flag = true;
  fields.injury_details = body.slice(0, 200);
  const loc = detectLocation(body);
  if (loc) {
    fields.injury_location = loc;
    fields.body_location = loc;   // colonna canonica DB
  }
  fields.severity = detectInjurySeverity(body);
  const dur = detectExpectedDuration(body);
  if (dur !== null) fields.expected_duration_days = dur;
  summary.push(`infortunio (${fields.severity})`);
}

function rpeOf(body: string): number | undefined {
  // Il PRIMO RPE è quello della sessione principale: in "corsa rpe 4 … bici
  // rpe 2" il debrief salvava l'ultimo.
  const m = body.match(/rpe\s*(?:[a-zà-ù]+\s+)?(\d{1,2})/i);
  if (!m) return undefined;
  const v = parseInt(m[1], 10);
  return v >= 1 && v <= 10 ? v : undefined;
}

export function parseLog(body: string): { kind: string; fields: any; summary: string } {
  const fields: any = {};
  const summary: string[] = [];

  const rpe = rpeOf(body);
  if (rpe !== undefined) { fields.rpe = rpe; summary.push(`RPE ${rpe}`); }

  const sorMatch = body.match(/(soreness|dolore muscolare)\s*(\d{1,2})/i);
  if (sorMatch) {
    const v = parseInt(sorMatch[2], 10);
    if (v >= 0 && v <= 10) { fields.soreness = v; summary.push(`soreness ${v}`); }
  }

  if (detectIllness(body)) {
    illnessFields(body, fields, summary);
    return { kind: "illness", fields, summary: summary.join(", ") };
  }

  if (detectPain(body)) {
    injuryFields(body, fields, summary);
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

export function parseDebrief(body: string): { fields: any; summary: string } {
  const fields: any = {};
  const parsed: any = {};
  const summary: string[] = [];
  const lower = body.toLowerCase();

  const rpe = rpeOf(body);
  if (rpe !== undefined) { fields.rpe = rpe; summary.push(`RPE ${rpe}`); }

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

  if (detectIllness(body)) illnessFields(body, fields, summary);

  // Prima il debrief salvava "dolori: spalla dx fastidio" solo come
  // parsed_data.pain_reported, senza flag né conferma.
  const pain = detectPain(body);
  if (pain) injuryFields(body, fields, summary);
  parsed.pain_reported = pain;
  if (pain && fields.body_location) parsed.pain_location = fields.body_location;

  if (/\b(energia alta|fresco|riposato)\b/i.test(lower)) parsed.energy = "high";
  else if (/\b(energia media|normale)\b/i.test(lower)) parsed.energy = "medium";
  else if (/\b(energia bassa|stanco|scarico|distrutto|cotto)\b/i.test(lower)) parsed.energy = "low";

  if (/\b(ottima sessione|sessione perfetta|tutto bene|fluidit[aà]|gir(ava|o) bene|eccellente)\b/i.test(lower)) parsed.session_quality = "high";
  else if (/\b(sessione ok|nella media|decente|niente di speciale)\b/i.test(lower)) parsed.session_quality = "medium";
  else if (/\b(sessione brutta|fatica|pesante|non girava|bloccato|pessim[ao])\b/i.test(lower)) parsed.session_quality = "low";

  if (/\b(crampi?|stomaco|nausea|vomito|digestione|nutrizione|gel|barretta|disidratat[oa]|sete)\b/i.test(lower)) {
    parsed.nutrition_issue = true;
  }

  if (/\b(concentrato|presente|determinato|carico|motivato|grinta|flow)\b/i.test(lower)) parsed.mental_state = "high";
  else if (/\b(distratto|assente|svogliat[oa]|demotivat[oa]|ment[ae] altrove|annoiato)\b/i.test(lower)) parsed.mental_state = "low";

  const sleepMatch = body.match(/(?:dormi(?:to|re)?|sonno|ore di sonno|ore sonno)\s*(\d{1,2})\s*(?:ore|h)?/i);
  if (sleepMatch) parsed.sleep_hours_reported = parseInt(sleepMatch[1], 10);
  if (/\b(dormito bene|sonno buono|riposato bene|sonno profondo)\b/i.test(lower)) parsed.sleep_quality = "good";
  else if (/\b(dormito male|insonnia|sonno pessimo|svegliato|nottata|poco sonno)\b/i.test(lower)) parsed.sleep_quality = "poor";

  parsed.sensations = body.slice(0, 500);
  fields.parsed_data = parsed;

  return { fields, summary: summary.join(", ") };
}
