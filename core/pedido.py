"""Validação e normalização do pedido de extração (contas, documentos, meses, pasta).

Só biblioteca padrão. O Claude interpreta a conversa; este módulo garante que o que chega ao
servidor é consistente ANTES de abrir qualquer navegador ou criar qualquer pasta.
"""
from __future__ import annotations

import difflib
import os
import re
import uuid
from datetime import date
from pathlib import Path

TIPOS = ("corrente", "capital", "comprovantes", "cartao")

_ALIAS_TIPOS = {
    "corrente": "corrente", "conta corrente": "corrente", "extrato": "corrente",
    "extrato corrente": "corrente", "extrato conta corrente": "corrente", "cc": "corrente",
    "capital": "capital", "conta capital": "capital", "extrato capital": "capital",
    "extrato conta capital": "capital",
    "comprovante": "comprovantes", "comprovantes": "comprovantes", "emissao de comprovantes": "comprovantes",
    "cartao": "cartao", "cartoes": "cartao", "fatura": "cartao", "faturas": "cartao",
    "fatura de cartao": "cartao", "fatura do cartao": "cartao", "cartao de credito": "cartao",
}

ROTULO_TIPO = {
    "corrente": "Extrato conta corrente",
    "capital": "Extrato conta capital",
    "comprovantes": "Comprovantes",
    "cartao": "Fatura de cartão",
}

PASTA_TIPO = {  # nomes de pasta que o robô usa (apenas informativo; quem cria é o código do robô)
    "corrente": "Extrato CC",
    "capital": "Extratos Conta Capital",
    "comprovantes": "Comprovantes",
    "cartao": "Faturas do Cartão de Crédito",
}

ANO_MINIMO = 2020  # o seletor de ano do portal começa em 2020

_MESES_NOME = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _sem_acento(txt: str) -> str:
    import unicodedata
    base = unicodedata.normalize("NFKD", str(txt or ""))
    return "".join(c for c in base if not unicodedata.combining(c))


# ---------------------------------------------------------------- tipos
def normalizar_tipo(txt: str) -> str | None:
    chave = re.sub(r"\s+", " ", _sem_acento(txt).lower().strip())
    if chave in _ALIAS_TIPOS:
        return _ALIAS_TIPOS[chave]
    if chave in TIPOS:
        return chave
    # tolerância: "extrato da conta capital", "faturas dos cartões"...
    for palavra, tipo in (("capital", "capital"), ("comprov", "comprovantes"),
                          ("cart", "cartao"), ("fatura", "cartao"), ("corrente", "corrente")):
        if palavra in chave:
            return tipo
    return None


def normalizar_tipos(entradas) -> tuple[list[str], list[str]]:
    """Devolve (tipos canônicos sem repetição, na ordem pedida; entradas não reconhecidas)."""
    if isinstance(entradas, str):
        entradas = [entradas]
    vistos, ruins = [], []
    for e in entradas or []:
        if _sem_acento(str(e)).lower().strip() in ("todos", "todas", "tudo"):
            return list(TIPOS), []
        t = normalizar_tipo(str(e))
        if t is None:
            ruins.append(str(e))
        elif t not in vistos:
            vistos.append(t)
    return vistos, ruins


# ---------------------------------------------------------------- contas
def digitos(txt: str) -> str:
    return re.sub(r"\D", "", str(txt or ""))


def normalizar_conta(txt: str) -> str | None:
    """'470414' / '47.041-4' / '47041-4' -> '47.041-4'. None se não parecer uma conta."""
    d = digitos(txt)
    if len(d) < 3:
        return None
    corpo, dv = d[:-1], d[-1]
    grupos = []
    while corpo:
        grupos.insert(0, corpo[-3:])
        corpo = corpo[:-3]
    return f"{'.'.join(grupos)}-{dv}"


def resolver_contas(entradas, conhecidas: list[str]) -> dict:
    """Confere as contas pedidas contra a lista carregada do portal.

    Devolve {"aceitas": [...canônicas...], "nao_encontradas": [{"entrada", "sugestoes"}]}.
    """
    if isinstance(entradas, str):
        entradas = [entradas]
    mapa = {digitos(c): c for c in conhecidas}
    aceitas, faltando = [], []
    for e in entradas or []:
        d = digitos(e)
        if d in mapa:
            if mapa[d] not in aceitas:
                aceitas.append(mapa[d])
            continue
        sug = difflib.get_close_matches(d, list(mapa.keys()), n=3, cutoff=0.6) if d else []
        faltando.append({"entrada": str(e), "sugestoes": [mapa[s] for s in sug]})
    return {"aceitas": aceitas, "nao_encontradas": faltando}


# ---------------------------------------------------------------- meses
def parse_mes(txt: str) -> tuple[int, int] | None:
    """'06/2026', '6/2026', '06-2026', 'junho/2026', 'junho de 2026' -> (2026, 6)."""
    t = re.sub(r"\s+", " ", _sem_acento(txt).lower().strip())
    m = re.fullmatch(r"(\d{1,2})\s*[/\-.]\s*(\d{4})", t)
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r"([a-z]+)\s*(?:/|de|-)?\s*(\d{4})", t)
        if not m or m.group(1) not in _MESES_NOME:
            return None
        mes, ano = _MESES_NOME[m.group(1)], int(m.group(2))
    return (ano, mes) if 1 <= mes <= 12 else None


