# lid — plugin Liddera para o Sicoob

Plugin do **Claude Code** (aba **Código** do Claude Desktop) que conduz a extração de **extratos,
comprovantes e faturas de cartão** do SicoobNet PJ para várias contas e salva os PDFs na estrutura de
pastas da contabilidade.

É um produto **separado** do robô SicoobBot (`automacoes`): não tem tela, o Claude conduz por conversa.
O código que fala com o portal e as regras de pasta/nome/período são **os do robô**, copiados em `vendor/`.

## Status (v0.2.0)

Todas as partes foram construídas e testadas **sem o portal**; a parte que depende de login por QR **ainda não foi
testada com o Sicoob real**. Veja "O que foi e o que não foi verificado".

| Fase | Entrega | Situação |
|---|---|---|
| F1 | Esqueleto no padrão oficial (manifesto, marketplace, 6 skills) | ✅ |
| F2 | Código do robô em `vendor/` com script de sincronização e `VENDOR.json` | ✅ |
| F3 | Núcleo: pedido, runner, controle (só leitura), proteção do perfil, log, resultado | ✅ 37 testes |
| F4 | Servidor MCP + worker (navegador isolado) | ✅ 9 testes de integração |
| F5 | `/lid:preparar` (ambiente Python + Playwright + Chromium) e skills finais | ✅ testado do zero |
| F6 | Gravar no `controle_execucao_contas.json` (com backup) | ⏳ a fazer (hoje só lê) |
| F7 | Diagnóstico de seletores quando o portal mudar, guia de instalação | ⏳ a fazer |

## Requisitos
- **Windows**, **Claude Desktop** na aba **Código** (ou Claude Code).
- **Python 3.10 ou mais novo com o comando `python` no PATH** (python.org, marcando "Add python.exe to PATH"). Confira com `python --version`.
- Acesso ao SicoobNet PJ e ao **celular com o app do Sicoob** (login por QR code).
- Internet e ≈ 400 MB livres na primeira vez (ambiente Python + Chromium).
- O robô **SicoobBot fechado** durante o uso (os dois usam o mesmo perfil de navegador).
- Acesso de gravação à pasta de destino (por exemplo `H:\Drives compartilhados\Contábil`).

## Instalação
Na aba Código do Claude Desktop (precisa ter acesso de leitura ao repositório e estar autenticado no GitHub, ex.: `gh auth login`):
```
/plugin marketplace add liddera/plugin-sicoob
/plugin install lid@liddera-plugins
```
ou, em um passo (Claude Code 2.1.275+): `/plugin install lid --marketplace liddera/plugin-sicoob`.

- Marketplaces de terceiros **não atualizam sozinhos**: atualize pela aba *Marketplaces* de `/plugin` ou com `claude plugin update lid@liddera-plugins`.
- O `plugin.json` fixa a **versão**: a cada entrega, aumente `version`, senão a equipe não recebe a atualização.

Depois: `/lid:preparar` (uma vez por computador) e `/lid:login`.

## Como usar
1. **`/lid:preparar`** (uma vez): cria o ambiente Python do plugin, instala `playwright==1.63.0` e baixa o Chromium 153.0.8010.12 (≈ 200 MB).
2. **`/lid:login`**: abre o navegador do Sicoob; o usuário **escaneia o QR** (e cadastra o dispositivo, se pedir) e **não fecha a janela**.
   Depois o Claude pergunta, nesta ordem: **pasta → contas → documentos → meses** e mostra um resumo para confirmar.
3. **`/lid:extrair`**: executa em segundo plano (cada item leva de 20 a 70 s). Pede aprovação por gravar arquivos.
4. **`/lid:status`** (andamento), **`/lid:cancelar`** (para ao fim do item), **`/lid:resultado`** (relatório final).

Exemplo:
> **Você:** `/lid:login`
> **Claude:** Navegador aberto. Escaneie o QR e não feche a janela. *(login feito)* 78 contas carregadas. Vou salvar em `H:\Drives compartilhados\Contábil` (120 empresas encontradas). Usar essa pasta ou outra?
> **Você:** essa. Contas 47.041-4 e 109.317-7, extrato corrente e capital, de junho a setembro.
> **Claude:** 2 contas × 2 documentos × 4 meses = **16 itens**. Confirma?
> **Você:** sim → `/lid:extrair`

### O que o usuário pode informar
| Campo | Formas aceitas |
|---|---|
| **Pasta** | Caminho completo, só no `/lid:login`. Padrão `H:\Drives compartilhados\Contábil` |
| **Contas** | Números (com ou sem pontuação), nome da empresa (busca no portal), "todas" (confirmação extra), lista colada, "as pendentes", "as com erro" |
| **Documentos** | `corrente`, `capital`, `comprovantes`, `cartão` (um, vários ou todos) |
| **Meses** | `06/2026`, `06/2026 a 09/2026`, `junho a setembro de 2026`. Meses futuros e anteriores a 2020 são recusados |

