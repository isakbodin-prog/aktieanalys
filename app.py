#!/usr/bin/env python3
"""
eToro Portföljanalys — webbapp
==============================

Starta appen:
    python3 -m streamlit run app.py

Den öppnas i webbläsaren på http://localhost:8501.
Nycklarna läses från .env-filen precis som för etoro_analys.py.
"""

import json
import os

import pandas as pd
import streamlit as st

import etoro_analys as ea
from ikoner import IKON

st.set_page_config(page_title="eToro Portföljanalys",
                   page_icon=":material/monitoring:", layout="wide")

# ----------------------------------------------------------------------
# Dämpad, redaktionell färgpalett (ol.studio-inspirerad)
# ----------------------------------------------------------------------
MOSS = "#5F6B4A"    # mossgrön — positivt (upp, köp, ja)
RUST = "#9C5B41"    # dämpad rost — negativt (ner, sälj, nej)
SAND = "#A8863B"    # sandockra — avvakta / MA50
OLIV = "#6B7052"    # dämpad oliv — MA200 / accent
MUTED = "#8A8375"   # varm grå — neutralt/sekundärt
TEXT = "#433D34"    # varm mörkbrun (samma som temat)
HAIRLINE = "#D9D1C0"  # hårfin linje mot den varma gräddvita bakgrunden

REK_FARG = {"KÖP": MOSS, "AVVAKTA": SAND, "SÄLJ": RUST}

# ----------------------------------------------------------------------
# Hårfina linjer + typografiska finjusteringar (ol.studio-känsla)
# ----------------------------------------------------------------------
st.markdown(f"""
<style>
  hr {{ margin: 1.3rem 0 !important; border: none !important;
        border-top: 1px solid {HAIRLINE} !important; }}
  [data-testid="stExpander"] details {{ border-color: {HAIRLINE} !important; }}
  /* diskretare flikrad med hårlinje under */
  [data-testid="stTabs"] [data-baseweb="tab-list"] {{
      border-bottom: 1px solid {HAIRLINE}; gap: 1.6rem; }}
  /* sidfoten */
  .appfot {{ display: flex; justify-content: space-between; flex-wrap: wrap;
      gap: .5rem 2rem; margin: 3.5rem 0 1rem; padding-top: 1rem;
      border-top: 1px solid {HAIRLINE}; color: {MUTED};
      font-size: .78rem; letter-spacing: .02em; }}
  .appfot .mitt {{ text-align: center; }}

  /* --- Sidopanel: mer luft, diskreta knappar --- */
  section[data-testid="stSidebar"] > div {{ padding-top: 2.5rem; }}
  section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: 1.4rem; }}
  section[data-testid="stSidebar"] h1 {{
      font-size: 1.35rem !important; letter-spacing: .01em; margin-bottom: .4rem; }}
  /* knappar: transparent bakgrund, hårlinjeram, mjuk hover */
  section[data-testid="stSidebar"] button {{
      background: transparent !important; border: 1px solid {HAIRLINE} !important;
      color: {TEXT} !important; font-weight: 400 !important; border-radius: 3px !important; }}
  section[data-testid="stSidebar"] button:hover {{
      border-color: {OLIV} !important; color: {OLIV} !important; }}
  /* expander-huvuden: ramlösa, bara text */
  section[data-testid="stSidebar"] [data-testid="stExpander"] details {{
      border: none !important; }}
  section[data-testid="stSidebar"] [data-testid="stExpander"] summary {{
      padding-left: 0 !important; color: {MUTED} !important;
      font-size: .82rem !important; letter-spacing: .04em; text-transform: uppercase; }}
</style>
""", unsafe_allow_html=True)


def mark(value):
    """✓/✗/– som dämpat färgad HTML-span (kräver unsafe_allow_html=True)."""
    if value is None:
        return f'<span style="color:{MUTED}">–</span>'
    return (f'<span style="color:{MOSS}">✓</span>' if value
            else f'<span style="color:{RUST}">✗</span>')


def _cell_farg(v):
    """Dämpad textfärg per cellvärde — används av stylad()."""
    s = str(v)
    if s.startswith("▲") or s == "KÖP" or s.endswith("· ny") or s == "Unik övertygelse":
        return f"color: {MOSS}"
    if s.startswith("▼") or s == "SÄLJ":
        return f"color: {RUST}"
    if s == "AVVAKTA":
        return f"color: {SAND}"
    if s in ("Flockbeteende", "–"):
        return f"color: {MUTED}"
    return ""


def stylad(df, kolumner):
    """Dämpade cellfärger på valda kolumner + max 2 decimaler på alla tal."""
    subset = [k for k in kolumner if k in df.columns]
    styler = df.style.format(precision=2)
    fn = getattr(styler, "map", None) or styler.applymap
    return fn(_cell_farg, subset=subset)


# ----------------------------------------------------------------------
# Branschsymboler — stocksIndustryID från eToro + egen halvledargrupp
# ----------------------------------------------------------------------
HALVLEDARE = {"NVDA", "TSM", "MU", "ASML", "ASML.NV", "AMD", "INTC", "KLAC",
              "AVGO", "QCOM", "TXN", "AMAT", "LRCX", "MRVL", "ARM", "2330.TW"}

BRANSCH_TEXT = ("Branschikoner: chip = halvledare · dator = teknik · bank = finans · "
                "fabrik = industri · butik = tjänster · kasse = konsument · "
                "hjärta = hälsovård · blixt = kraft · berg = råvaror")


