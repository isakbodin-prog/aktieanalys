# SCHEMA.md — Datakontrakt backend ⇄ frontend

> **Detta är kontraktet mellan backend (`etoro_analys.py`) och frontend (`app.py`).**
> Frontend ska kunna byggas mot detta dokument UTAN att läsa backend-koden.
> Backend äger detta dokument. Ändrar backend ett fält som UI:t läser →
> uppdatera **både** koden och changeloggen nedan i samma commit.
>
> Sessionen är uppdelad: **backend** äger `etoro_analys.py`, pipelinen,
> poängmodellen och `UTBYGGNAD_*.md`. **frontend** äger `app.py`. Ingen rör
> den andras fil.

---

## Changelog

Notera datum + ändring varje gång ett fält som UI:t läser ändras
(nytt/borttaget/omdöpt/typändrat). Nyast överst.

- **2026-07-15** — Regimfilter & exitregel (UTBYGGNAD_regim_exit.md). Nya
  toppnycklar i `senaste_analys.json`: `regim` (marknadsregim GRÖN/GUL/RÖD/
  OKÄND, SPY vs MA200) och `exit_lista` (konsensusaktier uteslutna ur Bästa
  köp p.g.a. dödskors — pris<MA200 och MA50<MA200). `ranking` innehåller
  ALDRIG längre exit-aktier (de flyttas till `exit_lista`); konsensuslistan
  (`consensus`) är opåverkad. `claude`-entryn fick ett nytt fält
  `rekommendation_visning` (visningstext, degraderas till "KÖP (vänta på
  marknaden)" i RÖD regim — `rekommendation` förblir rått/oförändrat).
  `portfolj_historik.json.senaste` fick fältet `exit` ({ticker: exit_datum}).
  Nya historiktyper: `EXIT (TRENDBROTT)`, `ÅTER FRÅN EXIT`. `screener_facit.json`
  och pappersportföljerna är opåverkade i sak (ranking exkluderar redan
  exit-aktier innan de når dem). `pappersportfolj.json` kan nu ha en valfri
  `nya_i_kassa`-nyckel per post (RÖD regim → nya kandidater hölls i kassa).
- **2026-07-14** — §3b avkastningsmätning: `screener_facit.json` fick fältet
  `claude_rek`. Ny fil `pappersportfolj.json` (målvikter per ombalansering)
  dokumenterad och gist-synkad. Inga fält i `senaste_analys.json` ändrade —
  UI:t opåverkat. Nya rapportflikar (Episoder, Pappersportföljer) finns bara
  i `utvardering.xlsx`, som UI:t inte läser.
- **2026-07-13** — SCHEMA.md skapad. Dokumenterar nuläget efter att
  konsensus bytt till procentuella trösklar med hysteres (tre nivåer:
  `consensus` / `nara_konsensus` / `bubblar_niva`) och efter FAS 3
  (poängmodell v2 med komponenten `Värdering`, samt fälten `relativ_styrka`,
  `foreslagen_vikt_%`, `forward_pe`, `peg_ratio`, `riktkurs_*`,
  `nasta_rapport`, `volatilitet_arlig_%`).

---

## Filöversikt

| Fil | Skrivs av | Läses av UI? | Gist-synkad |
|---|---|---|---|
| `senaste_analys.json` | `run_analysis()` | **JA (primär)** | JA |
| `portfolj_historik.json` | `update_history()` | Indirekt (via `historik` i resultatet) | JA |
| `screener_facit.json` | `logga_facit()` | Nej (bara `--utvardera`) | JA |
| `pappersportfolj.json` | `logga_pappersportfolj()` | Nej (bara `--utvardera`) | JA |
| `bakgrund_topp50.json` | `run_screener()` | Nej | JA |
| `bakgrund_cache.json` | `load_background_portfolios()` | Nej | JA |

UI:t läser i praktiken **bara `senaste_analys.json`**. Historiken exponeras
redan inbakad i det som toppnyckeln `historik`.

---

## `senaste_analys.json`

