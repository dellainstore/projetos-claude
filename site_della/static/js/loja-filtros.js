/* Filtros da loja: ao trocar categoria/subcategoria, atualiza dropdown de
 * subcategorias e a lista de tamanhos via AJAX. Sem reload de página.
 * Aplicar de fato os filtros aos produtos = clicar em "Filtrar".
 */
(function () {
  'use strict';

  function log(msg, extra) {
    if (extra !== undefined) console.log('[loja-filtros]', msg, extra);
    else console.log('[loja-filtros]', msg);
  }

  function onReady(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  onReady(function () {
    var script    = document.currentScript || document.querySelector('script[data-url-tamanhos]');
    var urlBase   = script ? script.getAttribute('data-url-tamanhos') : '/loja/tamanhos/';
    var catSel    = document.getElementById('filtro-categoria');
    var subcatSel = document.getElementById('filtro-subcategoria');
    var subcatLbl = subcatSel ? subcatSel.previousElementSibling : null;
    var tamDetails = document.querySelector('.sidebar-tam-dropdown');

    log('init', { temCat: !!catSel, temSubcat: !!subcatSel, temTam: !!tamDetails, urlBase: urlBase });

    if (!catSel) {
      log('elemento #filtro-categoria não encontrado — abortando');
      return;
    }

    // Cache das opções originais (preenchido na primeira chamada)
    var allSubcatOptions = null;

    function filtrarSubcats() {
      if (!subcatSel) return;
      var catSlug = catSel.value;

      // Guarda todas as opções na primeira execução
      if (!allSubcatOptions) {
        allSubcatOptions = Array.prototype.slice.call(subcatSel.options).map(function (opt) {
          return { value: opt.value, text: opt.text, parent: opt.getAttribute('data-parent') };
        });
      }

      var prevSelected = subcatSel.value;
      var anyVisible   = false;

      // Remove todas e readiciona apenas as correspondentes
      // (opt.hidden não funciona em selects nativos de iOS/Android)
      while (subcatSel.options.length > 0) subcatSel.remove(0);

      allSubcatOptions.forEach(function (d) {
        var match = !d.value || !catSlug || d.parent === catSlug;
        if (!match) return;
        var o = new Option(d.text, d.value);
        if (d.value) o.setAttribute('data-parent', d.parent);
        subcatSel.add(o);
        if (d.value) anyVisible = true;
      });

      // Restaura seleção anterior se ainda estiver disponível
      subcatSel.value = prevSelected;

      subcatSel.style.display = anyVisible ? '' : 'none';
      if (subcatLbl) subcatLbl.style.display = anyVisible ? '' : 'none';
      log('subcats filtradas cat=' + (catSlug || '(todas)') + ' visiveis=' + anyVisible);
    }

    function renderTamanhos(tamanhos) {
      if (!tamDetails) return;
      var opcoes = tamDetails.querySelector('.sidebar-tam-opcoes');
      if (!opcoes) return;
      opcoes.innerHTML = '';
      if (!tamanhos || !tamanhos.length) {
        tamDetails.style.display = 'none';
        return;
      }
      tamDetails.style.display = '';
      tamanhos.forEach(function (nome) {
        var lbl = document.createElement('label');
        lbl.className = 'sidebar-tam-check-label';
        var input = document.createElement('input');
        input.type = 'checkbox';
        input.name = 'tamanho';
        input.value = nome;
        input.className = 'sr-only sidebar-tam-check';
        var span = document.createElement('span');
        span.className = 'sidebar-tam-caixa';
        lbl.appendChild(input);
        lbl.appendChild(span);
        lbl.appendChild(document.createTextNode(nome));
        opcoes.appendChild(lbl);
      });
      var summary = tamDetails.querySelector('.sidebar-tam-summary');
      var badge = summary && summary.querySelector('.sidebar-tam-badge');
      if (badge) badge.remove();
    }

    function atualizarTamanhos() {
      var cat    = catSel.value;
      var subcat = subcatSel ? subcatSel.value : '';
      var url    = urlBase + '?';
      if (subcat)     url += 'subcategoria=' + encodeURIComponent(subcat);
      else if (cat)   url += 'categoria='    + encodeURIComponent(cat);
      log('atualizarTamanhos -> ' + url);

      var req = new XMLHttpRequest();
      req.open('GET', url, true);
      req.setRequestHeader('Accept', 'application/json');
      req.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
      req.onload = function () {
        if (req.status !== 200) {
          console.warn('[loja-filtros] HTTP ' + req.status + ' em ' + url);
          return;
        }
        try {
          var data = JSON.parse(req.responseText);
          log('tamanhos recebidos', data.tamanhos);
          renderTamanhos(data.tamanhos);
        } catch (e) {
          console.warn('[loja-filtros] resposta nao-JSON em ' + url, req.responseText.slice(0, 200));
        }
      };
      req.onerror = function () {
        console.warn('[loja-filtros] erro de rede em ' + url);
      };
      req.send();
    }

    catSel.addEventListener('change', function () {
      log('categoria mudou para: ' + (catSel.value || '(todas)'));
      if (subcatSel) subcatSel.value = '';
      filtrarSubcats();
      atualizarTamanhos();
      buscarParcial();
    });

    if (subcatSel) {
      subcatSel.addEventListener('change', function () {
        log('subcategoria mudou para: ' + (subcatSel.value || '(todas)'));
        atualizarTamanhos();
        buscarParcial();
      });
    }

    filtrarSubcats(); // inicializa visibilidade de subcategorias

    // ---- Filtros reativos via AJAX parcial ----

    var resultados   = document.getElementById('loja-resultados');
    var formFiltros  = document.getElementById('form-filtros');
    var formOrdem    = document.getElementById('form-ordem');
    var ordemSel     = document.getElementById('select-ordem');
    var abortCtrl    = null;
    var debounce     = null;
    var urlBase      = formFiltros ? (formFiltros.getAttribute('action') || '/loja/') : '/loja/';

    function buildSkeleton() {
      var qtd = resultados ? Math.min(Math.max(resultados.querySelectorAll('.produto-card').length, 6), 12) : 8;
      var html = '<div class="loja-grid">';
      for (var i = 0; i < qtd; i++) {
        html += '<article class="produto-card-skeleton"><div class="skeleton-foto"></div><div class="skeleton-nome"></div><div class="skeleton-preco"></div></article>';
      }
      return html + '</div>';
    }

    function montarUrl() {
      var params = new URLSearchParams();
      if (formFiltros) {
        var fd = new FormData(formFiltros);
        for (var pair of fd.entries()) {
          if (pair[1]) params.append(pair[0], pair[1]);
        }
      }
      if (ordemSel && ordemSel.value) params.set('ordem', ordemSel.value);
      var qs = params.toString();
      return urlBase + (qs ? '?' + qs : '');
    }

    function buscarParcial() {
      if (!resultados || !formFiltros) return;
      if (abortCtrl) abortCtrl.abort();
      abortCtrl = new AbortController();

      resultados.innerHTML = buildSkeleton();

      var url = montarUrl();
      var sep = url.indexOf('?') === -1 ? '?' : '&';
      fetch(url + sep + '_partial=1', {
        signal: abortCtrl.signal,
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(function (html) {
        if (resultados) resultados.innerHTML = html;
        history.replaceState(null, '', url);
      })
      .catch(function (e) {
        if (e.name !== 'AbortError') {
          log('fetch parcial falhou, recarregando', e);
          window.location = url;
        }
      });
    }

    // Checkboxes de tamanho (renderizados dinamicamente): delegação no form
    formFiltros && formFiltros.addEventListener('change', function (e) {
      var el = e.target;
      if (el === catSel || el === subcatSel) return; // ja tratados acima
      if (el.type === 'number') return;               // tratado pelo debounce
      buscarParcial();
    });

    // Preços: debounce de 700ms
    formFiltros && formFiltros.addEventListener('input', function (e) {
      if (e.target.type !== 'number') return;
      clearTimeout(debounce);
      debounce = setTimeout(buscarParcial, 700);
    });

    // Ordenação: intercepta antes do della.js chamar form.submit()
    if (ordemSel) {
      ordemSel.addEventListener('change', function (e) {
        e.stopImmediatePropagation(); // impede della.js de submeter o form nativamente
        buscarParcial();
      });
    }

    // Botão "Filtrar": continua funcionando, mas via AJAX
    formFiltros && formFiltros.addEventListener('submit', function (e) {
      e.preventDefault();
      buscarParcial();
    });

    log('listeners registrados (modo reativo)');
  });
})();
