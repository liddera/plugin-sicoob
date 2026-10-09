"""Código estruturado do erro/aviso, a partir das mensagens do código do robô. Só biblioteca padrão.

O robô devolve só texto; o plugin guarda também um CÓDIGO curto para contar e filtrar com confiabilidade.
Ordem importa: o primeiro padrão que casar vence.
"""
from __future__ import annotations

import re

_PADROES = [
    ("navegador_fechado", r"Target page, context or browser has been closed|navegador (foi )?fechado"),
    ("sem_cartao", r"sem cart[õo]es"),
    ("sem_comprovantes", r"n[ãa]o existem comprovantes|nenhum comprovante"),
    ("limite_recuperacao", r"limite de recupera"),
    ("periodo_divergente", r"per[ií]odo divergente"),
    ("periodo_nao_identificado", r"n[ãa]o foi poss[ií]vel identificar o per[ií]odo"),
    ("periodo_esperado_invalido", r"determinar o per[ií]odo esperado"),
    ("conta_nao_encontrada", r"conta .{0,30}n[ãa]o apareceu|conta n[ãa]o encontrada"),
    ("exportar_desabilitado", r"permaneceu disabled"),
    ("exportacao", r"exporta[çc][ãa]o|download|resposta de exporta"),
    ("periodo_nao_aplicado", r"aplicar per[ií]odo"),
    ("troca_de_conta", r"tela de troca|trocar conta"),
    ("tempo_esgotado", r"timeout|tempo esgotado|excedeu"),
    ("sem_arquivo", r"nenhum arquivo foi gerado"),
]


def codigo_erro(mensagem: str) -> str:
    texto = " ".join(str(mensagem or "").split())
    if not texto:
        return ""
    for codigo, padrao in _PADROES:
        if re.search(padrao, texto, flags=re.IGNORECASE):
            return codigo
    return "desconhecido"
