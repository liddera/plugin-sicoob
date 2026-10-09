---
name: diagnostico
description: Mostra o estado do plugin para suporte (versões, caminhos, ambiente e as últimas linhas do log, sem dados bancários). Use quando o usuário pedir /lid:diagnostico, quando algo falhar ou quando o navegador fechar sozinho.
user-invocable: true
allowed-tools:
  - mcp__plugin_lid_sicoob__diagnostico
  - mcp__plugin_lid_sicoob__login_status
  - mcp__plugin_lid_sicoob__status
  - mcp__plugin_lid_sicoob__preparar_status
  - mcp__plugin_lid_sicoob__historico
---

# /lid:diagnostico

1. Chame `diagnostico` (aceita `linhas` para ver mais do log, até 200) e `login_status`.
2. Resuma em linguagem simples: versão do plugin, se o ambiente está pronto, o estado do navegador e do login.
3. Leia as últimas linhas do log e destaque o que importa:
   - `pagina_travou`: o navegador travou (indício de falta de memória);
   - `pagina_fechada`, `contexto_fechado`, `navegador_desconectado`: o navegador foi fechado ou caiu (por alguém ou por outro programa);
   - `perfil_bloqueado`: o perfil está em uso (robô aberto) ou é de um Chromium mais novo;
   - `login_timeout`, `login_abortado`: o login não foi concluído a tempo, ou o navegador foi fechado antes;
   - `execucao_inicio`, `execucao_fim`, `execucao_falha`: andamento das extrações.
4. Se fizer sentido, use `historico` com `consulta: "resumo"` (contagens do histórico do plugin e quantas linhas foram ignoradas por estarem cortadas).
5. Diga o caminho do log (`%LOCALAPPDATA%\SicoobBot\lid\logs\lid.log`) para o usuário anexar ao pedir ajuda.

O log **não** contém saldos nem movimentos. Nunca peça nem mostre credenciais.
