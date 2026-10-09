---
name: preparar
description: Confere e instala o que o plugin precisa no computador (ambiente Python, Playwright 1.63.0 e o Chromium 153 do robô). Use quando o usuário pedir /lid:preparar, na primeira vez que usar o plugin, ou quando o plugin disser que o ambiente não está pronto.
user-invocable: true
allowed-tools:
  - mcp__plugin_lid_sicoob__preparar_status
  - mcp__plugin_lid_sicoob__diagnostico
---

# /lid:preparar

Faça uma vez por computador (e de novo se o plugin avisar que o ambiente não está pronto).

> **Se as ferramentas do servidor `sicoob` não existirem** (o servidor não conseguiu iniciar), o motivo mais comum é o
> **Python não estar instalado ou não estar no PATH** (o plugin chama o comando `python`). Oriente: instalar o Python 3.10 ou mais
> novo em python.org marcando "Add python.exe to PATH", conferir com `python --version` no terminal, e **reiniciar o Claude**.

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

Nunca use credenciais. Não é preciso ter o Chrome instalado: o plugin usa o próprio Chromium.
