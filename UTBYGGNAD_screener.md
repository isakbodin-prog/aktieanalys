# Utbyggnad: Trader-screener + tvånivåkonsensus

Tillägg till eToro-projektet. Läs tillsammans med CLAUDE.md.

## Idé i korthet

Två nivåer av portföljdata med olika roller:

1. **Signalgruppen (5–15 utvalda profiler)** — handplockade eller screenade
   traders med OLIKA strategier. Konsensus här är signalen.
2. **Bakgrundsgruppen (topp ~50 via screener)** — bred referens som visar
   vad "alla" äger. Används INTE som köpsignal utan som brusfilter.

Den intressanta frågan: **vad äger signalgruppen som bakgrundsgruppen
INTE äger (eller äger mycket mindre av)?** Det isolerar utvalda traders
genuina avvikelser från flockbeteendet.

## Steg 0: Screener (nytt)

Endpoint: `GET /user-info/people/search`

VIKTIGT: parametern `period` är OBLIGATORISK — det var därför tidigare
anrop gav 404. Prova värden som `OneYearAgo`, `TwoYearsAgo`, `CurrYear`
(exakta värden behöver verifieras mot docs/test).

Kända parametrar (från dokumentation):
- `period` (krävs), `page`, `pageSize`, `sort`
- `gainMin` / `gainMax` — avkastningsintervall
- `maxDailyRiskScoreMin/Max`, `maxMonthlyRiskScoreMin/Max`
- `weeksSinceRegistrationMin` — sålla bort nykomlingar
- `countryId`, `instrumentId`, `instrumentPctMin/Max`
- `popularInvestor` (bool), `isTestAccount` (sätt false)

Förslag på screeningkriterier för "bäst, inte populärast":
- period: 2 år, sort på gain (fallande) — MEN sortera inte på copiers
- maxMonthlyRiskScore <= 6 (sållar bort högriskchansare)
- weeksSinceRegistrationMin >= 104 (minst 2 år aktiv)
- isTestAccount = false

Output: lista med användarnamn + nyckeltal → topp 50 = bakgrundsgrupp.
Signalgruppen väljs manuellt (nuvarande 5) eller från screenern med
tillägg av strategisk spridning.

## Steg 1–2: Portföljhämtning + konsensus (finns, utöka)

- Hämta portföljer för BÅDA grupperna (batcha, respektera 429/Retry-After;
  50+ profiler = många anrop, lägg in paus och cachea till disk, t.ex.
  JSON-fil per användare med timestamp, återanvänd < 24h gamla)
- Konsensus signalgrupp: instrument i >= 3 av 5 (eller N/3 om gruppen växer)
- Bakgrundsvikt: för varje instrument, andel av bakgrundsgruppen som
  äger det + deras snittvikt

## Steg 2b: Divergensanalys (nytt, kärnan)

För varje konsensusaktie i signalgruppen, beräkna:

    divergens = andel_signalgrupp - andel_bakgrundsgrupp

- Hög konsensus + LÅG bakgrundsandel = unik övertygelse → mest intressant
- Hög konsensus + HÖG bakgrundsandel = flockbeteende/megacap → svag signal

Rapportera båda men ranka på divergens.

## Steg 3–4: TA + analytikerdata (finns)

Oförändrat: yfinance för RSI14, MA50/MA200, rekommendation, riktkurs.
Körs bara på signalgruppens konsensusaktier (inte alla 50 portföljer).

## Steg 5: Excel-rapport (utöka)

Ny flik "Divergens": Instrument | I signalgrupp (x/5) | I bakgrund (%) |
Divergens | Snittvikt signal | TA-sammanfattning | Analytiker | Uppsida %

## Öppna frågor att testa i Code-sessionen

1. Exakta giltiga värden för `period`-parametern (testa mot API:et)
2. Vilket fält i search-svaret som är användarnamn (username/UserName)
3. Rate limit-budget: 55 portföljer + instrumentuppslag — mät hur lång
   tid en full körning tar och om cache behövs redan från start
4. Ticker-uppslaget från CLAUDE.md måste lösas först (blockerar allt)

## Varningar

- Survivorship bias kvarstår även med screener (förlorare lämnar plattformen)
- Historisk gain förutsäger inte framtida avkastning
- Detta är beslutsunderlag, inte köprekommendationer