## Ferramentas do servidor MCP
| Ferramenta | Faz |
|---|---|
| `preparar` / `preparar_status` | Instala o ambiente em segundo plano / mostra o andamento e o que falta |
| `conectar` / `login_status` | Abre o navegador na tela de login / informa navegador, login e nº de contas |
| `listar_contas` / `buscar_conta` | Lista os números / busca por número ou nome (devolve número, nome, PJ ou PF; nunca CNPJ/CPF) |
| `validar_pedido` | Confere pasta, contas, documentos e meses **sem executar** e devolve o resumo |
| `extrair` | Inicia a execução (exige `confirmado=true`); também `refazer: "erro"` e `refazer: "continuar"` |
| `status` / `cancelar` / `resultados` | Andamento / cancela ao fim do item / relatório |
| `atalho_contas` | Contas `pendentes` ou `com_erro` hoje, lidas do controle do robô |
| `diagnostico` | Caminhos, versões e últimas linhas do log (sem dados bancários) |

## Onde os arquivos são salvos
```
<pasta base>\<Empresa>\<ano>\Banco\Sicoob\<conta>\<tipo>\<MM>.pdf
```
| Documento | Pasta `<tipo>` |
|---|---|
| Extrato conta corrente | `Extrato CC` |
| Extrato conta capital | `Extratos Conta Capital` |
| Comprovantes | `Comprovantes` |
| Fatura de cartão | `Faturas do Cartão de Crédito` |

A pasta da empresa é procurada, nesta ordem, **pela conta no ano pedido**, **pela conta em outro ano** e **pelo nome da empresa**;
se não existir, é criada com o nome formatado (`Auto Posto Patrao Cacoal Ltda`). Um `MM.pdf` que já existe é **substituído**
(o relatório marca "substituído"). Capital sem movimentação gera o PDF só com os saldos, como o portal entrega.

## Relatório final
| Conta | Empresa | Documento | Mês | Resultado | Arquivo |
|---|---|---|---|---|---|
| 47.041-4 | … | Extrato corrente | 08/2026 | ✅ gerado | `…\Extrato CC\08.pdf` |
| 109.317-7 | … | Capital | 09/2026 | ✅ sem movimento (PDF só com os saldos) | `…\Extratos Conta Capital\09.pdf` |
| 14.035-0 | … | Comprovantes | 09/2026 | ⚠️ aviso: sem comprovantes | — |
| 16.900-5 | … | Cartão | 06/2026 | ❌ erro: motivo | — |
| 16.900-5 | … | Cartão | 07/2026 | ⏸️ não executado | — |

⚠️ **aviso não é erro** (conta sem cartão, mês sem comprovantes): não repete. ⏸️ aparece quando a execução foi cancelada ou o navegador fechou.

## Regras de execução (as do robô, com 2 diferenças)
- Ordem: todos os meses do 1º documento, depois os do 2º. Só o 1º item de cada conta entra pela lista de contas; os seguintes reaproveitam a conta; só o último volta à lista.
- **2 tentativas** por item e até **3 recuperações** por conta; depois desiste dos itens restantes dela.
- Antes de cada item, fecha drawers, diálogos e popups abertos (feito pelo código do robô).
- O mês do extrato precisa **bater com o pedido**.
- **Diferenças deliberadas em relação ao robô:** (1) aviso não é erro; (2) se o **navegador fechar**, a execução é **interrompida** e os itens restantes ficam "não executados", em vez de virarem "erro definitivo".

## Navegador, perfil e login
- **Chrome for Testing 153.0.8010.12** (Playwright 1.63.0), a mesma versão do EXE do robô, visível. Não precisa ter o Chrome instalado.
- Perfil: `%LOCALAPPDATA%\SicoobBot\perfil_sicoobnet_persistente`, o **mesmo do robô** (guarda o cadastro do dispositivo no Sicoob).
- Um Chromium **mais antigo não abre** um perfil usado por um **mais novo**. Por isso a versão é fixa, e o plugin confere o arquivo `Last Version` do perfil antes de abrir e recusa com uma explicação clara.
- **Um programa por vez** no perfil: com o robô aberto, o plugin avisa para fechá-lo.
- Login por QR e cadastro de dispositivo são **sempre manuais**. O plugin nunca digita credenciais. **Nunca feche a janela logada.**
- O navegador pertence ao plugin: ao **fechar o Claude**, o navegador fecha e o próximo uso exige novo QR.

## Arquitetura
```
Claude ─ skills ─▶ conduzem a conversa e a confirmação
   └─ MCP (stdio) ─▶ server/lid_server.py   (só biblioteca padrão; funciona antes do /lid:preparar)
                        └─ pipes JSON ─▶ worker/main.py   (ambiente com Playwright; dono do navegador)
                                            ├─ core/      pedido, runner, controle, perfil, resultado, log
                                            └─ vendor/sicoobbot/   código do robô (ações no portal, PDFs)
```
O servidor é separado do worker de propósito: uma queda do navegador não derruba o servidor, e o servidor consegue
oferecer `preparar` mesmo sem o Playwright instalado.