Skrivs i sin helhet vid varje lyckad `run_analysis()`. Alla toppnycklar nedan
finns ALLTID (skrivs ovillkorligt). Tomma tillstånd representeras med `{}`,
`[]` eller `0` — aldrig avsaknad av nyckel.

### Toppnivå

| Nyckel | Typ | Alltid? | Beskrivning |
|---|---|---|---|
| `tidpunkt` | str | ✅ | ISO-datumtid, minutupplösning: `"2026-07-13T23:10"` |
| `profiler` | list[str] | ✅ | Signalgruppens användarnamn, t.ex. `["thomaspj", …, "ingruc"]`. Längden = gruppstorleken N. |
| `portfolios` | dict | ✅ | `{användarnamn: {ticker: vikt_pct}}`. Varje profils innehav. |
| `consensus` | dict | ✅ | Konsensusaktier. Se **Konsensus-entry**. Kan vara `{}`. |
| `nara_konsensus` | dict | ✅ | Nära konsensus (kvarnivåns antal, under innivån). Samma entry-form. |
| `bubblar_niva` | dict | ✅ | Bubblarnivå (en ägare under kvarnivån). Samma entry-form. |
| `konsensus_trosklar` | dict | ✅ | `{in, kvar, n, in_pct, kvar_pct}` — se nedan. |
| `analyses` | dict | ✅ | Teknisk/fundamental analys PER KONSENSUSAKTIE. Se **Analysis-entry**. |
| `claude` | dict | ✅ | Claudes text per konsensusaktie. Se **Claude-entry**. Kan vara `{}`. |
| `claude_datum` | str \| null | ✅ | Datum då Claude-texterna genererades, eller `null`. |
| `ranking` | list | ✅ | Rangordnade konsensusaktier, bästa köp först. Se **Ranking-entry**. Innehåller ALDRIG exit-aktier (se `exit_lista`). |
| `exit_lista` | list | ✅ | Konsensusaktier i EXIT (§B trendbrott), uteslutna ur `ranking`/Bästa köp. Kan vara `[]`. Se **Exit-entry**. |
| `regim` | dict | ✅ | Marknadsregim (§A). Se **Regim**. |
| `historik` | list | ✅ | Ändringslogg, nyaste först. Se **Historik-entry**. |
| `innehav` | dict | ✅ | Innehavstid/vinst per aktie (konsensus + nära + bubblare). Se **Innehav-entry**. |
| `divergens` | dict | ✅ | Divergens per KONSENSUSAKTIE. Se **Divergens-entry**. Kan vara `{}`. |
| `divergens_nara` | dict | ✅ | Divergens per BUBBLARNIVÅ-aktie (för bubblare). Samma entry-form. |
| `bakgrund_antal` | int | ✅ | Antal portföljer i bakgrundsgruppen (0 om cache saknas). |
| `bransch` | dict | ✅ | `{ticker: industryID}` för konsensus + nära + bubblare. Se **Bransch**. |

> **Täckningsskillnad (viktigt för UI):**
> `analyses`, `claude`, `divergens`, `ranking` = **endast konsensusaktier**.
> `innehav`, `bransch` = konsensus + nära konsensus + bubblarnivå.
> `divergens_nara` = bubblarnivån. Slå aldrig upp en bubblar-aktie i `analyses`.

### `konsensus_trosklar`

| Fält | Typ | Beskrivning |
|---|---|---|
| `in` | int | Antal ägare som krävs för att komma IN (ceil(0.60 × N)). |
| `kvar` | int | Antal för att LIGGA KVAR (ceil(0.50 × N)). |
| `n` | int | Gruppstorleken (= len(profiler)). |
| `in_pct` | int | 60 (procent). |
| `kvar_pct` | int | 50 (procent). |

### Konsensus-entry (`consensus`, `nara_konsensus`, `bubblar_niva` — värdena)

Nyckel = ticker (str). Värde:

