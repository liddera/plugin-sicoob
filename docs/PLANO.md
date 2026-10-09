# Plano e decisões do plugin `lid`

## Decisões fechadas
| Tema | Decisão |
|---|---|
| Nome | Plugin `lid`; comandos `/lid:login`, `/lid:extrair`, `/lid:status`, `/lid:resultado`, `/lid:preparar`, `/lid:cancelar` |
| Onde roda | Claude Desktop, aba **Código** (executa no computador do usuário; servidor MCP local) |
| Navegador | O do robô: Chrome for Testing **153.0.8010.12** (Playwright 1.63.0), visível, perfil `%LOCALAPPDATA%\SicoobBot\perfil_sicoobnet_persistente` (compartilhado com o robô) |
| Login | Sempre manual (QR e cadastro de dispositivo). Nunca fechar o navegador logado |
| Pasta de destino | Informada **só no `/lid:login`** (padrão `H:\Drives compartilhados\Contábil`) |
| Contas/documentos/meses | Por conversa em linguagem normal, com resumo para confirmar antes de executar |
| Arquivo já existente | Sobrescrever como o robô, marcando "substituído" |
| Histórico | **Próprio do plugin** (JSON Lines, um registro por item concluído, em `%LOCALAPPDATA%\SicoobBot\lid\historico`); o `controle_execucao_contas.json` do robô fica só para consulta (`fonte="robo"`). Substitui a antiga F6 (gravar no arquivo do robô) |
| Código do robô | Copiado para `vendor/` (plugin independente), com `scripts/sync_vendor.py` |
| Atalhos | "pendentes", "com erro", "só o que falta" (`apenas_pendentes`), "refazer erros", "continuar de onde parou"; pendente = nunca teve sucesso; aviso fecha o item, exceto no mês corrente |
| Privacidade | Saldos e movimentos nunca voltam ao Claude |

## Diferenças deliberadas em relação ao robô
1. Aviso (sem cartão, sem comprovantes) **não é erro** e não repete.
2. Navegador fechado **interrompe** a execução: itens restantes "não executados", não "erro definitivo".
3. Capital sem movimentação gera o PDF com os saldos (já está no robô, commit 121c927).

## Fases
F1 esqueleto ✅ · F2 vendor ✅ · F3 núcleo ✅ · F4 servidor MCP + worker ✅ · F5 preparar e skills ✅ ·
F6 histórico próprio ✅ · F7 diagnóstico de seletores do portal ⏳ (o `/lid:diagnostico` de suporte já existe)

## Pendências conhecidas
- Teste com login real (exige o QR). Persistência do cadastro do dispositivo.
- Instalação pelo marketplace e uso em Windows; comando `python` no PATH da equipe.
- Causa da queda do navegador no Windows de um usuário do robô (o plugin registra os eventos para descobrir).
- `tools/auto_inspecao.py` do robô ainda navega pelo layout antigo do portal.
