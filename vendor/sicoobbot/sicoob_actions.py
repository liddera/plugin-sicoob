import time
import re
import unicodedata
import calendar
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from config import TEMPO_MAXIMO_LOGIN
from parse_extrato_sicoob_txt import parse_extrato_sicoob_txt
from build_html_extrato_sicoob import build_html_extrato_sicoob
from build_html_extrato_sicoob_capital import build_html_extrato_sicoob_capital
from build_html_comprovantes_sicoob import build_html_comprovantes_sicoob
from build_html_extrato_cartao import build_html_extrato_cartao
from decode_extrato_texto import decode_extrato_texto


# Modo de seleção do calendário:
#   "single" = se mês completo clica 1 vez, se parcial clica 2
#   "range"  = sempre clica 2 vezes (inicio + fim)
#   "none"   = nunca clica nos dias (deixa default do portal)
CALENDAR_MODE = "single"

# Layout novo do SicoobNet (2026-10): "Trocar conta" virou o ícone ⇄ do cabeçalho.
# O seletor antigo fica como fallback.
SEL_TROCAR_CONTA = "a:has-text('Trocar conta'), div.icone-acoes:has(span.arrow-lr)"

# Comprovantes: o antigo modal virou drawer (div.drawer-container.aberto); o conteúdo .comprovante é o mesmo.
SEL_MODAL_COMPROVANTE = "#modalDetalhesComprovante_modal, div.drawer-container.aberto"
SEL_COMPROVANTE_ITEM = "#modalDetalhesComprovante_modal .comprovante, div.drawer-container.aberto .comprovante"
SEL_MODAL_COMPROVANTE_CORPO = "#modalDetalhesComprovante_modal .modal-body, div.drawer-container.aberto .card-drawer-body"
SEL_MODAL_COMPROVANTE_FECHAR = (
    "div.drawer-container.aberto i.fechar, "
    "#modalDetalhesComprovante_modal .modal-header button.close, "
    "#modalDetalhesComprovante_modal .modal-header .close"
)


def click_menu_lateral(page, conta_numero, icone_class, content_label, timeout=10000):
    """
    Clica num item do menu lateral do SicoobNet de forma tolerante.
    Tenta em ordem: <i>, <a>, <i> com force=True, dispatch no <a>.
    Silencioso no caminho normal. Loga apenas erros (igual ao resto do código).
    Sem gravar HTML.
    """
    seletor_i = f"i.{icone_class}[title='{content_label}']"
    seletor_a = f"a[data-content-label='{content_label}']"

    # Layout novo: menu horizontal no topo (sicoob-menu-horizontal).
    seletor_topo = f"sicoob-menu-horizontal li.container-icone a:has-text('{content_label}')"

    estrategias = [
        ("topo",        seletor_topo, "normal"),
        ("i",           seletor_i, "normal"),
        ("a_pai",       seletor_a, "normal"),
        ("i_force",     seletor_i, "force"),
        ("a_dispatch",  seletor_a, "dispatch"),
    ]

    # Layout novo: o menu do topo é liga/desliga. Se este item já está aberto, um clique o fecharia.
    try:
        if page.locator(
            f"sicoob-menu-horizontal li.container-icone.active-menu-aberto:has(a:has-text('{content_label}'))"
        ).count() > 0:
            return "topo_ja_aberto"
    except Exception:
        pass

    for nome, seletor, modo in estrategias:
        try:
            page.wait_for_selector(seletor, state="visible", timeout=timeout)
            loc = page.locator(seletor).first
            if modo == "force":
                loc.click(force=True)
            elif modo == "dispatch":
                loc.dispatch_event("click")
            else:
                loc.click()
            return nome
        except Exception as e:
            print(f"⚠️ conta {conta_numero} | '{content_label}' falhou em '{nome}': {e}")
            continue

    raise RuntimeError(
        f"Falha total ao clicar no menu '{content_label}' (conta {conta_numero}). "
        f"Estratégias tentadas: topo, i, a_pai, i_force, a_dispatch."
    )


def _garantir_submenu_topo(page, rotulo, seletor_link, tentativas=2, espera_ms=5000):
    """
    Layout novo: o 1º clique no menu do topo pode se perder se a página ainda estiver
    carregando após trocar de conta. Se o link do submenu não ficar visível, clica de novo.
    Retorna True se o link ficou visível.
    """
    for t in range(tentativas):
        try:
            page.wait_for_selector(seletor_link, state="visible", timeout=espera_ms)
            return True
        except (PlaywrightTimeoutError, PlaywrightError):
            if t < tentativas - 1:
                try:
                    # Menu liga/desliga: só clica se o item não estiver aberto (senão fecharia o submenu).
                    if page.locator(
                        f"sicoob-menu-horizontal li.container-icone.active-menu-aberto:has(a:has-text('{rotulo}'))"
                    ).count() == 0:
                        page.locator(
                            f"sicoob-menu-horizontal li.container-icone a:has-text('{rotulo}')"
                        ).first.click(timeout=3000)
                except Exception:
                    pass
    return False


def esperar_login(page):
    print("🔎 Aguardando confirmação de login no dashboard...")
    inicio = time.time()

    selectors_logado = [
        "#layoutDashboard",
        "#header",
        "#idImagemFundoUsuario",
        "button.userInfo",
        "div:has-text('Olá,')",
    ]

    while time.time() - inicio < TEMPO_MAXIMO_LOGIN:

        for selector in selectors_logado:
            try:
                if page.locator(selector).first.is_visible(timeout=3000):
                    print(f"✅ Detectado elemento logado: {selector}")
                    time.sleep(2)
                    return True
            except (PlaywrightTimeoutError, PlaywrightError):
                continue
            except Exception as e:
                print(f"⚠️ Erro inesperado ao validar selector de login '{selector}': {e}")
                continue

        print("   Ainda aguardando login...")
        time.sleep(4)

    print("❌ Tempo esgotado sem detectar dashboard logado.")
    return False
    
def listar_contas(page):
    """
    Abre a seção de troca de contas e extrai diretamente do <select>
    apenas o número da conta (sem nome/titular) + index + value interno.
    """
    print("📂 Carregando lista de contas via dropdown...")

    # Clique em "Trocar conta" (mantemos robusto)
    trocar_selector = (
        "div.icone-acoes:has(span.arrow-lr), "
        "a.texto-trocar-conta, "
        "span.texto-header:has-text('Trocar conta'), "
        "a:has-text('Trocar conta'), "
        "img[alt*='troca conta'], img[src*='icone_troca_conta']"
    )
    try:
        page.locator(trocar_selector).first.click(timeout=15000)
        print("   → Clique em 'Trocar conta' efetuado.")
        time.sleep(2)  # folga para modal/dropdown aparecer
    except PlaywrightTimeoutError as e:
        print(f"⚠️ Timeout no clique em 'Trocar conta' (pode já estar visível): {e}")
    except PlaywrightError as e:
        print(f"⚠️ Erro Playwright no clique em 'Trocar conta' (pode já estar visível): {e}")
    except Exception as e:
        print(f"⚠️ Erro inesperado no clique em 'Trocar conta' (pode já estar visível): {e}")

    # Selector do dropdown (baseado no seu HTML)
    select_selector = (
        "#contaSelecionadaParaSerPrincipal, "
        "select.form-control, "
        "select[name*='contaSelecionada'], "
        "select:has(option[value='0'])"
    )

    print("   Aguardando dropdown de contas...")
    try:
        page.wait_for_selector(select_selector, state="visible", timeout=40000)
        print("   → Dropdown localizado!")
    except PlaywrightTimeoutError as e:
        print(f"❌ Timeout aguardando dropdown de contas: {e}")
        return []
    except PlaywrightError as e:
        print(f"❌ Erro Playwright ao aguardar dropdown de contas: {e}")
        return []
    except Exception as e:
        print(f"❌ Erro inesperado ao aguardar dropdown de contas: {e}")
        return []

    # Pega o select
    select = page.locator(select_selector).first

    # Todas as options
    options = select.locator("option").all()
    total_options = len(options)
    print(f"🔢 Total de opções encontradas: {total_options}")

    lista_contas = []
    for idx, opt in enumerate(options):
        try:
            value = opt.get_attribute("value") or ""
            numero = opt.inner_text().strip()

            # Ignora inválidas/default
            if not numero or value == "0" or "Nenhuma" in numero or "nenhuma conta" in numero.lower():
                continue

            lista_contas.append({
                "index": len(lista_contas),  # 0, 1, 2... só as válidas
                "value": value,
                "numero": numero
            })

            print(f"📌 Conta {len(lista_contas)}: {numero} (value={value}, index interno={idx})")

        except Exception as e:
            print(f"   Erro na option {idx}: {e}")
            continue

    print(f"✅ Total de contas válidas: {len(lista_contas)}")
    return lista_contas

##def encontrar_pasta_por_conta(base_path: Path, numero_conta: str, ano: str) -> Path | None:
 #   """
  #  Procura uma pasta de empresa que já contenha a conta para o ano atual.
   # Retorna a pasta encontrada ou None se não existir.
   # """
   # for empresa in base_path.iterdir():
    #    if not empresa.is_dir():
     #       continue
      #  pasta_ano = empresa / ano / "Banco" / "Sicoob" / numero_conta / "Extrato CC"
       # if pasta_ano.exists():
         #   return empresa
   # return None

