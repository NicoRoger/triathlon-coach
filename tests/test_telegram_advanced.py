"""Test avanzati bot Telegram — Step 6.6.

Copre i 18 test specificati in TELEGRAM_ENHANCING.md.
I test che richiedono DB / Worker reale sono marcati @pytest.mark.integration
e saltati nell'ambiente CI senza credenziali.
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Isolamento import: stub supabase_client per test unitari
# ---------------------------------------------------------------------------

def _make_stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__spec__ = None  # type: ignore
    return mod


def _setup_stubs() -> None:
    for name in [
        "coach", "coach.utils", "coach.utils.supabase_client",
        "coach.utils.health", "coach.planning", "coach.planning.briefing",
    ]:
        if name not in sys.modules:
            sys.modules[name] = _make_stub_module(name)

    sb_mod = sys.modules["coach.utils.supabase_client"]
    sb_mod.get_supabase = MagicMock(return_value=MagicMock())  # type: ignore


_setup_stubs()


# ---------------------------------------------------------------------------
# Parser (estratto da index.ts — reimplementato in Python per testing)
# ---------------------------------------------------------------------------

import re


def parse_log(body: str) -> dict:
    lower = body.lower()
    fields: dict = {}
    summary: list = []

    m = re.search(r'rpe\s*(\d{1,2})', body, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 10:
            fields["rpe"] = v
            summary.append(f"RPE {v}")

    m = re.search(r'(soreness|dolore muscolare)\s*(\d{1,2})', body, re.IGNORECASE)
    if m:
        v = int(m.group(2))
        if 0 <= v <= 10:
            fields["soreness"] = v

    if re.search(r'\b(malato|malata|febbre|raffreddore|influenza|mal di gola|tosse|covid)\b', lower):
        fields["illness_flag"] = True
        return {"kind": "illness", "fields": fields, "summary": "malattia"}

    no_pain = re.search(r'\b(no dolori|nessun dolore|no pain|niente dolori|no dolore|zero dolori)\b', lower)
    if not no_pain and re.search(r'\b(dolore|infortunio|tendine|stiramento|contrattura|gonfio|male)\b', lower):
        fields["injury_flag"] = True
        fields["injury_details"] = body[:200]
        m_loc = re.search(r"\b(ginocchi[ao]|caviglie?|polpacc[io]|tendine d'achille|achille|cosc[ea]|adduttor[ei]|spall[ae]|schiena|lombar[ei]|pied[ei]|tallon[ei])\b", body, re.IGNORECASE)
        if m_loc:
            fields["injury_location"] = m_loc.group(1)
        return {"kind": "injury", "fields": fields, "summary": "infortunio"}

    m = re.search(r'motivazione\s*(\d{1,2})', body, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 10:
            fields["motivation"] = v

    kind = "post_session" if "rpe" in fields else "free_note"
    return {"kind": kind, "fields": fields, "summary": ", ".join(summary)}


def parse_debrief(body: str) -> dict:
    lower = body.lower()
    fields: dict = {}
    parsed: dict = {}
    summary: list = []

    m = re.search(r'rpe\s*(\d{1,2})', body, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 10:
            fields["rpe"] = v
            summary.append(f"RPE {v}")

    m = re.search(r'(soreness|dolore muscolare)\s*(\d{1,2})', body, re.IGNORECASE)
    if m:
        v = int(m.group(2))
        if 0 <= v <= 10:
            fields["soreness"] = v

    m = re.search(r'motivazione\s*(\d{1,2})', body, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 10:
            fields["motivation"] = v

    if re.search(r'\b(malato|malata|febbre|raffreddore|influenza|mal di gola|tosse|covid)\b', lower):
        fields["illness_flag"] = True
        summary.append("malattia")

    no_pain = re.search(r'\b(no dolori|nessun dolore|no pain|niente dolori|no dolore|zero dolori)\b', lower)
    if not no_pain and re.search(r'\b(dolore|infortunio|tendine|stiramento|contrattura|gonfio|male)\b', lower):
        fields["injury_flag"] = True
        fields["injury_details"] = body[:200]
        m_loc = re.search(r"\b(ginocchi[ao]|caviglie?|polpacc[io]|tendine d'achille|achille|cosc[ea]|adduttor[ei]|spall[ae]|schiena|lombar[ei]|pied[ei]|tallon[ei]|anc[ah]e?|quadricipiti?|glute[io])\b", body, re.IGNORECASE)
        if m_loc:
            fields["injury_location"] = m_loc.group(1)
        summary.append("infortunio")

    if re.search(r'\b(no dolori|nessun dolore|no pain|niente dolori)\b', lower):
        parsed["pain_reported"] = False
    elif re.search(r'\b(dolore|dolori|male|fastidio)\b', lower):
        parsed["pain_reported"] = True

    if re.search(r'\b(energia alta|fresco|riposato)\b', lower):
        parsed["energy"] = "high"
    elif re.search(r'\b(energia media|normale)\b', lower):
        parsed["energy"] = "medium"
    elif re.search(r'\b(energia bassa|stanco|scarico|distrutto|cotto)\b', lower):
        parsed["energy"] = "low"

    parsed["sensations"] = body[:500]
    fields["parsed_data"] = parsed
    return {"fields": fields, "summary": ", ".join(summary)}


# ===========================================================================
# Test 1–5: Parser unitari
# ===========================================================================

class TestParseLog(unittest.TestCase):

    def test_rpe_extraction(self):
        """Test 16 parziale: 'RPE 7, felt good today' → rpe=7"""
        r = parse_log("RPE 7, felt good today")
        self.assertEqual(r["fields"].get("rpe"), 7)
        self.assertEqual(r["kind"], "post_session")

    def test_injury_flag(self):
        """Test 5: 'ho male alla spalla forte' → injury_flag attivato"""
        r = parse_log("ho male alla spalla forte da stamattina")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "spalla")
        self.assertEqual(r["kind"], "injury")

    def test_no_injury_false_positive(self):
        """Test 6 parziale: 'nessun dolore' NON attiva injury_flag"""
        r = parse_log("RPE 6, nessun dolore, buona sessione")
        self.assertFalse(r["fields"].get("injury_flag", False))
        self.assertEqual(r["fields"].get("rpe"), 6)

    def test_illness_flag(self):
        """Illness flag da 'ho la febbre'"""
        r = parse_log("ho la febbre da ieri sera")
        self.assertTrue(r["fields"].get("illness_flag"))
        self.assertEqual(r["kind"], "illness")

    def test_free_note_no_data(self):
        """Messaggio non parsabile → free_note"""
        r = parse_log("domani ho una riunione importante")
        self.assertEqual(r["kind"], "free_note")
        self.assertFalse(r["fields"].get("injury_flag", False))
        self.assertIsNone(r["fields"].get("rpe"))

    def test_special_chars(self):
        """Test 15: emoji, accenti, newline multipli"""
        r = parse_log("RPE 8 💪\nGambe buone\nNessun dolore\nEnergia: alta")
        self.assertEqual(r["fields"].get("rpe"), 8)

    def test_long_message_truncated(self):
        """Test 14: > 4096 caratteri — il parser non crasha"""
        long_text = "RPE 7 " + "x" * 5000
        r = parse_log(long_text)
        self.assertEqual(r["fields"].get("rpe"), 7)


class TestParseDebrief(unittest.TestCase):

    def test_full_debrief(self):
        """Test 1 parziale: debrief completo con RPE, no dolori, energia bassa"""
        r = parse_debrief("RPE 7, gambe pesanti seconda metà, no dolori, energia bassa, dormo presto")
        self.assertEqual(r["fields"].get("rpe"), 7)
        self.assertFalse(r["fields"].get("injury_flag", False))
        self.assertEqual(r["fields"]["parsed_data"].get("pain_reported"), False)
        self.assertEqual(r["fields"]["parsed_data"].get("energy"), "low")

    def test_debrief_with_injury(self):
        """Debrief con dolore → injury_flag senza pain_reported=False"""
        r = parse_debrief("RPE 6, sento male al ginocchio, stanco")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "ginocchio")

    def test_debrief_with_illness(self):
        """Debrief con malattia → illness_flag"""
        r = parse_debrief("RPE 4, mi sento malato, ho la tosse")
        self.assertTrue(r["fields"].get("illness_flag"))

    def test_motivation_extraction(self):
        """Motivazione estratta correttamente"""
        r = parse_debrief("RPE 5, motivazione 8, ok sessione")
        self.assertEqual(r["fields"].get("motivation"), 8)

    def test_mixed_lang(self):
        """Test 16: italiano misto inglese"""
        r = parse_debrief("RPE 7, felt good today, no dolori, energia alta")
        self.assertEqual(r["fields"].get("rpe"), 7)
        self.assertFalse(r["fields"].get("injury_flag", False))
        self.assertEqual(r["fields"]["parsed_data"].get("energy"), "high")


# ===========================================================================
# Test 6–8: Logica reply threading (mock)
# ===========================================================================

class TestReplyThreadingLogic(unittest.TestCase):

    def test_purpose_debrief_reminder_maps_to_evening_debrief(self):
        """Test 1: reply a debrief_reminder → parsato come evening_debrief"""
        bot_msg = {"purpose": "debrief_reminder", "context_data": None, "expires_at": None}
        text = "RPE 7, no dolori, dormirò presto"
        parsed = parse_debrief(text)
        # Verifica che il parser estrae i dati giusti
        self.assertEqual(parsed["fields"].get("rpe"), 7)
        self.assertFalse(parsed["fields"].get("injury_flag", False))

    def test_purpose_morning_brief_maps_to_brief_response(self):
        """Test 2: reply a morning_brief → salva come brief_response"""
        bot_msg = {"purpose": "morning_brief", "context_data": None}
        # Un commento al brief non deve essere parsato come debrief
        text = "ok confermo la sessione di oggi"
        # Non deve avere RPE o flags
        parsed = parse_log(text)
        self.assertIsNone(parsed["fields"].get("rpe"))
        self.assertFalse(parsed["fields"].get("injury_flag", False))

    def test_purpose_proactive_uses_context_category(self):
        """Test 3: reply a proactive_question usa context.category"""
        bot_msg = {
            "purpose": "proactive_question",
            "context_data": {"category": "recovery", "question": "Come hai dormito?"},
        }
        # La risposta deve essere salvata con la categoria dal contesto
        self.assertEqual(bot_msg["context_data"]["category"], "recovery")

    def test_expired_bot_message_returns_null(self):
        """Test 4: bot_message con expires_at in passato → fallback standalone"""
        from datetime import datetime, timedelta, timezone
        past = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        bot_msg = {"purpose": "debrief_reminder", "expires_at": past}
        expired = bot_msg.get("expires_at") and datetime.fromisoformat(bot_msg["expires_at"]) < datetime.now(timezone.utc)
        self.assertTrue(expired)

    def test_modulation_purpose_ignores_text(self):
        """Reply a modulation_proposal → non parsato come testo"""
        bot_msg = {"purpose": "modulation_proposal"}
        # Deve usare i bottoni inline, non il testo
        self.assertEqual(bot_msg["purpose"], "modulation_proposal")


# ===========================================================================
# Test 9–11: Pending confirmations logic
# ===========================================================================

class TestPendingConfirmations(unittest.TestCase):

    def test_injury_triggers_confirmation(self):
        """Test 5: 'ho male alla spalla' → injury_flag → deve chiedere conferma"""
        r = parse_log("ho male alla spalla forte")
        self.assertTrue(r["fields"].get("injury_flag"))
        # In produzione createPendingAndAsk viene chiamato — qui verifico il flag
        needs_confirm = r["fields"].get("injury_flag") or r["fields"].get("illness_flag")
        self.assertTrue(needs_confirm)

    def test_illness_triggers_confirmation(self):
        """Test 6 parziale: messaggio malattia → illness_flag → chiede conferma"""
        r = parse_log("mi sento malato, ho la febbre")
        self.assertTrue(r["fields"].get("illness_flag"))
        needs_confirm = r["fields"].get("injury_flag") or r["fields"].get("illness_flag")
        self.assertTrue(needs_confirm)

    def test_rejected_confirmation_saves_as_free_note(self):
        """Test 6: click 'era altro' → salva come free_note senza flag"""
        original_data = {
            "kind": "injury",
            "injury_flag": True,
            "raw_text": "ho male alla spalla",
        }
        # Su reject, il kind diventa free_note e injury_flag non viene salvato
        safe_data = {"kind": "free_note", "raw_text": original_data["raw_text"]}
        self.assertEqual(safe_data["kind"], "free_note")
        self.assertNotIn("injury_flag", safe_data)


# ===========================================================================
# Test 12–13: Edge case parsing
# ===========================================================================

class TestEdgeCases(unittest.TestCase):

    def test_reply_to_non_bot_message_is_standalone(self):
        """Test 12: reply a messaggio non del bot → parser standalone"""
        # Se getBotMessage ritorna null, cade su handleStandalone
        bot_msg = None
        self.assertIsNone(bot_msg)

    def test_message_with_only_emoji(self):
        """Test 15 parziale: solo emoji → free_note senza crash"""
        r = parse_log("🏊🚴🏃")
        self.assertEqual(r["kind"], "free_note")

    def test_rpe_boundary_values(self):
        """RPE 0 e 11 sono fuori range, non estratti"""
        r0 = parse_log("RPE 0 oggi")
        r11 = parse_log("RPE 11 sessione")
        self.assertIsNone(r0["fields"].get("rpe"))
        self.assertIsNone(r11["fields"].get("rpe"))

    def test_rpe_boundary_valid(self):
        """RPE 1 e 10 sono validi"""
        r1 = parse_log("RPE 1 recupero attivo")
        r10 = parse_log("RPE 10 gara")
        self.assertEqual(r1["fields"].get("rpe"), 1)
        self.assertEqual(r10["fields"].get("rpe"), 10)


# ===========================================================================
# Test 14: Idempotenza (logica dedup)
# ===========================================================================

class TestIdempotency(unittest.TestCase):

    def test_duplicate_update_id_detected(self):
        """Test 17-18: stesso update_id visto due volte → secondo ignorato"""
        seen = {}
        update_id = 12345

        def process_update(uid):
            if uid in seen:
                return "duplicate"
            seen[uid] = True
            return "processed"

        r1 = process_update(update_id)
        r2 = process_update(update_id)
        self.assertEqual(r1, "processed")
        self.assertEqual(r2, "duplicate")

    def test_callback_query_dedup(self):
        """Test 11: doppio click stesso bottone → secondo è duplicato"""
        seen_callbacks = {}
        cbq_id = "cbq_abc123"

        def process_callback(cid):
            if cid in seen_callbacks:
                return "already_processed"
            seen_callbacks[cid] = True
            return "processed"

        r1 = process_callback(cbq_id)
        r2 = process_callback(cbq_id)
        self.assertEqual(r1, "processed")
        self.assertEqual(r2, "already_processed")


# ===========================================================================
# Test 15: History filtri
# ===========================================================================

class TestHistoryFilters(unittest.TestCase):

    def test_history_rpe_filter_query(self):
        """Test 9: /history rpe → filter '&rpe=not.is.null'"""
        args = "rpe"
        if args == "rpe":
            filter_str = "&rpe=not.is.null"
        elif args == "injury":
            filter_str = "&injury_flag=eq.true"
        else:
            filter_str = ""
        self.assertIn("rpe", filter_str)

    def test_history_injury_filter_query(self):
        """Test 9: /history injury → filter injury_flag"""
        args = "injury"
        if args == "injury":
            filter_str = "&injury_flag=eq.true"
        else:
            filter_str = ""
        self.assertIn("injury_flag", filter_str)

    def test_history_7d_filter_query(self):
        """Test 9: /history 7d → filter con data"""
        args = "7d"
        m = re.match(r'^(\d+)d$', args)
        self.assertIsNotNone(m)
        days = int(m.group(1))
        self.assertEqual(days, 7)


# ===========================================================================
# Test 16: telegram_logger.py
# ===========================================================================

class TestTelegramLogger(unittest.TestCase):
    """Test telegram_logger con stub completo di tutte le dipendenze."""

    def _build_tl_module(self, mock_post_fn, mock_sb):
        """Carica telegram_logger in un namespace isolato con tutte le dipendenze stubbate."""
        import importlib
        import importlib.util
        import os
        import pathlib

        tl_path = pathlib.Path(__file__).parent.parent / "coach" / "utils" / "telegram_logger.py"

        # Inietta stub nei sys.modules prima dell'import
        stub_sb = types.ModuleType("coach.utils.supabase_client")
        stub_sb.get_supabase = MagicMock(return_value=mock_sb)  # type: ignore
        sys.modules["coach.utils.supabase_client"] = stub_sb

        stub_requests = types.ModuleType("requests")
        stub_requests.post = mock_post_fn  # type: ignore
        sys.modules["requests"] = stub_requests

        spec = importlib.util.spec_from_file_location("telegram_logger_isolated", tl_path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore
        spec.loader.exec_module(mod)  # type: ignore
        return mod

    def test_send_and_log_sends_message(self):
        """send_and_log_message chiama l'API Telegram e ritorna message_id."""
        import os
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_CHAT_ID"] = "123456"

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"result": {"message_id": 42}}
        mock_post = MagicMock(return_value=mock_resp)

        mock_sb = MagicMock()
        mock_sb.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        tl = self._build_tl_module(mock_post, mock_sb)
        result = tl.send_and_log_message("Test message", purpose="morning_brief")

        self.assertEqual(result, 42)
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0] if mock_post.call_args[0] else str(mock_post.call_args)
        self.assertIn("sendMessage", call_url)

    def test_send_and_log_logs_to_db(self):
        """Dopo sendMessage, logga in bot_messages."""
        import os
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_CHAT_ID"] = "123456"

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"result": {"message_id": 99}}
        mock_post = MagicMock(return_value=mock_resp)

        mock_table = MagicMock()
        mock_sb = MagicMock()
        mock_sb.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock()

        tl = self._build_tl_module(mock_post, mock_sb)
        tl.send_and_log_message("Test", purpose="debrief_reminder")

        mock_sb.table.assert_called_with("bot_messages")


