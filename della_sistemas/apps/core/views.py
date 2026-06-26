from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .decorators import login_obrigatorio, papel_required
from .models import User


def view_login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", "")
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect("core:home")
        messages.error(request, "Usuário ou senha incorretos.")

    return render(request, "login.html")


@require_POST
def view_logout(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("core:login")


@login_obrigatorio
def view_home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


def _get_stats() -> dict:
    """Lê estatísticas básicas do banco inclusoes.db."""
    try:
        from apps.produtos.services.db import get_conn
        hoje = date.today().strftime("%Y-%m-%d")
        ano_mes = date.today().strftime("%Y-%m")
        with get_conn() as conn:
            pendentes = conn.execute(
                "SELECT COUNT(*) FROM requests WHERE status = 'PENDING'"
            ).fetchone()[0]
            incluidos_hoje = conn.execute(
                "SELECT COUNT(*) FROM stock_moves WHERE date(requested_at,'unixepoch') = ?",
                (hoje,),
            ).fetchone()[0]
            aprovados_mes = conn.execute(
                "SELECT COUNT(*) FROM requests WHERE status = 'IMPLEMENTED'"
                " AND strftime('%Y-%m', datetime(updated_at,'unixepoch')) = ?",
                (ano_mes,),
            ).fetchone()[0]
            total_produtos = conn.execute(
                "SELECT COUNT(*) FROM variants_cache WHERE active = 1"
            ).fetchone()[0]
    except Exception:
        pendentes = incluidos_hoje = aprovados_mes = total_produtos = 0

    return {
        "pendentes": pendentes,
        "incluidos_hoje": incluidos_hoje,
        "aprovados_mes": aprovados_mes,
        "total_produtos": total_produtos,
    }


def _get_ultimas_inclusoes(limit: int = 8) -> list[dict]:
    """Retorna as últimas inclusões formatadas para a tabela do dashboard."""
    try:
        import datetime
        from apps.produtos.services.db import get_conn
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT r.request_id,
                   r.created_by,
                   r.status,
                   r.updated_at,
                   json_extract(r.payload_json, '$.base') AS produto_nome,
                   (SELECT SUM(json_extract(item.value, '$.qty'))
                    FROM json_each(r.payload_json, '$.items') AS item) AS qtd
            FROM requests r
            ORDER BY r.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        resultado = []
        for row in rows:
            ts = row["updated_at"]
            data = datetime.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M") if ts else "-"
            resultado.append({
                "request_id": row["request_id"],
                "produto_nome": row["produto_nome"] or "-",
                "qtd": row["qtd"] or 0,
                "created_by": row["created_by"],
                "status": row["status"],
                "data": data,
            })
        return resultado
    except Exception:
        return []


# ── Gerenciamento de usuários (somente superadmin) ──────────────────────────

@papel_required("superadmin")
def view_usuarios(request: HttpRequest) -> HttpResponse:
    usuarios = User.objects.all().order_by("username")
    return render(request, "usuarios.html", {"usuarios": usuarios})


@papel_required("superadmin")
def view_usuario_criar(request: HttpRequest) -> HttpResponse:
    from apps.core.permissions import PERMISSION_TREE

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        nome = request.POST.get("nome", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Nome de usuário já existe.")
        elif not password:
            messages.error(request, "Senha é obrigatória.")
        else:
            novas_permissoes = {}
            for grupo in PERMISSION_TREE:
                gid = grupo["id"]
                novas_permissoes[gid] = {}
                for p in grupo["perms"]:
                    pid = p["id"]
                    novas_permissoes[gid][pid] = (request.POST.get(f"perm_{gid}__{pid}") == "1")

            is_admin = novas_permissoes.get("admin", {}).get("usuarios", False)
            partes = nome.split(" ", 1)
            u = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=partes[0],
                last_name=partes[1] if len(partes) > 1 else "",
                papel="superadmin" if is_admin else "operador",
                is_staff=is_admin,
                permissoes=novas_permissoes,
            )
            messages.success(request, f"Usuário {username} criado com sucesso.")
            return redirect("core:usuarios")

    return render(request, "usuario_form.html", {"acao": "Criar", "permission_tree": PERMISSION_TREE})


@papel_required("superadmin")
def view_usuario_editar(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.core.permissions import PERMISSION_TREE
    usuario = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        nome = request.POST.get("nome", "")
        partes = nome.split(" ", 1)
        usuario.first_name = partes[0]
        usuario.last_name = partes[1] if len(partes) > 1 else ""
        usuario.email = request.POST.get("email", "").strip()
        nova_senha = request.POST.get("password", "")
        if nova_senha:
            usuario.set_password(nova_senha)

        # Salva permissões granulares a partir dos checkboxes
        novas_permissoes = {}
        for grupo in PERMISSION_TREE:
            gid = grupo["id"]
            novas_permissoes[gid] = {}
            for p in grupo["perms"]:
                pid = p["id"]
                chave = f"perm_{gid}__{pid}"
                novas_permissoes[gid][pid] = (request.POST.get(chave) == "1")

        usuario.permissoes = novas_permissoes
        # papel legado: inferido das permissões de admin
        usuario.papel = "superadmin" if novas_permissoes.get("admin", {}).get("usuarios") else "gestor"
        usuario.is_staff = novas_permissoes.get("admin", {}).get("usuarios", False)
        usuario.save()
        messages.success(request, f"Usuário {usuario.username} atualizado.")
        return redirect("core:usuarios")

    from apps.core.permissions import PERMISSION_TREE
    return render(request, "usuario_form.html", {
        "acao": "Editar",
        "usuario": usuario,
        "permission_tree": PERMISSION_TREE,
    })


@papel_required("superadmin")
def view_usuario_desativar(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method == "POST":
        usuario = get_object_or_404(User, pk=pk)
        if usuario == request.user:
            messages.error(request, "Você não pode desativar sua própria conta.")
        else:
            usuario.is_active = not usuario.is_active
            usuario.save()
            estado = "ativado" if usuario.is_active else "desativado"
            messages.success(request, f"Usuário {usuario.username} {estado}.")
    return redirect("core:usuarios")
