"""Backend real: Playwright + código do robô (vendor/sicoobbot).

Regras de threading: o Playwright (API síncrona) só pode ser usado pela thread que o criou. Por isso existe UMA
thread dedicada (`PW`) que é dona do navegador; as demais operações enviam tarefas para ela.
"""
from __future__ import annotations

import builtins
import calendar
import io
import os
import queue
import re
import sys
import threading
from concurrent.futures import Future, TimeoutError as FutTimeout
from contextlib import redirect_stdout

from core import logs, paths, perfil
from core import resultado as R
from core.runner import Runner


class Falha(Exception):
    """Erro esperado, com mensagem pronta para o usuário."""


class _Captura(io.TextIOBase):
    """Recebe tudo que o código do robô imprime: vai para o log e, durante um item, para um buffer."""

    def __init__(self, destino: list[str]):
        self.destino = destino

    def write(self, s):
        if s:
            self.destino.append(s)
            for linha in str(s).splitlines():
                if linha.strip():
                    logs.log("robô: " + linha.strip())
        return len(s or "")

    def flush(self):
        pass


class _Parar(BaseException):
    """Sinal para abortar a espera de login do robô. É BaseException de propósito: o `esperar_login` do robô
    engole qualquer `Exception` e continuaria esperando um navegador que já morreu."""


class _PaginaInterrompivel:
    """Envolve a página só durante a espera de login: se o navegador morreu, aborta em vez de esperar 500 s."""

    def __init__(self, page, deve_parar):
        self._page, self._deve_parar = page, deve_parar

    def locator(self, *a, **k):
        if self._deve_parar():
            raise _Parar()
        return self._page.locator(*a, **k)

    def __getattr__(self, nome):
        return getattr(self._page, nome)


