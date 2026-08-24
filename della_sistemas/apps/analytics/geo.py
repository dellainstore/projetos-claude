"""Distribuicao geografica dos visitantes do site.

Cidade e estado sao resolvidos no site_della no momento da visita, a partir do
IP e da base GeoLite2, e so o resultado e gravado: o IP nunca e persistido (ver
apps/analytics/services.py::_resolver_geo no site_della).

O painel conta VISITANTES, nao paginas vistas. Uma unica cliente pode gerar
dezenas de paginas numa sessao (o recorde observado foi 75), o que faria uma
pessoa muito engajada pesar como dezenas de visitantes de anuncio e distorcer
qualquer comparacao entre cidades.
"""

from django.db.models import Count

from apps.analytics.trafego import UF_BRASIL

# Nome por extenso, para a tela nao mostrar so a sigla.
NOMES_UF = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas',
    'BA': 'Bahia', 'CE': 'Ceará', 'DF': 'Distrito Federal',
    'ES': 'Espírito Santo', 'GO': 'Goiás', 'MA': 'Maranhão',
    'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais',
    'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná', 'PE': 'Pernambuco',
    'PI': 'Piauí', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
    'RS': 'Rio Grande do Sul', 'RO': 'Rondônia', 'RR': 'Roraima',
    'SC': 'Santa Catarina', 'SP': 'São Paulo', 'SE': 'Sergipe',
    'TO': 'Tocantins',
}

def visitantes_por_estado(sessoes_qs):
    """Os 27 estados com contagem de visitantes, prontos para o mapa.

    Recebe um queryset de SessaoSite ja filtrado por periodo e por trafego
    real. Devolve tambem os estados zerados, que o mapa desenha em cinza: um
    estado ausente do mapa se confundiria com erro de renderizacao.
    """
    from apps.analytics.mapa_brasil import PATHS_UF

    brutos = dict(
        sessoes_qs
        .filter(estado__in=UF_BRASIL)
        .values_list('estado')
        .annotate(t=Count('id'))
        .values_list('estado', 't')
    )
    maior = max(brutos.values()) if brutos else 0

    estados = []
    for uf in sorted(NOMES_UF):
        total = brutos.get(uf, 0)
        estados.append({
            'uf': uf,
            'nome': NOMES_UF[uf],
            'total': total,
            # 0 a 4: faixa de cor. Escala pela raiz, e nao linear, para o
            # segundo colocado nao sumir quando Sao Paulo concentra a maior
            # parte do volume (354 de 1.111 visitantes em agosto/2026).
            'nivel': 0 if not total or not maior else min(4, int((total / maior) ** 0.5 * 4) + 1),
            'path': PATHS_UF.get(uf, ''),
        })
    return sorted(estados, key=lambda e: -e['total'])


# Como regerar os contornos em apps/analytics/mapa_brasil.py, caso o IBGE mude
# a malha ou seja preciso outra tolerancia de simplificacao:
#
#   curl -o uf.json "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR\
#   ?formato=application/vnd.geo+json&intrarregiao=UF&qualidade=intermediaria"
#
# e rodar sobre esse GeoJSON: Douglas-Peucker com tolerancia 0,035 grau,
# projecao linear para viewBox de 1000 de largura, codigo IBGE (`codarea`)
# traduzido para sigla. A malha completa tem 251 KB; simplificada fica em 39 KB,
# que e o que vai no HTML de cada carregamento do painel.


def top_cidades(sessoes_qs, limite=12):
    """Cidades com mais visitantes, com a barra relativa ja calculada."""
    linhas = list(
        sessoes_qs
        .filter(estado__in=UF_BRASIL)
        .exclude(cidade='')
        .values('cidade', 'estado')
        .annotate(total=Count('id'))
        .order_by('-total')[:limite]
    )
    maior = linhas[0]['total'] if linhas else 0
    for linha in linhas:
        linha['pct_barra'] = round(linha['total'] / maior * 100) if maior else 0
    return linhas


def resumo_dispositivo(sessoes_qs):
    """Celular, computador e tablet, com percentual."""
    rotulos = {'mobile': 'Celular', 'desktop': 'Computador', 'tablet': 'Tablet'}
    brutos = dict(
        sessoes_qs.values_list('dispositivo').annotate(t=Count('id')).values_list('dispositivo', 't')
    )
    total = sum(brutos.values()) or 1
    return [
        {'rotulo': rotulos.get(chave, chave or 'Outro'), 'total': valor,
         'pct': round(valor / total * 100)}
        for chave, valor in sorted(brutos.items(), key=lambda x: -x[1])
        if valor
    ]
