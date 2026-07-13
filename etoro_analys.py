#!/usr/bin/env python3
"""
eToro portföljanalys — konsensus + teknisk analys + analytikerdata
==================================================================

KÖRNING (Terminal på Mac):
  1. Installera beroenden (en gång):
       pip3 install requests yfinance openpyxl pandas anthropic

  2. Lägg dina nycklar i .env-filen i samma mapp (klistra INTE in dem här):
       ETORO_API_KEY=din_offentliga_nyckel
       ETORO_USER_KEY=din_privata_nyckel
       ANTHROPIC_API_KEY=din_anthropic_nyckel   (för Claude-analysen, valfri)

  3. Kör:
       python3 etoro_analys.py

Resultat: portfolj_analys.xlsx i samma mapp (flikar: Konsensus & Analys,
Teknisk analys med Claudes bedömning, Historik med ändringslogg, en flik
per profil). Historiken sparas i portfolj_historik.json mellan körningar.
"""

import os
import sys
import uuid
import json
import requests

# ----------------------------------------------------------------------
# Konfiguration
# ----------------------------------------------------------------------
PROFILES = ["thomaspj", "michalhla", "JeppeKirkBonde", "triangulacapital", "Smudliczek", "ingruc"]
MIN_PORTFOLIOS = 3   # Aktien ska finnas i minst så här många portföljer
OUTPUT_FILE = "portfolj_analys.xlsx"

API_BASE = "https://public-api.etoro.com/api/v1"


