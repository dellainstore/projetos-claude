// Persiste scroll vertical da changelist de CorPadrao ao navegar entre linhas.
(function () {
  'use strict';
  var STORAGE_KEY = 'admin_corpadrao_changelist_scroll';

  function salvarScroll() {
    sessionStorage.setItem(STORAGE_KEY, String(window.scrollY || window.pageYOffset || 0));
  }

  document.addEventListener('DOMContentLoaded', function () {
    var saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved !== null) {
      window.scrollTo(0, parseInt(saved, 10) || 0);
      sessionStorage.removeItem(STORAGE_KEY);
    }

    document.querySelectorAll('#result_list a, .field-acoes_linha a').forEach(function (link) {
      link.addEventListener('click', salvarScroll);
    });

    window.addEventListener('beforeunload', salvarScroll);
  });
})();
