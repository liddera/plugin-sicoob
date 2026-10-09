---
name: preparar
description: Deixa o computador pronto para o plugin: confere o Python e instala o ambiente (Playwright 1.63.0 e o navegador Chromium 153). Use quando o usuário pedir /lid:preparar, na primeira vez que usar o plugin, quando o plugin disser que o ambiente não está pronto, ou quando as ferramentas do plugin não existirem (Python ausente).
user-invocable: true
allowed-tools:
  - mcp__plugin_lid_sicoob__preparar_status
  - mcp__plugin_lid_sicoob__diagnostico
---

# /lid:preparar

Faça uma vez por computador (e de novo se o plugin avisar que o ambiente não está pronto).

## A. As ferramentas do servidor `sicoob` existem?
Se você consegue chamar `preparar_status`, vá para a seção **B**.

Se **não existem** (o servidor do plugin não conseguiu iniciar), o motivo quase sempre é o **Python ausente ou fora do PATH**:
o servidor do plugin é um programa Python, então sem Python ele não liga, e nem este comando consegue instalar nada.
Siga estes passos, **sem instalar nada antes de o usuário autorizar**:

1. **Descubra se há Python.** Rode `python --version` no terminal. Se der erro, ou abrir a Microsoft Store, ou disser que não encontrou,
   considere que **não há Python**. Tente também `py -3 --version`.
2. **Há Python 3.10 ou mais novo**, mas o servidor não subiu: o Claude foi aberto antes de o Python estar no PATH, ou a falha
   ficou em cache (cerca de 15 minutos). Peça para **fechar e abrir o Claude** e rodar `/lid:preparar` de novo.
   Se for menor que 3.10, trate como ausente (precisa de 3.10 ou mais novo).
3. **Não há Python (Windows):**
   1. Rode `winget --version`. Se existir, **ofereça instalar**, explicando em linguagem simples: será instalado o Python 3.12 oficial
      (pequeno, uns 25 MB, precisa de internet) e o Windows pode pedir uma confirmação.
   2. **Só depois de o usuário dizer que sim**, rode:
      `winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements`
   3. Não tente contornar bloqueios (administrador, política da empresa): se der erro, mostre a mensagem e use o plano B.
   4. **Plano B (sem `winget` ou com erro):** oriente instalar em **python.org** (versão 3.10 ou mais nova) **marcando "Add python.exe to PATH"**.
4. **Não há Python (Linux ou macOS):** não use `winget`. Oriente instalar pelo gerenciador do sistema (por exemplo, `sudo apt install python3 python-is-python3`)
   e confirme que o comando `python` existe. Não rode comandos com `sudo` sem o usuário pedir.
5. **Depois de instalar:** o PATH só vale para programas abertos *depois*. Peça para o usuário **fechar e abrir o Claude de novo**,
   conferir com `python --version` em um terminal novo (deve mostrar 3.10 ou mais) e rodar `/lid:preparar` outra vez.

Nunca use credenciais e nunca instale outra coisa além do Python.

## B. Preparar o ambiente
1. Chame `preparar_status`. Se `ambiente.pronto` for `true`, diga que está tudo pronto e pare.
2. Se não estiver, mostre os `motivos` em linguagem simples e explique o que será feito:
   cria um ambiente Python próprio do plugin, instala o Playwright 1.63.0 e baixa o navegador Chromium 153.0.8010.12
   (cerca de 200 MB, download único; precisa de internet).
3. Chame `preparar` (ele pede a aprovação do usuário, porque instala programas). Ele roda em segundo plano.
4. Consulte `preparar_status` a cada poucos segundos e informe a etapa (`preparo.etapa` / `preparo.mensagem`)
   até `preparo.estado` ser `concluido` ou `erro`.
5. Se `concluido`: diga que pode usar `/lid:login`. Se `erro`: mostre a mensagem e orientações simples:
   - Python 3.10 ou mais novo é necessário (`python --version`);
   - rede ou antivírus podem bloquear o download: tente de novo ou peça apoio de TI;
   - para investigar, use `diagnostico` (mostra as últimas linhas do log, sem dados bancários).

Não é preciso ter o Chrome instalado: o plugin usa o próprio Chromium.
