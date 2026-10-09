"""Testes do histórico próprio e do código de erro (sem portal, sem navegador)."""
import json
import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core import resultado as R  # noqa: E402
from core.erros import codigo_erro  # noqa: E402
from core.historico import Historico  # noqa: E402
from core.runner import Runner  # noqa: E402
from core import pedido  # noqa: E402


def item(numero="A", tipo="corrente", ano=2026, mes=9, resultado="sucesso", **kw):
    it = R.novo_item(numero, tipo, ano, mes)
    it.update(resultado=resultado, **kw)
    return it


class TestCodigoErro(unittest.TestCase):
    def test_codigos(self):
        casos = {
            "Erro Playwright ao abrir tela de troca para conta X: Target page, context or browser has been closed": "navegador_fechado",
            "Conta 13.961-0 sem cartões de crédito vinculados.": "sem_cartao",
            "Não existem comprovantes para o período Dezembro/2026.": "sem_comprovantes",
            "Período divergente no extrato da conta capital. Esperado: 09/2026": "periodo_divergente",
            "Não foi possível identificar o período no extrato da conta capital.": "periodo_nao_identificado",
            "Falha ao aplicar período na conta X: Locator.wait_for: Timeout 10000ms exceeded.": "periodo_nao_aplicado",
            "Timeout no fluxo 'comprovantes' da conta X": "tempo_esgotado",
            "Botão 'Exportar extrato' permaneceu disabled": "exportar_desabilitado",
            "Timeout na exportação/download da conta X": "exportacao",
            "desistência: limite de recuperações da conta atingido": "limite_recuperacao",
            "algo que ninguém previu": "desconhecido",
            "": "",
        }
        for msg, esperado in casos.items():
            self.assertEqual(codigo_erro(msg), esperado, msg)


