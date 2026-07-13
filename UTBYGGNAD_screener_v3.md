# UTBYGGNAD screener v2 — Nya analytiska parametrar

> STATUS 2026-07-13: FAS 1, FAS 2 och FAS 3 (inkl. §12 omviktning)
> implementerade i etoro_analys.py. §6 (tradervikting) ej implementerbar —
> se CLAUDE.md API-detaljer. Poäng (v1) kvar i Rangordning för jämförelse
> tills --utvardera samlat tillräckligt facit för att kalibrera de nya
> vikterna.

> Tillägg till `UTBYGGNAD_screener.md`. Implementeras i `etoro_analys.py`.
> Prioritetsordning: FAS 1 = störst signaleffekt per kodrad, implementera först.
> Alla nya parametrar ska degradera snyggt: saknas data för en aktie → neutral
> poäng (ej krasch, ej 0), och en notis i Excel-kolumnen ("data saknas").

---

## FAS 1 — Implementera först

### 1. Signalfärskhet (eToro-data som redan hämtas)

**Problem:** Konsensus behandlar ett 550 dagar gammalt innehav med +236 % vinst
(MU-exemplet) som samma signal som ett färskt köp. Gamla vinnare som ligger kvar
är svagare signaler än aktiva nyköp.

**Implementation:**
- Data finns redan: `openTimestamp` per position aggregeras i steg 6b.
- Ny funktion `farskhetsvikt(dagar_sedan_aldsta_kop, dagar_sedan_senaste_kop)`:
  - Senaste köp ≤ 30 dagar → vikt 1.5 ("aktivt köp")
  - Senaste köp ≤ 180 dagar → vikt 1.0
  - Äldre → vikt 0.5 ("passivt innehav")
- Viktningen appliceras per trader vid konsensusräkningen: en aktie ägd av 3
  traders räknas som `sum(farskhetsvikt_i)` i stället för `3`.
- KONSENSUSVILLKOR (dubbelt, båda krävs): `antal_agare >= MIN_PORTFOLIOS (3)`
  OCH `viktad_konsensus >= MIN_KONSENSUSVIKT (3.0)`. Antalsvillkoret behålls
  eftersom viktningen annars öppnar en bakdörr: två traders med färska köp
  (2 × 1.5 = 3.0) skulle kvala in som "konsensus" — och med tradervikten i §6
  ovanpå (max 1.5 × 1.5 = 2.25/trader) räcker två traders med ännu större
  marginal. Viktningen mäter alltså intensitet INOM konsensus, den ersätter
  inte kravet på tre oberoende ägare.
- OBS: `openTimestamp` avser äldsta öppna position. Senaste köp approximeras med
  yngsta positionens openTimestamp per aktie/trader (finns i samma payload).
  Caveat (kommentera i koden): partiella stängningar lurar approximationen —
  stänger tradern sina äldsta lotter ser innehavet färskare ut än det är.

**Excel:** Ny kolumn i Konsensus & Analys: "Viktad konsensus" bredvid "Antal
portföljer". Ny kolumn "Senaste köp (dagar)" (min över traders).

**Acceptans:** MU:s viktade konsensus < 3.0 med nuvarande data (men MU behålls
i konsensuslistan om antal ägare >= 3 — den får bara lägre poäng); en hypotetisk
aktie med tre köp senaste månaden ger exakt 4.5 — testa med `>= 4.5 - epsilon`
eller `> 4.4`, inte `>= 4.5` rakt av (flyttalskänslighet).

### 2. Estimatrevideringar (yfinance, nytt)

**Problem:** Screenern använder riktkursens NIVÅ men inte dess RIKTNING.
Uppsida +50 % med fallande estimat är en klassisk fälla.

**Implementation:**
- `ticker.eps_trend` (DataFrame med current/7daysAgo/30daysAgo/60daysAgo/90daysAgo
  per period). Beräkna revisionskvot för innevarande + nästa räkenskapsår:
  `(current - 90daysAgo) / abs(90daysAgo)`.
- ROBUSTHET (obligatorisk): kvoten exploderar när 90daysAgo ligger nära noll
  och blir missvisande vid teckenbyte. Regler i prioritetsordning:
  1. Teckenbyte negativt → positivt: direkt +10 (hoppa över kvoten)
  2. Teckenbyte positivt → negativt: direkt -10
  3. `abs(90daysAgo) < 0.05`: neutral 0 (basen för liten för meningsfull kvot)
  4. Annars: clampa kvoten till intervallet [-50 %, +50 %] innan poängsättning
- Fallback om eps_trend saknas/tom: `ticker.revisions` eller hoppa (neutral).
- Poäng: revisionskvot > +5 % → +10; -5 % till +5 % → 0; < -5 % → -10.
  Läggs i Analytiker-komponenten (se omviktning i §12).

