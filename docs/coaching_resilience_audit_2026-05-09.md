# Audit Resilienza AI Coaching (Step 6)

**Data:** 2026-05-09

## 1. Test Budget Cap

- **Scenario Hard Cap ($5.00)**: Simulata l'eccezione `BudgetExceededError`. Il blocco previene ogni esecuzione ulteriore, mandando un solo fallback e scrivendo log. ✅ ok.
- **Scenario Soft Cap ($4.50)**: La factory sceglie `haiku` ignorando la `prefer_model='sonnet'`. ✅ ok.

## 2. Test Post-Session Analysis

- **Sessione senza piano**: Fallback perfetto ad un'analisi base. ✅ ok.
- **Sessione troppo breve**: Ignorata dallo script (skip logica su `<5 min` non attualmente hard-coded, ma LLM è reattivo a metriche inesistenti e genera summary nullo).
- **Fallimento API (Anthropic 503)**: Ritorna eccezione. Nessun retry automatico implementato a livello codice se non retry standard di Http. P2: Implementare tenacy retry.

## 3. Test Modulazione Mid-Week
- **Idempotenza Click Multipli**: Segnalato come problema in Audit Telegram Bot. Il bot chiude la callback_query markup dopo il click. Questo impedisce doppio click per gli utenti normali. ✅ ok.
- **Modulazione Vecchia**: Manca campo `expires_at`. Può essere accettata anche un mese dopo se il bottone è ancora visibile. P2.

## 4. Test Proactive Questions & Pattern Extraction
- **Pattern vuoti**: LLM genera file pulito senza crash. ✅ ok.
- **Ignora Check-in**: Se l'utente non risponde, la conversazione si ripristina alla ricezione del prossimo `/`. ✅ ok.

## 5. Bug Riscontrati
Nessun P0/P1 nativo.
