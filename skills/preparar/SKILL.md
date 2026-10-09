---
name: preparar
description: Confere e instala o que o plugin precisa no computador (Python, Playwright 1.63.0 e o Chromium 153 do robô). Use quando o usuário pedir /lid:preparar ou na primeira vez que usar o plugin.
user-invocable: true
---

# /lid:preparar

> Estado: esqueleto (F1). A verificação e a instalação serão implementadas na F5.

Faça uma vez por computador. Confira e, se faltar, instale, mostrando o progresso:

1. Python (ou `uv`).
2. `playwright==1.63.0` e as bibliotecas do robô.
3. O Chromium **153.0.8010.12** (cerca de 200 MB, é um download único). Precisa de internet e espaço em disco.
4. Se o robô SicoobBot estiver aberto, avise para fechá-lo.
5. Se um perfil de navegador existente foi usado por um Chromium mais novo que o do plugin, **não abra**: explique o motivo.

Se rede ou antivírus bloquearem o download, explique com clareza e oriente o usuário. Não use credenciais.
