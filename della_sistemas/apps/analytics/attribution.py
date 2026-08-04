"""Classificacao de origem de trafego (utm_source + fallback por click id).

Usado tanto pelo dashboard ao vivo (_calcular_origens) quanto pelo relatorio
semanal em PDF (gerar_relatorio_semanal) -- manter uma unica implementacao
evita que os dois divirjam (aconteceu ate 2026-07-08: sessao com fbclid e
sem utm_source aparecia como "Meta" no dashboard e "Direto / Outros" no
relatorio semanal).
"""


def label_origem(source: str, tem_fbclid: bool = False, tem_gclid: bool = False) -> str:
    s = (source or '').lower().strip()
    if 'google' in s:
        return 'Google'
    if s in ('ig', 'instagram') or 'instagram' in s:
        return 'Instagram'
    if s in ('fb', 'facebook') or 'facebook' in s:
        return 'Facebook'
    if 'meta' in s:
        return 'Meta'
    if 'whatsapp' in s or 'wapp' in s:
        return 'WhatsApp'
    if s:
        return s.capitalize()
    # Sem utm_source: o click id revela a origem paga do clique.
    if tem_fbclid:
        return 'Meta'
    if tem_gclid:
        return 'Google'
    return 'Direto / Outros'