## Arquivos e logs
Em `%LOCALAPPDATA%\SicoobBot\lid\`: `ultima_execucao.json` (resultado da última execução, base do relatório e do "refazer/continuar")
e `logs\lid.log`. O log registra **como o navegador morreu** (`pagina_travou`, `pagina_fechada`, `contexto_fechado`,
`navegador_desconectado`) e tudo que o código do robô imprime. Não grava saldos nem movimentos.

## Segurança e privacidade
- Só **consulta e exporta**: não há pagamento, transferência nem alteração no portal. Só o domínio `ib.sicoob.com.br`.
- Nenhuma credencial é digitada ou guardada.
- **Saldos e movimentos não voltam ao Claude:** os PDFs ficam em disco, e na conversa aparecem só status, nomes e caminhos.
- O controle do robô (`controle_execucao_contas.json`) é **somente leitura** nesta versão.

## Problemas comuns
| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Servidor `sicoob` aparece como **failed** / não há ferramentas | Python ausente ou fora do PATH (o plugin chama `python`) | Instalar o Python 3.10+, conferir `python --version`, **reiniciar o Claude**. O Claude guarda a falha em cache por 15 min; reiniciar resolve |
| "O ambiente do plugin não está pronto" | Falta rodar a preparação | `/lid:preparar` |
| "Feche o SicoobBot" / perfil em uso | O robô ou outra sessão usa o perfil | Fechar o robô |
| Navegador não abre, "Target page… closed" | Perfil usado por Chromium mais novo | Atualizar o plugin (mesma versão do robô) |
| Pasta não encontrada | Unidade `H:` não visível (por ex., programa como administrador) | Abrir como usuário normal e conferir a unidade |
| "Conta não encontrada" | Número errado ou fora da lista | Usar o nome da empresa ou conferir o número |
| "Sem comprovantes" / "sem cartão" | Não há dados naquele mês/conta | Normal, é aviso |
| Navegador fechou no meio | Fechado por alguém, ou caiu | Ver `/lid:status` e `diagnostico`; `/lid:login` e depois "continuar" |

## O que foi e o que não foi verificado
**Verificado (sem o portal):**
- 46 testes automáticos (núcleo, runner e integração servidor MCP ⇄ worker ⇄ runner, com arquivos reais) e mutações que provam que o runner pega violações das regras.
- `claude plugin validate --strict` nos dois manifestos.
- Pelo **Claude Code real**: o plugin carrega, os 6 comandos `/lid:*` aparecem, o servidor MCP conecta, as 13 ferramentas são registradas, `/lid:status` chama a ferramenta sem pedir permissão e o Claude interpreta a resposta.
- **Do zero**: `preparar` monta o ambiente (Playwright 1.63.0 + Chromium 153.0.8010.12) e `conectar` abre esse navegador; a queda é detectada e registrada com a causa; reabrir funciona; ao encerrar o servidor não sobra processo.
- O código do robô importa com a configuração do plugin.

**Ainda NÃO verificado:**
- O fluxo completo **com login real** no Sicoob (QR) usando este plugin: extrato, capital, comprovantes e cartão. As ações em si são as do robô (testadas no portal real com o Chromium 145; o EXE usa o 153).
- Se o **cadastro do dispositivo** persiste entre execuções.
- Instalação pelo marketplace e uso em **Windows** (os testes foram em Linux); o comando `python` no Windows da equipe.
- A **causa da queda do navegador** vista no Windows de um usuário do robô (por isso o registro de eventos).

## Estrutura do repositório
```
.claude-plugin/plugin.json        manifesto ("lid")
.claude-plugin/marketplace.json   marketplace "liddera-plugins"
.mcp.json                         servidor MCP "sicoob"
skills/<comando>/SKILL.md         login, extrair, status, resultado, preparar, cancelar
server/                           lid_server.py (MCP), setup_env.py (preparar)
worker/                           main.py, backend_real.py, backend_fake.py (testes)
core/                             pedido, runner, controle, perfil, resultado, logs, paths
vendor/sicoobbot/                 código do robô + config.py do plugin + VENDOR.json
scripts/sync_vendor.py            copia o código do robô e registra o commit de origem
tests/                            unittest (+ smoke_*.py manuais, com navegador real)
docs/                             plano e decisões
```

## Desenvolvimento
- Testes: `python -m unittest discover -s tests -t .` (usa `SICOOBBOT_HOME` para não tocar na pasta real).
- Validar: `claude plugin validate . --strict`. Carregar localmente: `claude --plugin-dir <caminho>`.
- Atualizar o código do robô: `python scripts/sync_vendor.py --robot <pasta automacoes>`; conferir integridade: `--check`.
  Nunca edite `vendor/sicoobbot/*.py` à mão (exceto `config.py`, que é do plugin); mudanças vão para o robô e voltam pelo script.
- Mantenha `playwright==1.63.0` igual ao do EXE do robô (`core/paths.py`).
- Testes devem usar **cargas realistas** (o maior extrato real tem ≈ 1.850 movimentos). Evite gerar PDFs enormes de propósito: já travou a máquina de quem testava.
- `tests/smoke_navegador_real.py` e `tests/smoke_preparar_real.py` abrem um navegador de verdade (sem login) e baixam o Chromium; rode só quando necessário.
