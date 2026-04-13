from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt


def oauth_callback(request):
    return HttpResponse('OK')


@csrf_exempt
def webhook(request):
    return HttpResponse('OK')
