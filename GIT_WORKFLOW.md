# Git-arbetsflöde — isolerade worktrees (frontend / backend)

Sessionerna är uppdelade (se CLAUDE.md): **frontend** äger `app.py`,
**backend** äger `etoro_analys.py`, pipelinen, `SCHEMA.md` och `UTBYGGNAD_*.md`.
För att de aldrig ska dela utcheckning och skriva över varandra jobbar de i
**var sin katalog (git worktree)** på var sin gren, och deployar till `main`
(som Render bygger från).

## Kataloger & grenar

| Katalog | Gren | Session | Rör filer |
|---|---|---|---|
| `…/Aktieanalys` | `frontend` | frontend | `app.py`, frontend-assets |
| `…/Aktieanalys-backend` | `backend` | backend | `etoro_analys.py`, `SCHEMA.md`, `UTBYGGNAD_*.md`, pipeline |
| *(ingen)* | `main` | — | **deploy-gren** — Render bygger härifrån. Checkas inte ut; uppdateras bara via push. |

Båda worktree:erna delar samma `.git`. Eftersom en gren bara kan vara utcheckad
i **en** worktree kan sessionerna aldrig råka stå på samma gren — kollisionen som
hände tidigare är nu omöjlig.

**Backend-sessionen ska köras i `…/Aktieanalys-backend`.** Frontend-sessionen
stannar i `…/Aktieanalys`.

## Så jobbar du (per session)

1. Jobba och committa i din egen katalog på din egen gren. Du behöver aldrig
   byta gren — worktree:n är låst till din.
2. **Deploya** (slår ihop din gren med `main` och triggar Render) — utan att
   checka ut `main`:
   ```
   git fetch origin
   git merge origin/main        # ta in andra sessionens senast deployade
   git push origin HEAD:main     # deploya din gren → Render
   ```
   `merge origin/main` hämtar in den andra sessionens filer (olika filer →
   ingen konflikt); `push origin HEAD:main` fast-forwardar `main` till din HEAD.

## Viktigt

- **Committa aldrig direkt genom att checka ut `main`.** All main-uppdatering
  sker via `push origin HEAD:main` ovan — då bevaras båda historikerna och ingen
  reset kan råka radera den andras arbete.
- Frontend och backend rör **olika filer**, så deras merges krockar inte i praktiken.
- Ny worktree skapas (om den saknas) med:
  `git worktree add ../Aktieanalys-backend backend`
  Lista dem med `git worktree list`.
