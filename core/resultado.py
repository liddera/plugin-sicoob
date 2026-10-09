"""Resultado da execução: estado, persistência da última execução e relatório.

Nunca guarda nem devolve saldos ou movimentos: só conta, empresa, documento, mês, status e caminho do arquivo.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from . import paths
from .pedido import ROTULO_TIPO

# resultados possíveis de um item
SUCESSO, SUBSTITUIDO, SEM_MOVIMENTO, AVISO, ERRO, NAO_EXECUTADO = (
    "sucesso", "substituido", "sem_movimento", "aviso", "erro", "nao_executado")
CONCLUIDOS_OK = {SUCESSO, SUBSTITUIDO, SEM_MOVIMENTO}

_ROTULO = {
    SUCESSO: "✅ gerado",
    SUBSTITUIDO: "✅ substituído",
    SEM_MOVIMENTO: "✅ sem movimento (PDF só com os saldos)",
    AVISO: "⚠️ aviso",
    ERRO: "❌ erro",
    NAO_EXECUTADO: "⏸️ não executado",
    None: "… pendente",
}


def novo_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def novo_item(numero: str, tipo: str, ano: int, mes: int) -> dict:
    return {"numero": numero, "empresa": "", "tipo": tipo, "ano": ano, "mes": mes,
            "chave": f"{mes:02d}/{ano}", "estado": "pendente", "resultado": None,
            "pdf_path": "", "mensagem": "", "tentativas": 0}


def nova_execucao(run_id: str, pedido: dict, itens: list[dict]) -> dict:
    return {"run_id": run_id, "inicio": agora(), "fim": "", "status": "running",
            "pedido": pedido, "itens": itens, "item_atual": None, "mensagem": ""}


def salvar(execucao: dict, caminho: Path | None = None) -> None:
    """Grava de forma segura (arquivo temporário + troca)."""
    p = Path(caminho) if caminho else paths.ultima_execucao_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(execucao, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def carregar(caminho: Path | None = None) -> dict | None:
    p = Path(caminho) if caminho else paths.ultima_execucao_path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def contagens(itens: list[dict]) -> dict:
    c = {"total": len(itens), "ok": 0, "avisos": 0, "erros": 0, "nao_executados": 0, "pendentes": 0, "substituidos": 0}
    for it in itens:
        r = it.get("resultado")
        if r in CONCLUIDOS_OK:
            c["ok"] += 1
            if r == SUBSTITUIDO:
                c["substituidos"] += 1
        elif r == AVISO:
            c["avisos"] += 1
        elif r == ERRO:
            c["erros"] += 1
        elif r == NAO_EXECUTADO:
            c["nao_executados"] += 1
        else:
            c["pendentes"] += 1
    return c


def itens_para_refazer(execucao: dict, modo: str) -> list[dict]:
    """modo 'erro' -> itens com erro; 'continuar' -> só os que não rodaram (não executados e pendentes)."""
    alvo = {ERRO} if modo == "erro" else {NAO_EXECUTADO, None}
    return [it for it in execucao.get("itens", []) if it.get("resultado") in alvo]


def andamento(execucao: dict) -> dict:
    c = contagens(execucao["itens"])
    feitos = c["total"] - c["pendentes"]
    return {"run_id": execucao["run_id"], "status": execucao["status"], "inicio": execucao["inicio"],
            "fim": execucao["fim"], "itens_total": c["total"], "itens_feitos": feitos,
            "ok": c["ok"], "avisos": c["avisos"], "erros": c["erros"], "nao_executados": c["nao_executados"],
            "item_atual": execucao.get("item_atual"), "mensagem": execucao.get("mensagem", "")}


def relatorio_markdown(execucao: dict) -> str:
    linhas = ["| Conta | Empresa | Documento | Mês | Resultado | Arquivo |", "|---|---|---|---|---|---|"]
    for it in execucao["itens"]:
        r = _ROTULO.get(it.get("resultado"), "… pendente")
        if it.get("resultado") in (AVISO, ERRO, NAO_EXECUTADO) and it.get("mensagem"):
            r += f": {it['mensagem']}"
        arq = it.get("pdf_path") or "—"
        linhas.append(f"| {it['numero']} | {it.get('empresa') or '—'} | {ROTULO_TIPO.get(it['tipo'], it['tipo'])} "
                      f"| {it['chave']} | {r} | {arq} |")
    c = contagens(execucao["itens"])
    partes = [f"{c['ok']} gerado(s)"]
    if c["substituidos"]:
        partes[0] += f" ({c['substituidos']} substituído(s))"
    partes.append(f"{c['avisos']} aviso(s)")
    partes.append(f"{c['erros']} erro(s)")
    if c["nao_executados"]:
        partes.append(f"{c['nao_executados']} não executado(s)")
    if c["pendentes"]:
        partes.append(f"{c['pendentes']} pendente(s)")
    resumo = f"**Execução {execucao['run_id']}** ({execucao['status']}): " + ", ".join(partes) + f" de {c['total']} itens."
    return resumo + "\n\n" + "\n".join(linhas)
