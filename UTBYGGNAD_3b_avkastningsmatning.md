# §3b — Avkastningsmätning: episoder + pappersportföljer

> STATUS 2026-07-14: IMPLEMENTERAD i etoro_analys.py under `--utvardera`.
> Del A (episoder) + Del B (fyra pappersportföljer) klara. Alla fem
> acceptanstesterna gröna: retroaktiv körning på 138 historikposter utan
> krasch (2 UT utan känt inträde räknas, exkluderas ej krasch); idempotens
> (ett datum per körning); P2/P4 skiljer sig endast för AVVAKTA/SÄLJ (MU
> AVVAKTA = halva P2-vikten, fritt→kassa); SPY-period matchar episoddatum;
> n-varningar i terminal + Excel. BASTA_KOP_MIN_POANG=0 (Bästa köp = alla
> konsensusaktier). pappersportfolj.json + facit.claude_rek dokumenterade
> i SCHEMA.md.
>
> Not: P4 lägger frigjord vikt i KASSA (redistribuerar inte) — det gör att
> P2 och P4 skiljer sig ENDAST för AVVAKTA/SÄLJ-aktier, vilket acceptanstest
> 3 kräver. "(omnormalisera)" i specen tolkades så för att uppfylla testet.

> Tillägg till UTBYGGNAD_screener_v2.md §3 (utvärderingsloopen).
> Implementeras i `etoro_analys.py`. Nya JSON-filer läggs i gist-synken
> (gist_pull/gist_push) — annars nollställs de på Render.
> Samma degraderingsprincip som v2: saknad data → neutral/exkluderad + notis,
> aldrig krasch.

## Syfte

Två kompletterande mätningar av om screenern faktiskt tillför värde:

- **Episodmätning:** hur gick aktierna UNDER tiden de låg på Bästa köp?
  (in-datum → ut-datum, mot benchmark)
- **Pappersportföljer:** fyra parallella simulerade portföljer som isolerar
  värdet av varje lager i systemet (urval / poängviktning / Claudes rek).

Båda körs under den befintliga flaggan `--utvardera` (utökning, ej ny flagga)
och kör INTE analysen.

---

## Del A: Episodmätning

### Datakälla
Rekonstruera episoder ur portfolj_historik.json:s ändringslogg retroaktivt:
- Episod = par av "IN på Bästa köp"-post och nästföljande "UT"-post för samma
  aktie. Saknas UT-post → öppen episod, mät till dagens datum.
- OBS: historiken loggar idag IN/UT UR KONSENSUS — verifiera att även Bästa
  köp-listans sammansättning kan härledas (poäng finns i screener_facit.json
  per datum). Om Bästa köp = alla konsensusaktier med poäng ≥ tröskel,
  dokumentera tröskeln som konstant (BASTA_KOP_MIN_POANG) så episoderna blir
  reproducerbara.

### Beräkning per episod
- Pris in/ut via yfinance med JUSTERADE priser (auto_adjust=True) så
  utdelningar/splittar räknas rätt. Närmaste handelsdag vid helgdatum.
- Episodavkastning = (pris_ut / pris_in) − 1
- Benchmark över EXAKT samma datumintervall: SPY (obligatorisk) +
  sektor-ETF enligt §10-mappningen (om tillgänglig).
- Överavkastning = episodavkastning − benchmarkavkastning. DETTA är måttet.

### Aggregering (rapport + ny Excel-flik "Episoder")
- Tabell per episod: Ticker | In-datum | Ut-datum (eller "öppen") | Dagar |
  Avkastning | SPY samma period | Överavkastning | Sektor-ETF-överavkastning |
  Poäng vid inträde | Claudes rek vid inträde
- Sammanfattning: snittöveravkastning, median, träffprocent (andel > 0
  överavkastning), uppdelat på:
  - STÄNGDA vs ÖPPNA episoder SEPARAT (öppna episoder har överlevnadsfel —
    kvarliggare är ofta vinnare; blanda ALDRIG ihop dem i ett snitt)
  - Claudes rek vid inträde (KÖP vs AVVAKTA) — testar om rek:en tillför info
