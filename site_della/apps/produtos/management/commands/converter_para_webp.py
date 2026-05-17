"""
Converte ProdutoImagem para WebP, atualiza o banco e move o original para backup.

Uso tipico:
  # Teste com 2 produtos especificos (mantem original lado a lado para comparar)
  python manage.py converter_para_webp --produto-slug body-segunda-pele --produto-slug saia-lenco \
      --keep-original --quality 90 --settings=core.settings.production

  # Dry-run em todos os produtos
  python manage.py converter_para_webp --dry-run --settings=core.settings.production

  # Rollout completo (move originais para backup)
  python manage.py converter_para_webp --quality 90 --settings=core.settings.production

Caracteristicas:
- Idempotente: pula imagens que ja sao WebP.
- Backup: move o arquivo original para `media/_pre_webp_backup/<mesmo caminho>` (a menos que --keep-original).
- Atualiza o campo `ProdutoImagem.imagem` no banco para o novo path .webp.
- Preserva transparencia automaticamente se PNG era RGBA (usa lossless).
"""

import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.produtos.models import Produto, ProdutoImagem


class Command(BaseCommand):
    help = 'Converte imagens de produto para WebP, atualiza banco e move originais para backup.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Lista o que seria feito, sem alterar nada.')
        parser.add_argument('--produto-slug', action='append', default=[],
                            help='Slug do produto (pode repetir varias vezes). Sem isso, processa todos.')
        parser.add_argument('--quality', type=int, default=90,
                            help='Qualidade WebP lossy (1-100). Default 90.')
        parser.add_argument('--keep-original', action='store_true',
                            help='Mantem o arquivo original ao lado do .webp (nao move para backup). Util para comparar.')
        parser.add_argument('--backup-dir', type=str,
                            default=os.path.join(settings.MEDIA_ROOT, '_pre_webp_backup'),
                            help='Pasta onde mover os originais. Default: media/_pre_webp_backup/')
        parser.add_argument('--force', action='store_true',
                            help='Regenera mesmo se um .webp com mesmo nome ja existe.')

    def handle(self, *args, **opts):
        from PIL import Image as PilImage

        dry = opts['dry_run']
        slugs = opts['produto_slug']
        quality = opts['quality']
        keep_original = opts['keep_original']
        backup_dir = Path(opts['backup_dir'])
        force = opts['force']

        if not (1 <= quality <= 100):
            self.stderr.write(self.style.ERROR('--quality deve estar entre 1 e 100.'))
            return

        if dry:
            self.stdout.write(self.style.WARNING('DRY-RUN: nenhuma alteracao sera feita.\n'))

        # Seleciona imagens a processar
        qs = ProdutoImagem.objects.select_related('produto').exclude(imagem='')
        if slugs:
            qs = qs.filter(produto__slug__in=slugs)
            self.stdout.write(self.style.NOTICE(f'Filtrando para slugs: {slugs}'))

        # Filtra: descarta as que ja sao .webp
        candidatas = []
        for img_obj in qs:
            ext = os.path.splitext(img_obj.imagem.name)[1].lower()
            if ext == '.webp':
                continue
            candidatas.append(img_obj)

        total = len(candidatas)
        if total == 0:
            self.stdout.write(self.style.WARNING('Nenhuma imagem nao-webp encontrada.'))
            return

        self.stdout.write(f'Imagens a processar: {total}')
        if not keep_original and not dry:
            self.stdout.write(f'Backup dos originais sera em: {backup_dir}')

        convertidas = puladas = erros = 0
        bytes_antes = bytes_depois = 0

        for i, img_obj in enumerate(candidatas, 1):
            try:
                old_path = Path(img_obj.imagem.path)
                if not old_path.exists():
                    self.stdout.write(self.style.WARNING(f'  [{i}/{total}] ARQUIVO NAO EXISTE: {old_path}'))
                    erros += 1
                    continue

                new_path = old_path.with_suffix('.webp')

                if new_path.exists() and not force:
                    self.stdout.write(f'  [{i}/{total}] PULA (webp ja existe): {old_path.name}')
                    puladas += 1
                    continue

                with PilImage.open(old_path) as img:
                    sz_antes = old_path.stat().st_size
                    mode = img.mode
                    use_lossless = mode in ('RGBA', 'LA', 'P') and self._has_transparency(img)

                    if dry:
                        kind = 'LOSSLESS' if use_lossless else f'LOSSY q{quality}'
                        self.stdout.write(f'  [{i}/{total}] {kind}: {old_path.name} ({sz_antes/1024:.0f}KB)')
                        bytes_antes += sz_antes
                        continue

                    # Converte modo se necessario para lossy
                    img_to_save = img
                    if not use_lossless and mode not in ('RGB', 'L'):
                        img_to_save = img.convert('RGB')

                    save_kwargs = {'format': 'WEBP', 'method': 6}
                    if use_lossless:
                        save_kwargs['lossless'] = True
                        save_kwargs['quality'] = 100
                    else:
                        save_kwargs['quality'] = quality

                    img_to_save.save(new_path, **save_kwargs)

                sz_depois = new_path.stat().st_size
                bytes_antes += sz_antes
                bytes_depois += sz_depois
                economia_pct = 100 * (1 - sz_depois / sz_antes)

                # Backup do original (a menos que keep_original)
                if not keep_original:
                    rel = old_path.relative_to(Path(settings.MEDIA_ROOT))
                    backup_path = backup_dir / rel
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old_path), str(backup_path))

                # Atualiza o banco
                new_relative = str(new_path.relative_to(Path(settings.MEDIA_ROOT))).replace(os.sep, '/')
                with transaction.atomic():
                    ProdutoImagem.objects.filter(pk=img_obj.pk).update(imagem=new_relative)

                convertidas += 1
                self.stdout.write(
                    f'  [{i}/{total}] OK: {old_path.name} ({sz_antes/1024:.0f}KB) -> '
                    f'{new_path.name} ({sz_depois/1024:.0f}KB) [-{economia_pct:.0f}%]'
                )

            except Exception as e:
                erros += 1
                self.stdout.write(self.style.ERROR(f'  [{i}/{total}] ERRO em {img_obj}: {e}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Total: {total} | Convertidas: {convertidas} | '
            f'Puladas: {puladas} | Erros: {erros}'
        ))
        if bytes_antes:
            economia_total = 100 * (1 - bytes_depois / bytes_antes) if bytes_depois else 0
            self.stdout.write(
                f'Tamanho antes: {bytes_antes/1024/1024:.1f}MB | '
                f'depois: {bytes_depois/1024/1024:.1f}MB | '
                f'economia: -{economia_total:.0f}%'
            )
        if dry:
            self.stdout.write(self.style.WARNING('Dry-run: nenhuma alteracao foi salva.'))

    @staticmethod
    def _has_transparency(img):
        """Verifica se imagem tem pixels transparentes (alpha real)."""
        try:
            if img.mode == 'RGBA':
                # Olha o canal alpha
                alpha = img.split()[-1]
                return any(p < 255 for p in alpha.getdata())
            if img.mode == 'LA':
                alpha = img.split()[-1]
                return any(p < 255 for p in alpha.getdata())
            if img.mode == 'P':
                return 'transparency' in img.info
        except Exception:
            pass
        return False