**Excel:** Kolumn "EPS-rev 90d (%)" i Konsensus & Analys + Teknisk analys.

**Acceptans:** Kolumnen fylls för ≥ 3 av 4 nuvarande konsensusaktier; saknad
data ger texten "–" och neutral poäng.

### 3. Utvärderingsloop (`--utvardera`)

**Problem:** Poängvikterna (30/25/25/20) är ovaliderade gissningar. Utan
facit-mätning optimeras screenern i blindo.

**Implementation:**
- Vid varje körning: appenda till `screener_facit.json` (gist-synkas som övriga
  JSON-filer): `{datum, ticker, poäng, poängkomponenter, pris, viktad_konsensus,
  divergens_pp}`. En rad per aktie på Rangordning + Divergens-flikarna.
- Ny CLI-flagga `--utvardera`:
  - Läser screener_facit.json, hämtar aktuella priser via yfinance (batch).
  - Beräknar forward-avkastning 21/63/126 handelsdagar per historisk rad
    (närmaste tillgängliga datum, yfinance history).
  - Rapport till terminal + ny Excel-flik "Utvärdering": avkastning per
    poängkvartil, per komponent (korrelation komponentpoäng ↔ forward-avkastning),
    divergens-decilernas träffsäkerhet.
  - Kör INTE analysen (samma mönster som --screener).
- Kräver ingen daglig körning — glesa datapunkter är OK, rapporten anger n.
- BLIND FLÄCK (skriv in i rapportens rubrik): facit-filen innehåller bara
  aktier screenern lyfte fram. Loopen kalibrerar därmed den INTERNA
  rangordningen bland kandidater — den kan aldrig upptäcka vinnare som
  aldrig kom med i urvalet. Rubrikförslag: "Utvärdering av intern
  rangordning (mäter ej täckning)". En bra kvartilkorrelation får inte
  övertolkas som att screenern hittar de bästa aktierna på marknaden.

**Acceptans:** Efter två körningar på olika datum producerar `--utvardera` en
rapport utan krasch; med < 10 datapunkter skrivs varning "för tidigt för
slutsatser (n=X)".

---

## FAS 2 — Signalkvalitet

### 4. Korrelationsklusterjustering (ändrad från sektorbaserad)

**Problem:** Konsensuslistan AMZN/MU/TSM/NVDA är en (1) AI-tes, inte fyra
oberoende signaler. Klustring överskattar konsensusstyrkan.

**Varför INTE sektoretiketter:** i yfinance är MU/TSM/NVDA/ASML "Technology"
men AMZN är "Consumer Cyclical" och GOOG "Communication Services" — en
sektorjustering straffar chipklustret men missar att AMZN/GOOG tillhör samma
AI-tes. Etiketten fångar inte samvariationen som är det egentliga problemet.

**Implementation (korrelationsbaserad):**
- Beräkna parvis korrelation på 63-dagars dagliga avkastningar mellan alla
  aktier i körningen — prisdata finns redan hämtad, inga nya anrop.
- Kluster: greedy gruppering där aktier med parvis korrelation > 0.7 hamnar
  i samma kluster (enkel single-linkage räcker, inget bibliotek behövs).
- Vid poängberäkning: `konsensuspoäng_justerad = konsensuspoäng /
  sqrt(klusterstorlek)`. Ensam i sitt kluster → oförändrad; fyra i samma
  kluster → delat med 2.
- Robusthet: aktier med < 40 dagars gemensam prishistorik → eget kluster
  (neutral). Korrelationströskeln 0.7 är startvärde — utvärderingsloopen (§3)
  kan kalibrera den.
- Hämta ändå `ticker.info['sector']` (cachea i instrumentcachen) — som
  informativ Excel-kolumn, inte som klustringsgrund.
- Divergens-fliken: ny kolumn "Sektor", "Kluster-ID" + "Klusterfaktor".

### 5. Flödesriktning (nettoflöde 30 dagar)

**Implementation:**
- Historikloggen innehåller redan VIKTÄNDRING-poster. Aggregera per aktie:
  summan av signalgruppens viktändringar senaste 30 dagarna (procentenheter).
- Poäng: nettoflöde > +1.0 pe → +5; < -1.0 pe → -5; annars 0. Läggs i
  Konsensus-komponenten.
- Kräver att historiken har ≥ 2 körningar ≥ 7 dagar isär; annars neutral.

**Excel:** Kolumn "Nettoflöde 30d (pe)" i Konsensus & Analys.

### 6. Tradervikting i signalgruppen

**Implementation:**
- Återanvänd screener-nyckeltalen (snittgain, riskpoäng) som redan hämtas i
  --screener-läget, men hämta dem även för signalgruppens 5 profiler (en extra
  API-batch, cachea 7 dagar i `signalgrupp_nyckeltal.json`).
