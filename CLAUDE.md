# eToro Portföljanalys — Projektöversikt

## Sessionsuppdelning (backend / frontend)
Arbetet är uppdelat på två sessioner med skilda ansvarsområden:
- **Backend** äger `etoro_analys.py`, eToro-API-logiken, poängmodellen,
  datapipelinen och alla `UTBYGGNAD_*.md`-specar. Rör ALDRIG `app.py`.
- **Frontend** äger `app.py` (Streamlit-UI:t). Rör ALDRIG `etoro_analys.py`.
- **`SCHEMA.md` är kontraktet dem emellan** — det exakta dataformatet på
  JSON-filerna (främst `senaste_analys.json`). Ändrar backend ett fält som
  UI:t läser måste `SCHEMA.md` (kod + changelog-sektion) uppdateras i samma
  commit. Frontend bygger mot SCHEMA.md, inte mot backend-koden.

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
- Konsensus per 2026-07-13 (in 4/6, kvar 3/6): AMZN, MU, NVDA, PYPL.
  TSM föll ur på viktkravet (3 ägare men viktad konsensus 2,5 < 3,0)

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
- INGEN endpoint för att slå upp gain/risk-nyckeltal för en SPECIFIK,
  namngiven profil (sonderat 2026-07-13): /user-info/people/{user} → 404,
  /user-info/people/{user}/stats → 404, /people/search saknar
  username/nickName/query-parameter (alla ger 404). /search är bara en
  bred discovery-endpoint med filter (gainMin, riskScore, etc.), ingen
  exakt namnträff. portfolio/live:s toppnivå saknar också gain/risk.
  → FAS 2.6 tradervikting (UTBYGGNAD_screener_v3.md §6) är därför INTE
  implementerad — tradervikt är neutral (1.0) för alla. Försök inte
  samma endpoints igen utan ny information.

## Kända miljöbegränsningar
- **Yahoo/yfinance-blockering på Render är INTERMITTENT och ASYMMETRISK**
  (verifierat 2026-07-17, körning 09:17 UTC): per-aktiefälten (§7–§10:
  EPS-rev, forward P/E, PEG, riktkursspridning, nästa rapport, sektor)
  kan komma igenom helt normalt i SAMMA körning som SPY-anropet för
  marknadsregimen (§A) blockeras/rate-limitas. Det är alltså inte "allt
  eller inget" — olika yfinance-anrop inom samma körning kan lyckas
  respektive misslyckas oberoende av varandra.
  - Motåtgärd för regimen: REGIM_TICKER_KEDJA (SPY → ^GSPC → VOO → IVV,
    alla S&P 500-trackare, identisk MA200-regim) i compute_market_regime()
    — bara om ALLA fyra misslyckas återanvänds senaste kända regim, med en
    åldersvarning ("⚠ regim baserad på X dagar gammal data") om den
    återanvända regimen är äldre än REGIM_ALDER_VARNING_HANDELSDAGAR (5).
  - Motåtgärd för per-aktiefälten: fältvis återanvändning från förra
    körningen (se Pipeline steg 3–4 ovan).
  - Nästa eskaleringssteg OM blockeringen förvärras (implementera INTE
    förrän det faktiskt behövs): beräkna regimen lokalt (utanför Render)
    och gist-synka resultatet, så Render aldrig behöver nå Yahoo för just
    SPY/index-anropet. Samma idé kan i så fall appliceras på per-aktie-
    fälten om de också blir konsekvent blockerade, inte bara intermittent.

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
- `python3 etoro_analys.py --utvardera` — utvärderar poängmodellen mot
  faktisk forward-avkastning (21/63/126 dgr) ur screener_facit.json
  (loggas automatiskt vid varje analyskörning, gist-synkad). Rapport per
  poängkvartil, komponentkorrelation och divergensutfall till terminal +
  utvardering.xlsx. Kör INTE analysen. Varnar vid n<10. Kör även §3b:
  (A) EPISODMÄTNING — rekonstruerar Bästa köp-perioder ur historikens
  IN/UT UR KONSENSUS och EXIT (TRENDBROTT) (§B), mäter överavkastning mot
  SPY (+ sektor-ETF) med justerade priser; stängda vs öppna episoder
  separat (överlevnadsfel), split på Claudes rek vid inträde OCH på
  ut_orsak ("trendbrott" vs "konsensus tappad"). (B) FYRA PAPPERSPORTFÖLJER —
  P1 likaviktad / P2 poängviktad / P3 SPY b&h / P4 poäng+Claude-filter;
  kedjad avkastning, omsättning, drawdown, parvisa differenser (urvalets/
  poängmodellens/Claudes värde). Flikar Episoder + Pappersportföljer i
  utvardering.xlsx. Pappersvikter loggas per körning till pappersportfolj-
  .json (gist-synkad); facit har fältet claude_rek sedan 2026-07-14.
