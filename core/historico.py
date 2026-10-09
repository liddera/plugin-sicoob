"""Histórico PRÓPRIO do plugin: um registro por item concluído (conta × documento × mês). Só biblioteca padrão.

Formato: JSON Lines, só acrescentando (nunca reescreve o arquivo). Fica na PASTA DE DADOS DO PLUGIN (a mesma do robô:
%LOCALAPPDATA%\\SicoobBot no Windows; veja core/paths.py), e NÃO na pasta de destino dos PDFs escolhida no /lid:login:
  <pasta de dados>/lid/historico/itens.jsonl       um registro por item concluído
  <pasta de dados>/lid/historico/execucoes.jsonl   início e fim de cada execução

Por que não o `controle_execucao_contas.json` do robô: ele é por dia e por documento, guarda o status da CONTA com um só
arquivo e uma só mensagem, não tem horários, causa estruturada, "aviso", "sem movimento" nem "substituído", e é reescrito
inteiro pela tela do robô (dois programas escrevendo se atropelariam). O do robô continua só para consulta (core/controle.py).

Robustez:
- uma linha por registro, gravada de uma vez com flush + fsync: uma queda no meio perde, no máximo, a última linha;
- linhas quebradas ou desconhecidas são ignoradas na leitura (e contadas);
- campo `schema` em cada linha, para evoluir o formato sem quebrar leituras antigas;
- rotação por tamanho (itens.AAAAMMDD_HHMMSS.jsonl); a leitura junta todos os arquivos.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime
from pathlib import Path

from . import paths
from . import resultado as R

SCHEMA = 1
LIMITE_ROTACAO = 20 * 1024 * 1024  # 20 MB

_OK = {R.SUCESSO, R.SUBSTITUIDO, R.SEM_MOVIMENTO}


def pasta_historico() -> Path:
    d = paths.lid_dir() / "historico"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Historico:
    def __init__(self, pasta: Path | None = None):
        self.pasta = Path(pasta) if pasta else pasta_historico()
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._ruins: dict[str, int] = {}

    # ----------------------------------------------------------------- escrita
    def _arquivo(self, nome: str) -> Path:
        return self.pasta / nome

    def _rotacionar(self, arq: Path) -> None:
        """Move o arquivo cheio para um nome ÚNICO (nunca sobrescreve um rotacionado anterior)."""
        base = f"{arq.stem}.{datetime.now():%Y%m%d_%H%M%S_%f}"
        destino = arq.with_name(base + ".jsonl")
        n = 1
        while destino.exists():
            destino = arq.with_name(f"{base}_{n}.jsonl")
            n += 1
        arq.replace(destino)

    def _termina_sem_quebra_de_linha(self, arq: Path) -> bool:
        try:
            if not arq.exists() or arq.stat().st_size == 0:
                return False
            with open(arq, "rb") as f:
                f.seek(-1, os.SEEK_END)
                return f.read(1) != b"\n"
        except OSError:
            return False

    def _acrescentar(self, nome: str, registro: dict) -> None:
        linha = json.dumps(registro, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._trava:
            arq = self._arquivo(nome)
            try:
                if arq.exists() and arq.stat().st_size > LIMITE_ROTACAO:
                    self._rotacionar(arq)
            except OSError:
                pass
            dados = linha.encode("utf-8")
            if self._termina_sem_quebra_de_linha(arq):
                dados = b"\n" + dados  # uma queda deixou uma linha cortada: não cola o novo registro nela
            with open(arq, "ab") as f:
                f.write(dados)
                f.flush()
                os.fsync(f.fileno())

    def registrar_item(self, run_id: str, item: dict, contexto: dict | None = None) -> dict:
        """Grava o resultado de um item concluído. `contexto`: pasta_base, plugin, chromium..."""
        ctx = contexto or {}
        reg = {
            "schema": SCHEMA, "evento": "item", "run_id": run_id, "ts": R.agora(),
            "inicio": item.get("inicio", ""), "duracao_s": item.get("duracao_s"),
            "numero": item["numero"], "empresa": item.get("empresa", ""), "tipo": item["tipo"], "chave": item["chave"],
            "resultado": item.get("resultado"), "codigo": item.get("codigo", ""), "mensagem": item.get("mensagem", ""),
            "tentativas": item.get("tentativas", 0), "recuperacoes": item.get("recuperacoes", 0),
            "pdf_path": item.get("pdf_path", ""), "tamanho_bytes": item.get("tamanho_bytes"),
            "substituido": bool(item.get("substituido")), "sem_movimento": bool(item.get("sem_movimento")),
            "pasta_base": ctx.get("pasta_base", ""), "plugin": ctx.get("plugin", ""), "chromium": ctx.get("chromium", ""),
            "origem": "plugin",
        }
        self._acrescentar("itens.jsonl", reg)
        return reg

    def registrar_execucao(self, evento: str, execucao: dict, contexto: dict | None = None) -> None:
        """evento: 'inicio' ou 'fim'."""
        ctx = contexto or {}
        cont = R.contagens(execucao["itens"])
        self._acrescentar("execucoes.jsonl", {
            "schema": SCHEMA, "evento": evento, "run_id": execucao["run_id"], "ts": R.agora(),
            "status": execucao.get("status"), "itens": cont["total"], "ok": cont["ok"], "avisos": cont["avisos"],
            "erros": cont["erros"], "nao_executados": cont["nao_executados"],
            "pedido": {k: execucao.get("pedido", {}).get(k) for k in ("pasta", "contas", "tipos", "meses", "refazer")},
            "mensagem": execucao.get("mensagem", ""), "plugin": ctx.get("plugin", ""), "chromium": ctx.get("chromium", ""),
        })

    # ----------------------------------------------------------------- leitura
    def _arquivos(self, prefixo: str) -> list[Path]:
        return sorted(self.pasta.glob(f"{prefixo}*.jsonl"), key=lambda p: (p.name != f"{prefixo}.jsonl", p.name))

    def _ler(self, prefixo: str) -> list[dict]:
        regs: list[dict] = []
        ruins = 0
        # rotacionados (nome com data) primeiro, o atual por último: ordem cronológica
        arquivos = [p for p in self._arquivos(prefixo) if p.name != f"{prefixo}.jsonl"]
        atual = self._arquivo(f"{prefixo}.jsonl")
        if atual.exists():
            arquivos.append(atual)
        for arq in arquivos:
            try:
                bruto = arq.read_bytes().decode("utf-8", errors="replace")
            except OSError:
                continue
            for linha in bruto.splitlines():
                if not linha.strip():
                    continue
                try:
                    reg = json.loads(linha)
                    if isinstance(reg, dict) and reg.get("evento"):
                        regs.append(reg)
                    else:
                        ruins += 1
                except json.JSONDecodeError:
                    ruins += 1  # linha cortada por uma queda, ou lixo
        self._ruins[prefixo] = ruins
        return regs

    @property
    def linhas_ruins(self) -> int:
        """Linhas ignoradas (cortadas, lixo) nas últimas leituras de cada arquivo."""
        return sum(self._ruins.values())

    def itens(self) -> list[dict]:
        return [r for r in self._ler("itens") if r.get("evento") == "item"]

    def execucoes(self) -> list[dict]:
        return self._ler("execucoes")

    @staticmethod
    def _chave(reg: dict) -> tuple[str, str, str]:
        return (reg["numero"], reg["tipo"], reg["chave"])

    def indice(self) -> dict:
        """Por item: último registro, último sucesso e número de registros."""
        idx: dict = {}
        for r in self.itens():
            try:
                k = self._chave(r)
            except KeyError:
                continue
            e = idx.setdefault(k, {"ultimo": None, "ultimo_sucesso": None, "registros": 0})
            e["ultimo"] = r
            e["registros"] += 1
            if r.get("resultado") in _OK:
                e["ultimo_sucesso"] = r
        return idx

    # ----------------------------------------------------------------- consultas
    def ultimo_do_item(self, numero: str, tipo: str, chave: str) -> dict | None:
        return self.indice().get((numero, tipo, chave))

    def com_erro(self, contas: list[str] | None = None, tipos: list[str] | None = None) -> list[dict]:
        """Itens cujo ÚLTIMO resultado foi erro (e que nunca tiveram sucesso depois)."""
        saida = []
        for (numero, tipo, chave), e in self.indice().items():
            if contas is not None and numero not in contas:
                continue
            if tipos is not None and tipo not in tipos:
                continue
            u = e["ultimo"]
            if u and u.get("resultado") == R.ERRO:
                saida.append({"numero": numero, "tipo": tipo, "chave": chave, "codigo": u.get("codigo", ""),
                              "mensagem": u.get("mensagem", ""), "quando": u.get("ts", "")})
        return sorted(saida, key=lambda i: (i["numero"], i["tipo"], i["chave"]))

    def pendentes(self, itens_pedidos: list[dict], hoje: date | None = None) -> list[dict]:
        """Dos itens pedidos, os que ainda precisam rodar: nunca tiveram sucesso.

        Um AVISO (sem cartão, sem comprovantes) vale como resolvido, porque o portal não tem o que baixar; exceto no mês
        corrente, em que isso pode mudar amanhã.
        """
        mes_atual = (hoje or date.today()).strftime("%m/%Y")
        idx = self.indice()
        faltam = []
        for it in itens_pedidos:
            e = idx.get((it["numero"], it["tipo"], it["chave"]))
            if e is None:
                faltam.append(it)
                continue
            u = e["ultimo"]
            aviso_definitivo = u.get("resultado") == R.AVISO and it["chave"] != mes_atual
            if e["ultimo_sucesso"] is None and not aviso_definitivo:
                faltam.append(it)
        return faltam

    def resumo(self) -> dict:
        idx = self.indice()
        por_resultado: dict[str, int] = {}
        for e in idx.values():
            r = (e["ultimo"] or {}).get("resultado")
            por_resultado[r] = por_resultado.get(r, 0) + 1
        execs = [e for e in self.execucoes() if e.get("evento") == "fim"]
        return {"itens_distintos": len(idx), "ultimo_resultado_por_item": por_resultado, "execucoes_concluidas": len(execs),
                "linhas_ignoradas": self.linhas_ruins, "pasta": str(self.pasta)}
