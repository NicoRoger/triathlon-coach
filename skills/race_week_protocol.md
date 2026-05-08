---
name: race_week_protocol
description: Protocollo completo per la settimana gara (T-7 a T+1). Da invocare automaticamente quando una gara A o B è entro 7 giorni, oppure quando l'atleta chiede esplicitamente "mi prepari la settimana gara" / "checklist gara". Include taper, logistica, race day plan, post-gara.
---

# Race Week Protocol

## Quando usare

**Trigger automatici:**
- Una gara con `priority='A'` o `priority='B'` è entro 7 giorni dalla data corrente
- Da T-7 il brief mattutino integra elementi di questo protocollo
- A T-2, T-1, T-0, T+1 ci sono comunicazioni dedicate

**Trigger manuali:**
- "preparami la gara di [data]"
- "checklist materiale per [gara]"
- "race day plan"

## Filosofia generale

Una gara A o B non si vince la settimana prima, ma si può perdere. Il taper è
delicato: ridurre volume troppo fa perdere stimolo, ridurre poco lascia fatica
residua. Bosquet et al. 2007 (meta-analisi su taper): riduzione volume 41-60%
con mantenimento intensità ottimizza performance, durata 8-14 giorni.

Per gare A: taper completo (8-14 giorni). Per gare B: mini-taper (3-5 giorni).

## Procedura per fasi

### T-7 (lunedì se gara domenica)

**Brief mattutino settimana gara**: include sezione "Modalità gara - Lavarone in 7 giorni".

**Volume settimana**: -40% rispetto alla settimana di carico precedente.
**Intensità**: mantenuta in micro-dosi (es. 3-4 intervalli Z4 di 2-3 min ciascuno).
**Sessioni**:
- 1 sessione qualità per disciplina nuoto+bici+corsa
- 1 brick breve metà settimana
- 0 sessioni lunghe
- Più recovery, sonno target +30min/notte

**Comunicazione settimana**:
- Reminder logistica: iscrizione confermata? Alloggio? Viaggio?
- Reminder materiale: inizia a controllare bici, ruote, cambio, freni
- Razionali del taper: l'atleta deve capire perché stiamo facendo poco

### T-3 (giovedì)

Sessione di **richiamo intensità**: corta ma intensa.
Esempio cross sprint: 10 min Z2 + 5×30s allungo + 10 min Z2.

Brief inizia a includere:
- Previsione meteo gara (cita fonte web se disponibile)
- **Meteo attività recenti** (Step 5.1): controlla `activities.weather` delle ultime
  3-5 attività outdoor per confrontare condizioni di allenamento vs forecast gara.
  Se T° gara >5°C sopra media allenamenti recenti → nota su acclimatamento e idratazione.
- Conferma profilo percorso
- Strategia pacing per disciplina (usa `activities.splits` delle sessioni chiave recenti per baseline pace)

### T-2 (venerdì se gara domenica)

**Ultima sessione di apertura**: 20-30 min Z1-Z2 + 3-4 allunghi brevi. TSS basso.

**Brief T-2** include checklist materiale. Per cross sprint, lista standard:

📋 **Materiale gara cross sprint**:
- Bici MTB controllata: pressioni gomme, freni, cambio, batteria computer
- Tappino bici di ricambio
- Pompa portatile + camera d'aria di ricambio
- Casco
- Occhiali bici
- Scarpe bici (se SPD)
- Body/trisuit
- Cuffia gara
- Occhialini nuoto + ricambio
- Cappello/visiera (se sole)
- Scarpe corsa trail
- Calze
- Numero gara (lo prendi prima del race brief)
- Chip
- Borraccia da bici (riempita)
- 2 gel (carbo)
- Sale o pasticche elettroliti
- Crema solare
- Vaselina/lubrificante anti-sfregamento
- Asciugamano (T1)
- Sacca/bidone transizione
- Documenti (CI, tessera FITRI)

**Briefing percorso T-2**:
- Profilo MTB: km salite, dislivello, settori tecnici
- Trail: profilo dislivello, punti tecnici
- Dove sono le transizioni
- Punto rifornimento (se previsto)

### T-1 (vigilia, sabato se gara domenica)

**Sessione vigilia**: 15-20 min molto facili Z1, eventuale 1-2 allunghi neutri.
Solo per "togliere la ruggine".

**Routine alimentazione**:
- Pranzo abbondante in carbo, normale (riso/pasta + proteina magra + verdura)
- Cena entro 19:30: stessa logica, evita fibre eccessive, evita cibi nuovi/grassi/piccanti
- Idratazione: spalmata, non bere 1L all'ultimo. Acqua + minerali.
- Niente alcol

**Bedtime ottimale**: target 8h sonno, sveglia 3h prima dello start.
- Esempio gara start ore 9:00 → sveglia 6:00 → letto entro 22:00
- Lui non dorme mai bene la notte prima della gara, è normale.
  La notte critica è T-2 (venerdì), non T-1.

**Preparazione materiale**:
- Tutto pronto e accanto alla porta
- Bici già caricata in macchina
- Sacca transizione preparata
- Body/trisuit già pronto
- Niente "domattina lo faccio"

