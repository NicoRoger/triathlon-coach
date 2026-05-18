"""Cognitive layer (Fase 4 MVP).

Riorganizzazione semantica dei moduli per chiarezza:

    cognition/
    ├── prediction/    # forecast numerici (FTP, race time, CTL projection)
    ├── inference/     # interpretazione pattern (beliefs, observations)
    └── prescription/  # azioni (priority engine, modulation, planner)

I sub-package re-esportano i moduli esistenti (no spostamenti fisici)
per non rompere import. La separazione è semantica, non strutturale.

Per il vero refactor fisico, vedi Fase 5 (future expansion).
"""
