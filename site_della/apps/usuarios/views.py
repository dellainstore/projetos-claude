from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Cliente, Endereco
from .forms import (
    LoginForm, CadastroForm, EditarPerfilForm,
    EnderecoForm, RecuperarSenhaForm, NovaSenhaForm, AtivacaoForm,
)


def _contexto_cadastro_pendente(usuario):
    campos_pendentes = usuario.campos_pendentes_cadastro() if usuario.is_authenticated else []
    return {
        'campos_pendentes_cadastro': campos_pendentes,
        'cadastro_incompleto': bool(campos_pendentes),
    }


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
        # Verifica CPF antes da validação completa do form — assim funciona mesmo
        # que o e-mail já exista no banco (cliente importado tentando se cadastrar)
        import re as _re
        cpf_raw = _re.sub(r'\D', '', request.POST.get('cpf', ''))
        if cpf_raw:
            try:
                cliente_existente = Cliente.objects.get(cpf=cpf_raw, precisa_ativar=True)
                uid = urlsafe_base64_encode(force_bytes(cliente_existente.pk))
                token = default_token_generator.make_token(cliente_existente)
                messages.info(
                    request,
                    'Identificamos que você já tem cadastro conosco! '
                    'Confirme seu e-mail e crie uma senha para ativar sua conta.'
                )
                return redirect('usuarios:ativar_conta', uidb64=uid, token=token)
            except Cliente.DoesNotExist:
                pass

        if form.is_valid():
            usuario = form.save()
            login(request, usuario, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Bem-vinda, {usuario.nome}! Sua conta foi criada com sucesso.')
            return redirect('usuarios:minha_conta')

    return render(request, 'usuarios/cadastro.html', {'form': form})


def ativar_conta(request, uidb64, token):
    """Ativação de conta para clientes importados do site antigo."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        cliente = Cliente.objects.get(pk=uid, precisa_ativar=True)
    except (TypeError, ValueError, OverflowError, Cliente.DoesNotExist):
        cliente = None

    token_valido = cliente is not None and default_token_generator.check_token(cliente, token)

    if not token_valido:
        return render(request, 'usuarios/ativar_conta.html', {'token_invalido': True})

    form = AtivacaoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email_informado = form.cleaned_data['email']
        if email_informado != cliente.email:
            form.add_error('email', 'E-mail não confere com o cadastro. Tente o e-mail que você usava antes.')
        else:
            cliente.set_password(form.cleaned_data['senha'])
            cliente.precisa_ativar = False
            cliente.telefone = ''
            cliente.save(update_fields=['password', 'precisa_ativar', 'telefone'])
            cliente.enderecos.all().delete()
            update_session_auth_hash(request, cliente)
            login(request, cliente, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(
                request,
                f'Bem-vinda de volta, {cliente.nome}! '
                'Por favor, atualize seu telefone e endereço de entrega antes de fazer um pedido.'
            )
            return redirect('usuarios:editar_perfil')

    return render(request, 'usuarios/ativar_conta.html', {
        'form': form,
        'cliente': cliente,
    })


# ─── Área do cliente ──────────────────────────────────────────────────────────

@login_required
def minha_conta(request):
    pedidos = request.user.pedidos.all()[:5]
    enderecos = request.user.enderecos.all()[:3]
    context = {
        'pedidos': pedidos,
        'enderecos': enderecos,
    }
    context.update(_contexto_cadastro_pendente(request.user))
    return render(request, 'usuarios/minha_conta.html', context)


@login_required
def editar_perfil(request):
    form = EditarPerfilForm(request.POST or None, instance=request.user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil atualizado com sucesso.')
            return redirect('usuarios:editar_perfil')

    context = {'form': form}
    context.update(_contexto_cadastro_pendente(request.user))
    return render(request, 'usuarios/editar_perfil.html', context)


# ─── Endereços ────────────────────────────────────────────────────────────────

@login_required
def enderecos(request):
    lista = request.user.enderecos.all()
    context = {'enderecos': lista}
    context.update(_contexto_cadastro_pendente(request.user))
    return render(request, 'usuarios/enderecos.html', context)


@login_required
def novo_endereco(request):
    form = EnderecoForm(request.POST or None)
    form.instance.cliente = request.user
    if request.method == 'POST':
        if form.is_valid():
            end = form.save(commit=False)
            end.cliente = request.user
            end.save()
            messages.success(request, 'Endereço adicionado.')
            return redirect('usuarios:enderecos')

    context = {'form': form, 'titulo': 'Novo endereço'}
    context.update(_contexto_cadastro_pendente(request.user))
    return render(request, 'usuarios/endereco_form.html', context)


@login_required
def editar_endereco(request, pk):
    endereco = get_object_or_404(Endereco, pk=pk, cliente=request.user)
    form = EnderecoForm(request.POST or None, instance=endereco)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Endereço atualizado.')
            return redirect('usuarios:enderecos')

    context = {
        'form': form,
        'titulo': 'Editar endereço',
        'endereco': endereco,
    }
    context.update(_contexto_cadastro_pendente(request.user))
    return render(request, 'usuarios/endereco_form.html', context)


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
    import logging
    from django.conf import settings as _settings
    logger = logging.getLogger(__name__)

    pedido = get_object_or_404(
        request.user.pedidos.prefetch_related('itens__produto'),
        numero=numero,
    )

    # Gera QR Code Pix para pedidos aguardando pagamento
    pix_qrcode = None
    pix_payload = None
    if pedido.status == 'aguardando_pagamento':
        try:
            from apps.pagamentos.pix import gerar_payload_pix, gerar_qrcode_base64
            chave_pix = getattr(_settings, 'PIX_CHAVE', '')
            if chave_pix:
                pix_payload = gerar_payload_pix(
                    chave=chave_pix,
                    valor=float(pedido.total),
                    nome_recebedor='DELLA INSTORE',
                    cidade='SAO PAULO',
                    txid=pedido.numero.replace('-', ''),
                    descricao=f'Pedido {pedido.numero}',
                )
                pix_qrcode = gerar_qrcode_base64(pix_payload)
        except Exception as e:
            logger.error('Erro ao gerar QR Code Pix no detalhe do usuário: %s', e)

    pagseguro_public_key = ''
    if pedido.status == 'aguardando_pagamento':
        try:
            from apps.pagamentos.services.pagseguro import obter_chave_publica
            pagseguro_public_key = obter_chave_publica()
        except Exception:
            pass

    return render(request, 'usuarios/detalhe_pedido.html', {
        'pedido':               pedido,
        'pix_qrcode':           pix_qrcode,
        'pix_payload':          pix_payload,
        'pagseguro_public_key': pagseguro_public_key,
    })


@login_required
@require_POST
def confirmar_entrega(request, numero):
    """Cliente confirma o recebimento do pedido — muda status para 'entregue'."""
    from apps.pedidos.models import Pedido, HistoricoPedido

    pedido = get_object_or_404(request.user.pedidos, numero=numero)
    if pedido.status != 'enviado':
        messages.error(request, 'Este pedido não pode ser marcado como entregue agora.')
        return redirect('usuarios:detalhe_pedido', numero=numero)

    HistoricoPedido.objects.create(
        pedido=pedido,
        status_anterior=pedido.status,
        status_novo='entregue',
        observacao=f'Recebimento confirmado pelo cliente ({request.user.email})',
    )
    pedido.status = 'entregue'
    pedido.save(update_fields=['status', 'atualizado_em'])
    messages.success(request, 'Recebimento confirmado! Obrigada por comprar com a gente.')
    return redirect('usuarios:detalhe_pedido', numero=numero)


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
