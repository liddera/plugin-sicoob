"""Configuração do plugin para o código do robô copiado em vendor/sicoobbot.

ESTE ARQUIVO É DO PLUGIN (não vem do robô e não é sobrescrito por scripts/sync_vendor.py).
Os módulos copiados fazem `from config import ...`; aqui ficam só os nomes que eles usam,
apontando para os caminhos do plugin (iguais aos do robô, para compartilhar o perfil).
"""
import os

# Igual ao robô: o Chromium fica dentro do pacote do Playwright (PLAYWRIGHT_BROWSERS_PATH=0).
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

from core import paths  # noqa: E402  (o worker coloca a raiz do plugin no sys.path)

BASE_PATH = paths.home_dir()
USER_DATA_DIR = paths.perfil_dir()
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_PATH = BASE_PATH / "checkpoint_sicoob.json"
CONTROLE_EXECUCAO_PATH = paths.controle_path()

HEADLESS = False
TEMPO_MAXIMO_LOGIN = 500  # segundos esperando o login por QR (igual ao robô)
URL_SICOOB = paths.URL_SICOOB

TENTATIVAS_MAX_PERIODO = 2  # RF-09a do robô
RECOVERY_MAX_CONTA = 3      # RF-09b do robô