def bransch_ikon(tk, bransch_map):
    """SVG-ikon (data-URI) för aktiens bransch — visas i tabellernas ikonkolumn."""
    if tk in HALVLEDARE:
        return IKON.get("halvledare")
    return IKON.get(bransch_map.get(tk))


# ----------------------------------------------------------------------
# Lösenordsskydd — aktivt bara när APP_PASSWORD är satt (t.ex. på Render).
# Utan det kan vem som helst som hittar sidan trigga API-anrop.
# Bokmärkesinloggning: spara ett bokmärke med ?nyckel=lösenordet så
# loggas du in automatiskt vid varje besök.
# ----------------------------------------------------------------------
APP_PASSWORD = os.environ.get("APP_PASSWORD")
if APP_PASSWORD and not st.session_state.get("auth_ok"):
    if st.query_params.get("nyckel") == APP_PASSWORD:
        st.session_state["auth_ok"] = True
    else:
        st.title("eToro Portföljanalys")
        pwd = st.text_input("Lösenord", type="password")
        if pwd:
            if pwd == APP_PASSWORD:
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Fel lösenord.")
        st.caption("Tips: spara ett bokmärke till adressen med `?nyckel=ditt-lösenord` "
                   "på slutet så loggas du in automatiskt.")
        st.stop()


def load_results():
    if os.path.exists(ea.RESULTS_FILE):
        with open(ea.RESULTS_FILE) as f:
            return json.load(f)
    return None


def trend_label(a):
    t = a.get("stigande_trend")
    if t is None:
        return "–"
    return "▲ Ja" if t else "▼ Nej"


def format_innehavstid(dagar):
    if dagar is None:
        return "—"
    return f"{dagar} dagar" if dagar < 90 else f"{dagar / 365:.1f} år"


def nya_pa_listan(log, typ, dagar=7):
    """Tickers som fått en '{typ}'-loggpost de senaste `dagar` dagarna."""
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=dagar)).isoformat()
    return {e["ticker"] for e in log if e["typ"] == typ and e["datum"] >= cutoff}


def _pe(d):
    """Formatera procentenheter, svensk decimal: +2,3 pe."""
    return f"{d:+.1f}".replace(".", ",") + " pe"


def _delta_pe(e):
    """Viktförändring i procentenheter ur en loggpost (nytt=+, sålt=−)."""
    import re
    tal = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", e["detalj"].replace(",", "."))]
    if e["typ"] == "VIKTÄNDRING" and len(tal) >= 2:
        return tal[1] - tal[0]
    if e["typ"] == "NYTT INNEHAV" and tal:
        return tal[0]
    if e["typ"] == "SÅLT INNEHAV" and tal:
        return -tal[0]
    return None


def rorelser_per_aktie(dagens):
    """{ticker: [{profil, delta, typ, detalj}]} för en dags viktrörelser."""
    moves = {}
    for e in dagens:
        if e["typ"] in ("VIKTÄNDRING", "NYTT INNEHAV", "SÅLT INNEHAV"):
            d = _delta_pe(e)
            if d is not None:
                moves.setdefault(e["ticker"], []).append(
                    {"profil": e["profil"], "delta": d, "typ": e["typ"], "detalj": e["detalj"]})
    return moves


def candlestick(ohlc):
    """Candlestick-graf (senaste ~90 dagarna) med MA50/MA200, i palettens färger."""
    import altair as alt

    df = pd.DataFrame(ohlc)
    df["d"] = pd.to_datetime(df["d"])
    df["upp"] = df["c"] >= df["o"]

    bas = alt.Chart(df).encode(
        x=alt.X("d:T", axis=alt.Axis(title=None, format="%-d %b", tickCount=5,
                                     grid=False, labelColor=MUTED, domainColor=HAIRLINE,
                                     tickColor=HAIRLINE)))
    farg = alt.condition("datum.upp", alt.value(MOSS), alt.value(RUST))
    y = alt.Y("l:Q", scale=alt.Scale(zero=False),
              axis=alt.Axis(title=None, grid=True, gridColor=HAIRLINE, gridOpacity=.6,
                            labelColor=MUTED, domainColor=HAIRLINE, tickColor=HAIRLINE))
    stapel_axel = alt.Y("o:Q", scale=alt.Scale(zero=False), axis=None)

    wick = bas.mark_rule(strokeWidth=1).encode(y=y, y2="h:Q", color=farg)
    body = bas.mark_bar(size=5).encode(y=stapel_axel, y2="c:Q", color=farg)
    ma50 = bas.mark_line(color=SAND, strokeWidth=1.2).encode(y=alt.Y("ma50:Q", axis=None))
    ma200 = bas.mark_line(color=OLIV, strokeWidth=1.2).encode(y=alt.Y("ma200:Q", axis=None))

    return (wick + body + ma50 + ma200).properties(height=280, background="transparent").configure_view(
        strokeWidth=0).configure_axis(labelFont="Space Grotesk", labelFontSize=11)


# ----------------------------------------------------------------------
# Sidopanel
# ----------------------------------------------------------------------
def data_ar_fran_idag(d):
    from datetime import date
    if not d:
        return False
    if date.today().weekday() in (5, 6):
        return True   # helg: marknaden stängd, befintlig data är per definition färsk
    return d.get("tidpunkt", "")[:10] == date.today().isoformat()


st.sidebar.title("eToro Portföljanalys")
run_now = st.sidebar.button(":material/refresh: Uppdatera nu", use_container_width=True)