class TestHistorico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = Historico(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def gravar(self, **kw):
        it = item(**kw)
        it.setdefault("pdf_path", "")
        return self.h.registrar_item("r1", it, {"pasta_base": "/x", "plugin": "0.2.0", "chromium": "153"})

    def test_ultimo_resultado_e_ultimo_sucesso(self):
        self.gravar(resultado="sucesso", pdf_path="/a/09.pdf")
        self.gravar(resultado="erro", mensagem="falhou", codigo="tempo_esgotado")
        e = self.h.ultimo_do_item("A", "corrente", "09/2026")
        self.assertEqual(e["ultimo"]["resultado"], "erro")
        self.assertEqual(e["ultimo_sucesso"]["pdf_path"], "/a/09.pdf")  # o sucesso anterior continua conhecido
        self.assertEqual(e["registros"], 2)
        self.assertIsNone(self.h.ultimo_do_item("A", "capital", "09/2026"))

    def test_com_erro_so_considera_o_ultimo_resultado(self):
        self.gravar(numero="A", resultado="erro")
        self.gravar(numero="B", resultado="erro")
        self.gravar(numero="B", resultado="sucesso", pdf_path="/b.pdf")   # B se recuperou
        self.gravar(numero="C", tipo="capital", resultado="erro")
        self.assertEqual([i["numero"] for i in self.h.com_erro()], ["A", "C"])
        self.assertEqual([i["numero"] for i in self.h.com_erro(tipos=["capital"])], ["C"])
        self.assertEqual([i["numero"] for i in self.h.com_erro(contas=["A"])], ["A"])

    def test_pendentes(self):
        self.gravar(numero="A", mes=8, resultado="sucesso", pdf_path="/a")
        self.gravar(numero="B", mes=8, resultado="erro")
        self.gravar(numero="C", mes=8, resultado="aviso")
        pedidos = [R.novo_item(n, "corrente", 2026, 8) for n in "ABCD"]
        # D nunca rodou, B só deu erro; A deu sucesso; C é aviso de um mês antigo (resolvido)
        faltam = self.h.pendentes(pedidos, hoje=date(2026, 10, 9))
        self.assertEqual([i["numero"] for i in faltam], ["B", "D"])
        # aviso no mês corrente pode mudar amanhã: continua pendente
        faltam = self.h.pendentes(pedidos, hoje=date(2026, 8, 20))
        self.assertEqual([i["numero"] for i in faltam], ["B", "C", "D"])

    def test_linha_cortada_e_lixo_sao_ignorados(self):
        self.gravar(numero="A", pdf_path="/a")
        arq = Path(self.tmp.name) / "itens.jsonl"
        with open(arq, "ab") as f:
            f.write(b'\n{"quebrada": \n')
            f.write(b'sem json nenhum\n')
            f.write(b'[1, 2, 3]\n')                       # JSON válido, mas não é um registro
            f.write(b'{"schema":1,"evento":"item","numero":"B","tipo":"corre')  # cortada no fim
        regs = self.h.itens()
        self.assertEqual([r["numero"] for r in regs], ["A"])
        self.assertEqual(self.h.linhas_ruins, 4)
        self.gravar(numero="C")                           # e dá para continuar gravando
        self.assertEqual({r["numero"] for r in self.h.itens()}, {"A", "C"})

    def test_registro_novo_nao_cola_na_linha_cortada(self):
        """Regressão: uma queda deixa a última linha sem quebra de linha; o registro seguinte NÃO pode ser colado nela."""
        self.gravar(numero="A")
        arq = Path(self.tmp.name) / "itens.jsonl"
        with open(arq, "ab") as f:
            f.write(b'{"schema":1,"evento":"item","numero":"B","tipo":"corre')  # sem \n
        self.gravar(numero="C")
        self.gravar(numero="D")
        self.assertEqual([r["numero"] for r in self.h.itens()], ["A", "C", "D"])  # C e D sobreviveram
        self.assertEqual(self.h.linhas_ruins, 1)

    def test_rotacao_nunca_sobrescreve_um_arquivo_rotacionado(self):
        """Regressão: duas rotações no mesmo segundo geravam o mesmo nome e uma apagava a outra."""
        import core.historico as H
        antigo = H.LIMITE_ROTACAO
        H.LIMITE_ROTACAO = 50  # roda a cada registro
        try:
            for m in range(1, 9):
                self.gravar(numero="A", mes=m)
        finally:
            H.LIMITE_ROTACAO = antigo
        self.assertEqual(len(self.h.itens()), 8)
        self.assertEqual(len({p.name for p in Path(self.tmp.name).glob("itens*.jsonl")}), len(list(Path(self.tmp.name).glob("itens*.jsonl"))))

    def test_registros_de_versao_futura_ainda_sao_lidos(self):
        arq = Path(self.tmp.name) / "itens.jsonl"
        arq.write_text(json.dumps({"schema": 99, "evento": "item", "numero": "A", "tipo": "corrente", "chave": "09/2026",
                                   "resultado": "sucesso", "campo_novo": 1}) + "\n", encoding="utf-8")
        self.assertEqual(self.h.itens()[0]["numero"], "A")

    def test_rotacao_junta_os_arquivos(self):
        import core.historico as H
        antigo = H.LIMITE_ROTACAO
        H.LIMITE_ROTACAO = 300
        try:
            for m in range(1, 7):
                self.gravar(numero="A", mes=m, resultado="sucesso", pdf_path="/a/%d.pdf" % m)
        finally:
            H.LIMITE_ROTACAO = antigo
        arquivos = sorted(p.name for p in Path(self.tmp.name).glob("itens*.jsonl"))
        self.assertGreater(len(arquivos), 1)                       # rodou a rotação
        self.assertEqual(len(self.h.itens()), 6)                   # e nada se perdeu
        self.assertEqual([r["chave"] for r in self.h.itens()], [f"{m:02d}/2026" for m in range(1, 7)])  # em ordem

    def test_gravacao_concorrente_nao_corrompe(self):
        def gravar_muitos(n):
            for i in range(40):
                self.h.registrar_item("r", item(numero=f"T{n}", mes=(i % 12) + 1, resultado="sucesso"), {})
        ts = [threading.Thread(target=gravar_muitos, args=(n,)) for n in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(self.h.itens()), 200)
        self.assertEqual(self.h.linhas_ruins, 0)

    def test_execucao_inicio_e_fim(self):
        e = R.nova_execucao("r1", {"pasta": "/x", "contas": ["A"], "tipos": ["corrente"], "meses": ["09/2026"]},
                            [item(resultado="sucesso")])
        self.h.registrar_execucao("inicio", e)
        e["status"] = "finished"
        self.h.registrar_execucao("fim", e)
        self.assertEqual([x["evento"] for x in self.h.execucoes()], ["inicio", "fim"])
        self.assertEqual(self.h.resumo()["execucoes_concluidas"], 1)


class TestRunnerAlimentaOHistorico(unittest.TestCase):
    def rodar(self, respostas, tipos=("corrente",), meses=((2026, 8), (2026, 9))):
        itens = [R.novo_item(i["numero"], i["tipo"], i["ano"], i["mes"]) for i in pedido.montar_itens(["A"], list(tipos), list(meses))]
        e = R.nova_execucao("t", {}, itens)
        vistos = []

        def acessar(it, conta, primeiro, ultimo):
            r = respostas.get(it["chave"], {"empresa": "E", "pdf_path": __file__})
            return dict(r)

        Runner(e, [{"numero": "A", "empresa": ""}], acessar, lambda: True, threading.Event(),
               ao_concluir=lambda it: vistos.append(dict(it))).executar()
        return vistos

    def test_dados_completos_do_item(self):
        v = self.rodar({"09/2026": {"empresa": "E", "pdf_path": __file__, "_substituido": True}})
        ok = [i for i in v if i["chave"] == "09/2026"][0]
        self.assertEqual(ok["resultado"], "substituido")
        self.assertTrue(ok["substituido"])
        self.assertGreater(ok["tamanho_bytes"], 0)
        self.assertEqual(ok["codigo"], "")
        self.assertIsNotNone(ok["duracao_s"])
        self.assertTrue(ok["inicio"] and ok["fim"])

    def test_erro_vira_codigo_e_so_um_registro_por_item(self):
        v = self.rodar({"08/2026": {"erro": "❌ Timeout no fluxo 'corrente'"}})
        erros = [i for i in v if i["chave"] == "08/2026"]
        self.assertEqual(len(erros), 1)  # as 2 tentativas viram UM registro final, não dois
        self.assertEqual((erros[0]["resultado"], erros[0]["codigo"], erros[0]["tentativas"]), ("erro", "tempo_esgotado", 2))

    def test_desistencia_tambem_e_registrada(self):
        itens_meses = ((2026, 5), (2026, 6), (2026, 7), (2026, 8), (2026, 9))
        resp = {f"{m:02d}/2026": {"erro": "❌ Timeout"} for m in (5, 6)}
        v = self.rodar(resp, meses=itens_meses)
        self.assertEqual(len(v), 5)
        # 05 e 06 falham 2x cada; a 4ª recuperação estoura o limite e os 3 meses restantes (07, 08, 09) viram desistência
        self.assertEqual([i["codigo"] for i in v if "desistência" in i["mensagem"]], ["limite_recuperacao"] * 3)

    def test_falha_do_historico_nao_derruba_a_execucao(self):
        itens = [R.novo_item("A", "corrente", 2026, 9)]
        e = R.nova_execucao("t", {}, itens)

        def quebra(it):
            raise OSError("disco cheio")

        Runner(e, [{"numero": "A", "empresa": ""}], lambda *a: {"pdf_path": __file__}, lambda: True, threading.Event(),
               ao_concluir=quebra).executar()
        self.assertEqual(e["status"], "finished")
        self.assertEqual(e["itens"][0]["resultado"], "sucesso")


if __name__ == "__main__":
    unittest.main()
