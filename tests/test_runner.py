"""Testes do runner com um `acessar` falso: verificam as regras do robô sem portal e sem navegador."""
import sys
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core import pedido, resultado as R  # noqa: E402
from core.runner import Runner, classificar  # noqa: E402


def montar(contas, tipos, meses):
    itens = [R.novo_item(i["numero"], i["tipo"], i["ano"], i["mes"]) for i in pedido.montar_itens(contas, tipos, meses)]
    return R.nova_execucao("teste", {}, itens)


class Fake:
    """Registra as chamadas e responde conforme um roteiro: {(numero, tipo, chave): [resp1, resp2, ...]}."""

    def __init__(self, roteiro=None, vivo=lambda: True):
        self.roteiro = roteiro or {}
        self.chamadas = []

    def __call__(self, item, conta, primeiro, ultimo):
        chave = (item["numero"], item["tipo"], item["chave"])
        self.chamadas.append((*chave, primeiro, ultimo))
        fila = self.roteiro.get(chave)
        if fila:
            r = fila.pop(0) if len(fila) > 1 else fila[0]
            if isinstance(r, Exception):
                raise r
            return dict(r)
        return {"empresa": f"Empresa {item['numero']}", "pdf_path": f"/x/{item['numero']}/{item['tipo']}/{item['chave'][:2]}.pdf"}


def rodar(execucao, fake, vivo=lambda: True, cancelado=None, **kw):
    contas = [{"numero": n, "empresa": ""} for n in dict.fromkeys(i["numero"] for i in execucao["itens"])]
    return Runner(execucao, contas, fake, vivo, cancelado or threading.Event(), **kw).executar()


OK = {"empresa": "E", "pdf_path": "/x.pdf"}
ERR = {"empresa": "E", "erro": "❌ Timeout no fluxo"}


class TestOrdemEFlags(unittest.TestCase):
    def test_tudo_certo(self):
        e = montar(["A", "B"], ["corrente", "capital"], [(2026, 8), (2026, 9)])
        f = Fake()
        r = rodar(e, f)
        self.assertEqual(r["status"], "finished")
        self.assertTrue(all(i["resultado"] == "sucesso" for i in r["itens"]))
        # primeiro só no 1º item de cada conta; último só no último item de cada conta
        por_conta = {}
        for n, t, c, primeiro, ultimo in f.chamadas:
            por_conta.setdefault(n, []).append((t, c, primeiro, ultimo))
        for n, ch in por_conta.items():
            self.assertEqual([x[2] for x in ch], [True, False, False, False], n)
            self.assertEqual([x[3] for x in ch], [False, False, False, True], n)
            self.assertEqual([(x[0], x[1]) for x in ch], [("corrente", "08/2026"), ("corrente", "09/2026"),
                                                          ("capital", "08/2026"), ("capital", "09/2026")])
        # a conta B só começa depois de terminar a A
        self.assertEqual([c[0] for c in f.chamadas], ["A"] * 4 + ["B"] * 4)
        self.assertEqual(r["fim"] != "", True)

    def test_empresa_propagada(self):
        e = montar(["A"], ["corrente"], [(2026, 8), (2026, 9)])
        r = rodar(e, Fake())
        self.assertEqual({i["empresa"] for i in r["itens"]}, {"Empresa A"})


class TestErros(unittest.TestCase):
    def test_erro_e_sucesso_na_repeticao(self):
        e = montar(["A"], ["corrente"], [(2026, 8), (2026, 9)])
        f = Fake({("A", "corrente", "08/2026"): [ERR, OK]})
        r = rodar(e, f)
        self.assertEqual([i["resultado"] for i in r["itens"]], ["sucesso", "sucesso"])
        self.assertEqual(r["itens"][0]["tentativas"], 2)
        # depois do erro, a tentativa seguinte reentra na conta (primeiro=True)
        self.assertEqual([c[3] for c in f.chamadas], [True, True, False])

    def test_duas_falhas_viram_erro_definitivo_e_segue(self):
        e = montar(["A"], ["corrente"], [(2026, 8), (2026, 9)])
        f = Fake({("A", "corrente", "08/2026"): [ERR]})
        r = rodar(e, f)
        self.assertEqual([i["resultado"] for i in r["itens"]], ["erro", "sucesso"])
        self.assertEqual(r["itens"][0]["tentativas"], 2)
        self.assertEqual(r["status"], "finished")
        # o item seguinte também reentra na conta, porque veio de erro
        self.assertEqual([c[3] for c in f.chamadas], [True, True, True])

    def test_limite_de_recuperacao_desiste_do_resto_da_conta(self):
        e = montar(["A", "B"], ["corrente"], [(2026, 6), (2026, 7), (2026, 8), (2026, 9)])
        f = Fake({("A", "corrente", "06/2026"): [ERR], ("A", "corrente", "07/2026"): [ERR]})
        r = rodar(e, f)
        a = [i for i in r["itens"] if i["numero"] == "A"]
        self.assertEqual([i["resultado"] for i in a], ["erro", "erro", "erro", "erro"])
        self.assertIn("limite de recuperações", a[2]["mensagem"])
        # a conta B não é afetada
        self.assertTrue(all(i["resultado"] == "sucesso" for i in r["itens"] if i["numero"] == "B"))
        # 06: 2 tentativas (rec 1,2), 07: tentativa 1 (rec 3) e tentativa 2 (rec 4 > 3 -> desiste)
        self.assertEqual(len([c for c in f.chamadas if c[0] == "A"]), 4)

    def test_excecao_inesperada_vira_erro(self):
        e = montar(["A"], ["corrente"], [(2026, 8)])
        r = rodar(e, Fake({("A", "corrente", "08/2026"): [RuntimeError("boom")]}))
        self.assertEqual(r["itens"][0]["resultado"], "erro")
        self.assertIn("boom", r["itens"][0]["mensagem"])


