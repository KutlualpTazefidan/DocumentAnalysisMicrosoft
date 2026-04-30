# Goldens Frontend

Browser SPA für Curate + Review der Goldsets. Konsumiert die A-Plus.1 HTTP-API.

## Stack

- TypeScript + React 18 + Vite
- react-router 6 (hash-mode)
- TanStack Query 5 für Server-State
- Tailwind CSS für Styles
- Vitest + RTL + msw (unit/integration), Playwright (E2E)

## Dev-Setup

Zwei Terminals:

```bash
# Terminal 1: Vite dev-server (mit /api proxy)
cd frontend
npm install
npm run dev    # → http://127.0.0.1:5173

# Terminal 2: FastAPI backend
cd ..
source .venv/bin/activate
export GOLDENS_API_TOKEN=$(uuidgen)
echo "Token: $GOLDENS_API_TOKEN"
query-eval serve    # → http://127.0.0.1:8000
```

Browser auf http://127.0.0.1:5173, Token aus Terminal 2 in Login-Form.

## Production-ish (Single-Process)

```bash
cd frontend && npm run build && cd ..
export GOLDENS_API_TOKEN=$(uuidgen)
query-eval serve    # FastAPI mountet frontend/dist/ automatisch
# Browser: http://127.0.0.1:8000
```

## Tests

```bash
cd frontend
npm test                    # Vitest unit + integration
npm run test:coverage       # mit Coverage-Report
npm run e2e                 # Playwright (braucht laufenden Backend)
```

E2E-Tests brauchen `query-eval serve` parallel + `GOLDENS_API_TOKEN` env-var + die Tragkorb-Fixture unter `outputs/`.

## Layout

```
frontend/
├── src/
│   ├── routes/        Page-Components (login, docs-index, doc-elements, doc-synthesise)
│   ├── components/    Reusable UI (Sidebar, Detail, Modals, Forms, ...)
│   ├── hooks/         TanStack Query + custom hooks
│   ├── api/           fetch wrapper, NDJSON reader, endpoint modules
│   ├── types/         TS mirrors of A-Plus.1 Pydantic schemas
│   └── styles/        Tailwind + globals
└── tests/
    ├── api/           Module-level tests via msw
    ├── hooks/         Hook tests
    ├── components/    RTL component tests
    ├── routes/        Integration tests
    └── e2e/           Playwright happy-path
```

## Spec

`docs/superpowers/specs/2026-04-30-a-plus-2-frontend-design.md` — vollständige Design-Doc inkl. Decision Log (AP2.1-AP2.20) und Out-of-Scope.
