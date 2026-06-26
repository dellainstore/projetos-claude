import re

# Captura padrões no final: "NOME (COR) (TAM)" (com espaços)
# Ex.: BODY ADRIANA (PRETO) (P)
RX = re.compile(r"^(?P<base>.+?)\s*\((?P<color>[^()]*)\)\s*\((?P<size>[^()]*)\)\s*$")

def parse_name(full_name: str) -> dict:
    """
    Retorna:
      base_name: nome do modelo (sem cor/tamanho)
      color: cor (ou None)
      size: tamanho (ou None)
      ok: bool (parse reconhecido)
    """
    name = (full_name or "").strip()
    m = RX.match(name)
    if not m:
        return {"base_name": name, "color": None, "size": None, "ok": False}

    base = (m.group("base") or "").strip()
    color = (m.group("color") or "").strip()
    size = (m.group("size") or "").strip()

    # normalizações leves (sem inventar regra demais)
    color = " ".join(color.split()).upper() if color else None
    size = " ".join(size.split()).upper() if size else None

    return {"base_name": base, "color": color, "size": size, "ok": True}
