"""
Migration 0005 — Criação dos modelos CorPadrao e TamanhoPadrao.

Estratégia com dados existentes:
  1. Cria as tabelas CorPadrao e TamanhoPadrao
  2. Adiciona campos FK temporários (cor_ref, tamanho_ref) na Variacao
  3. Data migration: lê os textos antigos, cria CorPadrao/TamanhoPadrao e preenche FKs
  4. Remove campos antigos (cor CharField, tamanho CharField, codigo_hex)
  5. Renomeia cor_ref → cor, tamanho_ref → tamanho
"""
from django.db import migrations, models
import django.db.models.deletion


def migrar_dados(apps, schema_editor):
    """Cria CorPadrao e TamanhoPadrao a partir dos textos existentes em Variacao."""
    Variacao = apps.get_model('produtos', 'Variacao')
    CorPadrao = apps.get_model('produtos', 'CorPadrao')
    TamanhoPadrao = apps.get_model('produtos', 'TamanhoPadrao')

    cores_cache = {}
    tamanhos_cache = {}
    ordem_cor = 0
    ordem_tam = 0

    for var in Variacao.objects.select_related().all():
        # ── Cor ──────────────────────────────────────────────────────────────
        cor_texto = (var.cor or '').strip()
        if cor_texto:
            chave = cor_texto.lower()
            if chave not in cores_cache:
                cor_obj, _ = CorPadrao.objects.get_or_create(
                    nome=cor_texto.title(),
                    defaults={
                        'codigo_hex': getattr(var, 'codigo_hex', '') or '',
                        'ordem': ordem_cor,
                    },
                )
                cores_cache[chave] = cor_obj
                ordem_cor += 1
            var.cor_ref = cores_cache[chave]

        # ── Tamanho ──────────────────────────────────────────────────────────
        tam_texto = (var.tamanho or '').strip()
        if tam_texto:
            chave = tam_texto.upper()
            if chave not in tamanhos_cache:
                tam_obj, _ = TamanhoPadrao.objects.get_or_create(
                    nome=tam_texto.upper(),
                    defaults={'ordem': ordem_tam},
                )
                tamanhos_cache[chave] = tam_obj
                ordem_tam += 1
            var.tamanho_ref = tamanhos_cache[chave]

        var.save()


class Migration(migrations.Migration):

    dependencies = [
        ('produtos', '0004_alter_variacao_options_and_more'),
    ]

    operations = [
        # ── 1. Cria os novos modelos ──────────────────────────────────────────
        migrations.CreateModel(
            name='CorPadrao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=50, unique=True, verbose_name='Nome da cor')),
                ('codigo_hex', models.CharField(blank=True, max_length=7, verbose_name='Código hex')),
                ('ordem', models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')),
            ],
            options={
                'verbose_name': 'Cor padrão',
                'verbose_name_plural': 'Cores padrão',
                'ordering': ['ordem', 'nome'],
            },
        ),
        migrations.CreateModel(
            name='TamanhoPadrao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=20, unique=True, verbose_name='Tamanho')),
                ('ordem', models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')),
            ],
            options={
                'verbose_name': 'Tamanho padrão',
                'verbose_name_plural': 'Tamanhos padrão',
                'ordering': ['ordem', 'nome'],
            },
        ),

        # ── 2. Adiciona FKs temporárias (nullable) na Variacao ────────────────
        migrations.AddField(
            model_name='variacao',
            name='cor_ref',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='produtos.corpadrao',
                verbose_name='Cor',
            ),
        ),
        migrations.AddField(
            model_name='variacao',
            name='tamanho_ref',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='produtos.tamanhopadrao',
                verbose_name='Tamanho',
            ),
        ),

        # ── 3. Data migration ─────────────────────────────────────────────────
        migrations.RunPython(migrar_dados, migrations.RunPython.noop),

        # ── 4. Remove campos antigos ──────────────────────────────────────────
        migrations.RemoveField(model_name='variacao', name='cor'),
        migrations.RemoveField(model_name='variacao', name='tamanho'),
        migrations.RemoveField(model_name='variacao', name='codigo_hex'),

        # ── 5. Renomeia cor_ref → cor, tamanho_ref → tamanho ─────────────────
        migrations.RenameField(model_name='variacao', old_name='cor_ref', new_name='cor'),
        migrations.RenameField(model_name='variacao', old_name='tamanho_ref', new_name='tamanho'),

        # ── 6. Ajusta Meta.ordering ───────────────────────────────────────────
        migrations.AlterModelOptions(
            name='variacao',
            options={
                'ordering': ['cor__ordem', 'cor__nome', 'tamanho__ordem', 'tamanho__nome'],
                'verbose_name': 'Variação',
                'verbose_name_plural': 'Variações',
            },
        ),
    ]
