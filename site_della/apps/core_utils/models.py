from django.db import models


class AcessoMonitoramento(models.Model):
    """Modelo sem tabela — existe só para hospedar a permissão de acesso ao
    painel de Monitoramento.

    managed=False não cria tabela; o Django ainda cria o ContentType e a
    Permission `core_utils.ver_monitoramento` no post_migrate. As views e o
    menu checam essa permissão (superusuário a possui implicitamente).
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ('ver_monitoramento', 'Pode acessar o painel de Monitoramento'),
        ]
        verbose_name = 'Acesso ao Monitoramento'
        verbose_name_plural = 'Acesso ao Monitoramento'