def load_env_file():
    """Läs nycklar från .env i skriptets mapp om de inte redan finns i miljön."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_env_file()
API_KEY = os.environ.get("ETORO_API_KEY")
USER_KEY = os.environ.get("ETORO_USER_KEY")


def headers():
    return {
        "x-api-key": API_KEY,
        "x-user-key": USER_KEY,
        "x-request-id": str(uuid.uuid4()),
        "Accept": "application/json",
    }


def api_get(path, params=None, quiet=False, retries=3):
    """GET-anrop mot eToro:s publika API med felhantering och 429-respekt."""
    import time
    url = f"{API_BASE}{path}"
    for _ in range(retries):
        r = requests.get(url, headers=headers(), params=params, timeout=30)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 15))
            print(f"  Rate limit — väntar {wait}s...")
            time.sleep(wait)
            continue
        if not quiet:
            print(f"  GET {path} -> {r.status_code}")
        if r.status_code == 200:
            return r.json()
        print(f"    Svar ({path}): {r.text[:200]}")
        return None
    return None


# ----------------------------------------------------------------------
# Steg 1: Hämta portföljer
# ----------------------------------------------------------------------
_instrument_cache = {}
_industry_cache = {}   # ticker -> stocksIndustryID (1=Råvaror ... 9=Kraft, se app.py)

def resolve_instruments(instrument_ids):
    """Översätt instrument-ID:n till tickers.

    /market-data/instruments utan parametrar returnerar HELA instrumentlistan
    (~15 500 st) med symbolFull — kommaseparerade instrumentIds ger 500, så vi
    hämtar allt en gång och slår upp lokalt.
    """
    if not _instrument_cache:
        print("  Hämtar hela instrumentlistan (en gång)...")
        data = api_get("/market-data/instruments")
        for item in (data or {}).get("instrumentDisplayDatas", []):
            iid = item.get("instrumentID")
            ticker = item.get("symbolFull")
            if iid is not None and ticker:
                _instrument_cache[int(iid)] = str(ticker)
                if item.get("stocksIndustryID") is not None:
                    _industry_cache[str(ticker)] = item["stocksIndustryID"]
        print(f"  {len(_instrument_cache)} instrument i uppslagstabellen.")

    missing = [int(i) for i in instrument_ids if int(i) not in _instrument_cache]
    if missing:
        print(f"    OBS: {len(missing)} instrument kunde inte namnges, behåller ID:n: {missing[:10]}")

    return {int(i): _instrument_cache.get(int(i), str(i)) for i in instrument_ids}


def get_portfolio(username, quiet=False):
    """Hämta en användares live-portfölj.

    Returnerar (weights, meta) där weights = {ticker: vikt%} och
    meta = {ticker: {"öppnad": "ÅÅÅÅ-MM-DD", "vinst_pct": x}} — äldsta öppna
    positionens datum och investeringsviktad vinst. Eller (None, None).
    """
    if not quiet:
        print(f"\nHämtar portfölj för: {username}")
    data = api_get(f"/user-info/people/{username}/portfolio/live", quiet=quiet)
    if not data:
        print(f"  Kunde inte hämta portfölj för '{username}'.")
        return None, None

    # Aggregera per instrumentId (en användare kan ha flera positioner i samma instrument)
    weights = {}     # iid -> summerad investmentPct
    first_open = {}  # iid -> äldsta openTimestamp
    last_open = {}   # iid -> yngsta openTimestamp (senaste köpet)
    profit_acc = {}  # iid -> (summa pct*netProfit, summa pct)

    def add_position(p):
        iid = p.get("instrumentId")
        pct = float(p.get("investmentPct") or 0)
        if iid is None:
            return
        weights[iid] = weights.get(iid, 0) + pct
        ts = p.get("openTimestamp")
        if ts and (iid not in first_open or ts < first_open[iid]):
            first_open[iid] = ts
        if ts and (iid not in last_open or ts > last_open[iid]):
            last_open[iid] = ts
        profit = p.get("netProfit")
        if profit is not None and pct:
            s, w = profit_acc.get(iid, (0.0, 0.0))
            profit_acc[iid] = (s + pct * float(profit), w + pct)

    for p in data.get("positions") or []:
        add_position(p)
    # Positioner inuti social trades (kopierade portföljer) räknas också
    for st in data.get("socialTrades") or []:
        for p in st.get("positions") or []:
            add_position(p)

    if not weights:
        print(f"  Portföljen för '{username}' verkar vara tom eller dold.")
        return None, None

    id_to_ticker = resolve_instruments(list(weights.keys()))
    out = {id_to_ticker[iid]: round(pct, 2) for iid, pct in weights.items()}
    meta = {}
    for iid in weights:
        ticker = id_to_ticker[iid]
        m = {}
        if iid in first_open:
            m["öppnad"] = first_open[iid][:10]
        if iid in last_open:
            m["senaste_köp"] = last_open[iid][:10]
        if iid in profit_acc and profit_acc[iid][1]:
            m["vinst_pct"] = round(profit_acc[iid][0] / profit_acc[iid][1], 1)
        if m:
            meta[ticker] = m
    if not quiet:
        print(f"  {len(out)} innehav hämtade.")
    return out, meta


# ----------------------------------------------------------------------
# Delad konsensusberäkning (används av både signal- och ev. andra grupper)
# ----------------------------------------------------------------------
MIN_KONSENSUSVIKT = 3.0   # referensnivå för viktad konsensus (tre köp 30–180 dgr = 3.0)


def farskhetsvikt(dagar_sedan_senaste_kop):
    """Hur mycket ett innehav ska väga utifrån hur färskt senaste köpet är.

    Aktivt nyköp (≤30 dgr) väger mer än en gammal vinnare som ligger kvar.
    Saknas datum → neutral 1.0 (degraderar snyggt).

    Caveat: "senaste köp" approximeras med yngsta öppna positionens
    openTimestamp. Partiella stängningar lurar detta — stänger tradern sina
    äldsta lotter och behåller ett gammalt köp ser innehavet ändå ut som det
    yngsta kvarvarande, vilket kan visa högre färskhet än den verkliga
    övertygelsen motiverar.
    """
    if dagar_sedan_senaste_kop is None:
        return 1.0
    if dagar_sedan_senaste_kop <= 30:
        return 1.5   # aktivt köp
    if dagar_sedan_senaste_kop <= 180:
        return 1.0
    return 0.5       # passivt innehav


def compute_consensus(portfolios, port_meta=None, min_portfolios=None):
    """Beräkna konsensus och nära konsensus ur en uppsättning portföljer.

    Returnerar (consensus, near_consensus): {ticker: {count, avg_weight,
    total_weight, holders, viktad_konsensus, senaste_köp_dagar}}. Medlemskap
    avgörs av antal ägare (stabilt); viktad_konsensus (Σ farskhetsvikt) och
    senaste_köp_dagar (min över ägarna) beskriver hur färsk signalen är och
    väger in i poängen.
    """
    from datetime import date
    min_portfolios = min_portfolios or MIN_PORTFOLIOS
    port_meta = port_meta or {}
    today = date.today()
    consensus, near_consensus = {}, {}
    all_tickers = set()
    for positions in portfolios.values():
        all_tickers.update(positions.keys())
    for ticker in all_tickers:
        holders = {name: p[ticker] for name, p in portfolios.items() if ticker in p}
        vikter, dagar_lista = [], []
        for name in holders:
            sk = ((port_meta.get(name) or {}).get(ticker) or {}).get("senaste_köp")
            dagar = (today - date.fromisoformat(sk)).days if sk else None
            if dagar is not None:
                dagar_lista.append(dagar)
            vikter.append(farskhetsvikt(dagar))
        entry = {"count": len(holders),
                 "avg_weight": sum(holders.values()) / len(holders),
                 "total_weight": round(sum(holders.values()), 2),
                 "holders": sorted(holders),
                 "viktad_konsensus": round(sum(vikter), 2),
                 "senaste_köp_dagar": min(dagar_lista) if dagar_lista else None}
        if len(holders) >= min_portfolios:
            consensus[ticker] = entry
        elif len(holders) == min_portfolios - 1:
            near_consensus[ticker] = entry
    return consensus, near_consensus


# ----------------------------------------------------------------------
# Steg 0: Screener — bakgrundsgrupp (topp ~50 traders som referens/brusfilter)
#
# Tre separata artefakter:
#   bakgrund_topp50.json — medlemslistan från screenern (--screener).
#     Stabil mellan körningar, kan inspekteras och handjusteras.
#   bakgrund_cache.json  — medlemmarnas portföljer (--divergens hämtar om).
#   Divergensen i default-läget räknas från cachen utan några extra anrop.
# ----------------------------------------------------------------------
BG_MEMBERS_FILE = "bakgrund_topp50.json"
BG_CACHE_FILE = "bakgrund_cache.json"
BG_SIZE = 50
SCREENER_FILTER = {
    "sort": "-gain",                  # minusprefix = fallande
    "pageSize": 100,                  # större pool per period för snittningen
    "gainMin": 15,                    # sållar bort förlorare och nollkonton
    "maxMonthlyRiskScoreMax": 6,      # inga högriskchansare
    "weeksSinceRegistrationMin": 104, # minst 2 år på plattformen
    "copiersMin": 50,                 # sållar BARA bort test-/spökkonton — rankas ej på
    # OBS: isTestAccount och popularInvestor ger 404 — finns ej i denna API-version
}
# API:et saknar TwoYearsAgo (404). "~2 år" approximeras med snittet av två
# perioder: rullande 12 månader + förra kalenderåret — båda måste vara bra.
SCREENER_PERIODS = ("OneYearAgo", "LastYear")


def run_screener():
    """Screena fram bakgrundsgruppen och spara topp 50 till BG_MEMBERS_FILE.

    Rankar på snittgain över SCREENER_PERIODS + låg riskpoäng — INTE på
    antal kopierare. Returnerar listan (eller None vid fel).
    """
    from datetime import date

    pools = {}
    for period in SCREENER_PERIODS:
        print(f"Screenar period {period}...")
        data = api_get("/user-info/people/search", {"period": period, **SCREENER_FILTER})
        if not data or not data.get("items"):
            print(f"  OBS: inga träffar för {period} — avbryter.")
            return None
        pools[period] = {i["userName"]: i for i in data["items"]
                         if i["userName"] not in PROFILES}   # grupperna hålls åtskilda

    # Kräv närvaro i båda perioderna (uthållighet, inte one-hit-wonders)
    gemensamma = set.intersection(*(set(p) for p in pools.values()))
    print(f"  {sum(len(p) for p in pools.values())} kandidater, "
          f"{len(gemensamma)} klarar kraven i båda perioderna.")

    def rank_score(username):
        gains = [pools[p][username]["gain"] for p in SCREENER_PERIODS]
        snitt_gain = sum(gains) / len(gains)
        risk = pools[SCREENER_PERIODS[0]][username]["maxMonthlyRiskScore"]
        return snitt_gain - risk * 5   # riskstraff: en riskpoäng kostar 5 gain-enheter

    rankade = sorted(gemensamma, key=rank_score, reverse=True)[:BG_SIZE]
    medlemmar = []
    for username in rankade:
        i1 = pools[SCREENER_PERIODS[0]][username]
        medlemmar.append({
            "userName": username,
            "gain_1ar": round(i1["gain"], 1),
            "gain_forra_aret": round(pools[SCREENER_PERIODS[1]][username]["gain"], 1),
            "riskpoang": i1["maxMonthlyRiskScore"],
            "veckor_registrerad": i1["weeksSinceRegistration"],
            "copiers": i1["copiers"],
        })

    with open(BG_MEMBERS_FILE, "w") as f:
        json.dump({"datum": date.today().isoformat(),
                   "kriterier": {"perioder": list(SCREENER_PERIODS), **SCREENER_FILTER},
                   "profiler": medlemmar}, f, ensure_ascii=False, indent=2)

    print(f"\nTopp {len(medlemmar)} sparad till {BG_MEMBERS_FILE}:")
    for i, m in enumerate(medlemmar[:10], 1):
        print(f"  {i:>2}. {m['userName']:<22} 1 år {m['gain_1ar']:>6.1f} % | "
              f"förra året {m['gain_forra_aret']:>6.1f} % | risk {m['riskpoang']}")
    if len(medlemmar) > 10:
        print(f"  ... och {len(medlemmar) - 10} till.")
    return medlemmar


def load_background_portfolios(refresh=False):
    """Bakgrundsgruppens portföljer.

    refresh=False (default-läget): läs bara befintlig cache — inga API-anrop.
    refresh=True (--divergens): hämta om portföljerna för medlemmarna i
    BG_MEMBERS_FILE och skriv ny cache.
    """
    import time
    from datetime import date

    cache = {}
    if os.path.exists(BG_CACHE_FILE):
        try:
            with open(BG_CACHE_FILE) as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache = {}

    if not refresh:
        ports = cache.get("portfolios")
        if ports:
            print(f"\nBakgrundsgrupp: {len(ports)} portföljer från cache ({cache.get('datum', '?')}).")
        return ports

    if not os.path.exists(BG_MEMBERS_FILE):
        raise RuntimeError(f"{BG_MEMBERS_FILE} saknas — kör 'python3 etoro_analys.py --screener' först.")
    with open(BG_MEMBERS_FILE) as f:
        members = json.load(f)
    usernames = [m["userName"] for m in members.get("profiler", [])]
    if not usernames:
        raise RuntimeError(f"{BG_MEMBERS_FILE} innehåller inga profiler.")

    print(f"\nHämtar {len(usernames)} bakgrundsportföljer (screenade {members.get('datum', '?')}, "
          "tar ~1–2 min)...")
    ports = {}
    for username in usernames:
        weights, _ = get_portfolio(username, quiet=True)
        if weights:
            ports[username] = weights
        time.sleep(0.5)   # snäll takt — många anrop i följd

    if not ports:
        print("  OBS: inga portföljer kunde hämtas — behåller gamla cachen.")
        return cache.get("portfolios")

    print(f"  {len(ports)} bakgrundsportföljer hämtade.")
    with open(BG_CACHE_FILE, "w") as f:
        json.dump({"datum": date.today().isoformat(), "medlemslista_datum": members.get("datum"),
                   "portfolios": ports}, f, ensure_ascii=False)
    return ports


def compute_divergence(consensus, portfolios, background):
    """Divergens = andel av signalgruppen som äger aktien − andel av bakgrunden.

    Hög divergens = signalgruppens unika övertygelse (mest intressant).
    Låg/negativ = flockbeteende — 'alla' äger den redan.
    """
    if not background:
        return {}
    bg_n = len(background)
    bg_owners, bg_weightsum = {}, {}
    for weights in background.values():
        for tk, w in weights.items():
            bg_owners[tk] = bg_owners.get(tk, 0) + 1
            bg_weightsum[tk] = bg_weightsum.get(tk, 0) + w

    out = {}
    for tk, info in consensus.items():
        sig = info["count"] / len(portfolios)
        bg = bg_owners.get(tk, 0) / bg_n
        out[tk] = {
            "signal_antal": info["count"],
            "signal_andel_pct": round(sig * 100),
            "bakgrund_antal": bg_owners.get(tk, 0),
            "bakgrund_andel_pct": round(bg * 100, 1),
            "bakgrund_snittvikt": (round(bg_weightsum[tk] / bg_owners[tk], 2)
                                   if bg_owners.get(tk) else 0.0),
            "divergens_pp": round((sig - bg) * 100, 1),
        }
    return out


# ----------------------------------------------------------------------
# Steg 2 & 3: Teknisk analys + analytikerdata (yfinance)
# ----------------------------------------------------------------------
ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")
_AV_URL = "https://www.alphavantage.co/query"


def fetch_history_alphavantage(yticker):
    """Reservkälla för dagskurser: Alpha Vantage (Yahoo blockerar ofta molnservrar).

    Returnerar en DataFrame med Open/High/Low/Close/Volume (senaste året) eller None.
    Gratisnyckel: https://www.alphavantage.co/support/#api-key (max 5 anrop/min, 25/dag).
    """
    import time
    import pandas as pd

    if not ALPHAVANTAGE_KEY or "." in yticker:   # bara USA-tickers utan suffix
        return None
    try:
        time.sleep(13)   # gratisnivån tillåter max 5 anrop/minut
        r = requests.get(_AV_URL, timeout=60, params={
            "function": "TIME_SERIES_DAILY", "symbol": yticker,
            "outputsize": "full", "apikey": ALPHAVANTAGE_KEY,
        })
        series = (r.json() or {}).get("Time Series (Daily)")
        if not series:
            return None
        df = pd.DataFrame.from_dict(series, orient="index").astype(float)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index().rename(columns={
            "1. open": "Open", "2. high": "High", "3. low": "Low",
            "4. close": "Close", "5. volume": "Volume"})
        return df[["Open", "High", "Low", "Close", "Volume"]].tail(252)   # ~1 handelsår
    except Exception:
        return None


def fetch_overview_alphavantage(yticker):
    """Analytikerdata från Alpha Vantage OVERVIEW, i samma format som Yahoos info-dict."""
    import time

    if not ALPHAVANTAGE_KEY or "." in yticker:
        return {}
    try:
        time.sleep(13)
        r = requests.get(_AV_URL, timeout=60, params={
            "function": "OVERVIEW", "symbol": yticker, "apikey": ALPHAVANTAGE_KEY,
        })
        d = r.json() or {}

        def num(key, cast=float):
            v = d.get(key)
            try:
                return cast(v)
            except (TypeError, ValueError):
                return None

        counts = {k: num(f"AnalystRating{k}", int) or 0
                  for k in ("StrongBuy", "Buy", "Hold", "Sell", "StrongSell")}
        n = sum(counts.values())
        rec = "n/a"
        if n:
            rec = max(counts, key=counts.get)
            rec = {"StrongBuy": "strong_buy", "Buy": "buy", "Hold": "hold",
                   "Sell": "sell", "StrongSell": "strong_sell"}[rec]
        return {
            "recommendationKey": rec,
            "targetMeanPrice": num("AnalystTargetPrice"),
            "numberOfAnalystOpinions": n or None,
            "sector": d.get("Sector") or None,
            "industry": d.get("Industry") or None,
            "forwardPE": num("ForwardPE"),
            "trailingPE": num("PERatio"),
            "pegRatio": num("PEGRatio"),
            # AV Overview saknar high/low riktkurs och nästa rapportdatum —
            # riktkurs_spridningskvot och nasta_rapport blir None (degraderar snyggt)
        }
    except Exception:
        return {}


def next_earnings_date(t):
    """Nästa kommande rapportdatum (ISO-datum) från yfinance .calendar. None vid miss.

    yfinance har bytt returformat mellan versioner (dict eller DataFrame) —
    hanteras defensivt. Endast Yahoo-källan har detta fält.
    """
    from datetime import date

    try:
        cal = t.calendar
        if cal is None:
            return None
        if isinstance(cal, dict):
            datum_lista = cal.get("Earnings Date")
        else:
            datum_lista = cal.loc["Earnings Date"].dropna().tolist()
        if not datum_lista:
            return None
        if not isinstance(datum_lista, (list, tuple)):
            datum_lista = [datum_lista]
        kandidater = []
        for d in datum_lista:
            try:
                kandidater.append(d if hasattr(d, "year") else date.fromisoformat(str(d)[:10]))
            except Exception:
                continue
        if not kandidater:
            return None
        kandidater.sort()
        idag = date.today()
        framtida = [d for d in kandidater if d >= idag]
        return (framtida[0] if framtida else kandidater[-1]).isoformat()
    except Exception:
        return None


def eps_revision_pct(t):
    """EPS-estimatrevidering för innevarande räkenskapsår över 90 dgr (%).

    Riktningen på analytikernas vinstestimat — stigande estimat stärker en
    köpsignal, fallande är en klassisk fälla trots hög uppsida. None vid miss.

    Robusthet (prioritetsordning, kvoten exploderar/missvisar annars):
    1. Teckenbyte negativt→positivt: +50 (garanterat över tröskeln, ingen kvot)
    2. Teckenbyte positivt→negativt: -50
    3. abs(90daysAgo) < 0.05: basen för liten för en meningsfull kvot → 0
    4. Annars: kvoten clampad till [-50, 50] innan poängsättning
    """
    try:
        et = t.eps_trend
        if et is None or et.empty or "0y" not in et.index:
            return None
        rad = et.loc["0y"]
        cur, old = float(rad["current"]), float(rad["90daysAgo"])
    except Exception:
        return None
    if old < 0 <= cur:
        return 50.0
    if old > 0 >= cur:
        return -50.0
    if abs(old) < 0.05:
        return 0.0
    pct = (cur - old) / abs(old) * 100
    return round(max(-50.0, min(50.0, pct)), 1)


def analyze_ticker(ticker):
    """Hämta teknisk data + analytikerdata. Yahoo Finance i första hand,
    Stooq som reserv för kursdata (Yahoo blockerar ofta molnservrars IP)."""
    import yfinance as yf
    import pandas as pd

    # eToro-tickers -> Yahoo-tickers (justera vid behov)
    yahoo_map = {"RR.L": "RR.L", "IAG.L": "IAG.L", "KBC.BR": "KBC.BR", "FUR.NV": "FUR.AS", "TI5A.NV": "TI5A.AS"}
    yticker = yahoo_map.get(ticker, ticker)

    hist, info, source = None, {}, "Yahoo"
    try:
        t = yf.Ticker(yticker)
        hist = t.history(period="1y")
        if hist.empty:
            hist = None
    except Exception:
        hist = None

    if hist is not None:
        try:
            info = t.info or {}
        except Exception:
            info = {}   # kursdata funkade men inte analytikerdatan — fylls från förra körningen
    else:
        hist = fetch_history_alphavantage(yticker)
        source = "Alpha Vantage"
        if hist is not None:
            info = fetch_overview_alphavantage(yticker)

    if hist is None:
        detail = ("varken Yahoo eller Alpha Vantage svarade" if ALPHAVANTAGE_KEY
                  else "Yahoo blockerade och ALPHAVANTAGE_API_KEY saknas")
        return {"ticker": ticker, "error": f"ingen prisdata ({detail})"}

    try:
        close = hist["Close"]
        volume = hist["Volume"]
        price = float(close.iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200_series = close.rolling(200).mean()
        ma200 = float(ma200_series.iloc[-1]) if len(close) >= 200 else None
        # Stiger MA200? Jämför med nivån för ca 1 månad (21 handelsdagar) sedan
        ma200_rising = (float(ma200_series.iloc[-1]) > float(ma200_series.iloc[-21])
                        if len(close) >= 221 else None)

        # RSI(14)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])

        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_val = float(macd_line.iloc[-1])
        macd_sig = float(macd_signal.iloc[-1])

        # Bollingerband (20, 2) — position i bandet: 0 % = nedre, 100 % = övre
        boll_mid = close.rolling(20).mean()
        boll_std = close.rolling(20).std()
        boll_upper = float((boll_mid + 2 * boll_std).iloc[-1])
        boll_lower = float((boll_mid - 2 * boll_std).iloc[-1])
        boll_pos = ((price - boll_lower) / (boll_upper - boll_lower) * 100
                    if boll_upper > boll_lower else None)

        # 52-veckorsnivåer och momentum
        high52 = float(close.max())
        low52 = float(close.min())
        ret_1m = (price / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else None
        ret_3m = (price / float(close.iloc[-63]) - 1) * 100 if len(close) >= 63 else None

        # Volymtrend: snitt senaste 20 dagar mot snitt senaste 3 mån
        vol_20 = float(volume.tail(20).mean())
        vol_90 = float(volume.tail(63).mean())
        vol_trend = (vol_20 / vol_90 - 1) * 100 if vol_90 else None

        rec = info.get("recommendationKey", "n/a")
        target = info.get("targetMeanPrice")
        n_analysts = info.get("numberOfAnalystOpinions")
        upside = round((target / price - 1) * 100, 1) if target else None
        eps_rev = eps_revision_pct(t) if source == "Yahoo" else None

        # §7 Värdering: forward P/E (fallback trailing), PEG — jämförs mot
        # sektormedian i ett efterföljande steg (build_ranking)
        forward_pe = info.get("forwardPE") or info.get("trailingPE")
        peg_ratio = info.get("pegRatio")

        # §8 Riktkursspridning — hög osäkerhet (>0.8) halverar uppsidepoängen
        target_high, target_low = info.get("targetHighPrice"), info.get("targetLowPrice")
        spridningskvot = None
        if target_high and target_low and target:
            spridningskvot = round((target_high - target_low) / target, 2)

        # §9 Nästa rapportdatum (endast Yahoo — ingen poängeffekt, bara varning)
        nasta_rapport = next_earnings_date(t) if source == "Yahoo" else None

        # §10 Industry (för sektor→ETF-mappning, halvledare→SOXX)
        industry = info.get("industry")

        # §11 Årlig volatilitet (dagsavkastning stddev × sqrt(252)) för
        # volatilitetsjusterad positionsstorlek — inget poängeffekt
        dagsavkastning = close.pct_change().dropna()
        volatilitet_arlig = (round(float(dagsavkastning.std()) * (252 ** 0.5) * 100, 1)
                             if len(dagsavkastning) >= 20 else None)

        # Kompakt prisserie för candlestick-grafen (senaste ~90 handelsdagarna,
        # med MA50/MA200 som överlägg). Kräver OHLC — finns hos både Yahoo och AV.
        ohlc = []
        if {"Open", "High", "Low"}.issubset(hist.columns):
            ma50_s = close.rolling(50).mean()
            ma200_s = close.rolling(200).mean()

            def _num(v):
                return None if pd.isna(v) else round(float(v), 2)

            tail = hist.tail(90)
            for ts, row in tail.iterrows():
                ohlc.append({
                    "d": ts.strftime("%Y-%m-%d"),
                    "o": _num(row["Open"]), "h": _num(row["High"]),
                    "l": _num(row["Low"]), "c": _num(row["Close"]),
                    "ma50": _num(ma50_s.get(ts)), "ma200": _num(ma200_s.get(ts)),
                })

        return {
            "ticker": ticker,
            "datakälla": source,
            "valuta": info.get("currency") or ("USD" if source == "Alpha Vantage" else None),
            "ohlc": ohlc,
            "pris": round(price, 2),
            "MA50": round(ma50, 2),
            "MA200": round(ma200, 2) if ma200 else None,
            "över_MA200": price > ma200 if ma200 else None,
            "MA200_stigande": ma200_rising,
            "stigande_trend": (price > ma200 and bool(ma200_rising)) if ma200 else None,
            "golden_cross": (ma50 > ma200) if ma200 else None,
            "RSI14": round(rsi, 1),
            "MACD": round(macd_val, 2),
            "MACD_signal": round(macd_sig, 2),
            "MACD_över_signal": macd_val > macd_sig,
            "bollinger_position_%": round(boll_pos, 1) if boll_pos is not None else None,
            "52v_högsta": round(high52, 2),
            "52v_lägsta": round(low52, 2),
            "avstånd_52v_högsta_%": round((price / high52 - 1) * 100, 1),
            "avkastning_1m_%": round(ret_1m, 1) if ret_1m is not None else None,
            "avkastning_3m_%": round(ret_3m, 1) if ret_3m is not None else None,
            "volymtrend_20d_vs_3m_%": round(vol_trend, 1) if vol_trend is not None else None,
            "rekommendation": rec,
            "riktkurs": target,
            "uppsida_%": upside,
            "antal_analytiker": n_analysts,
            "eps_rev_90d_pct": eps_rev,
            "sector": info.get("sector"),   # informativ kolumn — inte klustringsgrund (§4)
            "industry": industry,
            "forward_pe": round(forward_pe, 1) if forward_pe else None,
            "peg_ratio": round(peg_ratio, 2) if peg_ratio else None,
            "riktkurs_hog": target_high, "riktkurs_lag": target_low,
            "riktkurs_spridningskvot": spridningskvot,
            "nasta_rapport": nasta_rapport,
            "volatilitet_arlig_%": volatilitet_arlig,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


# ----------------------------------------------------------------------
# Steg 3b: Sammanvägd poäng och rangordning
# ----------------------------------------------------------------------
def compute_correlation_clusters(analyses, tickers, threshold=0.7, min_overlap=40):
    """Korrelationsbaserad klustring av konsensusaktierna (ersätter sektorbaserad).

    Sektoretiketter fångar inte samvariation mellan olika sektorer som ändå
    delar samma tes (t.ex. AMZN/GOOG hör till samma AI-tema som chipklustret,
    fast olika yfinance-sektor). I stället: parvis 63-dagars avkastnings-
    korrelation (priset finns redan i 'ohlc'), greedy single-linkage-kluster
    vid korrelation > threshold. Par med < min_overlap gemensamma dagar
    räknas inte (pandas min_periods → NaN → ingen sammanslagning).

    Returnerar {ticker: {"kluster_id": int, "klusterstorlek": int,
    "klusterfaktor": float}}. Aktier utan (tillräcklig) prisdata hamnar
    ensamma i sitt eget kluster (klusterfaktor 1.0 — neutral degradering).
    """
    import pandas as pd

    serier = {}
    for tk in tickers:
        ohlc = (analyses.get(tk) or {}).get("ohlc")
        if not ohlc:
            continue
        try:
            s = pd.Series([p["c"] for p in ohlc],
                         index=pd.to_datetime([p["d"] for p in ohlc]))
            serier[tk] = s.pct_change().dropna()
        except Exception:
            continue

    parent = {tk: tk for tk in tickers}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    if len(serier) >= 2:
        ret_df = pd.DataFrame(serier)
        corr = ret_df.corr(min_periods=min_overlap)
        cols = list(corr.columns)
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                val = corr.iloc[i, j]
                if pd.notna(val) and val > threshold:
                    union(cols[i], cols[j])

    grupper = {}
    for tk in tickers:
        grupper.setdefault(find(tk), []).append(tk)
    out = {}
    for idx, (_, medlemmar) in enumerate(sorted(grupper.items()), start=1):
        storlek = len(medlemmar)
        for tk in medlemmar:
            out[tk] = {"kluster_id": idx, "klusterstorlek": storlek,
                       "klusterfaktor": round(1 / (storlek ** 0.5), 3)}
    return out


def compute_netflow_30d(history_log, tickers, dagar=30):
    """Signalgruppens nettoviktändring per aktie senaste `dagar` dagarna (pe).

    Kräver att historiken spänner över >= 7 dagar (>= 2 körningar isär) för
    att vara meningsfull — annars {} (neutral poäng överallt).
    """
    import re
    from datetime import date, timedelta

    if not history_log:
        return {}
    datum = sorted({e["datum"] for e in history_log})
    if len(datum) < 2:
        return {}
    span = (date.fromisoformat(datum[-1]) - date.fromisoformat(datum[0])).days
    if span < 7:
        return {}

    cutoff = (date.today() - timedelta(days=dagar)).isoformat()
    netto = {}
    for e in history_log:
        if e["datum"] < cutoff or e["typ"] not in ("VIKTÄNDRING", "NYTT INNEHAV", "SÅLT INNEHAV"):
            continue
        tal = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", e["detalj"].replace(",", "."))]
        d = None
        if e["typ"] == "VIKTÄNDRING" and len(tal) >= 2:
            d = tal[1] - tal[0]
        elif e["typ"] == "NYTT INNEHAV" and tal:
            d = tal[0]
        elif e["typ"] == "SÅLT INNEHAV" and tal:
            d = -tal[0]
        if d is not None and e["ticker"] in tickers:
            netto[e["ticker"]] = netto.get(e["ticker"], 0.0) + d
    return {tk: round(v, 2) for tk, v in netto.items()}


def compute_sector_pe_medians(analyses, tickers):
    """Grov forward P/E-median per sektor, beräknad över analyserade aktier
    i denna körning (konsensus). Litet urval — 'grov' är avsiktligt."""
    from statistics import median
    grupp = {}
    for tk in tickers:
        a = analyses.get(tk) or {}
        sektor, fpe = a.get("sector"), a.get("forward_pe")
        if sektor and fpe and fpe > 0:
            grupp.setdefault(sektor, []).append(fpe)
    return {sektor: median(vals) for sektor, vals in grupp.items()}


def compute_valuation_score(a, sector_medians):
    """§7 Värderingspoäng (0–10): forward P/E mot sektormedian + PEG-bonus."""
    varde = 0.0
    fpe, peg = a.get("forward_pe"), a.get("peg_ratio")
    median_val = sector_medians.get(a.get("sector"))
    if fpe and median_val:
        if fpe < 0.8 * median_val:
            varde += 10
        elif fpe > 1.5 * median_val:
            varde -= 10
    if peg is not None and 0 < peg < 1.5:
        varde += 5
    return round(max(0.0, min(10.0, varde)), 1)


# §10 Relativ styrka mot sektor — ETF-mappning (halvledare→SOXX oavsett sektor)
_SEKTOR_ETF = {
    "Technology": "XLK", "Consumer Cyclical": "XLY", "Communication Services": "XLC",
    "Financial Services": "XLF", "Financial": "XLF", "Healthcare": "XLV",
    "Industrials": "XLI", "Energy": "XLE",
}


def _etf_for(sector, industry):
    if industry and "Semiconductor" in industry:
        return "SOXX"
    return _SEKTOR_ETF.get(sector, "SPY")


def _fetch_etf_return_63d(cache, etf_ticker):
    """63-dagarsavkastning för ett index-ETF, cachead per körning (max ~9 ETF:er)."""
    if etf_ticker in cache:
        return cache[etf_ticker]
    try:
        import yfinance as yf
        h = yf.Ticker(etf_ticker).history(period="6mo")
        if h.empty or len(h) < 64:
            cache[etf_ticker] = None
        else:
            close = h["Close"]
            cache[etf_ticker] = round((float(close.iloc[-1]) / float(close.iloc[-63]) - 1) * 100, 1)
    except Exception:
        cache[etf_ticker] = None
    return cache[etf_ticker]


def compute_relative_strength(analyses, tickers):
    """§10: RS = aktiens 63d-avkastning − dess sektor-ETF:s 63d-avkastning.

    Returnerar {ticker: {"rs_pe": x, "etf": "XLK", "bonus": ±5}}. ETF-priser
    hämtas högst en gång per unikt index i hela körningen (yfinance, ingen
    AV-reserv här — degraderar till None om Yahoo blockerar).
    """
    cache = {}
    out = {}
    for tk in tickers:
        a = analyses.get(tk) or {}
        r3 = a.get("avkastning_3m_%")
        etf = _etf_for(a.get("sector"), a.get("industry"))
        etf_ret = _fetch_etf_return_63d(cache, etf)
        if r3 is None or etf_ret is None:
            out[tk] = {"rs_pe": None, "etf": etf, "bonus": 0}
            continue
        rs = round(r3 - etf_ret, 1)
        out[tk] = {"rs_pe": rs, "etf": etf,
                  "bonus": 5 if rs > 5 else (-5 if rs < -5 else 0)}
    return out


def compute_suggested_weights(analyses, tickers, malvikt=2.0, tak=3.0, golv=0.5):
    """§11: Volatilitetsjusterad föreslagen vikt (%) — sizing, ingen poängeffekt.

    raw = 1/volatilitet, normaliserad så snittförslaget blir `malvikt` %,
    därefter clampad till [golv, tak]. Ingen poängeffekt.
    """
    raw = {}
    for tk in tickers:
        v = (analyses.get(tk) or {}).get("volatilitet_arlig_%")
        if v and v > 0:
            raw[tk] = 100.0 / v
    if not raw:
        return {}
    medel = sum(raw.values()) / len(raw)
    if not medel:
        return {}
    skala = malvikt / medel
    return {tk: round(min(tak, max(golv, r * skala)), 2) for tk, r in raw.items()}


def compute_score(a, cons, cluster_factor=1.0, nettoflode_pe=None):
    """Sammanvägd poäng 0–100 för en aktie.

    Trend 30 p + Momentum 25 p + Analytiker 25 p + Konsensus 20 p (justerad
    för korrelationskluster §4 och nettoflöde §5). Returnerar (totalpoäng,
    delpoäng-dict).
    """
    delpoang = {}

    # Trend (max 30) — investerarens viktigaste kriterium
    trend = 0
    if a.get("över_MA200"):
        trend += 10
    if a.get("MA200_stigande"):
        trend += 10
    if a.get("golden_cross"):
        trend += 10
    delpoang["Trend"] = trend

    # Momentum (max 25)
    mom = 0.0
    rsi = a.get("RSI14")
    if rsi is not None:
        if 45 <= rsi <= 65:      # styrkezon utan överköp
            mom += 10
        elif 35 <= rsi < 45 or 65 < rsi <= 70:
            mom += 6
        elif 30 <= rsi < 35:
            mom += 3
    if a.get("MACD_över_signal"):
        mom += 7
    r3 = a.get("avkastning_3m_%")
    if r3 is not None:
        mom += max(0.0, min(8.0, r3 / 5))   # +40 % på 3 mån ger full poäng
    delpoang["Momentum"] = round(mom, 1)

    # Analytiker (max 25): uppsida + antal + köprek + estimatrevidering
    ana = 0.0
    uppsida = a.get("uppsida_%")
    if uppsida is not None:
        ana += max(0.0, min(15.0, uppsida / 2))   # 30 % uppsida ger full poäng
    ana += min(5.0, (a.get("antal_analytiker") or 0) / 8)   # 40 analytiker ger full poäng
    if a.get("rekommendation") in ("strong_buy", "buy"):
        ana += 5
    eps_rev = a.get("eps_rev_90d_pct")
    if eps_rev is not None:   # stigande estimat +, fallande − (fångar uppsidefällan)
        ana += 10 if eps_rev > 5 else (-10 if eps_rev < -5 else 0)
    delpoang["Analytiker"] = round(max(0.0, min(25.0, ana)), 1)

    # Konsensus (max 20, före klusterjustering) — eniga, övertygade OCH
    # färska investerare, plus flödesriktning; delat med sqrt(klusterstorlek)
    # om aktien samvarierar starkt med andra konsensusaktier (§4)
    kon = 0.0
    vk = cons.get("viktad_konsensus")
    if vk is None:
        vk = float(cons["count"])   # degradera snyggt om färskhetsdata saknas
    kon += min(12.0, vk * 3.0)      # vk=3 (tröskel) → 9; vk≥4 → 12; stale trio (1.5) → 4.5
    kon += min(8.0, cons["avg_weight"] * 1.6)   # ~5 % snittvikt ger full poäng
    if nettoflode_pe is not None:
        kon += 5 if nettoflode_pe > 1.0 else (-5 if nettoflode_pe < -1.0 else 0)
    kon *= cluster_factor   # ensam i sitt kluster → oförändrad (faktor 1.0)
    delpoang["Konsensus"] = round(max(0.0, kon), 1)

    total = round(sum(delpoang.values()), 1)
    return total, delpoang


def compute_score_v2(a, cons, cluster_factor=1.0, nettoflode_pe=None,
                     rs_bonus=0, sector_medians=None):
    """§12 Omviktad poängmodell: Trend 25 + Momentum 20 + Analytiker 20 +
    Konsensus 25 + Värdering 10 (vikterna är startvärden — --utvardera ska
    på sikt kalibrera dem). Återanvänder v1:s delformler och klipper varje
    komponent till sin nya takhöjd, plus: relativ styrka (§10) i Momentum,
    riktkursspridning (§8) halverar uppsidan i Analytiker, Värdering (§7)
    är helt ny. Returnerar (totalpoäng, delpoäng-dict).
    """
    sector_medians = sector_medians or {}
    delpoang = {}

    # Trend (tak 25, samma flaggor som v1 vars råsumma är 0..30)
    trend_raw = 0
    if a.get("över_MA200"):
        trend_raw += 10
    if a.get("MA200_stigande"):
        trend_raw += 10
    if a.get("golden_cross"):
        trend_raw += 10
    delpoang["Trend"] = min(25, trend_raw)

    # Momentum (tak 20): v1:s bas (0..25) + relativ styrka mot sektor-ETF (±5)
    mom = 0.0
    rsi = a.get("RSI14")
    if rsi is not None:
        if 45 <= rsi <= 65:
            mom += 10
        elif 35 <= rsi < 45 or 65 < rsi <= 70:
            mom += 6
        elif 30 <= rsi < 35:
            mom += 3
    if a.get("MACD_över_signal"):
        mom += 7
    r3 = a.get("avkastning_3m_%")
    if r3 is not None:
        mom += max(0.0, min(8.0, r3 / 5))
    mom += rs_bonus
    delpoang["Momentum"] = round(max(0.0, min(20.0, mom)), 1)

    # Analytiker (tak 20): uppsidan halveras vid hög riktkursspridning (§8)
    ana = 0.0
    uppsida = a.get("uppsida_%")
    if uppsida is not None:
        uppsida_poang = max(0.0, min(15.0, uppsida / 2))
        if (a.get("riktkurs_spridningskvot") or 0) > 0.8:
            uppsida_poang /= 2
        ana += uppsida_poang
    ana += min(5.0, (a.get("antal_analytiker") or 0) / 8)
    if a.get("rekommendation") in ("strong_buy", "buy"):
        ana += 5
    eps_rev = a.get("eps_rev_90d_pct")
    if eps_rev is not None:
        ana += 10 if eps_rev > 5 else (-10 if eps_rev < -5 else 0)
    delpoang["Analytiker"] = round(max(0.0, min(20.0, ana)), 1)

    # Konsensus (tak 25) — identisk innehåll som v1, nya taket råkar matcha
    # exakt (12+8+5=25) så ingen omskalning behövs
    kon = 0.0
    vk = cons.get("viktad_konsensus")
    if vk is None:
        vk = float(cons["count"])
    kon += min(12.0, vk * 3.0)
    kon += min(8.0, cons["avg_weight"] * 1.6)
    if nettoflode_pe is not None:
        kon += 5 if nettoflode_pe > 1.0 else (-5 if nettoflode_pe < -1.0 else 0)
    kon *= cluster_factor
    delpoang["Konsensus"] = round(max(0.0, min(25.0, kon)), 1)

    # Värdering (tak 10) — helt ny komponent (§7)
    delpoang["Värdering"] = compute_valuation_score(a, sector_medians)

    total = round(sum(delpoang.values()), 1)
    return total, delpoang


def build_ranking(analyses, consensus, history_log=None):
    """Rangordna konsensusaktierna. Aktier utan stigande trend sist, oavsett poäng.

    Primär poäng = §12:s omviktade modell (Trend25/Momentum20/Analytiker20/
    Konsensus25/Värdering10). Gamla v1-poängen (Trend30/Momentum25/
    Analytiker25/Konsensus20) sparas som poäng_v1/delpoäng_v1 för jämförelse
    under övergångsperioden, tills --utvardera hunnit kalibrera vikterna.
    """
    giltiga = [tk for tk in consensus if "error" not in analyses.get(tk, {})]
    kluster = compute_correlation_clusters(analyses, giltiga)
    netto = compute_netflow_30d(history_log or [], giltiga)
    sector_medians = compute_sector_pe_medians(analyses, giltiga)
    rs = compute_relative_strength(analyses, giltiga)
    forslagen_vikt = compute_suggested_weights(analyses, giltiga)

    ranking = []
    for ticker, cons in consensus.items():
        a = analyses.get(ticker, {})
        if "error" in a:
            continue
        kf = kluster.get(ticker, {}).get("klusterfaktor", 1.0)
        nf = netto.get(ticker)
        rs_bonus = rs.get(ticker, {}).get("bonus", 0)

        total, delpoang = compute_score_v2(a, cons, cluster_factor=kf, nettoflode_pe=nf,
                                           rs_bonus=rs_bonus, sector_medians=sector_medians)
        total_v1, delpoang_v1 = compute_score(a, cons, cluster_factor=kf, nettoflode_pe=nf)

        ranking.append({
            "ticker": ticker,
            "poäng": total,
            "poäng_v1": total_v1,
            "trend_ok": bool(a.get("stigande_trend")),
            "delpoäng": delpoang,
            "delpoäng_v1": delpoang_v1,
            "kluster": kluster.get(ticker),
            "nettoflode_30d_pe": nf,
            "relativ_styrka": rs.get(ticker),
            "foreslagen_vikt_%": forslagen_vikt.get(ticker),
        })
    ranking.sort(key=lambda r: (not r["trend_ok"], -r["poäng"]))
    return ranking


# ----------------------------------------------------------------------
# Steg 4: Claude gör en gedigen teknisk analys per konsensusaktie
# ----------------------------------------------------------------------
def claude_analysis(analyses):
    """Skicka indikatordata till Claude API och få en skriven analys per aktie.

    Returnerar {ticker: {"rekommendation": str, "analys": str}}.
    Hoppar över (med varning) om ANTHROPIC_API_KEY saknas.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nOBS: ANTHROPIC_API_KEY saknas i miljön/.env — hoppar över Claude-analysen.")
        return {}

    import anthropic
    client = anthropic.Anthropic()

    system = (
        "Du är en erfaren teknisk analytiker på en svensk bank. Du får tekniska "
        "indikatorer och analytikerdata för en aktie i JSON-format. Skriv en gedigen "
        "men koncis teknisk analys på svenska (150–250 ord) som väger samman trend "
        "(MA50/MA200, golden cross), momentum (RSI, MACD, 1m/3m-avkastning), "
        "volatilitet (Bollingerband, avstånd till 52-veckorsnivåer), volymtrend och "
        "analytikernas riktkurs. Var konkret: nämn nivåer och vad som skulle ändra bilden.\n\n"
        "VIKTIGASTE KRITERIET för investeraren är stigande trend: aktien ska handlas "
        "över MA200 och MA200 ska vara stigande (fälten över_MA200, MA200_stigande, "
        "stigande_trend). Är stigande_trend false får rekommendationen ALDRIG vara KÖP "
        "— högst AVVAKTA, och ange då tydligt vilken nivå som måste återtas för att "
        "trendkriteriet ska vara uppfyllt. Är trendkriteriet uppfyllt, bedöm övriga "
        "indikatorer som vanligt.\n\n"
        "VINSTHEMTAGNINGSRISK: fälten investerarnas_innehavstid_dagar_* och "
        "investerarnas_upparbetade_vinst_pct_snitt visar hur länge eToro-investerarna "
        "ägt aktien och deras upparbetade vinst. Lång innehavstid i kombination med "
        "hög upparbetad vinst ökar risken att de börjar sälja och ta hem vinsten — "
        "väg in det i bedömningen och kommentera det uttryckligen när risken är "
        "förhöjd.\n\n"
        "DIVERGENS: fältet ägs_av_pct_av_bakgrundsgruppen visar hur stor andel av en "
        "bred referensgrupp (topp ~50 screenade traders) som äger aktien, och "
        "divergens_mot_bakgrundsgruppen_pp är skillnaden mot signalgruppens andel. "
        "Hög divergens = signalgruppens unika övertygelse (starkare signal); låg eller "
        "negativ = flockbeteende där 'alla' redan äger aktien. Nämn det kort.\n\n"
        "VALUTA: alla priser och nivåer anges i aktiens handelsvaluta (fältet "
        "'valuta', t.ex. USD, EUR, SEK). Använd rätt valutabeteckning — skriv "
        "ALDRIG 'kr' på ett USD-pris. Är valutan USD, skriv priser som t.ex. "
        "'242 USD' eller '$242', aldrig kronor.\n\n"
        "Svara EXAKT i detta format:\n"
        "REKOMMENDATION: <KÖP | AVVAKTA | SÄLJ>\n"
        "<själva analysen>"
    )

    from datetime import date
    idag = date.today().isoformat()
    results = {}
    for ticker, data in analyses.items():
        if "error" in data:
            continue
        print(f"  Claude analyserar {ticker}...")
        try:
            resp = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=2000,
                thinking={"type": "adaptive"},
                system=system,
                messages=[{
                    "role": "user",
                    "content": f"Analysera {ticker}:\n{json.dumps(data, ensure_ascii=False, indent=2)}",
                }],
            )
            text = next((b.text for b in resp.content if b.type == "text"), "").strip()
            rating = "?"
            if text.upper().startswith("REKOMMENDATION:"):
                first, _, rest = text.partition("\n")
                rating = first.split(":", 1)[1].strip()
                text = rest.strip()
            results[ticker] = {"rekommendation": rating, "analys": text, "genererad": idag}
        except anthropic.APIStatusError as e:
            print(f"    Claude-fel för {ticker}: {e.status_code} {e.message}")
        except Exception as e:
            print(f"    Claude-fel för {ticker}: {e}")
    return results


