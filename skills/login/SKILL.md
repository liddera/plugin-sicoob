---
name: login
description: Abre o navegador do Sicoob, aguarda o login por QR e monta o pedido de extração (pasta, contas, documentos e meses). Use quando o usuário pedir /lid:login, quiser acessar o SicoobNet ou começar uma extração.
user-invocable: true
allowed-tools:
  - mcp__plugin_lid_sicoob__conectar
  - mcp__plugin_lid_sicoob__login_status
  - mcp__plugin_lid_sicoob__listar_contas
  - mcp__plugin_lid_sicoob__buscar_conta
  - mcp__plugin_lid_sicoob__validar_pedido
  - mcp__plugin_lid_sicoob__atalho_contas
  - mcp__plugin_lid_sicoob__historico
---

# /lid:login

Primeiro passo de toda extração. **O login é sempre manual**: nunca digite credenciais e nunca cadastre o
dispositivo no lugar do usuário. Nunca peça para fechar o navegador logado, e nunca feche-o.

> **Se as ferramentas do servidor `sicoob` não existirem** (o servidor não conseguiu iniciar), a causa mais comum é o
> **Python não estar instalado ou não estar no PATH** (o plugin chama o comando `python`). Oriente: instalar o Python 3.10 ou mais
> novo em python.org marcando "Add python.exe to PATH", conferir com `python --version` no terminal, e **reiniciar o Claude**.
> Depois rode `/lid:preparar`.

## 1. Abrir o navegador e aguardar o login
1. Chame `conectar`. Ele abre o navegador do robô na tela de login do SicoobNet.
   - Se responder que o ambiente não está pronto, oriente a rodar `/lid:preparar` e pare.
   - Se disser que o perfil está em uso, peça para fechar o robô SicoobBot (um perfil só abre em um programa por vez).
   - Se disser que o perfil é de um navegador mais novo, explique que é preciso atualizar o plugin e pare.
2. Diga ao usuário: **escaneie o QR code no navegador que abriu** (e cadastre o dispositivo, se o Sicoob pedir)
   e **não feche a janela**.
3. Consulte `login_status` a cada poucos segundos até `login` ser `ok` (a espera pode chegar a uns 8 minutos).
   - `aguardando` ou `carregando_contas`: continue esperando e avise o usuário.
   - `erro`: mostre a `mensagem` e ofereça rodar `/lid:login` de novo.
4. Quando `login` for `ok`, informe quantas contas foram carregadas. Se o navegador já estava logado, não reabra.

## 2. Montar o pedido, nesta ordem
Pergunte uma coisa de cada vez (ou aceite tudo em uma frase) e converta para os campos da ferramenta.

1. **Pasta de destino**: sugira `H:\Drives compartilhados\Contábil` (padrão do robô) e pergunte "usar essa ou outra?".
2. **Contas**:
   - números, com ou sem pontuação (`47.041-4`, `470414`);
   - nome da empresa: use `buscar_conta` e mostre as contas encontradas para o usuário escolher;
   - "todas": peça confirmação extra;
   - "as com erro": use `atalho_contas` com `modo: "com_erro"` (itens cujo último resultado foi erro, pelo histórico do plugin) e mostre a lista;
   - "as pendentes": primeiro defina documentos e meses, depois use `atalho_contas` com `modo: "pendentes"`, `documentos` e `meses`
     (o que nunca teve sucesso); o robô tem um controle próprio, consultável com `fonte: "robo"` (somente leitura);
   - uma lista colada: um número por linha.
3. **Documentos**: extrato conta corrente, conta capital, comprovantes, fatura de cartão (um, vários ou "todos").
4. **Meses**: `06/2026`, `06/2026 a 09/2026`, "junho a setembro de 2026", "mês passado" (calcule e mostre as datas).
   Mês inteiro por padrão. Meses futuros são recusados.
5. Chame **`validar_pedido`** com `pasta`, `contas`, `documentos` e `meses`.
   - Se houver `problemas`, mostre-os com clareza (conta não encontrada com sugestões, mês futuro, pasta inacessível...) e corrija com o usuário.
   - Mostre os `avisos` (por exemplo, a pasta não tem pastas de empresa) e quantas pastas de empresa foram encontradas, com os exemplos.
6. Apresente o **resumo para confirmar**: pasta, contas, documentos, meses e o total de itens (contas × documentos × meses).

A extração em si é feita por `/lid:extrair`, depois do "sim" do usuário.

## Regras
- Nunca mostre saldos nem movimentos: apenas status, caminhos e nomes de empresa.
- Não rode `/lid:extrair` sem a confirmação explícita do resumo.
