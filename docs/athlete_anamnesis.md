# Anamnesi Atleta — Nicolò Ruggero

> FILE GENERATO AUTOMATICAMENTE da `scripts/generate_anamnesis.py` — non modificare a mano:
> ogni run lo riscrive da zero. Fonte di verità: il database (physiology_zones,
> active_constraints, mesocycles, beliefs, daily_metrics/wellness).
> Profilo statico, storia e pattern mentali restano in CLAUDE.md §2.

## Soglie e zone correnti (misurate)

### Run — LTHR 172 bpm | soglia 4:20/km | HRmax 194
*Metodo: manual_heat_corrected — valido dal 2026-06-21*
- Z1_recovery: >5:25/km
- Z2_endurance: 4:59-5:25/km
- Z3_tempo: 4:33-4:59/km
- Z4_threshold: 4:12-4:33/km
- Z5_vo2max: <4:12/km

### Swim — CSS 1:20/100m
*Metodo: CSS Test 400-200 (vasca lunga 50m, 04/06/2026). 400m in 5:20 (320s), 200m in 2:40 (160s). CSS = (400-200)/(320-160) = 1.25 m/s = 80 s/100m. — valido dal 2026-06-04*
- CSS_minus5: 1:25/100m (endurance)
- CSS: 1:20/100m (threshold)
- CSS_plus5: 1:15/100m (VO2max)

### Bike — LTHR 170 bpm
*Metodo: FTP Test 20min (26/05/2026, Padova, percorso piatto). HR media 20' = 182 bpm. LTHR = 182 × 0.95 = 173, corretta a 170 per caldo (33°C alza HR di 5-8 bpm). Atleta SENZA wattmetro → zone basate su LTHR, non watt. — valido dal 2026-05-26*
- Z1_recovery: <138 bpm
- Z2_aerobic: 138-151 bpm
- Z3_tempo: 151-162 bpm
- Z4_threshold: 162-170 bpm
- Z5_above: >170 bpm

## Vincoli medici attivi

### run — severità media, stato n/d
fascite plantare sinistra: max +10% volume/settimana, cap 14-15km/settimana attuale, asintomatica da 14gg

### swim — severità bassa, in recupero (via libera progressivo)
spalla dx post borsite + tendinopatia CLB: via libera fisio ai carichi (29/06), fuori fase critica. Carichi nuoto liberi, intensità reintroducibile gradualmente. Continuare esercizi fisio.
*Nota: Via libera fisio 29/06 registrato — update bloccato finora dal bug circular JSON in update_constraint, fixato e deployato il 07/07.*

