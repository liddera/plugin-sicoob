# Guia do usuário: plugin `lid` (Sicoob)

Este guia é para quem **vai usar** o plugin no dia a dia, sem precisar entender de programação.
Se você procura a parte técnica, veja o [README](../README.md).

> **Aviso:** a versão atual (0.3.0) já foi testada por completo **sem o portal do Sicoob**, mas o **primeiro teste com login real**
> ainda está pendente. Na primeira vez, rode com **1 conta e 1 mês**, salvando em uma **pasta de teste**.

---

## 1. O que é

É um assistente dentro do Claude que **baixa para você** os documentos do Sicoob e os guarda nas pastas certas:

| Documento | O que é |
|---|---|
| **Extrato conta corrente** | O extrato mensal da conta |
| **Extrato conta capital** | O extrato do capital na cooperativa |
| **Comprovantes** | Os comprovantes de pagamentos do mês |
| **Fatura de cartão** | A fatura do cartão de crédito |

Você **conversa** com o Claude e diz o que quer. Ele abre o navegador do Sicoob, você entra com o QR code, e o resto é automático.

**O que ele nunca faz:** pagar, transferir ou mexer em qualquer coisa do banco. Ele só **consulta e baixa**.
Seus saldos e movimentos **não aparecem na conversa**: os valores ficam só dentro dos PDFs.

---

## 2. Antes de começar (uma vez só)

Confira esta lista:

- [ ] Computador com **Windows**.
- [ ] **Claude Desktop**, na aba **Código**.
- [ ] **Python 3.10 ou mais novo** instalado (se não tiver, o Claude oferece instalar; veja abaixo).
- [ ] Acesso ao **repositório do plugin** no GitHub (peça à equipe de TI) e estar logado no GitHub no computador.
- [ ] Seu **celular com o app do Sicoob**, para ler o QR code.
- [ ] Internet e cerca de **400 MB livres** (só na primeira vez).
- [ ] Se você usa o **SicoobBot** neste computador, ele deve estar **fechado** (os dois não podem ficar abertos juntos).
- [ ] Acesso à **pasta onde os arquivos serão salvos** (por exemplo, o Drive da contabilidade).

**Se você não tem o Python, o Claude ajuda a instalar.** Ao rodar `/lid:preparar` (ou `/lid:login`), se o Claude perceber que falta o Python,
ele **explica e pede a sua permissão** para instalá-lo pelo próprio Windows (o Python oficial, uns 25 MB). Responda **sim**, aguarde, e depois
**feche e abra o Claude de novo** (é preciso reabrir para o Windows reconhecer o Python). Se isso não funcionar (por exemplo, o computador
bloqueia instalações), siga o passo manual abaixo.

**Como conferir o Python** (ou instalar manualmente): abra o menu Iniciar, digite `cmd`, abra o "Prompt de Comando" e digite:

```
python --version
```

Deve aparecer algo como `Python 3.12.3`. Se aparecer um erro ou uma versão menor que 3.10, instale o Python em **python.org**
e, na instalação, **marque a opção "Add python.exe to PATH"**. Depois **feche e abra o Claude de novo**.

---

## 3. Instalar o plugin (uma vez só)

No Claude Desktop, na aba **Código**, digite estas duas linhas, uma de cada vez:

```
/plugin marketplace add liddera/plugin-sicoob
/plugin install lid@liddera-plugins
```

Para conferir, digite `/lid:`. Devem aparecer estes comandos:

| Comando | Para que serve |
|---|---|
| `/lid:preparar` | Deixa o computador pronto (só na primeira vez) |
| `/lid:login` | Entrar no Sicoob e montar o pedido |
| `/lid:extrair` | Baixar os documentos |
| `/lid:status` | Ver como está indo |
| `/lid:cancelar` | Parar |
| `/lid:resultado` | Ver o relatório do que foi feito |
| `/lid:diagnostico` | Pedir ajuda: mostra informações para a TI |

**Atualizar depois:** o plugin **não se atualiza sozinho**. Quando a equipe avisar que há versão nova, rode
`claude plugin update lid@liddera-plugins` ou use a aba **Marketplaces** em `/plugin` e escolha *Update marketplace*.

