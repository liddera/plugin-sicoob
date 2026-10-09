import re
def parse_extrato_sicoob_txt(conteudo):
    linhas = conteudo.replace("\r\n", "\n").split("\n")
    dados = {
        "cabecalho_data": "",
        "cabecalho_hora": "",
        "cooperativa": "",
        "conta": "",
        "periodo": "",
        "institucional_l1": "",
        "institucional_l2": "",
        "movimentos": [],
        "resumo": [],
        "linhas_fallback": [],
        "rodape": [],
    }

    regex_linha_principal = re.compile(
        r"^\s*(\d{2}/\d{2}(?:/\d{4})?)\s+(.*?)\s+(-?\d{1,3}(?:\.\d{3})*,\d{2}\s*[CD]?)\s*$",
        re.IGNORECASE,
    )
    regex_valor_fim = re.compile(r"(-?\d{1,3}(?:\.\d{3})*,\d{2}\s*[CD]?)\s*$", re.IGNORECASE)
    regex_data_inicio = re.compile(r"^\s*\d{2}/\d{2}(?:/\d{4})?\b")
    regex_data_valor = re.compile(
        r"\d{2}/\d{2}(?:/\d{4})?.*-?\d{1,3}(?:\.\d{3})*,\d{2}\s*[CD]?\s*$",
        re.IGNORECASE,
    )

    def classificar_tipo(historico, valor):
        valor_norm = valor.replace(" ", "").upper()
        historico_up = historico.upper()
        if "SALDO" in historico_up:
            return "saldo"
        if valor_norm.endswith("C"):
            return "credito"
        if valor_norm.endswith("D") or valor_norm.startswith("-"):
            return "debito"
        return "credito"

    secao = ""
    movimento_atual = None

    for linha_raw in linhas:
        linha = linha_raw.rstrip()
        linha_strip = linha.strip()

        if not linha_strip:
            continue

        linha_up = linha_strip.upper()

        if (not dados["institucional_l1"]) and "SICOOB - SISTEMA DE COOPERATIVAS DE CRÉDITO DO BRASIL" in linha_up:
            dados["institucional_l1"] = linha_strip
            continue

        if (not dados["institucional_l2"]) and "PLATAFORMA DE SERVIÇOS FINANCEIROS DO SICOOB - SISBR" in linha_up:
            dados["institucional_l2"] = linha_strip
            continue

        if "EXTRATO CONTA CORRENTE" in linha and not dados["cabecalho_data"]:
            m_head = re.match(
                r"^\s*(\d{2}/\d{2}/\d{4})\s+EXTRATO CONTA CORRENTE\s+(\d{2}:\d{2}:\d{2})\s*$",
                linha,
            )
            if m_head:
                dados["cabecalho_data"] = m_head.group(1)
                dados["cabecalho_hora"] = m_head.group(2)
            continue

        if linha_strip.startswith("COOP.:"):
            dados["cooperativa"] = linha_strip.replace("COOP.:", "", 1).strip()
            continue

        if linha_strip.startswith("CONTA:"):
            dados["conta"] = linha_strip.replace("CONTA:", "", 1).strip()
            continue

        if linha_strip.startswith("PERÍODO:") or linha_strip.startswith("PERIODO:"):
            dados["periodo"] = re.sub(r"^PER[ÍI]ODO:\s*", "", linha_strip).strip()
            continue

        if "LANÇAMENTOS" in linha_strip:
            secao = "lancamentos"
            movimento_atual = None
            continue

        if "RESUMO" in linha_strip:
            secao = "resumo"
            movimento_atual = None
            continue

        if "EXTRATO No.:" in linha_strip or linha_strip.startswith("SAC:"):
            secao = "rodape"

        if re.fullmatch(r"-{10,}", linha_strip):
            continue

        if secao == "lancamentos":
            if "DATA" in linha_up and "DOCUMENTO" in linha_up and "VALOR" in linha_up:
                continue

            match_linha_principal = regex_linha_principal.match(linha)
            if match_linha_principal:
                data, trecho, valor = match_linha_principal.groups()
                data = data.strip()
                valor = valor.strip().replace(" ", "")
                trecho = trecho.strip()
                partes = re.split(r"(?:\s{2,}|\t+)", trecho, maxsplit=1) if trecho else []

                if len(partes) == 2:
                    documento = partes[0].strip()
                    historico = partes[1].strip()
                elif len(partes) == 1:
                    documento = ""
                    historico = partes[0].strip() or "(sem histórico)"
                else:
                    documento = ""
                    historico = "(sem histórico)"

                movimento_atual = {
                    "data": data,
                    "documento": documento,
                    "historico": historico,
                    "valor": valor,
                    "tipo": classificar_tipo(historico, valor),
                    "detalhes": [],
                }
                dados["movimentos"].append(movimento_atual)
                continue

            if regex_data_inicio.match(linha):
                valor_fim = regex_valor_fim.search(linha_strip)
                if valor_fim and ("SALDO ANTERIOR" in linha_up or "SALDO FINAL" in linha_up):
                    data = regex_data_inicio.match(linha).group(0).strip()
                    valor = valor_fim.group(1).strip().replace(" ", "")
                    meio = linha_strip[len(data) : valor_fim.start()].strip()
                    movimento_atual = {
                        "data": data,
                        "documento": "",
                        "historico": meio or "SALDO",
                        "valor": valor,
                        "tipo": "saldo",
                        "detalhes": [],
                    }
                    dados["movimentos"].append(movimento_atual)
                else:
                    dados["linhas_fallback"].append(linha_strip)
                continue

            if movimento_atual:
                identacao = len(linha) - len(linha.lstrip(" "))
                pode_ser_detalhe = identacao >= 6 or not re.search(r"\d{2}/\d{2}", linha_strip)
                parece_novo_registro = bool(regex_data_valor.search(linha_strip))
                if pode_ser_detalhe and not parece_novo_registro:
                    movimento_atual["detalhes"].append(linha_strip)
                else:
                    dados["linhas_fallback"].append(linha_strip)
            else:
                dados["linhas_fallback"].append(linha_strip)
            continue

        if secao == "resumo":
            valor_fim = regex_valor_fim.search(linha_strip)
            if valor_fim and ("SALDO ANTERIOR" in linha_up or "SALDO FINAL" in linha_up):
                dados["resumo"].append(
                    {"label": linha_strip[: valor_fim.start()].strip(), "valor": valor_fim.group(1).strip()}
                )
                continue

            match_resumo = re.match(r"^(.*?)\.+:\s*(.+)$", linha_strip)
            if match_resumo:
                dados["resumo"].append(
                    {"label": match_resumo.group(1).strip(), "valor": match_resumo.group(2).strip()}
                )
            else:
                dados["resumo"].append({"label": linha_strip, "valor": ""})
            continue

        if secao == "rodape":
            dados["rodape"].append(linha_strip)
            continue

        dados["linhas_fallback"].append(linha_strip)

    return dados
