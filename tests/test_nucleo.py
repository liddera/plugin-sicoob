"""Testes do núcleo (pedido, controle, perfil, resultado). Não precisam de portal nem de navegador."""
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core import controle, pedido, perfil, resultado  # noqa: E402


class TestContas(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(pedido.normalizar_conta("470414"), "47.041-4")
        self.assertEqual(pedido.normalizar_conta("47.041-4"), "47.041-4")
        self.assertEqual(pedido.normalizar_conta("1093177"), "109.317-7")
        self.assertEqual(pedido.normalizar_conta("13959-9"), "13.959-9")
        self.assertIsNone(pedido.normalizar_conta("ab"))

    def test_resolver(self):
        conhecidas = ["13.959-9", "47.041-4", "109.317-7"]
        r = pedido.resolver_contas(["47041-4", "1093177", "99.999-9", "13.959-8"], conhecidas)
        self.assertEqual(r["aceitas"], ["47.041-4", "109.317-7"])
        faltando = {f["entrada"]: f["sugestoes"] for f in r["nao_encontradas"]}
        self.assertIn("99.999-9", faltando)
        self.assertEqual(faltando["13.959-8"], ["13.959-9"])  # sugestão parecida

    def test_sem_repeticao(self):
        r = pedido.resolver_contas(["47.041-4", "470414"], ["47.041-4"])
        self.assertEqual(r["aceitas"], ["47.041-4"])


class TestTipos(unittest.TestCase):
    def test_aliases(self):
        for txt, esperado in [("extrato", "corrente"), ("Conta Corrente", "corrente"), ("capital", "capital"),
                              ("comprovantes", "comprovantes"), ("fatura", "cartao"), ("Cartão", "cartao"),
                              ("extrato da conta capital", "capital")]:
            self.assertEqual(pedido.normalizar_tipo(txt), esperado, txt)
        self.assertIsNone(pedido.normalizar_tipo("pix"))

    def test_lista(self):
        tipos, ruins = pedido.normalizar_tipos(["capital", "corrente", "capital", "pix"])
        self.assertEqual(tipos, ["capital", "corrente"])
        self.assertEqual(ruins, ["pix"])
        self.assertEqual(pedido.normalizar_tipos(["todos"])[0], list(pedido.TIPOS))


class TestMeses(unittest.TestCase):
    HOJE = date(2026, 10, 9)

    def test_intervalo_e_lista(self):
        m, pb = pedido.expandir_meses(["06/2026 a 09/2026"], self.HOJE)
        self.assertEqual(m, [(2026, 6), (2026, 7), (2026, 8), (2026, 9)])
        self.assertEqual(pb, [])
        m, _ = pedido.expandir_meses(["06/2026", "08/2026", "09/2026", "06/2026"], self.HOJE)
        self.assertEqual(m, [(2026, 6), (2026, 8), (2026, 9)])

    def test_por_extenso(self):
        m, pb = pedido.expandir_meses(["junho a setembro de 2026"], self.HOJE)
        self.assertEqual(m, [(2026, 6), (2026, 7), (2026, 8), (2026, 9)])
        self.assertEqual(pb, [])
        m, pb = pedido.expandir_meses(["06 a 09/2026"], self.HOJE)
        self.assertEqual(m, [(2026, 6), (2026, 7), (2026, 8), (2026, 9)])
        _, pb = pedido.expandir_meses(["foo a bar de 2026"], self.HOJE)
        self.assertTrue(pb)  # lixo continua sendo recusado, não adivinhado
        m, pb = pedido.expandir_meses(["junho/2026 a setembro/2026"], self.HOJE)
        self.assertEqual(m, [(2026, 6), (2026, 7), (2026, 8), (2026, 9)])

    def test_virada_de_ano(self):
        m, _ = pedido.expandir_meses(["11/2025 a 02/2026"], self.HOJE)
        self.assertEqual(m, [(2025, 11), (2025, 12), (2026, 1), (2026, 2)])

    def test_futuro_e_invalidos(self):
        m, pb = pedido.expandir_meses(["10/2026", "11/2026"], self.HOJE)
        self.assertEqual(m, [(2026, 10)])
        self.assertTrue(any("futuro" in p for p in pb))
        _, pb = pedido.expandir_meses(["13/2026"], self.HOJE)
        self.assertTrue(pb)
        _, pb = pedido.expandir_meses(["09/2026 a 06/2026"], self.HOJE)
        self.assertTrue(any("invertido" in p for p in pb))
        m, pb = pedido.expandir_meses(["12/2019"], self.HOJE)
        self.assertEqual(m, [])
        self.assertTrue(pb)


class TestItens(unittest.TestCase):
    def test_ordem_do_robo(self):
        itens = pedido.montar_itens(["A", "B"], ["corrente", "capital"], [(2026, 8), (2026, 9)])
        seq = [(i["numero"], i["tipo"], i["chave"]) for i in itens]
        self.assertEqual(seq[:4], [("A", "corrente", "08/2026"), ("A", "corrente", "09/2026"),
                                   ("A", "capital", "08/2026"), ("A", "capital", "09/2026")])
        self.assertEqual(len(itens), 8)
        self.assertEqual(pedido.resumo_pedido("x", ["A", "B"], ["corrente", "capital"], [(2026, 8), (2026, 9)])["total_itens"], 8)


class TestPasta(unittest.TestCase):
    def test_pasta_ok(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("Zeta Ltda", "Alfa Ltda", "Beta Ltda", "Gama Ltda"):
                (Path(d) / n).mkdir()
            r = pedido.validar_pasta(d)
            self.assertTrue(r["ok"] and r["gravavel"])
            self.assertEqual(r["empresas_total"], 4)
            self.assertEqual(r["exemplos"], ["Alfa Ltda", "Beta Ltda", "Gama Ltda"])
            self.assertEqual(os.listdir(d).count(".lid_teste"), 0)  # não deixou lixo
            self.assertFalse([n for n in os.listdir(d) if n.startswith(".lid_teste")])

    def test_pasta_vazia_avisa(self):
        with tempfile.TemporaryDirectory() as d:
            r = pedido.validar_pasta(d)
            self.assertTrue(r["ok"])
            self.assertTrue(r["avisos"])

    def test_inexistente(self):
        r = pedido.validar_pasta(r"H:\nao\existe")
        self.assertFalse(r["ok"])
        self.assertTrue(r["erros"])
        self.assertFalse(pedido.validar_pasta("")["ok"])


class TestControle(unittest.TestCase):
    def setUp(self):
        self.ctl = {"versao": 1, "atualizado_em": "", "ciclos": {
            "2026-10-09::corrente": {"contas": {
                "A": {"status": "sucesso", "periodos": {"09/2026": {"status": "sucesso"}}},
                "B": {"status": "erro", "periodos": {"09/2026": {"status": "erro", "erro_resumo": "falhou"}}},
                "C": {"status": "parcial", "periodos": {"08/2026": {"status": "sucesso"}, "09/2026": {"status": "erro"}}},
                "D": {"status": "pendente"},
            }, "execucoes": {}},
            "03/2026": {"contas": {"A": {"status": "erro"}}},  # chave antiga: ignorada
        }}

    def test_classificar(self):
        g = controle.classificar_contas(self.ctl, ["A", "B", "C", "D", "E"], "corrente", "2026-10-09")
        self.assertEqual(g["sucesso"], ["A"])
        self.assertEqual(g["com_erro"], ["B", "C"])
        self.assertEqual(g["pendentes"], ["D", "E"])  # E não consta no ciclo => não iniciada

    def test_itens_com_erro(self):
        itens = controle.itens_com_erro(self.ctl, ["corrente", "capital"], "2026-10-09")
        self.assertEqual({(i["numero"], i["chave"]) for i in itens}, {("B", "09/2026"), ("C", "09/2026")})

    def test_carregar_tolerante(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            self.assertEqual(controle.carregar(p)["ciclos"], {})  # ausente
            p.write_text("{quebrado", encoding="utf-8")
            self.assertEqual(controle.carregar(p)["ciclos"], {})  # inválido
            p.write_text(json.dumps(self.ctl), encoding="utf-8")
            self.assertIn("2026-10-09::corrente", controle.carregar(p)["ciclos"])

    def test_nunca_escreve(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps(self.ctl), encoding="utf-8")
            antes = p.read_bytes()
            controle.carregar(p)
            controle.classificar_contas(controle.carregar(p), ["A"], "corrente", "2026-10-09")
            self.assertEqual(p.read_bytes(), antes)


class TestPerfil(unittest.TestCase):
    def test_comparar(self):
        self.assertEqual(perfil.comparar_versoes("153.0.8010.12", "145.0.7632.6"), 1)
        self.assertEqual(perfil.comparar_versoes("145.0.7632.6", "153.0.8010.12"), -1)
        self.assertEqual(perfil.comparar_versoes("153.0.8010.12", "153.0.8010.12"), 0)
        self.assertEqual(perfil.comparar_versoes("153.0.8010.2", "153.0.8010.12"), -1)  # numérico, não texto

    def test_checar(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(perfil.checar_perfil("153.0.8010.12", d)["ok"])  # perfil novo
            (Path(d) / "Last Version").write_text("145.0.7632.6", encoding="utf-8")
            self.assertTrue(perfil.checar_perfil("153.0.8010.12", d)["ok"])  # perfil mais velho: ok
            (Path(d) / "Last Version").write_text("153.0.8010.12", encoding="utf-8")
            self.assertTrue(perfil.checar_perfil("153.0.8010.12", d)["ok"])  # igual: ok
            (Path(d) / "Last Version").write_text("154.0.1.1", encoding="utf-8")
            r = perfil.checar_perfil("153.0.8010.12", d)
            self.assertFalse(r["ok"])
            self.assertEqual(r["codigo"], "perfil_mais_novo")

    @unittest.skipIf(os.name == "nt", "usa SingletonLock (Linux/mac)")
    def test_em_uso(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(perfil.perfil_em_uso(d))
            os.symlink(f"host-{os.getpid()}", Path(d) / "SingletonLock")  # processo vivo (este)
            self.assertTrue(perfil.perfil_em_uso(d))
            self.assertEqual(perfil.checar_perfil("153.0.8010.12", d)["codigo"], "perfil_em_uso")
            os.remove(Path(d) / "SingletonLock")
            os.symlink("host-999999999", Path(d) / "SingletonLock")  # processo que não existe
            self.assertFalse(perfil.perfil_em_uso(d))


class TestResultado(unittest.TestCase):
    def test_salvar_e_carregar(self):
        e = resultado.nova_execucao("r1", {"pasta": "x"}, [resultado.novo_item("A", "corrente", 2026, 9)])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "u.json"
            resultado.salvar(e, p)
            self.assertEqual(resultado.carregar(p)["run_id"], "r1")
            self.assertFalse(list(Path(d).glob("*.tmp")))

    def test_refazer(self):
        itens = [resultado.novo_item("A", "corrente", 2026, m) for m in (6, 7, 8, 9)]
        for it, r in zip(itens, (resultado.SUCESSO, resultado.ERRO, resultado.NAO_EXECUTADO, None)):
            it["resultado"] = r
        e = {"itens": itens}
        self.assertEqual([i["chave"] for i in resultado.itens_para_refazer(e, "erro")], ["07/2026"])
        self.assertEqual([i["chave"] for i in resultado.itens_para_refazer(e, "continuar")], ["08/2026", "09/2026"])

    def test_relatorio_sem_dados_bancarios(self):
        e = resultado.nova_execucao("r1", {}, [resultado.novo_item("A", "capital", 2026, 9)])
        e["itens"][0].update(resultado="sem_movimento", pdf_path="C:/x/09.pdf", empresa="Empresa X")
        txt = resultado.relatorio_markdown(e)
        self.assertIn("sem movimento", txt)
        self.assertIn("C:/x/09.pdf", txt)


if __name__ == "__main__":
    unittest.main()
