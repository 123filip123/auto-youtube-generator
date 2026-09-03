# Frontend

React + TypeScript + Vite + Tailwind v4 + shadcn/ui.

Styling is deliberately plain — default shadcn components, no theme work yet.

```bash
npm install
npm run dev     # http://localhost:5173, proxies /api and /media to :8000
npm test        # vitest
npm run build   # type-check and build into dist/
```

The backend must be running on port 8000 (`uvicorn api.app:app --port 8000`
from the repository root).

`src/lib/types.ts` mirrors `api/schemas.py` field for field. When you change
one, change the other.

## Layout

| Path | Responsibility |
|---|---|
| `src/lib/types.ts` | TypeScript mirror of the wire contract. |
| `src/lib/api.ts` | Typed `fetch` wrapper, one function per endpoint. |
| `src/hooks/useRun.ts` | Polls one run until it reaches a terminal status. |
| `src/components/` | `StageProgress`, `AssetList`, `LogPanel`, `ItemEditor`. |
| `src/pages/` | One file per route. |
| `src/components/ui/` | shadcn components — generated, don't hand-edit. |

## Notes

- `src/setupTests.ts` stubs `ResizeObserver` and the pointer-capture methods.
  jsdom implements neither, and Radix primitives call them on mount.
- Tests never hit the network; `fetch` is stubbed per test.
