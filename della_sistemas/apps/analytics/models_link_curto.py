"""Historico de links gerados em Site > Gerar link.

Separado de `models.py` porque este e um modelo GERENCIADO (tabela propria no
db.sqlite3 do della_sistemas), diferente dos demais modelos de `apps.analytics`,
que sao todos espelhos somente-leitura do banco do site_della (managed=False).
Migration normal (makemigrations/migrate), diferente do resto do app.

Guarda so o que o site_della nao sabe e nao precisa saber: quem gerou o link e
quando, do lado do della_sistemas. O site_della guarda so codigo -> destino,
sem nome de usuario nenhum (ver apps/conteudo/models.py::LinkCurto la).
"""

from django.conf import settings
from django.db import models


class LinkGerado(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='links_gerados',
    )
    # Chave de reaproveitamento: gerar de novo o MESMO destino (pagina + canal
    # + nome opcional) devolve o link ja existente em vez de criar outro. E
    # assim que "perder o link e gerar de novo" recupera o mesmo endereco.
    # E tambem o que o site_della usa como alvo do redirect /l/<codigo>/.
    destino   = models.URLField('Destino (com UTM)', max_length=600, unique=True)
    # So para exibir no historico: o link exatamente como a pessoa colou, sem
    # a UTM anexada. `destino` (acima) e feio de ler numa lista ("Cris gerou
    # PARA ONDE?") — ninguem quer ver query string, quer ver a pagina.
    pagina    = models.URLField('Pagina (sem UTM)', max_length=600, blank=True)
    canal     = models.CharField('Canal', max_length=60)
    url_curta = models.URLField('Link curto', max_length=300, blank=True)
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        app_label = 'analytics'
        ordering = ['-criado_em']
        verbose_name = 'Link Gerado'
        verbose_name_plural = 'Links Gerados'

    def __str__(self):
        return f'{self.canal} -> {self.destino[:60]}'