with st.sidebar.expander("Inställningar"):
    with_claude = st.checkbox(
        "Inkludera Claude-analys", value=True,
        help="Claude körs max en gång per dag (drar API-credits) — annars återanvänds dagens analys.",
    )
    force_claude = st.checkbox(
        "Tvinga om Claude-analysen", value=False,
        help="Kör Claude igen även om den redan körts idag. Drar credits!",
    )

with st.sidebar.expander("Bakgrundsgrupp & divergens"):
    def _fildatum(fil):
        try:
            with open(fil) as f:
                return json.load(f).get("datum")
        except (OSError, json.JSONDecodeError):
            return None

    st.caption(f"Senast screenad: {_fildatum(ea.BG_MEMBERS_FILE) or 'aldrig'} · "
               f"portföljer hämtade: {_fildatum(ea.BG_CACHE_FILE) or 'aldrig'}")
    st.caption("Körs även automatiskt: screener månadsvis, divergens varje lördag.")

    if st.button(":material/person_search: Kör screener", use_container_width=True,
                 help="Väljer om vilka 50 traders som utgör bakgrundsgruppen. Snabbt (~10 s)."):
        with st.spinner("Screenar fram topp 50..."):
            try:
                if ea.run_screener():
                    ea.gist_push()
                    st.success("Bakgrundsgruppen är uppdaterad!")
                else:
                    st.error("Screenern misslyckades — försök igen senare.")
            except Exception as e:
                st.error(str(e))

    if st.button(":material/balance: Uppdatera divergens", use_container_width=True,
                 help="Hämtar bakgrundsgruppens 50 portföljer och kör om analysen. Tar 3–5 minuter."):
        with st.spinner("Hämtar 50 bakgrundsportföljer och räknar om divergensen — tar 3–5 minuter..."):
            try:
                ea.run_analysis(with_claude=with_claude, refresh_background=True)
                st.success("Divergensen är uppdaterad!")
            except RuntimeError as e:
                st.error(str(e))

# Vid sidöppning: synka först mot gisten (fångar t.ex. --divergens-körningar
# gjorda på datorn), kör sedan analysen bara om dagens data saknas.
if "auto_check" not in st.session_state:
    st.session_state["auto_check"] = True
    ea.gist_pull()              # no-op om GIST_ID/GITHUB_TOKEN saknas
    befintlig = load_results()
    if not data_ar_fran_idag(befintlig):
        run_now = True

if run_now:
    with st.spinner("Hämtar portföljdata från eToro och räknar indikatorer — tar 1–2 minuter..."):
        try:
            ea.run_analysis(with_claude=with_claude, force_claude=force_claude)
        except RuntimeError as e:
            st.sidebar.error(str(e))

data = load_results()