- `--force-claude` — kringgår Claude-dagsspärren (kombinerbar med ovan).
- Webbappen kör alltid standardläget; bakgrunden uppdateras bara via CLI.

## Pipeline (i skriptet)
0. Marknadsregim (§A, UTBYGGNAD_regim_exit.md): index vs dess MA200 → GRÖN
   (över + stigande) / RÖD (under + fallande) / GUL (blandat, bara
   varning) / OKÄND (hela kedjan missade, behandlas som GRÖN). REGIM_TICKER_
   KEDJA provas i tur och ordning (SPY → ^GSPC → VOO → IVV, alla S&P 500 —
   identisk MA200-regim) så att en enskild blockerad ticker inte slår ut
   hela beräkningen (se § Kända miljöbegränsningar); regim_kalla anger
   vilken som lyckades. Misslyckas ALLA fyra återanvänds senaste kända
   regim (regim_datum = datum för senaste LYCKADE beräkning, ej senaste
   körning); är den återanvända regimen äldre än 5 handelsdagar eskaleras
   notisen till en varning ("⚠ regim baserad på X dagar gammal data") i
   JSON, Excel-headern och appens regimbadge — regimen fortsätter gälla
   funktionellt (GRÖN beter sig som GRÖN), bara notisen ändras.
   Bara RÖD har effekt: Claudes KÖP-text på Bästa köp-aktier visas
   nedgraderad ("KÖP (vänta på marknaden)") via claude[tk].rekommendation_
   visning — den råa rekommendation-nyckeln och poängen/facit förblir
   OFÖRÄNDRADE. Pappersportföljerna (P1/P2/P4) gör inga nya köp i RÖD —
   kandidater som inte fanns i föregående ombalansering hålls i kassa
   (nya_i_kassa i pappersportfolj.json). Skrivs till result["regim"].
1. Hämta 5 portföljer → aggregera investmentPct per instrumentId
2. Konsensus: PROCENTUELLA trösklar med HYSTERES (ersatte MIN_PORTFOLIOS=3
   2026-07-13). KONSENSUS_ANDEL_IN=0.60 för att komma IN på listan,
   KONSENSUS_ANDEL_KVAR=0.50 för att LIGGA KVAR (kvarnivån gäller bara
   aktier som var konsensus förra körningen — läses ur portfolj_historik-
   .json via load_previous_consensus()). Antal ägare mot ceil(andel×N):
   6 profiler → IN 4, KVAR 3. DUBBELVILLKOR (skalat från §1) gäller ENDAST
   INnivån: antal ägare >= tröskeln OCH viktad_konsensus (Σ färskhetsvikt)
   >= samma tal — en ny kandidat med gamla/passiva köpare klarar inte IN på
   bara antal. På KVARnivån (hysteres, redan etablerad konsensusaktie)
   styr ENDAST antalsvillkoret listmedlemskapet — designbeslut 2026-07-17
   efter TSM-fallet (3 ägare, viktad_konsensus 2,5 < 3,0 hade annars fällt
   ur den trots oförändrat antal). Viktad konsensus påverkar ändå poängen
   (Konsensus-komponenten i compute_score_v2), bara inte listmedlemskapet.
   Tre nivåer returneras av compute_consensus(): konsensus,
   nära konsensus (klarar kvarnivåns antal men ej in), bubblarnivå
   (exakt en ägare under kvarnivån — bubblare = de med divergens ≥ +30).
   Historiksnapshoten bär regelversion (KONSENSUS_REGEL) — nivåövergångar
   loggas bara mellan körningar med samma regel, så en omdefinition
   spammar inte "Lämnat listorna". IN/UT-poster anger tillämpad tröskel.
3. Teknisk analys via yfinance: RSI14, MA50/MA200, golden cross, MACD,
   Bollingerband, 52v-nivåer, 1m/3m-momentum, volymtrend