---

## 4. Preparar o computador (uma vez só)

Digite:

```
/lid:preparar
```

O Claude vai explicar o que será instalado e **pedir sua permissão** (clique em permitir). Ele baixa o navegador que o plugin usa
(cerca de 200 MB) e leva **de 1 a 5 minutos**. No final ele avisa: *"Tudo pronto"*.

> Você **não precisa** ter o Chrome instalado. O plugin traz o seu próprio navegador.

---

## 5. Usar no dia a dia

### Passo 1: entrar no Sicoob

```
/lid:login
```

1. Uma **janela de navegador** abre na tela de login do Sicoob.
2. No celular, abra o app do Sicoob e **leia o QR code**. Se o Sicoob pedir para **cadastrar o dispositivo**, faça normalmente.
3. **Não feche essa janela.** Se fechar, será preciso ler o QR code de novo.
4. O Claude avisa quando o login terminar e quantas contas foram encontradas.

#### Primeira vez, ou você já usava o SicoobBot?

O plugin guarda o cadastro do seu dispositivo em um **"perfil" de navegador**. Se este computador já tinha o SicoobBot, os dois **compartilham esse perfil**.
Por isso o `/lid:login` se comporta de forma diferente conforme o seu caso, e o Claude avisa qual é:

| Seu caso | O que acontece | O que você faz |
|---|---|---|
| **Nunca usou o SicoobBot** (nenhum perfil neste computador) | É a **primeira vez**: o Sicoob vai pedir para **cadastrar o dispositivo** | Faça o cadastro (uma vez). Ele fica guardado para as próximas vezes |
| **Já usa o SicoobBot** (versão gerada em 8/10/2026 ou mais nova) | O plugin **reaproveita o perfil** que já existe. O Sicoob **não deve** pedir o cadastro de novo (ainda não foi confirmado na prática) | Feche o SicoobBot antes de usar o plugin |
| **Usa uma versão antiga do SicoobBot** | O Claude **avisa e pergunta**: usar o plugin atualiza o perfil, e **esse programa antigo deixa de abrir** até ser atualizado | Se aceitar, o plugin segue. Se não quiser arriscar, **atualize o SicoobBot primeiro** (peça uma versão nova à TI) |
| Seu SicoobBot é **mais novo** que o plugin | O plugin **não abre** e explica | Atualize o plugin (seção 3) |
| O **SicoobBot está aberto** | O plugin **não abre** e pede para fechá-lo | Feche o SicoobBot |

### Passo 2: dizer o que você quer

O Claude pergunta **uma coisa de cada vez** (ou você pode dizer tudo numa frase só). A ordem é:

**1) Em qual pasta salvar?**
Ele sugere a pasta padrão. Responda *"essa"* ou escreva outro caminho, por exemplo uma pasta de teste: `C:\Teste\Extratos`.
Ele confere se a pasta existe e mostra alguns nomes de empresa que encontrou nela, para você ver que é a pasta certa.

**2) Quais contas?** Você pode dizer:

| Você escreve | O que acontece |
|---|---|
| `47.041-4` ou `470414` | Usa essa conta (com ou sem pontuação) |
| `47.041-4 e 109.317-7` | Usa as duas |
| `Auto Posto Avenida` | Ele busca no Sicoob pelo nome e mostra as contas para você escolher |
| `todas` | Usa todas as contas (ele pede uma confirmação extra) |
| `as que deram erro` | Usa as que falharam antes |
| `as pendentes` | Usa as que ainda não foram feitas (para os documentos e meses que você indicar) |

**3) Quais documentos?** `corrente`, `capital`, `comprovantes`, `cartão`, vários ao mesmo tempo, ou `todos`.

**4) Quais meses?**

| Você escreve | Resultado |
|---|---|
| `09/2026` | Só setembro de 2026 |
| `06/2026 a 09/2026` ou `junho a setembro de 2026` | Junho, julho, agosto e setembro |
| `06, 08 e 09/2026` | Só esses três meses |
| `mês passado` | O Claude calcula e mostra as datas |

Não é possível pedir **meses que ainda não terminaram** nem anteriores a **2020**.

