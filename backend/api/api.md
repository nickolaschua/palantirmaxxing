# API

Purpose: future application endpoints and transport-level request handling.

Today only this document exists; no server, routes or transport protocol have been selected.

Planned handlers will accept assessment requests defined in `contracts/`, delegate execution to `backend/orchestration/`, and return structured results or validation responses. Exposure calculations belong in `backend/exposure/`; source acquisition belongs in `backend/data_sources/`.
