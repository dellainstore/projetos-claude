"""
Backend de autenticação que aceita e-mail OU CPF como identificador.
- Se o valor só tem dígitos (>= 11), tenta CPF.
- Caso contrário (ou além disso), tenta e-mail.
"""
import re
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOuCPFBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        Cliente = get_user_model()
        identificador = username.strip()

        # Normaliza: só dígitos para comparação por CPF
        digitos = re.sub(r'\D', '', identificador)

        usuario = None
        if len(digitos) == 11:
            try:
                usuario = Cliente.objects.get(cpf=digitos)
            except Cliente.DoesNotExist:
                usuario = None

        if usuario is None:
            try:
                usuario = Cliente.objects.get(email__iexact=identificador)
            except Cliente.DoesNotExist:
                usuario = None

        if usuario and usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
