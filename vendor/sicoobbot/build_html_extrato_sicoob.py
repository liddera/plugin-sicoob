from html import escape
from datetime import datetime
def build_html_extrato_sicoob(dados, numero):
    cooperativa = dados.get("cooperativa") or "Não capturado"
    conta = dados.get("conta") or numero
    periodo = dados.get("periodo") or "Não capturado"
    data_head = dados.get("cabecalho_data") or datetime.now().strftime("%d/%m/%Y")
    hora_head = dados.get("cabecalho_hora") or datetime.now().strftime("%H:%M:%S")
    movimentos = dados.get("movimentos", [])
    resumo = dados.get("resumo", [])
    institucional_l1 = dados.get("institucional_l1") or "SISTEMA DE COOPERATIVAS DE CRÉDITO DO BRASIL"
    institucional_l2 = dados.get("institucional_l2") or "PLATAFORMA DE SERVIÇOS FINANCEIROS DO SICOOB - SISBR"
    rodape = dados.get("rodape", [])

    html_parts = [
        f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Extrato Sicoob - {escape(numero)}</title>
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
      background: #efefef;
      color: #1f2b34;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 10pt;
      line-height: 1.22;
    }}
    @media screen {{
      .sheet {{
        width: 210mm;
        min-height: 297mm;
        margin: 8mm auto;
        padding: 10mm;
        background: #efefef;
      }}
    }}
    .sheet {{
      background: #efefef;
      padding: 6px 4px 0 4px;
    }}
    .top-brand {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }}
    .logo {{
      display: flex;
      align-items: baseline;
      gap: 5px;
      font-weight: 800;
      font-size: 20px;
      letter-spacing: 0.2px;
    }}
    .logo .s1 {{
      color: #00a859;
    }}
    .logo .s2 {{
      color: #005f83;
    }}
    .brand-text {{
      font-size: 11px;
      font-weight: 700;
      color: #0f3a54;
      text-transform: uppercase;
      line-height: 1.12;
    }}
    .section-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin: 10px 0 5px;
      font-weight: 700;
    }}
    .section-title .left {{
      display: flex;
      align-items: center;
      gap: 6px;
      color: #122b3a;
      font-size: 18px;
      text-transform: uppercase;
    }}
    .marker {{
      width: 12px;
      height: 12px;
      border: 2px solid #35c9be;
      border-radius: 3px;
      display: inline-block;
    }}
    .section-title .right {{
      font-size: 12px;
      color: #0f3a54;
      font-weight: 700;
    }}
    .meta {{
      margin: 4px 0 12px;
      color: #111;
      font-size: 10pt;
    }}
    .meta-row {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      margin: 1px 0;
    }}
    .meta .k {{
      min-width: 88px;
      color: #0f3a54;
      font-weight: 700;
      display: inline-block;
    }}
    .mov-title {{
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 8px 0 4px;
      color: #0f3a54;
      font-size: 18px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: auto;
    }}
    thead {{
      display: table-header-group;
    }}
    th {{
      text-align: left;
      color: #0f3a54;
      font-size: 9pt;
      padding: 2px 3px 3px;
      border-bottom: 1px solid #b8c2ca;
    }}
    th.col-data {{ width: 90px; }}
    th.col-doc {{ width: 110px; }}
    th.col-valor {{
      width: 120px;
      text-align: right;
    }}
    td {{
      padding: 2px 3px;
      vertical-align: top;
      border-bottom: 1px solid #dde3e7;
      word-break: break-word;
    }}
    tr.mov-principal {{
      page-break-inside: avoid;
    }}
    .data, .doc {{
      color: #12384e;
      font-weight: 700;
      white-space: nowrap;
    }}
    .hist {{
      color: #18242c;
      font-weight: 700;
    }}
    .valor {{
      text-align: right;
      font-weight: 800;
      white-space: nowrap;
      font-feature-settings: "tnum" 1;
    }}
    tr.credito .valor {{
      color: #00a859;
    }}
    tr.debito .valor {{
      color: #d21f4d;
    }}
    tr.saldo .valor {{
      color: #324a5a;
    }}
    tr.detalhe td {{
      border-bottom: none;
      padding-top: 0;
      color: #2f3e48;
      font-size: 9pt;
    }}
    tr.detalhe td:first-child,
    tr.detalhe td:nth-child(2),
    tr.detalhe td:last-child {{
      color: transparent;
    }}
    .resumo {{
      margin-top: 12px;
      page-break-inside: avoid;
    }}
    .resumo-title {{
      color: #0f3a54;
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 4px;
      text-transform: uppercase;
    }}
    .resumo table td {{
      border-bottom: 1px dashed #c8d0d6;
      padding: 2px 3px;
      font-size: 9.2pt;
    }}
    .resumo .l {{
      color: #1a2a33;
      width: 76%;
    }}
    .resumo .v {{
      text-align: right;
      width: 24%;
      font-weight: 700;
      white-space: nowrap;
    }}
    .rodape {{
      margin-top: 12px;
      padding-top: 6px;
      border-top: 1px solid #b8c2ca;
      color: #334651;
      font-size: 8.8pt;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="sheet">
    <div class="top-brand">
      <div class="logo"><span class="s1">SI</span><span class="s2">COOB</span></div>
      <div class="brand-text">
        {escape(institucional_l1)}<br>
        {escape(institucional_l2)}
      </div>
    </div>

    <div class="section-title">
      <div class="left"><span class="marker"></span> EXTRATO DE CONTA CORRENTE</div>
      <div class="right">{escape(data_head)} - {escape(hora_head)}</div>
    </div>

    <div class="meta">
      <div class="meta-row"><div><span class="k">Cooperativa:</span> {escape(cooperativa)}</div></div>
      <div class="meta-row"><div><span class="k">Conta:</span> {escape(conta)}</div></div>
      <div class="meta-row"><div><span class="k">Período:</span> {escape(periodo)}</div></div>
    </div>

    <div class="mov-title"><span class="marker"></span> HISTÓRICO DE MOVIMENTAÇÃO</div>

    <table>
      <thead>
        <tr>
          <th class="col-data">Data</th>
          <th class="col-doc">Documento</th>
          <th>Histórico</th>
          <th class="col-valor">Valor</th>
        </tr>
      </thead>
      <tbody>
"""
    ]

    for mov in movimentos:
        classe = mov.get("tipo", "")
        html_parts.append(
            f"""
        <tr class="mov-principal {escape(classe)}">
          <td class="data">{escape(mov.get("data", ""))}</td>
          <td class="doc">{escape(mov.get("documento", ""))}</td>
          <td class="hist">{escape(mov.get("historico", ""))}</td>
          <td class="valor">R$ {escape(mov.get("valor", ""))}</td>
        </tr>
"""
        )
        for detalhe in mov.get("detalhes", []):
            html_parts.append(
                f"""
        <tr class="detalhe">
          <td></td>
          <td></td>
          <td>{escape(detalhe)}</td>
          <td></td>
        </tr>
"""
            )

    if not movimentos:
        html_parts.append(
            """
        <tr>
          <td colspan="4">Nenhum lançamento encontrado para o período.</td>
        </tr>
"""
        )

    html_parts.append(
        """
      </tbody>
    </table>
"""
    )

    if resumo:
        html_parts.append(
            """
    <div class="resumo">
      <div class="resumo-title">Resumo</div>
      <table>
"""
        )
        for item in resumo:
            label = item.get("label", "")
            valor = item.get("valor", "")
            html_parts.append(
                f"""
        <tr>
          <td class="l">{escape(label)}</td>
          <td class="v">{escape(valor)}</td>
        </tr>
"""
            )
        html_parts.append(
            """
      </table>
    </div>
"""
        )

    if rodape:
        html_parts.append('<div class="rodape">' + " | ".join(escape(l) for l in rodape[:5]) + "</div>")
    else:
        html_parts.append(f'<div class="rodape">Documento gerado em {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</div>')

    html_parts.append(
        """
  </div>
</body>
</html>
"""
    )
    return "".join(html_parts)
