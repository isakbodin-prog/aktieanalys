# eToro Portföljanalys — Projektöversikt

## Mål
Automatiskt hämta och jämföra 5 eToro-investerares portföljer, identifiera
konsensusinnehav (aktier i ≥3 av 5 portföljer), och berika med teknisk
analys + analytikerdata till en rankad Excel-rapport.

## Profiler som bevakas
thomaspj, michalhla, JeppeKirkBonde, triangulacapital, Smudliczek, ingruc

## Status just nu
- `etoro_analys.py` FUNGERAR HELT (verifierat 2026-07-06): alla 5 portföljer
  hämtas, tickers slås upp korrekt, portfolj_analys.xlsx genereras
- Ticker-uppslaget LÖST: GET /market-data/instruments UTAN parametrar
  returnerar hela instrumentlistan (~15 500 st) i ett svar. Ticker finns i
  `symbolFull`, ID i `instrumentID` (toppnyckel: instrumentDisplayDatas).
  Skriptet hämtar listan en gång och slår upp lokalt.
- thomaspj verifierad 15/15 mot kända innehav per 2026-07-01
- Konsensus (≥3 portföljer): AMZN (4 st), MU, TSM, NVDA, ASML

## API-detaljer (eToro Public API, lanserat feb 2026)
- Bas-URL: https://public-api.etoro.com/api/v1
- Headers på varje anrop: x-api-key (offentlig nyckel), x-user-key
  (privat nyckel), x-request-id (ny UUID per anrop)
- Nycklar: läses från .env i projektmappen (egen parser i skriptet, ingen
  python-dotenv); miljövariablerna ETORO_API_KEY/ETORO_USER_KEY har företräde
- Rate limit: 429 + Retry-After-header, respektera den
- /user-info/people/search ger 404 — använd INTE, username går direkt i path
- /market-data/instruments: kommaseparerade instrumentIds ger 500; upprepad
  param (?instrumentIds=A&instrumentIds=B) ger 200 men bara SISTA ID:t.
  Enda fungerande batchmetoden är att hämta HELA listan utan parametrar.
- Auth-test som funkar: GET /market-data/search?query=Apple → 200

## Körlägen (CLI)
- `python3 etoro_analys.py` — standardanalysen (signalgruppens 5 profiler).
  Divergensen räknas från cachade bakgrundsportföljer, inga extra anrop.
- `python3 etoro_analys.py --screener` — screena fram bakgrundsgruppen:
  två perioder (OneYearAgo + LastYear, TwoYearsAgo finns ej i API:et),
  kräver närvaro i båda, rankar på snittgain − 5×riskpoäng (ALDRIG på
  copiers; copiersMin=50 bara som spökkontofilter). Sparar topp 50 med
  nyckeltal till bakgrund_topp50.json (gist-synkad, kan handjusteras).
  Kör INTE analysen.
- `python3 etoro_analys.py --divergens` — hämtar om bakgrundsgruppens
  portföljer (kräver att --screener körts, annars RuntimeError) till
  bakgrund_cache.json och kör sedan hela analysen.
- `--force-claude` — kringgår Claude-dagsspärren (kombinerbar med ovan).
- Webbappen kör alltid standardläget; bakgrunden uppdateras bara via CLI.

## Pipeline (i skriptet)
1. Hämta 5 portföljer → aggregera investmentPct per instrumentId
2. Konsensus: instrument i ≥3 portföljer (MIN_PORTFOLIOS=3)
3. Teknisk analys via yfinance: RSI14, MA50/MA200, golden cross, MACD,
   Bollingerband, 52v-nivåer, 1m/3m-momentum, volymtrend