- n skrivs alltid ut; vid n < 10 stängda episoder: varning "för tidigt för
  slutsatser (n=X)" (samma mönster som §3).

---

## Del B: Fyra pappersportföljer

### Gemensamma regler
- Universum: aktierna på Bästa köp vid varje körningstillfälle.
- Ombalansering: vid varje analyskörning (standard- eller --divergens-läge)
  appendas dagens målvikter till pappersportfolj.json med datum. Ingen
  handel simuleras mellan körningar — portföljen "håller" vikterna.
- Avkastning beräknas i --utvardera: kedja ihop perioderna mellan
  ombalanseringsdatum med justerade priser (yfinance batch).
- Inga transaktionskostnader i simuleringen, MEN logga omsättning per
  ombalansering (summa |ny vikt − gammal vikt| / 2) — hög omsättning =
  edgen äts upp i verkligheten. Rapportera snittomsättning per portfölj.
- Kassa: om portföljen har färre aktier än normalt (t.ex. allt utom en åker
  ut) hålls resten som 0%-avkastande kassa — ingen hävstång, inga negativa
  vikter.

### De fyra portföljerna
1. **LIKAVIKTAD** — alla Bästa köp-aktier får vikt 1/N.
   → Mäter: har URVALET värde?
2. **POÄNGVIKTAD** — vikt ∝ max(poäng − 50, 0), normaliserat till 100 %.
   Aktie under 50 poäng = vikt 0 (finns i universum men äger inget).
   → Mäter (vs portfölj 1): tillför POÄNGMODELLEN något utöver urvalet?
3. **BENCHMARK** — SPY buy-and-hold över samma totalperiod (ingen
   ombalansering). Redovisa även sektorjusterad variant om enkelt.
   → Referensen allt mäts mot.
4. **POÄNGVIKTAD + CLAUDE-FILTER** — som portfölj 2, men aktier med
   AVVAKTA-rek får halverad vikt och SÄLJ-rek vikt 0 (omnormalisera).
   Saknas Claude-rek (dagsspärr/helg) → använd senaste kända rek.
   → Mäter (vs portfölj 2): tillför CLAUDES bedömning något utöver de
   mekaniska indikatorerna?

### Rapport (terminal + Excel-flik "Pappersportföljer")
- Kumulativ avkastning per portfölj sedan start + per ombalanseringsperiod
- Nyckeltal: totalavkastning, snittomsättning, max drawdown (enkel:
  största fall från toppen i den kedjade serien)
- Parvisa differenser med tolkningsrad:
  - P1 − P3 = urvalets värde
  - P2 − P1 = poängmodellens värde
  - P4 − P2 = Claude-rekommendationens värde
- Samma n-varning: < 8 ombalanseringsperioder → "för tidigt (n=X)"
- Webbappen: nytt expanderbart kort "Utvärdering" på Bästa köp-fliken som
  visar de tre differenserna + n. Resten kan vänta.

---

## Acceptanstest

1. Retroaktiv körning på befintlig historik (138 poster) producerar
   episodtabellen utan krasch; episoder utan prisdata (avnoterat/fel ticker)
   exkluderas med notis, inte krasch.
2. Två körningar samma dag ger identiska pappersportfölj-vikter
   (idempotens — appenda inte dubbletter till pappersportfolj.json,
   nyckla på datum).
3. Portfölj 2 och 4 skiljer sig ENDAST för aktier med AVVAKTA/SÄLJ-rek
   (verifiera med MU som har AVVAKTA: vikt i P4 = halva P2-vikten,
   omnormaliserat).
4. SPY-perioden i episodtabellen matchar episodens datum exakt (stickprov).
5. Med n < gränsen skrivs varningen ut i både terminal och Excel.

## Uppdatera efteråt
- CLAUDE.md: --utvardera-beskrivningen utökas med Del A + B
- Gist-synk: pappersportfolj.json tillagd
- Historiken får INTE ändra format — Del A läser den read-only