def _mes_sem_ano(txt: str) -> int | None:
    """'junho' -> 6; '06' -> 6; qualquer outra coisa -> None."""
    t = _sem_acento(txt).lower().strip()
    if t in _MESES_NOME:
        return _MESES_NOME[t]
    if re.fullmatch(r"\d{1,2}", t) and 1 <= int(t) <= 12:
        return int(t)
    return None


def _proximo(ano: int, mes: int) -> tuple[int, int]:
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def expandir_meses(entradas, hoje: date | None = None) -> tuple[list[tuple[int, int]], list[str]]:
    """Aceita itens como '06/2026' ou intervalos '06/2026 a 09/2026' (também '-', 'até').

    Devolve (lista ordenada e sem repetição de (ano, mes), lista de problemas).
    """
    hoje = hoje or date.today()
    if isinstance(entradas, str):
        entradas = [entradas]
    meses: set[tuple[int, int]] = set()
    problemas: list[str] = []
    for e in entradas or []:
        texto = _sem_acento(str(e)).lower()
        partes = re.split(r"\s+(?:a|ate)\s+|\s*--\s*|\s+-\s+|\s*\.\.\s*", texto)
        if len(partes) == 2:
            ini, fim = parse_mes(partes[0]), parse_mes(partes[1])
            if ini is None and fim is not None:  # "junho a setembro de 2026": o início herda o ano do fim
                so_mes = _mes_sem_ano(partes[0])
                if so_mes:
                    ini = (fim[0], so_mes)
            if not ini or not fim:
                problemas.append(f"intervalo de meses inválido: '{e}'")
                continue
            if ini > fim:
                problemas.append(f"intervalo invertido: '{e}'")
                continue
            cur = ini
            while cur <= fim:
                meses.add(cur)
                cur = _proximo(*cur)
        else:
            um = parse_mes(str(e))
            if not um:
                problemas.append(f"mês inválido: '{e}' (use 06/2026 ou 06/2026 a 09/2026)")
                continue
            meses.add(um)
    atual = (hoje.year, hoje.month)
    for ano, mes in sorted(meses):
        if (ano, mes) > atual:
            problemas.append(f"mês futuro não permitido: {mes:02d}/{ano}")
        if ano < ANO_MINIMO:
            problemas.append(f"ano anterior a {ANO_MINIMO} não é aceito pelo portal: {mes:02d}/{ano}")
    validos = [m for m in sorted(meses) if m <= atual and m[0] >= ANO_MINIMO]
    return validos, problemas


def chave_mes(ano: int, mes: int) -> str:
    return f"{mes:02d}/{ano}"


# ---------------------------------------------------------------- pasta
def validar_pasta(caminho: str) -> dict:
    """Confere a pasta base sem criar nada além de um arquivo temporário de teste."""
    res = {"caminho": caminho, "ok": False, "existe": False, "gravavel": False,
           "empresas_total": 0, "exemplos": [], "avisos": [], "erros": []}
    if not caminho or not str(caminho).strip():
        res["erros"].append("pasta de destino não informada")
        return res
    p = Path(caminho)
    if not p.exists():
        dica = ""
        if re.match(r"^[A-Za-z]:\\", str(caminho)):
            dica = (" Se for uma unidade de rede ou do Google Drive, confira se ela está visível para o programa "
                    "(programas abertos como administrador não enxergam unidades mapeadas do usuário).")
        res["erros"].append(f"a pasta não existe ou não está acessível.{dica}")
        return res
    if not p.is_dir():
        res["erros"].append("o caminho informado não é uma pasta")
        return res
    res["existe"] = True
    teste = p / f".lid_teste_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    try:
        teste.write_text("teste", encoding="utf-8")
        teste.unlink()
        res["gravavel"] = True
    except Exception as e:
        res["erros"].append(f"não é possível gravar nessa pasta ({e.__class__.__name__})")
        return res
    try:
        empresas = sorted((d.name for d in p.iterdir() if d.is_dir() and not d.name.startswith(".")), key=str.casefold)
    except Exception as e:
        res["avisos"].append(f"não consegui listar as pastas ({e.__class__.__name__})")
        empresas = []
    res["empresas_total"] = len(empresas)
    res["exemplos"] = empresas[:3]
    if not empresas:
        res["avisos"].append("a pasta não contém nenhuma pasta de empresa; confira se é a raiz certa "
                             "(novas pastas de empresa serão criadas aqui)")
    res["ok"] = True
    return res


# ---------------------------------------------------------------- itens
def montar_itens(contas: list[str], tipos: list[str], meses: list[tuple[int, int]]) -> list[dict]:
    """Itens na ordem do robô: por conta, todos os meses do 1º documento, depois os do 2º..."""
    itens = []
    for numero in contas:
        for tipo in tipos:
            for ano, mes in sorted(meses):
                itens.append({"numero": numero, "tipo": tipo, "mes": mes, "ano": ano, "chave": chave_mes(ano, mes)})
    return itens


def resumo_pedido(pasta: str, contas: list[str], tipos: list[str], meses: list[tuple[int, int]]) -> dict:
    total = len(contas) * len(tipos) * len(meses)
    return {
        "pasta": pasta,
        "contas": contas,
        "documentos": [ROTULO_TIPO[t] for t in tipos],
        "tipos": tipos,
        "meses": [chave_mes(a, m) for a, m in sorted(meses)],
        "total_itens": total,
        "conta": f"{len(contas)} conta(s) × {len(tipos)} documento(s) × {len(meses)} mês(es) = {total} itens",
    }
