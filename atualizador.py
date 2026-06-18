"""
Verifica se há nova versão disponível e aplica a atualização automaticamente.
A fonte é configurada em update_config.txt (URL HTTP ou caminho de rede UNC).
"""
import os
import shutil
import tempfile
import zipfile

# Arquivos que nunca serão sobrescritos pela atualização
_PROTEGIDOS = {"config.json", "update_config.txt", "LogsSAJ.exe", "version.txt"}


def _ler_fonte(base_dir: str) -> str:
    cfg = os.path.join(base_dir, "update_config.txt")
    if not os.path.exists(cfg):
        return ""
    for linha in open(cfg, encoding="utf-8"):
        linha = linha.strip()
        if linha and not linha.startswith("#"):
            return linha
    return ""


def _versao_local(base_dir: str) -> str:
    vf = os.path.join(base_dir, "version.txt")
    return open(vf, encoding="utf-8").read().strip() if os.path.exists(vf) else "0.0.0"


def _versao_remota(fonte: str) -> str | None:
    try:
        if fonte.startswith(("http://", "https://")):
            import urllib.request
            url = fonte.rstrip("/") + "/version.txt"
            with urllib.request.urlopen(url, timeout=5) as r:
                return r.read().decode().strip()
        else:
            vf = os.path.join(fonte, "version.txt")
            return open(vf, encoding="utf-8").read().strip() if os.path.exists(vf) else None
    except Exception:
        return None


def _baixar_zip(fonte: str, destino: str, status_fn) -> bool:
    try:
        if fonte.startswith(("http://", "https://")):
            import urllib.request
            url = fonte.rstrip("/") + "/pj-consultador-xml.zip"
            status_fn("Baixando pacote de atualização...")
            urllib.request.urlretrieve(url, destino)
        else:
            origem = os.path.join(fonte, "pj-consultador-xml.zip")
            status_fn("Copiando pacote de atualização...")
            shutil.copy2(origem, destino)
        return True
    except Exception:
        return False


def verificar_e_atualizar(base_dir: str, status_fn=None) -> bool:
    """
    Verifica e aplica atualização. Retorna True se aplicou (o app deve reiniciar).
    """
    def _s(msg):
        if status_fn:
            status_fn(msg)

    fonte = _ler_fonte(base_dir)
    if not fonte:
        return False

    local = _versao_local(base_dir)
    _s(f"Versão instalada: {local}. Consultando servidor...")

    remota = _versao_remota(fonte)
    if remota is None:
        _s("Servidor de atualização inacessível. Continuando...")
        return False

    if remota == local:
        _s(f"Sistema atualizado ({local}).")
        return False

    _s(f"Nova versão disponível: {remota}. Atualizando...")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        if not _baixar_zip(fonte, tmp_path, _s):
            return False

        _s("Aplicando atualização...")
        with zipfile.ZipFile(tmp_path, "r") as zf:
            for member in zf.namelist():
                nome = os.path.basename(member)
                if nome in _PROTEGIDOS or member.endswith("/"):
                    continue
                dest = os.path.join(base_dir, member)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        # Grava nova versão local
        open(os.path.join(base_dir, "version.txt"), "w", encoding="utf-8").write(remota + "\n")
        _s(f"Atualização {remota} aplicada com sucesso!")
        return True

    except Exception as e:
        _s(f"Erro na atualização: {e}. Continuando com versão atual.")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
