from whitenoise.storage import CompressedManifestStaticFilesStorage


class WhiteNoiseManifestStorageLeniente(CompressedManifestStaticFilesStorage):
    """
    Igual ao storage do WhiteNoise, mas não quebra a página quando um
    {% static %} referencia um arquivo que ainda não foi enviado (ex:
    placeholders de OG image). Para arquivos existentes continua gerando
    nomes com hash — o cache-busting automático segue funcionando.
    """
    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            return name
