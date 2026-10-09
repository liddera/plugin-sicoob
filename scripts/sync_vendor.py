#!/usr/bin/env python3
"""Copia para vendor/sicoobbot os módulos do robô SicoobBot que o plugin reaproveita.

Uso:  python scripts/sync_vendor.py --robot <pasta 'automacoes' do robô>

- Copia só a lista MODULOS (nunca o main.py nem o config.py: o config do plugin é o
  vendor/sicoobbot/config.py, que é do plugin e não é sobrescrito).
- Grava vendor/sicoobbot/VENDOR.json com o commit do robô e o sha256 de cada arquivo,
  para saber de onde veio o código e detectar edições manuais (use --check).
"""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path

MODULOS = [
    "sicoob_actions.py",
    "browser_manager.py",
    "parse_extrato_sicoob_txt.py",
    "decode_extrato_texto.py",
    "build_html_extrato_sicoob.py",
    "build_html_extrato_sicoob_capital.py",
    "build_html_comprovantes_sicoob.py",
    "build_html_extrato_cartao.py",
]
DESTINO = Path(__file__).resolve().parent.parent / "vendor" / "sicoobbot"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(robo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(robo), *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def sincronizar(robo: Path) -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    arquivos = {}
    for nome in MODULOS:
        origem = robo / nome
        if not origem.is_file():
            sys.exit(f"Módulo não encontrado no robô: {origem}")
        (DESTINO / nome).write_bytes(origem.read_bytes())
        arquivos[nome] = sha256(DESTINO / nome)
    sujo = bool(git(robo, "status", "--porcelain", "--", *MODULOS))
    info = {
        "origem": "robô SicoobBot (pasta automacoes)",
        "commit": git(robo, "rev-parse", "HEAD"),
        "assunto": git(robo, "log", "-1", "--format=%s"),
        "alteracoes_nao_commitadas": sujo,
        "playwright_do_robo": "1.63.0 (Chromium 153.0.8010.12), versão do EXE em 8/10/2026",
        "arquivos": arquivos,
    }
    (DESTINO / "VENDOR.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(arquivos)} módulos copiados de {robo} (commit {info['commit'][:7]}"
          f"{', COM alterações não commitadas' if sujo else ''}).")


def conferir() -> int:
    info = json.loads((DESTINO / "VENDOR.json").read_text(encoding="utf-8"))
    ruim = [n for n, h in info["arquivos"].items() if not (DESTINO / n).is_file() or sha256(DESTINO / n) != h]
    if ruim:
        print("Arquivos do vendor editados à mão ou ausentes:", ", ".join(ruim))
        return 1
    print(f"vendor íntegro (commit do robô {info['commit'][:7]}).")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--robot", type=Path, help="pasta 'automacoes' do robô")
    ap.add_argument("--check", action="store_true", help="só confere a integridade do vendor")
    a = ap.parse_args()
    if a.check:
        sys.exit(conferir())
    if not a.robot:
        ap.error("informe --robot <pasta automacoes> ou use --check")
    sincronizar(a.robot.resolve())