**Visualizzazione gara breve** (se l'atleta è ricettivo): 5 min mentale
in cui ripassi le sequenze (start, T1, primo km bici, T2, primi 500m corsa).
Friel raccomanda esplicitamente questa pratica.

### T-0 (giorno gara)

**Brief gara dettagliato**: questa è la comunicazione più importante della
settimana. Manda al risveglio o comunque entro le 2h prima dello start.

Struttura:
🏆 RACE DAY — Lavarone Cross Sprint
Start: ore HH:MM (in X ore)
⏰ TIMELINE

Sveglia: HH:MM
Colazione: HH:MM (entro 3h dallo start)
Partenza per location: HH:MM
Arrivo zona cambio: HH:MM (almeno 90 min prima start)
Briefing tecnico: HH:MM (di solito 30-45 min prima)
Warm-up: HH:MM (15-20 min prima start)
Start: HH:MM

🍳 COLAZIONE (3h prima)
Carbo ad alto IG, proteina moderata, basso grasso, basso fibre.
Esempio: 2 fette pane bianco + miele + 1 banana + caffè/tè + 200ml succo.
Quantità calibrata: ~1.5-2g carbo/kg peso = 100-130g carbo per te.
💧 IDRATAZIONE
Da sveglia a start: spalma 500-700ml acqua/sali.
30 min prima start: 200-300ml ultimo sorso, poi stop (rischio crampi addominali).
🔥 WARM-UP CROSS SPRINT
Sequenza ottimale ~20 min totali:

5 min jogging easy + mobility generale
5 min mobility specifica spalla (per la borsite, importante)
3-4 min in acqua: 200m easy + 4×25m allunghi
Ultimi 5 min: stretching dinamico, respirazione
NON arrivare freddo allo start.

🏊 PIANO NUOTO 750m

Linea di partenza: posizionati centro-sinistra (i tuoi punti forti
ti permettono di puntare i primi 5-8)
Primi 100m: spinta per uscire dal grumo, tieni 90% (non 100%)
100-600m: ritmo CSS attuale (con CSS tarato post-test giugno qui ci
saranno target precisi)
Ultimi 150m: alza ritmo per arrivare in forma alla T1

🚴 PIANO MTB 17 km Monte Rust

T1: calma, non sbagliare lacci e casco. ~45 secondi target.
Primi 2 km: avvicinamento, gestisci HR (non sopra Z3)
Salite tecniche Monte Rust: Z3-Z4, mai sopra Z4 in salita
Discese: rilassati, recupera, cuore alto va bene
Tratti misti: Z3 sostenuto
Ultimi 2 km: gestisci, prepara mentalmente T2

🏃 PIANO TRAIL 5K

T2: cambio scarpe rapido. ~30 sec target.
Primi 500m: GAMBE PESANTI normali, non panico, accetta il sentirti
rigido, in 3-4 min passa
500m-3km: Z4 sostenibile (HR target post-test)
Ultimi 2km: tira tutto, ormai arrivi

🥗 NUTRIZIONE IN GARA
Cross sprint = circa 1h15-1h30 totali. Non serve molto.

1 gel carbo prima del nuoto (10 min prima start)
1 gel a metà MTB
Sale/elettroliti se temperatura > 25°C

⚠️ SPALLA DX
Riscaldamento mobility 5 min DEDICATI prima del nuoto.
In gara dovrebbe reggere, ma se senti dolore acuto durante la frazione
nuoto: cambia ritmo, non forzare l'acuto. Meglio perdere 30s e finire.
💪 MENTAL CHECKPOINTS

Allo start: respira profondo 3 volte, ricorda: hai fatto tutto il
lavoro, oggi solo esecuzione.
T1: una cosa alla volta, niente fretta.
Punto critico bici (se c'è una salita lunga): "questo è il mio terreno"
Trail primi km: "le gambe arrivano, fidati"
Ultimi 1km: "tutto quello che hai"

🎯 TARGET
Posizione: 13°-18° (target gara A confermato in CLAUDE.md)
Tempo: [predizione attuale + range]
Esecuzione > tempo: chiudere bene, niente errori, arrivare integro.
Il tempo è conseguenza dell'esecuzione, non target diretto.

### T+1 (lunedì post-gara)

**Brief**: niente sessione, solo recovery attivo se va.
- Sonno extra
- Idratazione
- Camminata 30 min facile
- Niente intensità per 3 giorni minimum

**Debrief gara strutturato** (richiede risposta atleta):
1. Risultato finale: tempo totale, posizione cat/overall, frazioni se le hai
2. Frazione per frazione: come ti sei sentito, sensazioni, errori
3. T1 e T2: come sono andate
4. Nutrizione: ha funzionato? sintomi GI?
5. Spalla: come ha retto?
6. 3 cose andate bene
7. 3 cose da migliorare
8. Sensazione complessiva (1-10)

Salva il debrief in `subjective_log` con `kind='evening_debrief'`. 
Aggiorna `docs/race_history.md` con narrazione strutturata che diventa
memoria per gare future simili.

## Cosa NON fare

- ❌ Non cambiare niente di drastico nella settimana gara (no nuove scarpe,
  nuovi gel, nuove posizioni bici)
- ❌ Non testare nulla in T-3/T-2/T-1 ("vediamo se questa scarpa è meglio")
- ❌ Non ridurre carbo nella settimana gara (l'atleta deve essere
  glicogeno-pieno)
- ❌ Non insistere se l'atleta arriva al T-1 con HRV bassa: meglio dormire
  che andare a fare l'allenamento previsto
- ❌ Non improvvisare il piano gara la mattina stessa: tutto deve essere
  scritto e digerito da T-2 in poi
- ❌ Non promettere posizioni o tempi nel brief gara. Target = esecuzione,
  tempo = conseguenza

## Riferimenti

- Bosquet et al. 2007 — meta-analisi su taper
- Mujika 2010 — "Tapering and peaking for optimal performance"
- Friel "Triathlete's Training Bible" cap. peaking e race week
- Cook & Purdam 2009 — gestione tendinopatia in fase reattiva (per la spalla)