if data:
    cd = data.get("claude_datum")
    st.sidebar.caption(f"Data {data['tidpunkt'].replace('T', ' kl. ')}"
                       + (f" · Claude {cd}" if cd else ""))

    # Visa datafel tydligt (t.ex. om Yahoo Finance blockerar serverns anrop)
    fel = {t: a["error"] for t, a in data.get("analyses", {}).items() if "error" in a}
    if fel:
        with st.sidebar.expander(f":material/warning: {len(fel)} aktier saknar marknadsdata"):
            for t, e in fel.items():
                st.caption(f"**{t}**: {e}")
    # Se till att Excel-filen finns och matchar senaste analysen — återskapa
    # den ur sparad data om den saknas eller är äldre (t.ex. efter Render-sömn).
    behov_regen = not os.path.exists(ea.OUTPUT_FILE)
    if not behov_regen and os.path.exists(ea.RESULTS_FILE):
        behov_regen = os.path.getmtime(ea.OUTPUT_FILE) < os.path.getmtime(ea.RESULTS_FILE)
    if behov_regen:
        try:
            ea.excel_from_result(data)
        except Exception as e:
            st.sidebar.caption(f"Kunde inte skapa Excel-rapporten: {e}")

    if os.path.exists(ea.OUTPUT_FILE):
        with open(ea.OUTPUT_FILE, "rb") as f:
            st.sidebar.download_button(
                ":material/download: Ladda ner Excel-rapport", f.read(),
                file_name=ea.OUTPUT_FILE,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

st.sidebar.divider()
st.sidebar.caption("Bevakar " + " · ".join(ea.PROFILES))

# ----------------------------------------------------------------------
# Huvudinnehåll
# ----------------------------------------------------------------------
if not data:
    st.title("eToro Portföljanalys")
    st.info("Ingen analys har körts ännu. Klicka på **Kör ny analys** i sidopanelen för att komma igång.")
    st.stop()

consensus = data["consensus"]
analyses = data["analyses"]
claude = data.get("claude", {})
bransch = data.get("bransch", {})
consensus_order = sorted(consensus, key=lambda t: (-consensus[t]["count"], -consensus[t]["avg_weight"]))

tab_rang, tab_konsensus, tab_diverg, tab_analys, tab_andringar, tab_historik, tab_portfoljer = st.tabs(
    ["I. Bästa köp", "II. Konsensus", "III. Divergens", "IV. Claudes analys",
     "V. Senaste ändringar", "VI. Historik", "VII. Portföljer"]
)

# --- Rangordning ---
with tab_rang:
    st.subheader("Rangordning — sammanvägd poäng (0–100)")
    ranking = data.get("ranking", [])
    if not ranking:
        st.info("Ingen rangordning i senaste körningen — kör en ny analys.")
    else:
        # Rapport-badges: aktier med bolagsrapport inom 7 dagar
        from datetime import date as _d_rang
        rapport_snart = []
        for tk in [r["ticker"] for r in ranking]:
            rap = analyses.get(tk, {}).get("nasta_rapport")
            if rap:
                try:
                    dagar_kvar = (pd.Timestamp(rap).date() - _d_rang.today()).days
                    if 0 <= dagar_kvar <= 7:
                        rapport_snart.append((tk, dagar_kvar))
                except Exception:
                    pass
        if rapport_snart:
            badges = " · ".join(f"**{tk}** om {d} dgr" for tk, d in sorted(rapport_snart, key=lambda x: x[1]))
            st.caption(f":material/event_upcoming: **Rapport inom en vecka:** {badges}")

        rows = []
        for i, r in enumerate(ranking, start=1):
            d = r["delpoäng"]
            c = claude.get(r["ticker"], {})
            kluster = r.get("kluster") or {}
            rs = r.get("relativ_styrka") or {}
            rows.append({
                "Rang": i,
                "Bransch": bransch_ikon(r["ticker"], bransch),
                "Aktie": r["ticker"],
                "Poäng": r["poäng"],
                "Poäng (v1)": r.get("poäng_v1"),
                "Stigande trend": "▲ Ja" if r["trend_ok"] else "▼ Nej",
                "Trend (25)": d.get("Trend"),
                "Momentum (20)": d.get("Momentum"),
                "Analytiker (20)": d.get("Analytiker"),
                "Konsensus (25)": d.get("Konsensus"),
                "Värdering (10)": d.get("Värdering"),
                "Viktad kons.": consensus.get(r["ticker"], {}).get("viktad_konsensus"),
                "Nettoflöde 30d (pe)": r.get("nettoflode_30d_pe"),
                "Rel. styrka (pe)": rs.get("rs_pe"),
                "Föreslagen vikt (%)": r.get("foreslagen_vikt_%"),
                "Kluster": (f"#{kluster['kluster_id']} ({kluster['klusterstorlek']} st)"
                           if kluster.get("klusterstorlek", 1) > 1 else "ensam"),
                "Claude": c.get("rekommendation", "—"),
            })
        st.dataframe(
            stylad(pd.DataFrame(rows), ["Stigande trend", "Claude"]),
            use_container_width=True, hide_index=True,
            column_config={
                "Bransch": st.column_config.ImageColumn("", width=36),
                "Poäng": st.column_config.ProgressColumn(
                    "Poäng", min_value=0, max_value=100, format="%.1f"
                ),
            },
        )
        st.caption(
            "**Poängmodellen (§12, omviktad):** Trend 25 p · Momentum 20 p (inkl. relativ "
            "styrka mot sektor-ETF) · Analytiker 20 p (uppsida — halverad vid hög "
            "riktkursspridning — antal analytiker, köprekommendation, EPS-revidering) · "
            "Konsensus 25 p (viktad konsensus, snittvikt, nettoflöde 30d) — delat med "
            "√klusterstorlek om aktien samvarierar starkt (korr > 0,7) med andra "
            "konsensusaktier · Värdering 10 p (forward P/E mot sektormedian, PEG). "
            "**Poäng (v1)** är förra modellen (utan Värdering/RS/spridning) — kvar för "
            "jämförelse tills --utvardera hunnit kalibrera de nya vikterna. "
            "Aktier utan stigande trend rankas alltid sist, oavsett poäng."
        )

    # --- Senaste händelser: kondenserad översikt på förstasidan ---
    log = data.get("historik", [])
    if log:
        from datetime import date as _d, timedelta as _td
        cut30 = (_d.today() - _td(days=30)).isoformat()
        senaste_datum = log[0]["datum"]
        dagens = [e for e in log if e["datum"] == senaste_datum]

        # Förändringar i listorna (30 dgr): in/ut konsensus + lämnat nära konsensus
        lista_rader = []
        for e in log:
            if e["datum"] < cut30:
                continue
            if e["typ"] == "IN I KONSENSUS":
                lista_rader.append(f'<span style="color:{MOSS}">▲</span> **{e["ticker"]}** '
                                   f'in i konsensus — {e["detalj"]}')
            elif e["typ"] == "UT UR KONSENSUS":
                lista_rader.append(f'<span style="color:{RUST}">▼</span> **{e["ticker"]}** '
                                   f'lämnade konsensus — {e["detalj"]}')
            elif e["typ"] == "UT UR NÄRA KONSENSUS":
                lista_rader.append(f'<span style="color:{RUST}">▼</span> **{e["ticker"]}** '
                                   f'lämnade nära konsensus')

        # Största viktändringarna (senaste ändringsdagen), rankade på storlek
        moves = rorelser_per_aktie(dagens)
        vikt_rader = []
        for tk, ms in sorted(moves.items()):
            grupperade = set()
            for riktning, verb, farg in ((1, "ökat", MOSS), (-1, "minskat", RUST)):
                grupp = [m for m in ms if (m["delta"] > 0) == (riktning > 0)]
                if len(grupp) >= 2:
                    antal = {2: "Två", 3: "Tre", 4: "Fyra", 5: "Fem"}.get(len(grupp), str(len(grupp)))
                    pil = "▲" if riktning > 0 else "▼"
                    storlek = max(abs(m["delta"]) for m in grupp)
                    vikt_rader.append((storlek + 100,   # sammanfallande rörelser först
                        f'<span style="color:{farg}">{pil}</span> {antal} portföljer har {verb} **{tk}**'))
                    grupperade |= {m["profil"] for m in grupp}
            for m in ms:
                if m["profil"] in grupperade or m["typ"] != "VIKTÄNDRING" or abs(m["delta"]) < 3:
                    continue
                pil = (f'<span style="color:{MOSS}">▲</span>' if m["delta"] > 0
                       else f'<span style="color:{RUST}">▼</span>')
                verb = "ökade" if m["delta"] > 0 else "minskade"
                vikt_rader.append((abs(m["delta"]),
                    f'{pil} **{m["profil"]}** {verb} **{tk}** ({_pe(m["delta"])})'))
        vikt_rader = [t for _, t in sorted(vikt_rader, key=lambda x: -x[0])][:6]

        if lista_rader or vikt_rader:
            st.divider()
            st.subheader("Senaste händelser")
            kol1, kol2 = st.columns(2)
            with kol1:
                st.markdown("**Förändringar i listorna** · senaste 30 dagarna")
                if lista_rader:
                    for rad in lista_rader[:6]:
                        st.markdown(f"- {rad}", unsafe_allow_html=True)
                else:
                    st.caption("Inga in- eller utträden den senaste månaden.")
            with kol2:
                st.markdown(f"**Största viktändringarna** · {senaste_datum}")
                if vikt_rader:
                    for rad in vikt_rader:
                        st.markdown(f"- {rad}", unsafe_allow_html=True)
                else:
                    st.caption("Inga större viktändringar senaste ändringsdagen.")
            st.caption("Fullständiga flöden finns under **II. Konsensus** och **V. Senaste ändringar**.")

# --- Konsensus ---
with tab_konsensus:
    trosklar = data.get("konsensus_trosklar") or {}
    _n = trosklar.get("n") or len(data["profiler"])
    _in_krav, _kvar_krav = trosklar.get("in"), trosklar.get("kvar")
    if _in_krav is None or _kvar_krav is None:
        _in_krav, _kvar_krav = ea.konsensus_trosklar(_n)
    st.subheader(f"Konsensusaktier — in vid {_in_krav} av {_n} portföljer "
                 f"({trosklar.get('in_pct', 60)} %), kvar vid {_kvar_krav} "
                 f"({trosklar.get('kvar_pct', 50)} %)")
    log = data.get("historik", [])
    innehav = data.get("innehav", {})
    nya_kons = nya_pa_listan(log, "IN I KONSENSUS")
    rows = []
    for tk in consensus_order:
        a = analyses.get(tk, {})
        c = claude.get(tk, {})
        h = innehav.get(tk, {})
        rows.append({
            "Bransch": bransch_ikon(tk, bransch),
            "Aktie": tk + (" · ny" if tk in nya_kons else ""),
            "Stigande trend": trend_label(a),
            "Portföljer": consensus[tk]["count"],
            "Viktad kons.": consensus[tk].get("viktad_konsensus"),
            "Senaste köp (dgr)": consensus[tk].get("senaste_köp_dagar"),
            "Total vikt (%)": consensus[tk].get("total_weight")
                or round(consensus[tk]["avg_weight"] * consensus[tk]["count"], 2),
            "Snittvikt (%)": round(consensus[tk]["avg_weight"], 2),
            "Pris": a.get("pris"),
            "RSI14": a.get("RSI14"),
            "Analytiker": a.get("rekommendation"),
            "Riktkurs": a.get("riktkurs"),
            "Uppsida (%)": a.get("uppsida_%"),
            "Ägd längst": format_innehavstid(h.get("längst_dagar")),
            "Ägd snitt": format_innehavstid(h.get("snitt_dagar")),
            "Inv. vinst (%)": h.get("snitt_vinst_pct", "—"),
            "Claude": c.get("rekommendation", "—"),
        })
    st.dataframe(stylad(pd.DataFrame(rows), ["Aktie", "Stigande trend", "Claude"]),
                 use_container_width=True, hide_index=True,
                 column_config={"Bransch": st.column_config.ImageColumn("", width=36)})
    st.caption(
        "Stigande trend = priset över MA200 **och** MA200 stigande — utan den kan Claude aldrig ge KÖP. "
        "**Viktad kons.** väger varje ägare efter hur färskt köpet är (aktivt nyköp 1,5 · "
        "6 mån 1,0 · äldre 0,5) och måste nå samma tal som antalskravet — hysteresen gäller "
        "även den. Låg viktad konsensus = gammal, passiv signal. "
        "*· ny* = ny på listan senaste 7 dagarna. "
        "**Ägd längst** = äldsta öppna positionen bland investerarna; **Inv. vinst** = deras "
        "genomsnittliga upparbetade vinst — lång tid + hög vinst = risk för vinsthemtagning."
    )
    st.caption(BRANSCH_TEXT)

    # Nära konsensus — en portfölj från att kvala in
    near = data.get("nara_konsensus", {})
    if near:
        st.divider()
        st.subheader(f"Nära konsensus — {_kvar_krav} av {_n} portföljer (under innivån {_in_krav})")
        st.caption("Bevakningslista: klarar kvarnivåns antal men har inte kvalat in — "
                   "en ägare till (eller färskare köp) tar dem över innivån.")
        nya_nara = nya_pa_listan(log, "IN I NÄRA KONSENSUS")

        def total_vikt(info):
            return info.get("total_weight") or round(info["avg_weight"] * info["count"], 2)

        near_rows = []
        for tk, info in sorted(near.items(), key=lambda x: -total_vikt(x[1])):
            h = innehav.get(tk, {})
            near_rows.append({
                "Bransch": bransch_ikon(tk, bransch),
                "Aktie": tk + (" · ny" if tk in nya_nara else ""),
                "Total vikt (%)": total_vikt(info),
                "Snittvikt (%)": round(info["avg_weight"], 2),
                "Ägs av": ", ".join(info.get("holders", [])),
                "Ägd längst": format_innehavstid(h.get("längst_dagar")),
                "Inv. vinst (%)": h.get("snitt_vinst_pct", "—"),
            })
        st.dataframe(stylad(pd.DataFrame(near_rows), ["Aktie"]),
                     use_container_width=True, hide_index=True,
                     column_config={"Bransch": st.column_config.ImageColumn("", width=36)})
        st.caption("Sorterad på total vikt — investerarnas sammanlagda portföljandel i aktien.")

    # Lämnat listorna — när investerarna kliver av
    from datetime import date as _date, timedelta as _timedelta
    lamnat_cutoff = (_date.today() - _timedelta(days=30)).isoformat()
    lamnat = [e for e in log
              if e["typ"] in ("UT UR KONSENSUS", "UT UR NÄRA KONSENSUS")
              and e["datum"] >= lamnat_cutoff]
    st.divider()
    st.subheader("Lämnat listorna — senaste 30 dagarna")
    if not lamnat:
        st.caption("Ingen aktie har lämnat konsensus eller nära konsensus den senaste månaden.")
    else:
        lamnat_rows = [{
            "Datum": e["datum"],
            "Aktie": e["ticker"],
            "Lämnade": "Konsensus" if e["typ"] == "UT UR KONSENSUS" else "Nära konsensus",
            "Detalj": e["detalj"],
        } for e in lamnat]
        st.dataframe(pd.DataFrame(lamnat_rows), use_container_width=True, hide_index=True)
        st.caption("När investerare kliver av ett värdepapper kan det vara en tidig säljsignal.")

# --- Divergens ---
with tab_diverg:
    st.subheader("Divergens — signalgruppens unika övertygelser")
    divergens = data.get("divergens", {})
    bg_antal = data.get("bakgrund_antal", 0)
    if not divergens:
        st.info("Ingen divergensdata ännu — den beräknas vid nästa datahämtning.")
    else:
        st.caption(
            f"Jämför dina 5 utvalda investerare (signalgruppen) med en bred referens av "
            f"**{bg_antal} screenade topptraders** (bakgrundsgruppen: minst 2 år på plattformen, "
            f"gain ≥ 15 % senaste året, månadsrisk ≤ 6, minst 50 kopierare). "
            f"**Hög divergens** = få i den breda gruppen äger aktien → signalgruppens egen idé. "
            f"**Låg/negativ** = flockbeteende — 'alla' äger den redan."
        )
        div_rows = []
        for tk, dv in sorted(divergens.items(), key=lambda x: -x[1]["divergens_pp"]):
            c = claude.get(tk, {})
            if dv["divergens_pp"] >= 40:
                tolk = "Unik övertygelse"
            elif dv["divergens_pp"] >= 15:
                tolk = "Viss egen idé"
            else:
                tolk = "Flockbeteende"
            div_rows.append({
                "Bransch": bransch_ikon(tk, bransch),
                "Aktie": tk,
                "Signalgrupp": f"{dv['signal_antal']}/{len(data['profiler'])} ({dv['signal_andel_pct']} %)",
                "Bakgrund": f"{dv['bakgrund_antal']}/{bg_antal} ({dv['bakgrund_andel_pct']} %)",
                "Divergens (pp)": dv["divergens_pp"],
                "Bakgrundens snittvikt (%)": dv["bakgrund_snittvikt"],
                "Tolkning": tolk,
                "Claude": c.get("rekommendation", "—"),
            })
        st.dataframe(
            stylad(pd.DataFrame(div_rows), ["Tolkning", "Claude"]),
            use_container_width=True, hide_index=True,
            column_config={
                "Bransch": st.column_config.ImageColumn("", width=36),
                "Divergens (pp)": st.column_config.ProgressColumn(
                    "Divergens (pp)", min_value=-100, max_value=100, format="%+.1f"
                ),
            },
        )
        st.caption(
            "Divergens = signalgruppens ägarandel minus bakgrundsgruppens, i procentenheter. "
            "Bakgrundsgruppen används som brusfilter — inte som köpsignal."
        )

        # Bubblare: bubblarnivån (en ägare under kvarnivån) + hög divergens
        div_nara = data.get("divergens_nara", {})
        bubbel_kalla = data.get("bubblar_niva") if "bubblar_niva" in data else data.get("nara_konsensus", {})
        bubblare = sorted(((tk, dv) for tk, dv in div_nara.items() if dv["divergens_pp"] >= 30),
                          key=lambda x: (-x[1]["divergens_pp"],
                                         -(bubbel_kalla.get(x[0], {}).get("total_weight") or 0)))
        st.divider()
        st.subheader("Bubblare — nära att kvala in, med hög divergens")
        tr = data.get("konsensus_trosklar") or {}
        st.caption(
            f"Aktier som ägs av {max((tr.get('kvar') or 3) - 1, 1)} av dina "
            f"{tr.get('n', len(data.get('profiler', [])))} investerare men som flocken "
            "i stort sett inte äger (divergens ≥ +30 pp). Fler ägare tar dem uppåt "
            "i nivåerna — och då är dina utvalda tidiga, inte sena."
        )
        if not bubblare:
            st.caption("Inga bubblare just nu — aktierna på bubblarnivån ägs redan brett av flocken.")
        else:
            nya_nara_b = nya_pa_listan(data.get("historik", []), "IN I NÄRA KONSENSUS")
            bubbel_rows = []
            for tk, dv in bubblare:
                info = bubbel_kalla.get(tk, {})
                bubbel_rows.append({
                    "Bransch": bransch_ikon(tk, bransch),
                    "Aktie": tk + (" · ny" if tk in nya_nara_b else ""),
                    "Ägs av": ", ".join(info.get("holders", [])),
                    "Total vikt (%)": info.get("total_weight"),
                    "Bakgrund": f"{dv['bakgrund_antal']}/{data.get('bakgrund_antal', '?')} "
                                f"({dv['bakgrund_andel_pct']} %)",
                    "Divergens (pp)": dv["divergens_pp"],
                })
            st.dataframe(stylad(pd.DataFrame(bubbel_rows), ["Aktie"]),
                         use_container_width=True, hide_index=True,
                         column_config={"Bransch": st.column_config.ImageColumn("", width=36)})

# --- Claudes analys ---
with tab_analys:
    st.subheader("Claudes tekniska analys per aktie")
    if not claude:
        st.info("Ingen Claude-analys i senaste körningen. Bocka i rutan i sidopanelen och kör igen.")
    for tk in consensus_order:
        a = analyses.get(tk, {})
        c = claude.get(tk)
        rek = (c or {}).get("rekommendation")
        with st.expander(f"**{tk}** — {rek or 'ingen Claude-analys'}", expanded=False):
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Pris", a.get("pris"))
            m2.metric("RSI14", a.get("RSI14"))
            m3.metric("MA200", a.get("MA200"))
            uppsida = a.get("uppsida_%")
            m4.metric("Uppsida", f"{uppsida} %" if uppsida is not None else "—")
            m5.metric("Stigande trend", trend_label(a))

            i1, i2, i3, i4 = st.columns(4)
            i1.markdown(f"Golden cross: {mark(a.get('golden_cross'))}", unsafe_allow_html=True)
            i2.markdown(f"MACD över signal: {mark(a.get('MACD_över_signal'))}", unsafe_allow_html=True)
            i3.markdown(f"1 mån: {a.get('avkastning_1m_%', '—')} %  ·  3 mån: {a.get('avkastning_3m_%', '—')} %")
            i4.markdown(f"Från 52v-toppen: {a.get('avstånd_52v_högsta_%', '—')} %")

            epsr = a.get("eps_rev_90d_pct")
            if epsr is not None:
                farg = MOSS if epsr > 5 else (RUST if epsr < -5 else MUTED)
                rikt = "stigande" if epsr > 5 else ("fallande" if epsr < -5 else "stabila")
                st.markdown(f"EPS-estimat 90 dgr: <span style='color:{farg}'>{epsr:+.1f} % "
                            f"({rikt})</span>", unsafe_allow_html=True)

            if a.get("datakälla") == "cache":
                st.caption(f"Obs: marknadsdata från tidigare körning ({a.get('cache_datum', 'okänt')}) "
                           "— datakällorna svarade inte just nu.")

            ohlc = a.get("ohlc")
            if ohlc:
                st.altair_chart(candlestick(ohlc), use_container_width=True)
                st.caption(f"Dagskurser senaste ~90 handelsdagarna · "
                           f"<span style='color:{SAND}'>—</span> MA50 · "
                           f"<span style='color:{OLIV}'>—</span> MA200", unsafe_allow_html=True)

            h = innehav.get(tk, {})
            if h:
                vinst = h.get("snitt_vinst_pct")
                st.markdown(
                    f"Ägd längst: **{format_innehavstid(h.get('längst_dagar'))}** "
                    f"(av {h.get('längst_profil', '?')}) · snitt: "
                    f"**{format_innehavstid(h.get('snitt_dagar'))}** · "
                    f"upparbetad snittvinst: **{vinst if vinst is not None else '—'} %**"
                )
                per = h.get("per_profil", {})
                if per:
                    per_rows = [{
                        "Investerare": prof,
                        "Ägt i": format_innehavstid(v["dagar"]),
                        "Upparbetad vinst (%)": v.get("vinst_pct", "—"),
                    } for prof, v in sorted(per.items(), key=lambda x: -x[1]["dagar"])]
                    st.dataframe(pd.DataFrame(per_rows), hide_index=True)

            if c:
                st.markdown("---")
                st.markdown(c["analys"])
                if c.get("genererad"):
                    st.caption(f"Analys genererad: {c['genererad']}")

# --- Senaste ändringar ---
with tab_andringar:
    st.subheader("Senaste ändringar i portföljerna")
    log = data.get("historik", [])
    if not log:
        st.info(
            "Inga ändringar registrerade ännu. När en investerare tar in eller säljer "
            "en aktie dyker det upp här efter nästa körning."
        )
    else:
        senaste_datum = log[0]["datum"]
        dagens = [e for e in log if e["datum"] == senaste_datum]
        st.caption(f"Ändringar registrerade {senaste_datum}:")

        STOR_ANDRING = 2.0   # procentenheter — gräns för "stor viktändring"
        moves = rorelser_per_aktie(dagens)
        agare = {tk: sum(1 for p in data["portfolios"].values() if tk in p) for tk in moves}

        samman, stora, mindre = [], [], []
        for tk, ms in sorted(moves.items()):
            grupperade_profiler = set()
            for riktning, verb, farg in ((1, "ökat", MOSS), (-1, "minskat", RUST)):
                grupp = [m for m in ms if (m["delta"] > 0) == (riktning > 0)]
                if len(grupp) >= 2:
                    antal = {2: "Två", 3: "Tre", 4: "Fyra", 5: "Fem"}.get(len(grupp), str(len(grupp)))
                    vem = ", ".join(f"{m['profil']} ({_pe(m['delta'])})" for m in grupp)
                    pil = "▲" if riktning > 0 else "▼"
                    samman.append(f'<span style="color:{farg}">{pil}</span> **{antal} portföljer har {verb} {tk}** — {vem}')
                    grupperade_profiler |= {m["profil"] for m in grupp}
            for m in ms:
                if m["profil"] in grupperade_profiler or m["typ"] != "VIKTÄNDRING":
                    continue   # in-/utsålda visas i sektionen nedan
                if abs(m["delta"]) >= STOR_ANDRING:
                    verb = "ökat" if m["delta"] > 0 else "minskat"
                    pil = (f'<span style="color:{MOSS}">▲</span>' if m["delta"] > 0
                           else f'<span style="color:{RUST}">▼</span>')
                    stora.append(f"{pil} **{m['profil']}** har {verb} **{tk}** "
                                 f"{'kraftigt' if abs(m['delta']) >= 4 else 'tydligt'}: "
                                 f"{m['detalj']} ({_pe(m['delta'])})")
                elif agare.get(tk, 0) > 1:
                    # små ändringar visas bara för aktier som flera portföljer äger
                    mindre.append(f"{tk} ({m['profil']} {_pe(m['delta'])})")

        if samman:
            st.markdown("#### Sammanfallande rörelser")
            st.caption("Flera investerare har rört samma aktie åt samma håll — starkaste signalen.")
            for rad in samman:
                st.markdown(f"- {rad}", unsafe_allow_html=True)
        if stora:
            st.markdown("#### Stora viktändringar")
            for rad in stora:
                st.markdown(f"- {rad}", unsafe_allow_html=True)
        if mindre:
            st.markdown(f"*Mindre justeringar i gemensamt ägda aktier: {' · '.join(mindre)}*")
        if not (samman or stora or mindre):
            st.markdown("*Inga betydande viktrörelser sedan förra körningen.*")

        st.divider()
        intag = [e for e in dagens if e["typ"] in ("NYTT INNEHAV", "IN I KONSENSUS")]
        utsalt = [e for e in dagens if e["typ"] in ("SÅLT INNEHAV", "UT UR KONSENSUS")]
        col_in, col_ut = st.columns(2)
        with col_in:
            st.markdown(f'#### <span style="color:{MOSS}">▲</span> Intaget', unsafe_allow_html=True)
            if not intag:
                st.caption("Inga nya innehav.")
            for e in intag:
                vem = f" hos **{e['profil']}**" if e["profil"] else " (konsensus)"
                st.markdown(f"- **{e['ticker']}**{vem} — {e['detalj']}")
        with col_ut:
            st.markdown(f'#### <span style="color:{RUST}">▼</span> Utsålt', unsafe_allow_html=True)
            if not utsalt:
                st.caption("Inga sålda innehav.")
            for e in utsalt:
                vem = f" hos **{e['profil']}**" if e["profil"] else " (konsensus)"
                st.markdown(f"- **{e['ticker']}**{vem} — {e['detalj']}")

        with st.expander("Alla dagens ändringar i detalj"):
            df = pd.DataFrame(dagens).rename(columns={
                "datum": "Datum", "typ": "Typ", "profil": "Profil",
                "ticker": "Aktie", "detalj": "Detalj"})
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption("Hela loggen över alla körningar finns under fliken **VI. Historik**.")

# --- Historik ---
with tab_historik:
    st.subheader("Ändringar mellan körningar")
    log = data.get("historik", [])
    if not log:
        st.info("Inga ändringar loggade ännu — historiken fylls på från och med nästa körning.")
    else:
        df = pd.DataFrame(log).rename(columns={
            "datum": "Datum", "typ": "Typ", "profil": "Profil",
            "ticker": "Aktie", "detalj": "Detalj",
        })
        typer = ["Alla"] + sorted(df["Typ"].unique())
        val = st.selectbox("Filtrera på typ", typer)
        if val != "Alla":
            df = df[df["Typ"] == val]
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- Portföljer ---
with tab_portfoljer:
    st.subheader("Innehav per profil")
    profil = st.selectbox("Välj profil", data["profiler"])
    positions = data["portfolios"][profil]
    df = pd.DataFrame(
        sorted(positions.items(), key=lambda x: -x[1]),
        columns=["Aktie", "Vikt (%)"],
    )
    col1, col2 = st.columns([1, 2])
    with col1:
        st.dataframe(df, use_container_width=True, hide_index=True, height=500)
    with col2:
        st.bar_chart(df.set_index("Aktie").head(15), color=MOSS)
        st.caption("De 15 största innehaven.")

# ----------------------------------------------------------------------
# Sidfot (ol.studio-inspirerad)
# ----------------------------------------------------------------------
from datetime import date as _date_fot

st.markdown(
    f"""
    <div class="appfot">
      <span>I. Bästa köp — VII. Portföljer</span>
      <span class="mitt">eToro Portföljanalys — All Rights Reserved © {_date_fot.today().year}</span>
      <span>Data: eToro · Yahoo Finance &nbsp;·&nbsp; Analys: Claude</span>
    </div>
    """,
    unsafe_allow_html=True,
)
