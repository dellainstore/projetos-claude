from django.shortcuts import render, redirect
from django.contrib.auth import login, logout


def login_view(request):
    return render(request, 'usuarios/login.html')


def logout_view(request):
    logout(request)
    return redirect('produtos:home')


def cadastro(request):
    return render(request, 'usuarios/cadastro.html')


def minha_conta(request):
    return render(request, 'usuarios/minha_conta.html')


def editar_perfil(request):
    return render(request, 'usuarios/editar_perfil.html')


def enderecos(request):
    return render(request, 'usuarios/enderecos.html')


def novo_endereco(request):
    return render(request, 'usuarios/endereco_form.html')


def editar_endereco(request, pk):
    return render(request, 'usuarios/endereco_form.html')


def excluir_endereco(request, pk):
    return redirect('usuarios:enderecos')


def recuperar_senha(request):
    return render(request, 'usuarios/recuperar_senha.html')


def confirmar_senha(request, uidb64, token):
    return render(request, 'usuarios/confirmar_senha.html')
