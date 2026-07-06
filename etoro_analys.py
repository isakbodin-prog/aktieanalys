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
PROFILES = ["thomaspj", "michalhla", "JeppeKirkBonde", "triangulacapital", "Smudliczek"]
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


def api_get(path, params=None):
    """GET-anrop mot eToro:s publika API med felhantering."""
    url = f"{API_BASE}{path}"
    r = requests.get(url, headers=headers(), params=params, timeout=30)
    print(f"  GET {path} -> {r.status_code}")
    if r.status_code == 200:
        return r.json()
    print(f"    Svar: {r.text[:300]}")
    return None


# ----------------------------------------------------------------------
# Steg 1: Hämta portföljer
# ----------------------------------------------------------------------
_instrument_cache = {}

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
        print(f"  {len(_instrument_cache)} instrument i uppslagstabellen.")

    missing = [int(i) for i in instrument_ids if int(i) not in _instrument_cache]
    if missing:
        print(f"    OBS: {len(missing)} instrument kunde inte namnges, behåller ID:n: {missing[:10]}")

    return {int(i): _instrument_cache.get(int(i), str(i)) for i in instrument_ids}


def get_portfolio(username):
    """Hämta en användares live-portfölj. Returnerar dict {ticker: vikt%} eller None."""
    print(f"\nHämtar portfölj för: {username}")
    data = api_get(f"/user-info/people/{username}/portfolio/live")
    if not data:
        print(f"  Kunde inte hämta portfölj för '{username}'.")
        return None

    # Aggregera investmentPct per instrumentId (en användare kan ha flera positioner i samma instrument)
    weights = {}
    for p in data.get("positions") or []:
        iid = p.get("instrumentId")
        pct = p.get("investmentPct") or 0
        if iid is not None:
            weights[iid] = weights.get(iid, 0) + float(pct)

    # Positioner inuti social trades (kopierade portföljer) räknas också
    for st in data.get("socialTrades") or []:
        for p in st.get("positions") or []:
            iid = p.get("instrumentId")
            pct = p.get("investmentPct") or 0
            if iid is not None:
                weights[iid] = weights.get(iid, 0) + float(pct)

    if not weights:
        print(f"  Portföljen för '{username}' verkar vara tom eller dold.")
        return None

    id_to_ticker = resolve_instruments(list(weights.keys()))
    out = {id_to_ticker[iid]: round(pct, 2) for iid, pct in weights.items()}
    print(f"  {len(out)} innehav hämtade.")
    return out


# ----------------------------------------------------------------------
# Steg 2 & 3: Teknisk analys + analytikerdata (yfinance)
# ----------------------------------------------------------------------
ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")
_AV_URL = "https://www.alphavantage.co/query"


def fetch_history_alphavantage(yticker):
    """Reservkälla för dagskurser: Alpha Vantage (Yahoo blockerar ofta molnservrar).

    Returnerar en DataFrame med kolumnerna Close/Volume (senaste året) eller None.
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
        df = df.sort_index().rename(columns={"4. close": "Close", "5. volume": "Volume"})
        return df[["Close", "Volume"]].tail(252)   # ~1 handelsår
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
        }
    except Exception:
        return {}


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

        return {
            "ticker": ticker,
            "datakälla": source,
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
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


# ----------------------------------------------------------------------
# Steg 3b: Sammanvägd poäng och rangordning
# ----------------------------------------------------------------------
def compute_score(a, cons):
    """Sammanvägd poäng 0–100 för en aktie.

    Trend 30 p + Momentum 25 p + Analytiker 25 p + Konsensus 20 p.
    Returnerar (totalpoäng, delpoäng-dict).
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

    # Analytiker (max 25)
    ana = 0.0
    uppsida = a.get("uppsida_%")
    if uppsida is not None:
        ana += max(0.0, min(15.0, uppsida / 2))   # 30 % uppsida ger full poäng
    ana += min(5.0, (a.get("antal_analytiker") or 0) / 8)   # 40 analytiker ger full poäng
    if a.get("rekommendation") in ("strong_buy", "buy"):
        ana += 5
    delpoang["Analytiker"] = round(ana, 1)

    # Konsensus (max 20) — hur eniga och övertygade investerarna är
    kon = 0.0
    span = max(1, len(PROFILES) - MIN_PORTFOLIOS)
    kon += min(10.0, (cons["count"] - MIN_PORTFOLIOS) * (10 / span) + 10 / span)
    kon += min(10.0, cons["avg_weight"] * 2)   # 5 % snittvikt ger full poäng
    delpoang["Konsensus"] = round(kon, 1)

    total = round(sum(delpoang.values()), 1)
    return total, delpoang