| Fält | Typ | Alltid? | Beskrivning |
|---|---|---|---|
| `count` | int | ✅ | Antal signalprofiler som äger aktien. |
| `avg_weight` | float | ✅ | Snittvikt (%) över ägarna. Ej avrundad — runda i UI. |
| `total_weight` | float | ✅ | Summerad vikt (%), 2 dec. |
| `holders` | list[str] | ✅ | Ägarnas användarnamn, sorterade. |
| `viktad_konsensus` | float | ✅ | Σ färskhetsvikt (aktivt köp 1,5 · ≤6 mån 1,0 · äldre 0,5), 2 dec. |
| `senaste_köp_dagar` | int \| null | ✅* | Dagar sedan färskaste köpet bland ägarna. `null` om inget datum fanns. |
| `tröskel` | int | ✅ | Tillämpad tröskel för denna aktie (in- eller kvarnivå). |
| `hysteres` | bool | ✅ | `true` om aktien var konsensus förra körningen (då gällde kvarnivån). |

`* ` fältet finns alltid; värdet kan vara `null`. Vid `null` → visa "–".

### Analysis-entry (`analyses` — värdena, PER KONSENSUSAKTIE)

Nyckel = ticker. Värdet har **två möjliga former**:

**A. Felform** (prisdata kunde inte hämtas):
```json
{ "ticker": "XYZ", "error": "ingen prisdata (…)" }
```
→ Om `"error"` finns: visa aktien med "data saknas", hoppa över indikatorer.

**B. Full form** (alla fält nedan finns):

| Fält | Typ | Kan vara null? | Beskrivning |
|---|---|---|---|
| `ticker` | str | nej | |
| `datakälla` | str | nej | `"Yahoo"`, `"Alpha Vantage"` eller `"cache"`. |
| `cache_datum` | str | *bara vid cache* | Sätts endast när `datakälla == "cache"` — tidpunkt datan är från. |
| `valuta` | str \| null | ja | Handelsvaluta, t.ex. `"USD"`. `null` = okänd. |
| `ohlc` | list | nej (kan vara `[]`) | Candlestick-serie, ~90 dagar. Se **OHLC-punkt**. |
| `pris` | float | nej | Senaste pris (2 dec). |
| `MA50` | float | nej | |
| `MA200` | float \| null | ja | `null` om < 200 dagars historik. |
| `över_MA200` | bool \| null | ja | |
| `MA200_stigande` | bool \| null | ja | |
| `stigande_trend` | bool \| null | ja | Priset över MA200 **och** MA200 stigande. UI:s hårda köpkriterium. |
| `golden_cross` | bool \| null | ja | |
| `RSI14` | float | nej | |
| `MACD` | float | nej | |
| `MACD_signal` | float | nej | |
| `MACD_över_signal` | bool | nej | |
| `bollinger_position_%` | float \| null | ja | 0 = nedre bandet, 100 = övre. |
| `52v_högsta` | float | nej | |
| `52v_lägsta` | float | nej | |
| `avstånd_52v_högsta_%` | float | nej | Negativt = under toppen. |
| `avkastning_1m_%` | float \| null | ja | |
| `avkastning_3m_%` | float \| null | ja | |
| `volymtrend_20d_vs_3m_%` | float \| null | ja | |
| `rekommendation` | str | nej | Analytikernas: `"strong_buy"`, `"buy"`, `"hold"`, `"sell"`, `"strong_sell"`, `"n/a"`. |
| `riktkurs` | float \| null | ja | Analytikernas snittriktkurs. |
| `uppsida_%` | float \| null | ja | Uppsida mot riktkurs. |
| `antal_analytiker` | int \| null | ja | |
| `eps_rev_90d_pct` | float \| null | ja | EPS-estimatrevidering 90 dgr (clampad ±50). |
| `sector` | str \| null | ja | yfinance-sektor (informativ). |
| `industry` | str \| null | ja | yfinance-industri. |
| `forward_pe` | float \| null | ja | Forward P/E (fallback trailing). |
| `peg_ratio` | float \| null | ja | |
| `riktkurs_hog` | float \| null | ja | Högsta analytikerriktkurs. |
| `riktkurs_lag` | float \| null | ja | Lägsta. |
| `riktkurs_spridningskvot` | float \| null | ja | (hög − låg)/mean. > 0,8 = hög osäkerhet. |
| `nasta_rapport` | str \| null | ja | ISO-datum för nästa bolagsrapport. |
| `volatilitet_arlig_%` | float \| null | ja | Årlig volatilitet. |
| `investerarnas_innehavstid_dagar_längst` | int | *bara om innehav finns* | Injiceras för Claude; kan saknas. |
| `investerarnas_innehavstid_dagar_snitt` | int | *bara om innehav finns* | |
| `investerarnas_upparbetade_vinst_pct_snitt` | float \| null | *bara om innehav finns* | |