# ----------------------------------------------------------------------
# Steg 5: Ändringshistorik mellan körningar
# ----------------------------------------------------------------------
HISTORY_FILE = "portfolj_historik.json"
WEIGHT_CHANGE_THRESHOLD = 1.0  # procentenheter — mindre viktändringar loggas inte

# ----------------------------------------------------------------------
# Beständig lagring i GitHub Gist (för Render, vars disk är tillfällig).
# Aktiveras när GIST_ID och GITHUB_TOKEN är satta — annars no-op och allt
# fungerar lokalt som vanligt.
# ----------------------------------------------------------------------
GIST_ID = os.environ.get("GIST_ID")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
FACIT_FILE = "screener_facit.json"
GIST_FILES = ("portfolj_historik.json", "senaste_analys.json",
              "bakgrund_topp50.json", "bakgrund_cache.json", FACIT_FILE)


def _gist_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def gist_pull():
    """Hämta historik + senaste analys från gisten till lokala filer."""
    if not (GIST_ID and GITHUB_TOKEN):
        return
    try:
        r = requests.get(f"https://api.github.com/gists/{GIST_ID}",
                         headers=_gist_headers(), timeout=30)
        if r.status_code != 200:
            print(f"  OBS: kunde inte läsa gisten ({r.status_code}) — kör vidare utan.")
            return
        for name, f in (r.json().get("files") or {}).items():
            if name not in GIST_FILES or not f:
                continue
            content = f.get("content", "")
            if f.get("truncated"):
                content = requests.get(f["raw_url"], timeout=30).text
            if content.strip():
                with open(name, "w") as fh:
                    fh.write(content)
        print("  Historik hämtad från GitHub Gist.")
    except requests.RequestException as e:
        print(f"  OBS: gist-hämtning misslyckades ({e}) — kör vidare utan.")


