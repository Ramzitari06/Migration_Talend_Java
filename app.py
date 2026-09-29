from __future__ import annotations

import streamlit as st

from migration_engine import AnalysisResult, analyze_archive, findings_csv


st.set_page_config(
    page_title="Passerelle JDK | Talend",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
    :root {
      --ink: #182320;
      --muted: #65716c;
      --paper: #f5f7f2;
      --line: #dce3dc;
      --green: #d7f36a;
      --deep: #193b32;
      --orange: #c45d39;
    }
    html, body, [class*="css"] { font-family: 'Manrope', sans-serif; color: var(--ink); }
    .stApp { background: var(--paper); }
    [data-testid="stSidebar"] { background: #e9eee7; border-right: 1px solid var(--line); }
    [data-testid="stSidebar"] .block-container { padding-top: 2rem; }
    .masthead { border-bottom: 1px solid var(--line); padding: 0 0 1.25rem; margin-bottom: 1.7rem; }
    .eyebrow { color: var(--deep); font: 500 11px 'DM Mono', monospace; letter-spacing: 0; text-transform: uppercase; }
    .title { font-size: clamp(2rem, 3vw, 3.1rem); line-height: 1.04; font-weight: 800; margin: .4rem 0 .6rem; }
    .subtitle { max-width: 780px; color: var(--muted); font-size: 15px; line-height: 1.6; }
    .scope-note { border-left: 3px solid var(--orange); background: #fff8f4; padding: .8rem 1rem; color: #603a2f; font-size: 13px; line-height: 1.55; }
    .metric { background: #fff; border: 1px solid var(--line); border-top: 3px solid var(--deep); padding: 1rem 1.1rem; min-height: 104px; }
    .metric-label { color: var(--muted); font-size: 12px; }
    .metric-value { font: 500 27px 'DM Mono', monospace; padding-top: .35rem; }
    .section-label { font: 500 11px 'DM Mono', monospace; text-transform: uppercase; color: var(--muted); margin: 1rem 0 .55rem; }
    code, .mono { font-family: 'DM Mono', monospace !important; }
    div[data-testid="stDownloadButton"] button { border-radius: 3px; border: 1px solid var(--deep); }
    div.stButton > button[kind="primary"] { background: var(--deep); border: 0; border-radius: 3px; min-height: 44px; }
    div.stButton > button[kind="primary"]:hover { background: #285848; }
    div[data-testid="stFileUploader"] { border: 1px dashed #8e9c91; border-radius: 3px; background: rgba(255,255,255,.55); }
    [data-testid="stDataFrame"] { border: 1px solid var(--line); }
    @media (max-width: 700px) { .title { font-size: 2rem; } .subtitle { font-size: 14px; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_metric(label: str, value: str | int) -> None:
    st.markdown(
        f'<div class="metric"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div></div>',
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.markdown('<div class="eyebrow">Contexte de migration</div>', unsafe_allow_html=True)
    source_release = st.selectbox("Release source", ["Talend 2023-06"], index=0)
    target_release = st.selectbox("Release cible", ["Talend 2026-06"], index=0)
    st.divider()
    st.markdown("**Périmètre technique**")
    st.caption("Analyse statique du contenu exporté. Le ZIP reste traité dans cette session Streamlit.")
    st.markdown(
        '<div class="scope-note">Cet assistant ne remplace pas la migration officielle dans Talend Studio. '
        'Il ne modifie pas les métadonnées propriétaires <code>.item</code> ni les dépendances du runtime.</div>',
        unsafe_allow_html=True,
    )


st.markdown(
    '<header class="masthead"><div class="eyebrow">Data engineering / Java 11 → Java 17</div>'
    '<div class="title">Passerelle JDK</div>'
    '<div class="subtitle">Préparez vos jobs Talend à la montée de version : repérez les usages sensibles, '
    'examinez les réglages de compilation et générez un export avec les seules cibles Java 11 reconnues mises à jour.</div></header>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-label">01 / Charger un export projet Talend</div>', unsafe_allow_html=True)
uploaded_file = st.file_uploader("Archive ZIP du projet ou des jobs exportés", type=["zip"], label_visibility="collapsed")
upgrade_requested = st.checkbox(
    "Mettre à jour dans une copie les cibles Java 11 explicites (Maven, Gradle et propriétés reconnues)",
    value=False,
    disabled=uploaded_file is None,
)

if st.button("Analyser l’archive", type="primary", disabled=uploaded_file is None, use_container_width=False):
    try:
        result = analyze_archive(uploaded_file.getvalue(), upgrade_java_target=upgrade_requested)
        st.session_state["migration_result"] = result
        st.session_state["migration_filename"] = uploaded_file.name
        st.session_state["migration_source_release"] = source_release
        st.session_state["migration_target_release"] = target_release
    except ValueError as error:
        st.error(str(error))

result: AnalysisResult | None = st.session_state.get("migration_result")
if result is not None:
    st.markdown('<div class="section-label">02 / Résultats de l’analyse</div>', unsafe_allow_html=True)
    high_findings = sum(finding.severity == "Élevée" for finding in result.findings)
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        render_metric("Fichiers analysés", result.files_scanned)
    with col_b:
        render_metric("Constats", len(result.findings))
    with col_c:
        render_metric("À traiter en priorité", high_findings)
    with col_d:
        render_metric("Configurations modifiées", len(result.changed_files))

    if result.skipped_files:
        st.warning(f"{len(result.skipped_files)} fichier(s) ignoré(s) : limite de taille ou de volume atteinte.")
    if result.changed_files:
        st.success("Une copie de l’archive est prête. Seules les configurations reconnues ont été modifiées.")

    if not result.findings:
        st.success("Aucun motif surveillé ni cible de compilation inférieure à Java 17 détecté dans les fichiers analysés.")
    else:
        findings_rows = [
            {
                "Sévérité": finding.severity,
                "Règle": finding.rule,
                "Fichier": finding.path,
                "Ligne": finding.line,
                "Constat": finding.message,
                "Extrait": finding.snippet,
                "Recommandation": finding.recommendation,
            }
            for finding in result.findings
        ]
        st.dataframe(findings_rows, use_container_width=True, hide_index=True)

    downloads = st.columns([1, 1, 3])
    with downloads[0]:
        st.download_button(
            "Télécharger le rapport CSV",
            data=findings_csv(result.findings),
            file_name="talend-java17-findings.csv",
            mime="text/csv",
        )
    if result.updated_archive is not None:
        with downloads[1]:
            st.download_button(
                "Télécharger le ZIP mis à jour",
                data=result.updated_archive,
                file_name="talend-java17-migration.zip",
                mime="application/zip",
            )
        st.caption("Fichiers de configuration modifiés : " + ", ".join(result.changed_files))

    with st.expander("Règles et limites de l’analyse"):
        st.markdown(
            """
            - JAXB et Java Activation, absents du JDK depuis Java 11.
            - API internes `sun.misc` et `jdk.internal`.
            - Moteur Nashorn retiré du JDK.
            - Accès réflexifs à vérifier avec l’encapsulage fort de Java 17.
            - Cibles Java explicites inférieures à 17 dans les fichiers reconnus.

            Les dépendances, composants Talend, routines personnalisées et métadonnées de job doivent être validés dans Talend Studio. Les réglages ambigus ne sont jamais réécrits automatiquement.
            """
        )