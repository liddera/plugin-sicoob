#!/usr/bin/env python3
"""Servidor MCP (stdio) do plugin lid. Só biblioteca padrão: funciona ANTES do /lid:preparar.

Ele não controla o navegador: encaminha as chamadas ao `worker` (processo no ambiente com Playwright), que é
quem abre o Chromium. Assim uma queda do navegador não derruba o servidor, e o servidor consegue oferecer a
ferramenta `preparar` mesmo sem o Playwright instalado.

Protocolo MCP (JSON-RPC 2.0, uma mensagem por linha): initialize, notifications/initialized, ping,
tools/list, tools/call.
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import Future, TimeoutError as FutTimeout
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "server"))

from core import logs, paths  # noqa: E402
import setup_env  # noqa: E402

VERSOES_SUPORTADAS = ["2025-06-18", "2025-03-26", "2024-11-05"]
NOME_SERVIDOR = "lid-sicoob"


def _versao_plugin() -> str:
    try:
        return json.loads((RAIZ / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("version", "0")
    except Exception:
        return "0"


_STR = {"type": "string"}
_LISTA_STR = {"type": "array", "items": {"type": "string"}}
_PEDIDO = {
    "pasta": {"type": "string", "description": "Pasta base (raiz que contém as pastas das empresas), ex.: H:\\Drives compartilhados\\Contábil"},
    "contas": {**_LISTA_STR, "description": "Números das contas (ex.: 47.041-4) ou [\"todas\"]"},
    "documentos": {**_LISTA_STR, "description": "corrente, capital, comprovantes, cartão (ou [\"todos\"])"},
    "meses": {**_LISTA_STR, "description": "Meses como 06/2026 ou intervalos como 06/2026 a 09/2026"},
    "refazer": {"type": "string", "enum": ["erro", "continuar"],
                "description": "Refaz só os itens com erro, ou continua os que não rodaram, da última execução (ignora contas/documentos/meses)"},
    "apenas_pendentes": {"type": "boolean",
                         "description": "Roda só os itens do pedido que nunca tiveram sucesso no histórico do plugin (pula o que já foi feito)"},
}

# nome, descrição, op do worker (None = local), timeout (s), só leitura, propriedades do schema, obrigatórios
TOOLS = [
    ("preparar", "Prepara o computador para usar o plugin: cria o ambiente Python, instala o Playwright 1.63.0 e baixa o Chromium 153 "
     "(≈200 MB, uma vez). Roda em segundo plano; acompanhe com preparar_status.", None, 30, False, {}, []),
    ("preparar_status", "Mostra se o ambiente está pronto e o andamento da preparação.", None, 60, True, {}, []),
    ("diagnostico", "Mostra caminhos, versões e as últimas linhas do log do plugin (sem dados bancários), para suporte.", None, 30, True,
     {"linhas": {"type": "integer", "description": "quantas linhas finais do log (padrão 30)"}}, []),
    ("conectar", "Abre o navegador do Sicoob na tela de login e aguarda o QR code. O login e o cadastro de dispositivo são MANUAIS "
     "(o usuário escaneia o QR). Nunca feche o navegador logado. Depois consulte login_status. A resposta traz `perfil`: situação 'novo' "
     "(primeira vez: o Sicoob pede o cadastro do dispositivo) ou 'existente' (perfil já usado neste computador). Se vier "
     "`precisa_confirmar`, o perfil é de uma versão mais antiga do navegador (em geral, do SicoobBot): pergunte ao usuário e só então chame de novo com aceitar_atualizar_perfil=true.",
     "conectar", 200, False,
     {"aceitar_atualizar_perfil": {"type": "boolean", "description": "true só depois de o usuário aceitar que o perfil de uma versão antiga do navegador seja atualizado"}}, []),
    ("login_status", "Informa se o navegador está aberto, se o login foi concluído e quantas contas foram carregadas.", "login_status", 30, True, {}, []),
    ("listar_contas", "Lista os números das contas carregadas do portal depois do login.", "listar_contas", 120, True, {}, []),
    ("buscar_conta", "Busca contas no portal por número ou nome da empresa. Devolve número, nome e tipo (PJ/PF), nunca CNPJ/CPF.",
     "buscar_conta", 120, True, {"texto": {"type": "string", "description": "número ou parte do nome"}}, ["texto"]),
    ("validar_pedido", "Valida o pedido SEM executar: confere pasta, contas, documentos e meses e devolve o resumo com o total de itens e os problemas.",
     "validar_pedido", 60, True, _PEDIDO, []),
    ("extrair", "Inicia a extração em segundo plano. Só chame depois de o usuário confirmar o resumo (confirmado=true). "
     "Acompanhe com status e veja o relatório com resultados.", "extrair", 60, False,
     {**_PEDIDO, "confirmado": {"type": "boolean", "description": "true somente após o usuário confirmar o resumo"}}, ["confirmado"]),
    ("status", "Andamento da extração (itens feitos, item atual, avisos, erros).", "status", 15, True, {}, []),
    ("cancelar", "Cancela a extração ao fim do item atual (não fecha o navegador).", "cancelar", 15, False, {}, []),
    ("resultados", "Relatório da última extração: conta, empresa, documento, mês, resultado e arquivo. Nunca inclui saldos nem movimentos.",
     "resultados", 30, True, {}, []),
    ("atalho_contas", "Contas pendentes ou com erro, a partir do histórico do plugin (padrão) ou do controle do SicoobBot (fonte='robo', somente leitura). "
     "'com_erro': itens cujo último resultado foi erro. 'pendentes': dos documentos e meses informados, o que nunca teve sucesso.",
     "atalho_contas", 60, True,
     {"modo": {"type": "string", "enum": ["pendentes", "com_erro"]},
      "documentos": {**_LISTA_STR, "description": "documentos (obrigatório para 'pendentes')"},
      "meses": {**_LISTA_STR, "description": "meses (obrigatório para 'pendentes')"},
      "contas": {**_LISTA_STR, "description": "restringe a estas contas (padrão: todas as carregadas)"},
      "fonte": {"type": "string", "enum": ["plugin", "robo"], "description": "padrão plugin"},
      "documento": {"type": "string", "description": "só para fonte='robo' (padrão corrente)"}}, ["modo"]),
    ("historico", "Consulta o histórico do plugin: 'resumo' (contagens) ou 'item' (último resultado e último sucesso de uma conta, documento e mês, "
     "com o caminho do arquivo). Nunca inclui saldos nem movimentos.", "historico", 30, True,
     {"consulta": {"type": "string", "enum": ["resumo", "item"]}, "conta": _STR, "documento": _STR,
      "mes": {"type": "string", "description": "MM/AAAA"}}, ["consulta"]),
]
_POR_NOME = {t[0]: t for t in TOOLS}


def _lista_ferramentas() -> list[dict]:
    saida = []
    for nome, desc, _op, _t, leitura, props, obrig in TOOLS:
        schema = {"type": "object", "properties": props, "additionalProperties": False}
        if obrig:
            schema["required"] = obrig
        saida.append({"name": nome, "description": desc, "inputSchema": schema,
                      "annotations": {"readOnlyHint": leitura, "openWorldHint": True}})
    return saida


# ----------------------------------------------------------------------------- worker
class Worker:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.trava = threading.Lock()
        self.pend: dict[int, Future] = {}
        self.ids = itertools.count(1)

    def _comando(self) -> list[str]:
        override = os.environ.get("LID_WORKER_CMD")
        if override:
            return json.loads(override)
        return [str(paths.venv_python()), str(RAIZ / "worker" / "main.py")]

    def _subir(self) -> None:
        env = dict(os.environ)
        env.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", PLAYWRIGHT_BROWSERS_PATH="0")
        flags = {"creationflags": 0x08000000} if os.name == "nt" else {}
        self.proc = subprocess.Popen(self._comando(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=env, cwd=str(RAIZ), **flags)
        logs.evento("worker_subiu", pid=self.proc.pid)
        threading.Thread(target=self._ler_saida, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._ler_erros, args=(self.proc,), daemon=True).start()

    def _ler_saida(self, proc) -> None:
        for bruto in iter(proc.stdout.readline, b""):
            try:
                msg = json.loads(bruto.decode("utf-8"))
            except Exception:
                continue
            fut = self.pend.pop(msg.get("id"), None)
            if fut and not fut.done():
                fut.set_result(msg)
        codigo = proc.wait()
        logs.evento("worker_encerrou", pid=proc.pid, codigo=codigo)
        for fut in list(self.pend.values()):
            if not fut.done():
                fut.set_exception(RuntimeError("O processo do plugin foi encerrado de repente (o navegador fecha junto). "
                                               "Rode /lid:login de novo."))
        self.pend.clear()
        with self.trava:
            if self.proc is proc:
                self.proc = None

    def _ler_erros(self, proc) -> None:
        for bruto in iter(proc.stderr.readline, b""):
            linha = bruto.decode("utf-8", "replace").strip()
            if linha:
                logs.log("worker stderr: " + linha[:300], "WARN")

    def chamar(self, op: str, args: dict, timeout: float) -> dict:
        with self.trava:
            if self.proc is None or self.proc.poll() is not None:
                self._subir()
            proc = self.proc
            rid = next(self.ids)
            fut: Future = Future()
            self.pend[rid] = fut
            proc.stdin.write((json.dumps({"id": rid, "op": op, "args": args}, ensure_ascii=False) + "\n").encode("utf-8"))
            proc.stdin.flush()
        try:
            return fut.result(timeout)
        except FutTimeout:
            self.pend.pop(rid, None)
            raise RuntimeError(f"A operação '{op}' passou de {int(timeout)} s sem resposta (ela pode ter continuado em segundo plano; "
                               "consulte status ou login_status).")

    def encerrar(self) -> None:
        with self.trava:
            p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.close()
            except Exception:
                pass
            try:
                p.terminate()
            except Exception:
                pass


WORKER = Worker()


# ----------------------------------------------------------------------------- tools
def _texto(data) -> str:
    return data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)


def _resultado_tool(texto: str, erro: bool = False) -> dict:
    return {"content": [{"type": "text", "text": texto}], "isError": erro}


def _ultimas_linhas_do_log(n: int) -> list[str]:
    try:
        return (paths.logs_dir() / "lid.log").read_text(encoding="utf-8").splitlines()[-n:]
    except Exception:
        return []


def _ambiente_ou_motivo() -> str | None:
    """None se dá para chamar o worker; senão, a mensagem para o usuário."""
    if os.environ.get("LID_WORKER_CMD"):
        return None
    chk = setup_env.checar_ambiente()
    if chk["pronto"]:
        return None
    return "O ambiente do plugin não está pronto: " + " ".join(chk["motivos"]) + " Rode /lid:preparar."


def executar_ferramenta(nome: str, args: dict) -> dict:
    if nome not in _POR_NOME:
        return _resultado_tool(f"Ferramenta desconhecida: {nome}", True)
    _n, _d, op, timeout, _l, _p, _o = _POR_NOME[nome]
    try:
        if nome == "preparar":
            return _resultado_tool(_texto(setup_env.iniciar_preparo()))
        if nome == "preparar_status":
            return _resultado_tool(_texto({"ambiente": setup_env.checar_ambiente(forcar=True), "preparo": setup_env.estado_preparo()}))
        if nome == "diagnostico":
            n = int(args.get("linhas") or 30)
            return _resultado_tool(_texto({
                "plugin": _versao_plugin(), "pasta_base": str(paths.home_dir()), "perfil": str(paths.perfil_dir()),
                "log": str(paths.logs_dir() / "lid.log"), "ambiente": setup_env.checar_ambiente(),
                "ultimas_linhas_do_log": _ultimas_linhas_do_log(max(1, min(n, 200)))}))
        motivo = _ambiente_ou_motivo()
        if motivo:
            return _resultado_tool(motivo, True)
        resp = WORKER.chamar(op, args or {}, timeout)
        if not resp.get("ok"):
            return _resultado_tool(resp.get("erro", "erro desconhecido"), True)
        data = resp.get("data")
        if nome == "resultados" and isinstance(data, dict) and "relatorio" in data:
            return _resultado_tool(data["relatorio"])
        return _resultado_tool(_texto(data))
    except Exception as e:
        logs.log(f"falha na ferramenta {nome}: {e}", "ERROR")
        return _resultado_tool(str(e), True)


# ----------------------------------------------------------------------------- protocolo MCP
_SAIDA = threading.Lock()


def enviar(msg: dict) -> None:
    with _SAIDA:
        sys.stdout.buffer.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()


def tratar(req: dict) -> None:
    metodo, rid = req.get("method"), req.get("id")
    if rid is None:  # notificação: sem resposta
        return
    try:
        if metodo == "initialize":
            pedida = (req.get("params") or {}).get("protocolVersion")
            versao = pedida if pedida in VERSOES_SUPORTADAS else VERSOES_SUPORTADAS[0]
            resultado = {"protocolVersion": versao, "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": {"name": NOME_SERVIDOR, "version": _versao_plugin()},
                         "instructions": "Plugin lid (Sicoob): login manual por QR; só consulta e exporta; nunca devolva saldos ou movimentos."}
        elif metodo == "ping":
            resultado = {}
        elif metodo == "tools/list":
            resultado = {"tools": _lista_ferramentas()}
        elif metodo == "tools/call":
            p = req.get("params") or {}
            resultado = executar_ferramenta(p.get("name", ""), p.get("arguments") or {})
        else:
            enviar({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Método não suportado: {metodo}"}})
            return
        enviar({"jsonrpc": "2.0", "id": rid, "result": resultado})
    except Exception as e:  # nunca deixa uma requisição sem resposta
        logs.log(f"erro no protocolo ({metodo}): {e}", "ERROR")
        enviar({"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": f"Erro interno: {e}"}})


def main() -> None:
    logs.evento("servidor_inicio", versao=_versao_plugin(), python=sys.version.split()[0])
    stdin = sys.stdin.buffer
    ativas: list[threading.Thread] = []
    for bruto in iter(stdin.readline, b""):
        try:
            req = json.loads(bruto.decode("utf-8"))
        except Exception:
            continue
        t = threading.Thread(target=tratar, args=(req,), daemon=True)
        t.start()
        ativas = [a for a in ativas if a.is_alive()] + [t]
    for t in ativas:  # ao fechar a entrada, termina de responder o que já estava em andamento
        t.join(timeout=5)
    logs.evento("servidor_fim")
    WORKER.encerrar()


if __name__ == "__main__":
    main()