> **Regel för UI:** för fält märkta "kan vara null" — visa "–" (eller motsvarande)
> vid `null`. Kolla ALLTID `"error" in analys` först.

#### OHLC-punkt (element i `analyses[tk].ohlc`)

| Fält | Typ | Beskrivning |
|---|---|---|
| `d` | str | Datum `"YYYY-MM-DD"`. |
| `o`,`h`,`l`,`c` | float \| null | Open/High/Low/Close. |
| `ma50` | float \| null | `null` tidigt i serien. |
| `ma200` | float \| null | `null` tidigt i serien. |

### Claude-entry (`claude` — värdena)

Nyckel = ticker (endast konsensusaktier, och bara de som analyserats).
`claude` kan vara `{}` (ingen nyckel, helg, eller Claude bortvald).

| Fält | Typ | Beskrivning |
|---|---|---|
| `rekommendation` | str | RÅ rekommendation: `"KÖP"`, `"AVVAKTA"`, `"SÄLJ"` eller `"?"`. Ändras ALDRIG av regimfiltret (mätserier/facit läser detta fältet). |
| `rekommendation_visning` | str | **Visa detta i UI**, inte `rekommendation`. Identisk med `rekommendation` UTOM i RÖD regim på en Bästa köp-aktie med `"KÖP"` → blir `"KÖP (vänta på marknaden)"`. |
| `analys` | str | Fri text (markdown-vänlig). |
| `genererad` | str | ISO-datum då texten skapades. |

→ Saknas en konsensusaktie i `claude`: visa "ingen Claude-analys".

### Ranking-entry (element i `ranking`)

Lista, redan sorterad (bästa köp först; aktier utan stigande trend sist).

| Fält | Typ | Kan vara null? | Beskrivning |
|---|---|---|---|
| `ticker` | str | nej | |
| `poäng` | float | nej | **Primär** poäng 0–100 (modell v2). |
| `poäng_v1` | float | nej | Gamla modellen, för jämförelse. |
| `trend_ok` | bool | nej | = `stigande_trend`. Styr sorteringen. |
| `delpoäng` | dict | nej | v2-komponenter: `{Trend, Momentum, Analytiker, Konsensus, Värdering}` (alla float/int). |
| `delpoäng_v1` | dict | nej | v1-komponenter: `{Trend, Momentum, Analytiker, Konsensus}` (utan Värdering). |
| `kluster` | dict \| null | ja | `{kluster_id:int, klusterstorlek:int, klusterfaktor:float}`. `null` om ej beräknat. |
| `nettoflode_30d_pe` | float \| null | ja | Signalgruppens nettoviktändring 30 dgr. `null` om historik < 7 dgr. |
| `relativ_styrka` | dict \| null | ja | `{rs_pe:float\|null, etf:str, bonus:int}`. |
| `foreslagen_vikt_%` | float \| null | ja | Volatilitetsjusterad sizing (0,5–3 %). |

### Exit-entry (element i `exit_lista`)

Konsensusaktier i §B:s dödskors (pris<MA200 och MA50<MA200) — uteslutna ur
`ranking`/Bästa köp, men KVAR i `consensus` (konsensuslistan påverkas inte).
Samma fält som **Ranking-entry** ovan, plus:

| Fält | Typ | Beskrivning |
|---|---|---|
| `exit_datum` | str | ISO-datum då aktien FÖRST flaggades EXIT (bevaras oförändrat medan villkoret består). |
| `exit_villkor` | str | Klartext, t.ex. `"Dödskors: pris < MA200 och MA50 < MA200"`. |

