# UTBYGGNAD — Divergensgrind ersätter konsensusgrinden

Status: IMPLEMENTERAT i backend 2026-10-05 med tak 10 % (kvar 15 %, nästan
20 %). Avvikelser från specen: nycklarna `consensus`/`nara_konsensus` behölls
med nytt innehåll i stället för en ny `kandidater`-nyckel (§6), så sajten inte
går sönder innan frontend bytt texter; historiktyperna behöll sina namn; §7
(skuggportfölj, uppdelad utvärdering) är INTE gjort — bara fältet `regel`
loggas. §8 (sjunde profil) väntar. Faktiskt kontrakt: SCHEMA.md 2026-10-05.

## 1. Problem

Bästa köp rankar bara aktier som klarar konsensusgrinden (in 4 av 6, kvar
3 av 6). Av signalgruppens 171 unika tickers ägs 143 av en profil, 22 av
två, 5 av tre och 1 av fyra. Grinden släpper därför bara igenom aktier som
nästan alla äger: AMZN, MU, NVDA, PYPL sedan juli, tre listbyten på hela
loggperioden. Poängmodellen får aldrig se de aktier som är svåra att hitta.

## 2. Ny grind

En aktie blir KANDIDAT (rankas på Bästa köp) när båda gäller:

- `signal_antal >= KANDIDAT_MIN_AGARE` (2)
- `bakgrund_andel_pct <= KANDIDAT_MAX_BAKGRUND_PCT` (10)

Bakgrundsandel i stället för divergens i procentenheter som tak: AMZN har
+26,7 pp i divergens (67 % mot 40 %) och skulle klara en pp-grind trots att
40 % av bakgrundsgruppen äger den. Taket på bakgrundsandelen är det som
faktiskt betyder "svår att hitta".

Utfall på datan från 2026-08-23:

| Tak | Kandidater |
|---|---|
| ≤ 10 % | 14: 1810.HK, ASML.NV, AVAV, D, LMT, NOC, NOVO-B.CO, NU, RHM.DE, RR.L, RRC, SMSN.L, VALE, VST |
| ≤ 20 % | 21: ovan + BABA, BRK.B, ETOR, GOOGL, JPM, PLTR, PYPL |

Hysteres som i dag, för att undvika flappande: IN vid ≤ 10 %, KVAR till
≤ 15 %. Ägarkravet har ingen hysteres (2 är redan golvet).

## 3. Poängmodellen

`compute_score_v2` behålls men Konsensus-komponenten (25 p) görs om, annars
straffas just de aktier grinden släpper in:

- i dag: antal ägare + viktad konsensus + nettoflöde, delat med klusterrot
- nytt: divergens (pp) + färskhetsvikt (senaste köp) + nettoflöde, samma
  klusterjustering

Trend, Momentum, Analytiker, Värdering, relativ styrka, exitregeln och
regimhanteringen är oförändrade.

## 4. Kostnad och drift

- yfinance: ~15–20 tickers per körning i stället för 4. Befintlig pool
  (max_workers=4 + stagger) behålls; fältvis fallback och cache-åldersvarning
  täcker blockering.
- Utländska tickers (1810.HK, RHM.DE, NOVO-B.CO, RR.L, SMSN.L): `yahoo_map`
  måste utökas och varje ny suffix verifieras mot Yahoo. Alpha Vantage-
  reserven gäller bara USA-tickers.
- Claude: bara de `CLAUDE_MAX_KANDIDATER` (6) högst rankade analyseras.
  Övriga får `claude[tk]` = saknas, som en ny aktie utan text i dag.
- Divergens räknas i dag bara för konsensus + bubblarnivå. Den måste räknas
  för alla aktier med ≥ 2 ägare (TSM/MSFT på nära-nivån saknar värde i dag).

## 5. Buggar som ska rättas i samma veva

- `Michalhla` ligger i bakgrundsgruppen (plats 40 i topp 50) trots att
  `michalhla` är en signalprofil. Filtret på rad 469 jämför skiftlägeskänsligt
  (`not in PROFILES`). Samma trader räknas alltså på båda sidor. Jämför
  gemener, och filtrera även vid inläsning av `bakgrund_topp50.json`.

## 6. Kontraktsändringar (SCHEMA.md, frontend måste följa)

- `consensus` byter innebörd till kandidatlistan, eller ersätts av ny
  toppnyckel `kandidater` (beslut i implementationen; ny nyckel är renare,
  `consensus` kan ligga kvar en övergångsperiod).
- `nara_konsensus`, `bubblar_niva`, `divergens_nara`: utgår eller slås ihop
  till en "nästan kandidat"-lista (klarar ägarkravet, bakgrund 10–20 %).
- `konsensus_trosklar`: ersätts av `kandidat_trosklar`.
- `ranking[].delpoäng`: nyckeln `Konsensus` byter namn/innehåll.
- Historiktyper: `IN I/UT UR KONSENSUS` → `NY KANDIDAT` / `UTGÅR SOM KANDIDAT`.
  `KONSENSUS_REGEL` höjs så övergången inte loggas som massutträde.
- UI-texter: "Konsensus"-fliken och "X av 6 äger" behöver nya ord.

## 7. Mätning

Facit och pappersportföljer börjar om från bytesdatumet (ny regelversion i
`screener_facit.json`/`pappersportfolj.json`), så gamla och nya grinden inte
blandas i `--utvardera`. Gamla grinden körs parallellt som skuggportfölj i
utvärderingen, så det går att se om bytet faktiskt slår konsensuslistan.

## 8. Sjunde profil (separat beslut)

Sex profiler ger 15 par som kan överlappa, sju ger 21. Det breddar
kandidatlistan men löser inte grundproblemet på egen hand. Välj inte efter
"vem lyfter flest aktier in på listan" (cirkulärt) och undvik mycket breda
portföljer: 96 innehav à 1 % är svag övertygelse. Om ägande ska räknas bara
över en minsta vikt (t.ex. 1,5 %) avgörs när en bred profil faktiskt läggs
till. En profil som flyttas från bakgrunds- till signalgruppen försvinner
ur bakgrunden (grupperna hålls åtskilda).

## 9. Ordning

1. §5-buggen + divergens för alla ≥ 2-ägare (ofarligt, ändrar inget i UI)
2. Grind + poängkomponent + Claude-tak bakom ny toppnyckel, gamla fält kvar
3. Frontend byter till nya nyckeln
4. Gamla fält tas bort, facit/pappersportfölj startar ny serie
