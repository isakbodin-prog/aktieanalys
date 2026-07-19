# Git-arbetsflöde — två grenar (frontend / backend)

Sessionerna är uppdelade (se CLAUDE.md): **frontend** äger `app.py`,
**backend** äger `etoro_analys.py`, pipelinen, `SCHEMA.md` och `UTBYGGNAD_*.md`.
För att de inte ska skriva över varandras commits på `main` jobbar de på var
sin gren och slår ihop till `main` (som Render deployar från).

## Grenar

| Gren | Ägs av | Rör filer |
|---|---|---|
| `main` | (delad) | **deploy-gren** — Render bygger härifrån. Uppdateras bara via merge. |
| `frontend` | frontend-sessionen | `app.py`, frontend-assets |
| `backend` | backend-sessionen | `etoro_analys.py`, `SCHEMA.md`, `UTBYGGNAD_*.md`, datapipelinen |

Eftersom frontend och backend rör **olika filer** krockar deras merges till
`main` inte i praktiken (git slår ihop icke-överlappande filer rent).

## Så jobbar du (per session)

1. Stå på din gren innan du börjar:
   - frontend: `git checkout frontend`
   - backend:  `git checkout backend`
2. Gör dina ändringar och committa **på din gren** (aldrig direkt på `main`).
3. När du vill driftsätta — slå ihop din gren till `main` och pusha:
   ```
   git checkout main
   git merge <din-gren>        # frontend eller backend
   git push origin main        # → Render deployar
   git checkout <din-gren>     # tillbaka till din gren
   ```
4. Håll din gren i synk med main när den andra sessionen deployat:
   ```
   git checkout <din-gren>
   git merge main
   ```

## Viktigt

- **Committa aldrig direkt på `main`.** All main-uppdatering sker via merge —
  då bevaras båda historikerna och ingen reset kan råka radera den andras arbete.
- Sessionerna **delar samma arbetskatalog**: `git checkout` byter grenen för
  BÅDA. Stå därför alltid på din egen gren innan du committar, och undvik att
  köra båda sessionerna samtidigt mitt i osparade ändringar. (Vill man köra
  parallellt helt isolerat: använd `git worktree` för en separat katalog per
  gren.)