### all — severità media, sintomatico
Iter diagnostico cardiologico in corso — stop precauzionale auto-imposto da metà luglio 2026, ripresa graduale dal 21/09/2026. Trigger: coppie ventricolari a morfologia BBDx ad alti carichi durante test da sforzo al cicloergometro (16/07/2026), atleta asintomatico. Accertamenti: (1) Ecocardio 20/07/2026 — funzione sistolica biventricolare conservata, prolasso mitralico con insufficienza lieve; (2) RM cuore con mdc 27/08/2026 (AOU Padova) — VS moderatamente dilatato (VTD indicizzato 121 ml/m2, v.n. 68-103), VD lievemente dilatato (121 ml/m2, v.n. 68-114), FE 51% VS / 53% VD (limiti inferiori di norma), cinesi segmentaria conservata, strain globale nei limiti (GLS -15.8%), massa e spessori nei limiti, T1 e T2 mapping globali nei limiti (T1 aumentato solo nel segmento laterale distale), ECV 23% nei limiti, nessuna alterazione in perfusione di primo passaggio, sfumata stria di LGE intramiocardico al setto inferiore medio compatibile con FIBROSI A PATTERN NON ISCHEMICO; (3) Holter ECG 12 derivazioni 01-02/09/2026 — 23h43, ritmo sinusale 46-158 bpm (media 74), ZERO battiti ventricolari ectopici, zero TV/coppie/triplette, 22 SVE isolate, QTc nei limiti, HRV nei limiti, ripolarizzazione precoce fisiologica. IMPLICAZIONI PRATICHE fino a visita conclusiva con la cardiologa (23/09/2026): solo lavoro aerobico Z1-Z2, nessuna intensità sopra Z2, nessuno sforzo massimale o progressivo fino a esaurimento, nessun test (FTP, CSS, soglia), nessuna gara o uscita in gruppo con dinamiche competitive. Motivo: l'aritmia si è manifestata SOLO ad alti carichi e l'Holter, pulito, non ha riprodotto quella condizione (FC max registrata 158 bpm). Stop immediato e contatto medico in caso di cardiopalmo, sensazione di battiti irregolari sotto sforzo, dolore toracico, dispnea sproporzionata, presincope o sincope. Da rivedere dopo il 23/09/2026 con l'indicazione della cardiologa su idoneità agonistica, tetto di intensità ed eventuali esami di follow-up (test da sforzo massimale di ripetizione, Holter durante allenamento intenso).
*Nota: CRONOLOGIA CONSOLIDATA 20/09/2026 (sostituisce le note precedenti; correzione rilevante sulla datazione del secondo episodio, che il coach aveva erroneamente collocato a fine agosto). SEQUENZA: 16/07/2026 test da sforzo al cicloergometro eseguito a fine giornata lavorativa — coppie ventricolari a morfologia BBDx ad alti carichi, reperto che ha originato l'iter. 20/07/2026 ecocolordoppler — funzione biventricolare conservata, prolasso mitralico con insufficienza lieve. Metà luglio: stop precauzionale auto-imposto. 26/08/2026 (vigilia della RM, dopo giornata lavorativa) PRIMO episodio di ectopia percepita. 27/08/2026 RM cardiaca con mdc — sfumata stria di LGE al setto inferiore medio, fibrosi a pattern non ischemico; volumi biventricolari aumentati, FE 51/53%, strain, T2 ed ECV nei limiti. 01-02/09/2026 Holter 12 derivazioni 23h43, indossato anche durante corsa di 30' (FC media 150, max 158 alle 18:51): ZERO battiti ventricolari ectopici, sia a riposo sia nella finestra di sforzo. ~10/09/2026 inizio BACTRIM (cotrimossazolo) per infezione delle vie urinarie. ~14-15/09/2026 SECONDO episodio di ectopia percepita, in 5a-6a giornata di terapia, dopo giornata lavorativa. 18/09/2026 (venerdì) fine Bactrim dopo 8 giorni. 19/09/2026 nessun sintomo in condizioni analoghe. DUE LETTURE DA SOTTOPORRE ALLA CARDIOLOGA IL 23/09/2026. (A) A favore del cofattore reversibile: la 5a-6a giornata di cotrimossazolo è la finestra tipica in cui si manifestano le alterazioni elettrolitiche da trimetoprim (iperkaliemia, iponatriemia), quindi l'associazione temporale è stretta; il farmaco è inoltre riportato a possibile rischio di allungamento del QT. (B) Elemento che riduce il valore rassicurante dell'Holter: il secondo episodio è SUCCESSIVO all'Holter pulito del 01-02/09, che quindi non copre la sintomatologia più recente — dato che rafforza l'indicazione a un monitoraggio prolungato (loop recorder o Holter multi-giorno) piuttosto che a un singolo esame di 24 ore. Denominatore comune di TUTTI gli eventi, documentati e percepiti: insorgenza dopo giornata lavorativa, in contesto di deprivazione di sonno protratta e stress lavorativo elevato; nessun evento nei periodi di allenamento regolare. ESAMI EMATOCHIMICI: l'atleta conferma di NON averne di recenti in tutto l'iter. Da chiedere potassio, magnesio, sodio, creatinina, TSH, emocromo, ferritina. Nota: a 2+ giorni dalla sospensione del farmaco un'eventuale alterazione indotta dal cotrimossazolo può essersi già normalizzata, quindi il valore retrospettivo è limitato e il valore principale è avere un basale.*

## Stato allenamento corrente

Nessun mesociclo attivo.

## Baseline fisiologiche (finestra 28gg)
- HR riposo: 51 bpm tipica (range 47-64)
- HRV rMSSD baseline: 76 ms (n=27)

## Pattern osservati (belief non flaggate, weak+)
- [validated_belief n=13 conf=0.95] Superamento zone in sessioni tecnica/recupero (HR media 151bpm in Z2 target, 80% Z3 in recovery)
- [validated_belief n=11 conf=0.95] Fatica muscolare braccia ricorrente + scarsa mobilità spalle (RPE 4, n=6 debrief, pace lenta)
- [validated_belief n=9 conf=0.95] Overpacing in test soglia (HR 194bpm, calo potenza finale, pacing irregolare)
- [validated_belief n=8 conf=0.95] RPE sottostimato Z3-Z4 (delta -1.5, RPE 2 con gambe pesanti, incoerenza HR 155bpm)

## Storico test fisiologici

| Data | Disciplina | Metodo |
|---|---|---|
| 2026-06-21 | run | manual_heat_corrected |
| 2026-06-04 | swim | CSS Test 400-200 (vasca lunga 50m, 04/06/2026) |
| 2026-05-30 | run | threshold_run_20min_provisional |
| 2026-05-26 | bike | FTP Test 20min (26/05/2026, Padova, percorso piatto) |
