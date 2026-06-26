from django.contrib.auth.backends import ModelBackend
from apps.core.models import User


class CaseInsensitiveBackend(ModelBackend):
    """Permite login com qualquer capitalização do usuário (neto, Neto, NETO)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
