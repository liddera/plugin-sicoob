from html import escape


def build_html_extrato_sicoob_capital(texto_bruto):
    conteudo = escape(texto_bruto or "")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Extrato Conta Capital</title>
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
      color: #111;
      background: #fff;
      font-family: "Courier New", Courier, monospace;
      font-size: 10pt;
      line-height: 1.25;
    }}
    .sheet {{
      padding: 2mm;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
    }}
  </style>
</head>
<body>
  <div class="sheet">
    <pre>{conteudo}</pre>
  </div>
</body>
</html>
"""
