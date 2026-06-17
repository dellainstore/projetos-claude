"""
Converte imagens de banners e conteudo editorial para WebP.

Cobre: BannerPrincipal (foto + foto_mobile), MiniBanner (foto), LookSemana (foto).

Uso:
  # Teste sem alterar nada
  python manage.py converter_banners_webp --dry-run --settings=core.settings.production

  # Rollout (move originais para backup)
  python manage.py converter_banners_webp --quality 85 --settings=core.settings.production
"""

import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Converte imagens de banners/conteudo para WebP e atualiza o banco.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Lista o que seria feito sem alterar nada.')
        parser.add_argument('--quality', type=int, default=85,
                            help='Qualidade WebP lossy (1-100). Default 85.')
        parser.add_argument('--keep-original', action='store_true',
                            help='Mantem o arquivo original ao lado do .webp (nao move para backup).')
        parser.add_argument('--backup-dir', type=str,
                            default=os.path.join(settings.MEDIA_ROOT, '_pre_webp_backup'),
                            help='Pasta onde mover os originais.')

    def handle(self, *args, **opts):
        from PIL import Image as PilImage
        from apps.conteudo.models import BannerPrincipal, MiniBanner, LookDaSemana

        dry = opts['dry_run']
        quality = opts['quality']
        keep_original = opts['keep_original']
        backup_dir = Path(opts['backup_dir'])

        if dry:
            self.stdout.write(self.style.WARNING('--- DRY-RUN: nenhum arquivo sera alterado ---\n'))

        targets = []

        for banner in BannerPrincipal.objects.all():
            if banner.foto:
                targets.append((banner, 'foto', banner.foto))
            if banner.foto_mobile:
                targets.append((banner, 'foto_mobile', banner.foto_mobile))

        for mb in MiniBanner.objects.all():
            if mb.foto:
                targets.append((mb, 'foto', mb.foto))

        for look in LookDaSemana.objects.all():
            if look.foto:
                targets.append((look, 'foto', look.foto))

        total = len(targets)
        convertidos = 0
        pulados = 0
        erros = 0

        for obj, field_name, field in targets:
            original_name = field.name
            original_path = Path(settings.MEDIA_ROOT) / original_name

            if not original_path.exists():
                self.stdout.write(self.style.WARNING(f'  SKIP (arquivo nao encontrado): {original_name}'))
                pulados += 1
                continue

            if original_path.suffix.lower() == '.webp':
                self.stdout.write(f'  SKIP (ja e WebP): {original_name}')
                pulados += 1
                continue

            new_name = str(Path(original_name).with_suffix('.webp'))
            new_path = Path(settings.MEDIA_ROOT) / new_name

            size_before = original_path.stat().st_size
            self.stdout.write(
                f'  {obj.__class__.__name__} id={obj.pk} [{field_name}]: '
                f'{original_path.name} ({size_before//1024}KB) -> {new_path.name}'
            )

            if dry:
                convertidos += 1
                continue

            try:
                with PilImage.open(original_path) as img:
                    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                        img_rgb = img.convert('RGBA')
                        img_rgb.save(new_path, 'WEBP', quality=quality, lossless=True)
                    else:
                        img_rgb = img.convert('RGB')
                        img_rgb.save(new_path, 'WEBP', quality=quality)

                size_after = new_path.stat().st_size
                reducao = (1 - size_after / size_before) * 100
                self.stdout.write(self.style.SUCCESS(
                    f'    -> {size_after//1024}KB ({reducao:.0f}% menor)'
                ))

                with transaction.atomic():
                    setattr(obj, field_name, new_name)
                    obj.save(update_fields=[field_name])

                if not keep_original:
                    bkp_path = backup_dir / original_name
                    bkp_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(original_path), str(bkp_path))

                convertidos += 1

            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'    ERRO: {exc}'))
                if new_path.exists():
                    new_path.unlink()
                erros += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Concluido: {convertidos} convertidos | {pulados} pulados | {erros} erros (de {total} total)'
        ))
        if dry:
            self.stdout.write(self.style.WARNING('Rode sem --dry-run para aplicar as conversoes.'))
