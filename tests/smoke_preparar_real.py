"""Teste manual (NÃO é rodado pelo unittest): máquina "limpa". Usa pasta temporária e baixa o Chromium de verdade (~200 MB).
Fluxo: preparar (venv + playwright 1.63.0 + chromium 153) -> conectar com o ambiente preparado -> derruba -> reabre."""
import json, os, subprocess, sys, tempfile, time, signal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_integracao import Cliente

home = tempfile.mkdtemp(prefix="lid_prep_")
c = Cliente(home, com_worker=False)           # sem worker de teste: tudo pelo ambiente real
c.req("initialize", {"protocolVersion": "2025-06-18"})
def chromes():
    out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
    return [int(l.split()[0]) for l in out.splitlines() if home in l and "chrome" in l]
try:
    _, d = c.tool_json("preparar_status")
    print("antes: pronto =", d["ambiente"]["pronto"], "|", d["ambiente"]["motivos"])
    erro, txt = c.tool("conectar"); print("conectar sem preparar -> erro =", erro, "|", txt[:90])
    print("preparar ->", c.tool_json("preparar")[1])
    t0 = time.time()
    while time.time() - t0 < 900:
        _, d = c.tool_json("preparar_status")
        if d["preparo"]["estado"] in ("concluido", "erro"):
            break
        time.sleep(5)
    print(f"preparo: {d['preparo']['estado']} em {int(time.time()-t0)}s | {d['preparo']['mensagem']}")
    print("ambiente:", {k: d["ambiente"][k] for k in ("pronto", "playwright", "chromium_versao", "chromium_instalado")})
    if d["ambiente"]["pronto"]:
        erro, d = c.tool_json("conectar", timeout=200)
        print("conectar ->", "ERRO" if erro else d.get("login"), "|", d if erro else d.get("mensagem"))
        time.sleep(6)
        _, d = c.tool_json("login_status"); print("login_status ->", d["navegador"], d["login"])
        _, dg = c.tool_json("diagnostico", {"linhas": 6}); print("chromium do worker (log):", [l for l in dg["ultimas_linhas_do_log"] if "navegador_aberto" in l])
        print("processos chrome:", len(chromes()))
        for pid in chromes():
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
        time.sleep(6)
        _, d = c.tool_json("login_status"); print("após queda ->", d["navegador"], d["login"])
finally:
    c.fechar(); time.sleep(3)
    print("processos chrome ao final:", len(chromes()))
