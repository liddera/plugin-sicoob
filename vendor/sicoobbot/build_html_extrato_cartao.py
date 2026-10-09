from html import escape


def build_html_extrato_cartao(html_modal, numero_conta, empresa, vencimento):
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Extrato de Fatura - Cartao</title>
  <style>
    @page {{
      size: A4;
      margin: 10mm;
    }}
    body {{
      font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
      color: #113544;
      background: #fff;
      margin: 0;
      padding: 0;
    }}
    .meta {{
      margin-bottom: 8mm;
      border-bottom: 1px solid #d8e1e6;
      padding-bottom: 4mm;
      font-size: 12px;
    }}
    .meta strong {{
      color: #0c2f43;
    }}
    .content .footDownloads,
    .content button,
    .content iframe,
    .content app-report-print {{
      display: none !important;
    }}
    .content table {{
      width: 100%;
      border-collapse: collapse;
    }}
    .content th,
    .content td {{
      font-size: 12px;
      padding: 4px 6px;
      vertical-align: top;
    }}
    .content td[style*='text-align: right'] {{
      text-align: right !important;
      white-space: nowrap;
    }}
  </style>
</head>
<body>
  <div class="meta">
    <strong>Empresa:</strong> {escape(empresa or "")}
    &nbsp;&nbsp;|&nbsp;&nbsp;
    <strong>Conta:</strong> {escape(numero_conta or "")}
    &nbsp;&nbsp;|&nbsp;&nbsp;
    <strong>Vencimento:</strong> {escape(vencimento or "")}
  </div>
  <div class="content">
    {html_modal or ""}
  </div>
</body>
</html>
"""