class TestAvisos(unittest.TestCase):
    def test_sem_cartao_nao_repete_nem_conta_como_erro(self):
        e = montar(["A"], ["cartao", "corrente"], [(2026, 7), (2026, 8), (2026, 9)])
        f = Fake({("A", "cartao", "07/2026"): [{"empresa": "E", "erro": "⚠️ Conta A sem cartões de crédito vinculados."}]})
        r = rodar(e, f)
        cart = [i for i in r["itens"] if i["tipo"] == "cartao"]
        self.assertEqual([i["resultado"] for i in cart], ["aviso", "aviso", "aviso"])
        self.assertEqual([c for c in f.chamadas if c[1] == "cartao"].__len__(), 1)  # só chamou uma vez
        # o aviso não força reentrada: o 1º item de corrente já vem com primeiro=False
        corr = [c for c in f.chamadas if c[1] == "corrente"]
        self.assertFalse(corr[0][3])
        self.assertTrue(all(i["resultado"] == "sucesso" for i in r["itens"] if i["tipo"] == "corrente"))

    def test_sem_comprovantes_e_aviso(self):
        e = montar(["A"], ["comprovantes"], [(2026, 12)])
        r = rodar(e, Fake({("A", "comprovantes", "12/2026"): [{"erro": "⚠️ Não existem comprovantes para o período Dezembro/2026."}]}))
        self.assertEqual(r["itens"][0]["resultado"], "aviso")
        self.assertEqual(len([1 for _ in r["itens"]]), 1)

    def test_classificar(self):
        self.assertEqual(classificar({"pdf_path": "/a.pdf"})[0], "sucesso")
        self.assertEqual(classificar({"pdf_path": "/a.pdf", "_substituido": True})[0], "substituido")
        self.assertEqual(classificar({"pdf_path": "/a.pdf", "_sem_movimento": True})[0], "sem_movimento")
        self.assertEqual(classificar({"erro": "⚠️ aviso"})[0], "aviso")
        self.assertEqual(classificar({"erro": "❌ falhou"}), ("erro", "falhou"))
        self.assertEqual(classificar({})[0], "erro")  # sem erro e sem arquivo não é sucesso


class TestInterrupcoes(unittest.TestCase):
    def test_navegador_fechado_interrompe_sem_erro_definitivo(self):
        e = montar(["A", "B"], ["corrente"], [(2026, 8), (2026, 9)])
        chamadas = {"n": 0}

        def vivo():
            return chamadas["n"] < 1  # morre depois do primeiro item

        class F(Fake):
            def __call__(s, *a, **k):
                chamadas["n"] += 1
                return super().__call__(*a, **k)

        r = rodar(e, F(), vivo=vivo)
        self.assertEqual(r["status"], "interrompida")
        res = [i["resultado"] for i in r["itens"]]
        self.assertEqual(res[0], "sucesso")
        self.assertEqual(res[1:], ["nao_executado"] * 3)
        self.assertNotIn("erro", res)

    def test_excecao_de_navegador_fechado(self):
        e = montar(["A"], ["corrente"], [(2026, 8), (2026, 9)])
        f = Fake({("A", "corrente", "08/2026"): [Exception("Page.screenshot: Target page, context or browser has been closed")]})
        r = rodar(e, f)
        self.assertEqual(r["status"], "interrompida")
        self.assertEqual([i["resultado"] for i in r["itens"]], ["nao_executado", "nao_executado"])

    def test_cancelar(self):
        e = montar(["A"], ["corrente"], [(2026, 6), (2026, 7), (2026, 8)])
        ev = threading.Event()

        class F(Fake):
            def __call__(s, item, *a):
                r = super().__call__(item, *a)
                if item["chave"] == "07/2026":
                    ev.set()
                return r

        r = rodar(e, F(), cancelado=ev)
        self.assertEqual(r["status"], "cancelled")
        self.assertEqual([i["resultado"] for i in r["itens"]], ["sucesso", "sucesso", "nao_executado"])

    def test_continuar_so_o_que_falta(self):
        e = montar(["A"], ["corrente"], [(2026, 6), (2026, 7), (2026, 8)])
        e["itens"][0]["resultado"] = "sucesso"
        f = Fake()
        r = rodar(e, f)
        self.assertEqual([c[2] for c in f.chamadas], ["07/2026", "08/2026"])  # não refez o 06
        self.assertTrue(f.chamadas[0][3])  # 1ª chamada desta rodada entra pela lista

    def test_atualizacoes_para_status(self):
        e = montar(["A"], ["corrente"], [(2026, 8)])
        vistos = []
        rodar(e, Fake(), ao_atualizar=lambda ex: vistos.append((ex["item_atual"] is not None, ex["status"])))
        self.assertIn((True, "running"), vistos)       # durante o item há item_atual
        self.assertEqual(vistos[-1], (False, "finished"))


if __name__ == "__main__":
    unittest.main()
