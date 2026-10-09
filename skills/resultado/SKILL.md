---
name: resultado
description: Mostra o relatório final da última extração (conta, empresa, documento, mês, resultado e arquivo). Use quando o usuário pedir /lid:resultado ou quiser ver o que foi gerado.
user-invocable: true
---

# /lid:resultado

> Estado: esqueleto (F1). Depende do servidor MCP (F4).

Mostre uma tabela, no mesmo estilo do robô SicoobBot:

| Conta | Empresa | Documento | Mês | Resultado | Arquivo |
|---|---|---|---|---|---|

Resultados possíveis: ✅ gerado, ✅ substituído, ✅ sem movimento (PDF só de saldos), ⚠️ aviso (sem cartão, sem comprovantes)
e ❌ erro com o motivo. Termine com o total de certos, avisos e erros e, se houver erro, ofereça refazer só esses itens.

Nunca mostre saldos nem movimentos: apenas status e caminhos de arquivo.
