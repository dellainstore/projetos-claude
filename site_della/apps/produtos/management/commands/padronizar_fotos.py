import os
from django.core.management.base import BaseCommand
from apps.produtos.models import ProdutoImagem


class Command(BaseCommand):
    help = 'Redimensiona fotos de produtos para caber em 1200×1600 (Lanczos). Melhora qualidade no desktop.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Apenas mostra o que seria feito, sem salvar')
        parser.add_argument('--max-w', type=int, default=1200, help='Largura máxima (padrão: 1200)')
        parser.add_argument('--max-h', type=int, default=1600, help='Altura máxima (padrão: 1600)')
        parser.add_argument('--somente-pequenas', action='store_true', help='Processa apenas imagens menores que max_w × max_h (só upscale)')

    def handle(self, *args, **options):
        from PIL import Image as PilImage

        dry_run = options['dry_run']
        max_w = options['max_w']
        max_h = options['max_h']
        somente_pequenas = options['somente_pequenas']

        if dry_run:
            self.stdout.write(self.style.WARNING('Modo dry-run — nenhuma alteração será feita.\n'))

        imagens = ProdutoImagem.objects.exclude(imagem='').select_related('produto').order_by('produto__slug', 'ordem')
        total = imagens.count()
        processadas = upscales = downscales = ignoradas = erros = 0

        for img_obj in imagens:
            try:
                path = img_obj.imagem.path
                if not os.path.exists(path):
                    self.stdout.write(self.style.WARNING(f'  ⚠ arquivo não encontrado: {path}'))
                    erros += 1
                    continue

                with PilImage.open(path) as img:
                    w, h = img.size
                    ratio = min(max_w / w, max_h / h)

                    if abs(ratio - 1.0) < 0.02:
                        ignoradas += 1
                        continue

                    if somente_pequenas and ratio < 1.0:
                        ignoradas += 1
                        continue

                    new_w = round(w * ratio)
                    new_h = round(h * ratio)
                    action = 'UP  ' if ratio > 1 else 'DOWN'
                    self.stdout.write(f'  [{action}] {w}×{h} → {new_w}×{new_h}  {os.path.basename(path)}')

                    if not dry_run:
                        fmt = img.format or 'PNG'
                        mode = img.mode
                        resized = img.resize((new_w, new_h), PilImage.LANCZOS)
                        if fmt == 'JPEG':
                            if mode in ('RGBA', 'P'):
                                resized = resized.convert('RGB')
                            resized.save(path, format='JPEG', quality=90, optimize=True)
                        elif fmt == 'PNG':
                            resized.save(path, format='PNG', optimize=True, compress_level=6)
                        elif fmt == 'WEBP':
                            resized.save(path, format='WEBP', quality=90, method=6)
                        else:
                            resized.save(path, format=fmt)

                    processadas += 1
                    if ratio > 1:
                        upscales += 1
                    else:
                        downscales += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ erro em {img_obj}: {e}'))
                erros += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Total no banco: {total} | '
            f'Processadas: {processadas} (↑{upscales} upscale, ↓{downscales} downscale) | '
            f'Ignoradas (já ok): {ignoradas} | '
            f'Erros: {erros}'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('dry-run: nenhuma alteração foi salva.'))
