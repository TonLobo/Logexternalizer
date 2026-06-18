"""
pj-consultador-xml — Consulta de Logs de Integração (HUB / MNI) via logexternalizer SAJ.
"""
import io
import json
import re as _re
from datetime import datetime

import pandas as pd
import streamlit as st

import config as _cfg

from exporter import (
    export_csv,
    export_xml_formatted,
    export_pdf,
    export_pdf_par,
)
from fetcher import (
    fetch_hub_pgmps,
    fetch_hub_operacoes,
    fetch_hub_datas,
    fetch_hub_arquivos,
    fetch_mni_pgmps,
    fetch_mni_pvc,
    fetch_mni_datas,
    fetch_mni_arquivos,
    fetch_xml,
    save_query,
    load_saved_queries,
    export_zip,
    _mni_session,
    _hub_session,
)
from xml_parser import (
    pretty_print_xml,
    search_in_xml,
    extract_soap_summary,
)

st.set_page_config(
    page_title="Logs Integração SAJ",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stSidebar"] { background: #111827; }
.stApp { background: #0f1117; }
.block-container { padding-top: 1.2rem; }
.metric-box {
    background: #1e2130; border-radius: 8px;
    padding: 12px 16px; margin: 4px 0;
}
.request-badge  { background:#1d4ed8; color:#bfdbfe; padding:2px 10px; border-radius:12px; font-size:.75rem; }
.response-badge { background:#065f46; color:#a7f3d0; padding:2px 10px; border-radius:12px; font-size:.75rem; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📋 Logs Integração")
    st.caption("logexternalizer · SAJ / Softplan")
    st.markdown("---")
    section = st.radio(
        "Fonte",
        ["🔷 Logs-HUB", "🔶 Logs-MNI (XML)", "💾 Consultas Salvas"],
        label_visibility="collapsed",
    )
    st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# SEÇÃO HUB
# ═══════════════════════════════════════════════════════════════════════════
if section == "🔷 Logs-HUB":
    st.header("🔷 Logs-HUB — Consultas SOAP por PGMP")

    # ── 1. Carrega lista de PGMPs ─────────────────────────────────────────
    @st.cache_data(ttl=300)
    def get_hub_pgmps():
        return fetch_hub_pgmps()

    with st.spinner("Carregando lista de PGMPs..."):
        pgmps = get_hub_pgmps()

    if not pgmps:
        st.error("Não foi possível carregar a lista de PGMPs. Verifique a conectividade.")
        st.stop()

    labels = [p["label"] for p in pgmps]
    hashes = {p["label"]: p["hash"] for p in pgmps}

    _saved = _cfg.load()
    col1, col2, col3 = st.columns(3)

    with col1:
        _pgmp_idx = labels.index(_saved["hub_pgmp"]) if _saved["hub_pgmp"] in labels else 0
        pgmp_sel = st.selectbox("PGMP", labels, index=_pgmp_idx, key="hub_pgmp_sel")

    hub_hash = hashes[pgmp_sel]
    _cfg.save(hub_pgmp=pgmp_sel)

    # ── 2. Operações ──────────────────────────────────────────────────────
    @st.cache_data(ttl=120)
    def get_operacoes(h):
        try:
            return fetch_hub_operacoes(h)
        except Exception as e:
            return {"_error": str(e)}

    with st.spinner("Carregando operações..."):
        operacoes = get_operacoes(hub_hash)

    if isinstance(operacoes, dict) and "_error" in operacoes:
        st.error(f"❌ Sem acesso ao servidor HUB (`172.50.1.164:9999`).\n\n**Verifique se está na rede SAJ / VPN.**\n\nDetalhe: `{operacoes['_error']}`")
        st.stop()

    if not operacoes:
        st.warning(f"Nenhuma operação encontrada para {pgmp_sel}.")
        st.stop()

    with col2:
        _op_idx = operacoes.index(_saved["hub_operacao"]) if _saved["hub_operacao"] in operacoes else 0
        op_sel = st.selectbox("Operação", operacoes, index=_op_idx, key="hub_op_sel")
    _cfg.save(hub_operacao=op_sel)

    # ── 3. Datas ──────────────────────────────────────────────────────────
    @st.cache_data(ttl=60)
    def get_datas(h, op):
        try:
            return fetch_hub_datas(h, op)
        except Exception as e:
            return {"_error": str(e)}

    with st.spinner("Carregando datas..."):
        datas = get_datas(hub_hash, op_sel)

    if isinstance(datas, dict) and "_error" in datas:
        st.error(f"❌ Timeout ao buscar datas.\n\nDetalhe: `{datas['_error']}`")
        st.stop()

    if not datas:
        st.warning("Nenhuma data disponível para esta operação.")
        st.stop()

    with col3:
        _data_idx = datas.index(_saved["hub_data"]) if _saved["hub_data"] in datas else 0
        data_sel = st.selectbox("Data", datas, index=_data_idx, key="hub_data_sel")
    _cfg.save(hub_data=data_sel)

    st.markdown("---")

    # ── 4. Arquivos da data ───────────────────────────────────────────────
    @st.cache_data(ttl=60)
    def get_arquivos(h, op, d):
        try:
            return fetch_hub_arquivos(h, op, d)
        except Exception as e:
            return {"_error": str(e)}

    with st.spinner(f"Carregando arquivos de {data_sel}..."):
        arquivos = get_arquivos(hub_hash, op_sel, data_sel)

    if isinstance(arquivos, dict) and "_error" in arquivos:
        st.error(f"❌ Erro ao listar arquivos.\n\nDetalhe: `{arquivos['_error']}`")
        st.stop()

    if not arquivos:
        st.info("Nenhum arquivo XML encontrado para esta data.")
        st.stop()

    # ── Filtros ───────────────────────────────────────────────────────────
    def _limpar_filtros_hub():
        st.session_state["hub_filtro_nome"]   = ""
        st.session_state["hub_tipo_filtro"]   = "Todos"
        st.session_state["hub_ordem"]         = "Mais recente"
        st.session_state["hub_busca_conteudo"] = ""
        for k in ("hub_content_matches", "hub_content_term",
                  "hub_file_sel", "hub_file_sel_box", "hub_xmls", "hub_uuid"):
            st.session_state.pop(k, None)

    col_f1, col_f2, col_f3, col_f4 = st.columns([3, 1, 1, 1])
    with col_f1:
        busca_lista = st.text_input(
            "🔎 Filtrar por nome do arquivo",
            placeholder="nome, timestamp, UUID...",
            key="hub_filtro_nome",
        )
    with col_f2:
        tipo_filtro = st.selectbox(
            "Tipo", ["Todos", "request", "response"], key="hub_tipo_filtro"
        )
    with col_f3:
        ordem = st.selectbox(
            "Ordenar", ["Mais recente", "Mais antigo"], key="hub_ordem"
        )
    with col_f4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Limpar filtros", key="hub_btn_limpar", use_container_width=True):
            _limpar_filtros_hub()
            st.rerun()

    # ── Busca por conteúdo interno ────────────────────────────────────────
    with st.expander("🔍 Buscar dentro do conteúdo dos XMLs"):
        col_bc1, col_bc2, col_bc3 = st.columns([4, 1, 1])
        with col_bc1:
            busca_conteudo = st.text_input(
                "Termo a localizar nos XMLs",
                placeholder="ex: numeroProcesso, CNPJ, erro, operação...",
                key="hub_busca_conteudo",
            )
        with col_bc2:
            st.markdown("<br>", unsafe_allow_html=True)
            btn_buscar_conteudo = st.button("🔎 Buscar", key="hub_btn_busca_conteudo")
        with col_bc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Limpar", key="hub_btn_limpar_conteudo"):
                st.session_state["hub_busca_conteudo"] = ""
                st.session_state.pop("hub_content_matches", None)
                st.session_state.pop("hub_content_term", None)
                st.rerun()

        # Chave de cache: muda quando PGMP/operação/data mudam
        cache_key = f"hub_content_cache_{pgmp_sel}_{op_sel}_{data_sel}"

        if btn_buscar_conteudo and busca_conteudo:
            # Baixa todos os arquivos (com cache na session) e busca o termo
            if cache_key not in st.session_state:
                st.session_state[cache_key] = {}

            content_cache = st.session_state[cache_key]
            matches = []
            prog = st.progress(0, text="Baixando e pesquisando arquivos...")

            for i, a in enumerate(arquivos):
                prog.progress((i + 1) / len(arquivos),
                               text=f"Pesquisando {i+1}/{len(arquivos)}: {a['name'][:50]}...")
                # Usa cache se já baixou
                if a["name"] not in content_cache:
                    try:
                        content_cache[a["name"]] = fetch_xml(a["url"], session=_hub_session())
                    except Exception:
                        content_cache[a["name"]] = ""

                xml_c = content_cache[a["name"]]
                if busca_conteudo.lower() in xml_c.lower():
                    results_c = search_in_xml(xml_c, busca_conteudo)
                    matches.append({
                        "name": a["name"],
                        "tipo": a["tipo"],
                        "timestamp": a["timestamp"],
                        "url": a["url"],
                        "hits": len(results_c),
                        "preview": results_c[0]["value"][:100] if results_c else "",
                    })

            prog.empty()
            st.session_state["hub_content_matches"] = matches
            st.session_state["hub_content_term"] = busca_conteudo
            st.session_state[cache_key] = content_cache

        # Exibe resultado da busca por conteúdo
        matches = st.session_state.get("hub_content_matches", [])
        term_usado = st.session_state.get("hub_content_term", "")
        if matches and term_usado:
            st.success(f"**{len(matches)}** arquivo(s) contêm `{term_usado}`")
            df_matches = pd.DataFrame([{
                "Horário": m["timestamp"].strftime("%H:%M:%S") if m["timestamp"] else "",
                "Tipo": m["tipo"],
                "Arquivo": m["name"],
                "Ocorrências": m["hits"],
                "Preview": m["preview"],
            } for m in matches])
            evt_m = st.dataframe(
                df_matches,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="hub_df_matches",
            )
            sel_m = evt_m.selection.rows if evt_m.selection.rows else []
            if sel_m:
                st.session_state["hub_file_sel"] = df_matches.iloc[sel_m[0]]["Arquivo"]
                st.info(f"✅ Arquivo selecionado: `{st.session_state['hub_file_sel']}`")
        elif term_usado and not matches:
            st.warning(f"Nenhum arquivo contém `{term_usado}`.")

    # Monta lista individual de arquivos
    rows = []
    for a in arquivos:
        if tipo_filtro != "Todos" and a["tipo"] != tipo_filtro:
            continue
        if busca_lista and busca_lista.lower() not in a["name"].lower():
            continue
        rows.append({
            "Horário": a["timestamp"].strftime("%H:%M:%S") if a["timestamp"] else "",
            "Tipo": a["tipo"],
            "Arquivo": a["name"],
            "_url": a["url"],
            "_ts": a["timestamp"] or datetime.min,
            "_tipo": a["tipo"],
            "_uuid": a.get("uuid", ""),
        })

    if not rows:
        st.info("Nenhum arquivo corresponde ao filtro.")
        st.stop()

    df = pd.DataFrame(rows)
    df = df.sort_values("_ts", ascending=(ordem == "Mais antigo"))
    df = df.reset_index(drop=True)

    st.subheader(f"{len(df)} arquivo(s) — {pgmp_sel} · {op_sel} · {data_sel}")

    # Tabela clicável — seleção sincroniza com o selectbox abaixo
    evt = st.dataframe(
        df[["Horário", "Tipo", "Arquivo", "_uuid"]].rename(columns={"_uuid": "UUID"}),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="hub_df_sel",
    )

    # Sincroniza seleção da tabela → selectbox (atualiza ANTES do selectbox renderizar)
    sel_rows = evt.selection.rows if evt.selection.rows else []
    if sel_rows:
        fname_clicked = df.iloc[sel_rows[0]]["Arquivo"]
        st.session_state["hub_file_sel"] = fname_clicked
        st.session_state["hub_file_sel_box"] = fname_clicked  # força selectbox

    # Export CSV da tabela
    csv_rows_t = [{"PGMP": pgmp_sel, "Operação": op_sel, "Data": data_sel,
                   "Arquivo": r["Arquivo"], "Tipo": r["Tipo"], "Horário": r["Horário"]}
                  for r in rows]
    st.download_button(
        "⬇️ Exportar tabela (CSV)",
        data=export_csv(csv_rows_t, ["PGMP", "Operação", "Data", "Arquivo", "Tipo", "Horário"]),
        file_name=f"{pgmp_sel}_{op_sel}_{data_sel}.csv",
        mime="text/csv",
        key="hub_csv",
    )

    st.markdown("---")
    st.subheader("📂 Visualizar e Exportar")

    # Selectbox sincronizado com clique na tabela
    all_files = df["Arquivo"].tolist()
    # Inicializa session_state apenas no primeiro carregamento (config como fallback).
    # Cliques na tabela já setam hub_file_sel_box diretamente — não sobrescrever.
    if "hub_file_sel_box" not in st.session_state:
        fallback = _cfg.load().get("hub_file") or all_files[0]
        st.session_state["hub_file_sel_box"] = fallback if fallback in all_files else all_files[0]
    elif st.session_state["hub_file_sel_box"] not in all_files:
        st.session_state["hub_file_sel_box"] = all_files[0]

    arq_sel_name = st.selectbox(
        "Arquivo selecionado",
        all_files,
        key="hub_file_sel_box",
    )
    st.session_state["hub_file_sel"] = arq_sel_name
    _cfg.save(hub_file=arq_sel_name)

    arq_sel_row = df[df["Arquivo"] == arq_sel_name].iloc[0]
    arq_sel_tipo = arq_sel_row["_tipo"]
    arq_sel_url  = arq_sel_row["_url"]
    arq_sel_ts   = arq_sel_row["_ts"]

    # ── Auto-pareia: UUID idêntico (prioritário) ou timestamp mais próximo ──
    tipo_oposto = "response" if arq_sel_tipo == "request" else "request"
    df_oposto = df[df["_tipo"] == tipo_oposto].copy()
    par_auto = None
    par_metodo = ""

    if not df_oposto.empty:
        arq_sel_uuid = arq_sel_row["_uuid"]

        # 1º: mesmo UUID
        if arq_sel_uuid:
            uuid_match = df_oposto[df_oposto["_uuid"] == arq_sel_uuid]
            if not uuid_match.empty:
                par_auto = uuid_match.iloc[0]
                par_metodo = "mesmo UUID"

        # 2º: timestamp mais próximo (até 120s)
        if par_auto is None:
            df_oposto["_diff"] = (df_oposto["_ts"] - arq_sel_ts).abs().dt.total_seconds()
            melhor = df_oposto.nsmallest(1, "_diff").iloc[0]
            if melhor["_diff"] <= 120:
                par_auto = melhor
                par_metodo = f"timestamp mais próximo ({int(melhor['_diff'])}s)"

    if par_auto is not None:
        st.info(
            f"🔗 **{tipo_oposto.capitalize()} pareado** ({par_metodo}): `{par_auto['Arquivo']}`"
        )

    col_bi1, col_bi2 = st.columns([5, 1])
    with col_bi1:
        busca_interna = st.text_input(
            "🔍 Buscar nos XMLs",
            placeholder="processo, CNPJ, erro, operação...",
            key="hub_busca_interna",
        )
    with col_bi2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Limpar", key="hub_btn_limpar_interna", use_container_width=True):
            st.session_state["hub_busca_interna"] = ""
            for k in ("hub_xmls", "hub_uuid", "pdf_sel", "pdf_par", "pdf_full_par"):
                st.session_state.pop(k, None)
            st.rerun()

    if st.button("📥 Carregar arquivo + par", key="hub_load"):
        xmls = {"_sel_name": arq_sel_name}
        for label, row_data in [("sel", arq_sel_row), ("par", par_auto)]:
            if row_data is None:
                xmls[label] = None
                continue
            with st.spinner(f"Baixando {row_data['Tipo']}..."):
                try:
                    xmls[label] = {"xml": fetch_xml(row_data["_url"], session=_hub_session()),
                                   "name": row_data["Arquivo"],
                                   "tipo": row_data["_tipo"]}
                except Exception as e:
                    xmls[label] = {"xml": f"<!-- Erro: {e} -->",
                                   "name": row_data["Arquivo"],
                                   "tipo": row_data["_tipo"]}
        st.session_state["hub_xmls"] = xmls

    xmls = st.session_state.get("hub_xmls", {})
    if xmls and xmls.get("_sel_name") == arq_sel_name:
        # Resumo SOAP
        ref_xml = (xmls.get("sel") or {}).get("xml", "")
        summary = extract_soap_summary(ref_xml) if ref_xml else {}
        if summary:
            cols = st.columns(min(len(summary), 4))
            for i, (k, v) in enumerate(list(summary.items())[:4]):
                cols[i].metric(k, v[:60])
            st.markdown("")

        # Busca interna nos dois XMLs carregados
        if busca_interna:
            for label in ("sel", "par"):
                entry = xmls.get(label)
                if not entry or not entry.get("xml"):
                    continue
                results = search_in_xml(entry["xml"], busca_interna)
                badge = f"**{entry['tipo'].upper()}** (`{entry['name']}`)"
                if results:
                    st.success(f"{badge} — {len(results)} ocorrência(s) de `{busca_interna}`")
                    for r in results[:30]:
                        with st.expander(f"`{r['tag']}` — {r['value'][:80]}"):
                            st.code(r["context"], language="xml")
                            if r["path"]:
                                st.caption(f"XPath: `{r['path']}`")
                else:
                    st.info(f"{badge} — sem resultados.")

        # ── Abas: arquivo selecionado + par ──────────────────────────────
        sel_entry = xmls.get("sel")
        par_entry = xmls.get("par")

        tab_label_sel = f"{'📤' if arq_sel_tipo == 'request' else '📥'} {arq_sel_tipo.capitalize()} (selecionado)"
        tab_label_par = f"{'📥' if tipo_oposto == 'response' else '📤'} {tipo_oposto.capitalize()} (par)"

        tab_sel, tab_par = st.tabs([tab_label_sel, tab_label_par])

        for tab, entry, key_prefix in [(tab_sel, sel_entry, "sel"), (tab_par, par_entry, "par")]:
            with tab:
                if not entry or not entry.get("xml"):
                    st.info("Arquivo não carregado ou não encontrado.")
                    continue

                xml_t     = entry["xml"]
                nome_arq  = entry["name"]
                tipo_arq  = entry["tipo"]
                titulo_pdf = f"{pgmp_sel} · {op_sel}"
                sub_pdf    = f"{data_sel} · {nome_arq}"

                st.caption(f"`{nome_arq}`")
                pretty = pretty_print_xml(xml_t)
                st.code(pretty[:30_000], language="xml")
                if len(pretty) > 30_000:
                    st.caption("_(truncado em 30.000 chars)_")

                st.markdown("**Exportar:**")
                c1, c2, c3 = st.columns(3)

                with c1:
                    st.download_button(
                        "⬇️ XML formatado",
                        data=export_xml_formatted(xml_t),
                        file_name=nome_arq,
                        mime="application/xml",
                        key=f"dl_{key_prefix}_xml",
                    )
                with c2:
                    if st.button("⬇️ Gerar PDF", key=f"btn_{key_prefix}_pdf"):
                        with st.spinner("Gerando PDF..."):
                            st.session_state[f"pdf_{key_prefix}"] = export_pdf(
                                xml_t, titulo=titulo_pdf, subtitulo=sub_pdf, tipo=tipo_arq
                            )
                    if f"pdf_{key_prefix}" in st.session_state:
                        st.download_button(
                            "⬇️ Baixar PDF",
                            data=st.session_state[f"pdf_{key_prefix}"],
                            file_name=nome_arq.replace(".xml", ".pdf"),
                            mime="application/pdf",
                            key=f"dl_{key_prefix}_pdf",
                        )
                with c3:
                    summary_t = extract_soap_summary(xml_t)
                    summary_t.update({"pgmp": pgmp_sel, "operacao": op_sel,
                                      "data": data_sel, "arquivo": nome_arq, "tipo": tipo_arq})
                    st.download_button(
                        "⬇️ CSV (resumo)",
                        data=export_csv([summary_t], list(summary_t.keys())),
                        file_name=nome_arq.replace(".xml", ".csv"),
                        mime="text/csv",
                        key=f"dl_{key_prefix}_csv",
                    )

        # ── Exportar par completo ────────────────────────────────────────
        st.markdown("---")
        st.markdown("**Exportar par completo:**")
        cp1, cp2, cp3 = st.columns(3)

        xml_sel_raw = sel_entry["xml"] if sel_entry else None
        xml_par_raw = par_entry["xml"] if par_entry else None
        xml_req_raw = xml_sel_raw if arq_sel_tipo == "request" else xml_par_raw
        xml_res_raw = xml_sel_raw if arq_sel_tipo == "response" else xml_par_raw

        with cp1:
            if st.button("💾 Salvar consulta", key="hub_save"):
                p = save_query(arq_sel_name, {
                    "pgmp": pgmp_sel, "operacao": op_sel, "data": data_sel,
                    "arquivo": arq_sel_name, "par": par_auto["Arquivo"] if par_auto is not None else "",
                    "busca": busca_interna, **summary,
                })
                st.success(f"Salvo: `{p.name}`")

        with cp2:
            items_par = [(e["name"], pretty_print_xml(e["xml"]))
                         for e in [sel_entry, par_entry] if e and e.get("xml")]
            if items_par:
                st.download_button(
                    "⬇️ ZIP (XML formatados)",
                    data=export_zip(items_par),
                    file_name=f"{arq_sel_name}.zip",
                    mime="application/zip",
                    key="dl_par_zip",
                )

        with cp3:
            if st.button("⬇️ Gerar PDF (par completo)", key="btn_full_par_pdf"):
                with st.spinner("Gerando PDF..."):
                    st.session_state["pdf_full_par"] = export_pdf_par(
                        xml_req_raw, xml_res_raw,
                        titulo=f"{pgmp_sel} · {op_sel}",
                        subtitulo=f"{data_sel} · {arq_sel_name}",
                    )
            if "pdf_full_par" in st.session_state:
                st.download_button(
                    "⬇️ Baixar PDF (par)",
                    data=st.session_state["pdf_full_par"],
                    file_name=f"{arq_sel_name}.pdf",
                    mime="application/pdf",
                    key="dl_full_par_pdf",
                )

        # ZIP da data inteira
        if st.button("📦 Exportar data inteira (ZIP)", key="hub_zip_all"):
            with st.spinner("Baixando todos os arquivos..."):
                items = []
                for _, row_z in df.iterrows():
                    try:
                        c = fetch_xml(row_z["_url"], session=_hub_session())
                        items.append((row_z["Arquivo"], pretty_print_xml(c)))
                    except Exception:
                        pass
            zb = export_zip(items)
            st.download_button(
                "⬇️ Baixar ZIP completo",
                data=zb,
                file_name=f"{pgmp_sel}_{op_sel}_{data_sel}.zip",
                mime="application/zip",
                key="hub_zip_all_dl",
            )


# ═══════════════════════════════════════════════════════════════════════════
# SEÇÃO MNI
# ═══════════════════════════════════════════════════════════════════════════
elif section == "🔶 Logs-MNI (XML)":
    st.header("🔶 Logs-MNI — XMLs por PGMP / Data")

    # ── 1. PGMPs ─────────────────────────────────────────────────────────
    @st.cache_data(ttl=300)
    def get_mni_pgmps():
        try:
            return fetch_mni_pgmps()
        except Exception as e:
            return {"_error": str(e)}

    with st.spinner("Carregando PGMPs MNI..."):
        pgmps_mni = get_mni_pgmps()

    if isinstance(pgmps_mni, dict) and "_error" in pgmps_mni:
        st.error(f"❌ Sem acesso ao servidor MNI (`172.50.1.164:9999`).\n\n**Verifique se está na rede SAJ / VPN.**\n\nDetalhe: `{pgmps_mni['_error']}`")
        st.stop()

    if not pgmps_mni:
        st.error("Não foi possível listar os PGMPs MNI.")
        st.stop()

    _saved_mni = _cfg.load()
    col1, col2 = st.columns(2)
    with col1:
        _mni_pgmp_idx = pgmps_mni.index(_saved_mni["mni_pgmp"]) if _saved_mni["mni_pgmp"] in pgmps_mni else 0
        pgmp_mni = st.selectbox("PGMP", pgmps_mni, index=_mni_pgmp_idx,
                                format_func=str.upper, key="mni_pgmp_sel")
    _cfg.save(mni_pgmp=pgmp_mni)

    # ── 2. PVC / Datas ───────────────────────────────────────────────────
    @st.cache_data(ttl=120)
    def get_pvc(pgmp):
        try:
            return fetch_mni_pvc(pgmp)
        except Exception as e:
            return None

    pvc = get_pvc(pgmp_mni)
    if not pvc:
        st.warning(f"Nenhum PVC encontrado para {pgmp_mni}.")
        st.stop()

    @st.cache_data(ttl=60)
    def get_mni_datas(p):
        try:
            return fetch_mni_datas(p)
        except Exception as e:
            return {"_error": str(e)}

    datas_mni = get_mni_datas(pvc)
    if isinstance(datas_mni, dict) and "_error" in datas_mni:
        st.error(f"❌ Timeout ao buscar datas MNI.\n\nDetalhe: `{datas_mni['_error']}`")
        st.stop()

    if not datas_mni:
        st.info("Nenhuma data com logs disponível.")
        st.stop()

    with col2:
        _mni_data_idx = datas_mni.index(_saved_mni["mni_data"]) if _saved_mni["mni_data"] in datas_mni else 0
        data_mni = st.selectbox("Data", datas_mni, index=_mni_data_idx, key="mni_data_sel")
    _cfg.save(mni_data=data_mni)

    st.markdown("---")

    # ── 3. Arquivos ───────────────────────────────────────────────────────
    @st.cache_data(ttl=60)
    def get_mni_arquivos(p, d):
        try:
            return fetch_mni_arquivos(p, d)
        except Exception as e:
            return {"_error": str(e)}

    arquivos_mni = get_mni_arquivos(pvc, data_mni)
    if isinstance(arquivos_mni, dict) and "_error" in arquivos_mni:
        st.error(f"❌ Erro ao listar arquivos MNI.\n\nDetalhe: `{arquivos_mni['_error']}`")
        st.stop()

    if not arquivos_mni:
        st.info("Nenhum arquivo nesta data.")
        st.stop()

    # ── Filtros ───────────────────────────────────────────────────────────
    def _limpar_filtros_mni():
        st.session_state["mni_filter"] = ""
        st.session_state["mni_tipo"]   = "Todos"
        st.session_state["mni_ordem"]  = "Mais recente"
        st.session_state["mni_busca_interna"] = ""
        st.session_state["mni_busca_conteudo"] = ""
        for k in ("mni_xmls", "mni_sel_name", "mni_content_matches",
                  "mni_content_term", "mni_file_sel", "mni_file_sel_box",
                  "mni_pdf_sel", "mni_pdf_par", "mni_pdf_full_par"):
            st.session_state.pop(k, None)

    col_f1, col_f2, col_f3, col_f4 = st.columns([3, 1, 1, 1])
    with col_f1:
        busca_mni = st.text_input("🔎 Filtrar por nome do arquivo",
                                  placeholder="nome, timestamp, UUID...", key="mni_filter")
    with col_f2:
        tipo_mni = st.selectbox("Tipo", ["Todos", "request", "response"], key="mni_tipo")
    with col_f3:
        ordem_mni = st.selectbox("Ordenar", ["Mais recente", "Mais antigo"], key="mni_ordem")
    with col_f4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Limpar filtros", key="mni_btn_limpar", use_container_width=True):
            _limpar_filtros_mni()
            st.rerun()

    # ── Busca por conteúdo ────────────────────────────────────────────────
    with st.expander("🔍 Buscar dentro do conteúdo dos XMLs"):
        col_bc1, col_bc2, col_bc3 = st.columns([4, 1, 1])
        with col_bc1:
            busca_mni_cont = st.text_input(
                "Termo a localizar nos XMLs",
                placeholder="ex: numeroProcesso, CNPJ, erro...",
                key="mni_busca_conteudo",
            )
        with col_bc2:
            st.markdown("<br>", unsafe_allow_html=True)
            btn_buscar_mni = st.button("🔎 Buscar", key="mni_btn_busca_cont")
        with col_bc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ Limpar", key="mni_btn_limpar_cont"):
                st.session_state["mni_busca_conteudo"] = ""
                st.session_state.pop("mni_content_matches", None)
                st.session_state.pop("mni_content_term", None)
                st.rerun()

        mni_cache_key = f"mni_content_cache_{pgmp_mni}_{data_mni}"

        if btn_buscar_mni and busca_mni_cont:
            if mni_cache_key not in st.session_state:
                st.session_state[mni_cache_key] = {}
            content_cache_mni = st.session_state[mni_cache_key]
            matches_mni = []
            prog_mni = st.progress(0, text="Baixando e pesquisando arquivos...")

            for i, a in enumerate(arquivos_mni):
                prog_mni.progress((i + 1) / len(arquivos_mni),
                                  text=f"Pesquisando {i+1}/{len(arquivos_mni)}: {a['name'][:50]}...")
                if a["name"] not in content_cache_mni:
                    try:
                        content_cache_mni[a["name"]] = fetch_xml(a["url"], session=_mni_session())
                    except Exception:
                        content_cache_mni[a["name"]] = ""
                xml_c = content_cache_mni[a["name"]]
                if busca_mni_cont.lower() in xml_c.lower():
                    results_c = search_in_xml(xml_c, busca_mni_cont)
                    matches_mni.append({
                        "name": a["name"], "tipo": a["tipo"],
                        "timestamp": a["timestamp"], "url": a["url"],
                        "hits": len(results_c),
                        "preview": results_c[0]["value"][:100] if results_c else "",
                    })
            prog_mni.empty()
            st.session_state["mni_content_matches"] = matches_mni
            st.session_state["mni_content_term"] = busca_mni_cont
            st.session_state[mni_cache_key] = content_cache_mni

        matches_mni = st.session_state.get("mni_content_matches", [])
        term_mni = st.session_state.get("mni_content_term", "")
        if matches_mni and term_mni:
            st.success(f"**{len(matches_mni)}** arquivo(s) contêm `{term_mni}`")
            df_mni_matches = pd.DataFrame([{
                "Horário": m["timestamp"].strftime("%H:%M:%S") if m["timestamp"] else "",
                "Tipo": m["tipo"], "Arquivo": m["name"],
                "Ocorrências": m["hits"], "Preview": m["preview"],
            } for m in matches_mni])
            evt_mm = st.dataframe(df_mni_matches, use_container_width=True, hide_index=True,
                                  on_select="rerun", selection_mode="single-row", key="mni_df_matches")
            sel_mm = evt_mm.selection.rows if evt_mm.selection.rows else []
            if sel_mm:
                st.session_state["mni_file_sel"] = df_mni_matches.iloc[sel_mm[0]]["Arquivo"]
                st.session_state["mni_file_sel_box"] = df_mni_matches.iloc[sel_mm[0]]["Arquivo"]
                st.info(f"✅ Arquivo selecionado: `{st.session_state['mni_file_sel']}`")
        elif term_mni and not matches_mni:
            st.warning(f"Nenhum arquivo contém `{term_mni}`.")

    # ── Monta lista de arquivos ───────────────────────────────────────────
    rows_mni = []
    for a in arquivos_mni:
        if tipo_mni != "Todos" and a["tipo"] != tipo_mni:
            continue
        if busca_mni and busca_mni.lower() not in a["name"].lower():
            continue
        rows_mni.append({
            "Horário": a["timestamp"].strftime("%H:%M:%S") if a["timestamp"] else "",
            "Tipo": a["tipo"],
            "Arquivo": a["name"],
            "UUID": a.get("uuid", ""),
            "_url": a["url"],
            "_ts": a["timestamp"] or datetime.min,
            "_tipo": a["tipo"],
            "_uuid": a.get("uuid", ""),
        })

    if not rows_mni:
        st.info("Sem resultados para o filtro.")
        st.stop()

    df_mni = pd.DataFrame(rows_mni)
    df_mni = df_mni.sort_values("_ts", ascending=(ordem_mni == "Mais antigo"))
    df_mni = df_mni.reset_index(drop=True)

    st.subheader(f"{len(df_mni)} arquivo(s) — {pgmp_mni.upper()} · {data_mni}")

    # Tabela clicável
    evt_mni = st.dataframe(
        df_mni[["Horário", "Tipo", "Arquivo", "UUID"]],
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="mni_df_sel",
    )
    sel_mni_rows = evt_mni.selection.rows if evt_mni.selection.rows else []
    if sel_mni_rows:
        fname_mni = df_mni.iloc[sel_mni_rows[0]]["Arquivo"]
        st.session_state["mni_file_sel"] = fname_mni
        st.session_state["mni_file_sel_box"] = fname_mni

    # CSV da tabela
    csv_mni_rows = [{"PGMP": pgmp_mni.upper(), "Data": data_mni,
                     "Arquivo": r["Arquivo"], "Tipo": r["Tipo"], "Horário": r["Horário"]}
                    for r in rows_mni]
    st.download_button(
        "⬇️ Exportar tabela (CSV)",
        data=export_csv(csv_mni_rows, ["PGMP", "Data", "Arquivo", "Tipo", "Horário"]),
        file_name=f"{pgmp_mni}_{data_mni}.csv",
        mime="text/csv", key="mni_csv_table",
    )

    st.markdown("---")
    st.subheader("📂 Visualizar e Exportar")

    # Selectbox sincronizado com clique na tabela
    all_mni_files = df_mni["Arquivo"].tolist()
    # Inicializa session_state apenas no primeiro carregamento (config como fallback).
    # Cliques na tabela já setam mni_file_sel_box diretamente — não sobrescrever.
    if "mni_file_sel_box" not in st.session_state:
        fallback_mni = _cfg.load().get("mni_file") or all_mni_files[0]
        st.session_state["mni_file_sel_box"] = fallback_mni if fallback_mni in all_mni_files else all_mni_files[0]
    elif st.session_state["mni_file_sel_box"] not in all_mni_files:
        st.session_state["mni_file_sel_box"] = all_mni_files[0]

    arq_mni_sel = st.selectbox(
        "Arquivo selecionado", all_mni_files,
        key="mni_file_sel_box",
    )
    st.session_state["mni_file_sel"] = arq_mni_sel
    _cfg.save(mni_file=arq_mni_sel)

    arq_mni_row  = df_mni[df_mni["Arquivo"] == arq_mni_sel].iloc[0]
    arq_mni_tipo = arq_mni_row["_tipo"]
    arq_mni_ts   = arq_mni_row["_ts"]
    arq_mni_uuid = arq_mni_row["_uuid"]

    # Auto-pareia por UUID ou timestamp
    tipo_op_mni = "response" if arq_mni_tipo == "request" else "request"
    df_op_mni = df_mni[df_mni["_tipo"] == tipo_op_mni].copy()
    par_mni = None
    par_mni_metodo = ""

    if not df_op_mni.empty:
        if arq_mni_uuid:
            uuid_m = df_op_mni[df_op_mni["_uuid"] == arq_mni_uuid]
            if not uuid_m.empty:
                par_mni = uuid_m.iloc[0]
                par_mni_metodo = "mesmo UUID"
        if par_mni is None:
            df_op_mni["_diff"] = (df_op_mni["_ts"] - arq_mni_ts).abs().dt.total_seconds()
            melhor_mni = df_op_mni.nsmallest(1, "_diff").iloc[0]
            if melhor_mni["_diff"] <= 120:
                par_mni = melhor_mni
                par_mni_metodo = f"timestamp mais próximo ({int(melhor_mni['_diff'])}s)"

    if par_mni is not None:
        st.info(f"🔗 **{tipo_op_mni.capitalize()} pareado** ({par_mni_metodo}): `{par_mni['Arquivo']}`")

    # Busca interna
    col_bi1, col_bi2 = st.columns([5, 1])
    with col_bi1:
        busca_mni_int = st.text_input("🔍 Buscar nos XMLs",
                                      placeholder="processo, CNPJ, erro...",
                                      key="mni_busca_interna")
    with col_bi2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Limpar", key="mni_btn_limpar_inner", use_container_width=True):
            st.session_state["mni_busca_interna"] = ""
            for k in ("mni_xmls", "mni_sel_name", "mni_pdf_sel",
                      "mni_pdf_par", "mni_pdf_full_par"):
                st.session_state.pop(k, None)
            st.rerun()

    if st.button("📥 Carregar arquivo + par", key="mni_load"):
        mni_xmls = {"_sel_name": arq_mni_sel}
        for label, row_d in [("sel", arq_mni_row), ("par", par_mni)]:
            if row_d is None:
                mni_xmls[label] = None
                continue
            with st.spinner(f"Baixando {row_d['Tipo']}..."):
                try:
                    mni_xmls[label] = {
                        "xml":  fetch_xml(row_d["_url"], session=_mni_session()),
                        "name": row_d["Arquivo"],
                        "tipo": row_d["_tipo"],
                    }
                except Exception as e:
                    mni_xmls[label] = {"xml": f"<!-- Erro: {e} -->",
                                       "name": row_d["Arquivo"], "tipo": row_d["_tipo"]}
        st.session_state["mni_xmls"] = mni_xmls

    mni_xmls = st.session_state.get("mni_xmls", {})
    if mni_xmls and mni_xmls.get("_sel_name") == arq_mni_sel:
        ref_xml_mni = (mni_xmls.get("sel") or {}).get("xml", "")
        summary_mni = extract_soap_summary(ref_xml_mni) if ref_xml_mni else {}
        if summary_mni:
            cols = st.columns(min(len(summary_mni), 4))
            for i, (k, v) in enumerate(list(summary_mni.items())[:4]):
                cols[i].metric(k, v[:60])
            st.markdown("")

        # Busca interna nos dois XMLs
        if busca_mni_int:
            for label in ("sel", "par"):
                entry = mni_xmls.get(label)
                if not entry or not entry.get("xml"):
                    continue
                results = search_in_xml(entry["xml"], busca_mni_int)
                badge = f"**{entry['tipo'].upper()}** (`{entry['name']}`)"
                if results:
                    st.success(f"{badge} — {len(results)} ocorrência(s) de `{busca_mni_int}`")
                    for r in results[:30]:
                        with st.expander(f"`{r['tag']}` — {r['value'][:80]}"):
                            st.code(r["context"], language="xml")
                            if r["path"]:
                                st.caption(f"XPath: `{r['path']}`")
                else:
                    st.info(f"{badge} — sem resultados.")

        # ── Abas: selecionado + par ───────────────────────────────────────
        tab_label_s = f"{'📤' if arq_mni_tipo == 'request' else '📥'} {arq_mni_tipo.capitalize()} (selecionado)"
        tab_label_p = f"{'📥' if tipo_op_mni == 'response' else '📤'} {tipo_op_mni.capitalize()} (par)"
        tab_mni_sel, tab_mni_par = st.tabs([tab_label_s, tab_label_p])

        for tab, entry, kp in [(tab_mni_sel, mni_xmls.get("sel"), "sel"),
                                (tab_mni_par, mni_xmls.get("par"), "par")]:
            with tab:
                if not entry or not entry.get("xml"):
                    st.info("Arquivo não carregado ou não encontrado.")
                    continue
                xml_t    = entry["xml"]
                nome_arq = entry["name"]
                tipo_arq = entry["tipo"]

                st.caption(f"`{nome_arq}`")
                pretty = pretty_print_xml(xml_t)
                st.code(pretty[:30_000], language="xml")
                if len(pretty) > 30_000:
                    st.caption("_(truncado em 30.000 chars)_")

                st.markdown("**Exportar:**")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.download_button(
                        "⬇️ XML formatado",
                        data=export_xml_formatted(xml_t),
                        file_name=nome_arq,
                        mime="application/xml",
                        key=f"mni_dl_{kp}_xml",
                    )
                with c2:
                    if st.button("⬇️ Gerar PDF", key=f"mni_btn_{kp}_pdf"):
                        with st.spinner("Gerando PDF..."):
                            st.session_state[f"mni_pdf_{kp}"] = export_pdf(
                                xml_t,
                                titulo=f"{pgmp_mni.upper()} · {data_mni}",
                                subtitulo=nome_arq, tipo=tipo_arq,
                            )
                    if f"mni_pdf_{kp}" in st.session_state:
                        st.download_button(
                            "⬇️ Baixar PDF",
                            data=st.session_state[f"mni_pdf_{kp}"],
                            file_name=nome_arq.replace(".xml", ".pdf"),
                            mime="application/pdf",
                            key=f"mni_dl_{kp}_pdf",
                        )
                with c3:
                    s_t = extract_soap_summary(xml_t)
                    s_t.update({"pgmp": pgmp_mni, "data": data_mni,
                                "arquivo": nome_arq, "tipo": tipo_arq})
                    st.download_button(
                        "⬇️ CSV (resumo)",
                        data=export_csv([s_t], list(s_t.keys())),
                        file_name=nome_arq.replace(".xml", ".csv"),
                        mime="text/csv",
                        key=f"mni_dl_{kp}_csv",
                    )

        # ── Exportar par completo ─────────────────────────────────────────
        st.markdown("---")
        st.markdown("**Exportar par completo:**")
        cp1, cp2, cp3 = st.columns(3)

        sel_e = mni_xmls.get("sel")
        par_e = mni_xmls.get("par")
        xml_req_mni = (sel_e["xml"] if arq_mni_tipo == "request" else (par_e["xml"] if par_e else None))
        xml_res_mni = (sel_e["xml"] if arq_mni_tipo == "response" else (par_e["xml"] if par_e else None))

        with cp1:
            if st.button("💾 Salvar consulta", key="mni_save"):
                p = save_query(arq_mni_sel, {
                    "pgmp": pgmp_mni, "data": data_mni,
                    "arquivo": arq_mni_sel,
                    "par": par_mni["Arquivo"] if par_mni is not None else "",
                    "busca": busca_mni_int, **summary_mni,
                })
                st.success(f"Salvo: `{p.name}`")

        with cp2:
            items_mni = [(e["name"], pretty_print_xml(e["xml"]))
                         for e in [sel_e, par_e] if e and e.get("xml")]
            if items_mni:
                st.download_button(
                    "⬇️ ZIP (XML formatados)",
                    data=export_zip(items_mni),
                    file_name=f"{arq_mni_sel}.zip",
                    mime="application/zip",
                    key="mni_dl_par_zip",
                )

        with cp3:
            if st.button("⬇️ Gerar PDF (par completo)", key="mni_btn_full_par_pdf"):
                with st.spinner("Gerando PDF..."):
                    st.session_state["mni_pdf_full_par"] = export_pdf_par(
                        xml_req_mni, xml_res_mni,
                        titulo=f"{pgmp_mni.upper()} · {data_mni}",
                        subtitulo=arq_mni_sel,
                    )
            if "mni_pdf_full_par" in st.session_state:
                st.download_button(
                    "⬇️ Baixar PDF (par)",
                    data=st.session_state["mni_pdf_full_par"],
                    file_name=f"{arq_mni_sel}.pdf",
                    mime="application/pdf",
                    key="mni_dl_full_par_pdf",
                )

        # ZIP data inteira
        if st.button("📦 Exportar data inteira (ZIP)", key="mni_zip_all"):
            with st.spinner("Baixando todos os arquivos..."):
                items_all = []
                for _, row_z in df_mni.iterrows():
                    try:
                        c = fetch_xml(row_z["_url"], session=_mni_session())
                        items_all.append((row_z["Arquivo"], pretty_print_xml(c)))
                    except Exception:
                        pass
            zb_mni = export_zip(items_all)
            st.download_button(
                "⬇️ Baixar ZIP completo",
                data=zb_mni,
                file_name=f"{pgmp_mni}_{data_mni}.zip",
                mime="application/zip",
                key="mni_zip_all_dl",
            )


# ═══════════════════════════════════════════════════════════════════════════
# SEÇÃO CONSULTAS SALVAS
# ═══════════════════════════════════════════════════════════════════════════
elif section == "💾 Consultas Salvas":
    st.header("💾 Consultas Salvas")

    queries = load_saved_queries()
    if not queries:
        st.info("Nenhuma consulta salva.")
        st.stop()

    st.metric("Total", len(queries))

    filtro = st.text_input("🔎 Filtrar", placeholder="PGMP, operação, processo...")

    rows_s = []
    for q in queries:
        rows_s.append({
            "Nome": q.get("query_name", ""),
            "PGMP": q.get("pgmp", ""),
            "Operação": q.get("operacao", ""),
            "Data": q.get("data", ""),
            "Processo": q.get("numeroProcesso", ""),
            "Salvo em": q.get("saved_at", "")[:16],
            "_data": q,
        })

    df_s = pd.DataFrame(rows_s)
    if filtro:
        mask = df_s.apply(lambda row: filtro.lower() in str(row.values).lower(), axis=1)
        df_s = df_s[mask]

    df_s = df_s.sort_values("Salvo em", ascending=False)
    st.dataframe(df_s[["Nome", "PGMP", "Operação", "Data", "Processo", "Salvo em"]],
                 use_container_width=True, hide_index=True)

    all_json = json.dumps(
        [q["_data"] for q in queries], ensure_ascii=False, indent=2, default=str
    )
    st.download_button(
        "⬇️ Exportar todas (JSON)",
        data=all_json.encode("utf-8"),
        file_name="consultas_salvas.json",
        mime="application/json",
    )

    if not df_s.empty:
        sel = st.selectbox("Ver detalhe", df_s["Nome"].tolist())
        row_sel = df_s[df_s["Nome"] == sel].iloc[0]["_data"]
        with st.expander("Detalhes completos"):
            st.json(row_sel)
