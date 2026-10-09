"""Caminhos do plugin. Só biblioteca padrão.

Os dados do robô e do plugin ficam na MESMA pasta base, para compartilhar o perfil do navegador
(que guarda o cadastro do dispositivo do Sicoob) e o histórico `controle_execucao_contas.json`:

  Windows:  %LOCALAPPDATA%\\SicoobBot
  outros:   $SICOOBBOT_HOME ou ~/.local/share/SicoobBot   (uso em desenvolvimento/testes)
"""
from __future__ import annotations

import os
from pathlib import Path

URL_SICOOB = "https://ib.sicoob.com.br/sicoobnet/ib/#/login"
PASTA_BASE_PADRAO = r"H:\Drives compartilhados\Contábil"  # mesmo padrão fixo do robô (main.py)
CHROMIUM_ESPERADO = "153.0.8010.12"  # versão do Chromium embutido no EXE (Playwright 1.63.0)
PLAYWRIGHT_VERSAO = "1.63.0"


def home_dir() -> Path:
    env = os.environ.get("SICOOBBOT_HOME")
    if env:
        base = Path(env)
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"]) / "SicoobBot"
    else:
        base = Path.home() / ".local" / "share" / "SicoobBot"
    base.mkdir(parents=True, exist_ok=True)
    return base


def perfil_dir() -> Path:
    return home_dir() / "perfil_sicoobnet_persistente"


def controle_path() -> Path:
    return home_dir() / "controle_execucao_contas.json"


def lid_dir() -> Path:
    """Pasta própria do plugin dentro da pasta base (log, última execução)."""
    d = home_dir() / "lid"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = lid_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ultima_execucao_path() -> Path:
    return lid_dir() / "ultima_execucao.json"


def data_dir() -> Path:
    """Dados persistentes do plugin (ambiente Python). Sobrevive a atualizações do plugin."""
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    d = Path(env) if env else lid_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def venv_dir() -> Path:
    return data_dir() / "venv"


def venv_python() -> Path:
    v = venv_dir()
    return v / "Scripts" / "python.exe" if os.name == "nt" else v / "bin" / "python"


def plugin_root() -> Path:
    """Raiz do plugin (pasta que contém core/, vendor/, worker/, server/)."""
    return Path(__file__).resolve().parent.parent


def versao_plugin() -> str:
    try:
        import json
        return json.loads((plugin_root() / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("version", "0")
    except Exception:
        return "0"
