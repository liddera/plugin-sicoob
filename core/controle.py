"""Leitura (SOMENTE LEITURA) do `controle_execucao_contas.json` do robô SicoobBot.

Formato (definido pelo robô, em main.py):
  {"versao": 1, "atualizado_em": "...",
   "ciclos": {"<AAAA-MM-DD>::<tipo>": {"contas": {"<número>": {"status": ..., "periodos": {"MM/AAAA": {...}}}},
                                       "execucoes": {"<run_id>": {...}}}}}

O ciclo é o DIA da execução e há um "balde" por tipo de documento. Chaves antigas (por exemplo "03/2026")
podem existir de versões anteriores do robô e são ignoradas aqui.
A gravação fica para a fase F6 (com cópia de segurança); por enquanto este módulo nunca escreve.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import paths

STATUS_PENDENTES = {"nao_iniciada", "pendente"}
STATUS_COM_ERRO = {"erro", "parcial"}
STATUS_SUCESSO = {"sucesso", "reprocessada"}


def carregar(caminho: Path | None = None) -> dict:
    """Mesmas regras do robô: arquivo ausente ou inválido vira um controle vazio."""
    vazio = {"versao": 1, "atualizado_em": "", "ciclos": {}}
    p = Path(caminho) if caminho else paths.controle_path()
    if not p.exists():
        return vazio
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return vazio
    if not isinstance(dados, dict):
        return vazio
    dados.setdefault("versao", 1)
    dados.setdefault("atualizado_em", "")
    if not isinstance(dados.get("ciclos"), dict):
        dados["ciclos"] = {}
    return dados


def ciclo_de_hoje(hoje: date | None = None) -> str:
    return (hoje or date.today()).strftime("%Y-%m-%d")


def chave(ciclo: str, tipo: str) -> str:
    return f"{ciclo}::{tipo}"


def info_conta(controle: dict, ciclo: str, tipo: str, numero: str) -> dict:
    balde = controle.get("ciclos", {}).get(chave(ciclo, tipo), {})
    contas = balde.get("contas", {}) if isinstance(balde, dict) else {}
    info = contas.get(numero, {}) if isinstance(contas, dict) else {}
    return info if isinstance(info, dict) else {}


def status_conta(controle: dict, ciclo: str, tipo: str, numero: str) -> str:
    return info_conta(controle, ciclo, tipo, numero).get("status") or "nao_iniciada"


def classificar_contas(controle: dict, todas_contas: list[str], tipo: str, ciclo: str | None = None) -> dict:
    """Separa as contas do dia em pendentes / com erro / com sucesso, como os botões do robô."""
    ciclo = ciclo or ciclo_de_hoje()
    grupos = {"pendentes": [], "com_erro": [], "sucesso": [], "em_processamento": []}
    for numero in todas_contas:
        st = status_conta(controle, ciclo, tipo, numero)
        if st in STATUS_PENDENTES:
            grupos["pendentes"].append(numero)
        elif st in STATUS_COM_ERRO:
            grupos["com_erro"].append(numero)
        elif st in STATUS_SUCESSO:
            grupos["sucesso"].append(numero)
        else:
            grupos["em_processamento"].append(numero)
    grupos["contagem"] = {k: len(v) for k, v in grupos.items() if isinstance(v, list)}
    grupos["ciclo"] = ciclo
    grupos["tipo"] = tipo
    return grupos


def itens_com_erro(controle: dict, tipos: list[str], ciclo: str | None = None) -> list[dict]:
    """Itens (conta × documento × mês) cujo mês terminou com erro no ciclo informado (padrão: hoje)."""
    ciclo = ciclo or ciclo_de_hoje()
    itens = []
    for tipo in tipos:
        balde = controle.get("ciclos", {}).get(chave(ciclo, tipo), {})
        contas = balde.get("contas", {}) if isinstance(balde, dict) else {}
        if not isinstance(contas, dict):
            continue
        for numero, info in contas.items():
            periodos = info.get("periodos", {}) if isinstance(info, dict) else {}
            if not isinstance(periodos, dict):
                continue
            for mes_ano, p in periodos.items():
                if isinstance(p, dict) and p.get("status") == "erro":
                    itens.append({"numero": numero, "tipo": tipo, "chave": mes_ano, "erro": p.get("erro_resumo", "")})
    return itens
