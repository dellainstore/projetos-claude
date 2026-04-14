from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.http import JsonResponse

from .models import Cliente, Endereco
from .forms import (
    LoginForm, CadastroForm, EditarPerfilForm,
    EnderecoForm, RecuperarSenhaForm, NovaSenhaForm,
)


# ─── Autenticação ─────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('usuarios:minha_conta')

    form = LoginForm(request=request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            usuario = form.get_usuario()
            login(request, usuario)
            if not request.POST.get('lembrar'):
                # sessão expira ao fechar o browser
                request.session.set_expiry(0)
            next_url = request.GET.get('next', '')
            # segurança: só redirecionar para URLs relativas
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('usuarios:minha_conta')

    return render(request, 'usuarios/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('produtos:home')


def cadastro(request):
    if request.user.is_authenticated:
        return redirect('usuarios:minha_conta')

    form = CadastroForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            usuario = form.save()
            login(request, usuario, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Bem-vinda, {usuario.nome}! Sua conta foi criada com sucesso.')
            return redirect('usuarios:minha_conta')

    return render(request, 'usuarios/cadastro.html', {'form': form})


# ─── Área do cliente ──────────────────────────────────────────────────────────

@login_required
def minha_conta(request):
    pedidos = request.user.pedidos.all()[:5]
    enderecos = request.user.enderecos.all()[:3]
    context = {
        'pedidos': pedidos,
        'enderecos': enderecos,
    }
    return render(request, 'usuarios/minha_conta.html', context)


@login_required
def editar_perfil(request):
    form = EditarPerfilForm(request.POST or None, instance=request.user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil atualizado com sucesso.')
            return redirect('usuarios:editar_perfil')

    return render(request, 'usuarios/editar_perfil.html', {'form': form})


# ─── Endereços ────────────────────────────────────────────────────────────────

@login_required
def enderecos(request):
    lista = request.user.enderecos.all()
    return render(request, 'usuarios/enderecos.html', {'enderecos': lista})


@login_required
def novo_endereco(request):
    form = EnderecoForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            end = form.save(commit=False)
            end.cliente = request.user
            end.save()
            messages.success(request, 'Endereço adicionado.')
            return redirect('usuarios:enderecos')

    return render(request, 'usuarios/endereco_form.html', {'form': form, 'titulo': 'Novo endereço'})


@login_required
def editar_endereco(request, pk):
    endereco = get_object_or_404(Endereco, pk=pk, cliente=request.user)
    form = EnderecoForm(request.POST or None, instance=endereco)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Endereço atualizado.')
            return redirect('usuarios:enderecos')

    return render(request, 'usuarios/endereco_form.html', {
        'form': form,
        'titulo': 'Editar endereço',
        'endereco': endereco,
    })


@login_required
def excluir_endereco(request, pk):
    endereco = get_object_or_404(Endereco, pk=pk, cliente=request.user)
    if request.method == 'POST':
        endereco.delete()
        messages.success(request, 'Endereço removido.')
    return redirect('usuarios:enderecos')


@login_required
def definir_principal(request, pk):
    endereco = get_object_or_404(Endereco, pk=pk, cliente=request.user)
    # desativa todos, ativa este
    request.user.enderecos.update(principal=False)
    endereco.principal = True
    endereco.save(update_fields=['principal'])
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    messages.success(request, 'Endereço principal atualizado.')
    return redirect('usuarios:enderecos')


# ─── Histórico de pedidos ─────────────────────────────────────────────────────

@login_required
def meus_pedidos(request):
    pedidos = request.user.pedidos.all()
    return render(request, 'usuarios/meus_pedidos.html', {'pedidos': pedidos})


@login_required
def detalhe_pedido(request, numero):
    pedido = get_object_or_404(
        request.user.pedidos.prefetch_related('itens__produto'),
        numero=numero,
    )
    return render(request, 'usuarios/detalhe_pedido.html', {'pedido': pedido})


# ─── Recuperação de senha ─────────────────────────────────────────────────────

def recuperar_senha(request):
    form = RecuperarSenhaForm(request.POST or None)
    enviado = False

    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        try:
            usuario = Cliente.objects.get(email=email)
        except Cliente.DoesNotExist:
            usuario = None

        if usuario:
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            token = default_token_generator.make_token(usuario)
            link = request.build_absolute_uri(
                f'/conta/recuperar-senha/confirmar/{uid}/{token}/'
            )
            try:
                from .emails import enviar_recuperacao_senha
                enviar_recuperacao_senha(usuario, link)
            except Exception:
                pass  # falha silenciosa — não revela se e-mail existe

        enviado = True  # sempre mostrar tela de confirmação (evita enumerar e-mails)

    return render(request, 'usuarios/recuperar_senha.html', {'form': form, 'enviado': enviado})


def confirmar_senha(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        usuario = Cliente.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Cliente.DoesNotExist):
        usuario = None

    token_valido = usuario is not None and default_token_generator.check_token(usuario, token)

    if not token_valido:
        return render(request, 'usuarios/confirmar_senha.html', {'token_invalido': True})

    form = NovaSenhaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario.set_password(form.cleaned_data['senha'])
        usuario.save()
        # mantém a sessão ativa após a troca de senha
        update_session_auth_hash(request, usuario)
        messages.success(request, 'Senha redefinida com sucesso. Faça login.')
        return redirect('usuarios:login')

    return render(request, 'usuarios/confirmar_senha.html', {'form': form})
