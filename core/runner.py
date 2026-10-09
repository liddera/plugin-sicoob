"""Execução dos itens (conta × documento × mês) com as MESMAS regras do robô SicoobBot (main.py).

Regras reproduzidas do robô:
- por conta, itens agrupados por documento e depois por mês;
- `primeiro_periodo` só no 1º item da conta (e depois de um erro, que força a reentrada); os seguintes
  reaproveitam a conta; `ultimo_periodo` só no último item (volta à lista de contas);
- erro: conta como recuperação; 2 tentativas por item (TENTATIVAS_MAX_PERIODO) e mais de 3 recuperações
  por conta (RECOVERY_MAX_CONTA) fazem desistir dos itens restantes da conta.

Diferenças deliberadas em relação ao robô (decididas com a equipe):
- AVISO não é erro (conta sem cartão, mês sem comprovantes): não repete e não conta como recuperação;
- navegador fechado INTERROMPE a execução: os itens restantes ficam "não executados" (e não "erro definitivo").

O runner não conhece Playwright: recebe `acessar(...)`, uma função que chama `acessar_extrato` do robô.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

from . import resultado as R
from .erros import codigo_erro

TENTATIVAS_MAX_PERIODO = 2
RECOVERY_MAX_CONTA = 3
MSG_NAVEGADOR_FECHADO = "Target page, context or browser has been closed"


class NavegadorFechado(Exception):
    pass


def classificar(res: dict) -> tuple[str, str]:
    """Traduz o retorno de `acessar_extrato` em (resultado, mensagem)."""
    erro = (res.get("erro") or "").strip()
    if not erro:
        if not res.get("pdf_path"):
            return R.ERRO, "o processo terminou sem erro, mas nenhum arquivo foi gerado"
        if res.get("_substituido"):
            return R.SUBSTITUIDO, ""
        if res.get("_sem_movimento"):
            return R.SEM_MOVIMENTO, ""
        return R.SUCESSO, ""
    resumo = " ".join(erro.split())[:300]
    if erro.startswith("⚠️"):
        return R.AVISO, resumo.lstrip("⚠️ ").strip()
    return R.ERRO, resumo.lstrip("❌ ").strip()


class Runner:
    def __init__(
        self,
        execucao: dict,
        contas: list[dict],
        acessar: Callable[[dict, dict, bool, bool], dict],
        navegador_vivo: Callable[[], bool],
        cancelado: threading.Event,
        ao_atualizar: Callable[[dict], None] = lambda e: None,
        tentativas_max: int = TENTATIVAS_MAX_PERIODO,
        recovery_max: int = RECOVERY_MAX_CONTA,
        ao_concluir: Callable[[dict], None] = lambda item: None,
    ):
        self.exec = execucao
        self.contas = {c["numero"]: dict(c) for c in contas}
        self.acessar = acessar
        self.vivo = navegador_vivo
        self.cancelado = cancelado
        self.ao_atualizar = ao_atualizar
        self.tentativas_max = tentativas_max
        self.recovery_max = recovery_max
        self.ao_concluir = ao_concluir  # chamado quando um item recebe seu resultado final (vai para o histórico)
        self._t0: dict[int, float] = {}

    # -------------------------------------------------------------- utilitários
    def _itens_da_conta(self, numero: str) -> list[dict]:
        return [it for it in self.exec["itens"] if it["numero"] == numero]

    def _fechar(self, item: dict, resultado: str | None, msg: str = "", pdf: str = "", res: dict | None = None,
                recuperacoes: int = 0) -> None:
        res = res or {}
        item["estado"] = "concluido"
        item["resultado"] = resultado
        item["mensagem"] = msg
        if pdf:
            item["pdf_path"] = pdf
        item["codigo"] = codigo_erro(msg) if resultado in (R.ERRO, R.AVISO) else ""
        item["recuperacoes"] = recuperacoes
        item["substituido"] = bool(res.get("_substituido"))
        item["sem_movimento"] = bool(res.get("_sem_movimento"))
        if pdf:
            try:
                item["tamanho_bytes"] = os.path.getsize(pdf)
            except OSError:
                item["tamanho_bytes"] = None
        t0 = self._t0.pop(id(item), None)
        item.setdefault("inicio", R.agora())
        item["duracao_s"] = round(time.monotonic() - t0, 2) if t0 is not None else 0.0
        item["fim"] = R.agora()
        self.exec["item_atual"] = None
        self.ao_atualizar(self.exec)
        try:
            self.ao_concluir(item)
        except Exception:  # o histórico nunca pode derrubar a execução
            pass

    def _marcar_nao_executados(self, itens: list[dict], motivo: str) -> None:
        for it in itens:
            if it.get("resultado") is None:
                it["estado"] = "concluido"
                it["resultado"] = R.NAO_EXECUTADO
                it["mensagem"] = motivo
        self.exec["item_atual"] = None

    # -------------------------------------------------------------- execução
    def executar(self) -> dict:
        ordem_contas = list(dict.fromkeys(it["numero"] for it in self.exec["itens"]))
        try:
            for numero in ordem_contas:
                if self.cancelado.is_set():
                    break
                self._executar_conta(numero)
            if self.cancelado.is_set():
                restantes = [it for it in self.exec["itens"] if it.get("resultado") is None]
                self._marcar_nao_executados(restantes, "execução cancelada pelo usuário")
                self.exec["status"] = "cancelled"
            else:
                self.exec["status"] = "finished"
        except NavegadorFechado as e:
            restantes = [it for it in self.exec["itens"] if it.get("resultado") is None]
            self._marcar_nao_executados(restantes, "navegador fechado antes de processar este item")
            self.exec["status"] = "interrompida"
            self.exec["mensagem"] = str(e)
        self.exec["fim"] = R.agora()
        self.ao_atualizar(self.exec)
        return self.exec

    def _executar_conta(self, numero: str) -> None:
        itens = self._itens_da_conta(numero)
        conta = self.contas.setdefault(numero, {"numero": numero, "empresa": ""})
        idx = 0
        recovery = 0
        reentrar = True
        sem_cartao = False
        while idx < len(itens):
            if self.cancelado.is_set():
                return
            item = itens[idx]
            if item.get("resultado") is not None:  # já resolvido (ex.: refazer só os que faltam)
                idx += 1
                continue
            if not self.vivo():
                raise NavegadorFechado("o navegador foi fechado")

            # a conta já respondeu "sem cartão": os outros meses do cartão terão o mesmo resultado
            if item["tipo"] == "cartao" and sem_cartao:
                self._fechar(item, R.AVISO, "conta sem cartões de crédito vinculados", recuperacoes=recovery)
                idx += 1
                continue

            primeiro = reentrar
            ultimo = idx == len(itens) - 1
            item["estado"] = "em_andamento"
            item["tentativas"] = int(item.get("tentativas", 0)) + 1
            self._t0.setdefault(id(item), time.monotonic())
            item.setdefault("inicio", R.agora())
            self.exec["item_atual"] = {"numero": numero, "tipo": item["tipo"], "chave": item["chave"],
                                       "tentativa": item["tentativas"]}
            self.ao_atualizar(self.exec)

            try:
                res = self.acessar(item, conta, primeiro, ultimo) or {}
            except NavegadorFechado:
                raise
            except Exception as e:  # erro inesperado vindo do robô
                if MSG_NAVEGADOR_FECHADO in str(e):
                    raise NavegadorFechado("o navegador foi fechado durante o processamento")
                res = {"erro": f"❌ Erro inesperado: {e}"}

            if res.get("empresa"):
                conta["empresa"] = res["empresa"]
                for it in itens:
                    it["empresa"] = res["empresa"]

            if MSG_NAVEGADOR_FECHADO in (res.get("erro") or "") and not self.vivo():
                raise NavegadorFechado("o navegador foi fechado durante o processamento")

            categoria, msg = classificar(res)

            if categoria in R.CONCLUIDOS_OK:
                self._fechar(item, categoria, msg, res.get("pdf_path", ""), res, recovery)
                reentrar = False
                idx += 1
            elif categoria == R.AVISO:
                if item["tipo"] == "cartao":
                    sem_cartao = True
                self._fechar(item, R.AVISO, msg, res=res, recuperacoes=recovery)
                reentrar = False  # a conta continua selecionada; o aviso não derruba o estado da tela
                idx += 1
            else:  # erro
                recovery += 1
                reentrar = True
                if recovery > self.recovery_max:
                    self._fechar(item, R.ERRO, msg, res=res, recuperacoes=recovery)
                    for resto in itens[idx + 1:]:
                        if resto.get("resultado") is None:
                            self._fechar(resto, R.ERRO, "desistência: limite de recuperações da conta atingido",
                                         recuperacoes=recovery)
                    return
                if item["tentativas"] >= self.tentativas_max:
                    self._fechar(item, R.ERRO, msg, res=res, recuperacoes=recovery)  # erro definitivo deste item
                    idx += 1
                else:
                    item["mensagem"] = msg  # nova tentativa do mesmo item
                    self.ao_atualizar(self.exec)
