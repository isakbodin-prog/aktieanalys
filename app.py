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

st.set_page_config(page_title="eToro Portföljanalys", page_icon="📈", layout="wide")

# ----------------------------------------------------------------------
# Lösenordsskydd — aktivt bara när APP_PASSWORD är satt (t.ex. på Render).
# Utan det kan vem som helst som hittar sidan trigga API-anrop.
# ----------------------------------------------------------------------
APP_PASSWORD = os.environ.get("APP_PASSWORD")
if APP_PASSWORD and not st.session_state.get("auth_ok"):
    st.title("🔒 eToro Portföljanalys")
    pwd = st.text_input("Lösenord", type="password")
    if pwd:
        if pwd == APP_PASSWORD:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Fel lösenord.")
    st.stop()


def load_results():
    if os.path.exists(ea.RESULTS_FILE):
        with open(ea.RESULTS_FILE) as f:
            return json.load(f)
    return None


def trend_label(a):
    t = a.get("stigande_trend")
    if t is None:
        return "❓"
    return "✅ JA" if t else "❌ NEJ"


def ja_nej(value):
    if value is None:
        return "❓"
    return "✅" if value else "❌"


def format_innehavstid(dagar):
    if dagar is None:
        return "—"
    return f"{dagar} dagar" if dagar < 90 else f"{dagar / 365:.1f} år"


def nya_pa_listan(log, typ, dagar=7):
    """Tickers som fått en '{typ}'-loggpost de senaste `dagar` dagarna."""
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=dagar)).isoformat()
    return {e["ticker"] for e in log if e["typ"] == typ and e["datum"] >= cutoff}


# ----------------------------------------------------------------------
# Sidopanel
# ----------------------------------------------------------------------
st.sidebar.title("📈 eToro Portföljanalys")
st.sidebar.caption("Profiler som bevakas:")
for p in ea.PROFILES:
    st.sidebar.markdown(f"- {p}")
st.sidebar.divider()

with_claude = st.sidebar.checkbox(
    "Inkludera Claude-analys", value=True,
    help="Claude körs max en gång per dag (drar API-credits) — annars återanvänds dagens analys.",
)
force_claude = st.sidebar.checkbox(
    "Tvinga om Claude-analysen", value=False,
    help="Kör Claude igen även om den redan körts idag. Drar credits!",
)

def data_ar_fran_idag(d):
    from datetime import date
    return bool(d) and d.get("tidpunkt", "")[:10] == date.today().isoformat()


run_now = st.sidebar.button("🔄 Uppdatera nu", type="primary", use_container_width=True)

