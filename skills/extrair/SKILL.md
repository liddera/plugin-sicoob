---
name: extrair
description: Executa a extração confirmada no /lid:login (extratos, comprovantes e faturas do Sicoob) e acompanha o andamento. Use quando o usuário pedir /lid:extrair, mandar rodar ou refazer os itens com erro.
user-invocable: true
---

# /lid:extrair

> Estado: esqueleto (F1). Depende do servidor MCP (F4).

1. Exija um login ativo e um pedido confirmado. Se faltar, peça `/lid:login` antes.
2. Valide o pedido de novo (conta existe, documento válido, mês não é futuro, pasta gravável).
3. Inicie a execução e devolva o número dela. A execução roda em segundo plano; cada item leva de 20 a 70 s.
4. Regras de execução (as do robô SicoobBot):
   - ordem: todos os meses do 1º documento, depois os do 2º;
   - só o primeiro item da conta entra pela lista de contas; os seguintes reaproveitam a conta; só o último volta à lista;
   - 2 tentativas por item e até 3 recuperações por conta;
   - antes de cada item, fechar drawers, diálogos e popups abertos;
   - conta sem cartão e mês sem comprovantes são **avisos**, não erros; capital sem movimento gera PDF só com os saldos;
   - arquivo `MM.pdf` já existente é substituído e marcado como "substituído" no relatório.
5. Informe o andamento quando o usuário perguntar (veja `/lid:status`).
6. Ao terminar, mostre o relatório (veja `/lid:resultado`) e ofereça **refazer só os itens com erro**.

Atalhos aceitos nas contas: "as pendentes", "as com erro" e "continuar de onde parou" (leitura do
`controle_execucao_contas.json` do robô, sem gravar na primeira versão).

Nunca devolva saldos nem movimentos na conversa.