### Regim (`regim`)

Marknadsregim beräknad från SPY vs dess MA200 (§A), oberoende av eToro-data.

| Fält | Typ | Kan vara null? | Beskrivning |
|---|---|---|---|
| `regim` | str | nej | `"GRÖN"` (över MA200 + stigande), `"RÖD"` (under + fallande), `"GUL"` (blandat, bara varning) eller `"OKÄND"` (SPY-data saknas — behandlas som GRÖN överallt). |
| `spy_pris` | float \| null | ja | `null` vid `OKÄND`. |
| `spy_ma200` | float \| null | ja | `null` vid `OKÄND`. |
| `notis` | str \| null | ja | Förklaring vid `OKÄND` (t.ex. "SPY-hämtning misslyckades"). |
| `datum` | str | nej | ISO-datum för beräkningen. |

> Endast `"RÖD"` har effekt (Claude-textnedgradering, inga nya pappersköp).
> `"GUL"` och `"OKÄND"` är rent informativa — hellre falskt grönt än att
> blockera på datafel.

### Historik-entry (element i `historik`)

Lista, **nyaste först** (ackumuleras över alla körningar).

| Fält | Typ | Beskrivning |
|---|---|---|
| `datum` | str | ISO-datum `"YYYY-MM-DD"`. |
| `typ` | str | Se **Historik-typer** nedan. |
| `profil` | str | Användarnamn, eller `""` för listhändelser (in/ut konsensus). |
| `ticker` | str | Aktien, eller `""` för `NY PROFIL`. |
| `detalj` | str | Klartext, t.ex. `"9.2 % → 4.2 %"` eller `"under 50 %-kvarnivån (3 av 6 portföljer)"`. |

**Historik-typer** (`typ`):
`NY PROFIL`, `NYTT INNEHAV`, `SÅLT INNEHAV`, `VIKTÄNDRING`,
`IN I KONSENSUS`, `UT UR KONSENSUS`, `IN I NÄRA KONSENSUS`, `UT UR NÄRA KONSENSUS`,
`EXIT (TRENDBROTT)`, `ÅTER FRÅN EXIT`.

### Innehav-entry (`innehav` — värdena)

Nyckel = ticker (konsensus + nära + bubblare). Finns bara för aktier där
minst en ägare har öppningsdatum (annars ingen nyckel).

| Fält | Typ | Kan vara null? | Beskrivning |
|---|---|---|---|
| `längst_dagar` | int | nej | Äldsta öppna positionens ålder (dagar). |
| `längst_profil` | str | nej | Vem som ägt längst. |
| `snitt_dagar` | int | nej | Snittålder över ägarna. |
| `snitt_vinst_pct` | float \| null | ja | Investeringsviktad snittvinst (%). |
| `per_profil` | dict | nej | `{användarnamn: {dagar:int, vinst_pct:float\|null}}`. |

### Divergens-entry (`divergens`, `divergens_nara` — värdena)

Nyckel = ticker. `{}` om bakgrundsgrupp saknas.

| Fält | Typ | Beskrivning |
|---|---|---|
| `signal_antal` | int | Antal signalprofiler som äger aktien. |
| `signal_andel_pct` | int | Andel av signalgruppen (%). |
| `bakgrund_antal` | int | Antal bakgrundsprofiler som äger aktien. |
| `bakgrund_andel_pct` | float | Andel av bakgrundsgruppen (%). |
| `bakgrund_snittvikt` | float | Bakgrundsägarnas snittvikt (%). |
| `divergens_pp` | float | signal_andel − bakgrund_andel (procentenheter). **Huvudmåttet.** |

### Bransch (`bransch`)

`{ticker: industryID}` där industryID är eToros `stocksIndustryID` (int) eller
`null`. Mappning (för ikon/etikett i UI):
`1` Basic Materials · `2` Conglomerates · `3` Consumer Goods · `4` Financial ·
`5` Healthcare · `6` Industrial Goods · `7` Services · `8` Technology ·
`9` Utilities. (UI:t har egen halvledar-override baserat på ticker.)

---

## `portfolj_historik.json`

