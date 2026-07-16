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
                   page_icon=":material/monitoring:", layout="wide",
                   initial_sidebar_state="collapsed")

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
# Redaktionellt designsystem (ol.studio / ofricolada-inspirerat):
# serif-display, små mono-etiketter, centrerad kolumn, hårfina linjer.
# ----------------------------------------------------------------------
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400;1,6..72,500&family=Space+Grotesk:wght@400;500&display=swap');

  /* Centrerad redaktionell kolumn med generös luft */
  [data-testid="stMainBlockContainer"], .block-container {{
      max-width: 940px !important; padding-top: 3.2rem !important; padding-bottom: 2rem !important; }}

  /* Typografi: serif-display i rubriker, resten grotesk */
  h1, h2, h3, h4 {{ font-family: 'Newsreader', Georgia, serif !important;
      font-weight: 400 !important; letter-spacing: -.01em; }}

  hr {{ margin: 1.3rem 0 !important; border: none !important;
        border-top: 1px solid {HAIRLINE} !important; }}

  /* ---- Hjälte: Bästa köp ---- */
  .hero-label {{ font-family: 'Space Grotesk', sans-serif; text-transform: uppercase;
      letter-spacing: .24em; font-size: .68rem; color: {MUTED}; margin-bottom: .5rem; }}
  .hero-title {{ font-family: 'Newsreader', serif; font-size: 3.4rem; line-height: 1;
      letter-spacing: -.025em; color: {TEXT}; margin: 2.4rem 0 .55rem; }}
  .hero-sub {{ font-family: 'Space Grotesk', sans-serif; font-size: .8rem; color: {MUTED};
      letter-spacing: .01em; margin-bottom: 1.7rem; max-width: 34rem; line-height: 1.5; }}

  .stocklist {{ margin: .2rem 0 .5rem; }}
  .stock {{ border-top: 1px solid {HAIRLINE}; }}
  .stock:last-child {{ border-bottom: 1px solid {HAIRLINE}; }}
  .stoggle {{ position: absolute; opacity: 0; width: 0; height: 0; pointer-events: none; }}
  .rad {{ display: flex; align-items: center; gap: 1.1rem; padding: 1.15rem .3rem;
      cursor: pointer; transition: padding-left .28s ease; }}
  .stock:hover .rad {{ padding-left: .95rem; }}
  .rang {{ font-family: 'Space Grotesk', sans-serif; font-size: .76rem; color: {MUTED};
      width: 1.7rem; flex: 0 0 auto; }}
  .bikon {{ width: 24px; height: 24px; opacity: .72; flex: 0 0 auto; }}
  .tk {{ font-family: 'Newsreader', serif; font-size: 1.55rem; color: {TEXT};
      min-width: 5.5rem; flex: 0 0 auto; }}
  .meter {{ flex: 1 1 auto; height: 2px; background: {HAIRLINE}; position: relative; min-width: 50px; }}
  .meter .fill {{ position: absolute; inset: 0 auto 0 0; height: 100%; background: {TEXT}; }}
  .poang {{ font-family: 'Space Grotesk', sans-serif; font-size: 1rem; color: {TEXT};
      width: 3.1rem; text-align: right; flex: 0 0 auto; }}
  .crek {{ font-family: 'Space Grotesk', sans-serif; font-size: .66rem; text-transform: uppercase;
      letter-spacing: .14em; width: 5.2rem; text-align: right; flex: 0 0 auto; }}
  .trend {{ width: 1rem; text-align: center; font-size: .78rem; flex: 0 0 auto; }}

  .detalj {{ max-height: 0; overflow: hidden; opacity: 0;
      transition: max-height .5s cubic-bezier(.4,0,.2,1), opacity .4s ease; }}
  .stock:hover .detalj, .stoggle:checked ~ .detalj {{ max-height: 560px; opacity: 1; }}
  .detalj-inner {{ padding: .1rem .3rem 1.7rem 3.9rem; }}
  .nyckeltal {{ display: flex; flex-wrap: wrap; gap: 2.4rem; margin-bottom: 1.4rem; }}
  .nyckeltal .lbl {{ display: block; font-family: 'Space Grotesk', sans-serif; font-size: .62rem;
      text-transform: uppercase; letter-spacing: .12em; color: {MUTED}; margin-bottom: .25rem; }}
  .nyckeltal .val {{ font-family: 'Newsreader', serif; font-size: 1.4rem; color: {TEXT}; }}
  .delpoang {{ display: flex; flex-direction: column; gap: .5rem; max-width: 440px; }}
  .dp {{ display: flex; align-items: center; gap: .9rem;
      font-family: 'Space Grotesk', sans-serif; font-size: .72rem; }}
  .dp .dplbl {{ width: 5rem; color: {TEXT}; flex: 0 0 auto; }}
  .dp .dpbar {{ flex: 1 1 auto; height: 2px; background: {HAIRLINE}; position: relative; }}
  .dp .dpbar span {{ position: absolute; inset: 0 auto 0 0; height: 100%; background: {OLIV}; }}
  .dp .dpval {{ width: 3rem; text-align: right; color: {MUTED}; flex: 0 0 auto; }}
  .detalj .meta {{ margin-top: 1.1rem; font-family: 'Space Grotesk', sans-serif;
      font-size: .68rem; letter-spacing: .03em; color: {MUTED}; }}

  /* ---- Diskret, numrerat dragspel för övriga vyer ---- */
  [data-testid="stMainBlockContainer"] [data-testid="stExpander"] {{ border: none !important; }}
  [data-testid="stMainBlockContainer"] [data-testid="stExpander"] details {{
      border: none !important; border-top: 1px solid {HAIRLINE} !important;
      border-radius: 0 !important; background: transparent !important; }}
  [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary {{
      padding: 1.15rem .2rem !important; font-family: 'Space Grotesk', sans-serif !important;
      text-transform: uppercase; letter-spacing: .16em; font-size: .74rem; color: {TEXT}; }}
  [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary:hover {{ color: {OLIV}; }}

  /* sidfoten */
  .appfot {{ display: flex; justify-content: space-between; flex-wrap: wrap;
      gap: .5rem 2rem; margin: 3.5rem 0 1rem; padding-top: 1rem;
      border-top: 1px solid {HAIRLINE}; color: {MUTED};
      font-family: 'Space Grotesk', sans-serif; font-size: .72rem; letter-spacing: .06em;
      text-transform: uppercase; }}
  .appfot .mitt {{ text-align: center; text-transform: none; letter-spacing: .02em; }}
  .appfot-sub {{ text-align: center; color: {MUTED}; font-family: 'Space Grotesk', sans-serif;
      font-size: .66rem; letter-spacing: .07em; text-transform: uppercase; margin: .5rem 0 1.6rem; }}

  /* --- Sidopanelen är dold; ersatt av diskret toppnavigering --- */
  section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{
      display: none !important; }}

  /* --- Diskret toppnavigering --- */
  .wordmark {{ font-family: 'Newsreader', serif; font-size: 1.2rem; color: {TEXT};
      letter-spacing: .01em; padding-top: .4rem; }}
  .dateline {{ font-family: 'Space Grotesk', sans-serif; font-size: .64rem; text-transform: uppercase;
      letter-spacing: .16em; color: {MUTED}; margin: .2rem 0 2.6rem; }}
  hr.navhr {{ margin: .8rem 0 0 !important; }}

  /* Diskreta, textlika knappar/popover/nedladdning i huvudytan */
  [data-testid="stMainBlockContainer"] .stButton > button,
  [data-testid="stMainBlockContainer"] [data-testid="stDownloadButton"] > button,
  [data-testid="stMainBlockContainer"] [data-testid="stPopover"] button {{
      background: transparent !important; border: none !important; box-shadow: none !important;
      color: {MUTED} !important; font-family: 'Newsreader', Georgia, serif !important;
      font-weight: 400 !important; font-size: .84rem !important; text-transform: none;
      letter-spacing: .01em; white-space: nowrap; border-radius: 0 !important;
      padding: .3rem .3rem !important; min-height: 0 !important; }}
  [data-testid="stMainBlockContainer"] .stButton > button:hover,
  [data-testid="stMainBlockContainer"] [data-testid="stDownloadButton"] > button:hover,
  [data-testid="stMainBlockContainer"] [data-testid="stPopover"] button:hover {{
      color: {OLIV} !important; }}
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


def _num(v, suf="", dec=1):
    """Svenskt tal med enhet, eller '—' vid null."""
    return "—" if v is None else f"{v:.{dec}f}{suf}".replace(".", ",")


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


def _sv1(v):
    """Ett tal med svensk decimal, en decimal (för poäng i hjälten)."""
    return f"{v:.1f}".replace(".", ",")


def hero_html(ranking, claude_map, consensus_map, bransch_map, komp_max):
    """Bästa köp som redaktionell hover/klick-lista (ren HTML/CSS, inga widgets).

    Varje aktie visar bara ticker, poängmätare och Claude-rek; detaljerna
    (nyckeltal + poänguppdelning) fälls ut på hover eller klick via CSS.
    """
    rek_farg = {"KÖP": MOSS, "AVVAKTA": SAND, "SÄLJ": RUST}
    rader = []
    for i, r in enumerate(ranking, start=1):
        tk = r["ticker"]
        poang = r["poäng"]
        crek = (claude_map.get(tk) or {}).get("rekommendation", "—")
        farg = rek_farg.get(crek, MUTED)
        if r["trend_ok"]:
            trendmark = f'<span class="trend" style="color:{MOSS}">▲</span>'
        else:
            trendmark = f'<span class="trend" style="color:{RUST}">▼</span>'
        ikon = bransch_ikon(tk, bransch_map)
        img = f'<img class="bikon" src="{ikon}">' if ikon else '<span class="bikon"></span>'

        rs = r.get("relativ_styrka") or {}
        kluster = r.get("kluster") or {}
        vk = consensus_map.get(tk, {}).get("viktad_konsensus")
        nyckel = [
            ("Föreslagen vikt", _num(r.get("foreslagen_vikt_%"), " %")),
            ("Viktad kons.", _num(vk)),
            ("Nettoflöde 30d", _num(r.get("nettoflode_30d_pe"), " pe")),
            ("Rel. styrka", _num(rs.get("rs_pe"), " pe")),
        ]
        nyckel_html = "".join(
            f'<div><span class="lbl">{lbl}</span><span class="val">{val}</span></div>'
            for lbl, val in nyckel)

        dp_html = ""
        for namn, mx in komp_max.items():
            v = r["delpoäng"].get(namn)
            if v is None:
                continue
            pct = min(max(v / mx, 0.0), 1.0) * 100
            dp_html += (f'<div class="dp"><span class="dplbl">{namn}</span>'
                        f'<span class="dpbar"><span style="width:{pct:.0f}%"></span></span>'
                        f'<span class="dpval">{v:.0f}/{mx}</span></div>')

        if kluster.get("klusterstorlek", 1) > 1:
            kl = f"Kluster #{kluster['kluster_id']} ({kluster['klusterstorlek']} samvarierande)"
        else:
            kl = "Kluster: ensam"
        meta = f"Poäng v1: {_num(r.get('poäng_v1'))} · {kl}"

        rader.append(
            f'<div class="stock">'
            f'<input type="checkbox" id="st_{tk}" class="stoggle">'
            f'<label class="rad" for="st_{tk}">'
            f'<span class="rang">{i:02d}</span>{img}'
            f'<span class="tk">{tk}</span>'
            f'<span class="meter"><span class="fill" style="width:{poang:.0f}%"></span></span>'
            f'<span class="poang">{_sv1(poang)}</span>'
            f'<span class="crek" style="color:{farg}">{crek}</span>{trendmark}'
            f'</label>'
            f'<div class="detalj"><div class="detalj-inner">'
            f'<div class="nyckeltal">{nyckel_html}</div>'
            f'<div class="delpoang">{dp_html}</div>'
            f'<div class="meta">{meta}</div>'
            f'</div></div></div>')
    return f'<div class="stocklist">{"".join(rader)}</div>'


# ----------------------------------------------------------------------
# Diskret toppnavigering (ersätter sidopanelen)
# ----------------------------------------------------------------------
def data_ar_fran_idag(d):
    from datetime import date
    if not d:
        return False
    if date.today().weekday() in (5, 6):
        return True   # helg: marknaden stängd, befintlig data är per definition färsk
    return d.get("tidpunkt", "")[:10] == date.today().isoformat()


nav_l, nav_r = st.columns([4, 6], vertical_alignment="center")
with nav_l:
    st.markdown('<div class="wordmark">eToro Portföljanalys</div>', unsafe_allow_html=True)
with nav_r:
    n1, n2, n3, n4 = st.columns(4)
    run_now = n1.button("Uppdatera", use_container_width=True)
    with n2.popover("Claude", use_container_width=True):
        with_claude = st.checkbox(
            "Inkludera Claude-analys", value=True,
            help="Claude körs max en gång per dag (drar API-credits) — annars återanvänds dagens analys.",
        )
        force_claude = st.checkbox(
            "Tvinga om Claude-analysen", value=False,
            help="Kör Claude igen även om den redan körts idag. Drar credits!",
        )
    with n3.popover("Bakgrund", use_container_width=True):
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
            st.error(str(e))

data = load_results()

if data:
    # Se till att Excel-filen finns/matchar senaste analysen; lägg nedladdningen
    # i navens sista kolumn (n4).
    behov_regen = not os.path.exists(ea.OUTPUT_FILE)
    if not behov_regen and os.path.exists(ea.RESULTS_FILE):
        behov_regen = os.path.getmtime(ea.OUTPUT_FILE) < os.path.getmtime(ea.RESULTS_FILE)
    if behov_regen:
        try:
            ea.excel_from_result(data)
        except Exception as e:
            st.caption(f"Kunde inte skapa Excel-rapporten: {e}")
    if os.path.exists(ea.OUTPUT_FILE):
        with open(ea.OUTPUT_FILE, "rb") as f:
            n4.download_button(
                "Excel", f.read(), file_name=ea.OUTPUT_FILE,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

st.markdown('<hr class="navhr">', unsafe_allow_html=True)

if data:
    # Visa datafel diskret (t.ex. om Yahoo Finance blockerar serverns anrop)
    fel = {t: a["error"] for t, a in data.get("analyses", {}).items() if "error" in a}
    if fel:
        with st.popover(f":material/warning: {len(fel)} aktier saknar marknadsdata"):
            for t, e in fel.items():
                st.caption(f"**{t}**: {e}")

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

ranking = data.get("ranking", [])
KOMP_MAX = {"Trend": 25, "Momentum": 20, "Analytiker": 20,
            "Konsensus": 25, "Värdering": 10}

# ======================================================================
# HJÄLTE — Bästa köp (redaktionell hover/klick-lista)
# ======================================================================
st.markdown(
    '<div class="hero-title">Bästa köp</div>'
    '<div class="hero-sub">Sammanvägd poäng 0–100. Håll muspekaren över eller klicka '
    'på en aktie för poänguppdelning och nyckeltal.</div>',
    unsafe_allow_html=True,
)

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

    st.markdown(hero_html(ranking, claude, consensus, bransch, KOMP_MAX), unsafe_allow_html=True)

    with st.popover("Så räknas poängen"):
        st.caption(
            "**Poängmodellen (§12, omviktad):** Trend 25 p · Momentum 20 p (inkl. relativ "
            "styrka mot sektor-ETF) · Analytiker 20 p (uppsida — halverad vid hög "
            "riktkursspridning — antal analytiker, köprekommendation, EPS-revidering) · "
            "Konsensus 25 p (viktad konsensus, snittvikt, nettoflöde 30d) — delat med "
            "√klusterstorlek om aktien samvarierar starkt (korr > 0,7) med andra "
            "konsensusaktier · Värdering 10 p (forward P/E mot sektormedian, PEG). "
            "**Poäng v1** är förra modellen (utan Värdering/RS/spridning) — kvar för "
            "jämförelse tills --utvardera hunnit kalibrera de nya vikterna. "
            "Aktier utan stigande trend rankas alltid sist, oavsett poäng."
        )

# ======================================================================
# Senaste händelser — kondenserad översikt direkt under hjälten
# ======================================================================
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
        st.caption("Fullständiga flöden finns under **Konsensus** och **Senaste ändringar** nedan.")

# ======================================================================
# Övriga vyer — diskret, numrerat dragspel (klickas fram)
# ======================================================================
st.markdown('<div class="hero-label" style="margin-top:2.6rem">Fördjupning</div>',
            unsafe_allow_html=True)
innehav = data.get("innehav", {})

with st.expander("I · Konsensus"):
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
    def _total_vikt(info):
        return info.get("total_weight") or round(info["avg_weight"] * info["count"], 2)

    # Slimmad översikt — klicka en rad för detaljerna (renderas under tabellen).
    rows = []
    for tk in consensus_order:
        a = analyses.get(tk, {})
        rows.append({
            "Bransch": bransch_ikon(tk, bransch),
            "Aktie": tk + (" · ny" if tk in nya_kons else ""),
            "Stigande trend": trend_label(a),
            "Portföljer": consensus[tk]["count"],
            "Total vikt (%)": _total_vikt(consensus[tk]),
            "Analytiker": a.get("rekommendation"),
            "Claude": claude.get(tk, {}).get("rekommendation", "—"),
        })
    val = st.dataframe(
        stylad(pd.DataFrame(rows), ["Aktie", "Stigande trend", "Claude"]),
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="kons_val",
        column_config={"Bransch": st.column_config.ImageColumn("", width=36)})

    # Detaljkort för den markerade raden — konsensussignal, teknik, innehavstid.
    markerade = val.selection.rows
    if not markerade:
        st.caption("Klicka på en rad ovan för konsensussignal, teknik, analytiker och innehavstid.")
    else:
        tk = consensus_order[markerade[0]]
        info = consensus[tk]
        a = analyses.get(tk, {})
        c = claude.get(tk, {})
        h = innehav.get(tk, {})
        crek = c.get("rekommendation", "—")
        st.markdown(f"#### {tk} — {info['count']} portföljer · "
                    f"trend {trend_label(a)} · Claude {crek}")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total vikt", _num(_total_vikt(info), " %"))
        k2.metric("Viktad kons.", _num(info.get("viktad_konsensus")))
        k3.metric("Senaste köp", _num(info.get("senaste_köp_dagar"), " dgr", 0))
        k4.metric("Snittvikt", _num(info.get("avg_weight"), " %"))

        if "error" in a:
            st.caption(f"Marknadsdata saknas: {a['error']}")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Pris", _num(a.get("pris")))
            m2.metric("RSI14", _num(a.get("RSI14")))
            m3.metric("Riktkurs", _num(a.get("riktkurs")))
            m4.metric("Uppsida", _num(a.get("uppsida_%"), " %"))

        holders = info.get("holders", [])
        if holders:
            st.caption("Ägs av: " + ", ".join(holders))
        if h:
            st.caption(
                f"Ägd längst: **{format_innehavstid(h.get('längst_dagar'))}** "
                f"(av {h.get('längst_profil', '?')}) · snitt "
                f"**{format_innehavstid(h.get('snitt_dagar'))}** · upparbetad "
                f"snittvinst **{_num(h.get('snitt_vinst_pct'), ' %')}** — lång tid + "
                f"hög vinst = risk för vinsthemtagning."
            )

    st.caption(
        "**Stigande trend** = priset över MA200 **och** MA200 stigande — utan den kan "
        "Claude aldrig ge KÖP. **Viktad kons.** väger varje ägare efter hur färskt köpet "
        "är (aktivt nyköp 1,5 · 6 mån 1,0 · äldre 0,5) och måste nå samma tal som "
        "antalskravet — hysteresen gäller även den. Låg viktad konsensus = gammal, passiv "
        "signal. *· ny* = ny på listan senaste 7 dagarna. **Ägd längst** = äldsta öppna "
        "positionen bland investerarna; **upparbetad snittvinst** = deras genomsnittliga "
        "vinst — lång tid + hög vinst = risk för vinsthemtagning."
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

        near_rows = []
        for tk, info in sorted(near.items(), key=lambda x: -_total_vikt(x[1])):
            h = innehav.get(tk, {})
            near_rows.append({
                "Bransch": bransch_ikon(tk, bransch),
                "Aktie": tk + (" · ny" if tk in nya_nara else ""),
                "Total vikt (%)": _total_vikt(info),
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

with st.expander("II · Divergens"):
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

with st.expander("III · Claudes analys"):
    st.subheader("Claudes tekniska analys per aktie")
    if not claude:
        st.info("Ingen Claude-analys i senaste körningen. Bocka i rutan i sidopanelen och kör igen.")
    elif not consensus_order:
        st.caption("Inga konsensusaktier att analysera just nu.")
    else:
        tk = st.selectbox(
            "Välj aktie", consensus_order, key="claude_sel",
            format_func=lambda t: f"{t} — {(claude.get(t) or {}).get('rekommendation', 'ingen analys')}")
        a = analyses.get(tk, {})
        c = claude.get(tk)

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

with st.expander("IV · Senaste ändringar"):
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

        st.markdown("**Alla dagens ändringar**")
        df = pd.DataFrame(dagens).rename(columns={
            "datum": "Datum", "typ": "Typ", "profil": "Profil",
            "ticker": "Aktie", "detalj": "Detalj"})
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption("Hela loggen över alla körningar finns under **Historik** nedan.")

with st.expander("V · Historik"):
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

with st.expander("VI · Portföljer"):
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

_cd = data.get("claude_datum")
_dl = f"Data {data['tidpunkt'].replace('T', ' kl. ')}" + (f" · Claude {_cd}" if _cd else "")
st.markdown(
    f"""
    <div class="appfot">
      <span>{_dl}</span>
      <span class="mitt">eToro Portföljanalys — All Rights Reserved © {_date_fot.today().year}</span>
      <span>Data: eToro · Yahoo Finance &nbsp;·&nbsp; Analys: Claude</span>
    </div>
    <div class="appfot-sub">Bevakar {" · ".join(ea.PROFILES)}</div>
    """,
    unsafe_allow_html=True,
)
