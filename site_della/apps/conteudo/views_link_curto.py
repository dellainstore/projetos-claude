"""Encurtador de link (dellainstore.com/l/<codigo>).

Duas views:
- `criar_link_curto`: endpoint interno, chamado so pelo della_sistemas
  (Site > Gerar link), autenticado por segredo compartilhado no header.
  Nunca exposto para navegador nem para cliente final.
- `abrir_link_curto`: publica, redireciona qualquer visitante para o destino.

Ver o modelo `LinkCurto` (apps/conteudo/models.py) para o porque de nao
precisar de nenhum evento de analytics extra: o redirect e transparente e a
UTM ja vai embutida em `destino`.
"""

import hashlib
import hmac
import json
import secrets

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.conteudo.models import LinkCurto

# Sem 0/O e sem 1/l/I: dois desses caracteres lado a lado num link ditado por
# telefone ou reescrito a mao (raro, mas acontece) e o motivo classico de
# link curto "quebrado". 6 caracteres nesse alfabeto = 32 bilhoes de
# combinacoes, folga enorme para o volume desta loja.
_ALFABETO = '23456789abcdefghijkmnpqrstuvwxyz'
_TAMANHO_CODIGO = 6


def _gerar_codigo() -> str:
    return ''.join(secrets.choice(_ALFABETO) for _ in range(_TAMANHO_CODIGO))


def _segredo_valido(request) -> bool:
    recebido = request.META.get('HTTP_X_LINK_CURTO_SECRET', '')
    esperado = settings.LINK_CURTO_SECRET
    if not esperado:
        return False
    # compare_digest: mesma tecnica do HMAC de webhook do Bling, evita timing
    # attack (comparação char-a-char normal vaza quanto do segredo bateu).
    return hmac.compare_digest(recebido, esperado)


@csrf_exempt
@require_POST
def criar_link_curto(request):
    """Cria (ou reaproveita) um link curto para `destino`.

    So aceita destino do proprio site: o endpoint e protegido por segredo,
    mas a validacao de dominio fica como segunda camada — um link curto
    nosso nunca deve conseguir apontar para fora do dellainstore.com.
    """
    if not _segredo_valido(request):
        return HttpResponse(status=403)

    try:
        payload = json.loads(request.body or b'{}')
        destino = str(payload.get('destino', '')).strip()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'erro': 'corpo invalido'}, status=400)

    if not destino or 'dellainstore.com' not in destino:
        return JsonResponse({'erro': 'destino invalido'}, status=400)
    if len(destino) > 600:
        return JsonResponse({'erro': 'destino muito longo'}, status=400)

    # Idempotente independente de quem chama: se ja existe um link curto
    # exatamente para esse destino, devolve o mesmo em vez de criar outro.
    existente = LinkCurto.objects.filter(destino=destino).first()
    if existente:
        return JsonResponse({
            'codigo': existente.codigo,
            'url': f'{settings.SITE_URL}/l/{existente.codigo}',
            'reaproveitado': True,
        })

    for _ in range(6):
        try:
            novo = LinkCurto.objects.create(codigo=_gerar_codigo(), destino=destino)
            break
        except IntegrityError:
            continue  # colisao rarissima de codigo; tenta outro
    else:
        return JsonResponse({'erro': 'nao foi possivel gerar codigo'}, status=500)

    return JsonResponse({
        'codigo': novo.codigo,
        'url': f'{settings.SITE_URL}/l/{novo.codigo}',
        'reaproveitado': False,
    })


@require_GET
def abrir_link_curto(request, codigo):
    """Redireciona /l/<codigo>/ para o destino, contando o clique."""
    link = get_object_or_404(LinkCurto, codigo=codigo)
    LinkCurto.objects.filter(pk=link.pk).update(cliques=F('cliques') + 1)
    return redirect(link.destino)
