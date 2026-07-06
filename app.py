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

if st.sidebar.button("🔄 Uppdatera nu", type="primary", use_container_width=True):
    st.session_state.pop("auto_refreshed", None)  # tillåt omhämtning nedan
    st.session_state["force_claude"] = force_claude

# Hämta färsk eToro-data automatiskt när sidan öppnas (en gång per besök).
# Claude-analysen är dagsspärrad inne i run_analysis, så detta drar inga
# credits om den redan körts idag.
if "auto_refreshed" not in st.session_state:
    with st.spinner("Hämtar färsk portföljdata från eToro och räknar indikatorer..."):
        try:
            ea.run_analysis(with_claude=with_claude,
                            force_claude=st.session_state.pop("force_claude", False))
            st.session_state["auto_refreshed"] = True
        except RuntimeError as e:
            st.session_state["auto_refreshed"] = True
            st.sidebar.error(str(e))

data = load_results()

if data:
    st.sidebar.caption(f"Portföljdata: {data['tidpunkt'].replace('T', ' kl. ')}")
    cd = data.get("claude_datum")
    st.sidebar.caption(f"🤖 Claude-analys från: {cd}" if cd else "🤖 Ingen Claude-analys ännu")
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
    rows = []
    for tk in consensus_order:
        a = analyses.get(tk, {})
        c = claude.get(tk, {})
        rows.append({
            "Aktie": tk,
            "Stigande trend": trend_label(a),
            "Portföljer": consensus[tk]["count"],
            "Snittvikt (%)": round(consensus[tk]["avg_weight"], 2),
            "Pris": a.get("pris"),
            "RSI14": a.get("RSI14"),
            "Analytiker": a.get("rekommendation"),
            "Riktkurs": a.get("riktkurs"),
            "Uppsida (%)": a.get("uppsida_%"),
            "Claude": c.get("rekommendation", "—"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        "Stigande trend = priset över MA200 **och** MA200 stigande. "
        "Aktier utan stigande trend kan aldrig få KÖP av Claude."
    )

    # Nära konsensus — en portfölj från att kvala in
    near = data.get("nara_konsensus", {})
    if near:
        st.divider()
        st.subheader(f"🔍 Nära konsensus — i {ea.MIN_PORTFOLIOS - 1} av {len(data['profiler'])} portföljer")
        st.caption("Bevakningslista: köper en investerare till någon av dessa kvalar den in i konsensus.")
        near_rows = [{
            "Aktie": tk,
            "Snittvikt (%)": round(info["avg_weight"], 2),
            "Ägs av": ", ".join(info.get("holders", [])),
        } for tk, info in sorted(near.items(), key=lambda x: -x[1]["avg_weight"])]
        st.dataframe(pd.DataFrame(near_rows), use_container_width=True, hide_index=True)

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