4. Analytikerdata via yfinance: rekommendation, riktkurs, uppsida %
5. Claude-analys: indikatorerna skickas till Claude API (anthropic-SDK,
   modell claude-opus-4-8, adaptive thinking) som skriver en analys på
   svenska per konsensusaktie + rekommendation (KÖP/AVVAKTA/SÄLJ).
   Kräver ANTHROPIC_API_KEY i .env — saknas den hoppas steget över.
   DAGSSPÄRR: körs max 1 gång/dag (claude_datum i senaste_analys.json);
   samma dag återanvänds texterna, men NYA konsensusaktier analyseras.
   Kringgå med force_claude=True / CLI-flaggan --force-claude.
   HELGVILA: lördag/söndag återanvänds senaste analysen (marknaden
   stängd) och appen hämtar ingen ny data — fredagens data är färsk.
   Webbappen hämtar eToro-data automatiskt vid sidöppning BARA om dagens
   data saknas (senaste_analys.json:s tidpunkt ≠ idag); annars visas
   befintlig data direkt. Kallstart utan lokal fil → gist_pull först.
   "Uppdatera nu"-knappen tvingar alltid en färsk hämtning.
6. Historik: jämför med förra körningen (portfolj_historik.json) och
   loggar NYTT INNEHAV / SÅLT INNEHAV / VIKTÄNDRING (≥1 procentenhet) /
   IN/UT UR KONSENSUS / IN/UT UR NÄRA KONSENSUS (med övergångsdetalj,
   t.ex. "upp från nära konsensus"). Loggen ackumuleras över tid.
   Appen visar 🆕-badge (ny på lista ≤7 dagar) och "Lämnat listorna"
   (≤30 dagar) längst ner på Konsensus-fliken.
6b. Innehavstid: positionernas openTimestamp/netProfit aggregeras per
   aktie (äldsta öppning, snittdagar, investeringsviktad vinst) →
   result["innehav"]. Visas i app/Excel och skickas till Claude som
   underlag för vinsthemtagningsrisk (lång tid + hög vinst = varning).
7. Skriv portfolj_analys.xlsx: Konsensus & Analys, Teknisk analys
   (indikatorer + Claudes text), Historik, en flik per profil

## Deploy (GitHub + Render)
- Repo: https://github.com/isakbodin-prog/aktieanalys (privat) — push till
  main triggar automatisk deploy på Render (gratisnivå, somnar efter 15 min)
- Start command: streamlit run app.py --server.port $PORT
  --server.address 0.0.0.0 --server.headless true
- Miljövariabler på Render: ETORO_API_KEY, ETORO_USER_KEY,
  ANTHROPIC_API_KEY, APP_PASSWORD (lösenordsskydd, aktivt bara när satt),
  GIST_ID + GITHUB_TOKEN (beständig historik, se nedan)
- Renders disk är TILLFÄLLIG → portfolj_historik.json och
  senaste_analys.json synkas mot en privat GitHub Gist (gist_pull vid
  körningsstart, gist_push efter körning). Utan gisten nollställs
  historiken OCH Claude-dagsspärren vid varje omstart.

## Webbapp (Streamlit)
- Starta: `python3 -m streamlit run app.py` → öppnas på http://localhost:8501
- Flikar: Bästa köp (sammanvägd poäng 0–100, se compute_score),
  Konsensus (tabell med trend/Claude-rek + "Nära konsensus"-sektion för
  aktier i 2 av 5 portföljer), Claudes analys (expanderbara kort per
  aktie), Senaste ändringar (in-/utflöden från senaste körningen),
  Historik (filtrerbar ändringslogg), Portföljer (innehav + diagram)
- Sidopanel: "Kör ny analys"-knapp (med valbar Claude-analys) +
  Excel-nedladdning
- Appen anropar run_analysis() i etoro_analys.py och läser/skriver
  senaste_analys.json

## Filer
- etoro_analys.py — pipelinen (run_analysis() är entrén, main() för CLI)
- app.py — Streamlit-webbappen
- .env — API-nycklar: ETORO_API_KEY, ETORO_USER_KEY, ANTHROPIC_API_KEY
  (chmod 600, checka ALDRIG in / dela ej)
- portfolj_analys.xlsx — Excel-rapport (genereras)
- senaste_analys.json — senaste körningens resultat, läses av appen
  (genereras)
- portfolj_historik.json — ögonblicksbild + ändringslogg (genereras,
  radera ej — då nollställs historiken)
- thomaspj_portfolio.xlsx — äldre manuell version (ersatt av Historik-fliken)

## Nästa steg
1. Ev. cacha instrumentlistan lokalt (JSON-fil) för snabbare körningar
2. Ev. schemalagd körning (cron/launchd) så historiken fylls på automatiskt