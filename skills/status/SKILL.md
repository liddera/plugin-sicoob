---
name: status
description: Mostra o andamento da extração em curso (itens feitos, item atual, avisos e erros). Use quando o usuário pedir /lid:status ou perguntar como está a extração.
user-invocable: true
---

# /lid:status

> Estado: esqueleto (F1). Depende do servidor MCP (F4).

Consulte a execução atual e responda de forma curta, por exemplo:

> Conta 2/2 · extrato corrente · mês 08/2026 · 9 de 16 itens · 0 erros.

Inclua: itens concluídos, item em andamento, avisos e erros até agora. Se não houver execução em curso,
diga isso e sugira `/lid:login` ou `/lid:resultado`. Não mostre saldos nem movimentos.
