// Test del parser REALE del bot (src/parse.ts), eseguiti con
//   node --experimental-strip-types --test test/
// Le frasi vengono dalla settimana simulata del 29/09-05/10/2026 e dai casi
// già coperti da tests/test_telegram_advanced.py (che reimplementa il parser
// in Python e quindi non verifica questo codice).
import { test } from "node:test";
import assert from "node:assert/strict";
import { detectLocation, detectPain, parseDebrief, parseLog } from "../src/parse.ts";

test("dolore alla spalla detto in modi diversi apre la conferma infortunio", () => {
  for (const msg of [
    "spalla dx un po' dolorante",
    "fastidio alla spalla dx",
    "mi tira la spalla",
    "mi tira la spalla destra quando alzo il braccio",
    "ho un po di dolore alla spalla dx",
    "spalla destra rigida dopo il nuoto",
    "mi fa male la spalla",
    "spalla indolenzita",
  ]) {
    const r = parseLog(msg);
    assert.equal(r.kind, "injury", msg);
    assert.equal(r.fields.injury_flag, true, msg);
    assert.match(r.fields.body_location, /^spalla/, msg);
  }
});

test("il lato viene salvato", () => {
  assert.equal(detectLocation("fastidio alla spalla dx"), "spalla dx");
  assert.equal(detectLocation("spalla destra rigida"), "spalla dx");
  assert.equal(detectLocation("polpaccio sinistro duro"), "polpaccio sx");
  assert.equal(detectLocation("dolore al ginocchio"), "ginocchio");
});

test("fastidio lieve = severità mild", () => {
  assert.equal(parseLog("spalla dx un po' dolorante").fields.severity, "mild");
  assert.equal(parseLog("mi tira la spalla").fields.severity, "mild");
  assert.equal(parseLog("dolore acuto al ginocchio, non riesco a piegarlo").fields.severity, "severe");
});

test("'male' che non è dolore non apre la conferma", () => {
  for (const msg of [
    "non male la sessione oggi",
    "non è andata male",
    "ieri notte male, hotel rumoroso 5 ore",
    "ho dormito male",
    "sessione andata male, gambe vuote",
    "no dolori, tutto ok",
    "nessun fastidio",
  ]) {
    assert.equal(detectPain(msg), false, msg);
    assert.notEqual(parseLog(msg).kind, "injury", msg);
  }
});

test("la negazione non nasconde un dolore reale in coda", () => {
  assert.equal(detectPain("no dolori muscolari, ma dolore alla spalla"), true);
});

test("malattia: negazioni e sintomi lievi", () => {
  assert.notEqual(parseLog("niente febbre, solo un po' stanco").kind, "illness");
  assert.notEqual(parseLog("tosse no, tutto ok").kind, "illness");
  const sore = parseLog("gola che gratta ma niente febbre");
  assert.equal(sore.kind, "illness");
  assert.equal(sore.fields.severity, "mild");
  assert.equal(parseLog("febbre a 39 da ieri").fields.severity, "severe");
  // "39" che non è una temperatura non rende severa la malattia
  assert.notEqual(parseLog("raffreddore, nuotato 39 minuti piano").fields.severity, "severe");
});

test("il debrief serale flagga il dolore (prima salvava solo pain_reported)", () => {
  const d = parseDebrief("rpe 6 nuoto bene, forse la spalla dx un po dolorante verso la fine ma niente di grave");
  assert.equal(d.fields.rpe, 6);
  assert.equal(d.fields.injury_flag, true);
  assert.equal(d.fields.body_location, "spalla dx");
  assert.equal(d.fields.parsed_data.pain_reported, true);

  const d2 = parseDebrief("RPE 5, dolori: spalla dx fastidio, energia media");
  assert.equal(d2.fields.injury_flag, true);

  const ok = parseDebrief("RPE 7, gambe pesanti seconda metà, no dolori, energia bassa, dormo presto");
  assert.equal(ok.fields.injury_flag, undefined);
  assert.equal(ok.fields.parsed_data.pain_reported, false);
  assert.equal(ok.fields.parsed_data.energy, "low");
});

test("con due RPE vale il primo (sessione principale)", () => {
  assert.equal(parseDebrief("RPE corsa 4, poi bici spin rpe 2").fields.rpe, 4);
});

test("casi già coperti restano invariati", () => {
  assert.equal(parseLog("RPE 7 gambe ok").fields.rpe, 7);
  assert.equal(parseLog("RPE 7 gambe ok").kind, "post_session");
  assert.equal(parseLog("febbre e mal di gola").kind, "illness");
  assert.equal(parseLog("dolore al ginocchio").kind, "injury");
  assert.equal(parseLog("motivazione 8").fields.motivation, 8);
  assert.equal(parseLog("soreness 4").fields.soreness, 4);
  assert.equal(parseLog("RPE 11").fields.rpe, undefined);
  assert.equal(parseLog("bella giornata").kind, "free_note");
});

test("RPE con una parola in mezzo, ma senza prendere numeri successivi", () => {
  assert.equal(parseLog("rpe corsa 4").fields.rpe, 4);
  assert.equal(parseLog("rpe 6 10 vasche facili").fields.rpe, 6);
});
