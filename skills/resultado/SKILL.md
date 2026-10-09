---
name: resultado
description: Mostra o relatório final da última extração (conta, empresa, documento, mês, resultado e arquivo). Use quando o usuário pedir /lid:resultado ou quiser ver o que foi gerado.
user-invocable: true
allowed-tools:
  - mcp__plugin_lid_sicoob__resultados
  - mcp__plugin_lid_sicoob__status
---

# /lid:resultado

Chame `resultados` e apresente a tabela que ela devolve, sem alterar os dados:

| Conta | Empresa | Documento | Mês | Resultado | Arquivo |
|---|---|---|---|---|---|

Significado dos resultados:
- ✅ gerado, ✅ substituído (o arquivo já existia e foi trocado), ✅ sem movimento (o PDF traz só os saldos, como o portal entrega);
- ⚠️ aviso: conta sem cartão ou mês sem comprovantes. **Não é erro.**
- ❌ erro, com o motivo; ⏸️ não executado (a execução foi cancelada ou interrompida).

Termine com o total de certos, avisos e erros. Se houver ❌, ofereça **refazer só esses itens**; se houver ⏸️, ofereça
**continuar de onde parou** (ambos pelo `/lid:extrair`).

Nunca mostre saldos nem movimentos: apenas status e caminhos de arquivo.
