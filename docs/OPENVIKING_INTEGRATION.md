# OpenViking Integration Notes

## Goal
Use OpenViking as an optional memory backend without forcing AGPL obligations onto the core project path.

## Integration Strategy
- Core app depends on `MemoryStore` protocol only.
- `SQLiteStore` is default and always available.
- `OpenVikingMemoryAdapter` is optional and wrapped with fallback.
- On remote failure:
- adapter falls back to local SQLite
- failure cooldown is applied to reduce repeated timeout penalties

## Current Adapter Endpoints
The adapter currently attempts:
- `POST /api/v1/retrieval/find`
- `POST /api/v1/sessions/commit`
- `POST /api/v1/sessions/checkpoint`

If your deployed OpenViking service uses different paths or payloads, update:
- `deepresearch_x/memory/openviking.py`

## Required Env
```env
MEMORY_BACKEND=openviking
OPENVIKING_BASE_URL=http://127.0.0.1:8100
OPENVIKING_TIMEOUT_SECONDS=0.8
```

## Verification Checklist
1. Start OpenViking service.
2. Run one request with `memory_backend=openviking`.
3. Confirm response returns `200` and memory fields are populated.
4. Stop OpenViking service and rerun request.
5. Confirm request still succeeds via SQLite fallback.

## AGPL Boundary Note
- Core repository does not import OpenViking source code.
- Integration is via adapter and network boundary.
- You should still validate your deployment/distribution model with legal guidance for production use.
