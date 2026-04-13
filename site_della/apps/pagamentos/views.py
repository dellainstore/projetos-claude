from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def pagseguro_retorno(request):
    return HttpResponse('OK')


@csrf_exempt
def pagseguro_notificacao(request):
    return HttpResponse('OK')


@csrf_exempt
def stone_webhook(request):
    return HttpResponse('OK')


def pix_gerar(request, pedido_numero):
    return JsonResponse({'status': 'ok'})


def pix_status(request, pedido_numero):
    return JsonResponse({'status': 'pending'})