def build_ranking(analyses, consensus):
    """Rangordna konsensusaktierna. Aktier utan stigande trend sist, oavsett poäng."""
    ranking = []
    for ticker, cons in consensus.items():
        a = analyses.get(ticker, {})
        if "error" in a:
            continue
        total, delpoang = compute_score(a, cons)
        ranking.append({
            "ticker": ticker,
            "poäng": total,
            "trend_ok": bool(a.get("stigande_trend")),
            "delpoäng": delpoang,
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
        "Svara EXAKT i detta format:\n"
        "REKOMMENDATION: <KÖP | AVVAKTA | SÄLJ>\n"
        "<själva analysen>"
    )

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
            results[ticker] = {"rekommendation": rating, "analys": text}
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
GIST_FILES = ("portfolj_historik.json", "senaste_analys.json")


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


def update_history(portfolios, consensus_tickers):
    """Jämför med förra körningen, logga ändringar och spara ny ögonblicksbild.

    Returnerar hela ändringsloggen (nyaste först).
    """
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
        for tk in sorted(new_cons - old_cons):
            log("IN I KONSENSUS", "", tk, "finns nu i ≥3 portföljer")
        for tk in sorted(old_cons - new_cons):
            log("UT UR KONSENSUS", "", tk, "finns i <3 portföljer")

        if entries:
            print(f"  {len(entries)} ändringar sedan {prev.get('datum', 'förra körningen')}.")
        else:
            print(f"  Inga ändringar sedan {prev.get('datum', 'förra körningen')}.")
    else:
        print("  Första körningen — skapar utgångsläge för historiken.")

    state["senaste"] = {"datum": today, "portfolios": portfolios,
                        "consensus": sorted(consensus_tickers)}
    state["logg"] = entries + state.get("logg", [])
    with open(HISTORY_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    return state["logg"]


# ----------------------------------------------------------------------
# Steg 6: Excel-rapport
# ----------------------------------------------------------------------
def write_excel(portfolios, consensus, analyses, claude_texts, history_log,
                ranking=None, near_consensus=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

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
        ws.append(["Rang", "Instrument", "Poäng (0–100)", "Stigande trend",
                   "Trend (30)", "Momentum (25)", "Analytiker (25)", "Konsensus (20)",
                   "Claudes rekommendation"])
        style_header(ws)
        for i, r in enumerate(ranking, start=1):
            d = r["delpoäng"]
            ws.append([i, r["ticker"], r["poäng"], "JA" if r["trend_ok"] else "NEJ",
                       d.get("Trend"), d.get("Momentum"), d.get("Analytiker"), d.get("Konsensus"),
                       claude_texts.get(r["ticker"], {}).get("rekommendation", "")])
            ws.cell(row=ws.max_row, column=4).fill = green if r["trend_ok"] else red

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
    ws = wb.create_sheet("Konsensus & Analys", 1)
    ws.append(["Instrument", "Stigande trend", "Antal portföljer", "Snittvikt (%)", "Pris", "RSI14",
               "Över MA200", "Rekommendation", "Riktkurs", "Uppsida (%)", "Antal analytiker"])
    style_header(ws)
    consensus_order = sorted(consensus.items(), key=lambda x: (-x[1]["count"], -x[1]["avg_weight"]))
    for ticker, info in consensus_order:
        a = analyses.get(ticker, {})
        trend = a.get("stigande_trend")
        ws.append([
            ticker, "JA" if trend else ("NEJ" if trend is not None else "?"),
            info["count"], round(info["avg_weight"], 2),
            a.get("pris"), a.get("RSI14"), a.get("över_MA200"),
            a.get("rekommendation"), a.get("riktkurs"), a.get("uppsida_%"), a.get("antal_analytiker"),
        ])
        if trend is not None:
            ws.cell(row=ws.max_row, column=2).fill = green if trend else red

    # Nära konsensus — en portfölj från att kvala in
    if near_consensus:
        ws.append([])
        ws.append([f"NÄRA KONSENSUS — i {MIN_PORTFOLIOS - 1} av {len(portfolios)} portföljer"])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        ws.append(["Instrument", "Antal portföljer", "Snittvikt (%)", "Ägs av"])
        for c in ws[ws.max_row]:
            if c.value:
                c.font, c.fill = hfont, hfill
        for ticker, info in sorted(near_consensus.items(), key=lambda x: -x[1]["avg_weight"]):
            ws.append([ticker, info["count"], round(info["avg_weight"], 2),
                       ", ".join(info.get("holders", []))])

    # Teknisk analys (indikatorer + Claudes text)
    ws = wb.create_sheet("Teknisk analys", 2)
    ws.append(["Instrument", "Stigande trend", "Över MA200", "MA200 stigande",
               "Pris", "MA50", "MA200", "Golden cross", "RSI14",
               "MACD > signal", "Bollinger (%)", "Avstånd 52v-högsta (%)",
               "Avkastning 1m (%)", "Avkastning 3m (%)", "Volymtrend (%)",
               "Claudes rekommendation", "Claudes analys"])
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
            a.get("volymtrend_20d_vs_3m_%"), c.get("rekommendation"), c.get("analys"),
        ])
        if trend is not None:
            ws.cell(row=ws.max_row, column=2).fill = green if trend else red
    ws.column_dimensions["Q"].width = 100
    for row in ws.iter_rows(min_row=2, min_col=17, max_col=17):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # Historik (ändringslogg, nyaste först)
    ws = wb.create_sheet("Historik", 3)
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


# ----------------------------------------------------------------------
# Huvudflöde
# ----------------------------------------------------------------------
RESULTS_FILE = "senaste_analys.json"


def run_analysis(with_claude=True, force_claude=False):
    """Kör hela pipelinen. Returnerar resultatet som dict och sparar det
    till RESULTS_FILE + portfolj_analys.xlsx. Kastar RuntimeError vid fel
    (så att webbappen kan visa felet i stället för att dö).

    Claude-analysen körs max en gång per dag (kostar API-credits) — har den
    redan körts idag återanvänds texterna. Nya konsensusaktier analyseras
    dock alltid. force_claude=True kringgår dagsspärren.
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
    for username in PROFILES:
        p = get_portfolio(username)
        if p:
            portfolios[username] = p

    if not portfolios:
        raise RuntimeError("Inga portföljer kunde hämtas via eToro-API:et.")

    # Konsensus + nära konsensus (en portfölj ifrån)
    consensus = {}
    near_consensus = {}
    all_tickers = set()
    for positions in portfolios.values():
        all_tickers.update(positions.keys())
    for ticker in all_tickers:
        holders = {name: p[ticker] for name, p in portfolios.items() if ticker in p}
        entry = {"count": len(holders),
                 "avg_weight": sum(holders.values()) / len(holders),
                 "holders": sorted(holders)}
        if len(holders) >= MIN_PORTFOLIOS:
            consensus[ticker] = entry
        elif len(holders) == MIN_PORTFOLIOS - 1:
            near_consensus[ticker] = entry

    print(f"\nKonsensus-aktier (i minst {MIN_PORTFOLIOS} portföljer): {sorted(consensus)}")
    print(f"Nära konsensus (i {MIN_PORTFOLIOS - 1} portföljer): {len(near_consensus)} st")

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

    # Saknas analytikerdata (Yahoo nere/blockerad)? Återanvänd förra körningens
    # — riktkurser och rekommendationer ändras långsamt.
    prev_analyses = prev.get("analyses") or {}
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

    # Claude skriver en gedigen teknisk analys per konsensusaktie
    # (max en gång per dag — återanvänd dagens texter om de finns)
    prev_claude = prev.get("claude") or {}
    prev_datum = prev.get("claude_datum")
    today = date.today().isoformat()

    claude_texts = {}
    claude_datum = None
    if with_claude:
        if prev_datum == today and not force_claude:
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

    # Sammanvägd rangordning
    ranking = build_ranking(analyses, consensus)
    print("\nRangordning (bästa köp först):")
    for i, r in enumerate(ranking, start=1):
        print(f"  {i}. {r['ticker']}: {r['poäng']} p (trend {'OK' if r['trend_ok'] else 'EJ OK'})")

    # Ändringshistorik mot förra körningen
    print("\nUppdaterar ändringshistorik...")
    history_log = update_history(portfolios, list(consensus.keys()))

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
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    write_excel(portfolios, consensus, analyses, claude_texts, history_log, ranking, near_consensus)

    # Spara beständig historik till gisten
    gist_push()
    return result


def main():
    print("=== eToro portföljanalys ===")
    try:
        run_analysis(force_claude="--force-claude" in sys.argv)
    except RuntimeError as e:
        sys.exit(f"\nFEL: {e}")


if __name__ == "__main__":
    main()
