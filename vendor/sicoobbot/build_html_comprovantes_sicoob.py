import re
from html import escape


def _garantir_dois_pontos(texto):
    valor = re.sub(r"\s+", " ", str(texto or "")).strip()
    if not valor or valor.endswith(":"):
        return valor
    return f"{valor}:"


def _normalizar_rotulos_tabela_dados(html_modal):
    """
    Insere ":" no próprio HTML dos rótulos da tabela .dados para manter
    consistência no texto extraído do PDF (sem depender de pseudo-elemento CSS).
    """
    if not html_modal:
        return ""

    re_table_dados = re.compile(
        r"(<table[^>]*class=[\"'][^\"']*\bdados\b[^\"']*[\"'][^>]*>)(.*?)(</table>)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _sub_span_duas_colunas(m):
        return f"{m.group(1)}{_garantir_dois_pontos(m.group(2))}{m.group(3)}"

    def _sub_texto_duas_colunas(m):
        return f"{m.group(1)}{_garantir_dois_pontos(m.group(2))}{m.group(3)}"

    def _sub_span_uma_coluna(m):
        return f"{m.group(1)}{_garantir_dois_pontos(m.group(2))}{m.group(3)}"

    def _sub_texto_uma_coluna(m):
        return f"{m.group(1)}{_garantir_dois_pontos(m.group(2))}{m.group(3)}"

    def _processar_tabela(match):
        abertura, conteudo, fechamento = match.groups()

        # <td><span>Rótulo</span></td><td>Valor</td>
        conteudo = re.sub(
            r"(<tr[^>]*>\s*<td[^>]*>\s*<span[^>]*>\s*)([^<]+?)(\s*</span>\s*</td>\s*<td[^>]*>)",
            _sub_span_duas_colunas,
            conteudo,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # <td>Rótulo</td><td>Valor</td>
        conteudo = re.sub(
            r"(<tr[^>]*>\s*<td[^>]*>)([^<]+?)(</td>\s*<td[^>]*>)",
            _sub_texto_duas_colunas,
            conteudo,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # <td><span>Seção</span></td> (linha única)
        conteudo = re.sub(
            r"(<tr[^>]*>\s*<td[^>]*>\s*<span[^>]*>\s*)([^<]+?)(\s*</span>\s*</td>\s*</tr>)",
            _sub_span_uma_coluna,
            conteudo,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # <td>Seção</td> (linha única)
        conteudo = re.sub(
            r"(<tr[^>]*>\s*<td[^>]*>)([^<]+?)(</td>\s*</tr>)",
            _sub_texto_uma_coluna,
            conteudo,
            flags=re.IGNORECASE | re.DOTALL,
        )

        return f"{abertura}{conteudo}{fechamento}"

    return re_table_dados.sub(_processar_tabela, html_modal)


def build_html_comprovantes_sicoob(html_modal, numero_conta, empresa, periodo):
    html_modal_normalizado = _normalizar_rotulos_tabela_dados(html_modal or "")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Comprovantes Sicoob</title>
  <style>
    @page {{
      size: A4 portrait;
      margin: 10mm;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      color: #08374f;
      background: #fff;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 10pt;
      line-height: 1.25;
    }}
    .content .row.ng-star-inserted,
    .content .footDownloads,
    .content #idBtnImprimir,
    .content iframe,
    .content label[for='selectModoImpressao'],
    .content #selectModoImpressao {{
      display: none !important;
    }}
    .content .comprovante {{
      page-break-inside: avoid;
      break-inside: avoid;
      page-break-after: always;
      break-after: page;
      margin-bottom: 6mm;
    }}
    .content .comprovante:last-of-type {{
      page-break-after: auto;
      break-after: auto;
    }}
    .content table {{
      width: 100%;
      border-collapse: collapse;
    }}
    .content td {{
      vertical-align: top;
      padding: 1.3mm 1mm;
      word-break: break-word;
    }}
    .content table.titulo td,
    .content table.transacao td {{
      text-align: center;
      font-weight: 700;
    }}
    .content table.transacao td.transacao-data,
    .content table.transacao td.transacao-hora {{
      width: 20%;
      font-weight: 400;
      font-size: 9pt;
    }}
    .content table.dados td:first-child {{
      width: 32%;
      font-weight: 700;
    }}
    .content tr.tab td:first-child {{
      font-weight: 400;
    }}
    .content hr {{
      display: none !important;
    }}
    .content small.release-version {{
      color: #909da6;
      font-size: 8pt;
      float: right;
    }}
  </style>
</head>
<body>
  <div class="content">
    {html_modal_normalizado}
  </div>
</body>
</html>"""
