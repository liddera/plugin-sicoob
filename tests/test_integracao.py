"""Integração de ponta a ponta SEM portal: servidor MCP real (stdio) -> worker real -> runner real,
com o backend simulado (LID_FAKE=1), gravando arquivos de verdade em uma pasta temporária."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class Cliente:
    """Cliente MCP mínimo: fala JSON-RPC por linhas com o servidor."""

    def __init__(self, home: str, fake_env: dict | None = None, com_worker: bool = True):
        env = dict(os.environ)
        env.update(SICOOBBOT_HOME=home, CLAUDE_PLUGIN_DATA=str(Path(home) / "data"), PYTHONIOENCODING="utf-8")
        for k in [k for k in env if k.startswith("LID_")]:
            env.pop(k)
        if com_worker:
            env.update(LID_FAKE="1", LID_WORKER_CMD=json.dumps([sys.executable, str(RAIZ / "worker" / "main.py")]))
        env.update(fake_env or {})
        self.p = subprocess.Popen([sys.executable, str(RAIZ / "server" / "lid_server.py")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(RAIZ))
        self.n = 0
        self.resp = {}
        self.cond = threading.Condition()
        threading.Thread(target=self._ler, daemon=True).start()

    def _ler(self):
        for b in iter(self.p.stdout.readline, b""):
            m = json.loads(b.decode("utf-8"))
            with self.cond:
                self.resp[m.get("id")] = m
                self.cond.notify_all()

    def req(self, metodo, params=None, timeout=30):
        self.n += 1
        rid = self.n
        self.p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": metodo, "params": params or {}}) + "\n").encode())
        self.p.stdin.flush()
        with self.cond:
            if not self.cond.wait_for(lambda: rid in self.resp, timeout):
                raise TimeoutError(metodo)
            return self.resp.pop(rid)

    def tool(self, nome, args=None, timeout=30):
        r = self.req("tools/call", {"name": nome, "arguments": args or {}}, timeout)["result"]
        texto = r["content"][0]["text"]
        return r["isError"], texto

    def tool_json(self, nome, args=None, timeout=30):
        erro, texto = self.tool(nome, args, timeout)
        return erro, (json.loads(texto) if not erro and texto.lstrip().startswith(("{", "[")) else texto)

    def esperar(self, nome, pred, args=None, timeout=20):
        fim = time.time() + timeout
        while time.time() < fim:
            _, d = self.tool_json(nome, args)
            if pred(d):
                return d
            time.sleep(0.1)
        raise TimeoutError(f"{nome}: condição não atendida: {d}")

    def fechar(self):
        try:
            self.p.stdin.close()
            self.p.wait(10)
        except Exception:
            self.p.kill()
        for f in (self.p.stdout, self.p.stderr):
            try:
                f.close()
            except Exception:
                pass


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = str(Path(self._tmp.name) / "home")
        self.pasta = Path(self._tmp.name) / "Contabil"
        for n in ("Auto Posto Avenida Ltda", "Posto Patrao Ltda"):
            (self.pasta / n).mkdir(parents=True)
        self.cli = None

    def tearDown(self):
        if self.cli:
            self.cli.fechar()
        self._tmp.cleanup()

    def iniciar(self, **kw):
        self.cli = Cliente(self.home, **kw)
        self.cli.req("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "teste", "version": "1"}})
        return self.cli

    def logar(self):
        c = self.cli
        c.tool("conectar", timeout=30)
        c.esperar("login_status", lambda d: d["login"] == "ok")

    def pedido(self, **extra):
        p = {"pasta": str(self.pasta), "contas": ["47.041-4", "109.317-7"], "documentos": ["corrente", "capital"],
             "meses": ["08/2026 a 09/2026"]}
        p.update(extra)
        return p


class TestProtocolo(Base):
    def test_initialize_e_lista_de_ferramentas(self):
        c = self.iniciar()
        r = c.req("initialize", {"protocolVersion": "2024-11-05"})["result"]
        self.assertEqual(r["protocolVersion"], "2024-11-05")
        self.assertEqual(r["serverInfo"]["name"], "lid-sicoob")
        self.assertIn("tools", r["capabilities"])
        r2 = c.req("initialize", {"protocolVersion": "1999-01-01"})["result"]
        self.assertEqual(r2["protocolVersion"], "2025-06-18")  # negocia para uma suportada
        tools = c.req("tools/list")["result"]["tools"]
        nomes = {t["name"] for t in tools}
        self.assertEqual(nomes, {"preparar", "preparar_status", "diagnostico", "conectar", "login_status", "listar_contas",
                                 "buscar_conta", "validar_pedido", "extrair", "status", "cancelar", "resultados", "atalho_contas", "historico"})
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object")
            self.assertTrue(t["description"])
        self.assertEqual(c.req("ping")["result"], {})
        self.assertEqual(c.req("metodo/inexistente")["error"]["code"], -32601)

    def test_ambiente_nao_preparado_orienta_o_usuario(self):
        c = self.iniciar(com_worker=False)  # sem worker de teste: usa a checagem real do ambiente
        erro, txt = c.tool("conectar")
        self.assertTrue(erro)
        self.assertIn("/lid:preparar", txt)
        erro, d = c.tool_json("preparar_status")
        self.assertFalse(erro)
        self.assertFalse(d["ambiente"]["pronto"])
        self.assertTrue(d["ambiente"]["motivos"])
        erro, d = c.tool_json("diagnostico")
        self.assertFalse(erro)
        self.assertIn("lid.log", d["log"])


class TestFluxoCompleto(Base):
    def test_sem_login_nao_extrai(self):
        c = self.iniciar()
        erro, txt = c.tool("extrair", {**self.pedido(), "confirmado": True})
        self.assertTrue(erro)
        self.assertIn("login", txt.lower())

    def test_login_validacao_e_extracao(self):
        c = self.iniciar()
        erro, d = c.tool_json("login_status")
        self.assertEqual(d["navegador"], "fechado")
        c.tool("conectar")
        d = c.esperar("login_status", lambda x: x["login"] == "ok")
        self.assertEqual(d["contas_carregadas"], 3)
        self.assertEqual(c.tool_json("listar_contas")[1]["contas"], ["47.041-4", "109.317-7", "14.035-0"])
        self.assertEqual(c.tool_json("buscar_conta", {"texto": "patrao"})[1]["encontradas"][0]["numero"], "109.317-7")

        # pedido com problemas: conta inexistente, documento inválido, mês futuro, pasta inexistente
        _, v = c.tool_json("validar_pedido", {"pasta": "/nao/existe", "contas": ["99.999-9"], "documentos": ["pix"], "meses": ["01/2099"]})
        self.assertFalse(v["ok"])
        txt = " | ".join(v["problemas"])
        for trecho in ("conta não encontrada", "documento não reconhecido", "futuro", "pasta"):
            self.assertIn(trecho, txt)

        # pedido bom
        _, v = c.tool_json("validar_pedido", self.pedido(contas=["47041-4", "1093177"]))
        self.assertTrue(v["ok"], v)
        self.assertEqual(v["resumo"]["total_itens"], 8)
        self.assertEqual(v["pasta"]["empresas_total"], 2)

        # sem confirmação não executa
        erro, txt = c.tool("extrair", self.pedido())
        self.assertTrue(erro)
        self.assertIn("confirm", txt)

        erro, ini = c.tool_json("extrair", {**self.pedido(), "confirmado": True})
        self.assertFalse(erro, ini)
        self.assertEqual(ini["total_itens"], 8)
        st = c.esperar("status", lambda s: s.get("status") == "finished")
        self.assertEqual((st["ok"], st["erros"], st["itens_total"]), (8, 0, 8))

        _, rel = c.tool("resultados")
        self.assertIn("| 47.041-4 |", rel)
        self.assertIn("8 gerado(s)", rel)
        # arquivos de verdade, na estrutura do robô
        alvo = self.pasta / "Auto Posto Avenida Ltda" / "2026" / "Banco" / "Sicoob" / "47.041-4"
        self.assertTrue((alvo / "Extrato CC" / "08.pdf").is_file())
        self.assertTrue((alvo / "Extratos Conta Capital" / "09.pdf").is_file())
        # a última execução ficou gravada em disco
        gravado = json.loads((Path(self.home) / "lid" / "ultima_execucao.json").read_text(encoding="utf-8"))
        self.assertEqual(gravado["status"], "finished")
        # log em arquivo existe e não tem erro interno
        log = (Path(self.home) / "lid" / "logs" / "lid.log").read_text(encoding="utf-8")
        self.assertIn("EVENTO extrair", log)
        self.assertNotIn("[ERROR]", log)

        # segunda rodada: os arquivos existem, então são "substituídos"
        c.tool("extrair", {**self.pedido(contas=["47.041-4"], documentos=["corrente"], meses=["08/2026"]), "confirmado": True})
        c.esperar("status", lambda s: s.get("status") == "finished" and s["itens_total"] == 1)
        _, rel = c.tool("resultados")
        self.assertIn("substituído", rel)

    def test_nao_deixa_rodar_duas_extracoes(self):
        c = self.iniciar(fake_env={"LID_FAKE_ATRASO_S": "0.4"})
        self.logar()
        c.tool("extrair", {**self.pedido(), "confirmado": True})
        erro, txt = c.tool("extrair", {**self.pedido(), "confirmado": True})
        self.assertTrue(erro)
        self.assertIn("andamento", txt)
        c.tool("cancelar")
        c.esperar("status", lambda s: s.get("status") in ("cancelled", "finished"))


class TestRefazerCancelarInterromper(Base):
    def test_erro_aviso_e_refazer(self):
        roteiro = {
            "47.041-4|corrente|08/2026": [{"erro": "❌ Timeout no fluxo"}],                  # falha sempre -> erro definitivo
            "109.317-7|capital|09/2026": [{"erro": "⚠️ Conta 109.317-7 sem cartões de crédito vinculados."}],  # aviso
        }
        c = self.iniciar(fake_env={"LID_FAKE_ROTEIRO": json.dumps(roteiro)})
        self.logar()
        c.tool("extrair", {**self.pedido(), "confirmado": True})
        st = c.esperar("status", lambda s: s.get("status") == "finished")
        self.assertEqual((st["erros"], st["avisos"], st["ok"]), (1, 1, 6))
        _, rel = c.tool("resultados")
        self.assertIn("❌ erro: Timeout no fluxo", rel)
        self.assertIn("⚠️ aviso", rel)

        # refazer só o item com erro (o roteiro continua falhando: o item volta a ser erro, só ele roda)
        erro, ini = c.tool_json("extrair", {"refazer": "erro", "confirmado": True})
        self.assertFalse(erro, ini)
        self.assertEqual(ini["total_itens"], 1)
        st = c.esperar("status", lambda s: s.get("status") == "finished" and s["itens_total"] == 1)
        self.assertEqual(st["erros"], 1)

    def test_cancelar_e_continuar(self):
        c = self.iniciar(fake_env={"LID_FAKE_ATRASO_S": "0.25"})
        self.logar()
        c.tool("extrair", {**self.pedido(), "confirmado": True})
        time.sleep(0.6)
        erro, d = c.tool_json("cancelar")
        self.assertTrue(d["cancelado"])
        st = c.esperar("status", lambda s: s.get("status") == "cancelled")
        self.assertGreater(st["nao_executados"], 0)
        feitos = st["ok"]
        # continuar de onde parou: roda só o que faltava
        erro, ini = c.tool_json("extrair", {"refazer": "continuar", "confirmado": True})
        self.assertFalse(erro, ini)
        self.assertEqual(ini["total_itens"], 8 - feitos)
        c.esperar("status", lambda s: s.get("status") == "finished" and s["itens_total"] == 8 - feitos, timeout=30)

    def test_navegador_fechado_interrompe_sem_marcar_erro(self):
        c = self.iniciar(fake_env={"LID_FAKE_FECHAR_APOS": "2"})
        self.logar()
        c.tool("extrair", {**self.pedido(), "confirmado": True})
        st = c.esperar("status", lambda s: s.get("status") == "interrompida")
        self.assertEqual(st["ok"], 2)
        self.assertEqual(st["erros"], 0)
        self.assertEqual(st["nao_executados"], 6)
        _, d = c.tool_json("login_status")
        self.assertEqual(d["login"], "erro")  # o plugin percebe e manda refazer o login

    def test_atalho_pendentes_e_com_erro_lendo_o_controle_do_robo(self):
        hoje = time.strftime("%Y-%m-%d")
        ctl = {"versao": 1, "atualizado_em": "", "ciclos": {f"{hoje}::corrente": {"contas": {
            "47.041-4": {"status": "sucesso"},
            "109.317-7": {"status": "erro", "periodos": {"09/2026": {"status": "erro", "erro_resumo": "x"}}}}, "execucoes": {}}}}
        Path(self.home).mkdir(parents=True, exist_ok=True)
        ctl_path = Path(self.home) / "controle_execucao_contas.json"
        ctl_path.write_text(json.dumps(ctl), encoding="utf-8")
        antes = ctl_path.read_bytes()
        c = self.iniciar()
        self.logar()
        _, d = c.tool_json("atalho_contas", {"modo": "com_erro", "documento": "corrente", "fonte": "robo"})
        self.assertEqual(d["contas"], ["109.317-7"])
        _, d = c.tool_json("atalho_contas", {"modo": "pendentes", "documento": "corrente", "fonte": "robo"})
        self.assertEqual(d["contas"], ["14.035-0"])
        self.assertEqual(ctl_path.read_bytes(), antes)  # somente leitura




class TestHistoricoPropriO(Base):
    def _ler_linhas(self, nome="itens.jsonl"):
        arq = Path(self.home) / "lid" / "historico" / nome
        return [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_cada_item_vai_para_o_historico_com_dados_completos(self):
        roteiro = {"109.317-7|capital|09/2026": [{"erro": "⚠️ Conta 109.317-7 sem cartões de crédito vinculados."}],
                   "47.041-4|corrente|08/2026": [{"erro": "❌ Timeout no fluxo 'corrente'"}]}
        c = self.iniciar(fake_env={"LID_FAKE_ROTEIRO": json.dumps(roteiro)})
        self.logar()
        c.tool("extrair", {**self.pedido(), "confirmado": True})
        c.esperar("status", lambda s: s.get("status") == "finished")
        regs = self._ler_linhas()
        self.assertEqual(len(regs), 8)  # um registro por item concluído
        por = {(r["numero"], r["tipo"], r["chave"]): r for r in regs}
        ok = por[("47.041-4", "corrente", "09/2026")]
        self.assertEqual((ok["resultado"], ok["origem"], ok["plugin"], ok["chromium"]), ("sucesso", "plugin", "0.3.0", "153.0.8010.12"))
        self.assertTrue(ok["pdf_path"].endswith("09.pdf") and ok["tamanho_bytes"] > 0)
        self.assertIn("inicio", ok)
        self.assertIsNotNone(ok["duracao_s"])
        erro = por[("47.041-4", "corrente", "08/2026")]
        self.assertEqual((erro["resultado"], erro["codigo"], erro["tentativas"]), ("erro", "tempo_esgotado", 2))
        aviso = por[("109.317-7", "capital", "09/2026")]
        self.assertEqual((aviso["resultado"], aviso["codigo"]), ("aviso", "sem_cartao"))
        execs = self._ler_linhas("execucoes.jsonl")
        self.assertEqual([e["evento"] for e in execs], ["inicio", "fim"])
        self.assertEqual((execs[1]["ok"], execs[1]["avisos"], execs[1]["erros"]), (6, 1, 1))

    def test_atalhos_pendentes_e_com_erro_e_apenas_pendentes(self):
        roteiro = {"47.041-4|corrente|08/2026": [{"erro": "❌ Timeout no fluxo"}]}
        c = self.iniciar(fake_env={"LID_FAKE_ROTEIRO": json.dumps(roteiro)})
        self.logar()
        ped = self.pedido(contas=["47.041-4"], documentos=["corrente"], meses=["08/2026 a 09/2026"])
        c.tool("extrair", {**ped, "confirmado": True})
        c.esperar("status", lambda s: s.get("status") == "finished")
        # com erro: só o item cujo último resultado foi erro
        _, d = c.tool_json("atalho_contas", {"modo": "com_erro"})
        self.assertEqual([(i["numero"], i["chave"], i["codigo"]) for i in d["itens"]], [("47.041-4", "08/2026", "tempo_esgotado")])
        self.assertEqual(d["fonte"], "histórico do plugin")
        # pendentes: do pedido (2 contas × corrente × 2 meses), falta tudo da conta 109.317-7 e o mês com erro da 47.041-4
        _, d = c.tool_json("atalho_contas", {"modo": "pendentes", "documentos": ["corrente"], "meses": ["08/2026 a 09/2026"],
                                            "contas": ["47.041-4", "109.317-7"]})
        self.assertEqual((d["itens_pedidos"], d["itens_pendentes"]), (4, 3))
        self.assertEqual(d["contas"], ["47.041-4", "109.317-7"])
        # apenas_pendentes: no pedido completo, só roda o que falta (sucesso anterior é pulado)
        ped2 = self.pedido(contas=["47.041-4", "109.317-7"], documentos=["corrente"], meses=["08/2026 a 09/2026"])
        _, v = c.tool_json("validar_pedido", {**ped2, "apenas_pendentes": True})
        self.assertTrue(v["ok"], v)
        self.assertTrue(any("Só o que falta: 3 de 4" in a for a in v["avisos"]), v["avisos"])
        erro, ini = c.tool_json("extrair", {**ped2, "apenas_pendentes": True, "confirmado": True})
        self.assertFalse(erro, ini)
        self.assertEqual(ini["total_itens"], 3)
        c.esperar("status", lambda s: s.get("status") == "finished" and s["itens_total"] == 3)
        # agora só sobra o item que continua falhando; tudo o mais foi feito
        _, v = c.tool_json("validar_pedido", {**ped2, "apenas_pendentes": True})
        self.assertTrue(v["ok"])
        self.assertTrue(any("Só o que falta: 1 de 4" in a for a in v["avisos"]))

    def test_nada_pendente_e_recusado_com_mensagem_clara(self):
        c = self.iniciar()
        self.logar()
        ped = self.pedido(contas=["47.041-4"], documentos=["corrente"], meses=["09/2026"])
        c.tool("extrair", {**ped, "confirmado": True})
        c.esperar("status", lambda s: s.get("status") == "finished")
        _, v = c.tool_json("validar_pedido", {**ped, "apenas_pendentes": True})
        self.assertFalse(v["ok"])
        self.assertIn("Nada a fazer", " ".join(v["problemas"]))

    def test_consulta_historico_por_item(self):
        c = self.iniciar()
        self.logar()
        ped = self.pedido(contas=["47.041-4"], documentos=["capital"], meses=["09/2026"])
        c.tool("extrair", {**ped, "confirmado": True})
        c.esperar("status", lambda s: s.get("status") == "finished")
        _, d = c.tool_json("historico", {"consulta": "item", "conta": "470414", "documento": "extrato capital", "mes": "09/2026"})
        self.assertTrue(d["encontrado"])
        self.assertEqual(d["ultimo"]["resultado"], "sucesso")
        self.assertTrue(d["ultimo_sucesso"]["pdf_path"].endswith("09.pdf"))
        _, d = c.tool_json("historico", {"consulta": "item", "conta": "47.041-4", "documento": "corrente", "mes": "01/2026"})
        self.assertFalse(d["encontrado"])
        _, d = c.tool_json("historico", {"consulta": "resumo"})
        self.assertEqual(d["itens_distintos"], 1)
        self.assertEqual(d["execucoes_concluidas"], 1)

    def test_historico_sobrevive_a_arquivo_cortado_por_uma_queda(self):
        c = self.iniciar()
        self.logar()
        ped = self.pedido(contas=["47.041-4"], documentos=["corrente"], meses=["08/2026 a 09/2026"])
        c.tool("extrair", {**ped, "confirmado": True})
        c.esperar("status", lambda s: s.get("status") == "finished")
        arq = Path(self.home) / "lid" / "historico" / "itens.jsonl"
        with open(arq, "ab") as f:
            f.write(b'{"schema":1,"evento":"item","run_id":"x","numero":"47.041-4","tipo":"corre')  # linha cortada no meio
        _, d = c.tool_json("historico", {"consulta": "resumo"})
        self.assertEqual(d["itens_distintos"], 2)       # os registros bons continuam valendo
        self.assertEqual(d["linhas_ignoradas"], 1)      # e a linha quebrada é contada, não derruba nada


if __name__ == "__main__":
    unittest.main()