**5) Conferir o resumo.** Antes de começar, o Claude mostra algo assim:

> **Pasta:** `H:\Drives compartilhados\Contábil` (120 empresas encontradas)
> **Contas (2):** 47.041-4, 109.317-7
> **Documentos (2):** extrato corrente, extrato capital
> **Meses (4):** 06, 07, 08, 09/2026
> **Total: 16 itens.** Confirma?

Se estiver certo, responda **sim**. Se algo estiver errado, diga o que corrigir.

### Passo 3: baixar

```
/lid:extrair
```

O Claude pede a **sua permissão** para gravar os arquivos. Clique em permitir. Depois:

- Cada item leva de **20 a 70 segundos**. Muitos itens podem levar **horas**: deixe o computador ligado.
- **Não mexa na janela do navegador** enquanto ele trabalha (não clique, não feche, não digite).
- Você pode **continuar usando o computador** para outras coisas, só sem mexer nessa janela.
- Para saber como está: `/lid:status`. Para parar: `/lid:cancelar` (ele para ao terminar o item atual).

### Passo 4: ver o resultado

```
/lid:resultado
```

Aparece uma tabela com cada item, o resultado e **onde o arquivo foi salvo**.

| Símbolo | Significa | O que fazer |
|---|---|---|
| ✅ gerado | Deu certo | Nada |
| ✅ substituído | O arquivo daquele mês já existia e foi trocado pelo novo | Nada (só conferir se era isso mesmo) |
| ✅ sem movimento | A conta não teve movimentação naquele mês. O PDF traz só os saldos, como o Sicoob entrega | Nada |
| ⚠️ aviso | Não havia o que baixar (por exemplo, **conta sem cartão** ou **mês sem comprovantes**) | Normal. **Não é erro** |
| ❌ erro | Não conseguiu. O motivo aparece ao lado | Veja a seção 8 e peça para **refazer** |
| ⏸️ não executado | A execução foi parada (por você ou porque o navegador fechou) | Peça para **continuar** |

### Refazer sem começar do zero

Depois de uma execução, é só dizer ao Claude:

- *"Refaça só os que deram erro."*
- *"Continue de onde parou."*
- *"Rode de novo, mas só o que falta."* (ele pula o que já foi baixado, **inclusive de outros dias**)

---

## 6. Onde ficam os arquivos

Dentro da pasta que você escolheu, tudo segue **sempre o mesmo padrão**:

```
<pasta escolhida>
└── <Nome da Empresa>
    └── <ano>
        └── Banco
            └── Sicoob
                └── <número da conta>
                    ├── Extrato CC                       →  08.pdf, 09.pdf ...
                    ├── Extratos Conta Capital           →  08.pdf, 09.pdf ...
                    ├── Comprovantes                     →  08.pdf, 09.pdf ...
                    └── Faturas do Cartão de Crédito     →  08.pdf, 09.pdf ...
```

- O arquivo se chama pelo **número do mês** (`09.pdf` é setembro).
- O plugin **procura a pasta da empresa que já existe**: primeiro pela conta, depois pelo nome. Se não achar, **cria uma pasta nova**.
- Se o arquivo daquele mês **já existir**, ele é **substituído** (e o relatório avisa).

---

## 7. Boas práticas (leia uma vez)

**Faça**
- Na primeira vez, teste com **1 conta, 1 mês e uma pasta de teste**.
- Mantenha a **janela do navegador aberta** do login até o fim.
- Se usa o **SicoobBot**, feche-o antes de usar o plugin (e vice-versa).
- Confira o **resumo** antes de dizer "sim".

**Não faça**
- Não **feche a janela do Sicoob** no meio. O login se perde e precisa do QR code de novo.
- Não **clique dentro** da janela enquanto ela está trabalhando.
- Não abra o plugin **como administrador**: ele pode não enxergar o Drive (`H:`).
- Não compartilhe o QR code nem a senha do Sicoob com ninguém. **O plugin nunca pede sua senha.**

**Importante:** ao **fechar o Claude**, o navegador do plugin **também fecha**, e no próximo uso será preciso rodar `/lid:login` e ler o QR code de novo.

---

## 8. Se algo der errado

