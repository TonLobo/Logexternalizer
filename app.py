"""
pj-consultador-xml — Consulta, busca, salva e exporta XMLs SoapUI / logexternalizer.
"""
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from fetcher import (
    DATA_DIR,
    fetch_pgmbox_entries,
    fetch_xml_from_url,
    load_local_xml_files,
    save_query,
    load_saved_queries,
    export_xml,
    LOG_URL,
)
from xml_parser import (
    parse_soapui_project,
    parse_log_entry,
    search_in_xml,
    pretty_print_xml,
)

st.set_page_config(
    page_title="Consultador XML",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Estilos ──────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .stApp { background: #0f1117; }
    .block-container { padding-top: 1.5rem; }
    .highlight { background: #1e2130; border-radius: 8px; padding: 1rem; }
    .tag-pill {
        display: inline-block; background: #1a4f6e; color: #7ecef5;
        border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; margin: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://www.softplan.com.br/wp-content/uploads/2021/11/softplan-logo-white.png",
        width=160,
    ) if False else st.title("🔍 Consultador XML")

    st.markdown("---")
    section = st.radio(
        "Seção",
        ["📂 Arquivos Locais", "🌐 Pgmbox (Remote)", "💾 Consultas Salvas"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("SAJ · Softplan")


# ════════════════════════════════════════════════════════════════════════════
# SEÇÃO 1 — ARQUIVOS LOCAIS
# ════════════════════════════════════════════════════════════════════════════
if section == "📂 Arquivos Locais":
    st.header("📂 Arquivos XML Locais")

    col_upload, col_dir = st.columns([2, 3])
    with col_upload:
        uploaded = st.file_uploader(
            "Enviar arquivos XML",
            type=["xml"],
            accept_multiple_files=True,
        )
    with col_dir:
        custom_dir = st.text_input(
            "Ou informe um diretório",
            placeholder=r"Ex: C:\Users\...\Soapui",
        )

    # Carrega arquivos
    entries: list[dict] = []

    if uploaded:
        for uf in uploaded:
            content = uf.read().decode("utf-8", errors="replace")
            entries.append(
                {
                    "filename": uf.name,
                    "path": "(upload)",
                    "raw_xml": content,
                    "source": "upload",
                }
            )
    elif custom_dir:
        entries = load_local_xml_files(custom_dir)
    else:
        entries = load_local_xml_files()

    if not entries:
        st.info("Nenhum arquivo encontrado. Envie XMLs acima ou informe um diretório.")
        st.stop()

    # Parse dos projetos
    projects = []
    for e in entries:
        meta = parse_soapui_project(e["raw_xml"], e.get("filename", ""))
        if not meta:
            meta = parse_log_entry(e["raw_xml"])
        meta.update(
            {
                "filename": e.get("filename", ""),
                "source": e.get("source", "local"),
                "raw_xml": e["raw_xml"],
                "file_mtime": e.get("file_mtime"),
            }
        )
        projects.append(meta)

    # ── Tabela ────────────────────────────────────────────────────────────
    st.subheader(f"{len(projects)} arquivo(s) carregado(s)")

    col_search, col_sort = st.columns([3, 1])
    with col_search:
        search_term = st.text_input("🔎 Filtrar por nome / endpoint", placeholder="ex: TJSP, EPROC, MNI…")
    with col_sort:
        sort_by = st.selectbox("Ordenar por", ["Nome", "Interfaces", "Data (desc)", "Data (asc)"])

    # Monta DataFrame
    rows = []
    for p in projects:
        rows.append(
            {
                "Arquivo": p.get("filename", ""),
                "Projeto": p.get("project_name", ""),
                "Interfaces": p.get("interface_count", 0),
                "Versão SoapUI": p.get("soapui_version", ""),
                "Data": p.get("date") or p.get("file_mtime"),
                "_raw_xml": p.get("raw_xml", ""),
                "_endpoints": ", ".join(p.get("endpoints", [])[:3]),
            }
        )

    df = pd.DataFrame(rows)

    if search_term:
        mask = (
            df["Arquivo"].str.contains(search_term, case=False, na=False)
            | df["Projeto"].str.contains(search_term, case=False, na=False)
            | df["_endpoints"].str.contains(search_term, case=False, na=False)
        )
        df = df[mask]

    sort_map = {
        "Nome": ("Projeto", True),
        "Interfaces": ("Interfaces", False),
        "Data (desc)": ("Data", False),
        "Data (asc)": ("Data", True),
    }
    s_col, s_asc = sort_map[sort_by]
    try:
        df = df.sort_values(s_col, ascending=s_asc, na_position="last")
    except Exception:
        pass

    display_df = df.drop(columns=["_raw_xml", "_endpoints"])
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Detalhe de um arquivo ─────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Detalhe / Busca interna")

    filenames = df["Arquivo"].tolist()
    if not filenames:
        st.info("Nenhum resultado para o filtro aplicado.")
        st.stop()

    selected_file = st.selectbox("Selecione um arquivo", filenames)
    selected_row = df[df["Arquivo"] == selected_file].iloc[0]
    raw_xml = selected_row["_raw_xml"]

    inner_query = st.text_input("🔍 Buscar dentro do XML selecionado", placeholder="ex: CNPJ, processo, endpoint…")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("💾 Salvar consulta"):
            path = save_query(
                selected_file,
                {
                    "filename": selected_file,
                    "projeto": selected_row["Projeto"],
                    "search_term": search_term,
                    "inner_query": inner_query,
                    "interfaces": int(selected_row["Interfaces"]),
                },
            )
            st.success(f"Salvo em `{path.name}`")

    with col_b:
        st.download_button(
            "⬇️ Exportar XML",
            data=raw_xml.encode("utf-8"),
            file_name=selected_file or "export.xml",
            mime="application/xml",
        )

    with col_c:
        # Exportar todos os filtrados como ZIP
        if st.button("📦 Exportar todos (ZIP)"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for _, row in df.iterrows():
                    zf.writestr(row["Arquivo"], row["_raw_xml"])
            buf.seek(0)
            st.download_button(
                "⬇️ Baixar ZIP",
                data=buf,
                file_name="xmls_exportados.zip",
                mime="application/zip",
            )

    # Busca interna
    if inner_query:
        results = search_in_xml(raw_xml, inner_query)
        if results:
            st.success(f"{len(results)} ocorrência(s) encontrada(s) para **{inner_query}**")
            for r in results[:50]:
                with st.expander(f"📌 `{r['tag']}` — {r['value'][:80]}"):
                    st.code(r["context"], language="xml")
                    if r["path"]:
                        st.caption(f"XPath: `{r['path']}`")
        else:
            st.warning(f"Nenhuma ocorrência de **{inner_query}** neste arquivo.")

    # Visualização do XML
    with st.expander("📄 Ver XML completo (formatado)"):
        pretty = pretty_print_xml(raw_xml)
        st.code(pretty[:20_000], language="xml")
        if len(pretty) > 20_000:
            st.caption("_(conteúdo truncado em 20.000 caracteres para exibição)_")


# ════════════════════════════════════════════════════════════════════════════
# SEÇÃO 2 — PGMBOX REMOTE
# ════════════════════════════════════════════════════════════════════════════
elif section == "🌐 Pgmbox (Remote)":
    st.header("🌐 Consulta Pgmbox — logexternalizer")

    col_url, col_max = st.columns([4, 1])
    with col_url:
        url = st.text_input("URL", value=LOG_URL)
    with col_max:
        max_entries = st.number_input("Máx. entradas", min_value=10, max_value=5000, value=200, step=50)

    if st.button("🔄 Buscar"):
        with st.spinner("Conectando ao pgmbox…"):
            entries = fetch_pgmbox_entries(url, max_entries=int(max_entries))
        st.session_state["pgmbox_entries"] = entries
        st.session_state["pgmbox_url"] = url

    entries = st.session_state.get("pgmbox_entries", [])
    if not entries:
        st.info("Clique em **Buscar** para consultar o pgmbox.")
        st.stop()

    # Verifica erros
    if len(entries) == 1 and "error" in entries[0]:
        st.error(f"Erro ao conectar: {entries[0]['error']}")
        st.stop()

    # Caso retorne HTML bruto (sem tabela parseable)
    if len(entries) == 1 and "raw_html" in entries[0]:
        st.warning("Resposta recebida — exibindo HTML bruto (verifique autenticação ou estrutura da página).")
        with st.expander("Ver resposta bruta"):
            st.code(entries[0]["raw_html"][:10_000])
        st.stop()

    st.subheader(f"{len(entries)} entrada(s) encontrada(s)")

    # Busca/filtro
    search_remote = st.text_input("🔎 Filtrar entradas", placeholder="pesquise em qualquer campo…")

    rows = []
    for i, e in enumerate(entries):
        cells = e.get("cells", [])
        rows.append(
            {
                "#": i + 1,
                "Conteúdo": " | ".join(cells) if cells else e.get("title", ""),
                "Link": e.get("link", ""),
                "_entry": e,
            }
        )

    df_remote = pd.DataFrame(rows)

    if search_remote:
        df_remote = df_remote[
            df_remote["Conteúdo"].str.contains(search_remote, case=False, na=False)
        ]

    sort_remote = st.selectbox("Ordenar por", ["#", "Conteúdo"])
    df_remote = df_remote.sort_values(sort_remote, ascending=True)

    st.dataframe(df_remote[["#", "Conteúdo", "Link"]], use_container_width=True, hide_index=True)

    # Detalhe de entrada
    st.markdown("---")
    selected_idx = st.number_input(
        "Selecionar entrada (#)",
        min_value=1,
        max_value=max(df_remote["#"].tolist() or [1]),
        value=1,
    )

    matching = df_remote[df_remote["#"] == selected_idx]
    if not matching.empty:
        entry = matching.iloc[0]["_entry"]
        link = entry.get("link", "")

        if link:
            if st.button("📥 Carregar XML desta entrada"):
                with st.spinner("Baixando XML…"):
                    try:
                        xml_content = fetch_xml_from_url(link, base_url=st.session_state.get("pgmbox_url", LOG_URL))
                        st.session_state["remote_xml"] = xml_content
                        st.session_state["remote_xml_name"] = link.split("/")[-1]
                    except Exception as ex:
                        st.error(str(ex))

        xml_content = st.session_state.get("remote_xml", "")
        if xml_content:
            inner_q = st.text_input("🔍 Buscar dentro do XML remoto", key="remote_inner_q")
            if inner_q:
                res = search_in_xml(xml_content, inner_q)
                if res:
                    st.success(f"{len(res)} resultado(s)")
                    for r in res[:30]:
                        with st.expander(f"`{r['tag']}` — {r['value'][:80]}"):
                            st.code(r["context"], language="xml")
                else:
                    st.warning("Sem resultados.")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Salvar esta consulta", key="save_remote"):
                    path = save_query(
                        st.session_state.get("remote_xml_name", "remote"),
                        {"url": link, "source": "remote"},
                    )
                    st.success(f"Salvo: `{path.name}`")
            with col2:
                st.download_button(
                    "⬇️ Exportar XML",
                    data=xml_content.encode("utf-8"),
                    file_name=st.session_state.get("remote_xml_name", "export.xml"),
                    mime="application/xml",
                )

            with st.expander("📄 XML completo"):
                st.code(pretty_print_xml(xml_content)[:15_000], language="xml")


# ════════════════════════════════════════════════════════════════════════════
# SEÇÃO 3 — CONSULTAS SALVAS
# ════════════════════════════════════════════════════════════════════════════
elif section == "💾 Consultas Salvas":
    st.header("💾 Consultas Salvas")

    queries = load_saved_queries()
    if not queries:
        st.info("Nenhuma consulta salva ainda.")
        st.stop()

    st.metric("Total de consultas", len(queries))

    search_saved = st.text_input("🔎 Filtrar consultas", placeholder="nome, projeto…")

    rows = []
    for q in queries:
        rows.append(
            {
                "Nome": q.get("query_name", ""),
                "Projeto": q.get("projeto", ""),
                "Busca": q.get("search_term", "") or q.get("inner_query", ""),
                "Salvo em": q.get("saved_at", ""),
                "_file": q.get("_file", ""),
                "_data": q,
            }
        )

    df_saved = pd.DataFrame(rows)
    if search_saved:
        df_saved = df_saved[
            df_saved["Nome"].str.contains(search_saved, case=False, na=False)
            | df_saved["Projeto"].str.contains(search_saved, case=False, na=False)
        ]

    sort_saved = st.selectbox("Ordenar por", ["Salvo em (desc)", "Nome", "Projeto"])
    if sort_saved == "Salvo em (desc)":
        df_saved = df_saved.sort_values("Salvo em", ascending=False)
    else:
        df_saved = df_saved.sort_values(sort_saved.split()[0], ascending=True)

    st.dataframe(df_saved[["Nome", "Projeto", "Busca", "Salvo em"]], use_container_width=True, hide_index=True)

    # Exportar todas as consultas salvas como JSON
    all_json = json.dumps([q["_data"] for q in queries], ensure_ascii=False, indent=2, default=str)
    st.download_button(
        "⬇️ Exportar todas (JSON)",
        data=all_json.encode("utf-8"),
        file_name="consultas_salvas.json",
        mime="application/json",
    )

    # Detalhe
    if not df_saved.empty:
        selected_name = st.selectbox("Ver detalhe de", df_saved["Nome"].tolist())
        row = df_saved[df_saved["Nome"] == selected_name].iloc[0]
        with st.expander("Dados completos"):
            st.json(row["_data"])
