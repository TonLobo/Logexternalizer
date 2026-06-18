"""
Persistência das últimas seleções do usuário em config.json local.
Sobrevive ao fechamento/reinício do app.
"""
import json
from pathlib import Path

_CONFIG_FILE = Path(__file__).parent / "config.json"

_DEFAULTS = {
    "hub_pgmp": None,
    "hub_operacao": None,
    "hub_data": None,
    "hub_file": None,
    "mni_pgmp": None,
    "mni_data": None,
    "mni_file": None,
}


def load() -> dict:
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(**kwargs) -> None:
    current = load()
    current.update({k: v for k, v in kwargs.items() if k in _DEFAULTS})
    _CONFIG_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