4. Analytikerdata via yfinance: rekommendation, riktkurs, uppsida %, EPS-rev,
   forward P/E, PEG, riktkursspridning, nästa rapport, sektor. Alla dessa
   fält (och SPY-regimen i steg 0) kan falla bort tyst om Yahoo blockerar/
   rate-limitar molnservrar (Render) — även när prishistoriken i steg 3
   fungerar (separata yfinance-anrop: .info/.eps_trend/.calendar).
   DIAGNOSTIK (2026-07-17): varje tyst fallback loggar nu ticker + fält +
   feltyp/meddelande via _logga_yf_miss() — "OBS: yfinance-miss för
   TICKER.fält: ExceptionType: meddelande" (eller en beskrivning om det
   inte var en exception, t.ex. ett misstänkt tunt .info-svar utan fel).
   Kör lokalt och jämför med Render-loggen för att skilja "miljön blockerad"
   från "koden trasig". FALLBACK: faller ett §7–§10-fält bort trots att
   prisdata (datakälla Yahoo) finns, återanvänds fältet från förra
   körningens analys (samma mönster som riktkurs-fallbacken); SPY-regimen
   återanvänder på samma sätt förra kända GRÖN/GUL/RÖD i stället för att
   visa OKÄND.
   Värderingspoängen (§7, se UTBYGGNAD_screener_v2.md) blir NEUTRAL (5/10)
   om data helt saknas — aldrig 0, som annars är omöjligt att skilja från
   en genuint dyr aktie. Excel-kommentar flaggar cellen när detta slår till.
5. Claude-analys: en tokensnål, explicit fältlista (ticker, pris, valuta,
   RSI14, MA50/MA200, stigande_trend, MACD/golden-cross-status, Bollinger,
   52v-läge, 1m/3m-momentum, poäng v2 + delpoäng, viktad konsensus,
   divergens, EPS-rev, riktkurs+spridning, uppsida, innehavstid/vinst,
   nästa rapport, EXIT) — ALDRIG hela indikator-dicten eller rå
   yfinance-data — byggs av _bygg_claude_input() och skickas till Claude
   API (anthropic-SDK) som skriver en analys på svenska (max ~120 ord,
   naturligt språk utan råa fältnamn eller markdown) per konsensusaktie +
   rekommendation (KÖP/AVVAKTA/SÄLJ). Regimen skickas INTE med i prompten
   (visas redan i rapportheadern; en återanvänd text skulle annars bära en
   inaktuell regim-etikett) — se i stället regimskifte-triggern nedan.
   Kräver ANTHROPIC_API_KEY i .env — saknas den hoppas steget över.
   Sonnet-omanalyser körs UTAN adaptive thinking (ren textbudget,
   max_tokens=600); Opus-grundanalyser ("ny på listan") behåller adaptive
   thinking med mer marginal (max_tokens=2000), eftersom thinking äter av
   samma budget. Trimningen (2026-07-16) sänkte snittförbrukningen från
   ~10 300 till ~1 600 tokens/anrop (85 %) utan kvalitetsförlust.
   DAGSSPÄRR: körs max 1 gång/dag (claude_datum i senaste_analys.json);
   samma dag återanvänds texterna, men NYA konsensusaktier analyseras.
   Kringgå med force_claude=True / CLI-flaggan --force-claude.
   HELGVILA: lördag/söndag återanvänds senaste analysen (marknaden
   stängd) och appen hämtar ingen ny data — fredagens data är färsk.
   CLAUDE-TRIGGERFILTER (inom dagsspärren/helgvilan, ändrar den INTE):
   behover_ny_analys(ticker, dagens_data, senaste_analys) avgör om en
   redan analyserad aktie omanalyseras — bara vid väsentlig förändring
   sedan claude[tk].indikator_snapshot sparades (RSI korsat 30/70, pris
   korsat MA200, MACD korsat signallinjen, golden/death cross, EXIT-status
   ändrad, poäng ändrat >10, viktad konsensus ändrad >1.0, regimskifte
   GRÖN↔RÖD (GUL/OKÄND triggar inte), eller text äldre än 7 dagar). Annars
   återanvänds texten och claude[tk].analys_alder_dagar
   uppdateras. Modellval: claude-opus-4-8 för grundanalys ("ny på listan" —
   aktien saknar sparad text), annars claude-sonnet-4-6 för omanalys av
   befintlig aktie (loggas i claude[tk].modell/.analys_orsak). Gamla texter
   utan indikator_snapshot omanalyseras en gång, sedan normalt.
   --force-claude kringgår triggerfiltret helt (alla omanalyseras) men
   modellvalet styrs ändå av "ny på listan"-status.
   TOKENFÖRBRUKNING: varje lyckat API-anrop loggas (datum/tidsstämpel,
   ticker, orsak, modell, input/output-tokens, cache-fält, körningsläge
   standard/divergens/force) till claude_forbrukning.json — en rad per
   anrop, gist-synkad. Saknas usage-objektet i svaret (äldre SDK) loggas
   raden ändå med tokenfälten null + en varning, kraschar aldrig. Filen
   komprimeras automatiskt (rader >90 dagar → veckosummor per modell,
   uppdelat på drift/force — se nedan) när den växer förbi 5000 rader.
   Terminalsammanfattning efter Claude-steget: antal anrop per modell +
   antal återanvända, tokens denna körning, ackumulerat denna kalendervecka.
   --utvardera har en egen sektion "Claude-förbrukning" — uppdelad i
   NORMAL DRIFT (poster med genuin trigger, orsak != "force-claude": tokens
   per vecka, fördelning per orsak/modell, snitt per anrop — huvudsiffran)
   och en kompakt FELSÖKNING/FORCE-rad (poster som bara tillkom pga.
   --force-claude-flaggan, ingen egen trigger) som läggs under som tillägg
   ("+ N force-anrop..."), så testkörningar inte förorenar driftssiffrorna.
   OBS: denna gränsdragning (_är_force_post) är per POST på fältet `orsak`,
   inte samma som run-nivåns `körningsläge`-fält (som taggar hela anropet
   som "force" så fort flaggan användes, även tickers med egen genuin
   orsak som "ny på listan" — de räknas ändå som normal drift). Bara
   terminalrapport, ingen Excel-flik.
   Webbappen hämtar eToro-data automatiskt vid sidöppning BARA om dagens
   data saknas (senaste_analys.json:s tidpunkt ≠ idag); annars visas
   befintlig data direkt. Kallstart utan lokal fil → gist_pull först.
   "Uppdatera nu"-knappen tvingar alltid en färsk hämtning.
