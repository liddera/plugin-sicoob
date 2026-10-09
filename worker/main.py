#!/usr/bin/env python3
"""Worker do plugin lid: roda no ambiente que tem o Playwright e é dono do navegador.

Fala com o servidor MCP por linhas JSON em stdin/stdout:
  pedido:    {"id": 1, "op": "status", "args": {...}}
  resposta:  {"id": 1, "ok": true, "data": {...}}   ou   {"id": 1, "ok": false, "erro": "mensagem"}

Tudo que o código do robô imprime vai para o log (nunca para o canal do protocolo).
`LID_FAKE=1` troca o navegador por um backend simulado (testes do encanamento, sem portal).
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "vendor" / "sicoobbot"))

# Canal do protocolo = stdout original em UTF-8. Todo `print` do robô é desviado para o log.
_PROTO = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n", write_through=True)
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")


class _SaidaParaLog(io.TextIOBase):
    def write(self, s):
        from core import logs
        for linha in str(s).splitlines():
            if linha.strip():
                logs.log("stdout: " + linha.strip())
        return len(s or "")

    def flush(self):
        pass


sys.stdout = _SaidaParaLog()

from core import controle, logs, paths, pedido, perfil  # noqa: E402
from core.historico import Historico  # noqa: E402
from core import resultado as R  # noqa: E402
from worker.backend_real import Falha  # noqa: E402

_TRAVA_SAIDA = threading.Lock()


def responder(msg: dict) -> None:
    with _TRAVA_SAIDA:
        _PROTO.write(json.dumps(msg, ensure_ascii=False) + "\n")
        _PROTO.flush()


class Estado:
    def __init__(self):
        self.navegador = "fechado"      # fechado | aberto | travou
        self.login = "nao_iniciado"     # nao_iniciado | aguardando | carregando_contas | ok | erro
        self.mensagem = ""
        self.contas: list[str] = []
        self.execucao: dict | None = None
        self.cancelado = threading.Event()
        self.rodando = False
        self.trava = threading.Lock()


ST = Estado()
BACKEND = None
HIST = Historico()


def backend():
    global BACKEND
    if BACKEND is None:
        if os.environ.get("LID_FAKE") == "1":
            from worker.backend_fake import BackendFake
            BACKEND = BackendFake(ST)
        else:
            from worker.backend_real import BackendReal
            BACKEND = BackendReal(ST)
    return BACKEND


# ------------------------------------------------------------------ operações
def op_ping(_):
    return {"worker": "ok", "pid": os.getpid(), **backend().diagnostico()}


def _estado_login() -> dict:
    return {"navegador": ST.navegador, "login": ST.login, "mensagem": ST.mensagem, "contas_carregadas": len(ST.contas)}


def op_conectar(args):
    b = backend()
    args = args or {}
    if ST.navegador == "aberto" and b.vivo_rapido():
        if ST.login in ("ok", "aguardando", "carregando_contas"):
            return {**_estado_login(), "aviso": "O navegador já está aberto."}
        # o login deu erro/timeout, mas o navegador segue aberto: só espera o login de novo (não abre outro)
        ST.login, ST.mensagem = "aguardando", "Escaneie o QR code no navegador que já está aberto e não feche a janela."
        b.esperar_login_e_listar()
        return _estado_login()
    if ST.navegador in ("aberto", "travou"):
        ST.navegador = "fechado"
    versao = b.versao_chromium()
    chk = perfil.checar_perfil(versao)  # perfil em uso (robô aberto) ou de um Chromium mais novo: recusa com explicação
    if not chk["ok"]:
        logs.evento("perfil_bloqueado", codigo=chk["codigo"], versao_perfil=chk.get("versao_perfil"))
        raise Falha(chk["motivo"])
    sit = perfil.situacao(versao)
    if sit["afeta_robo_antigo"] and not args.get("aceitar_atualizar_perfil"):
        logs.evento("perfil_pede_confirmacao", versao_perfil=sit["versao_perfil"], versao_chromium=versao)
        return {"precisa_confirmar": True, "perfil": sit,
                "mensagem": sit["observacao"] + " Pergunte ao usuário; se ele aceitar, chame conectar de novo com "
                            "aceitar_atualizar_perfil=true. Se preferir não arriscar, atualize antes o programa que criou o perfil (por exemplo, o SicoobBot)."}
    ST.login, ST.mensagem = "aguardando", "Escaneie o QR code no navegador que abriu e não feche a janela."
    ST.contas = []
    b.abrir_navegador()
    ST.navegador = "aberto"
    b.esperar_login_e_listar()
    logs.evento("perfil_usado", situacao=sit["situacao"], versao_perfil=sit["versao_perfil"], versao_chromium=versao)
    return {**_estado_login(), "perfil": sit}


def op_login_status(_):
    if ST.navegador == "aberto" and not backend().vivo_rapido():
        ST.navegador = "fechado"
    if ST.navegador in ("fechado", "travou") and ST.login in ("aguardando", "carregando_contas", "ok"):
        ST.login = "erro"
        ST.mensagem = ("O navegador travou. Rode /lid:login de novo (novo QR)." if ST.navegador == "travou"
                       else "O navegador foi fechado. Rode /lid:login de novo (novo QR).")
    return _estado_login()


def _em_execucao() -> bool:
    """Há uma extração rodando? Decide pelo estado da própria execução (não por um flag separado)."""
    return bool(ST.execucao) and ST.execucao.get("status") == "running"


def _exigir_login():
    if ST.navegador != "aberto" or ST.login != "ok":
        raise Falha("Não há login ativo. Rode /lid:login e escaneie o QR code antes.")


def op_listar_contas(_):
    _exigir_login()
    return {"total": len(ST.contas), "contas": ST.contas}


def op_buscar_conta(args):
    _exigir_login()
    texto = str(args.get("texto", "")).strip()
    if len(texto) < 2:
        raise Falha("Informe pelo menos 2 caracteres para a busca.")
    if _em_execucao():
        raise Falha("Há uma extração em andamento; aguarde terminar para buscar contas.")
    return {"encontradas": backend().buscar_contas(texto)}


def _ultima_execucao() -> dict | None:
    return ST.execucao or R.carregar()


def _planejar(args: dict) -> dict:
    """Valida o pedido SEM abrir nada. Devolve o plano ou levanta Falha com todos os problemas."""
    problemas, avisos = [], []
    refazer = args.get("refazer")
    anterior = _ultima_execucao() if refazer else None
    if refazer:
        if refazer not in ("erro", "continuar"):
            raise Falha("refazer deve ser 'erro' ou 'continuar'.")
        if not anterior:
            raise Falha("Não há execução anterior para refazer.")
        base = anterior["itens"]
        alvos = R.itens_para_refazer(anterior, refazer)
        if not alvos:
            raise Falha("Não há itens para refazer nessa categoria na última execução.")
        pasta = args.get("pasta") or anterior["pedido"].get("pasta", "")
        itens_novos = [R.novo_item(i["numero"], i["tipo"], i["ano"], i["mes"]) for i in alvos]
        contas = list(dict.fromkeys(i["numero"] for i in itens_novos))
        tipos = list(dict.fromkeys(i["tipo"] for i in itens_novos))
        meses = sorted({(i["ano"], i["mes"]) for i in itens_novos})
    else:
        pasta = str(args.get("pasta", "")).strip()
        entradas = args.get("contas") or []
        if isinstance(entradas, str):
            entradas = [entradas]
        if [str(e).strip().lower() for e in entradas] in (["todas"], ["todos"]):
            contas = list(ST.contas)
            avisos.append(f"Todas as {len(contas)} contas foram selecionadas.")
        elif not ST.contas:
            contas = []
            problemas.append("A lista de contas do portal ainda não foi carregada (faça o login antes).")
        else:
            r = pedido.resolver_contas(entradas, ST.contas)
            contas = r["aceitas"]
            for f in r["nao_encontradas"]:
                sug = f" Parecidas: {', '.join(f['sugestoes'])}." if f["sugestoes"] else ""
                problemas.append(f"conta não encontrada na lista do portal: {f['entrada']}.{sug}")
        if not contas and not problemas:
            problemas.append("Nenhuma conta informada.")
        tipos, ruins = pedido.normalizar_tipos(args.get("documentos") or [])
        problemas += [f"documento não reconhecido: '{x}' (use corrente, capital, comprovantes ou cartão)" for x in ruins]
        if not tipos and not ruins:
            problemas.append("Nenhum documento informado.")
        meses, pm = pedido.expandir_meses(args.get("meses") or [])
        problemas += pm
        if not meses and not pm:
            problemas.append("Nenhum mês informado.")
        itens_novos = [R.novo_item(i["numero"], i["tipo"], i["ano"], i["mes"])
                       for i in pedido.montar_itens(contas, tipos, meses)] if contas and tipos and meses else []
        if args.get("apenas_pendentes") and itens_novos:
            total = len(itens_novos)
            faltam = {(i["numero"], i["tipo"], i["chave"]) for i in HIST.pendentes(itens_novos)}
            itens_novos = [i for i in itens_novos if (i["numero"], i["tipo"], i["chave"]) in faltam]
            if not itens_novos:
                problemas.append(f"Nada a fazer: os {total} itens do pedido já foram concluídos antes (histórico do plugin).")
            else:
                avisos.append(f"Só o que falta: {len(itens_novos)} de {total} itens (os outros já foram concluídos antes).")
    info_pasta = pedido.validar_pasta(pasta)
    problemas += info_pasta["erros"]
    avisos += info_pasta["avisos"]
    resumo = pedido.resumo_pedido(pasta, contas, tipos, meses) if (contas and tipos and meses) else None
    if resumo and itens_novos and len(itens_novos) != resumo["total_itens"]:
        resumo["total_itens_a_rodar"] = len(itens_novos)
    return {"problemas": problemas, "avisos": avisos, "pasta": info_pasta, "resumo": resumo,
            "itens": itens_novos, "contas": contas, "tipos": tipos, "meses": meses, "refazer": refazer}


def op_validar_pedido(args):
    p = _planejar(args)
    return {"ok": not p["problemas"], "problemas": p["problemas"], "avisos": p["avisos"],
            "pasta": {k: p["pasta"][k] for k in ("caminho", "ok", "empresas_total", "exemplos")},
            "resumo": p["resumo"],
            "login_ativo": ST.navegador == "aberto" and ST.login == "ok"}


def _persistir(e: dict) -> None:
    try:
        R.salvar(e)
    except Exception as ex:
        logs.log(f"falha ao gravar a execução: {ex}", "WARN")


def _terminou() -> None:
    ST.rodando = False


def op_extrair(args):
    if not args.get("confirmado"):
        raise Falha("O pedido precisa ser confirmado pelo usuário antes de executar (confirmado=true).")
    _exigir_login()
    with ST.trava:
        if _em_execucao():
            raise Falha("Já existe uma extração em andamento. Use /lid:status ou /lid:cancelar.")
        p = _planejar(args)
        if p["problemas"]:
            raise Falha("Pedido inválido: " + " | ".join(p["problemas"]))
        if not backend().vivo_rapido():
            raise Falha("O navegador não está respondendo. Rode /lid:login de novo.")
        pasta = p["pasta"]["caminho"]
        run_id = R.novo_run_id()
        pedido_gravado = {"pasta": pasta, "contas": p["contas"], "tipos": p["tipos"],
                          "meses": [pedido.chave_mes(a, m) for a, m in p["meses"]], "refazer": p["refazer"]}
        execucao = R.nova_execucao(run_id, pedido_gravado, p["itens"])
        ST.execucao = execucao
        ST.cancelado = threading.Event()
        ST.rodando = True
    _persistir(execucao)
    logs.evento("extrair", run_id=run_id, itens=len(p["itens"]), refazer=p["refazer"])
    ctx = {"pasta_base": pasta, "plugin": paths.versao_plugin(), "chromium": backend().versao_chromium() or ""}

    def _gravar_item(item):
        try:
            HIST.registrar_item(run_id, item, ctx)
        except Exception as ex:
            logs.log(f"falha ao gravar o histórico do item: {ex}", "WARN")

    def _terminar():
        try:
            HIST.registrar_execucao("fim", execucao, ctx)
        except Exception as ex:
            logs.log(f"falha ao gravar o histórico da execução: {ex}", "WARN")
        _terminou()

    try:
        HIST.registrar_execucao("inicio", execucao, ctx)
    except Exception as ex:
        logs.log(f"falha ao gravar o histórico da execução: {ex}", "WARN")
    backend().rodar_execucao(execucao, [{"numero": n, "empresa": ""} for n in p["contas"]], pasta,
                             ST.cancelado, _persistir, _terminar, _gravar_item)
    return {"run_id": run_id, "total_itens": len(p["itens"]), "mensagem": "Execução iniciada. Acompanhe com /lid:status."}


def op_status(_):
    e = _ultima_execucao()
    if not e:
        return {"status": "sem_execucao"}
    a = R.andamento(e)
    a["em_andamento"] = _em_execucao()
    a["navegador"] = ST.navegador
    return a


def op_cancelar(_):
    if not _em_execucao():
        return {"cancelado": False, "mensagem": "Não há extração em andamento."}
    ST.cancelado.set()
    return {"cancelado": True, "mensagem": "Cancelamento pedido: para ao fim do item atual."}


def op_resultados(args):
    e = _ultima_execucao()
    if not e:
        raise Falha("Ainda não há nenhuma execução.")
    return {"run_id": e["run_id"], "status": e["status"], "contagens": R.contagens(e["itens"]),
            "relatorio": R.relatorio_markdown(e), "em_andamento": _em_execucao()}


def op_atalho_contas(args):
    """Contas a (re)fazer, a partir do HISTÓRICO DO PLUGIN (padrão) ou do controle do robô (fonte='robo', só leitura)."""
    modo = args.get("modo")
    if modo not in ("pendentes", "com_erro"):
        raise Falha("modo deve ser 'pendentes' ou 'com_erro'.")
    if args.get("fonte") == "robo":
        tipo = pedido.normalizar_tipo(str(args.get("documento", "corrente"))) or "corrente"
        ctl = controle.carregar()
        if modo == "com_erro":
            itens = controle.itens_com_erro(ctl, [tipo])
            return {"fonte": "controle do SicoobBot (hoje, somente leitura)", "documento": tipo,
                    "contas": list(dict.fromkeys(i["numero"] for i in itens)), "itens": itens}
        _exigir_login()
        g = controle.classificar_contas(ctl, ST.contas, tipo)
        return {"fonte": "controle do SicoobBot (hoje, somente leitura)", "documento": tipo, "contas": g["pendentes"], "contagem": g["contagem"]}
    tipos, ruins = pedido.normalizar_tipos(args.get("documentos") or ([args["documento"]] if args.get("documento") else []))
    if ruins:
        raise Falha(f"documento não reconhecido: {', '.join(ruins)}")
    if modo == "com_erro":
        itens = HIST.com_erro(tipos=tipos or None)
        return {"fonte": "histórico do plugin", "contas": list(dict.fromkeys(i["numero"] for i in itens)), "itens": itens}
    _exigir_login()
    if not tipos:
        raise Falha("Informe os documentos para saber o que está pendente.")
    meses, pm = pedido.expandir_meses(args.get("meses") or [])
    if pm or not meses:
        raise Falha("Informe meses válidos para saber o que está pendente. " + " | ".join(pm))
    contas = ST.contas
    if args.get("contas"):
        r = pedido.resolver_contas(args["contas"], ST.contas)
        contas = r["aceitas"]
    pedidos = [R.novo_item(i["numero"], i["tipo"], i["ano"], i["mes"]) for i in pedido.montar_itens(contas, tipos, meses)]
    faltam = HIST.pendentes(pedidos)
    return {"fonte": "histórico do plugin", "itens_pedidos": len(pedidos), "itens_pendentes": len(faltam),
            "contas": list(dict.fromkeys(i["numero"] for i in faltam)),
            "exemplos": [{"numero": i["numero"], "tipo": i["tipo"], "chave": i["chave"]} for i in faltam[:10]]}


def op_historico(args):
    consulta = args.get("consulta")
    if consulta == "resumo":
        return HIST.resumo()
    if consulta == "item":
        numero = pedido.normalizar_conta(str(args.get("conta", "")))
        tipo = pedido.normalizar_tipo(str(args.get("documento", "")))
        mes = pedido.parse_mes(str(args.get("mes", "")))
        if not (numero and tipo and mes):
            raise Falha("Informe conta, documento e mês (ex.: 47.041-4, corrente, 08/2026).")
        e = HIST.ultimo_do_item(numero, tipo, pedido.chave_mes(*mes))
        if not e:
            return {"encontrado": False}
        campos = ("ts", "run_id", "resultado", "codigo", "mensagem", "pdf_path", "tamanho_bytes", "duracao_s", "tentativas")
        return {"encontrado": True, "registros": e["registros"],
                "ultimo": {k: e["ultimo"].get(k) for k in campos},
                "ultimo_sucesso": ({k: e["ultimo_sucesso"].get(k) for k in campos} if e["ultimo_sucesso"] else None)}
    raise Falha("consulta deve ser 'resumo' ou 'item'.")


OPS = {
    "ping": op_ping, "conectar": op_conectar, "login_status": op_login_status, "listar_contas": op_listar_contas,
    "buscar_conta": op_buscar_conta, "validar_pedido": op_validar_pedido, "extrair": op_extrair,
    "status": op_status, "cancelar": op_cancelar, "resultados": op_resultados, "atalho_contas": op_atalho_contas,
    "historico": op_historico,
}


def tratar(req: dict) -> None:
    rid = req.get("id")
    try:
        fn = OPS.get(req.get("op"))
        if not fn:
            raise Falha(f"operação desconhecida: {req.get('op')}")
        responder({"id": rid, "ok": True, "data": fn(req.get("args") or {})})
    except Falha as e:
        responder({"id": rid, "ok": False, "erro": str(e)})
    except Exception as e:
        logs.log("erro interno: " + traceback.format_exc(), "ERROR")
        responder({"id": rid, "ok": False, "erro": f"Erro interno do plugin: {e.__class__.__name__}: {e}"})


def main() -> None:
    logs.evento("worker_inicio", pid=os.getpid(), fake=os.environ.get("LID_FAKE") == "1")
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            req = json.loads(linha)
        except json.JSONDecodeError:
            continue
        threading.Thread(target=tratar, args=(req,), daemon=True).start()
    logs.evento("worker_fim", motivo="stdin fechado")


if __name__ == "__main__":
    main()
