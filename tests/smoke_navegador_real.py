"""Teste manual (NÃO é rodado pelo unittest): servidor MCP -> worker REAL -> Chromium de verdade, sem login.
Abre uma janela do navegador por alguns segundos, com perfil temporário. Uso:
  python tests/smoke_navegador_real.py <python-com-playwright>
"""
import json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_integracao import Cliente, RAIZ

py = sys.argv[1]
home = tempfile.mkdtemp(prefix="lid_smoke_")
c = Cliente(home, com_worker=False, fake_env={"LID_WORKER_CMD": json.dumps([py, str(RAIZ / "worker" / "main.py")])})
c.req("initialize", {"protocolVersion": "2025-06-18"})
log = Path(home) / "lid" / "logs" / "lid.log"

def chromes():
    out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
    return [int(l.split()[0]) for l in out.splitlines() if home in l and "chrome" in l]

def eventos():
    return log.read_text(encoding="utf-8") if log.exists() else ""

try:
    erro, d = c.tool_json("conectar", timeout=200)
    print("conectar        ->", "ERRO" if erro else d.get("login"), "|", d if erro else d.get("mensagem"))
    time.sleep(6)
    _, d = c.tool_json("login_status")
    print("login_status    ->", d["navegador"], d["login"])
    print("processos chrome:", len(chromes()), "| evento navegador_aberto:", "EVENTO navegador_aberto" in eventos())
    # simula queda: mata os processos do navegador
    for pid in chromes():
        try: os.kill(pid, signal.SIGKILL)
        except ProcessLookupError: pass
    time.sleep(6)
    ev = eventos()
    print("eventos de queda registrados:", [n for n in ("pagina_fechada", "contexto_fechado", "navegador_desconectado", "pagina_travou") if f"EVENTO {n}" in ev])
    _, d = c.tool_json("login_status")
    print("login_status    ->", d["navegador"], d["login"], "|", d["mensagem"])
    erro, d = c.tool_json("conectar", timeout=200)
    print("conectar de novo->", "ERRO" if erro else d.get("login"), "|", d if erro else d.get("mensagem"))
    time.sleep(5)
    print("processos chrome depois de reabrir:", len(chromes()))
finally:
    c.fechar()
    time.sleep(3)
    print("processos chrome depois de encerrar o servidor:", len(chromes()))
