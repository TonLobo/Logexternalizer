"""
Utilitários para parse e extração de informações de XMLs SoapUI e logexternalizer.
"""
import re
from datetime import datetime
from typing import Optional
from lxml import etree
from bs4 import BeautifulSoup


SOAPUI_NS = "http://eviware.com/soapui/config"


def parse_soapui_project(xml_content: str, filename: str = "") -> dict:
    """Extrai metadados de um projeto SoapUI XML."""
    try:
        root = etree.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
    except etree.XMLSyntaxError:
        return {}

    ns = {"con": SOAPUI_NS}

    def attr(name):
        return root.get(name, "")

    name = attr("name") or filename.replace("-soapui-project.xml", "")
    soapui_version = attr("soapui-version")
    project_id = attr("id")

    # Coleta interfaces (endpoints WSDL/REST)
    interfaces = []
    for iface in root.findall("con:interface", ns):
        iface_name = iface.get("name", "")
        definition = iface.get("definition", "")
        iface_type = iface.get("type", "")
        interfaces.append({"name": iface_name, "definition": definition, "type": iface_type})

    # Tenta extrair data do conteúdo
    date = _extract_date_from_content(xml_content)

    return {
        "project_name": name,
        "project_id": project_id,
        "soapui_version": soapui_version,
        "interfaces": interfaces,
        "interface_count": len(interfaces),
        "endpoints": [i["definition"] for i in interfaces if i["definition"]],
        "date": date,
        "filename": filename,
        "raw_xml": xml_content,
    }


def parse_log_entry(xml_content: str) -> dict:
    """Extrai dados de uma entrada de log XML do logexternalizer."""
    try:
        root = etree.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
    except etree.XMLSyntaxError:
        return {}

    def get_text(tag: str) -> str:
        el = root.find(".//" + tag)
        if el is None:
            # tenta sem namespace
            for child in root.iter():
                if child.tag.split("}")[-1] == tag:
                    return (child.text or "").strip()
        return (el.text or "").strip() if el is not None else ""

    date = _extract_date_from_content(xml_content)

    return {
        "date": date,
        "raw_xml": xml_content,
    }


def search_in_xml(xml_content: str, query: str) -> list[dict]:
    """
    Busca um termo dentro do XML e retorna os contextos onde foi encontrado.
    Retorna lista de {tag, path, value, context}.
    """
    if not query:
        return []

    query_lower = query.lower()
    results = []

    try:
        root = etree.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
    except etree.XMLSyntaxError:
        # fallback: busca de texto puro
        lines = xml_content.splitlines()
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                results.append({
                    "tag": f"linha {i+1}",
                    "path": "",
                    "value": line.strip(),
                    "context": _get_line_context(lines, i),
                })
        return results

    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        text = (el.text or "").strip()
        if query_lower in text.lower():
            results.append({
                "tag": tag,
                "path": _get_xpath(el),
                "value": text[:300],
                "context": text[:500],
            })
        for attr_name, attr_val in el.attrib.items():
            if query_lower in attr_val.lower():
                results.append({
                    "tag": f"{tag}[@{attr_name}]",
                    "path": _get_xpath(el),
                    "value": attr_val[:300],
                    "context": f"@{attr_name}={attr_val[:300]}",
                })

    return results


def pretty_print_xml(xml_content: str) -> str:
    """Formata o XML com indentação legível."""
    try:
        root = etree.fromstring(xml_content.encode("utf-8") if isinstance(xml_content, str) else xml_content)
        return etree.tostring(root, pretty_print=True, encoding="unicode")
    except etree.XMLSyntaxError:
        return xml_content


def _extract_date_from_content(content: str) -> Optional[datetime]:
    """Tenta extrair uma data do conteúdo XML."""
    patterns = [
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
        r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}",
        r"\d{2}/\d{2}/\d{4}",
        r"\d{4}-\d{2}-\d{2}",
    ]
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]
    for pattern, fmt in zip(patterns, formats):
        match = re.search(pattern, content)
        if match:
            try:
                return datetime.strptime(match.group(), fmt)
            except ValueError:
                continue
    return None


def _get_xpath(element) -> str:
    """Retorna um XPath simplificado para o elemento."""
    parts = []
    el = element
    while el is not None:
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        parts.append(tag)
        el = el.getparent()
    return "/" + "/".join(reversed(parts))


def _get_line_context(lines: list, index: int, window: int = 2) -> str:
    start = max(0, index - window)
    end = min(len(lines), index + window + 1)
    return "\n".join(lines[start:end])