def gist_push():
    """Spara historik + senaste analys till gisten."""
    if not (GIST_ID and GITHUB_TOKEN):
        return
    payload = {"files": {}}
    for name in GIST_FILES:
        if os.path.exists(name):
            with open(name) as fh:
                payload["files"][name] = {"content": fh.read()}
    if not payload["files"]:
        return
    try:
        r = requests.patch(f"https://api.github.com/gists/{GIST_ID}",
                           headers=_gist_headers(), json=payload, timeout=30)
        if r.status_code == 200:
            print("  Historik sparad till GitHub Gist.")
        else:
            print(f"  OBS: kunde inte spara till gisten ({r.status_code}).")
    except requests.RequestException as e:
        print(f"  OBS: gist-sparning misslyckades ({e}).")


def update_history(portfolios, consensus_tickers, near_tickers=None):
    """Jämför med förra körningen, logga ändringar och spara ny ögonblicksbild.

    Returnerar hela ändringsloggen (nyaste först).
    """
    near_tickers = near_tickers or []
    from datetime import date
    today = date.today().isoformat()

    state = {"senaste": None, "logg": []}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  OBS: kunde inte läsa {HISTORY_FILE} ({e}) — börjar om historiken.")

    prev = state.get("senaste")
    entries = []

    def log(typ, profil, ticker, detalj):
        entries.append({"datum": today, "typ": typ, "profil": profil,
                        "ticker": ticker, "detalj": detalj})

    if prev:
        for profile, positions in portfolios.items():
            old = prev.get("portfolios", {}).get(profile)
            if old is None:
                log("NY PROFIL", profile, "", f"{len(positions)} innehav")
                continue
            for tk, w in positions.items():
                if tk not in old:
                    log("NYTT INNEHAV", profile, tk, f"vikt {w} %")
                elif abs(w - old[tk]) >= WEIGHT_CHANGE_THRESHOLD:
                    log("VIKTÄNDRING", profile, tk, f"{old[tk]} % → {w} %")
            for tk, w in old.items():
                if tk not in positions:
                    log("SÅLT INNEHAV", profile, tk, f"hade vikt {w} %")

        old_cons = set(prev.get("consensus", []))
        new_cons = set(consensus_tickers)
        old_near = set(prev.get("near_consensus") or [])
        new_near = set(near_tickers)

        for tk in sorted(new_cons - old_cons):
            detalj = ("upp från nära konsensus" if tk in old_near
                      else "finns nu i ≥3 portföljer")
            log("IN I KONSENSUS", "", tk, detalj)
        for tk in sorted(old_cons - new_cons):
            detalj = ("ner till nära konsensus (2 portföljer)" if tk in new_near
                      else "färre än 2 portföljer kvar")
            log("UT UR KONSENSUS", "", tk, detalj)

        # Nära konsensus-övergångar (bara om förra ögonblicksbilden har listan,
        # annars skulle första körningen efter uppgraderingen spamma loggen)
        if "near_consensus" in prev:
            for tk in sorted(new_near - old_near - old_cons):
                log("IN I NÄRA KONSENSUS", "", tk, "finns nu i 2 portföljer")
            for tk in sorted(old_near - new_near - new_cons):
                log("UT UR NÄRA KONSENSUS", "", tk, "färre än 2 portföljer kvar")

        if entries:
            print(f"  {len(entries)} ändringar sedan {prev.get('datum', 'förra körningen')}.")
        else:
            print(f"  Inga ändringar sedan {prev.get('datum', 'förra körningen')}.")
    else:
        print("  Första körningen — skapar utgångsläge för historiken.")

    state["senaste"] = {"datum": today, "portfolios": portfolios,
                        "consensus": sorted(consensus_tickers),
                        "near_consensus": sorted(near_tickers)}
    state["logg"] = entries + state.get("logg", [])
    with open(HISTORY_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    return state["logg"]


# ----------------------------------------------------------------------
# Steg 6: Excel-rapport
# ----------------------------------------------------------------------
def write_excel(portfolios, consensus, analyses, claude_texts, history_log,
                ranking=None, near_consensus=None, holding_info=None, divergence=None,
                divergence_near=None):
    from datetime import date, timedelta
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    holding_info = holding_info or {}
    nyhets_cutoff = (date.today() - timedelta(days=7)).isoformat()
    rank_by_ticker = {r["ticker"]: r for r in (ranking or [])}

    def is_new(ticker, typ):
        return any(e["ticker"] == ticker and e["typ"] == typ and e["datum"] >= nyhets_cutoff
                   for e in history_log or [])

    wb = Workbook()
    hfont = Font(bold=True, color="FFFFFF")
    hfill = PatternFill("solid", start_color="1F4E78")

    def style_header(ws):
        for c in ws[1]:
            c.font, c.fill = hfont, hfill

    # Rangordning — sammanvägd poäng, bästa köp först
    if ranking:
        green = PatternFill("solid", start_color="C6EFCE")
        red = PatternFill("solid", start_color="FFC7CE")
        ws = wb.create_sheet("Rangordning", 0)
        ws.append(["Rang", "Instrument", "Poäng (0–100)", "Poäng (v1)", "Stigande trend",
                   "Trend (25)", "Momentum (20)", "Analytiker (20)", "Konsensus (25)",
                   "Värdering (10)", "Relativ styrka (pe)", "Föreslagen vikt (%)",
                   "Claudes rekommendation"])
        style_header(ws)
        for i, r in enumerate(ranking, start=1):
            d = r["delpoäng"]
            rs = r.get("relativ_styrka") or {}
            ws.append([i, r["ticker"], r["poäng"], r.get("poäng_v1"),
                       "JA" if r["trend_ok"] else "NEJ",
                       d.get("Trend"), d.get("Momentum"), d.get("Analytiker"), d.get("Konsensus"),
                       d.get("Värdering"), rs.get("rs_pe"), r.get("foreslagen_vikt_%"),
                       claude_texts.get(r["ticker"], {}).get("rekommendation", "")])
            ws.cell(row=ws.max_row, column=5).fill = green if r["trend_ok"] else red

    # Flik per profil
    for name, positions in portfolios.items():
        ws = wb.create_sheet(name[:31])
        ws.append(["Instrument", "Vikt (%)"])
        style_header(ws)
        for ticker, w in sorted(positions.items(), key=lambda x: -x[1]):
            ws.append([ticker, w])

    # Konsensus + analys
    green = PatternFill("solid", start_color="C6EFCE")
    red = PatternFill("solid", start_color="FFC7CE")
    # Divergens — signalgruppens unika övertygelser vs flocken
    if divergence:
        ws = wb.create_sheet("Divergens", 1)
        ws.append(["Instrument", "I signalgrupp", "Signalandel (%)", "I bakgrund (antal)",
                   "Bakgrundsandel (%)", "Divergens (pp)", "Bakgrundens snittvikt (%)",
                   "Claudes rekommendation", "Sektor", "Kluster-ID", "Klusterfaktor"])
        style_header(ws)
        for tk, dv in sorted(divergence.items(), key=lambda x: -x[1]["divergens_pp"]):
            kluster = rank_by_ticker.get(tk, {}).get("kluster") or {}
            ws.append([tk, f"{dv['signal_antal']}/{len(portfolios)}", dv["signal_andel_pct"],
                       dv["bakgrund_antal"], dv["bakgrund_andel_pct"], dv["divergens_pp"],
                       dv["bakgrund_snittvikt"],
                       claude_texts.get(tk, {}).get("rekommendation", ""),
                       analyses.get(tk, {}).get("sector"),
                       kluster.get("kluster_id"), kluster.get("klusterfaktor")])

        # Bubblare: nära konsensus med hög divergens
        bubblare = sorted(((tk, dv) for tk, dv in (divergence_near or {}).items()
                           if dv["divergens_pp"] >= 30),
                          key=lambda x: -x[1]["divergens_pp"])
        if bubblare:
            ws.append([])
            ws.append(["BUBBLARE — nära konsensus med hög divergens (ett köp från att kvala in)"])
            ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
            ws.append(["Instrument", "Ägs av (signalgrupp)", "Total vikt (%)",
                       "I bakgrund (antal)", "Bakgrundsandel (%)", "Divergens (pp)"])
            for c in ws[ws.max_row]:
                if c.value:
                    c.font, c.fill = hfont, hfill
            for tk, dv in bubblare:
                info = (near_consensus or {}).get(tk, {})
                ws.append([tk, ", ".join(info.get("holders", [])),
                           info.get("total_weight"),
                           dv["bakgrund_antal"], dv["bakgrund_andel_pct"], dv["divergens_pp"]])

    ws = wb.create_sheet("Konsensus & Analys", 2)
    ws.append(["Instrument", "Ny", "Stigande trend", "Antal portföljer", "Snittvikt (%)", "Pris", "RSI14",
               "Över MA200", "Rekommendation", "Riktkurs", "Uppsida (%)", "Antal analytiker",
               "Ägd längst (dagar)", "Investerarnas snittvinst (%)",
               "Viktad konsensus", "Senaste köp (dagar)", "EPS-rev 90d (%)", "Nettoflöde 30d (pe)",
               "P/E (forward)", "PEG", "Riktkurs spridning", "Nästa rapport"])
    style_header(ws)
    varning_fill = PatternFill("solid", start_color="FFEB9C")
    idag = date.today()
    consensus_order = sorted(consensus.items(), key=lambda x: (-x[1]["count"], -x[1]["avg_weight"]))
    for ticker, info in consensus_order:
        a = analyses.get(ticker, {})
        h = holding_info.get(ticker, {})
        trend = a.get("stigande_trend")
        spridning = a.get("riktkurs_spridningskvot")
        hog, lag = a.get("riktkurs_hog"), a.get("riktkurs_lag")
        spridning_txt = f"{lag:g}–{hog:g}" if (hog and lag) else None
        rapport = a.get("nasta_rapport")
        rapport_snart = False
        if rapport:
            try:
                rapport_snart = (date.fromisoformat(rapport) - idag).days <= 7
            except ValueError:
                pass
        ws.append([
            ticker, "NY" if is_new(ticker, "IN I KONSENSUS") else "",
            "JA" if trend else ("NEJ" if trend is not None else "?"),
            info["count"], round(info["avg_weight"], 2),
            a.get("pris"), a.get("RSI14"), a.get("över_MA200"),
            a.get("rekommendation"), a.get("riktkurs"), a.get("uppsida_%"), a.get("antal_analytiker"),
            h.get("längst_dagar"), h.get("snitt_vinst_pct"),
            info.get("viktad_konsensus"), info.get("senaste_köp_dagar"),
            a.get("eps_rev_90d_pct"),
            rank_by_ticker.get(ticker, {}).get("nettoflode_30d_pe"),
            a.get("forward_pe"), a.get("peg_ratio"), spridning_txt,
            f"⚠ {rapport}" if rapport_snart else rapport,
        ])
        if trend is not None:
            ws.cell(row=ws.max_row, column=3).fill = green if trend else red
        if rapport_snart:
            ws.cell(row=ws.max_row, column=ws.max_column).fill = varning_fill

    # Nära konsensus — en portfölj från att kvala in
    if near_consensus:
        ws.append([])
        ws.append([f"NÄRA KONSENSUS — i {MIN_PORTFOLIOS - 1} av {len(portfolios)} portföljer"])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.append(["Instrument", "Ny", "Antal portföljer", "Total vikt (%)", "Snittvikt (%)",
                   "Ägs av", "Ägd längst (dagar)", "Investerarnas snittvinst (%)"])
        for c in ws[ws.max_row]:
            if c.value:
                c.font, c.fill = hfont, hfill
        def _total(info):
            return info.get("total_weight") or round(info["avg_weight"] * info["count"], 2)
        for ticker, info in sorted(near_consensus.items(), key=lambda x: -_total(x[1])):
            h = holding_info.get(ticker, {})
            ws.append([ticker, "NY" if is_new(ticker, "IN I NÄRA KONSENSUS") else "",
                       info["count"], _total(info), round(info["avg_weight"], 2),
                       ", ".join(info.get("holders", [])),
                       h.get("längst_dagar"), h.get("snitt_vinst_pct")])

    # Lämnat listorna nyligen (senaste 30 dagarna)
    lamnat_cutoff = (date.today() - timedelta(days=30)).isoformat()
    lamnat = [e for e in history_log or []
              if e["typ"] in ("UT UR KONSENSUS", "UT UR NÄRA KONSENSUS")
              and e["datum"] >= lamnat_cutoff]
    if lamnat:
        ws.append([])
        ws.append(["LÄMNAT LISTORNA (senaste 30 dagarna)"])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.append(["Datum", "Instrument", "Typ", "Detalj"])
        for c in ws[ws.max_row]:
            if c.value:
                c.font, c.fill = hfont, hfill
        for e in lamnat:
            ws.append([e["datum"], e["ticker"], e["typ"], e["detalj"]])

    # Teknisk analys (indikatorer + Claudes text)
    ws = wb.create_sheet("Teknisk analys", 3)
    ws.append(["Instrument", "Stigande trend", "Över MA200", "MA200 stigande",
               "Pris", "MA50", "MA200", "Golden cross", "RSI14",
               "MACD > signal", "Bollinger (%)", "Avstånd 52v-högsta (%)",
               "Avkastning 1m (%)", "Avkastning 3m (%)", "Volymtrend (%)",
               "Claudes rekommendation", "Claudes analys", "Analys genererad", "EPS-rev 90d (%)"])
    style_header(ws)
    for ticker, _ in consensus_order:
        a = analyses.get(ticker, {})
        c = claude_texts.get(ticker, {})
        trend = a.get("stigande_trend")
        ws.append([
            ticker, "JA" if trend else ("NEJ" if trend is not None else "?"),
            a.get("över_MA200"), a.get("MA200_stigande"),
            a.get("pris"), a.get("MA50"), a.get("MA200"), a.get("golden_cross"),
            a.get("RSI14"), a.get("MACD_över_signal"), a.get("bollinger_position_%"),
            a.get("avstånd_52v_högsta_%"), a.get("avkastning_1m_%"), a.get("avkastning_3m_%"),
            a.get("volymtrend_20d_vs_3m_%"),
            c.get("rekommendation"), c.get("analys"), c.get("genererad"),
            a.get("eps_rev_90d_pct"),
        ])
        if trend is not None:
            ws.cell(row=ws.max_row, column=2).fill = green if trend else red
    ws.column_dimensions["Q"].width = 100
    for row in ws.iter_rows(min_row=2, min_col=17, max_col=17):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # Historik (ändringslogg, nyaste först)
    ws = wb.create_sheet("Historik", 4)
    ws.append(["Datum", "Typ", "Profil", "Instrument", "Detalj"])
    style_header(ws)
    if history_log:
        for e in history_log:
            ws.append([e["datum"], e["typ"], e["profil"], e["ticker"], e["detalj"]])
    else:
        ws.append(["", "Första körningen — ändringar visas från nästa körning.", "", "", ""])
    for col, width in (("A", 12), ("B", 18), ("C", 18), ("D", 12), ("E", 40)):
        ws.column_dimensions[col].width = width

    del wb["Sheet"]
    wb.save(OUTPUT_FILE)
    print(f"\nKlart! Rapport sparad som: {OUTPUT_FILE}")


def excel_from_result(result):
    """Återskapa portfolj_analys.xlsx från ett sparat resultat (RESULTS_FILE).

    Används av webbappen så att nedladdningsknappen alltid fungerar — även
    när Excel-filen saknas (t.ex. efter att Render vaknat ur sömn utan att
    ha kört en ny analys). All data finns redan i resultatet.
    """
    write_excel(
        result.get("portfolios", {}),
        result.get("consensus", {}),
        result.get("analyses", {}),
        result.get("claude", {}),
        result.get("historik", []),
        result.get("ranking"),
        result.get("nara_konsensus"),
        result.get("innehav"),
        result.get("divergens"),
        result.get("divergens_nara"),
    )


# ----------------------------------------------------------------------
# Huvudflöde
# ----------------------------------------------------------------------
RESULTS_FILE = "senaste_analys.json"


def run_analysis(with_claude=True, force_claude=False, refresh_background=False):
    """Kör hela pipelinen. Returnerar resultatet som dict och sparar det
    till RESULTS_FILE + portfolj_analys.xlsx. Kastar RuntimeError vid fel
    (så att webbappen kan visa felet i stället för att dö).

    Claude-analysen körs max en gång per dag (kostar API-credits) — har den
    redan körts idag återanvänds texterna. Nya konsensusaktier analyseras
    dock alltid. force_claude=True kringgår dagsspärren.

    refresh_background=True (--divergens) hämtar om bakgrundsgruppens
    portföljer; annars används befintlig cache utan extra API-anrop.
    """
    from datetime import datetime, date

    if not API_KEY or not USER_KEY:
        raise RuntimeError("ETORO_API_KEY och ETORO_USER_KEY saknas — lägg dem i .env-filen.")

    # Hämta beständig historik (Render har tillfällig disk)
    gist_pull()

    print("\nTestar API-anslutning...")
    test = api_get("/market-data/search", {"query": "Apple"})
    if test is None:
        raise RuntimeError("eToro-anslutningen misslyckades. Kontrollera nycklarna i .env.")
    print("Anslutning OK!")

    portfolios = {}
    port_meta = {}
    for username in PROFILES:
        p, meta = get_portfolio(username)
        if p:
            portfolios[username] = p
            port_meta[username] = meta or {}

    if not portfolios:
        raise RuntimeError("Inga portföljer kunde hämtas via eToro-API:et.")

    # Konsensus + nära konsensus (en portfölj ifrån)
    consensus, near_consensus = compute_consensus(portfolios, port_meta)

    print(f"\nKonsensus-aktier (i minst {MIN_PORTFOLIOS} portföljer): {sorted(consensus)}")
    print(f"Nära konsensus (i {MIN_PORTFOLIOS - 1} portföljer): {len(near_consensus)} st")

    # Bakgrundsgrupp + divergens (vad äger signalgruppen som flocken INTE äger?)
    background = load_background_portfolios(refresh=refresh_background)
    divergence = compute_divergence(consensus, portfolios, background)
    # Bubblare: nära konsensus-aktier med hög divergens — ett köp från att
    # kvala in, och flocken äger dem inte
    divergence_near = compute_divergence(near_consensus, portfolios, background)
    if divergence:
        rankad = sorted(divergence.items(), key=lambda x: -x[1]["divergens_pp"])
        print("Divergens (signalgrupp − bakgrundsgrupp):")
        for tk, dv in rankad:
            print(f"  {tk:<6} signal {dv['signal_andel_pct']}% | "
                  f"bakgrund {dv['bakgrund_andel_pct']}% | divergens {dv['divergens_pp']:+.1f} pp")

    # Förra körningens resultat (för Claude-dagsspärren och som reserv
    # för analytikerdata när Yahoo blockerar)
    prev = {}
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE) as f:
                prev = json.load(f)
        except (json.JSONDecodeError, OSError):
            prev = {}

    # Teknisk analys + analytikerdata
    import time
    analyses = {}
    for ticker in consensus:
        print(f"Analyserar {ticker}...")
        analyses[ticker] = analyze_ticker(ticker)
        if "error" in analyses[ticker]:
            print(f"    FEL för {ticker}: {analyses[ticker]['error']}")
        elif analyses[ticker].get("datakälla") != "Yahoo":
            print(f"    (Yahoo blockerade — data från {analyses[ticker]['datakälla']})")
        time.sleep(1.5)   # snäll paus så Yahoo inte strypmarkerar oss

    # Fallerar båda datakällorna (t.ex. Alpha Vantages dagsgräns på 25 anrop)?
    # Återanvänd då hela förra körningens analys i stället för en tom rad.
    prev_analyses = prev.get("analyses") or {}
    for ticker, a in analyses.items():
        if "error" not in a:
            continue
        pa = prev_analyses.get(ticker)
        if pa and "error" not in pa:
            cached = dict(pa)
            cached["datakälla"] = "cache"
            cached["cache_datum"] = (prev.get("tidpunkt") or "")[:16].replace("T", " kl. ")
            analyses[ticker] = cached
            print(f"    {ticker}: datakällorna svarade inte — återanvänder analysen från {cached['cache_datum']}")
    for ticker, a in analyses.items():
        if "error" in a or a.get("riktkurs"):
            continue
        pa = prev_analyses.get(ticker) or {}
        if pa.get("riktkurs"):
            a["rekommendation"] = pa.get("rekommendation", "n/a")
            a["riktkurs"] = pa["riktkurs"]
            a["antal_analytiker"] = pa.get("antal_analytiker")
            if a.get("pris"):
                a["uppsida_%"] = round((pa["riktkurs"] / a["pris"] - 1) * 100, 1)
            print(f"    {ticker}: analytikerdata återanvänd från {prev.get('tidpunkt', 'förra körningen')[:10]}")

    # Innehavstid + investerarnas upparbetade vinst (från positionernas
    # openTimestamp/netProfit) för konsensus- och nära konsensus-aktier
    holding_info = {}
    today_d = date.today()
    for ticker in list(consensus) + list(near_consensus):
        per_profil = {}
        for prof, meta in port_meta.items():
            m = meta.get(ticker) or {}
            if m.get("öppnad"):
                dagar = (today_d - date.fromisoformat(m["öppnad"])).days
                per_profil[prof] = {"dagar": dagar, "vinst_pct": m.get("vinst_pct")}
        if not per_profil:
            continue
        längst_prof, längst = max(per_profil.items(), key=lambda x: x[1]["dagar"])
        vinster = [v["vinst_pct"] for v in per_profil.values() if v["vinst_pct"] is not None]
        holding_info[ticker] = {
            "längst_dagar": längst["dagar"],
            "längst_profil": längst_prof,
            "snitt_dagar": round(sum(v["dagar"] for v in per_profil.values()) / len(per_profil)),
            "snitt_vinst_pct": round(sum(vinster) / len(vinster), 1) if vinster else None,
            "per_profil": per_profil,
        }

    # Ge Claude innehavskontexten (för "ta hem vinsten"-bedömningen)
    # och divergensen (unik övertygelse vs flockbeteende)
    for ticker, a in analyses.items():
        h = holding_info.get(ticker)
        if h and "error" not in a:
            a["investerarnas_innehavstid_dagar_längst"] = h["längst_dagar"]
            a["investerarnas_innehavstid_dagar_snitt"] = h["snitt_dagar"]
            a["investerarnas_upparbetade_vinst_pct_snitt"] = h["snitt_vinst_pct"]
        dv = divergence.get(ticker)
        if dv and "error" not in a:
            a["ägs_av_pct_av_bakgrundsgruppen"] = dv["bakgrund_andel_pct"]
            a["divergens_mot_bakgrundsgruppen_pp"] = dv["divergens_pp"]

    # Claude skriver en gedigen teknisk analys per konsensusaktie
    # (max en gång per dag — återanvänd dagens texter om de finns)
    prev_claude = prev.get("claude") or {}
    prev_datum = prev.get("claude_datum")
    today = date.today().isoformat()

    claude_texts = {}
    claude_datum = None
    helg = date.today().weekday() in (5, 6)   # lördag/söndag — marknaden stängd
    if with_claude:
        if helg and prev_claude and not force_claude:
            # Helgvila: kurserna är fredagens, så senaste analysen gäller ännu
            claude_texts = {t: c for t, c in prev_claude.items() if t in consensus}
            claude_datum = prev_datum
            print("\nHelg — marknaden stängd, Claude-analysen från senaste handelsdagen återanvänds.")
        elif prev_datum == today and not force_claude:
            claude_texts = {t: c for t, c in prev_claude.items() if t in consensus}
            claude_datum = prev_datum
            missing = {t: a for t, a in analyses.items()
                       if t not in claude_texts and "error" not in a}
            if missing:
                print(f"\nClaude-analys körd idag — analyserar bara {len(missing)} nya aktier...")
                claude_texts.update(claude_analysis(missing))
            else:
                print("\nClaude-analysen är redan körd idag — återanvänder den (max 1 gång/dag).")
        else:
            print("\nClaude-analys av konsensusaktierna...")
            claude_texts = claude_analysis(analyses)
            claude_datum = today if claude_texts else None
    else:
        # Claude bortvald denna körning — visa senaste kända texter
        claude_texts = {t: c for t, c in prev_claude.items() if t in consensus}
        claude_datum = prev_datum

    # Ändringshistorik mot förra körningen (görs innan rangordningen så
    # nettoflödet §5 kan använda dagens nyloggade ändringar också)
    print("\nUppdaterar ändringshistorik...")
    history_log = update_history(portfolios, list(consensus.keys()), list(near_consensus.keys()))

    # Sammanvägd rangordning
    ranking = build_ranking(analyses, consensus, history_log)
    print("\nRangordning (bästa köp först):")
    for i, r in enumerate(ranking, start=1):
        print(f"  {i}. {r['ticker']}: {r['poäng']} p (trend {'OK' if r['trend_ok'] else 'EJ OK'})")

    result = {
        "tidpunkt": datetime.now().isoformat(timespec="minutes"),
        "profiler": list(portfolios.keys()),
        "portfolios": portfolios,
        "consensus": consensus,
        "nara_konsensus": near_consensus,
        "analyses": analyses,
        "claude": claude_texts,
        "claude_datum": claude_datum,
        "ranking": ranking,
        "historik": history_log,
        "innehav": holding_info,
        "divergens": divergence,
        "divergens_nara": divergence_near,
        "bakgrund_antal": len(background) if background else 0,
        "bransch": {tk: _industry_cache.get(tk)
                    for tk in list(consensus) + list(near_consensus)},
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    write_excel(portfolios, consensus, analyses, claude_texts, history_log, ranking,
                near_consensus, holding_info, divergence, divergence_near)

    # Logga facit för --utvardera (poäng vs framtida avkastning)
    logga_facit(today, ranking, divergence, analyses, consensus)

    # Spara beständig historik till gisten
    gist_push()
    return result


def logga_facit(datum, ranking, divergence, analyses, consensus):
    """Appenda dagens poäng/divergens per konsensusaktie till FACIT_FILE.

    En rad per aktie och dag (idempotent — samma dag skrivs över), för senare
    utvärdering mot faktisk forward-avkastning via --utvardera.
    """
    facit = []
    if os.path.exists(FACIT_FILE):
        try:
            with open(FACIT_FILE) as f:
                facit = json.load(f)
        except (json.JSONDecodeError, OSError):
            facit = []
    facit = [r for r in facit if r.get("datum") != datum]   # ersätt dagens rader
    for r in ranking:
        tk = r["ticker"]
        a = analyses.get(tk, {})
        dv = (divergence or {}).get(tk, {})
        facit.append({
            "datum": datum,
            "ticker": tk,
            "poäng": r["poäng"],
            "komponenter": r["delpoäng"],
            "pris": a.get("pris"),
            "viktad_konsensus": consensus.get(tk, {}).get("viktad_konsensus"),
            "divergens_pp": dv.get("divergens_pp"),
        })
    with open(FACIT_FILE, "w") as f:
        json.dump(facit, f, ensure_ascii=False, indent=2)
    print(f"  Facit uppdaterat: {sum(1 for r in facit if r['datum'] == datum)} rader för {datum} "
          f"(totalt {len(facit)}).")


def run_utvardering():
    """Utvärdera poängmodellen mot faktisk forward-avkastning (21/63/126 dgr).

    Läser FACIT_FILE, hämtar prishistorik via yfinance och rapporterar
    avkastning per poängkvartil, komponentkorrelationer och divergensutfall
    till terminal + Excel-fliken 'Utvärdering' (utvardering.xlsx). Kör INTE
    analysen — glesa datapunkter är OK, rapporten anger n.
    """
    import yfinance as yf
    import pandas as pd

    gist_pull()
    if not os.path.exists(FACIT_FILE):
        raise RuntimeError(f"{FACIT_FILE} saknas — kör analysen minst en gång först.")
    with open(FACIT_FILE) as f:
        facit = json.load(f)
    if not facit:
        raise RuntimeError("Facit är tomt — kör analysen några gånger på olika datum först.")

    HORISONTER = [("21d", 21), ("63d", 63), ("126d", 126)]
    PRIMÄR = "63d"
    tickers = sorted({r["ticker"] for r in facit})
    BLIND_FLACK = (
        "Utvärdering av intern rangordning (mäter ej täckning) — facit "
        "innehåller bara aktier screenern redan lyfte fram. En bra "
        "kvartilkorrelation visar att modellen rangordnar KANDIDATERNA väl, "
        "inte att den hittar de bästa aktierna på hela marknaden."
    )
    print(BLIND_FLACK)
    print(f"\nUtvärderar {len(facit)} facitrader, {len(tickers)} unika aktier...")

    close_cache = {}
    for tk in tickers:
        try:
            h = yf.Ticker(tk).history(period="2y")
            if not h.empty:
                close_cache[tk] = h["Close"]
        except Exception:
            pass

    # Forward-avkastning per rad (närmaste handelsdag ≥ raddatumet)
    for r in facit:
        r["fwd"] = {}
        close = close_cache.get(r["ticker"])
        if close is None:
            continue
        d = pd.Timestamp(r["datum"])
        if close.index.tz is not None:
            d = d.tz_localize(close.index.tz)
        pos = int(close.index.searchsorted(d))
        if pos >= len(close):
            continue
        p0 = float(close.iloc[pos])
        for namn, n in HORISONTER:
            if pos + n < len(close) and p0:
                r["fwd"][namn] = round((float(close.iloc[pos + n]) / p0 - 1) * 100, 1)

    # Datamängd med primärhorisontens forward-avkastning
    rader = [r for r in facit if r["fwd"].get(PRIMÄR) is not None]
    n = len(rader)
    print(f"\nDatapunkter med {PRIMÄR} forward-avkastning: {n}")
    if n == 0:
        print("Ännu inga färdiga forward-fönster — kom tillbaka när facit mognat.")
        return
    if n < 10:
        print(f"VARNING: för tidigt för slutsatser (n={n}). Behöver ~10+ datapunkter.")

    df = pd.DataFrame([{
        "poäng": r["poäng"], "divergens_pp": r.get("divergens_pp"),
        "fwd": r["fwd"][PRIMÄR],
        **{f"k_{k}": v for k, v in (r.get("komponenter") or {}).items()},
    } for r in rader])

    rapport = []   # (rubrik, [(etikett, värde)])

    # 1. Avkastning per poängkvartil
    kvartil_rader = []
    try:
        df["kvartil"] = pd.qcut(df["poäng"], 4, labels=["Q1 (lägst)", "Q2", "Q3", "Q4 (högst)"],
                                duplicates="drop")
        for kv, grp in df.groupby("kvartil", observed=True):
            kvartil_rader.append((str(kv), f"snitt {grp['fwd'].mean():+.1f} %  (n={len(grp)})"))
    except (ValueError, IndexError):
        kvartil_rader.append(("—", "för få unika poäng för kvartiler"))
    rapport.append((f"Forward-avkastning ({PRIMÄR}) per poängkvartil", kvartil_rader))

    # 2. Komponentkorrelation mot forward-avkastning
    komp_rader = []
    for kol in [c for c in df.columns if c.startswith("k_")]:
        if df[kol].nunique() > 1:
            korr = df[kol].corr(df["fwd"])
            komp_rader.append((kol[2:], f"korr {korr:+.2f}"))
    komp_rader.append(("Totalpoäng", f"korr {df['poäng'].corr(df['fwd']):+.2f}"))
    rapport.append(("Korrelation komponentpoäng ↔ forward-avkastning", komp_rader))

    # 3. Divergensutfall (hög vs låg divergens)
    div_rader = []
    dd = df.dropna(subset=["divergens_pp"])
    if len(dd) >= 4:
        median = dd["divergens_pp"].median()
        hög = dd[dd["divergens_pp"] >= median]["fwd"].mean()
        låg = dd[dd["divergens_pp"] < median]["fwd"].mean()
        div_rader = [(f"Hög divergens (≥ {median:.0f} pp)", f"snitt {hög:+.1f} %"),
                     (f"Låg divergens (< {median:.0f} pp)", f"snitt {låg:+.1f} %")]
    else:
        div_rader = [("—", "för få divergensdatapunkter")]
    rapport.append(("Divergensutfall", div_rader))

    # Terminalrapport
    for rubrik, poster in rapport:
        print(f"\n{rubrik}:")
        for etikett, värde in poster:
            print(f"  {etikett:<22} {värde}")

    # Excel-flik
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Utvärdering"
    ws.append([f"Utvärdering av intern rangordning (mäter ej täckning) — "
               f"{n} datapunkter ({PRIMÄR} forward)"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([BLIND_FLACK])
    if n < 10:
        ws.append([f"VARNING: för tidigt för slutsatser (n={n})"])
    for rubrik, poster in rapport:
        ws.append([])
        ws.append([rubrik])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        for etikett, värde in poster:
            ws.append([etikett, värde])
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 30
    wb.save("utvardering.xlsx")
    print("\nRapport sparad som: utvardering.xlsx")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="eToro portföljanalys — konsensus, teknisk analys och divergens.",
        epilog="Utan flaggor körs standardanalysen av signalgruppens 5 profiler "
               "(divergensen räknas från senast cachade bakgrundsportföljer).")
    parser.add_argument("--screener", action="store_true",
                        help=f"screena fram bakgrundsgruppen (topp {BG_SIZE}) och spara till "
                             f"{BG_MEMBERS_FILE} — kör inte analysen")
    parser.add_argument("--divergens", action="store_true",
                        help="hämta om bakgrundsgruppens portföljer (kräver att --screener "
                             "körts någon gång) och kör sedan hela analysen")
    parser.add_argument("--force-claude", action="store_true",
                        help="kör Claude-analysen även om den redan körts idag (drar credits)")
    parser.add_argument("--utvardera", action="store_true",
                        help="utvärdera poängmodellen mot faktisk forward-avkastning "
                             f"({FACIT_FILE}) — kör inte analysen")
    args = parser.parse_args()

    print("=== eToro portföljanalys ===")
    try:
        if args.utvardera:
            run_utvardering()
            return
        if args.screener:
            if not API_KEY or not USER_KEY:
                raise RuntimeError("ETORO_API_KEY och ETORO_USER_KEY saknas — lägg dem i .env-filen.")
            gist_pull()
            if run_screener() is None:
                raise RuntimeError("Screenern misslyckades — se utskriften ovan.")
            gist_push()
            return
        run_analysis(force_claude=args.force_claude, refresh_background=args.divergens)
    except RuntimeError as e:
        sys.exit(f"\nFEL: {e}")


if __name__ == "__main__":
    main()
