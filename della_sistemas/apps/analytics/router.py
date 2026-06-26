class DellaSiteRouter:
    """Roteia leituras dos modelos analytics_site para o banco della_site (somente leitura)."""

    APP_LABEL = 'analytics_site'
    DB_ALIAS = 'della_site'

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.APP_LABEL:
            return self.DB_ALIAS
        return None

    def db_for_write(self, model, **hints):
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if (obj1._meta.app_label == self.APP_LABEL
                or obj2._meta.app_label == self.APP_LABEL):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == self.APP_LABEL:
            return False
        return None
