"""Proteção do perfil persistente do navegador (compartilhado com o robô SicoobBot).

Fatos verificados:
- um Chromium MAIS NOVO abre o perfil de um mais antigo, mas o MAIS ANTIGO não abre mais um perfil que um
  mais novo usou (o processo cai ao iniciar com "Target page, context or browser has been closed");
- um perfil só abre em um processo por vez.
O arquivo `Last Version` do perfil guarda a versão do Chromium que o usou por último.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import paths


def _tupla(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def comparar_versoes(a: str, b: str) -> int:
    ta, tb = _tupla(a), _tupla(b)
    return (ta > tb) - (ta < tb)


def versao_do_perfil(perfil: Path | None = None) -> str | None:
    arq = (Path(perfil) if perfil else paths.perfil_dir()) / "Last Version"
    try:
        return arq.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def versao_chromium_do_playwright(pacote_playwright: Path | None = None) -> str | None:
    """Lê a versão do Chromium que o Playwright instalado declara (driver/package/browsers.json)."""
    try:
        if pacote_playwright is None:
            import playwright  # type: ignore
            pacote_playwright = Path(playwright.__file__).parent
        dados = json.loads((Path(pacote_playwright) / "driver" / "package" / "browsers.json").read_text(encoding="utf-8"))
        for b in dados.get("browsers", []):
            if b.get("name") == "chromium":
                return b.get("browserVersion")
    except Exception:
        pass
    return None


def perfil_em_uso(perfil: Path | None = None) -> bool:
    """Melhor esforço: há um navegador usando este perfil agora?"""
    p = Path(perfil) if perfil else paths.perfil_dir()
    if os.name == "nt":
        lock = p / "lockfile"
        if not lock.exists():
            return False
        try:
            with open(lock, "rb"):
                return False  # abriu: arquivo antigo, ninguém segurando
        except PermissionError:
            return True
        except OSError:
            return False
    trava = p / "SingletonLock"
    if not os.path.lexists(trava):
        return False
    try:
        alvo = os.readlink(trava)  # "host-pid"
        pid = int(alvo.rsplit("-", 1)[-1])
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, FileNotFoundError):
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def checar_perfil(versao_chromium: str | None, perfil: Path | None = None) -> dict:
    """Decide se é seguro abrir o perfil com este Chromium."""
    p = Path(perfil) if perfil else paths.perfil_dir()
    versao_perfil = versao_do_perfil(p)
    if perfil_em_uso(p):
        return {"ok": False, "codigo": "perfil_em_uso", "versao_perfil": versao_perfil,
                "motivo": "O navegador do Sicoob já está aberto (o robô SicoobBot ou outra sessão usa este perfil). "
                          "Feche o robô e tente de novo; um perfil só abre em um programa por vez."}
    if versao_perfil and versao_chromium and comparar_versoes(versao_perfil, versao_chromium) > 0:
        return {"ok": False, "codigo": "perfil_mais_novo", "versao_perfil": versao_perfil,
                "motivo": f"Este perfil foi usado por um navegador mais novo (Chromium {versao_perfil}) do que o do plugin "
                          f"({versao_chromium}), e o mais antigo não consegue abri-lo. Atualize o plugin/robô para a mesma "
                          "versão ou use outro perfil."}
    return {"ok": True, "codigo": "ok", "versao_perfil": versao_perfil, "motivo": ""}
