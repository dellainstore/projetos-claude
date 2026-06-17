from django.db import migrations


def criar_botoes_iniciais(apps, schema_editor):
    """Popula os 4 botoes fixos atuais da pagina /links.

    Idempotente: so cria se a tabela estiver vazia, para nao duplicar caso o
    admin ja tenha cadastrado algo.
    """
    LinkBio = apps.get_model('conteudo', 'LinkBio')
    if LinkBio.objects.exists():
        return

    botoes = [
        {
            'titulo': 'Loja online',
            'subtitulo': '',
            'url': 'https://www.dellainstore.com/',
            'icone': 'loja',
            'nova_aba': False,
            'ordem': 10,
        },
        {
            'titulo': 'WhatsApp Vendas',
            'subtitulo': '',
            'url': "https://wa.me/5511988879928?text=Olá! Vim pelo Instagram da D'ELLA Instore",
            'icone': 'whatsapp',
            'nova_aba': True,
            'ordem': 20,
        },
        {
            'titulo': 'Show Room (Tina/Sara)',
            'subtitulo': 'Rua Visconde da Luz, 183 - Vila Nova Conceição, SP',
            'url': 'https://www.google.com/maps/search/?api=1&query=Rua+Visconde+da+Luz%2C+183+-+Vila+Nova+Concei%C3%A7%C3%A3o%2C+S%C3%A3o+Paulo+-+SP',
            'icone': 'local',
            'nova_aba': True,
            'ordem': 30,
        },
        {
            'titulo': 'Loja Studio Anacã (Michelle)',
            'subtitulo': 'Av. Brasil, 649 - Jardim Paulista, SP',
            'url': 'https://www.google.com/maps/search/?api=1&query=Av.+Brasil%2C+649+-+Jardim+Paulista%2C+S%C3%A3o+Paulo+-+SP',
            'icone': 'local',
            'nova_aba': True,
            'ordem': 40,
        },
    ]
    for b in botoes:
        LinkBio.objects.create(ativo=True, **b)


def remover_botoes_iniciais(apps, schema_editor):
    # Reversao no-op: nao apaga dados que o admin possa ter editado.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('conteudo', '0019_linkbio_icone_linkbio_nova_aba_linkbio_subtitulo_and_more'),
    ]

    operations = [
        migrations.RunPython(criar_botoes_iniciais, remover_botoes_iniciais),
    ]