class PW:
    """Thread dona do Playwright e do navegador."""

    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.page = None  # preenchida depois de abrir o navegador (para bombear eventos quando ocioso)
        self.erro_inicio: str | None = None
        self.pronto = threading.Event()
        self.t = threading.Thread(target=self._loop, name="playwright", daemon=True)
        self.t.start()
        self.pronto.wait(30)

    def _loop(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:  # playwright não instalado neste ambiente
            self.erro_inicio = f"Playwright indisponível: {e}"
            self.pronto.set()
            return
        with sync_playwright() as p:
            self.p = p
            self.pronto.set()
            while True:
                try:
                    fn, fut = self.q.get(timeout=1.0)
                except queue.Empty:
                    # ocioso: deixa o Playwright processar eventos (crash/close do navegador)
                    try:
                        if self.page is not None:
                            self.page.wait_for_timeout(50)
                    except Exception:
                        pass
                    continue
                if fn is None:
                    break
                try:
                    fut.set_result(fn(p))
                except BaseException as e:  # noqa: BLE001 - repassa qualquer erro a quem pediu
                    fut.set_exception(e)

    def submit(self, fn) -> Future:
        fut: Future = Future()
        self.q.put((fn, fut))
        return fut

    def run(self, fn, timeout: float | None = None):
        return self.submit(fn).result(timeout)


class BackendReal:
    def __init__(self, estado, sicoob_mod=None):
        self.st = estado
        self.pw = PW()
        self.ctx = None
        self.page = None
        self._sicoob = sicoob_mod
        self._substituidos: list[str] = []

    # ---------------------------------------------------------- módulos do robô
    @property
    def sicoob(self):
        if self._sicoob is None:
            import sicoob_actions  # vendor/sicoobbot no sys.path (feito pelo worker)
            self._sicoob = sicoob_actions
            self._instalar_espiao_de_arquivos()
        return self._sicoob

    def _instalar_espiao_de_arquivos(self):
        """Faz `open()` dentro do módulo do robô avisar quando vai SOBRESCREVER um arquivo existente."""
        substituidos = self._substituidos

        def open_espiao(file, mode="r", *a, **k):
            try:
                if "w" in mode and os.path.exists(file):
                    substituidos.append(os.fspath(file))
            except Exception:
                pass
            return builtins.open(file, mode, *a, **k)

        self._sicoob.open = open_espiao  # só vale para chamadas feitas dentro do módulo do robô

    # ---------------------------------------------------------- navegador
    def versao_chromium(self) -> str | None:
        return perfil.versao_chromium_do_playwright()

    def diagnostico(self) -> dict:
        return {"modo": "real", "playwright": self.pw.erro_inicio or "ok", "chromium": self.versao_chromium()}

    def vivo_rapido(self) -> bool:
        """Seguro para qualquer thread: usa só o estado atualizado pelos eventos do navegador."""
        return self.page is not None and self.st.navegador == "aberto"

    def nav_vivo(self) -> bool:
        """SÓ na thread do Playwright: confirma de verdade que o navegador responde (os flags podem estar defasados)."""
        if self.page is None:
            return False
        try:
            return bool(self.page.evaluate("1"))
        except Exception:
            return False

    def abrir_navegador(self) -> None:
        if self.pw.erro_inicio:
            raise Falha(self.pw.erro_inicio + ". Rode /lid:preparar.")
        chk = perfil.checar_perfil(self.versao_chromium())
        if not chk["ok"]:
            logs.evento("perfil_bloqueado", codigo=chk["codigo"], versao_perfil=chk.get("versao_perfil"))
            raise Falha(chk["motivo"])

        def abrir(p):
            from browser_manager import iniciar_navegador
            with redirect_stdout(_Captura([])):
                ctx, page = iniciar_navegador(p, headless=False)
            self._registrar_eventos(ctx, page)
            page.goto(paths.URL_SICOOB, timeout=120000, wait_until="domcontentloaded")
            self.ctx, self.page = ctx, page
            self.pw.page = page

        try:
            self.pw.run(abrir, timeout=180)
        except FutTimeout:
            raise Falha("O navegador anterior ainda está sendo encerrado. Aguarde alguns segundos e rode /lid:login de novo.")
        logs.evento("navegador_aberto", chromium=self.versao_chromium())

    def _registrar_eventos(self, ctx, page):
        """Registra COMO o navegador morreu (crash x close x disconnected): hoje esse dado se perde no EXE."""
        st = self.st

        def marcar(nome, estado):
            def _(*_a):
                logs.evento(nome, item_atual=(st.execucao or {}).get("item_atual"))
                st.navegador = estado
            return _

        try:
            page.on("crash", marcar("pagina_travou", "travou"))
            page.on("close", marcar("pagina_fechada", "fechado"))
            ctx.on("close", marcar("contexto_fechado", "fechado"))
            if ctx.browser:
                ctx.browser.on("disconnected", marcar("navegador_desconectado", "fechado"))
        except Exception as e:
            logs.log(f"não consegui registrar eventos do navegador: {e}", "WARN")

    def esperar_login_e_listar(self) -> None:
        """Ocupa a thread do Playwright até o login terminar; depois carrega a lista de contas."""
        st = self.st

        def tarefa(p):
            try:
                pagina = _PaginaInterrompivel(self.page, lambda: st.navegador != "aberto")
                with redirect_stdout(_Captura([])):
                    ok = self.sicoob.esperar_login(pagina)
                    if not ok:
                        st.login, st.mensagem = "erro", "Tempo esgotado sem detectar o login. Rode /lid:login de novo."
                        logs.evento("login_timeout")
                        return
                    st.login = "carregando_contas"
                    contas = self.sicoob.listar_contas(self.page)
                st.contas = [c["numero"] for c in contas]
                st.login, st.mensagem = "ok", f"{len(st.contas)} contas carregadas."
                logs.evento("login_ok", contas=len(st.contas))
            except _Parar:
                st.login, st.mensagem = "erro", "O navegador foi fechado antes de terminar o login. Rode /lid:login de novo (novo QR)."
                logs.evento("login_abortado", motivo="navegador fechado")
            except Exception as e:
                st.login, st.mensagem = "erro", f"Falha ao esperar o login: {e}"
                logs.evento("login_erro", erro=str(e)[:200])

        self.pw.submit(tarefa)

    # ---------------------------------------------------------- contas
    def listar_contas(self) -> list[str]:
        def f(p):
            with redirect_stdout(_Captura([])):
                return [c["numero"] for c in self.sicoob.listar_contas(self.page)]
        return self.pw.run(f, timeout=120)

    def buscar_contas(self, texto: str) -> list[dict]:
        """Usa o campo de busca do portal. Devolve número, nome e tipo (PJ/PF); nunca CNPJ/CPF."""
        def f(p):
            page = self.page
            if page.locator("h3:has-text('Lista de contas')").count() == 0:
                page.locator(self.sicoob.SEL_TROCAR_CONTA).first.click(timeout=15000)
                page.wait_for_selector("h3:has-text('Lista de contas')", timeout=40000)
            campo = page.locator("input.sicoob-input-text").first
            campo.fill(texto)
            campo.press("Enter")
            page.wait_for_timeout(2000)
            linhas = page.locator("div.seletor-conta")
            achados = []
            for i in range(min(linhas.count(), 30)):
                bruto = linhas.nth(i).inner_text()
                m_conta = re.search(r"Conta\s+([\d.]+-\d)", bruto)
                m_nome = re.search(r"Nome:\s*(.+)", bruto)
                m_tipo = re.search(r"\b(PJ|PF)\b", bruto)
                if m_conta:
                    achados.append({"numero": m_conta.group(1),
                                    "nome": (m_nome.group(1).strip() if m_nome else ""),
                                    "tipo": (m_tipo.group(1) if m_tipo else "")})
            campo.fill("")
            campo.press("Enter")
            return achados
        return self.pw.run(f, timeout=120)

    # ---------------------------------------------------------- execução
    def _acessar(self, pasta: str):
        sicoob = self.sicoob

        def acessar(item: dict, conta: dict, primeiro: bool, ultimo: bool) -> dict:
            mes, ano = item["mes"], item["ano"]
            ultimo_dia = calendar.monthrange(ano, mes)[1]
            saida: list[str] = []
            self._substituidos.clear()
            with redirect_stdout(_Captura(saida)):
                res = sicoob.acessar_extrato(
                    page=self.page,
                    conta=conta,
                    mes_selecionado=mes,
                    ano_selecionado=ano,
                    dia_inicio=1,
                    dia_fim=31,
                    base_drive=pasta,
                    tipo_extrato=item["tipo"],
                    periodo_comprovantes="Mês atual",
                    comprovante_modo="intervalo" if item["tipo"] == "comprovantes" else "periodo",
                    comprovante_data_inicial=f"01/{mes:02d}/{ano}",
                    comprovante_data_final=f"{ultimo_dia:02d}/{mes:02d}/{ano}",
                    cartao_mes_referencia=f"{mes:02d}/{ano}",
                    cartao_formato="PDF",
                    cartao_baixar_ambos=False,
                    primeiro_periodo=primeiro,
                    ultimo_periodo=ultimo,
                )
            res = dict(res or {})
            texto = "".join(saida)
            res["_substituido"] = bool(res.get("pdf_path")) and os.fspath(res["pdf_path"]) in self._substituidos
            res["_sem_movimento"] = "sem movimentação no período" in texto
            return res

        return acessar

    def rodar_execucao(self, execucao: dict, contas: list[dict], pasta: str, cancelado, persistir, ao_terminar) -> None:
        def job(p):
            try:
                logs.evento("execucao_inicio", run_id=execucao["run_id"], itens=len(execucao["itens"]))
                Runner(execucao, contas, self._acessar(pasta), self.nav_vivo, cancelado, ao_atualizar=persistir).executar()
                logs.evento("execucao_fim", run_id=execucao["run_id"], status=execucao["status"])
            except Exception as e:  # nunca deixa a execução "rodando" para sempre
                execucao["status"], execucao["mensagem"] = "interrompida", f"falha inesperada: {e}"
                execucao["fim"] = R.agora()
                logs.evento("execucao_falha", erro=str(e)[:300])
            finally:
                try:
                    persistir(execucao)
                finally:
                    ao_terminar()

        self.pw.submit(job)