| O que você vê | Provável causa | O que fazer |
|---|---|---|
| O plugin diz que **o ambiente não está pronto** | Falta a preparação | Digite `/lid:preparar` |
| O Claude diz que **não encontra as ferramentas** do plugin, ou o servidor aparece como **falhou** | Python não instalado, ou fora do PATH | Deixe o Claude **oferecer a instalação** (ele pede a sua permissão) ou veja a seção 2; depois **feche e abra o Claude** (ele guarda a falha por uns 15 minutos) |
| Pede para **fechar o SicoobBot** | Ele está aberto e usa o mesmo perfil | Feche o SicoobBot |
| O navegador **não abre** e fala em perfil de um navegador "mais novo" | O SicoobBot é mais novo que o plugin | Atualize o plugin (seção 3) ou chame a TI |
| O Claude pergunta se pode **atualizar o perfil de uma versão antiga** | O SicoobBot deste computador usa um navegador mais antigo | Veja a tabela do Passo 1: aceite, ou atualize o SicoobBot antes |
| **Pasta não encontrada** | Caminho errado, ou o Drive (`H:`) não está visível | Confira o caminho; não use "executar como administrador" |
| **Conta não encontrada** | Número errado ou conta fora da lista | Use o **nome da empresa** ou confira o número |
| Muitos itens com ❌ de uma só conta | O Sicoob demorou ou mudou algo | Peça `Refaça só os que deram erro`. Se continuar, chame a TI |
| A janela do navegador **fechou sozinha** no meio | Foi fechada, ou o programa travou | Digite `/lid:login`, leia o QR code e peça `Continue de onde parou` |
| Os ícones ficaram estranhos (⏸️) | A execução foi interrompida | Peça `Continue de onde parou` |

**Antes de pedir ajuda à TI**, digite:

```
/lid:diagnostico
```

Ele mostra um resumo (versões, estado do navegador e as últimas linhas do registro do plugin) e o **caminho do arquivo de registro**.
Mande isso para a TI. Esse registro **não contém saldos, movimentos nem senhas**.

---

## 9. Perguntas frequentes

**Preciso ler o QR code toda vez?**
Sim, em cada vez que abrir o navegador (por exemplo, depois de fechar o Claude). O cadastro do dispositivo no Sicoob costuma ficar guardado, mas isso ainda não foi confirmado.

**Posso pedir um mês que já baixei?**
Pode. O arquivo antigo é substituído e o relatório avisa. Para **pular o que já foi feito**, diga *"só o que falta"*.

**Por que "sem cartão" ou "sem comprovantes" não é erro?**
Porque o Sicoob realmente não tem aquele documento. O plugin anota e segue para o próximo item.

**Posso usar o SicoobBot e o plugin no mesmo computador?**
Pode, mas **um de cada vez**. Os dois usam o mesmo navegador por dentro e não funcionam juntos.

**O plugin guarda histórico?**
Sim. Ele registra, no seu computador, cada item feito (resultado, horário, duração, arquivo). É o que permite *"refaça os que deram erro"* e *"só o que falta"*. O registro **não** guarda saldos nem movimentos.

**Onde esse histórico e o registro de funcionamento ficam?**
Em `C:\Users\<seu usuário>\AppData\Local\SicoobBot\lid\`. Não é a pasta onde os PDFs são salvos.

**Quanto tempo leva?**
De 20 a 70 segundos por item. Por exemplo, 2 contas × 2 documentos × 4 meses = 16 itens, algo entre 5 e 20 minutos.

---

## 10. Pequeno dicionário

| Palavra | Quer dizer |
|---|---|
| **Item** | Um documento de uma conta em um mês (por exemplo, extrato corrente da conta 47.041-4 em 08/2026) |
| **Pasta de destino** | A pasta onde os PDFs são salvos |
| **QR code** | O desenho que você lê com o app do Sicoob para entrar |
| **Cadastrar dispositivo** | Autorizar este computador no Sicoob, uma vez |
| **Perfil do navegador** | O "cantinho" do navegador do plugin onde ficam guardados os dados de acesso, inclusive o cadastro do dispositivo |
| **Aviso** | Não havia o que baixar. Não é erro |