6. Historik: jämför med förra körningen (portfolj_historik.json) och
   loggar NYTT INNEHAV / SÅLT INNEHAV / VIKTÄNDRING (≥1 procentenhet) /
   IN/UT UR KONSENSUS / IN/UT UR NÄRA KONSENSUS (med övergångsdetalj,
   t.ex. "upp från nära konsensus") / EXIT (TRENDBROTT) / ÅTER FRÅN EXIT
   (§B, se nedan). Loggen ackumuleras över tid.
   Appen visar 🆕-badge (ny på lista ≤7 dagar) och "Lämnat listorna"
   (≤30 dagar) längst ner på Konsensus-fliken.
6b. Innehavstid: positionernas openTimestamp/netProfit aggregeras per
   aktie (äldsta öppning, snittdagar, investeringsviktad vinst) →
   result["innehav"]. Visas i app/Excel och skickas till Claude som
   underlag för vinsthemtagningsrisk (lång tid + hög vinst = varning).
6c. Exitregel (§B, UTBYGGNAD_regim_exit.md): dödskors — pris < MA200 OCH
   MA50 < MA200 (båda krävs, ren rekyl räcker inte) — flyttar aktien från
   ranking (Bästa köp) till result["exit_lista"] med exit_datum (första
   flaggningen, bevarat idempotent över körningar) och villkorstext.
   Konsensuslistan/divergensen påverkas INTE — aktien kan ligga kvar i
   konsensus men är flaggad. Episodmätningen (§3b Del A) räknar EXIT som
   ett UT-datum med ut_orsak "trendbrott" (skilt från "konsensus tappad").
   Pappersportföljerna säljer position till kassa vid nästa ombalansering
   eftersom ranking redan uteslutit aktien. Återinträde när villkoret
   inte längre gäller (ingen karenstid).
7. Skriv portfolj_analys.xlsx: Konsensus & Analys, Teknisk analys
   (indikatorer + Claudes text + EXIT-flagga), Rangordning (regimbadge +
   EXIT-sektion), Historik, en flik per profil

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