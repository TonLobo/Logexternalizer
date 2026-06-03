"""
Módulo para buscar XMLs do logexternalizer (pgmbox) e de arquivos locais.
"""
import os
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

LOG_URL = "http://softplan_read:JRxXuVsZ697F@logexternalizer.sajcloud.com.br/pj/pgmbox/index.html"
DATA_DIR = Path(__file__).parent / "data"
SAVED_QUERIES_DIR = Path(__file__).parent / "saved_queries"


def fetch_pgmbox_entries(
    url: str = LOG_URL,
    timeout: int = 30,
    max_entries: Optional[int] = None,
) -> list[dict]:
    """
    Busca entradas de XML do pgmbox. Retorna lista de dicts com:
    {id, date, title, content_url, raw_xml, source='remote'}
    """
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        return [{"error": str(e)}]

    soup = BeautifulSoup(resp.text, "html.parser")
    entries = []

    # Tenta encontrar links/tabelas com entradas de XML
    links = soup.find_all("a", href=True)
    rows = soup.find_all("tr")

    if rows:
        for row in rows[:max_entries] if max_entries else rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            link_el = row.find("a", href=True)
            entry = {
                "source": "remote",
                "cells": texts,
                "link": link_el["href"] if link_el else None,
                "raw_html": str(row),
            }
            entries.append(entry)
    elif links:
        for link in (links[:max_entries] if max_entries else links):
            href = link["href"]
            if href.endswith(".xml") or "xml" in href.lower():
                entries.append({
                    "source": "remote",
                    "link": href,
                    "title": link.get_text(strip=True),
                })

    return entries if entries else [{"raw_html": resp.text, "source": "remote"}]


def fetch_xml_from_url(url: str, base_url: str = LOG_URL, timeout: int = 30) -> str:
    """Busca o conteúdo XML de uma URL relativa ou absoluta."""
    if not url.startswith("http"):
        from urllib.parse import urljoin
        url = urljoin(base_url, url)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def load_local_xml_files(directory: str = None) -> list[dict]:
    """
    Carrega arquivos XML locais de um diretório.
    Retorna lista de dicts com {filename, path, raw_xml, source='local'}.
    """
    target = Path(directory) if directory else DATA_DIR
    if not target.exists():
        return []

    files = []
    for f in sorted(target.glob("*.xml")):
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            files.append({
                "filename": f.name,
                "path": str(f),
                "raw_xml": content,
                "source": "local",
                "file_mtime": datetime.fromtimestamp(f.stat().st_mtime),
            })
        except OSError:
            continue
    return files


def save_query(name: str, data: dict) -> Path:
    """Salva uma consulta como JSON na pasta saved_queries."""
    SAVED_QUERIES_DIR.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^\w\-]", "_", name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SAVED_QUERIES_DIR / f"{safe_name}_{ts}.json"

    # Limita tamanho do raw_xml no JSON salvo para não inflar o arquivo
    payload = {k: v for k, v in data.items() if k != "raw_xml"}
    payload["saved_at"] = datetime.now().isoformat()
    payload["query_name"] = name

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_saved_queries() -> list[dict]:
    """Carrega todas as consultas salvas."""
    SAVED_QUERIES_DIR.mkdir(exist_ok=True)
    queries = []
    for f in sorted(SAVED_QUERIES_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_file"] = str(f)
            queries.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return queries


def export_xml(content: str, filename: str) -> Path:
    """Exporta conteúdo XML para a pasta exports."""
    exports_dir = Path(__file__).parent / "exports"
    exports_dir.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w\-.]", "_", filename)
    if not safe.endswith(".xml"):
        safe += ".xml"
    path = exports_dir / safe
    path.write_text(content, encoding="utf-8")
    return path
