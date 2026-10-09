---
name: extrair
description: Executa a extração confirmada no /lid:login (extratos, comprovantes e faturas do Sicoob) e acompanha o andamento. Use quando o usuário pedir /lid:extrair, mandar rodar, refazer os itens com erro ou continuar de onde parou.
user-invocable: true
allowed-tools:
  - mcp__plugin_lid_sicoob__login_status
  - mcp__plugin_lid_sicoob__validar_pedido
  - mcp__plugin_lid_sicoob__status
  - mcp__plugin_lid_sicoob__resultados
  - mcp__plugin_lid_sicoob__atalho_contas
  - mcp__plugin_lid_sicoob__historico
---

# /lid:extrair

Executa o pedido já montado no `/lid:login`. A ferramenta `extrair` grava arquivos no disco, então ela **pede
a aprovação do usuário**: só chame depois de ele ter confirmado o resumo.

## Antes de começar
1. Confirme que há login ativo com `login_status` (`login` = `ok`). Se não houver, peça `/lid:login`.
2. Se o usuário não montou um pedido nesta conversa, volte ao `/lid:login` para montá-lo. Refazer e continuar não
   precisam de pedido novo.

## Iniciar
- **Pedido novo:** chame `extrair` com `pasta`, `contas`, `documentos`, `meses` e `confirmado: true`.
- **Só o que falta:** o mesmo pedido com `apenas_pendentes: true` roda apenas os itens que nunca tiveram sucesso no histórico do plugin
  (pula o que já foi feito, inclusive de outros dias). `validar_pedido` mostra "só o que falta: N de M itens"; se não sobrar nada, ele avisa.
- **Refazer os itens com erro da última execução:** `extrair` com `refazer: "erro"` e `confirmado: true`.
- **Continuar de onde parou** (itens que não rodaram: cancelamento ou navegador fechado): `extrair` com `refazer: "continuar"`.
- O resultado traz o número da execução e o total de itens. A execução roda em segundo plano (cada item leva de 20 a 70 s).

## Regras que a execução segue (as do robô SicoobBot)
- Ordem: todos os meses do 1º documento, depois os do 2º.
- Só o primeiro item de cada conta entra pela lista de contas; os seguintes reaproveitam a conta; só o último volta à lista.
- 2 tentativas por item e até 3 recuperações por conta; depois, desiste dos itens restantes da conta.
- **Aviso não é erro:** conta sem cartão e mês sem comprovantes não são repetidos.
- Capital sem movimento gera o PDF só com os saldos. Um `MM.pdf` que já existe é substituído e marcado no relatório.
- Se o navegador for fechado, a execução é **interrompida** e os itens restantes ficam "não executados" (não viram erro).

## Acompanhar
Quando o usuário perguntar, use `status` (veja `/lid:status`). Não fique consultando sem necessidade: avise quantos itens faltam.

## Ao terminar
Mostre o relatório com `resultados` (veja `/lid:resultado`) e, se houver erros, ofereça **refazer só esses itens**.
Se a execução foi interrompida, explique o motivo e ofereça `/lid:login` seguido de "continuar".

## Regras
- Nunca mostre saldos nem movimentos.
- Nunca feche o navegador logado.
