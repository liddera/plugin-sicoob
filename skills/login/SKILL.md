---
name: login
description: Abre o navegador do Sicoob, aguarda o login por QR e monta o pedido de extração (pasta, contas, documentos e meses). Use quando o usuário pedir /lid:login, quiser acessar o SicoobNet ou começar uma extração.
user-invocable: true
---

# /lid:login

Primeiro passo de toda extração. **O login é sempre manual**: nunca digite credenciais e nunca
cadastre dispositivo no lugar do usuário.

> Estado: esqueleto (F1). As ferramentas do servidor MCP ainda não existem (F4).

## 1. Abrir e aguardar o login
1. Se o robô SicoobBot estiver aberto, peça ao usuário para fechá-lo (um perfil de navegador só abre em um processo por vez).
2. Abra o navegador do robô, na tela de login do SicoobNet, com o perfil persistente `%LOCALAPPDATA%\SicoobBot`.
3. Diga ao usuário para **escanear o QR code** (e cadastrar o dispositivo, se o Sicoob pedir) e **não fechar a janela**. Nunca feche o navegador logado.
4. Aguarde a confirmação de login. Se o navegador já estiver logado, não reabra: siga para o passo 2.
5. Informe quantas contas foram carregadas.

## 2. Montar o pedido, nesta ordem
1. **Pasta de destino**: mostre o padrão `H:\Drives compartilhados\Contábil` e pergunte "usar essa ou outra?".
   Valide que existe, que dá para gravar e que parece a raiz certa (mostre quantas pastas de empresa há e 2 ou 3 nomes).
2. **Contas**: números (com ou sem pontuação), nome da empresa, "todas" (peça confirmação extra), lista colada,
   "as pendentes" ou "as com erro". Recuse conta que não esteja na lista e sugira as parecidas.
3. **Documentos**: extrato conta corrente, conta capital, comprovantes, fatura de cartão (um, vários ou todos).
4. **Meses**: `06/2026`, `06/2026 a 09/2026`, "junho a setembro". Mês inteiro por padrão; recuse meses futuros.
   Intervalo de dias é opcional.
5. **Resumo para confirmar**, com a pasta, as contas, os documentos, os meses e o total de itens (contas × documentos × meses).

A extração em si é feita por `/lid:extrair`, depois da confirmação.

Nunca devolva saldos nem movimentos na conversa: apenas status e caminhos de arquivo.