- Tradervikt = `1 + 0.5 * normaliserad_rank(gain - 5*risk)` inom gruppen
  (bästa trader 1.5, sämsta 1.0). Multipliceras med färskhetsvikten i §1.
- Konsekvens: konsensusvikt per aktie = Σ (tradervikt × färskhetsvikt).

---

## FAS 3 — Fundamentalt & tekniskt

### 7. Värderingskomponent

- `info['forwardPE']`, `info['pegRatio']` (fallback trailingPE).
- Jämför mot sektormedian beräknad över ALLA aktier i körningen (konsensus +
  nära konsensus + bubblare ger ~30 tickers, tillräckligt för grov median).
- Poäng: forward P/E < 0.8× sektormedian → +10; > 1.5× → -10; PEG < 1.5 → +5.
- Ny poängkomponent "Värdering (10)" — se §12.

### 8. Riktkursspridning

- `info['targetHighPrice']`, `info['targetLowPrice']`, `info['targetMeanPrice']`.
- Spridningskvot = (high - low) / mean. > 0.8 → flagga "hög osäkerhet" och
  halvera Analytiker-komponentens uppsidepoäng.
- **Excel:** Kolumn "Riktkurs spridning" (low–high) i Konsensus & Analys.

### 9. Rapportdatum-varning

- `ticker.calendar` → nästa rapportdatum. Ingen poängeffekt.
- **Excel:** Kolumn "Nästa rapport" + ⚠️-symbol om ≤ 7 dagar.
- **App:** Badge "Rapport om X dgr" på Bästa köp-fliken när ≤ 7 dagar.

### 10. Relativ styrka mot sektor

- Mappa sektor → ETF: Technology→XLK (halvledare→SOXX om industry innehåller
  "Semiconductor"), Consumer Cyclical→XLY, Communication→XLC, Financial→XLF,
  Healthcare→XLV, Industrials→XLI, Energy→XLE, övriga→SPY.
- RS = aktiens 63-dagarsavkastning − ETF:ns 63-dagarsavkastning.
- Poäng: RS > +5 pe → +5; < -5 pe → -5. Läggs i Momentum-komponenten.
- ETF-priserna hämtas en gång per körning (≤ 10 extra yfinance-anrop).

### 11. Volatilitetsjusterad positionsstorlek

- ATR14 (eller 90-dagars daglig stddev × sqrt(252)) från befintlig prishistorik
  (ingen ny hämtning).
- Föreslagen vikt = `målrisk / volatilitet`, normaliserad så snittförslaget
  blir 2 %. Tak 3 %, golv 0.5 %.
- **Excel:** Kolumn "Föreslagen vikt (%)" på Rangordning. **Ingen poängeffekt** —
  det är ett sizing-verktyg, inte en rankingfaktor.

---

## §12. Omviktad poängmodell

Ersätter dagens Trend 30 / Momentum 25 / Analytiker 25 / Konsensus 20:

| Komponent | Vikt | Innehåll |
|---|---|---|
| Trend | 25 | Oförändrad logik |
| Momentum | 20 | Befintlig + relativ styrka (§10) |
| Analytiker | 20 | Uppsida (halverad vid hög spridning §8) + EPS-revideringar (§2) |
| Konsensus | 25 | Viktad konsensus (§1, §6) + nettoflöde (§5), klusterjusterad (§4) |
| Värdering | 10 | §7 |

Vikterna är STARTVÄRDEN — utvärderingsloopen (§3) ska på sikt kalibrera dem.
Behåll gamla poängen som kolumn "Poäng (v1)" i Excel under en övergångsperiod
så serierna kan jämföras.

---

## Småfixar (från granskning 2026-07-13)

- **Claude-textens datum:** stämpla analystexten med genereringsdatum i
  Teknisk analys-fliken ("Analys genererad: YYYY-MM-DD") — dagsspärren gör att
  text och indikatorkolumner annars kan vara osynkade utan att det syns.
- **Valutaetikett:** Claude-prompten skriver "kr" på USD-priser (AMZN "247 kr").
  Skicka med valuta per instrument från eToro-payloaden eller yfinance
  `info['currency']` i prompten.

## Tekniska randvillkor

- Alla nya yfinance-fält: try/except per fält, neutral poäng vid miss.
- Inga nya eToro-anrop i standardläget utom §6 (cacheas 7 dagar).
- Nya JSON-filer (`screener_facit.json`, `signalgrupp_nyckeltal.json`) läggs
  till i gist-synken (gist_pull/gist_push) — annars nollställs de på Render.
- Excel-kolumnordning: nya kolumner läggs EFTER befintliga så att inlästa
  vyer/formler inte förskjuts.
- Webbappen: exponera "Viktad konsensus", "Nettoflöde" och "Föreslagen vikt"
  på Bästa köp-fliken; resten kan vänta.
