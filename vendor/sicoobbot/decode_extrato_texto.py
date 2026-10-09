def decode_extrato_texto(texto_bytes):
    try:
        return texto_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return texto_bytes.decode("latin-1", errors="replace")