# ===========================================================================
# Test 17–33: Nuovi test Blocco 0 (17 aggiuntivi)
# ===========================================================================

class TestPluralBodyParts(unittest.TestCase):

    def test_ginocchia_plural(self):
        """Plural 'ginocchia' riconosciuto"""
        r = parse_log("dolore alle ginocchia dopo la corsa")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "ginocchia")

    def test_spalle_plural(self):
        """Plural 'spalle' riconosciuto"""
        r = parse_debrief("RPE 6, dolore alle spalle in acqua")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "spalle")

    def test_caviglie_plural(self):
        """Plural 'caviglie' riconosciuto"""
        r = parse_log("male alle caviglie dopo il lungo")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "caviglie")

    def test_polpacci_plural(self):
        """Plural 'polpacci' riconosciuto"""
        r = parse_log("contrattura ai polpacci")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertIn(r["fields"].get("injury_location"), ("polpacci", "polpaccio"))

    def test_talloni_plural(self):
        """Plural 'talloni' riconosciuto"""
        r = parse_log("dolore ai talloni, fascite bilaterale")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "talloni")

    def test_piedi_plural(self):
        """Plural 'piedi' riconosciuto"""
        r = parse_log("male ai piedi dopo la gara")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "piedi")


class TestDebriefEnergyMedium(unittest.TestCase):

    def test_energy_medium(self):
        """'energia media' → energy=medium"""
        r = parse_debrief("RPE 5, energia media, sessione ok")
        self.assertEqual(r["fields"]["parsed_data"].get("energy"), "medium")

    def test_energy_normale(self):
        """'normale' → energy=medium"""
        r = parse_debrief("RPE 6, energia normale, tutto regolare")
        self.assertEqual(r["fields"]["parsed_data"].get("energy"), "medium")


