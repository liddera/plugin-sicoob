from config import USER_DATA_DIR
import os

def iniciar_navegador(p, headless=False):
    """
    Configura e lança o navegador Chromium com perfil persistente.
    
    Parâmetros:
        p: Instância de sync_playwright
        headless: True = invisível (headless), False = visível (com janela)
    
    Retorna:
        context, page
    """
    print(f"🌐 Configurando navegador (headless={headless})...")

    # Opt-in: SICOOB_ATTACH_PORT=9222 reaproveita um navegador JÁ aberto e logado
    # (iniciado com SICOOB_DEBUG_PORT), em vez de abrir outro e pedir o QR de novo.
    attach_port = os.getenv("SICOOB_ATTACH_PORT")
    if attach_port:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{attach_port}")
        context = browser.contexts[0]
        page = next((pg for pg in context.pages if "sicoob" in pg.url), None) or context.pages[0]
        print(f"✅ Anexado ao navegador existente (porta {attach_port}): {page.url}")
        return context, page

    # Garante que a pasta do perfil existe
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)
        print(f"   → Pasta de perfil criada: {USER_DATA_DIR}")

    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
    ]

    # Opt-in: SICOOB_DEBUG_PORT=9222 expõe CDP para inspeção do DOM (tools/dump_dom.py)
    debug_port = os.getenv("SICOOB_DEBUG_PORT")
    if debug_port:
        args.append(f"--remote-debugging-port={debug_port}")
        print(f"   → Porta de depuração CDP ativa: {debug_port}")

    context = p.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
        accept_downloads=True,
        args=args,
        ignore_default_args=["--enable-automation", "--disable-extensions"],
        viewport=None,
    )

    page = context.new_page()

    # Anti-detecção
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    print("✅ Navegador inicializado e pronto para uso.")
    return context, page