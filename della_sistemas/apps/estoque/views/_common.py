from django.core.paginator import Paginator

PAGE_SIZE = 200


def paginar(request, records: list[dict], *, per_page: int = PAGE_SIZE):
    paginator = Paginator(records, per_page)
    numero = request.GET.get("pagina") or 1
    return paginator.get_page(numero)
