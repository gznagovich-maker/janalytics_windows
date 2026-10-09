"""
sheet_dashboard
===============
Dashboard di analisi che integra un Google Sheet "PASRS" (PALKIA Academy
Showdown Reporting Spreadsheet) con l'analisi nativa dei replay di JAnalytics.

Moduli:
  - models            : dataclass di dominio (DTO)
  - sheet_client      : accesso HTTP al Google Sheet (tab, CSV, htmlview)
  - sheet_mapper      : mapping dei tab del foglio verso i DTO
  - replay_resolver   : download/parsing dei log Showdown (identità Specie+Forma)
  - dashboard_stats   : statistiche pure (filtri, usage, matchup, lead)
  - dashboard_worker  : QThread che orchestra il caricamento
"""