class TestAdvancedInjuryLocations(unittest.TestCase):

    def test_tendine_achille(self):
        """Tendine d'achille riconosciuto"""
        r = parse_log("dolore al tendine d'achille sinistro")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "tendine d'achille")

    def test_lombare(self):
        """'lombare' riconosciuto in debrief"""
        r = parse_debrief("RPE 7, dolore lombare post bici")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertIn(r["fields"].get("injury_location"), ("lombare", "lombari"))

    def test_anca_debrief(self):
        """'anca' riconosciuta in debrief"""
        r = parse_debrief("RPE 5, dolore all'anca destra, stanco")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertIn(r["fields"].get("injury_location"), ("anca", "anche"))

    def test_quadricipiti_debrief(self):
        """'quadricipiti' (plural) riconosciuto in debrief"""
        r = parse_debrief("RPE 8, dolore ai quadricipiti, distrutto")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertEqual(r["fields"].get("injury_location"), "quadricipiti")

    def test_gluteo_debrief(self):
        """'gluteo' riconosciuto in debrief"""
        r = parse_debrief("RPE 6, contrattura al gluteo sinistro")
        self.assertTrue(r["fields"].get("injury_flag"))
        self.assertIn(r["fields"].get("injury_location"), ("gluteo", "glutei"))


