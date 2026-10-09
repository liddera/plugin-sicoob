"""Preparação do ambiente do plugin (usado por /lid:preparar). Só biblioteca padrão.

Cria um ambiente Python próprio em ${CLAUDE_PLUGIN_DATA}/venv (sobrevive a atualizações do plugin) com
`playwright==1.63.0` e baixa o Chromium da mesma versão do EXE do robô (153.0.8010.12), dentro do pacote do
Playwright (PLAYWRIGHT_BROWSERS_PATH=0, igual ao robô).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core import logs, paths  # noqa: E402

_CHECAGEM = r'''
import json, pathlib
try:
    import playwright
    from importlib.metadata import version
    base = pathlib.Path(playwright.__file__).parent / "driver" / "package"
    bj = json.loads((base / "browsers.json").read_text(encoding="utf-8"))
    cv = next((b.get("browserVersion") for b in bj["browsers"] if b["name"] == "chromium"), None)
    ok = any((base / ".local-browsers").glob("chromium-*"))
    print(json.dumps({"playwright": version("playwright"), "chromium_versao": cv, "chromium_instalado": ok}))
except Exception as e:
    print(json.dumps({"erro": str(e)}))
'''

_estado = {"estado": "nao_iniciado", "etapa": "", "mensagem": "", "linhas": [], "inicio": "", "fim": ""}
_trava = threading.Lock()
_cache = {"t": 0.0, "res": None}


def _env_playwright() -> dict:
    env = dict(os.environ)
    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def _flags_processo() -> dict:
    return {"creationflags": 0x08000000} if os.name == "nt" else {}  # CREATE_NO_WINDOW


def checar_ambiente(forcar: bool = False) -> dict:
    if not forcar and _cache["res"] is not None and time.time() - _cache["t"] < 20:
        return _cache["res"]
    py = paths.venv_python()
    res = {"python_servidor": ".".join(map(str, sys.version_info[:3])), "venv_existe": py.exists(),
           "playwright": None, "chromium_versao": None, "chromium_instalado": False,
           "esperado": {"playwright": paths.PLAYWRIGHT_VERSAO, "chromium": paths.CHROMIUM_ESPERADO},
           "pronto": False, "motivos": []}
    if sys.version_info < (3, 10):
        res["motivos"].append(f"É necessário Python 3.10 ou mais novo (encontrado {res['python_servidor']}).")
    if not py.exists():
        res["motivos"].append("O ambiente do plugin ainda não foi criado.")
    else:
        try:
            out = subprocess.run([str(py), "-c", _CHECAGEM], capture_output=True, text=True, timeout=60,
                                 env=_env_playwright(), **_flags_processo())
            info = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else {"erro": out.stderr[-200:]}
        except Exception as e:
            info = {"erro": str(e)}
        if info.get("erro"):
            res["motivos"].append(f"Playwright não está utilizável: {info['erro']}")
        else:
            res.update({k: info.get(k) for k in ("playwright", "chromium_versao", "chromium_instalado")})
            if res["playwright"] != paths.PLAYWRIGHT_VERSAO:
                res["motivos"].append(f"Playwright {res['playwright']} instalado; o plugin precisa da {paths.PLAYWRIGHT_VERSAO}.")
            if not res["chromium_instalado"]:
                res["motivos"].append("O navegador (Chromium) ainda não foi baixado.")
            elif res["chromium_versao"] != paths.CHROMIUM_ESPERADO:
                res["motivos"].append(f"Chromium {res['chromium_versao']} difere do esperado ({paths.CHROMIUM_ESPERADO}).")
    res["pronto"] = not res["motivos"]
    _cache.update(t=time.time(), res=res)
    return res


def estado_preparo() -> dict:
    with _trava:
        return {**_estado, "linhas": list(_estado["linhas"][-12:])}


def _set(**kw) -> None:
    with _trava:
        _estado.update(kw)


def _anotar(linha: str) -> None:
    logs.log("preparar: " + linha)
    with _trava:
        _estado["linhas"].append(linha)


def _rodar(etapa: str, cmd: list[str], timeout: int = 1500) -> None:
    _set(etapa=etapa, mensagem=f"{etapa}…")
    _anotar(f"{etapa}: {' '.join(cmd)}")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_env_playwright(), **_flags_processo())
    for linha in (p.stdout + p.stderr).splitlines()[-6:]:
        if linha.strip():
            _anotar("  " + linha.strip()[:200])
    if p.returncode != 0:
        raise RuntimeError(f"{etapa} falhou (código {p.returncode}). Veja o log do plugin.")


def _preparar() -> None:
    try:
        _set(estado="em_andamento", inicio=time.strftime("%Y-%m-%d %H:%M:%S"), fim="", mensagem="Começando…")
        _estado["linhas"].clear()
        if sys.version_info < (3, 10):
            raise RuntimeError("É necessário Python 3.10 ou mais novo. Instale-o e abra o Claude de novo.")
        py = paths.venv_python()
        if not py.exists():
            _rodar("Criando o ambiente Python", [sys.executable, "-m", "venv", str(paths.venv_dir())])
        chk = checar_ambiente(forcar=True)
        if chk["playwright"] != paths.PLAYWRIGHT_VERSAO:
            _rodar(f"Instalando Playwright {paths.PLAYWRIGHT_VERSAO}",
                   [str(py), "-m", "pip", "install", "--disable-pip-version-check", f"playwright=={paths.PLAYWRIGHT_VERSAO}"])
        chk = checar_ambiente(forcar=True)
        if not chk["chromium_instalado"] or chk["chromium_versao"] != paths.CHROMIUM_ESPERADO:
            _rodar("Baixando o navegador Chromium (cerca de 200 MB)", [str(py), "-m", "playwright", "install", "chromium"])
        chk = checar_ambiente(forcar=True)
        if not chk["pronto"]:
            raise RuntimeError("Ambiente ainda incompleto: " + " ".join(chk["motivos"]))
        _set(estado="concluido", etapa="", mensagem="Tudo pronto. Pode usar /lid:login.", fim=time.strftime("%Y-%m-%d %H:%M:%S"))
        logs.evento("preparar_ok")
    except subprocess.TimeoutExpired:
        _set(estado="erro", mensagem="A etapa demorou demais (rede lenta ou bloqueada). Tente de novo.", fim=time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        _set(estado="erro", mensagem=str(e), fim=time.strftime("%Y-%m-%d %H:%M:%S"))
        logs.evento("preparar_erro", erro=str(e)[:300])


def iniciar_preparo() -> dict:
    with _trava:
        if _estado["estado"] == "em_andamento":
            return {"iniciado": False, "mensagem": "A preparação já está em andamento."}
    threading.Thread(target=_preparar, name="preparar", daemon=True).start()
    return {"iniciado": True, "mensagem": "Preparação iniciada em segundo plano. Consulte o andamento com preparar_status."}
