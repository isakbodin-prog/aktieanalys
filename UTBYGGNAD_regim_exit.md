# UTBYGGNAD — Regimfilter & Exitregel (liten spec)

> STATUS 2026-07-15: IMPLEMENTERAD i etoro_analys.py. §A (compute_market_regime)
> och §B (compute_exit_status) klara. Alla acceptanstester gröna: §A.1 dagens
> data → GRÖN (SPY 751 vs MA200 693); §A.2 simulerad RÖD → build_ranking tar
> inte emot regim alls (poängen kan strukturellt inte förorenas), Claude-texten
> degraderas via ett separat claude[tk].rekommendation_visning-fält (rått
> rekommendation-fält oförändrat), pappersportföljerna utesluter nya
> kandidater (verifierat med syntetisk föregående-ombalansering); §A.3
> SPY-miss → OKÄND, behandlas som GRÖN + notis. §B.1 verifierat mot
> senaste_analys.json (dödskors → EXIT); §B.2 ren rekyl (pris<MA200,
> MA50>MA200) hamnar inte i EXIT; §B.3 episod med ut_orsak "trendbrott" vs
> "konsensus tappad" verifierad; §B.4 idempotens verifierad (två körningar
> samma exitstatus → ingen dubbellogg). Sidoscreenern är MEDVETET UTELÄMNAD
> (se not nedan) — rör den inte.
>
> Tillägg till etoro_analys.py. Två defensiva regler lånade från
> trendföljning (Kavastu-stil). Ingen ny signalkälla, ingen ny datahämtning
> utöver 1–2 index-ETF:er via yfinance. Samma degraderingsprincip som v2:
> saknad data → neutral + notis, aldrig krasch.
>
> MEDVETET UTELÄMNAT: sidoscreenern (marknadsomfattande trendscreening).
> Byggs tidigast när --utvardera visar n >= 10 stängda episoder, så att
> beslutet fattas på data. Lägg INTE till den i denna omgång även om det
> vore enkelt.

---

## §A. Marknadsregimfilter

**Problem:** Pipelinen poängsätter aktier identiskt oavsett om marknaden
som helhet stiger eller befinner sig i fritt fall. Trendföljningens mest
robusta lärdom: inga nya köp i beartrend.

**Implementation:**
- Hämta SPY dagligt (yfinance, auto_adjust=True, 1 anrop, cachea i
  körningens minne — ingen ny fil).
- Regim = GRÖN om `SPY > MA200(SPY)` OCH `MA200 stigande (MA200 idag >
  MA200 för 20 handelsdagar sedan)`. Annars RÖD.
- Valfritt GUL mellanläge: pris > MA200 men MA200 fallande, eller tvärtom.
  GUL = varning utan rekommendationsändring.
- EFFEKT vid RÖD regim:
  - Claudes rekommendationer på Bästa köp nedgraderas: KÖP → "KÖP (vänta
    på marknaden)" — poängen beräknas och visas OFÖRÄNDRAD (mätserierna
    får inte förorenas av regimfiltret).
  - Pappersportföljerna (§3b): P1/P2/P4 gör INGA nya köp i RÖD regim —
    befintliga innehav behålls (exit sköts av §B), nya kandidater går till
    kassa. Detta loggas per ombalansering ("regim: RÖD, X kandidater
    hölls i kassa").
- Regimstatus skrivs till senaste_analys.json (fält: regim, regim_datum,
  spy_pris, spy_ma200) → SCHEMA.md uppdateras.

**Excel/app:** Regimbadge överst på Bästa köp-fliken och i Excel-headern
på Rangordning: "Marknadsregim: GRÖN/GUL/RÖD (SPY vs MA200)".

**Acceptans:**
1. Med dagens data: regimen beräknas och visas (förmodligen GRÖN).
2. Simulera RÖD (tvinga med testflagga eller mocka SPY-serien): inga nya
   köp i pappersportföljerna, rekommendationstexten ändras, poängen
   oförändrad mot GRÖN-körning på samma data.
3. yfinance-miss på SPY → regim "OKÄND", allt beter sig som GRÖN + notis
   i rapporten (hellre falskt grönt än att blockera på datafel).

## §B. Exitregel (trendbrott)

**Problem:** Aktier lämnar idag Bästa köp bara när konsensus faller.
Ingen mekanism fångar att trenden dött medan konsensus består —
pappersportföljer och episoder rider ner förlorare.

**Implementation:**
- Exitvillkor per aktie (data finns redan i TA-steget):
  `pris < MA200` OCH `MA50 < MA200` (båda krävs — pris under MA200 ensamt
  är en normal rekyl, dödskorset bekräftar).
- EFFEKT:
  - Aktien flyttas från Bästa köp till ny sektion "EXIT (trendbrott)" på
    Rangordning-fliken med datum och vilket villkor som föll.
  - Episodmätningen (§3b Del A): trendbrott räknas som UT-datum för
    episoden — lägg till ut-orsak i episodtabellen: "konsensus tappad"
    vs "trendbrott" (två olika exit-typer ska kunna jämföras i
    utvärderingen).
  - Pappersportföljerna säljer positionen vid nästa ombalansering
    (vikt 0, till kassa/omnormalisering).
  - Konsensuslistan påverkas INTE — aktien kan vara kvar i konsensus
    (traderna äger den ju) men flaggas. Divergens-fliken orörd.
- Återinträde: aktien kvalar in på Bästa köp igen först när exitvillkoret
  inte längre gäller OCH den fortfarande klarar konsensus/poängkraven.
  Ingen karenstid (hysteresen ligger redan i dödskors-kravet).

**Excel/app:** Ut-orsak-kolumn i Episoder-fliken; EXIT-sektion på
Rangordning; ⚠-badge i appen på aktier i EXIT.

**Acceptans:**
1. PYPL med nuvarande data (pris < MA200, MA50 < MA200) hamnar i EXIT —
   verifiera mot Teknisk analys-flikens värden.
2. Aktie med pris < MA200 men MA50 > MA200 (ren rekyl) hamnar INTE i EXIT.
3. Episod som avslutas av trendbrott får ut-orsak "trendbrott" i tabellen.
4. Två körningar i rad: EXIT-status idempotent (inga dubbelposter).

## Uppdatera efteråt
- CLAUDE.md: regim + exit under Pipeline-beskrivningen
- SCHEMA.md: nya fält (regim*, exit-lista) — frontend-sessionen behöver dem
- Historikloggen: nya posttyper "EXIT (trendbrott)" / "ÅTER FRÅN EXIT"
