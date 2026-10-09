---
name: status
description: Mostra o andamento da extração em curso (itens feitos, item atual, avisos e erros). Use quando o usuário pedir /lid:status ou perguntar como está a extração.
user-invocable: true
allowed-tools:
  - mcp__plugin_lid_sicoob__status
  - mcp__plugin_lid_sicoob__login_status
---

# /lid:status

Chame `status` e responda de forma curta, por exemplo:

> Conta 109.317-7 · extrato corrente · 09/2026 · 9 de 16 itens · 0 erros · 1 aviso.

Use os campos: `itens_feitos` / `itens_total`, `item_atual` (conta, documento, mês, tentativa), `ok`, `avisos`, `erros`,
`nao_executados` e `status` (`running`, `finished`, `cancelled`, `interrompida`).

- `status: sem_execucao`: diga que não há execução e sugira `/lid:login`.
- `interrompida`: explique que o navegador foi fechado ou caiu, que os itens restantes não foram executados, e ofereça
  `/lid:login` seguido de "continuar de onde parou". Se precisar investigar, o plugin grava um log; use `diagnostico`.
- `cancelled`: mostre o que foi concluído e ofereça "continuar".

Não mostre saldos nem movimentos.