# Vid sidöppning: hämta bara om dagens data saknas. Ingen daytrading här —
# en körning per dag räcker, och det sparar både väntetid och API-kvoter.
if "auto_check" not in st.session_state:
    st.session_state["auto_check"] = True
    befintlig = load_results()
    if befintlig is None:
        ea.gist_pull()          # kallstart på Render: hämta senaste från gisten
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
    st.sidebar.caption(f"Portföljdata: {data['tidpunkt'].replace('T', ' kl. ')} "
                       "(hämtas automatiskt en gång per dag)")
    cd = data.get("claude_datum")
    st.sidebar.caption(f"🤖 Claude-analys från: {cd}" if cd else "🤖 Ingen Claude-analys ännu")

    # Visa datafel tydligt (t.ex. om Yahoo Finance blockerar serverns anrop)
    fel = {t: a["error"] for t, a in data.get("analyses", {}).items() if "error" in a}
    if fel:
        with st.sidebar.expander(f"⚠️ {len(fel)} aktier saknar marknadsdata"):
            for t, e in fel.items():
                st.caption(f"**{t}**: {e}")
    if os.path.exists(ea.OUTPUT_FILE):
        with open(ea.OUTPUT_FILE, "rb") as f:
            st.sidebar.download_button(
                "⬇️ Ladda ner Excel-rapport", f.read(),
                file_name=ea.OUTPUT_FILE,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

# ----------------------------------------------------------------------
# Huvudinnehåll
# ----------------------------------------------------------------------
if not data:
    st.title("📈 eToro Portföljanalys")
    st.info("Ingen analys har körts ännu. Klicka på **Kör ny analys** i sidopanelen för att komma igång.")
    st.stop()

consensus = data["consensus"]
analyses = data["analyses"]
claude = data.get("claude", {})
consensus_order = sorted(consensus, key=lambda t: (-consensus[t]["count"], -consensus[t]["avg_weight"]))

tab_rang, tab_konsensus, tab_analys, tab_andringar, tab_historik, tab_portfoljer = st.tabs(
    ["🏆 Bästa köp", "🎯 Konsensus", "🤖 Claudes analys", "🔄 Senaste ändringar",
     "📜 Historik", "💼 Portföljer"]
)

# --- Rangordning ---
with tab_rang:
    st.subheader("Rangordning — sammanvägd poäng (0–100)")
    ranking = data.get("ranking", [])
    if not ranking:
        st.info("Ingen rangordning i senaste körningen — kör en ny analys.")
    else:
        rows = []
        for i, r in enumerate(ranking, start=1):
            d = r["delpoäng"]
            c = claude.get(r["ticker"], {})
            rows.append({
                "Rang": i,
                "Aktie": r["ticker"],
                "Poäng": r["poäng"],
                "Stigande trend": "✅" if r["trend_ok"] else "❌",
                "Trend (30)": d.get("Trend"),
                "Momentum (25)": d.get("Momentum"),
                "Analytiker (25)": d.get("Analytiker"),
                "Konsensus (20)": d.get("Konsensus"),
                "Claude": c.get("rekommendation", "—"),
            })
        st.dataframe(
            pd.DataFrame(rows), use_container_width=True, hide_index=True,
            column_config={
                "Poäng": st.column_config.ProgressColumn(
                    "Poäng", min_value=0, max_value=100, format="%.1f"
                ),
            },
        )
        st.caption(
            "**Poängmodellen:** Trend 30 p (över MA200, MA200 stigande, golden cross) · "
            "Momentum 25 p (RSI i styrkezon, MACD över signal, 3-månadersavkastning) · "
            "Analytiker 25 p (uppsida mot riktkurs, antal analytiker, köprekommendation) · "
            "Konsensus 20 p (antal portföljer, snittvikt). "
            "Aktier utan stigande trend rankas alltid sist, oavsett poäng."
        )

# --- Konsensus ---
with tab_konsensus:
    st.subheader(f"Konsensusaktier — innehav i minst {ea.MIN_PORTFOLIOS} av {len(data['profiler'])} portföljer")
    log = data.get("historik", [])
    innehav = data.get("innehav", {})
    nya_kons = nya_pa_listan(log, "IN I KONSENSUS")
    rows = []
    for tk in consensus_order:
        a = analyses.get(tk, {})
        c = claude.get(tk, {})
        h = innehav.get(tk, {})
        rows.append({
            "Aktie": f"🆕 {tk}" if tk in nya_kons else tk,
            "Stigande trend": trend_label(a),
            "Portföljer": consensus[tk]["count"],
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
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        "Stigande trend = priset över MA200 **och** MA200 stigande — utan den kan Claude aldrig ge KÖP. "
        "🆕 = ny på listan senaste 7 dagarna. "
        "**Ägd längst** = äldsta öppna positionen bland investerarna; **Inv. vinst** = deras "
        "genomsnittliga upparbetade vinst — lång tid + hög vinst = risk för vinsthemtagning."
    )

    # Nära konsensus — en portfölj från att kvala in
    near = data.get("nara_konsensus", {})
    if near:
        st.divider()
        st.subheader(f"🔍 Nära konsensus — i {ea.MIN_PORTFOLIOS - 1} av {len(data['profiler'])} portföljer")
        st.caption("Bevakningslista: köper en investerare till någon av dessa kvalar den in i konsensus.")
        nya_nara = nya_pa_listan(log, "IN I NÄRA KONSENSUS")
        near_rows = []
        for tk, info in sorted(near.items(), key=lambda x: -x[1]["avg_weight"]):
            h = innehav.get(tk, {})
            near_rows.append({
                "Aktie": f"🆕 {tk}" if tk in nya_nara else tk,
                "Snittvikt (%)": round(info["avg_weight"], 2),
                "Ägs av": ", ".join(info.get("holders", [])),
                "Ägd längst": format_innehavstid(h.get("längst_dagar")),
                "Inv. vinst (%)": h.get("snitt_vinst_pct", "—"),
            })
        st.dataframe(pd.DataFrame(near_rows), use_container_width=True, hide_index=True)

    # Lämnat listorna — när investerarna kliver av
    from datetime import date as _date, timedelta as _timedelta
    lamnat_cutoff = (_date.today() - _timedelta(days=30)).isoformat()
    lamnat = [e for e in log
              if e["typ"] in ("UT UR KONSENSUS", "UT UR NÄRA KONSENSUS")
              and e["datum"] >= lamnat_cutoff]
    st.divider()
    st.subheader("📤 Lämnat listorna — senaste 30 dagarna")
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

# --- Claudes analys ---
with tab_analys:
    st.subheader("Claudes tekniska analys per aktie")
    if not claude:
        st.info("Ingen Claude-analys i senaste körningen. Bocka i rutan i sidopanelen och kör igen.")
    for tk in consensus_order:
        a = analyses.get(tk, {})
        c = claude.get(tk)
        badge = {"KÖP": "🟢", "AVVAKTA": "🟡", "SÄLJ": "🔴"}.get((c or {}).get("rekommendation", ""), "⚪")
        with st.expander(f"{badge} **{tk}** — {(c or {}).get('rekommendation', 'ingen Claude-analys')}",
                         expanded=False):
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Pris", a.get("pris"))
            m2.metric("RSI14", a.get("RSI14"))
            m3.metric("MA200", a.get("MA200"))
            uppsida = a.get("uppsida_%")
            m4.metric("Uppsida", f"{uppsida} %" if uppsida is not None else "—")
            m5.metric("Stigande trend", trend_label(a))

            i1, i2, i3, i4 = st.columns(4)
            i1.markdown(f"Golden cross: {ja_nej(a.get('golden_cross'))}")
            i2.markdown(f"MACD över signal: {ja_nej(a.get('MACD_över_signal'))}")
            i3.markdown(f"1 mån: {a.get('avkastning_1m_%', '—')} %  ·  3 mån: {a.get('avkastning_3m_%', '—')} %")
            i4.markdown(f"Från 52v-toppen: {a.get('avstånd_52v_högsta_%', '—')} %")

            if a.get("datakälla") == "cache":
                st.caption(f"⚠️ Marknadsdata från tidigare körning ({a.get('cache_datum', 'okänt')}) "
                           "— datakällorna svarade inte just nu.")

            h = innehav.get(tk, {})
            if h:
                vinst = h.get("snitt_vinst_pct")
                st.markdown(
                    f"💼 Ägd längst: **{format_innehavstid(h.get('längst_dagar'))}** "
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

        intag = [e for e in dagens if e["typ"] in ("NYTT INNEHAV", "IN I KONSENSUS")]
        utsalt = [e for e in dagens if e["typ"] in ("SÅLT INNEHAV", "UT UR KONSENSUS")]
        ovrigt = [e for e in dagens if e["typ"] not in
                  ("NYTT INNEHAV", "IN I KONSENSUS", "SÅLT INNEHAV", "UT UR KONSENSUS")]

        col_in, col_ut = st.columns(2)
        with col_in:
            st.markdown("### 🟢 Intaget")
            if not intag:
                st.caption("Inga nya innehav.")
            for e in intag:
                vem = f" hos **{e['profil']}**" if e["profil"] else " (konsensus)"
                st.markdown(f"- **{e['ticker']}**{vem} — {e['detalj']}")
        with col_ut:
            st.markdown("### 🔴 Utsålt")
            if not utsalt:
                st.caption("Inga sålda innehav.")
            for e in utsalt:
                vem = f" hos **{e['profil']}**" if e["profil"] else " (konsensus)"
                st.markdown(f"- **{e['ticker']}**{vem} — {e['detalj']}")

        if ovrigt:
            st.markdown("### ⚖️ Viktändringar")
            for e in ovrigt:
                st.markdown(f"- **{e['ticker']}** hos **{e['profil']}** — {e['detalj']}")

        st.caption("Hela loggen över alla körningar finns under fliken **📜 Historik**.")

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
        st.bar_chart(df.set_index("Aktie").head(15))
        st.caption("De 15 största innehaven.")
