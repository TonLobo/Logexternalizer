"""
Acesso ao logexternalizer — seção LOGS-INTEGRAÇÃO (Logs-HUB e Logs-MNI).

Hierarquia HUB:
  http://172.50.1.164:9999/s3-hub/{hash}/{operacao}/{data}/{arquivo}.xml

Hierarquia MNI:
  http://172.50.1.164:9999/{pgmp}/{pvc}/{data}/{arquivo}.xml

Página índice (pgmbox):
  http://logexternalizer.sajcloud.com.br/pj/pgmbox/index.html
"""
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ── Credenciais / Endpoints ────────────────────────────────────────────────
PGMBOX_INDEX = "http://logexternalizer.sajcloud.com.br/pj/pgmbox/index.html"
PGMBOX_CREDS = ("softplan_read", "JRxXuVsZ697F")

HUB_BASE     = "http://172.50.1.164:9999"
HUB_CREDS    = ("dockerlogs", "@Softplan")   # @ literal na senha

MNI_BASE     = "http://172.50.1.164:9999"
MNI_CREDS    = ("dockerlogs", "@Softplan")

TIMEOUT_FAST = 300  # listagens de diretório
TIMEOUT_XML  = 300  # download de XML

SAVED_DIR    = Path(__file__).parent / "saved_queries"
EXPORTS_DIR  = Path(__file__).parent / "exports"

_SESSION_HUB = None
_SESSION_MNI = None


def _hub_session() -> requests.Session:
    global _SESSION_HUB
    if _SESSION_HUB is None:
        s = requests.Session()
        s.auth = HUB_CREDS
        _SESSION_HUB = s
    return _SESSION_HUB


def _mni_session() -> requests.Session:
    global _SESSION_MNI
    if _SESSION_MNI is None:
        s = requests.Session()
        s.auth = MNI_CREDS
        _SESSION_MNI = s
    return _SESSION_MNI


# ══════════════════════════════════════════════════════════════════════════
# LOGS-HUB
# ══════════════════════════════════════════════════════════════════════════

def fetch_hub_pgmps() -> list[dict]:
    """
    Lê o pgmbox/index.html e extrai todos os links LOGS-HUB (s3-hub).
    Retorna lista de {label, url, hash}.
    """
    resp = requests.get(PGMBOX_INDEX, auth=PGMBOX_CREDS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    ambientes = soup.find_all(class_="ambiente")
    if len(ambientes) < 2:
        return []

    node = ambientes[1].parent
    found = False
    pgmps = []
    from bs4 import Tag
    for child in node.children:
        if not isinstance(child, Tag):
            continue
        if "INTEGRA" in child.get_text():
            found = True
        if found:
            for a in child.find_all("a", href=True):
                href = a["href"]
                label = a.get_text(strip=True)
                if "s3-hub" in href and label.startswith("PGMP"):
                    m = re.search(r"/s3-hub/([^/]+)/", href)
                    h = m.group(1) if m else ""
                    pgmps.append({"label": label, "url": href, "hash": h})
    return pgmps


def fetch_hub_operacoes(hub_hash: str) -> list[str]:
    """Lista as operações disponíveis para um PGMP (ex: consultar-arvore-documentos)."""
    url = f"{HUB_BASE}/s3-hub/{hub_hash}/"
    resp = _hub_session().get(url, timeout=TIMEOUT_FAST)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [
        a.get_text(strip=True).rstrip("/")
        for a in soup.find_all("a", href=True)
        if a["href"] not in ("../", "/") and not a["href"].startswith("http")
    ]


def fetch_hub_datas(hub_hash: str, operacao: str) -> list[str]:
    """Lista as datas disponíveis para uma operação (YYYY-MM-DD)."""
    url = f"{HUB_BASE}/s3-hub/{hub_hash}/{operacao}/"
    resp = _hub_session().get(url, timeout=TIMEOUT_FAST)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    datas = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"\d{4}-\d{2}-\d{2}/", href):
            datas.append(href.rstrip("/"))
    return sorted(datas, reverse=True)


def fetch_hub_arquivos(hub_hash: str, operacao: str, data: str) -> list[dict]:
    """
    Lista os XMLs de uma data.
    Retorna [{name, url, size, modified, tipo (request|response)}].
    """
    url = f"{HUB_BASE}/s3-hub/{hub_hash}/{operacao}/{data}/"
    resp = _hub_session().get(url, timeout=TIMEOUT_FAST)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    arquivos = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.endswith(".xml"):
            continue
        # Usa o href como nome real — o texto exibido pode estar truncado pelo servidor
        name = href.split("/")[-1]
        tipo = "response" if "response" in name else "request"
        ts = _extract_ts_from_name(name, date_ctx=data)
        arquivos.append({
            "name": name,
            "url": f"{HUB_BASE}/s3-hub/{hub_hash}/{operacao}/{data}/{href}",
            "tipo": tipo,
            "timestamp": ts,
            "uuid": _extract_uuid_from_name(name),
        })
    return sorted(arquivos, key=lambda x: x["timestamp"] or datetime.min)


