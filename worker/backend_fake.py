"""Backend FALSO, só para testar o encanamento (servidor MCP ⇄ worker ⇄ runner) sem portal e sem navegador.

Ligado por `LID_FAKE=1`. Nunca é usado em produção. Variáveis opcionais:
  LID_FAKE_CONTAS   "47.041-4,109.317-7"   contas do "portal"
  LID_FAKE_ROTEIRO  {"conta|tipo|MM/AAAA": [{"erro": "..."}, {...}]}   respostas por item (a última se repete)
  LID_FAKE_LOGIN_S  segundos até o "login" terminar (padrão 0.2)
  LID_FAKE_ATRASO_S segundos por item (padrão 0), para testar status/cancelar
  LID_FAKE_FECHAR_APOS  n  -> o "navegador" morre depois de n itens
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from core import pedido
from core.runner import Runner


class BackendFake:
    NOMES = {"47.041-4": "AUTO POSTO AVENIDA LTDA", "109.317-7": "AUTO POSTO PATRAO LTDA", "14.035-0": "JOSE DA SILVA"}

    def __init__(self, estado):
        self.st = estado
        self.aberto = False
        self.itens_feitos = 0
        self.roteiro = json.loads(os.environ.get("LID_FAKE_ROTEIRO", "{}"))
        self.contas = [c.strip() for c in os.environ.get("LID_FAKE_CONTAS", "47.041-4,109.317-7,14.035-0").split(",") if c.strip()]

    def versao_chromium(self):
        return "153.0.8010.12"

    def diagnostico(self):
        return {"modo": "fake", "playwright": "ok (simulado)", "chromium": self.versao_chromium()}

    def nav_vivo(self):
        limite = os.environ.get("LID_FAKE_FECHAR_APOS")
        if limite and self.itens_feitos >= int(limite):
            return False
        return self.aberto

    def vivo_rapido(self):
        return self.nav_vivo()

    def abrir_navegador(self):
        self.aberto = True

    def esperar_login_e_listar(self):
        def f():
            time.sleep(float(os.environ.get("LID_FAKE_LOGIN_S", "0.2")))
            self.st.contas = list(self.contas)
            self.st.login, self.st.mensagem = "ok", f"{len(self.contas)} contas carregadas."
        threading.Thread(target=f, daemon=True).start()

    def listar_contas(self):
        return list(self.contas)

    def buscar_contas(self, texto):
        t = texto.lower()
        return [{"numero": n, "nome": self.NOMES.get(n, "EMPRESA " + n), "tipo": "PF" if n == "14.035-0" else "PJ"}
                for n in self.contas if t in n.lower() or t in self.NOMES.get(n, "").lower()]

    def _acessar(self, pasta):
        def acessar(item, conta, primeiro, ultimo):
            time.sleep(float(os.environ.get("LID_FAKE_ATRASO_S", "0")))
            self.itens_feitos += 1
            chave = f"{item['numero']}|{item['tipo']}|{item['chave']}"
            fila = self.roteiro.get(chave)
            if fila:
                r = dict(fila.pop(0) if len(fila) > 1 else fila[0])
                if r.get("excecao"):
                    raise RuntimeError(r["excecao"])
                r.setdefault("empresa", self.NOMES.get(item["numero"], "EMPRESA"))
                if r.get("erro"):
                    return r
            empresa = self.NOMES.get(item["numero"], "EMPRESA " + item["numero"])
            destino = Path(pasta) / empresa.title() / str(item["ano"]) / "Banco" / "Sicoob" / item["numero"] / pedido.PASTA_TIPO[item["tipo"]]
            destino.mkdir(parents=True, exist_ok=True)
            arq = destino / f"{item['mes']:02d}.pdf"
            existia = arq.exists()
            arq.write_bytes(b"%PDF-1.4 arquivo de teste (backend fake)\n")
            return {"empresa": empresa, "pdf_path": str(arq), "_substituido": existia}
        return acessar

    def rodar_execucao(self, execucao, contas, pasta, cancelado, persistir, ao_terminar, ao_concluir=lambda item: None):
        def job():
            try:
                Runner(execucao, contas, self._acessar(pasta), self.nav_vivo, cancelado, ao_atualizar=persistir,
                       ao_concluir=ao_concluir).executar()
            finally:
                persistir(execucao)
                ao_terminar()
        threading.Thread(target=job, daemon=True).start()
