# lid — plugin Liddera para o Sicoob

Plugin do Claude Code (aba **Código** do Claude Desktop) que conduz a extração de extratos,
comprovantes e faturas do SicoobNet PJ. Produto **separado** do robô SicoobBot, sem tela: o Claude
é a interface. Reaproveita as **mesmas regras** do robô.

> Status: **F1, esqueleto** (v0.1.0). As skills descrevem o comportamento; o servidor MCP (F4) ainda não existe.

## Instalação
```
/plugin marketplace add liddera/plugin-sicoob
/plugin install lid@liddera-plugins
```

## Comandos
| Comando | Faz |
|---|---|
| `/lid:preparar` | Confere/instala Python, Playwright 1.63.0 e o Chromium 153 |
| `/lid:login` | Abre o navegador, aguarda o QR e monta o pedido (pasta, contas, documentos, meses) |
| `/lid:extrair` | Executa a extração e acompanha |
| `/lid:status` | Andamento da execução |
| `/lid:resultado` | Relatório final |
| `/lid:cancelar` | Para ao fim do item atual |

## Regras fechadas
- Navegador do robô: **Chrome for Testing 153.0.8010.12** (Playwright 1.63.0), visível; perfil `%LOCALAPPDATA%\SicoobBot\perfil_sicoobnet_persistente`.
- Login por QR e cadastro de dispositivo: **manuais**. Nunca fechar o navegador logado.
- Pasta de destino: informada **só no `/lid:login`**.
- `MM.pdf` existente é substituído (marcado "substituído" no relatório).
- Controle `controle_execucao_contas.json` do robô: **só leitura** na primeira versão.
- Código do robô: copiado para `vendor/` com script de sincronização.
- Só consulta e exporta; domínio `ib.sicoob.com.br`; saldos e movimentos não voltam ao Claude.

## Estrutura
```
.claude-plugin/plugin.json        nome "lid"
.claude-plugin/marketplace.json   marketplace "liddera-plugins"
skills/{login,extrair,status,resultado,preparar,cancelar}/SKILL.md
docs/                             plano e decisões
```
Fases: F1 esqueleto (esta) · F2 vendor · F3 núcleo · F4 servidor MCP · F5 preparar e skills finais · F6 gravação do controle · F7 distribuição.
