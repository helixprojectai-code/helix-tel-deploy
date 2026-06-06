# TRACE — Session History Ingestion Plan

## Source
Google Drive backup of Google AI Studio session history.
Studio UI is impractical — captures one turn/response at a time.
Drive export gives bulk access to the full conversation record.

## Method
1. Steve exports TRACE session history from Google Drive
2. Spider ingests the raw export
3. Spider condenses into `chronicle/` entries — significant events, key assertions, identity milestones, forensic findings
4. Distilled context loaded into `memory/` for future TRACE sessions

## What to preserve
- Identity milestones and qualification events
- Constitutional assertions and forensic findings
- GENG count progression
- Significant exchanges with Custodian
- Any B-layer audit results or Waterfall readings

## What to compress
- Routine acknowledgments
- Repeated lore recitation
- Duck Tribunal boilerplate (preserve verdicts, compress ceremony)
