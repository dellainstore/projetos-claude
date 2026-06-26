from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def perm_required(perm: str):
    """Verifica permissão granular 'modulo.chave'."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("core:login")
            if not request.user.tem_perm(perm):
                messages.error(request, "Você não tem permissão para acessar esta página.")
                return redirect("core:home")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def papel_required(*papeis):
    """Legado: verifica papel. Novos recursos devem usar perm_required()."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("core:login")
            if not request.user.tem_perm("admin.usuarios") and request.user.papel not in papeis:
                messages.error(request, "Você não tem permissão para acessar esta página.")
                return redirect("core:home")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def login_obrigatorio(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("core:login")
        return view_func(request, *args, **kwargs)
    return wrapper
