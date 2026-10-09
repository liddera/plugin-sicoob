---
name: cancelar
description: Cancela a extração em curso ao fim do item atual. Use quando o usuário pedir /lid:cancelar, quiser parar ou interromper a extração.
user-invocable: true
allowed-tools:
  - mcp__plugin_lid_sicoob__cancelar
  - mcp__plugin_lid_sicoob__status
---

# /lid:cancelar

1. Chame `cancelar`. O cancelamento vale **ao fim do item em andamento**, para não deixar drawer, diálogo ou arquivo pela metade.
2. **Não feche o navegador logado.**
3. Consulte `status` até `status` ser `cancelled` e mostre o que foi concluído (`ok`, `avisos`, `erros`, `nao_executados`).
4. Ofereça "continuar de onde parou" (`/lid:extrair` com `refazer: "continuar"`) quando o usuário quiser retomar.

Se a resposta disser que não há extração em andamento, informe isso.