def _normalizar_nome_empresa(texto):
    base = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acentos = "".join(ch for ch in base if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", sem_acentos.lower())


def _formatar_nome_empresa_para_pasta(nome_empresa):
    """
    Formata o nome apenas para criação de pasta nova:
    - remove caracteres inválidos de caminho;
    - compacta espaços;
    - aplica title case com conectivos comuns em minúsculo;
    - mantém algumas siglas em maiúsculo.
    """
    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", str(nome_empresa or "")).strip()
    nome_limpo = re.sub(r"\s+", " ", nome_limpo)
    if not nome_limpo:
        return "Empresa Sem Nome"

    conectivos = {"de", "da", "do", "das", "dos", "e"}
    siglas_upper = {"MEI", "S/A", "SA", "CPF", "CNPJ"}
    sufixos_titulo = {"LTDA", "ME", "EPP", "EIRELI"}

    partes = []
    for idx, token in enumerate(nome_limpo.split(" ")):
        token_base = token.strip()
        if not token_base:
            continue
        token_upper = token_base.upper()
        token_lower = token_base.lower()

        if token_upper in siglas_upper:
            partes.append(token_upper)
        elif token_upper in sufixos_titulo:
            partes.append(token_lower.capitalize())
        elif idx > 0 and token_lower in conectivos:
            partes.append(token_lower)
        else:
            partes.append(token_lower.capitalize())

    nome_formatado = " ".join(partes).strip()
    return nome_formatado or "Empresa Sem Nome"


def encontrar_pasta_por_conta(base_path, numero_conta, ano, nome_empresa=""):
    """
    Procura a pasta de empresa nesta ordem:
    1) conta no ano informado;
    2) conta em qualquer outro ano;
    3) nome da empresa normalizado.
    Retorna a pasta da empresa se encontrada, senão None.
    """
    if not base_path.exists() or not base_path.is_dir():
        return None

    # 1) Match exato por conta no ano alvo
    for empresa in base_path.iterdir():
        if not empresa.is_dir():
            continue
        banco_sicoob = empresa / ano / "Banco" / "Sicoob"
        if banco_sicoob.is_dir():
            conta_pasta = banco_sicoob / numero_conta
            if conta_pasta.is_dir():
                print(f"📂 Empresa encontrada por conta no ano {ano}: {empresa.name}")
                return empresa

    # 2) Match por conta em qualquer ano
    for empresa in base_path.iterdir():
        if not empresa.is_dir():
            continue
        for ano_dir in empresa.iterdir():
            if not ano_dir.is_dir() or not re.fullmatch(r"\d{4}", ano_dir.name):
                continue
            conta_pasta = ano_dir / "Banco" / "Sicoob" / numero_conta
            if conta_pasta.is_dir():
                print(f"📂 Empresa encontrada por conta em outro ano ({ano_dir.name}): {empresa.name}")
                return empresa

    # 3) Fallback por nome da empresa normalizado
    alvo = _normalizar_nome_empresa(nome_empresa)
    if alvo:
        for empresa in base_path.iterdir():
            if not empresa.is_dir():
                continue
            if _normalizar_nome_empresa(empresa.name) == alvo:
                print(f"📂 Empresa encontrada por nome normalizado: {empresa.name}")
                return empresa

    return None


def _parse_periodo_comprovantes(periodo, mes_ref, ano_ref):
    periodo_txt = (periodo or "").strip()
    if not periodo_txt or "mês atual" in periodo_txt.lower():
        return str(ano_ref), f"{int(mes_ref):02d}"

    partes = [p.strip() for p in periodo_txt.split("/") if p.strip()]
    if len(partes) != 2:
        return str(ano_ref), f"{int(mes_ref):02d}"

    mes_txt = (
        partes[0].lower()
        .replace("ç", "c")
        .replace("á", "a")
        .replace("ã", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
    )
    ano_txt = re.sub(r"\D", "", partes[1])
    mapa_meses = {
        "janeiro": "01",
        "fevereiro": "02",
        "marco": "03",
        "abril": "04",
        "maio": "05",
        "junho": "06",
        "julho": "07",
        "agosto": "08",
        "setembro": "09",
        "outubro": "10",
        "novembro": "11",
        "dezembro": "12",
    }

    if mes_txt in mapa_meses and len(ano_txt) == 4:
        return ano_txt, mapa_meses[mes_txt]

    return str(ano_ref), f"{int(mes_ref):02d}"

def _mes_ano_esperado(mes_ref, ano_ref):
    try:
        return f"{int(mes_ref):02d}/{int(ano_ref)}"
    except Exception:
        return ""


def _normalizar_texto_periodo(texto):
    base = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acentos = "".join(ch for ch in base if not unicodedata.combining(ch))
    return sem_acentos.lower()


def _extrair_mes_ano_periodo_corrente(periodo_txt):
    periodo = str(periodo_txt or "").strip()
    if not periodo:
        return ""

    # Ex.: "01/02/2026 A 29/02/2026" -> usa a última data do período.
    datas = re.findall(r"\b(\d{2})/(\d{2})/(\d{4})\b", periodo)
    if datas:
        _, mes, ano = datas[-1]
        return f"{mes}/{ano}"

    # Ex.: "02/2026"
    match_mes_ano = re.search(r"\b(0?[1-9]|1[0-2])\s*/\s*(\d{4})\b", periodo)
    if match_mes_ano:
        mes = f"{int(match_mes_ano.group(1)):02d}"
        ano = match_mes_ano.group(2)
        return f"{mes}/{ano}"

    # Ex.: "Fevereiro/2026"
    periodo_norm = _normalizar_texto_periodo(periodo)
    match_nome_mes = re.search(
        r"\b(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b\s*/?\s*(\d{4})",
        periodo_norm,
    )
    if match_nome_mes:
        mapa = {
            "janeiro": "01",
            "fevereiro": "02",
            "marco": "03",
            "abril": "04",
            "maio": "05",
            "junho": "06",
            "julho": "07",
            "agosto": "08",
            "setembro": "09",
            "outubro": "10",
            "novembro": "11",
            "dezembro": "12",
        }
        mes = mapa.get(match_nome_mes.group(1), "")
        ano = match_nome_mes.group(2)
        if mes:
            return f"{mes}/{ano}"

    return ""


def _extrair_mes_ano_periodo_capital(texto_conteudo):
    texto = str(texto_conteudo or "")
    if not texto.strip():
        return ""

    contagem = {}
    ultima_data = {}

    for linha in texto.splitlines():
        linha_strip = linha.strip()
        if not linha_strip:
            continue

        linha_up = _normalizar_texto_periodo(linha_strip).upper()
        if "SALDO ANTERIOR" in linha_up:
            continue

        datas = re.findall(r"\b(\d{2})/(\d{2})/(\d{4})\b", linha_strip)
        if not datas:
            continue

        # Se a linha não tem indicação de movimentação, ignora para evitar cabeçalhos.
        if "HIST" in linha_up or "DATA" in linha_up or "EXTRATO" in linha_up:
            continue

        for dia, mes, ano in datas:
            chave = f"{mes}/{ano}"
            contagem[chave] = contagem.get(chave, 0) + 1
            valor_data = int(f"{ano}{mes}{dia}")
            ultima_data[chave] = max(ultima_data.get(chave, 0), valor_data)

    if not contagem:
        return ""

    return max(contagem.keys(), key=lambda chave: (contagem[chave], ultima_data.get(chave, 0)))


def _capital_sem_movimento_confere(texto_conteudo, mes_ref, ano_ref):
    """
    Mês de capital sem nenhuma movimentação: o extrato traz só "SALDO ANTERIOR" e "SALDO ATUAL".
    Confirma que é o mês pedido pela data do SALDO ANTERIOR, que deve ser o último dia do mês anterior.
    """
    try:
        esperado = (datetime(int(ano_ref), int(mes_ref), 1) - timedelta(days=1)).strftime("%d/%m/%Y")
    except Exception:
        return False
    for linha in str(texto_conteudo or "").splitlines():
        if "SALDO ANTERIOR" in _normalizar_texto_periodo(linha).upper():
            if esperado in re.findall(r"\b\d{2}/\d{2}/\d{4}\b", linha):
                return True
    return False


def _parse_data_ddmmyyyy(valor, fallback_ano=None, fallback_mes=None, fallback_dia="01"):
    txt = (valor or "").strip()
    m = re.match(r"^\s*(\d{2})/(\d{2})/(\d{4})\s*$", txt)
    if m:
        return m.group(3), m.group(2), m.group(1)
    ano = str(fallback_ano or datetime.now().year)
    mes = f"{int(fallback_mes or datetime.now().month):02d}"
    dia = f"{int(fallback_dia or 1):02d}"
    return ano, mes, dia


def _mes_ano_from_ddmmyyyy(valor):
    txt = (valor or "").strip()
    m = re.match(r"^\s*\d{2}/(\d{2})/(\d{4})\s*$", txt)
    if not m:
        return ""
    return f"{m.group(1)}/{m.group(2)}"


def _selecionar_data_calendar(page, dia, mes, ano):
    select_mes = page.locator("select.ui-datepicker-month, select.p-datepicker-month").first
    select_ano = page.locator("select.ui-datepicker-year, select.p-datepicker-year").first
    select_mes.wait_for(state="visible", timeout=10000)
    select_ano.wait_for(state="visible", timeout=10000)
    select_mes.select_option(value=str(int(mes) - 1))
    select_ano.select_option(value=str(int(ano)))
    page.wait_for_timeout(300)
    dia_sel = page.locator(
        "table.ui-datepicker-calendar td:not(.ui-datepicker-other-month) "
        f"a.ui-state-default:has-text('{int(dia)}')"
    ).first
    dia_sel.wait_for(state="visible", timeout=5000)
    dia_sel.click(timeout=5000)


def _fechar_overlays_novo_layout(page):
    """
    Fecha, de forma best-effort, drawers e diálogos do layout novo que um erro tenha deixado abertos
    (drawer de exportação/comprovante, diálogo "Fechar", popup swal2). Eles cobrem a tela e bloqueiam
    o clique em "Trocar conta", derrubando também as contas seguintes. Nunca levanta exceção.
    """
    candidatos = [
        "div.drawer-container.aberto i.fechar",
        "div.ui-dialog-mask button[data-content-label='Fechar']",
        "button.swal2-confirm",
    ]
    for _ in range(4):
        fechou = False
        for sel in candidatos:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=3000)
                    page.wait_for_timeout(500)
                    fechou = True
            except Exception:
                pass
        if not fechou:
            break


def _forcar_limpeza_dom_modal(page):
    """
    Força o fechamento de qualquer modal/backdrop Bootstrap-style ainda
    residual no DOM, na melhor tentativa possível (best-effort, nunca levanta
    exceção). Generaliza o helper que antes só existia dentro do ramo
    Comprovantes (fechamento de #modalDetalhesComprovante_modal) para os 3
    ramos de acessar_extrato().

    Usado nos caminhos de erro antes de retornar, para deixar a página num
    estado mais recuperável para a tentativa de "Trocar conta" de recovery
    feita pelo orquestrador (RF-04/RF-09, .spec/features/selecao-multiplos-meses).
    """
    _fechar_overlays_novo_layout(page)
    try:
        page.evaluate(
            """() => {
                document.querySelectorAll(
                    '.modal.show, .modal[style*="display: block"], .modal[style*="display:block"]'
                ).forEach((modal) => {
                    modal.classList.remove('show');
                    modal.style.display = 'none';
                    modal.setAttribute('aria-hidden', 'true');
                });
                document.querySelectorAll('.modal-backdrop').forEach((el) => el.remove());
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
            }"""
        )
    except Exception:
        pass


def acessar_extrato(
    page,
    conta,
    mes_selecionado,
    ano_selecionado,
    dia_inicio=None,
    dia_fim=None,
    base_drive=None,
    tipo_extrato="corrente",
    periodo_comprovantes="Mês atual",
    comprovante_modo="periodo",
    comprovante_data_inicial="",
    comprovante_data_final="",
    cartao_mes_referencia="",
    cartao_formato="PDF",
    cartao_baixar_ambos=False,
    primeiro_periodo=True,
    ultimo_periodo=True,
):
    """
    Fluxo completo:
    busca conta → captura nome empresa →
    acessa conta → vai ao extrato →
    aplica período via calendário → exporta PDF → salva na estrutura contábil padrão.

    primeiro_periodo/ultimo_periodo (RF-02/RF-03/RF-08, .spec/features/selecao-multiplos-meses):
    quando uma conta tem múltiplos meses selecionados, o orquestrador (main.py)
    chama esta função uma vez por mês. Os passos 1-7 (selecionar a conta) só
    rodam quando primeiro_periodo=True; o passo final "Trocar conta" só roda
    quando ultimo_periodo=True. Os defaults (True, True) preservam o
    comportamento anterior a esta feature para o caso de 1 único mês (RF-08).
    """
    tipo_txt = str(tipo_extrato).strip().lower()
    if "comprov" in tipo_txt:
        tipo_extrato_norm = "comprovantes"
    elif "cart" in tipo_txt:
        tipo_extrato_norm = "cartao"
    elif "capital" in tipo_txt:
        tipo_extrato_norm = "capital"
    else:
        tipo_extrato_norm = "corrente"
    numero = conta.get('numero', '').strip()
    # RNF-01 (.spec/features/selecao-multiplos-meses): identificador de período
    # usado no nome do screenshot de erro, para não colidir entre meses
    # distintos da mesma conta numa mesma execução.
    try:
        periodo_arquivo = f"{int(mes_selecionado):02d}-{ano_selecionado}"
    except (TypeError, ValueError):
        periodo_arquivo = "periodo-desconhecido"
    resultado = {
        "numero": numero,
        "empresa": "",
        "periodo": "",
        "periodo_esperado": "",
        "periodo_obtido": "",
        "pdf_path": "",
        "fallback_linhas": [],
    }
    if not numero:
        msg = "❌ Número da conta não encontrado."
        print(msg)
        resultado["erro"] = msg
        return resultado
    if not mes_selecionado or not ano_selecionado:
        msg = "❌ Mês/ano não informado para seleção do período."
        print(msg)
        resultado["erro"] = msg
        return resultado

    # Um erro no item anterior pode ter deixado drawer/diálogo aberto; fecha antes de navegar.
    _fechar_overlays_novo_layout(page)

    print(f"\n🚀 Processando extrato PDF para conta: {numero} | tipo={tipo_extrato_norm}")

    nome_empresa_limpo = ""
    nome_empresa_pasta = ""

    if primeiro_periodo:
        # 1. Abre tela Lista de contas
        try:
            if page.locator("h3:has-text('Lista de contas')").count() == 0:
                page.locator(SEL_TROCAR_CONTA).first.click(timeout=15000)
                page.wait_for_selector("h3:has-text('Lista de contas')", timeout=40000)
        except PlaywrightTimeoutError as e:
            msg = f"❌ Timeout ao abrir tela de troca para conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado
        except PlaywrightError as e:
            msg = f"❌ Erro Playwright ao abrir tela de troca para conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado
        except Exception as e:
            msg = f"❌ Erro inesperado ao abrir tela de troca para conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado

        # 2. Limpa busca anterior
        try:
            page.locator("button:has-text('X')").first.click(timeout=5000)
        except PlaywrightTimeoutError as e:
            print(f"ℹ️ Limpeza de busca anterior não necessária/timeout para conta {numero}: {e}")
        except PlaywrightError as e:
            print(f"ℹ️ Falha Playwright ao limpar busca anterior para conta {numero}: {e}")
        except Exception as e:
            print(f"ℹ️ Erro inesperado ao limpar busca anterior para conta {numero}: {e}")
            pass

        # 3. Busca conta
        try:
            input_busca = page.locator("input.sicoob-input-text").first
            input_busca.fill(numero)
            input_busca.press("Enter")
            page.wait_for_timeout(2000)  # pequeno delay após Enter
        except PlaywrightTimeoutError as e:
            msg = f"❌ Timeout na busca da conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado
        except PlaywrightError as e:
            msg = f"❌ Erro Playwright na busca da conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado
        except Exception as e:
            msg = f"❌ Erro inesperado na busca da conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado

        # 4. Verifica se apareceu
        conta_row_sel = f"div.seletor-conta:has-text('{numero}')"
        if page.locator(conta_row_sel).count() == 0:
            msg = f"❌ Conta {numero} não apareceu."
            print(msg)
            resultado["erro"] = msg
            return resultado

        # 5. Captura nome da empresa
        try:
            nome_empresa_raw = page.locator(conta_row_sel)\
                .locator("div.text-info-conta:has-text('Nome:')")\
                .inner_text(timeout=10000)
            nome_empresa = nome_empresa_raw.replace("Nome:", "").strip()
            print(f"🏢 Empresa detectada: {nome_empresa}")
        except PlaywrightTimeoutError as e:
            nome_empresa = "Empresa_Sem_Nome"
            print(f"⚠️ Timeout ao capturar nome da empresa da conta {numero}: {e}. Usando padrão: {nome_empresa}")
        except PlaywrightError as e:
            nome_empresa = "Empresa_Sem_Nome"
            print(f"⚠️ Erro Playwright ao capturar nome da empresa da conta {numero}: {e}. Usando padrão: {nome_empresa}")
        except Exception as e:
            nome_empresa = "Empresa_Sem_Nome"
            print(f"⚠️ Erro inesperado ao capturar nome da empresa da conta {numero}: {e}. Usando padrão: {nome_empresa}")

        nome_empresa_limpo = re.sub(r'[\\/*?:"<>|]', "", nome_empresa).strip()
        nome_empresa_pasta = _formatar_nome_empresa_para_pasta(nome_empresa_limpo or nome_empresa)
        resultado["empresa"] = nome_empresa_limpo or nome_empresa

        # 6. Acessa conta
        try:
            page.locator(conta_row_sel)\
                .locator("div.info-acesso-conta")\
                .first.click(timeout=15000)
        except PlaywrightTimeoutError as e:
            msg = f"❌ Timeout ao acessar conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado
        except PlaywrightError as e:
            msg = f"❌ Erro Playwright ao acessar conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado
        except Exception as e:
            msg = f"❌ Erro inesperado ao acessar conta {numero}: {e}"
            print(msg)
            resultado["erro"] = msg
            return resultado

        # 7. Aguarda dashboard
        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except PlaywrightTimeoutError as e:
            print(f"ℹ️ Timeout aguardando dashboard da conta {numero} (seguindo): {e}")
        except PlaywrightError as e:
            print(f"ℹ️ Erro Playwright aguardando dashboard da conta {numero} (seguindo): {e}")
        except Exception as e:
            print(f"ℹ️ Erro inesperado aguardando dashboard da conta {numero} (seguindo): {e}")
            pass

        # Layout novo: o menu do topo renderiza antes de o app estar pronto, e um clique
        # nesse intervalo se perde. Espera o menu montar + uma folga curta.
        try:
            page.wait_for_function(
                "document.querySelectorAll('sicoob-menu-horizontal li.container-icone').length >= 8",
                timeout=10000,
            )
            page.wait_for_timeout(1500)
        except (PlaywrightTimeoutError, PlaywrightError):
            pass
    else:
        # Meses seguintes da mesma conta (RF-03): não repete Trocar conta/busca,
        # reaproveita a empresa já resolvida no primeiro período desta conta.
        nome_empresa_limpo = conta.get("empresa", "") or ""
        nome_empresa_pasta = _formatar_nome_empresa_para_pasta(nome_empresa_limpo) if nome_empresa_limpo else ""
        resultado["empresa"] = nome_empresa_limpo
        print(f"↪️ Reaproveitando conta {numero} já selecionada (primeiro_periodo=False)")

    # 8. Vai para fluxo conforme tipo
    try:
        if tipo_extrato_norm == "cartao":
            click_menu_lateral(page, numero, "icone-card", "Cartões", timeout=15000)

            seletor_meus_cartoes = "a[href='#/cartoes'], a:has-text('Meus cartões')"
            _garantir_submenu_topo(page, "Cartões", seletor_meus_cartoes)
            page.wait_for_selector(seletor_meus_cartoes, state="visible", timeout=15000)
            page.locator(seletor_meus_cartoes).first.click(timeout=10000)
            page.wait_for_timeout(1200)

            # Modal informando ausência de cartões vinculados.
            try:
                popup_swal = page.locator("div.swal2-popup.swal2-modal").first
                if popup_swal.is_visible(timeout=2500):
                    swal_texto = popup_swal.locator("#swal2-content, .swal2-html-container").first.inner_text(timeout=3000)
                    swal_norm = unicodedata.normalize("NFKD", swal_texto).encode("ascii", "ignore").decode("ascii").lower()
                    if "nao existem cartoes de credito vinculados" in swal_norm:
                        page.locator("button.swal2-confirm").first.click(timeout=5000)
                        msg = f"⚠️ Conta {numero} sem cartões de crédito vinculados."
                        print(msg)
                        resultado["erro"] = msg
                        return resultado
            except Exception:
                pass

            seletor_detalhar_cartao = "a.link-cartao-credito.clickable, a[data-content-label='Detalhar cartão']"
            page.wait_for_selector(seletor_detalhar_cartao, state="visible", timeout=30000)
            page.locator(seletor_detalhar_cartao).first.click(timeout=10000)

            card_fatura = page.locator(
                "div.sectionCard",
                has=page.locator("span:has-text('Extrato da fatura')")
            ).first
            card_fatura.wait_for(state="visible", timeout=45000)

            venc_select = card_fatura.locator("select#idVencimentoFatura").first
            venc_select.wait_for(state="visible", timeout=45000)
            btn_emitir_fatura = card_fatura.locator("button:has-text('Emitir')").first
            mes_referencia_alvo = (cartao_mes_referencia or "").strip()

            def _coletar_opcoes_vencimento():
                return venc_select.evaluate(
                    """(sel) => Array.from(sel?.options || [])
                        .map((o) => ({
                            text: (o.textContent || '').trim(),
                            value: (o.value || '').trim()
                        }))
                        .filter((o) => o.text)"""
                )

            def _disparar_eventos_vencimento():
                venc_select.evaluate(
                    """(sel) => {
                        if (!sel) return;
                        sel.dispatchEvent(new Event('input', { bubbles: true }));
                        sel.dispatchEvent(new Event('change', { bubbles: true }));
                        sel.dispatchEvent(new Event('blur', { bubbles: true }));
                    }"""
                )

            def _ler_vencimento_selecionado():
                return (venc_select.evaluate(
                    """(sel) => {
                        const idx = sel ? sel.selectedIndex : -1;
                        if (!sel || idx < 0 || !sel.options || !sel.options[idx]) return '';
                        return (sel.options[idx].textContent || '').trim();
                    }"""
                ) or "").strip()

            # Aguarda o dropdown carregar opções válidas DD/MM/AAAA.
            opcoes_venc = []
            for _ in range(40):
                opcoes_venc = [
                    o for o in _coletar_opcoes_vencimento()
                    if re.match(r"^\d{2}/\d{2}/\d{4}$", (o.get("text", "") or "").strip())
                ]
                if opcoes_venc:
                    break
                page.wait_for_timeout(250)

            if not opcoes_venc:
                msg = f"❌ Não foi possível carregar as opções de vencimento do cartão para a conta {numero}."
                print(msg)
                resultado["erro"] = msg
                return resultado

            if mes_referencia_alvo:
                vencimento_alvo_txt = ""
                for opcao in opcoes_venc:
                    if _mes_ano_from_ddmmyyyy(opcao.get("text", "")) == mes_referencia_alvo:
                        vencimento_alvo_txt = opcao.get("text", "")
                        break

                if not vencimento_alvo_txt:
                    opcoes_mes = []
                    for opcao in opcoes_venc:
                        mm_aaaa = _mes_ano_from_ddmmyyyy(opcao.get("text", ""))
                        if mm_aaaa and mm_aaaa not in opcoes_mes:
                            opcoes_mes.append(mm_aaaa)
                    msg = (
                        f"❌ Mês de referência '{mes_referencia_alvo}' não encontrado para a conta {numero}. "
                        f"Meses disponíveis: {', '.join(opcoes_mes[:12])}"
                    )
                    print(msg)
                    resultado["erro"] = msg
                    return resultado

                # Tentativa manual: abre o drop e clica na opção.
                try:
                    venc_select.click(timeout=5000)
                    page.wait_for_timeout(120)
                    venc_select.locator("option", has_text=vencimento_alvo_txt).first.click(timeout=5000)
                except Exception:
                    pass
                _disparar_eventos_vencimento()
                page.wait_for_timeout(180)
                vencimento_escolhido = _ler_vencimento_selecionado()

                # Fallback único: seleção programática por texto no mesmo campo.
                if _mes_ano_from_ddmmyyyy(vencimento_escolhido) != mes_referencia_alvo:
                    print("↺ Fallback de seleção aplicado no vencimento do cartão.")
                    idx_alvo = venc_select.evaluate(
                        """(sel, args) => {
                            const alvo = (args?.alvo || '').trim();
                            const idx = Array.from(sel?.options || []).findIndex(
                                (o) => ((o.textContent || '').trim() === alvo)
                            );
                            if (idx >= 0) {
                                sel.selectedIndex = idx;
                                sel.dispatchEvent(new Event('input', { bubbles: true }));
                                sel.dispatchEvent(new Event('change', { bubbles: true }));
                                sel.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                            return idx;
                        }""",
                        {"alvo": vencimento_alvo_txt},
                    )
                    if int(idx_alvo) < 0:
                        msg = (
                            f"❌ Não foi possível localizar a data '{vencimento_alvo_txt}' "
                            f"no dropdown de vencimento para a conta {numero}."
                        )
                        print(msg)
                        resultado["erro"] = msg
                        return resultado
                    _disparar_eventos_vencimento()
                    page.wait_for_timeout(220)
                    vencimento_escolhido = _ler_vencimento_selecionado()
            else:
                vencimento_escolhido = _ler_vencimento_selecionado()

            if not vencimento_escolhido:
                vencimento_escolhido = (opcoes_venc[0].get("text", "") if opcoes_venc else "")
            if mes_referencia_alvo and _mes_ano_from_ddmmyyyy(vencimento_escolhido) != mes_referencia_alvo:
                msg = (
                    f"❌ Vencimento aplicado '{vencimento_escolhido}' não corresponde ao mês "
                    f"solicitado '{mes_referencia_alvo}' para a conta {numero}."
                )
                print(msg)
                resultado["erro"] = msg
                return resultado
            resultado["periodo"] = vencimento_escolhido
            if mes_referencia_alvo:
                print(f"→ Mês de referência solicitado: {mes_referencia_alvo}")
            else:
                print("→ Mês de referência solicitado: automático (mais recente)")
            print(f"→ Vencimento cartão selecionado: {vencimento_escolhido}")

            btn_emitir_fatura.click(timeout=15000)
            page.wait_for_selector("#modalExtratoFatura_modal", state="visible", timeout=120000)
            modal_cartao = page.locator("#modalExtratoFatura_modal").first

            ano_mov, mes_mov, dia_mov = _parse_data_ddmmyyyy(
                vencimento_escolhido,
                fallback_ano=ano_selecionado,
                fallback_mes=mes_selecionado,
                fallback_dia="01",
            )
            raiz_drive = Path(base_drive) if base_drive else Path(r"H:\Drives compartilhados\Contábil")
            empresa_existente = encontrar_pasta_por_conta(
                raiz_drive,
                numero,
                ano_mov,
                nome_empresa_limpo,
            )
            pasta_tipo_extrato = "Faturas do Cartão de Crédito"
            if empresa_existente:
                pasta_destino = empresa_existente / ano_mov / "Banco" / "Sicoob" / numero / pasta_tipo_extrato
                print(f"📂 Pasta existente encontrada: {empresa_existente.name}")
            else:
                pasta_destino = raiz_drive / nome_empresa_pasta / ano_mov / "Banco" / "Sicoob" / numero / pasta_tipo_extrato
                print(f"🏷️ Empresa (banco): {nome_empresa_limpo}")
                print(f"🏷️ Empresa (pasta nova): {nome_empresa_pasta}")
                print(f"📂 Criando nova pasta: {pasta_destino}")
            pasta_destino.mkdir(parents=True, exist_ok=True)

            formatos_execucao = ["OFX", "PDF"] if cartao_baixar_ambos else [(cartao_formato or "PDF").strip().upper()]
            for formato in formatos_execucao:
                if formato == "OFX":
                    ofx_btn = modal_cartao.locator("button:has-text('Exportar OFX')").first
                    ofx_btn.wait_for(state="visible", timeout=15000)
                    with page.expect_download(timeout=90000) as dl_info:
                        ofx_btn.click(timeout=15000)
                    download = dl_info.value
                    caminho_arquivo = pasta_destino / f"{mes_mov}.ofx"
                    download.save_as(str(caminho_arquivo))
                    resultado["pdf_path"] = str(caminho_arquivo)
                    print(f"📄 OFX de cartão salvo em: {caminho_arquivo}")
                else:
                    modal_body = modal_cartao.locator(".modal-body").first
                    html_modal = modal_body.inner_html(timeout=90000)
                    if not html_modal.strip():
                        raise Exception("Modal de extrato do cartão abriu sem conteúdo para PDF")

                    html_texto = build_html_extrato_cartao(
                        html_modal=html_modal,
                        numero_conta=numero,
                        empresa=nome_empresa_limpo,
                        vencimento=vencimento_escolhido,
                    )
                    pagina_tmp = page.context.new_page()
                    try:
                        pagina_tmp.set_content(html_texto, wait_until="load", timeout=25000)
                        pagina_tmp.emulate_media(media="print")
                        pdf_bytes = pagina_tmp.pdf(
                            format="A4",
                            landscape=False,
                            print_background=True,
                            margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                            prefer_css_page_size=True,
                        )
                    finally:
                        pagina_tmp.close()

                    caminho_arquivo = pasta_destino / f"{mes_mov}.pdf"
                    with open(caminho_arquivo, "wb") as f:
                        f.write(pdf_bytes)
                    resultado["pdf_path"] = str(caminho_arquivo)
                    print(f"📄 PDF de cartão salvo em: {caminho_arquivo}")

            # Fecha o modal de cartão após salvar.
            try:
                modal_cartao.locator("button[data-content-label='Fechar'], button:has-text('Fechar')").first.click(timeout=8000)
                page.wait_for_selector("#modalExtratoFatura_modal", state="hidden", timeout=15000)
            except Exception:
                try:
                    modal_cartao.locator(".modal-header button.close").first.click(timeout=5000)
                except Exception:
                    pass

            if ultimo_periodo:
                try:
                    page.locator(SEL_TROCAR_CONTA).first.dispatch_event("click")
                    page.wait_for_selector("h3:has-text('Lista de contas')", timeout=30000)
                    print("→ Voltou para lista com sucesso (cartão)")
                except Exception as e:
                    print(f"⚠️ Não foi possível voltar para lista após cartão da conta {numero}: {e}")

            return resultado

        click_menu_lateral(page, numero, "icone-conta", "Contas")

        if tipo_extrato_norm == "comprovantes":
            def _ler_popup_sem_comprovantes():
                """
                Detecta a ausência de comprovantes e retorna o texto do aviso.
                Layout novo: diálogo ib-sicoob-feedback-suport (span.texto-ib-sicoob-feedback-suport).
                Layout antigo: popup swal2.
                """
                try:
                    inline = page.locator(
                        "span.texto-ib-sicoob-feedback-suport:has-text('Não existem comprovantes')"
                    ).first
                    if inline.is_visible(timeout=300):
                        return (inline.inner_text(timeout=2000) or "").strip()
                except Exception:
                    pass
                try:
                    popup = page.locator("div.swal2-popup.swal2-modal").first
                    if not popup.is_visible(timeout=800):
                        return ""
                    texto = popup.locator("#swal2-content, .swal2-html-container").first.inner_text(timeout=2500)
                    txt_norm = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()
                    if "nao existem comprovantes" in txt_norm:
                        return (texto or "").strip()
                except Exception:
                    pass
                return ""

            def _confirmar_popup_sem_comprovantes():
                # Layout novo: diálogo (.ui-dialog) com botão "Fechar".
                botao_fechar = page.locator("div.ui-dialog-mask button[data-content-label='Fechar']")
                if botao_fechar.count() > 0:
                    try:
                        botao_fechar.first.click(timeout=5000)
                        page.wait_for_selector("div.ui-dialog-mask", state="hidden", timeout=10000)
                    except Exception:
                        pass
                    return
                if page.locator("button.swal2-confirm").count() == 0:
                    return
                try:
                    page.locator("button.swal2-confirm").first.click(timeout=5000)
                except Exception:
                    return
                try:
                    page.wait_for_selector("div.swal2-popup.swal2-modal", state="hidden", timeout=10000)
                except Exception:
                    pass

            seletor_entrada_comprovantes = (
                "a[href='#/comprovantes'], "
                "div.circulo.clickable[data-content-label='Comprovantes'], "
                "div.produto:has-text('Comprovantes') .circulo.clickable"
            )
            _garantir_submenu_topo(page, "Contas", seletor_entrada_comprovantes)
            page.wait_for_selector(seletor_entrada_comprovantes, state='visible', timeout=15000)
            page.locator(seletor_entrada_comprovantes).first.click()

            page.wait_for_selector(
                "p-dropdown#idTipoTransacao, #formConsultaComprovantes, #btnConsultarComprovantes",
                state='visible',
                timeout=30000,
            )

            # Layout novo: período único (p-calendar em modo intervalo) + botão Confirmar.
            def _aplicar_periodo_comprovantes(data_ini, data_fim):
                """data_ini/data_fim = (dia, mes, ano)."""
                page.locator("p-calendar input[readonly]").first.click(timeout=10000)
                page.wait_for_selector(".ui-datepicker-group", state="visible", timeout=20000)
                _selecionar_data_calendar(page, *data_ini)
                _selecionar_data_calendar(page, *data_fim)
                page.locator("button.new-btn-sicoob:has-text('Confirmar')").first.click(timeout=10000)
                page.wait_for_timeout(800)

            if comprovante_modo == "intervalo" and comprovante_data_inicial and comprovante_data_final:
                dia_i, mes_i, ano_i = comprovante_data_inicial.split("/")
                dia_f, mes_f, ano_f = comprovante_data_final.split("/")
                _aplicar_periodo_comprovantes((dia_i, mes_i, ano_i), (dia_f, mes_f, ano_f))
                periodo_alvo = f"{comprovante_data_inicial} - {comprovante_data_final}"
            else:
                periodo_alvo = (periodo_comprovantes or "Mês atual").strip()
                if "mês atual" not in periodo_alvo.lower():
                    # O portal já abre no mês corrente; outros meses viram intervalo do dia 1 ao último dia.
                    ano_p, mes_p = _parse_periodo_comprovantes(periodo_alvo, mes_selecionado, ano_selecionado)
                    ultimo_dia_p = calendar.monthrange(int(ano_p), int(mes_p))[1]
                    _aplicar_periodo_comprovantes(("1", mes_p, ano_p), (str(ultimo_dia_p), mes_p, ano_p))

            page.locator("#btnConsultarComprovantes, button:has-text('Consultar')").first.click(timeout=15000)
            resultado["periodo"] = periodo_alvo
            print(f"→ Fluxo comprovantes consultado com período: {periodo_alvo}")

            # Após consultar, pode abrir swal2 bloqueante quando não há comprovantes.
            popup_sem_comprovantes = ""
            encontrou_resultado_consulta = False
            for _ in range(80):  # até ~40s (80 * 500ms)
                popup_sem_comprovantes = _ler_popup_sem_comprovantes()
                if popup_sem_comprovantes:
                    _confirmar_popup_sem_comprovantes()
                    encontrou_resultado_consulta = True
                    break

                if page.locator(".ui-table-tbody tr, p-table tbody tr, div:has-text('Nenhum registro')").count() > 0:
                    encontrou_resultado_consulta = True
                    break
                page.wait_for_timeout(500)

            if not encontrou_resultado_consulta:
                page.wait_for_selector(
                    ".ui-table-tbody tr, p-table tbody tr, div:has-text('Nenhum registro')",
                    timeout=40000
                )

            # Fase C: seleciona todos e emite comprovantes em lote.
            if popup_sem_comprovantes:
                msg = (
                    f"⚠️ Não existem comprovantes para o período {periodo_alvo}. "
                    "Conta seguirá para a próxima."
                )
                print(msg)
                resultado["erro"] = msg
            elif page.locator("div:has-text('Nenhum registro')").count() > 0:
                msg = f"⚠️ Nenhum comprovante encontrado para o período {periodo_alvo}"
                print(msg)
                resultado["erro"] = msg
            else:
                header_checkbox = page.locator(
                    "p-tableheadercheckbox .ui-chkbox-box, th p-tableheadercheckbox .ui-chkbox-box"
                ).first
                header_checkbox.wait_for(state="visible", timeout=15000)

                if (header_checkbox.get_attribute("aria-checked") or "").lower() != "true":
                    header_checkbox.click(timeout=10000)

                emitir_lote_btn = page.locator("button.new-btn-sicoob[data-content-label='Emitir comprovantes'], #btnEmitirLoteComprovantes").first
                emitir_lote_btn.wait_for(state="visible", timeout=15000)
                for _ in range(30):
                    if not emitir_lote_btn.get_attribute("disabled"):
                        break
                    page.wait_for_timeout(300)
                if emitir_lote_btn.get_attribute("disabled"):
                    raise Exception("Botão 'Emitir comprovantes' permaneceu desabilitado")

                emitir_lote_btn.click(timeout=15000)
                page.wait_for_selector(SEL_MODAL_COMPROVANTE, state="visible", timeout=120000)
                page.wait_for_selector(SEL_COMPROVANTE_ITEM, timeout=120000)

                modal_body = page.locator(SEL_MODAL_COMPROVANTE_CORPO).first
                # No drawer novo o corpo traz controles da UI ("Modo de impressão"); fica só com os .comprovante.
                html_modal = modal_body.evaluate(
                    """el => {
                        if (!el.classList.contains('card-drawer-body')) return el.innerHTML;
                        const itens = [...el.querySelectorAll('.comprovante')];
                        return itens.length ? itens.map(i => i.outerHTML).join('') : el.innerHTML;
                    }""",
                    timeout=90000,
                )
                if not html_modal.strip():
                    raise Exception("Modal de comprovantes abriu sem conteúdo para PDF")

                html_texto = build_html_comprovantes_sicoob(
                    html_modal=html_modal,
                    numero_conta=numero,
                    empresa=nome_empresa_limpo,
                    periodo=periodo_alvo,
                )

                pagina_tmp = page.context.new_page()
                try:
                    pagina_tmp.set_content(html_texto, wait_until="load", timeout=25000)
                    pagina_tmp.emulate_media(media="print")
                    pdf_bytes = pagina_tmp.pdf(
                        format="A4",
                        landscape=False,
                        print_background=True,
                        margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                        prefer_css_page_size=True,
                    )
                finally:
                    pagina_tmp.close()

                ano_mov, mes_mov = _parse_periodo_comprovantes(periodo_alvo, mes_selecionado, ano_selecionado)
                raiz_drive = Path(base_drive) if base_drive else Path(r"H:\Drives compartilhados\Contábil")
                empresa_existente = encontrar_pasta_por_conta(
                    raiz_drive,
                    numero,
                    ano_mov,
                    nome_empresa_limpo,
                )
                pasta_tipo_extrato = "Comprovantes"
                if empresa_existente:
                    pasta_destino = empresa_existente / ano_mov / "Banco" / "Sicoob" / numero / pasta_tipo_extrato
                    print(f"📂 Pasta existente encontrada: {empresa_existente.name}")
                else:
                    pasta_destino = raiz_drive / nome_empresa_pasta / ano_mov / "Banco" / "Sicoob" / numero / pasta_tipo_extrato
                    print(f"🏷️ Empresa (banco): {nome_empresa_limpo}")
                    print(f"🏷️ Empresa (pasta nova): {nome_empresa_pasta}")
                    print(f"📂 Criando nova pasta: {pasta_destino}")

                pasta_destino.mkdir(parents=True, exist_ok=True)
                nome_arquivo = f"{mes_mov}.pdf"
                caminho_arquivo = pasta_destino / nome_arquivo
                print(f"📁 Usando raiz customizada: {raiz_drive}")
                with open(caminho_arquivo, "wb") as f:
                    f.write(pdf_bytes)
                resultado["pdf_path"] = str(caminho_arquivo)
                print(f"📄 Comprovantes salvos em: {caminho_arquivo}")

                # Fecha modal somente após gerar e salvar PDF.
                overlay_sel = (
                    "div.block-ui-wrapper.block-ui-main.active, "
                    "block-ui-content .loadingData.active, "
                    ".loadingData.active"
                )
                fechar_btn = page.locator(SEL_MODAL_COMPROVANTE_FECHAR).first

                # Tenta fechar com clique direto primeiro e depois retries com lógica de estado.
                modal_fechado = False
                ultimo_erro_close = None

                def _forcar_fechamento_modal_js():
                    page.evaluate(
                        """() => {
                            const modal = document.querySelector('#modalDetalhesComprovante_modal');
                            if (modal) {
                                modal.classList.remove('show');
                                modal.style.display = 'none';
                                modal.setAttribute('aria-hidden', 'true');
                            }
                            document.querySelectorAll('.modal-backdrop').forEach((el) => el.remove());
                            document.body.classList.remove('modal-open');
                            document.body.style.overflow = '';
                        }"""
                    )

                try:
                    fechar_btn.click(timeout=10000)
                    page.wait_for_selector(SEL_MODAL_COMPROVANTE, state="hidden", timeout=8000)
                    modal_fechado = True
                except (PlaywrightTimeoutError, PlaywrightError) as e:
                    ultimo_erro_close = e

                for tentativa in range(1, 6):
                    if modal_fechado:
                        break
                    try:
                        # Espera overlay sumir; se não, tenta remover para liberar o DOM.
                        try:
                            page.wait_for_selector(overlay_sel, state="hidden", timeout=30000)
                        except (PlaywrightTimeoutError, PlaywrightError):
                            try:
                                page.evaluate(
                                    """() => {
                                        document.querySelectorAll(
                                          'div.block-ui-wrapper.block-ui-main.active, block-ui-content .loadingData.active, .loadingData.active'
                                        ).forEach((el) => {
                                            el.style.pointerEvents = 'none';
                                            el.style.display = 'none';
                                            el.classList.remove('active');
                                        });
                                    }"""
                                )
                            except Exception:
                                pass

                        # Se o modal já estiver hidden, segue.
                        try:
                            page.wait_for_selector(SEL_MODAL_COMPROVANTE, state="hidden", timeout=3000)
                            modal_fechado = True
                            break
                        except (PlaywrightTimeoutError, PlaywrightError):
                            pass

                        # Se o botão estiver visível, tenta fechar normalmente.
                        if fechar_btn.is_visible():
                            try:
                                fechar_btn.click(timeout=8000)
                            except (PlaywrightTimeoutError, PlaywrightError):
                                pass

                        # Se o botão está hidden, aguarda fechamento ou força via JS.
                        try:
                            page.wait_for_selector(SEL_MODAL_COMPROVANTE, state="hidden", timeout=8000)
                            modal_fechado = True
                            break
                        except (PlaywrightTimeoutError, PlaywrightError):
                            _forcar_fechamento_modal_js()

                        page.wait_for_selector(SEL_MODAL_COMPROVANTE, state="hidden", timeout=8000)
                        modal_fechado = True
                        break
                    except (PlaywrightTimeoutError, PlaywrightError) as e:
                        ultimo_erro_close = e
                        try:
                            fechar_btn.dispatch_event("click")
                        except Exception:
                            pass
                        try:
                            page.keyboard.press("Escape")
                        except Exception:
                            pass
                        page.wait_for_timeout(800)

                if not modal_fechado:
                    raise Exception(f"Modal de comprovantes não fechou após tentativas: {ultimo_erro_close}")

            # Volta para lista de contas após finalizar comprovantes (somente no último período - RF-03).
            if ultimo_periodo:
                try:
                    page.locator(SEL_TROCAR_CONTA).first.dispatch_event("click")
                    page.wait_for_selector("h3:has-text('Lista de contas')", timeout=25000)
                    print("→ Voltou para lista com sucesso (comprovantes)")
                except Exception as e:
                    print(f"⚠️ Não foi possível voltar para lista após comprovantes da conta {numero}: {e}")

            print("→ Fase C concluída no fluxo comprovantes")
            return resultado

        if tipo_extrato_norm == "capital":
            seletor_menu_extrato = (
                "a[href='#/extrato-conta-capital'], "
                "a:has-text('Extrato conta capital')"
            )
        else:
            seletor_menu_extrato = "a[href='#/home-extrato'], a:has-text('Extrato de conta corrente')"

        # Layout novo: o submenu "Contas" já mostra os links; "Consultas" (acordeão) só existe no layout antigo.
        if not _garantir_submenu_topo(page, "Contas", seletor_menu_extrato):
            botao_consultas = page.locator("button.btn.btn-link[data-target='#div-itemmenu-0']:has-text('Consultas')").first
            try:
                botao_consultas.wait_for(state="visible", timeout=10000)
                botao_consultas.click()
            except Exception as e:
                print(f"⚠️ conta {numero} | 'Consultas' falhou no clique normal, tentando force: {e}")
                botao_consultas.click(force=True, timeout=10000)

        page.wait_for_selector(seletor_menu_extrato, state='visible', timeout=12000)
        page.locator(seletor_menu_extrato).first.click()

        # Espera a tela do extrato de fato trocar. Vindo de outra tela com calendário (ex.: comprovantes),
        # o clique no calendário podia pegar o da tela anterior, que some na troca (selects nunca aparecem).
        try:
            rota_extrato = "extrato-conta-capital" if tipo_extrato_norm == "capital" else "home-extrato"
            page.wait_for_url(re.compile(rf"#/{rota_extrato}"), timeout=15000)
        except (PlaywrightTimeoutError, PlaywrightError):
            pass
    except PlaywrightTimeoutError as e:
        # Nota: este except cobre qualquer timeout não tratado localmente dentro
        # dos ramos cartão/comprovantes/abertura de menu (tipo_extrato_norm
        # identifica qual fluxo estava em curso — a etapa exata fica no `e`).
        msg = f"❌ Timeout no fluxo '{tipo_extrato_norm}' da conta {numero}: {e}"
        print(msg)
        _forcar_limpeza_dom_modal(page)
        resultado["erro"] = msg
        return resultado
    except PlaywrightError as e:
        msg = f"❌ Erro Playwright no fluxo '{tipo_extrato_norm}' da conta {numero}: {e}"
        print(msg)
        _forcar_limpeza_dom_modal(page)
        resultado["erro"] = msg
        return resultado
    except Exception as e:
        msg = f"❌ Erro inesperado no fluxo '{tipo_extrato_norm}' da conta {numero}: {e}"
        print(msg)
        _forcar_limpeza_dom_modal(page)
        resultado["erro"] = msg
        return resultado

    # 9. Aguarda carregar extrato
    try:
        page.wait_for_load_state("networkidle", timeout=25000)
    except PlaywrightTimeoutError as e:
        print(f"ℹ️ Timeout aguardando tela de extrato da conta {numero} (seguindo): {e}")
    except PlaywrightError as e:
        print(f"ℹ️ Erro Playwright aguardando tela de extrato da conta {numero} (seguindo): {e}")
    except Exception as e:
        print(f"ℹ️ Erro inesperado aguardando tela de extrato da conta {numero} (seguindo): {e}")
        pass

    # 10. Aplica período - seleciona mês/ano e desmarca dias conforme GUI
    try:
        mes_sel = int(mes_selecionado)
        ano_sel = int(ano_selecionado)
        timeout_extrato_ms = 120000
        timeout_export_btn_ms = 90000
        timeout_drawer_ms = 90000
        timeout_formato_ms = 60000

        print("→ Abrindo calendário...")

        calendar_inputs = [
            "p-calendar input[readonly]",
            "input[placeholder='Lançamentos do dia']",
            "p-calendar .ui-calendar",
            "div.sicoob-icon-input .calendar-days",
        ]
        icon_calendar = None
        for sel in calendar_inputs:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=5000)
                icon_calendar = loc
                break
            except Exception:
                continue
        if not icon_calendar:
            raise RuntimeError("Não foi possível localizar o calendário do Período.")
        icon_calendar.click(timeout=10000)

        page.wait_for_selector(".ui-datepicker-group", state="visible", timeout=20000)
        print("→ Calendário aberto")

        page.wait_for_timeout(800)

        select_mes = page.locator("select.ui-datepicker-month, select.p-datepicker-month").first
        select_ano = page.locator("select.ui-datepicker-year, select.p-datepicker-year").first
        select_mes.wait_for(state="visible", timeout=10000)
        select_ano.wait_for(state="visible", timeout=10000)

        select_option_ok = False
        try:
            select_mes.select_option(value=str(mes_sel - 1))
            page.wait_for_timeout(400)
            select_ano.select_option(value=str(ano_sel))
            page.wait_for_timeout(1500)

            mes_aplicado = select_mes.evaluate("el => el.value")
            ano_aplicado = select_ano.evaluate("el => el.value")
            if mes_aplicado == str(mes_sel - 1) and ano_aplicado == str(ano_sel):
                select_option_ok = True
            else:
                print(f"⚠️ select_option não refletiu nos <select> (mês={mes_aplicado}, ano={ano_aplicado}). Caindo para setas.")
        except Exception as e:
            print(f"⚠️ select_option falhou: {e}. Caindo para setas.")

        if not select_option_ok:
            mes_atual = int(select_mes.evaluate("el => el.value")) + 1
            ano_atual = int(select_ano.evaluate("el => el.value"))
            diferenca = (ano_sel - ano_atual) * 12 + (mes_sel - mes_atual)

            if diferenca > 0:
                btn = page.locator("a.ui-datepicker-next").first
                for i in range(diferenca):
                    btn.click(timeout=5000, force=True)
                    page.wait_for_timeout(300)
            elif diferenca < 0:
                btn = page.locator("a.ui-datepicker-prev").first
                for i in range(abs(diferenca)):
                    btn.click(timeout=5000, force=True)
                    page.wait_for_timeout(300)

            page.wait_for_timeout(1000)

            mes_atual_final = int(select_mes.evaluate("el => el.value")) + 1
            ano_atual_final = int(select_ano.evaluate("el => el.value"))
            if mes_atual_final != mes_sel or ano_atual_final != ano_sel:
                print(f"⚠️ Validação do mês/ano não bateu após setas (esperado {mes_sel}/{ano_sel}, obtido {mes_atual_final}/{ano_atual_final}). Assumindo contagem.")

        print(f"→ Mês/Ano aplicado: {mes_sel}/{ano_sel}")

        def selecionar_dia_calendario(dia_valor):
            if not dia_valor:
                return
            try:
                dia_sel = page.locator(
                    "table.ui-datepicker-calendar td:not(.ui-datepicker-other-month) "
                    f"a.ui-state-default:has-text('{int(dia_valor)}')"
                ).first
                dia_sel.wait_for(state="visible", timeout=10000)
                dia_sel.click(timeout=5000)
                page.wait_for_timeout(300)
            except Exception as e:
                print(f"⚠️ Falha ao selecionar dia {dia_valor}: {e}")

        if dia_inicio and dia_fim and dia_inicio > dia_fim:
            dia_inicio, dia_fim = dia_fim, dia_inicio

        ultimo_mes = calendar.monthrange(ano_sel, mes_sel)[1]

        # UI-02 (.spec/features/selecao-multiplos-meses): dia_inicio/dia_fim
        # podem vir de um único intervalo global reaplicado a vários meses
        # (checklist de múltiplos meses) - trunca ao último dia real DESTE
        # mês/ano específico, senão um dia inexistente (ex.: 31 para um mês
        # de 30 dias) simplesmente não é encontrado no calendário do banco e
        # falha silenciosamente (só um aviso no log), deixando o intervalo
        # aplicado incompleto/diferente do esperado para aquele mês.
        if isinstance(dia_inicio, int):
            dia_inicio = min(dia_inicio, ultimo_mes)
        if isinstance(dia_fim, int):
            dia_fim = min(dia_fim, ultimo_mes)

        intervalo_completo = (
            isinstance(dia_inicio, int)
            and isinstance(dia_fim, int)
            and dia_inicio == 1
            and dia_fim == ultimo_mes
        )

        if CALENDAR_MODE == "single":
            if intervalo_completo:
                print("→ Mês completo detectado. Pulando seleção de dias (Sicoob já preenche o mês todo automaticamente).")
            else:
                selecionar_dia_calendario(dia_inicio)
                if dia_fim and dia_fim != dia_inicio:
                    page.wait_for_timeout(300)
                    selecionar_dia_calendario(dia_fim)
        elif CALENDAR_MODE == "range":
            selecionar_dia_calendario(dia_inicio)
            if dia_fim and dia_fim != dia_inicio:
                page.wait_for_timeout(300)
                selecionar_dia_calendario(dia_fim)
        else:  # "none"
            pass
        page.wait_for_timeout(500)

        confirmar_btn = page.locator(
            "button.new-btn-sicoob:has-text('Confirmar'), "
            "button:has-text('Confirmar'), "
            "button:has-text('Aplicar')"
        ).first

        confirmar_btn.wait_for(state="visible", timeout=15000)
        confirmar_btn.click(timeout=10000)
        page.wait_for_timeout(800)

        try:
            input_periodo = page.locator("p-calendar input[readonly]").first
            valor_aplicado = input_periodo.input_value()
            if not valor_aplicado or "/" not in valor_aplicado:
                raise RuntimeError(f"Período não aplicado: input vazio ou inválido ('{valor_aplicado}')")
            print(f"→ Período aplicado no input: {valor_aplicado}")
        except Exception as e:
            print(f"⚠️ Falha ao validar input do período: {e}")

        # Espera tabela/conteúdo carregar com timeout ajustado para períodos mais antigos
        try:
            if tipo_extrato_norm == "capital":
                page.wait_for_selector("button:has-text('Exportar extrato'), span.extrato-conta-capital-exportar", state="visible", timeout=25000)
            else:
                page.wait_for_selector(".mensagem-nenhum-lancamento, .lancamentos, table", state="attached", timeout=25000)
        except Exception as e:
            print(f"⚠️ Aviso: Tabela não detectada visualmente (pode estar vazia ou oculta). Prosseguindo para exportação...")
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_extrato_ms, 45000))
        except (PlaywrightTimeoutError, PlaywrightError):
            pass
        try:
            overlay = page.locator("div.overlay.visivel").first
            overlay.wait_for(state="hidden", timeout=12000)
        except (PlaywrightTimeoutError, PlaywrightError):
            pass
        print("→ Período aplicado e extrato estabilizado para exportação")

    except PlaywrightTimeoutError as e:
        msg = f"❌ Falha ao aplicar período na conta {numero}: {e}"
        print(msg)
        resultado["erro"] = msg
        return resultado
    except PlaywrightError as e:
        msg = f"❌ Erro Playwright ao aplicar período na conta {numero}: {e}"
        print(msg)
        resultado["erro"] = msg
        return resultado
    except Exception as e:
        msg = f"❌ Erro inesperado ao aplicar período na conta {numero}: {e}"
        print(msg)
        resultado["erro"] = msg
        return resultado

        # 11. Exportação
    try:
        print("→ Abrindo modal de exportação...")

        if tipo_extrato_norm == "capital":
            seletor_btn_exportar = (
                "span.extrato-conta-capital-exportar, "
                "span[data-content-label='Exportar extrato'].extrato-conta-capital-exportar, "
                "button:has-text('Exportar extrato')"
            )
        else:
            seletor_btn_exportar = "button:has-text('Exportar extrato')"

        export_btn = page.locator(seletor_btn_exportar).first

        modal_aberto = False
        ultimo_erro_export = None
        for tentativa in range(1, 4):
            try:
                print(f"→ Tentativa {tentativa}/3 para abrir exportação")
                export_btn.wait_for(state="visible", timeout=timeout_export_btn_ms)
                export_btn.click(timeout=15000)

                # Espera drawer abrir
                page.wait_for_selector("div.drawer-container.aberto, div.card-drawer", timeout=timeout_drawer_ms)
                page.wait_for_selector(
                    "div:has-text('Selecionar o formato desejado'), div:has-text('Selecione o formato desejado')",
                    timeout=timeout_formato_ms,
                )
                print(f"→ Modal aberto (tentativa {tentativa})")
                modal_aberto = True
                break
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                ultimo_erro_export = e
                print(f"⚠️ Falha ao abrir exportação (tentativa {tentativa}): {e}")
                try:
                    page.wait_for_selector(
                        "table tr, .mensagem-nenhum-lancamento, .lancamentos",
                        timeout=min(15000, timeout_extrato_ms),
                    )
                except (PlaywrightTimeoutError, PlaywrightError):
                    pass
                try:
                    overlay = page.locator("div.overlay.visivel").first
                    overlay.wait_for(state="hidden", timeout=6000)
                except (PlaywrightTimeoutError, PlaywrightError):
                    pass
                page.wait_for_timeout(2000)

        if not modal_aberto:
            raise Exception(f"Falha abrindo modal de exportação após 3 tentativas: {ultimo_erro_export}")

        # Seleciona o card de TEXTO (clica no span/card)
        texto_card = page.locator(
            "div.home-extrato-card-tipo-export:has(span:has-text('Texto')), "
            "div.extrato-card-tipo-export:has(span:has-text('Texto')), "
            "span.home-extrato-titulo-card-exportar:has-text('Texto'), "
            "span.extrato-titulo-card-exportar:has-text('Texto'), "
            "div.d-flex.align-items-center:has(span:has-text('Texto')), "
            "span:has-text('Texto')"
        ).first

        texto_card.wait_for(state="visible", timeout=15000)
        texto_card.click(position={"x": 20, "y": 20}, timeout=10000)  # offset para evitar filhos
        print("→ Opção Texto selecionada no card")

        # Escopo fixo no drawer aberto para não clicar em botão fora do modal.
        export_drawer = page.locator("div.drawer-container.aberto, div.card-drawer").last

        # Espera botão final habilitar
        final_btn = export_drawer.locator(
            "ib-sicoob-button[label='Exportar extrato'] button.new-btn-sicoob, "
            "button.new-btn-sicoob[data-content-label='Exportar extrato']"
        ).last

        final_btn.wait_for(state="visible", timeout=15000)

        # Polling até habilitar
        for _ in range(25):
            if not final_btn.get_attribute("disabled"):
                break
            page.wait_for_timeout(400)

        if final_btn.get_attribute("disabled"):
            msg = "❌ Botão 'Exportar extrato' permaneceu disabled"
            print(msg)
            resultado["erro"] = msg
            return resultado

        print("→ Botão final habilitado - exportando texto para conversão")

        final_btn_clickable = export_drawer.locator(
            "ib-sicoob-button[label='Exportar extrato'] .content-info-button.clickable, "
            "ib-sicoob-button[label='Exportar extrato'] span.clickable:has-text('Exportar extrato')"
        ).first

        def clicar_exportar_final():
            overlay = page.locator("div.overlay.visivel")
            try:
                if overlay.count() > 0:
                    overlay.first.wait_for(state="hidden", timeout=12000)
            except (PlaywrightTimeoutError, PlaywrightError):
                try:
                    page.evaluate("""() => {
                        document.querySelectorAll('div.overlay.visivel').forEach((el) => {
                            el.style.pointerEvents = 'none';
                            el.style.display = 'none';
                            el.classList.remove('visivel');
                        });
                    }""")
                    print("→ Overlay forçado a sumir via JS antes do clique final")
                except Exception:
                    pass

            try:
                final_btn.click(force=True, timeout=15000)
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                print(f"⚠️ Clique no botão direto falhou na conta {numero}, tentando fallback .clickable: {e}")
                try:
                    final_btn_clickable.click(force=True, timeout=15000)
                except (PlaywrightTimeoutError, PlaywrightError):
                    final_btn_clickable.dispatch_event("click")

        def resposta_eh_texto(resp):
            content_disposition = (resp.header_value("content-disposition") or "").lower()
            content_type = (resp.header_value("content-type") or "").lower()
            return (
                resp.status == 200
                and resp.request.method == "POST"
                and "attachment" in content_disposition
                and ".txt" in content_disposition
                and (
                    "text/plain" in content_type
                    or "application/octet-stream" in content_type
                )
            )

        texto_bytes = None

        # 11.1 Captura o arquivo texto pela resposta HTTP do endpoint de exportação
        try:
            with page.expect_response(resposta_eh_texto, timeout=45000) as resp_info:
                clicar_exportar_final()
            texto_bytes = resp_info.value.body()
            if texto_bytes:
                print("→ Texto capturado da resposta")
            else:
                raise Exception("Resposta de exportação retornou vazia")
        except PlaywrightTimeoutError:
            raise Exception("Timeout aguardando resposta de exportação de texto")
        except PlaywrightError as e:
            raise Exception(f"Erro Playwright ao capturar texto da rede: {e}")
        except Exception as e:
            raise Exception(f"Erro inesperado ao capturar texto da rede: {e}")

        # 11.2 Converte TXT -> PDF
        try:
            texto_conteudo = decode_extrato_texto(texto_bytes)

            if not texto_conteudo.strip():
                raise Exception("Texto capturado está vazio após decode")
            if tipo_extrato_norm == "capital":
                resultado["fallback_linhas"] = []
                resultado["periodo_esperado"] = _mes_ano_esperado(mes_selecionado, ano_selecionado)
                resultado["periodo_obtido"] = _extrair_mes_ano_periodo_capital(texto_conteudo)

                if not resultado["periodo_esperado"]:
                    msg = (
                        "❌ Não foi possível determinar o período esperado da referência "
                        f"(mes/ano: {int(mes_selecionado):02d}/{int(ano_selecionado)})."
                    )
                    print(msg)
                    resultado["erro"] = msg
                    return resultado

                if not resultado["periodo_obtido"] and _capital_sem_movimento_confere(
                    texto_conteudo, mes_selecionado, ano_selecionado
                ):
                    print("ℹ️ Extrato de capital sem movimentação no período — gerando o PDF apenas com os saldos.")
                    resultado["periodo_obtido"] = resultado["periodo_esperado"]

                if not resultado["periodo_obtido"]:
                    msg = (
                        "❌ Não foi possível identificar o período no extrato da conta capital. "
                        "Verifique calendário e reprocese a conta."
                    )
                    print(msg)
                    resultado["erro"] = msg
                    return resultado

                if resultado["periodo_obtido"] != resultado["periodo_esperado"]:
                    msg = (
                        "❌ Período divergente no extrato da conta capital. "
                        f"Esperado: {resultado['periodo_esperado']} | "
                        f"Obtido: {resultado['periodo_obtido']}. "
                        "Verifique calendário e reprocese a conta."
                    )
                    print(msg)
                    resultado["erro"] = msg
                    return resultado

                html_texto = build_html_extrato_sicoob_capital(texto_conteudo)
                print("→ Conta capital: texto decodificado e convertido direto para HTML/PDF")
            else:
                dados_extrato = parse_extrato_sicoob_txt(texto_conteudo)
                resultado["periodo"] = dados_extrato.get("periodo", "")
                resultado["fallback_linhas"] = dados_extrato.get("linhas_fallback", [])[:]
                resultado["periodo_esperado"] = _mes_ano_esperado(mes_selecionado, ano_selecionado)
                resultado["periodo_obtido"] = _extrair_mes_ano_periodo_corrente(resultado["periodo"])

                if not resultado["periodo_esperado"]:
                    msg = (
                        "❌ Não foi possível determinar o período esperado da referência "
                        f"(mes/ano: {int(mes_selecionado):02d}/{int(ano_selecionado)})."
                    )
                    print(msg)
                    resultado["erro"] = msg
                    return resultado

                if not resultado["periodo_obtido"]:
                    msg = (
                        "❌ Não foi possível identificar o período no extrato da conta corrente. "
                        f"Período bruto lido: '{resultado['periodo'] or 'vazio'}'. "
                        "Verifique calendário e reprocese a conta."
                    )
                    print(msg)
                    resultado["erro"] = msg
                    return resultado

                if resultado["periodo_obtido"] != resultado["periodo_esperado"]:
                    msg = (
                        "❌ Período divergente no extrato da conta corrente. "
                        f"Esperado: {resultado['periodo_esperado']} | "
                        f"Obtido: {resultado['periodo_obtido']} (bruto: '{resultado['periodo']}'). "
                        "Verifique calendário e reprocese a conta."
                    )
                    print(msg)
                    resultado["erro"] = msg
                    return resultado

                html_texto = build_html_extrato_sicoob(dados_extrato, numero)
                tipos = {"credito": 0, "debito": 0, "saldo": 0}
                for mov in dados_extrato.get("movimentos", []):
                    tipo = mov.get("tipo")
                    if tipo in tipos:
                        tipos[tipo] += 1

                print(
                    "→ Parsing extrato: "
                    f"{len(dados_extrato.get('movimentos', []))} movimento(s), "
                    f"{len(dados_extrato.get('resumo', []))} item(ns) de resumo, "
                    f"{len(dados_extrato.get('linhas_fallback', []))} linha(s) em fallback"
                )
                print(
                    "→ Tipos: "
                    f"{tipos['credito']} crédito(s), "
                    f"{tipos['debito']} débito(s), "
                    f"{tipos['saldo']} saldo(s)"
                )

            pagina_tmp = page.context.new_page()
            try:
                pagina_tmp.set_content(html_texto, wait_until="load", timeout=20000)
                pagina_tmp.emulate_media(media="print")
                pdf_bytes = pagina_tmp.pdf(
                    format="A4",
                    landscape=False,
                    print_background=True,
                    margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"},
                    prefer_css_page_size=True
                )
            finally:
                pagina_tmp.close()

            print("→ PDF gerado a partir de texto")
        except PlaywrightTimeoutError as e:
            raise Exception(f"Timeout convertendo texto para PDF: {e}")
        except PlaywrightError as e:
            raise Exception(f"Erro Playwright convertendo texto para PDF: {e}")
        except Exception as e:
            raise Exception(f"Erro convertendo texto para PDF: {e}")

        # 12. Salvar PDF (seu código original mantido)
        ano_mov = f"{int(ano_selecionado)}"
        mes_mov = f"{int(mes_selecionado):02d}"

        ##BASE_DRIVE = Path.home() / "Desktop" / "TESTE_EXTRATOS"
        BASE_DRIVE = Path(base_drive) if base_drive else Path(r"H:\Drives compartilhados\Contábil")

        empresa_existente = encontrar_pasta_por_conta(
            BASE_DRIVE,
            numero,
            ano_mov,
            nome_empresa_limpo,
        )
        pasta_tipo_extrato = "Extratos Conta Capital" if tipo_extrato_norm == "capital" else "Extrato CC"
        if empresa_existente:
            pasta_destino = empresa_existente / ano_mov / "Banco" / "Sicoob" / numero / pasta_tipo_extrato
            print(f"📂 Pasta existente encontrada: {empresa_existente.name}")
        else:
            pasta_destino = BASE_DRIVE / nome_empresa_pasta / ano_mov / "Banco" / "Sicoob" / numero / pasta_tipo_extrato
            print(f"🏷️ Empresa (banco): {nome_empresa_limpo}")
            print(f"🏷️ Empresa (pasta nova): {nome_empresa_pasta}")
            print(f"📂 Criando nova pasta: {pasta_destino}")

        pasta_destino.mkdir(parents=True, exist_ok=True)

        nome_arquivo = f"{mes_mov}.pdf"
        caminho_arquivo = pasta_destino / nome_arquivo
        with open(caminho_arquivo, "wb") as f:
            f.write(pdf_bytes)
        print(f"📁 Usando raiz customizada: {BASE_DRIVE}")
        print(f"📄 PDF gerado e salvo em: {caminho_arquivo}")
        resultado["pdf_path"] = str(caminho_arquivo)

    except PlaywrightTimeoutError as e:
        msg = f"❌ Timeout na exportação/download da conta {numero}: {e}"
        print(msg)
        page.screenshot(path=f"erro_export_{numero}_{periodo_arquivo}.png")
        _forcar_limpeza_dom_modal(page)
        resultado["erro"] = msg
        return resultado
    except PlaywrightError as e:
        msg = f"❌ Erro Playwright na exportação/download da conta {numero}: {e}"
        print(msg)
        page.screenshot(path=f"erro_export_{numero}_{periodo_arquivo}.png")
        _forcar_limpeza_dom_modal(page)
        resultado["erro"] = msg
        return resultado
    except Exception as e:
        msg = f"❌ Erro inesperado na exportação/download da conta {numero}: {e}"
        print(msg)
        page.screenshot(path=f"erro_export_{numero}_{periodo_arquivo}.png")
        _forcar_limpeza_dom_modal(page)
        resultado["erro"] = msg
        return resultado

    # 13. Volta para lista - tenta fechar modal pendente antes de trocar conta
    # (somente no último período selecionado para esta conta - RF-03/RF-08).
    if ultimo_periodo:
        try:
            # 1. Em vez de ESC, clica no botão de fechar via código (não rouba foco)
            try:
                # Tenta clicar em qualquer botão de fechar ou ícone 'X' via dispatch
                page.locator("span.pi-times, .fechar, button[aria-label='Close']").first.dispatch_event("click")
                print("→ Modal fechado via evento")
            except PlaywrightTimeoutError as e:
                print(f"ℹ️ Timeout ao tentar fechar modal da conta {numero} (seguindo): {e}")
            except PlaywrightError as e:
                print(f"ℹ️ Erro Playwright ao tentar fechar modal da conta {numero} (seguindo): {e}")
            except Exception as e:
                print(f"ℹ️ Erro inesperado ao tentar fechar modal da conta {numero} (seguindo): {e}")
                pass
            # 2. Aguarda o overlay sumir (Verificação de DOM, não visual)
            overlay = page.locator("div.overlay.visivel")
            if overlay.count() > 0:
                overlay.wait_for(state="hidden", timeout=5000)

            # 3. Trocar conta via Dispatch (Seguro para multi-tarefa)
            trocar_conta = page.locator(SEL_TROCAR_CONTA).first

            # O dispatch_event funciona mesmo se a janela estiver minimizada
            trocar_conta.dispatch_event("click")

            page.wait_for_selector("h3:has-text('Lista de contas')", timeout=25000)
            print("→ Voltou para lista com sucesso")

        except PlaywrightTimeoutError as e:
            print(f"⚠️ Timeout ao voltar para lista da conta {numero} (provável modal/overlay): {e}")
            print("  → Continuando para próxima conta mesmo assim...")
        except PlaywrightError as e:
            print(f"⚠️ Erro Playwright ao voltar para lista da conta {numero} (provável modal/overlay): {e}")
            print("  → Continuando para próxima conta mesmo assim...")
        except Exception as e:
            print(f"⚠️ Erro inesperado ao voltar para lista da conta {numero} (provável modal/overlay): {e}")
            print("  → Continuando para próxima conta mesmo assim...")
    print(f"✅ Processo finalizado para {numero}")
    return resultado