def fetch_xml(url: str, session: requests.Session = None, timeout: int = TIMEOUT_XML) -> str:
    """Baixa o conteúdo de um XML."""
    s = session or _hub_session()
    resp = s.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ══════════════════════════════════════════════════════════════════════════
# LOGS-MNI
# ══════════════════════════════════════════════════════════════════════════

def fetch_mni_pgmps() -> list[str]:
    """Lista os PGMP disponíveis no servidor MNI."""
    resp = _mni_session().get(f"{MNI_BASE}/", timeout=TIMEOUT_FAST)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    pgmps = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"pgm[a-z0-9]+/", href, re.I):
            pgmps.append(href.rstrip("/"))
    return sorted(pgmps)


def fetch_mni_pvc(pgmp: str) -> Optional[str]:
    """Retorna o caminho do PVC para um PGMP."""
    resp = _mni_session().get(f"{MNI_BASE}/{pgmp}/", timeout=TIMEOUT_FAST)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "mni-" in href.lower() and href not in ("../",):
            return f"{pgmp}/{href.rstrip('/')}"
    return None


def fetch_mni_datas(pvc_path: str) -> list[str]:
    """Lista as datas de log disponíveis para um PVC."""
    resp = _mni_session().get(f"{MNI_BASE}/{pvc_path}/", timeout=TIMEOUT_FAST)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    datas = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"\d{4}-\d{2}-\d{2}/", href):
            datas.append(href.rstrip("/"))
    return sorted(datas, reverse=True)


def fetch_mni_arquivos(pvc_path: str, data: str) -> list[dict]:
    """Lista os arquivos de log MNI de uma data."""
    url = f"{MNI_BASE}/{pvc_path}/{data}/"
    resp = _mni_session().get(url, timeout=TIMEOUT_FAST)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    arquivos = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href in ("../",) or "/" in href:
            continue
        name = href.split("/")[-1]  # nome real do href, não o texto truncado
        tipo = "response" if "response" in name else "request"
        ts = _extract_ts_from_name(name, date_ctx=data)
        arquivos.append({
            "name": name,
            "url": f"{MNI_BASE}/{pvc_path}/{data}/{href}",
            "tipo": tipo,
            "timestamp": ts,
            "uuid": _extract_uuid_from_name(name),
        })
    return sorted(arquivos, key=lambda x: x["timestamp"] or datetime.min)


# ══════════════════════════════════════════════════════════════════════════
# SALVAR / EXPORTAR
# ══════════════════════════════════════════════════════════════════════════

def save_query(name: str, metadata: dict) -> Path:
    SAVED_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SAVED_DIR / f"{safe}_{ts}.json"
    payload = {k: v for k, v in metadata.items() if k != "raw_xml"}
    payload["saved_at"] = datetime.now().isoformat()
    payload["query_name"] = name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_saved_queries() -> list[dict]:
    SAVED_DIR.mkdir(exist_ok=True)
    queries = []
    for f in sorted(SAVED_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_file"] = str(f)
            queries.append(data)
        except Exception:
            continue
    return queries


def export_xml_file(content: str, filename: str) -> Path:
    EXPORTS_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w\-.]", "_", filename)
    if not safe.endswith(".xml"):
        safe += ".xml"
    path = EXPORTS_DIR / safe
    path.write_text(content, encoding="utf-8")
    return path


def export_zip(items: list[tuple[str, str]]) -> bytes:
    """Recebe [(filename, xml_content)] e retorna bytes do ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, content in items:
            zf.writestr(fname, content)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _extract_ts_from_name(name: str, date_ctx: Optional[str] = None) -> Optional[datetime]:
    """
    Extrai datetime do nome do arquivo. Reconhece dois padrões:
      1. YYYY-MM-DD-HH-MM-SS  (ex: _2025-05-30-18-02-13-717.xml)
      2. HH-MM-SS-mmm_        (ex: 00-41-08-766_request_... — só hora, sem data)
    Para o padrão 2, usa date_ctx (YYYY-MM-DD) para completar a data.
    """
    # Padrão 1: data completa no nome
    m = re.search(r"(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})", name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d-%H-%M-%S")
        except ValueError:
            pass

    # Padrão 2: HH-MM-SS-mmm no início do nome (ex: 00-41-08-766_request_...)
    m2 = re.match(r"^(\d{2})-(\d{2})-(\d{2})-(\d{3})[_\-]", name)
    if m2:
        hh, mm, ss, ms = m2.groups()
        date_part = date_ctx or datetime.today().strftime("%Y-%m-%d")
        try:
            return datetime.strptime(
                f"{date_part} {hh}:{mm}:{ss}.{ms}", "%Y-%m-%d %H:%M:%S.%f"
            )
        except ValueError:
            pass

    return None


def _extract_uuid_from_name(name: str) -> str:
    """
    Extrai o UUID do nome do arquivo.
    Suporta padrões:
      - {op}_{uuid}_{tipo}_{ts}.xml
      - {HH-MM-SS-mmm}_{tipo}_{uuid}.xml
    """
    m = re.search(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", name)
    return m.group(1) if m else ""
