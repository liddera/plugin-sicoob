"""Log em arquivo do plugin. O EXE do robô não tem console e perdeu o erro original; aqui nada se perde.

Arquivo: <pasta base>/lid/logs/lid.log (rotação simples: 2 MB, 1 cópia). Só biblioteca padrão.
Nunca grava saldos nem movimentos: o código do robô só imprime andamento, caminhos e mensagens de erro.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from . import paths

_trava = threading.Lock()
_LIMITE = 2 * 1024 * 1024


def _arquivo() -> Path:
    return paths.logs_dir() / "lid.log"


def log(msg: str, nivel: str = "INFO") -> None:
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S} [{nivel}] {msg}\n"
    with _trava:
        try:
            arq = _arquivo()
            if arq.exists() and arq.stat().st_size > _LIMITE:
                antigo = arq.with_suffix(".log.1")
                if antigo.exists():
                    antigo.unlink()
                arq.replace(antigo)
            with open(arq, "a", encoding="utf-8") as f:
                f.write(linha)
        except Exception:
            pass  # log nunca pode derrubar a execução


def evento(nome: str, **dados) -> None:
    """Registra um evento estruturado (queda/fechamento do navegador, início/fim de execução...)."""
    log(f"EVENTO {nome} {json.dumps(dados, ensure_ascii=False, default=str)}")