Läses av backend read-only; UI:t behöver normalt **inte** öppna den (loggen
finns i `senaste_analys.json.historik`). Struktur för fullständighet:

```json
{
  "senaste": {
    "datum": "YYYY-MM-DD",
    "portfolios": { "användarnamn": { "ticker": vikt_pct } },
    "consensus": ["AMZN", …],          // sorterad lista
    "near_consensus": ["ASML", …],
    "regel": "andel_hysteres_v1",      // regelversion (KONSENSUS_REGEL)
    "exit": { "TICKER": "YYYY-MM-DD" } // §B: exit_datum per aktie i EXIT just nu
  },
  "logg": [ { …Historik-entry… } ]     // nyaste först
}
```

`logg`-elementen har exakt samma form som **Historik-entry** ovan.

---

## `screener_facit.json`

Skrivs av `logga_facit()` vid varje körning; läses bara av `--utvardera`.
Lista, en rad per (datum, konsensusaktie).

| Fält | Typ | Beskrivning |
|---|---|---|
| `datum` | str | ISO-datum. |
| `ticker` | str | |
| `poäng` | float | Primär poäng (v2) vid det datumet. |
| `komponenter` | dict | v2-delpoäng (samma keys som `ranking[].delpoäng`). |
| `pris` | float \| null | Pris vid inträdet. |
| `viktad_konsensus` | float \| null | |
| `divergens_pp` | float \| null | |
| `claude_rek` | str \| null | Claudes rek vid inträdet (`KÖP`/`AVVAKTA`/`SÄLJ`). `null` på rader loggade före 2026-07-14. |

Idempotent: samma dag skrivs över (nycklad på `datum`).

---

## `pappersportfolj.json`

Skrivs av `logga_pappersportfolj()` vid varje analyskörning; läses bara av
`--utvardera` (§3b Del B). Lista, en post per ombalanseringsdatum, sorterad
stigande på datum. Idempotent (nycklad på `datum`). UI:t läser den **inte**
direkt — pappersportföljernas utfall visas via `utvardering.xlsx`.

```json
[
  {
    "datum": "YYYY-MM-DD",
    "portfoljer": {
      "likaviktad":  { "TICKER": andel, … },   // P1: 1/N över Bästa köp
      "poangviktad": { "TICKER": andel, … },   // P2: ∝ max(poäng−50,0), normaliserat
      "claude":      { "TICKER": andel, … }     // P4: P2 × Claude-faktor, fritt→kassa
    },
    "nya_i_kassa": ["TICKER", …]   // valfri — bara i RÖD regim med nya kandidater
  }
]
```

Vikterna är andelar (summa ≤ 1; resten = 0 %-avkastande kassa). `poangviktad`
och `claude` skiljer sig ENDAST för AVVAKTA-aktier (×0,5) och SÄLJ (×0).
P3 (SPY buy-and-hold) har inga vikter — beräknas direkt i utvärderingen.
`nya_i_kassa` (§A regimfilter): i RÖD regim utesluts nya Bästa köp-kandidater
(fanns inte i föregående ombalansering) helt ur alla tre portföljerna —
nyckeln listar dem, annars saknas den (ingen tom lista skrivs).

---

## Kontraktsregler (sammanfattning för frontend)

1. Läs bara `senaste_analys.json`. Alla toppnycklar finns alltid; tomt = `{}`/`[]`/`0`.
2. `analyses`/`claude`/`divergens`/`ranking` täcker **bara konsensusaktier**.
   `innehav`/`bransch` täcker även nära + bubblare. `divergens_nara` = bubblarnivån.
3. Kolla alltid `"error" in analyses[tk]` innan du läser indikatorfält.
4. Fält märkta "kan vara null" → visa "–" vid `null`. Anta aldrig att ett
   nullbart fält har värde.
5. `ranking` är redan sorterad — rendera i ordning.
6. `historik` är nyaste först.
7. Nya fält läggs till bakåtkompatibelt (befintliga fält byter aldrig typ utan
   changelog-rad). Om ett fält du förväntar dig saknas: behandla som `null`.