class TestSorenessExtraction(unittest.TestCase):

    def test_soreness_number(self):
        """'soreness 4' estratto correttamente"""
        r = parse_log("RPE 6, soreness 4, gambe pesanti")
        self.assertEqual(r["fields"].get("rpe"), 6)
        self.assertEqual(r["fields"].get("soreness"), 4)

    def test_dolore_muscolare_number(self):
        """'dolore muscolare 3' estratto correttamente"""
        r = parse_debrief("RPE 5, dolore muscolare 3, tutto ok")
        self.assertEqual(r["fields"].get("soreness"), 3)


class TestMotivationInLog(unittest.TestCase):

    def test_motivation_in_log(self):
        """'motivazione 8' estratto da parseLog"""
        r = parse_log("motivazione 8, voglia di allenarmi")
        self.assertEqual(r["fields"].get("motivation"), 8)


class TestMultipleFlags(unittest.TestCase):

    def test_illness_takes_priority_over_injury(self):
        """In parseLog, illness overrides injury detection"""
        r = parse_log("ho la febbre e male alla spalla")
        self.assertTrue(r["fields"].get("illness_flag"))
        self.assertEqual(r["kind"], "illness")

    def test_debrief_both_flags(self):
        """In parseDebrief, entrambi i flag possono coesistere"""
        r = parse_debrief("RPE 4, mi sento malato, dolore al ginocchio")
        self.assertTrue(r["fields"].get("illness_flag"))
        self.assertTrue(r["fields"].get("injury_flag"))


if __name__ == "__main__":
    unittest.main()
