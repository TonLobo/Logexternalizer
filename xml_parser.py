"""
Parse e busca em XMLs SOAP do logexternalizer (MNI / HUB).
"""
import re
from typing import Optional
from lxml import etree


def pretty_print_xml(xml_content: str) -> str:
    """Formata XML com indentação. Trata MTOM/multipart retornando o fragmento XML."""
    content = _extract_xml_from_mtom(xml_content)
    try:
        root = etree.fromstring(content.encode("utf-8") if isinstance(content, str) else content)
        return etree.tostring(root, pretty_print=True, encoding="unicode")
    except etree.XMLSyntaxError:
        return content


def search_in_xml(xml_content: str, query: str) -> list[dict]:
    """
    Busca termo dentro do XML. Retorna [{tag, path, value, context}].
    """
    if not query:
        return []
    query_lower = query.lower()
    content = _extract_xml_from_mtom(xml_content)
    results = []

    try:
        root = etree.fromstring(content.encode("utf-8") if isinstance(content, str) else content)
    except etree.XMLSyntaxError:
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                results.append({
                    "tag": f"linha {i+1}",
                    "path": "",
                    "value": line.strip(),
                    "context": "\n".join(lines[start:end]),
                })
        return results

    for el in root.iter():
        tag = _local(el.tag)
        text = (el.text or "").strip()
        if text and query_lower in text.lower():
            results.append({
                "tag": tag,
                "path": _xpath(el),
                "value": text[:400],
                "context": text[:600],
            })
        for attr_name, attr_val in el.attrib.items():
            if query_lower in attr_val.lower():
                results.append({
                    "tag": f"{tag}[@{_local(attr_name)}]",
                    "path": _xpath(el),
                    "value": attr_val[:400],
                    "context": f"@{_local(attr_name)}={attr_val[:400]}",
                })
    return results


def extract_soap_summary(xml_content: str) -> dict:
    """
    Extrai metadados chave de um envelope SOAP MNI:
    operacao, numeroProcesso, idConsultante, orgao, tipo (request/response).
    """
    content = _extract_xml_from_mtom(xml_content)
    summary = {}
    try:
        root = etree.fromstring(content.encode("utf-8") if isinstance(content, str) else content)
    except etree.XMLSyntaxError:
        return summary

    # Operação = primeira tag dentro do Body
    body = _find_local(root, "Body")
    if body is not None:
        children = list(body)
        if children:
            summary["operacao"] = _local(children[0].tag)

    # Campos comuns MNI
    for tag in ["numeroProcesso", "idConsultante", "orgaoCooperado",
                "codigoErro", "descricaoErro", "dataHora"]:
        el = _find_local(root, tag)
        if el is not None and el.text:
            summary[tag] = el.text.strip()[:200]

    return summary


# ── helpers internos ────────────────────────────────────────────────────

def _extract_xml_from_mtom(content: str) -> str:
    """Se for resposta MTOM/multipart, extrai o fragmento XML principal."""
    if content.startswith("--uuid") or content.startswith("--MIMEBoundary"):
        # Pega o bloco que contém o XML SOAP
        parts = re.split(r"--(?:uuid|MIMEBoundary)[^\r\n]*", content)
        for part in parts:
            stripped = part.strip()
            # Remove headers MIME
            if "\r\n\r\n" in stripped:
                _, body = stripped.split("\r\n\r\n", 1)
            elif "\n\n" in stripped:
                _, body = stripped.split("\n\n", 1)
            else:
                body = stripped
            body = body.strip()
            if body.startswith("<") and ("Envelope" in body or "Body" in body):
                return body
        # Fallback: primeiro bloco com <
        for part in parts:
            idx = part.find("<")
            if idx >= 0:
                return part[idx:]
    return content


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _find_local(root, local_name: str):
    for el in root.iter():
        if _local(el.tag) == local_name:
            return el
    return None


def _xpath(element) -> str:
    parts = []
    el = element
    while el is not None:
        parts.append(_local(el.tag))
        el = el.getparent()
    return "/" + "/".join(reversed(parts))
