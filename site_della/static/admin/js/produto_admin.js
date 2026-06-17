(function () {
  'use strict';

  var FORM_SCROLL_KEY = 'della_produto_admin_scroll:' + window.location.pathname;

  // Cache de data: URLs gerados pelo FileReader para preview sem depender de blob: no CSP
  var dataUrlCache = {};

  function debounce(fn, wait) {
    var timeoutId = null;
    return function () {
      var args = arguments;
      clearTimeout(timeoutId);
      timeoutId = window.setTimeout(function () {
        fn.apply(null, args);
      }, wait);
    };
  }

  function getInlineRow(input) {
    return input.closest('tr') || input.closest('.inline-related');
  }

  function getVariationGroup() {
    return document.getElementById('variacoes-group');
  }

  function getVariationRows() {
    var group = getVariationGroup();
    if (!group) return [];
    return Array.from(group.querySelectorAll('tbody tr.form-row')).filter(function (row) {
      return !row.classList.contains('empty-form');
    });
  }

  function getAddRowLink(group) {
    return group ? group.querySelector('.add-row a') : null;
  }

  function getSelectedOption(select) {
    if (!select) return null;
    return select.options[select.selectedIndex] || null;
  }

  function buildColorPreviewHtml(hex1, hex2) {
    if (!hex1) return '—';
    var style = 'display:inline-block;width:22px;height:22px;border-radius:50%;border:1px solid #ccc;vertical-align:middle;';
    if (hex2) {
      style += 'background-color:' + hex1 + ';background-image:conic-gradient(from 135deg, ' + hex1 + ' 0deg 180deg, ' + hex2 + ' 180deg 360deg);';
    } else {
      style += 'background-color:' + hex1 + ';';
    }
    return '<span style="' + style + '" title="' + hex1 + '"></span>';
  }

  function updateVariationColorPreview(row) {
    var select = row.querySelector('.field-cor select');
    var target = row.querySelector('.field-cor_preview p');
    if (!select || !target) return;
    var option = getSelectedOption(select);
    var hex1 = option ? (option.getAttribute('data-cor-hex') || '') : '';
    var hex2 = option ? (option.getAttribute('data-cor-hex-secundario') || '') : '';
    target.innerHTML = buildColorPreviewHtml(hex1, hex2);
  }

  function updatePhotoColorPreview(row) {
    var select = row.querySelector('.field-cor select');
    var target = row.querySelector('.field-cor_preview p');
    if (!select || !target) return;
    var option = getSelectedOption(select);
    var hex1 = option ? (option.getAttribute('data-cor-hex') || '') : '';
    var hex2 = option ? (option.getAttribute('data-cor-hex-secundario') || '') : '';
    target.innerHTML = buildColorPreviewHtml(hex1, hex2);
  }

  function findPendingImageDataUrl(pendingKey) {
    var group = document.getElementById('imagens-group');
    if (!group) return null;
    var match = (pendingKey || '').match(/imagens-(\d+)/);
    if (!match) return null;
    var input = group.querySelector('#id_imagens-' + match[1] + '-imagem');
    if (!input || !input.files || !input.files[0]) return null;
    return URL.createObjectURL(input.files[0]);
  }

  function findExistingImageThumb(imageId) {
    var group = document.getElementById('imagens-group');
    if (!group) return null;
    var hidden = group.querySelector('input[type="hidden"][name$="-id"][value="' + imageId + '"]');
    if (!hidden) return null;
    var row = hidden.closest('tr.form-row, .inline-related');
    if (!row) return null;
    var img = row.querySelector('.field-thumb_preview img');
    return img ? img.src : null;
  }

  function buildPhotoThumbHtml(url) {
    if (!url) return '—';
    return '<img src="' + url + '" style="height:70px;width:70px;object-fit:contain;'
      + 'background:#fafaf8;border-radius:4px;border:1px solid #eee;" />';
  }

  function updatePhotoFotoPreview(row) {
    var select = row.querySelector('.field-imagem select');
    var target = row.querySelector('.field-foto_preview p');
    if (!select || !target) return;
    var value = select.value || '';
    var url = null;
    if (value.indexOf('pending:') === 0) {
      url = findPendingImageDataUrl(value.slice('pending:'.length));
    } else if (/^\d+$/.test(value)) {
      url = findExistingImageThumb(value);
    }
    target.innerHTML = buildPhotoThumbHtml(url);
  }

  function initColorPreviewSync() {
    var groups = ['variacoes-group', 'fotos_por_cor-group'];
    groups.forEach(function (groupId) {
      var group = document.getElementById(groupId);
      if (!group) return;
      group.querySelectorAll('tbody tr.form-row').forEach(function (row) {
        if (row.classList.contains('empty-form')) return;
        if (groupId === 'variacoes-group') {
          updateVariationColorPreview(row);
        } else {
          updatePhotoColorPreview(row);
          updatePhotoFotoPreview(row);
        }
      });
      if (group.dataset.colorPreviewBound === '1') return;
      group.dataset.colorPreviewBound = '1';
      group.addEventListener('change', function (event) {
        var row = getInlineRow(event.target);
        if (!row) return;
        if (event.target.matches('.field-cor select, td.field-cor select')) {
          if (groupId === 'variacoes-group') updateVariationColorPreview(row);
          else updatePhotoColorPreview(row);
        } else if (groupId === 'fotos_por_cor-group'
                   && event.target.matches('.field-imagem select, td.field-imagem select')) {
          updatePhotoFotoPreview(row);
        }
      });
    });
  }

  function copyFieldValue(source, target) {
    if (!source || !target) return;
    if (target.type === 'checkbox') {
      target.checked = source.checked;
      target.dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    target.value = source.value;
    target.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function cloneVariationRow(sourceRow, newRow) {
    copyFieldValue(sourceRow.querySelector('.field-cor select'), newRow.querySelector('.field-cor select'));
    copyFieldValue(sourceRow.querySelector('.field-preco input'), newRow.querySelector('.field-preco input'));
    copyFieldValue(sourceRow.querySelector('.field-preco_promocional input'), newRow.querySelector('.field-preco_promocional input'));
    copyFieldValue(sourceRow.querySelector('.field-disponibilidade select'), newRow.querySelector('.field-disponibilidade select'));
    copyFieldValue(sourceRow.querySelector('.field-prazo_confeccao_dias input'), newRow.querySelector('.field-prazo_confeccao_dias input'));
    copyFieldValue(sourceRow.querySelector('.field-ativa input[type="checkbox"]'), newRow.querySelector('.field-ativa input[type="checkbox"]'));

    var sourceTamanho = sourceRow.querySelector('.field-tamanho select');
    var targetTamanho = newRow.querySelector('.field-tamanho select');
    var sourceCor = sourceRow.querySelector('.field-cor select');

    if (sourceTamanho && targetTamanho && sourceCor && sourceCor.value) {
      targetTamanho.value = '';
      targetTamanho.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      copyFieldValue(sourceTamanho, targetTamanho);
    }

    ['.field-estoque input', '.field-sku_variacao input', '.field-bling_variacao_id input'].forEach(function (selector) {
      var input = newRow.querySelector(selector);
      if (!input) return;
      input.value = '';
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });

    updateVariationColorPreview(newRow);
    var firstEditable = newRow.querySelector('.field-tamanho select, .field-cor select, .field-estoque input');
    if (firstEditable) firstEditable.focus();
  }

  function createInlineCloneButtons() {
    var group = getVariationGroup();
    if (!group) return;
    getVariationRows().forEach(function (row) {
      var cell = row.querySelector('.field-clonar_btn');
      if (!cell) return;
      if (!cell.querySelector('.della-inline-clone')) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'della-inline-clone';
        button.textContent = 'Clonar';
        button.title = 'Clona esta linha para você ajustar a próxima variação antes de salvar';
        cell.innerHTML = '';
        cell.appendChild(button);
      }
    });
  }

  function initVariationClone() {
    var group = getVariationGroup();
    if (!group) return;
    createInlineCloneButtons();

    group.addEventListener('click', function (event) {
      var button = event.target.closest('.della-inline-clone');
      if (!button) return;
      event.preventDefault();

      var sourceRow = button.closest('tr.form-row');
      var addLink = getAddRowLink(group);
      if (!sourceRow || !addLink) return;

      var beforeCount = getVariationRows().length;
      addLink.click();

      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () {
          var rows = getVariationRows();
          var newRow = rows[rows.length - 1];
          if (!newRow || rows.length <= beforeCount) return;
          createInlineCloneButtons();
          cloneVariationRow(sourceRow, newRow);
        });
      });
    });
  }

  function saveFormScrollState() {
    var payload = {
      windowY: window.scrollY || window.pageYOffset || 0,
      containers: {},
    };
    document.querySelectorAll('.tabular.inline-related').forEach(function (container) {
      if (!container.id) return;
      payload.containers[container.id] = {
        top: container.scrollTop || 0,
        left: container.scrollLeft || 0,
      };
    });
    sessionStorage.setItem(FORM_SCROLL_KEY, JSON.stringify(payload));
  }

  function restoreFormScrollState() {
    var raw = sessionStorage.getItem(FORM_SCROLL_KEY);
    if (!raw) return;
    sessionStorage.removeItem(FORM_SCROLL_KEY);
    try {
      var payload = JSON.parse(raw);
      window.requestAnimationFrame(function () {
        window.scrollTo(0, payload.windowY || 0);
        Object.keys(payload.containers || {}).forEach(function (id) {
          var container = document.getElementById(id);
          if (!container) return;
          container.scrollTop = payload.containers[id].top || 0;
          container.scrollLeft = payload.containers[id].left || 0;
        });
      });
    } catch (error) {
      sessionStorage.removeItem(FORM_SCROLL_KEY);
    }
  }

  function initFormScrollPersistence() {
    restoreFormScrollState();
    var form = document.querySelector('#produto_form, form');
    if (!form) return;
    form.addEventListener('submit', saveFormScrollState);
    document.querySelectorAll('input[name="_save"], input[name="_continue"], input[name="_addanother"], button[name="_save"], button[name="_continue"], button[name="_addanother"]').forEach(function (button) {
      button.addEventListener('click', saveFormScrollState);
    });
  }

  function syncVariationHeadingHeight() {
    var group = getVariationGroup();
    if (!group) return;
    var heading = group.querySelector(':scope > .inline-heading');
    if (!heading) return;
    var h = Math.round(heading.getBoundingClientRect().height);
    if (h > 0) group.style.setProperty('--variacoes-heading-h', h + 'px');
  }

  function buildVariationStickyThead() {
    var group = getVariationGroup();
    if (!group) return;
    var container = group.querySelector('.tabular.inline-related');
    var sourceTable = container ? container.querySelector('table') : null;
    var sourceThead = sourceTable ? sourceTable.querySelector('thead') : null;
    if (!container || !sourceTable || !sourceThead) return;

    var wrap = group.querySelector(':scope > .della-thead-clone-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'della-thead-clone-wrap';
      wrap.setAttribute('aria-hidden', 'true');
      container.parentNode.insertBefore(wrap, container);
    }

    var cloneTable = wrap.querySelector('table');
    if (!cloneTable) {
      cloneTable = document.createElement('table');
      wrap.appendChild(cloneTable);
    }

    var existingThead = cloneTable.querySelector('thead');
    if (existingThead) existingThead.remove();
    cloneTable.appendChild(sourceThead.cloneNode(true));

    var width = sourceTable.scrollWidth || sourceTable.offsetWidth || 0;
    if (width > 0) cloneTable.style.width = width + 'px';
    cloneTable.style.transform = 'translateX(' + (-container.scrollLeft) + 'px)';

    if (wrap.dataset.scrollBound !== '1') {
      wrap.dataset.scrollBound = '1';
      container.addEventListener('scroll', function () {
        cloneTable.style.transform = 'translateX(' + (-container.scrollLeft) + 'px)';
      }, { passive: true });
    }
  }

  function buildVariationStickyScrollbar() {
    var group = getVariationGroup();
    if (!group) return;

    syncVariationHeadingHeight();
    buildVariationStickyThead();

    var container = group.querySelector('.tabular.inline-related');
    var table = container ? container.querySelector('table') : null;
    if (!container || !table) return;

    var extraProxies = Array.from(group.querySelectorAll('.della-inline-scrollbar-proxy'));
    extraProxies.slice(1).forEach(function (node) { node.remove(); });

    var proxy = extraProxies[0];
    if (!proxy) {
      proxy = document.createElement('div');
      proxy.className = 'della-inline-scrollbar-proxy';
      proxy.innerHTML = '<div></div>';
      group.appendChild(proxy);
    }

    var inner = proxy.firstElementChild;
    if (!inner) {
      inner = document.createElement('div');
      proxy.appendChild(inner);
    }

    inner.style.width = table.scrollWidth + 'px';
    proxy.style.display = table.scrollWidth > container.clientWidth ? 'block' : 'none';

    if (proxy.dataset.bound === '1') return;
    proxy.dataset.bound = '1';

    var syncingFromProxy = false;
    var syncingFromContainer = false;

    proxy.addEventListener('scroll', function () {
      if (syncingFromContainer) return;
      syncingFromProxy = true;
      container.scrollLeft = proxy.scrollLeft;
      syncingFromProxy = false;
    });

    container.addEventListener('scroll', function () {
      if (syncingFromProxy) return;
      syncingFromContainer = true;
      proxy.scrollLeft = container.scrollLeft;
      syncingFromContainer = false;
    });
  }

  function getPendingImageRefs() {
    var group = document.getElementById('imagens-group');
    if (!group) return [];
    var refs = [];
    Array.from(group.querySelectorAll('input[type="file"]')).forEach(function (input) {
      var name = input.name || '';
      if (name.indexOf('__prefix__') !== -1) return;
      var row = input.closest('tr.form-row, .inline-related');
      if (!row) return;
      if (row.classList.contains('empty-form')) return;
      if (row.classList.contains('has_original')) return;
      if (!input.files || input.files.length === 0) return;
      var file = input.files[0];
      if (!file) return;
      var match = (input.id || '').match(/imagens-(\d+)-imagem/);
      if (!match) return;
      refs.push({ key: 'imagens-' + match[1], filename: file.name });
    });
    return refs;
  }

  function syncPendingOptionsInColorPhotoSelects() {
    var group = document.getElementById('fotos_por_cor-group');
    if (!group) return;
    var refs = getPendingImageRefs();
    var refKeys = refs.map(function (r) { return 'pending:' + r.key; });

    Array.from(group.querySelectorAll('.field-imagem select')).forEach(function (select) {
      var previousValue = select.value;

      Array.from(select.querySelectorAll('option[data-pending="1"]')).forEach(function (opt) {
        if (refKeys.indexOf(opt.value) === -1) opt.remove();
      });

      refs.forEach(function (ref) {
        var value = 'pending:' + ref.key;
        var existing = select.querySelector('option[value="' + value + '"]');
        var label = 'Nova foto: ' + ref.filename;
        if (existing) {
          if (existing.textContent !== label) existing.textContent = label;
        } else {
          var opt = document.createElement('option');
          opt.value = value;
          opt.textContent = label;
          opt.setAttribute('data-pending', '1');
          select.appendChild(opt);
        }
      });

      if (previousValue && select.value !== previousValue) {
        var stillExists = select.querySelector('option[value="' + CSS.escape(previousValue) + '"]');
        if (stillExists) select.value = previousValue;
      }

      var row = getInlineRow(select);
      if (row) updatePhotoFotoPreview(row);
    });
  }

  var refreshInlineEnhancements = debounce(function () {
    createInlineCloneButtons();
    initColorPreviewSync();
    buildVariationStickyScrollbar();
    syncPendingOptionsInColorPhotoSelects();
  }, 60);

  function findImageInlineGroup() {
    var byDropzone = document.querySelector('.inline-group[data-inline-prefix="imagens"]');
    if (byDropzone) return byDropzone;

    var byId = document.getElementById('imagens-group');
    if (byId) return byId;

    var byModel = document.querySelector('.inline-group[data-inline-model="produtos-produtoimagem"]');
    if (byModel) return byModel;

    return Array.from(document.querySelectorAll('.inline-group')).find(function (group) {
      var title = group.querySelector('h2');
      return title && /fotos do produto/i.test(title.textContent || '');
    }) || null;
  }

  function getFileInputs(group) {
    return Array.from(group.querySelectorAll('input[type="file"]')).filter(function (input) {
      if ((input.name || '').indexOf('__prefix__') !== -1) return false;
      var row = getInlineRow(input);
      return row && row.style.display !== 'none';
    });
  }

  function isBlankUploadRow(input) {
    var row = getInlineRow(input);
    if (!row) return false;
    if (row.classList.contains('has_original')) return false;
    if (row.classList.contains('empty-form')) return false;
    return true;
  }

  function getEmptyFileInputs(group) {
    return getFileInputs(group).filter(function (input) {
      return isBlankUploadRow(input) && (!input.files || input.files.length === 0);
    });
  }

  function clickAddRow(group) {
    var addLink = group.querySelector('.add-row a');
    if (addLink) addLink.click();
  }

  function createSingleFileList(file) {
    var dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    return dataTransfer.files;
  }

  function updatePreview(input, file) {
    var row = getInlineRow(input);
    if (!row || !file || !file.type || file.type.indexOf('image/') !== 0) return;

    var previewCell = row.querySelector('.field-thumb_preview');
    if (!previewCell) return;

    var img = previewCell.querySelector('img');
    if (!img) {
      img = document.createElement('img');
      img.style.height = '70px';
      img.style.width = '70px';
      img.style.objectFit = 'contain';
      img.style.background = '#fafaf8';
      img.style.borderRadius = '6px';
      img.style.border = '1px solid #eee';
      previewCell.innerHTML = '';
      previewCell.appendChild(img);
    }

    var match = (input.id || '').match(/imagens-(\d+)-imagem/);
    var cacheKey = match ? 'imagens-' + match[1] : null;

    var reader = new FileReader();
    reader.onload = function (event) {
      img.src = event.target.result;
      if (cacheKey) dataUrlCache[cacheKey] = event.target.result;
      // Reconstrói o strip após FileReader terminar (dados disponíveis)
      buildPhotoCardStrip();
    };
    reader.readAsDataURL(file);
  }

  function assignFilesToInputs(group, files) {
    var pending = Array.from(files);

    function apply() {
      var emptyInputs = getEmptyFileInputs(group);
      while (emptyInputs.length < pending.length) {
        clickAddRow(group);
        emptyInputs = getEmptyFileInputs(group);
      }

      pending.forEach(function (file, index) {
        var input = emptyInputs[index];
        if (!input) return;
        input.files = createSingleFileList(file);
        updatePreview(input, file);
        input.dispatchEvent(new Event('change', { bubbles: true }));
      });
    }

    window.requestAnimationFrame(apply);
  }

  function initBulkDropzone() {
    var group = findImageInlineGroup();
    if (!group) return;

    var dropzone = group.querySelector('.della-upload-dropzone');
    if (!dropzone) {
      dropzone = document.createElement('div');
      dropzone.className = 'della-upload-dropzone';
      dropzone.innerHTML = (
        '<strong>Enviar varias fotos</strong>' +
        '<small>Arraste as imagens aqui ou clique para selecionar varias de uma vez.</small>'
      );
    }
    if (dropzone.dataset.dellaBound === '1') return;
    dropzone.dataset.dellaBound = '1';

    var picker = document.createElement('input');
    picker.type = 'file';
    picker.multiple = true;
    picker.accept = 'image/*';
    picker.style.display = 'none';

    dropzone.addEventListener('click', function () {
      picker.click();
    });

    picker.addEventListener('change', function () {
      if (picker.files && picker.files.length) {
        assignFilesToInputs(group, picker.files);
      }
      picker.value = '';
    });

    ['dragenter', 'dragover'].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.add('is-dragover');
      });
    });

    ['dragleave', 'dragend', 'drop'].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.remove('is-dragover');
      });
    });

    dropzone.addEventListener('drop', function (event) {
      var files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) {
        assignFilesToInputs(group, files);
      }
    });

    if (!dropzone.parentNode) {
      var afterTitle = group.querySelector('h2');
      if (afterTitle && afterTitle.nextSibling) {
        group.insertBefore(dropzone, afterTitle.nextSibling);
      } else {
        group.insertBefore(dropzone, group.firstChild);
      }
    }
    group.appendChild(picker);
  }

  function initPendingImageSync() {
    var group = document.getElementById('imagens-group');
    if (!group || group.dataset.pendingSyncBound === '1') return;
    group.dataset.pendingSyncBound = '1';
    group.addEventListener('change', function (event) {
      if (event.target && event.target.matches('input[type="file"]')) {
        syncPendingOptionsInColorPhotoSelects();
        window.requestAnimationFrame(buildPhotoCardStrip);
      }
    });
  }

  /* =========================================================================
     PHOTO CARD STRIP — Seção 22 (Task 3)
     ========================================================================= */

  function getImagenFormRows() {
    var group = findImageInlineGroup();
    if (!group) return [];
    return Array.from(group.querySelectorAll('tr.form-row')).filter(function (row) {
      return !row.classList.contains('empty-form');
    });
  }

  function getRowPrefix(row) {
    var anyInput = row.querySelector('input[name^="imagens-"]');
    if (!anyInput) return null;
    var m = anyInput.name.match(/^(imagens-\d+)-/);
    return m ? m[1] : null;
  }

  function getPhotoUrlForRow(row) {
    var img = row.querySelector('.field-thumb_preview img');
    // img.src sem atributo 'src' resolve para a URL da página — usar getAttribute
    if (img && img.getAttribute('src')) return img.src;
    // Verifica cache de data: URLs (preenchido pelo FileReader em updatePreview)
    var prefix = getRowPrefix(row);
    if (prefix && dataUrlCache[prefix]) return dataUrlCache[prefix];
    // Fallback: blob URL (necessita blob: em img-src no CSP)
    var fileInput = row.querySelector('input[type="file"]');
    if (fileInput && fileInput.files && fileInput.files[0]) {
      return URL.createObjectURL(fileInput.files[0]);
    }
    return null;
  }

  function isDeletedRow(row) {
    var chk = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
    return chk && chk.checked;
  }

  function isPrincipalRow(row) {
    var chk = row.querySelector('input[type="checkbox"][name$="-principal"]');
    return chk && chk.checked;
  }

  function refreshOrdemFromStrip(track) {
    var group = findImageInlineGroup();
    if (!group || !track) return;
    Array.from(track.querySelectorAll('.della-foto-card')).forEach(function (card, idx) {
      var prefix = card.dataset.rowPrefix;
      if (!prefix) return;
      var ordemInput = group.querySelector('input[name="' + prefix + '-ordem"]');
      if (ordemInput) ordemInput.value = idx;
    });
  }

  // Marca a 1ª foto do strip como principal; desmarca todas as demais
  function refreshPrincipalFromStrip(track) {
    var group = findImageInlineGroup();
    if (!group || !track) return;
    var cards = Array.from(track.querySelectorAll('.della-foto-card'));
    var firstPrefix = cards.length > 0 ? cards[0].dataset.rowPrefix : null;

    getImagenFormRows().forEach(function (row) {
      var prefix = getRowPrefix(row);
      if (!prefix) return;
      var chk = group.querySelector('input[type="checkbox"][name="' + prefix + '-principal"]');
      if (chk) chk.checked = (prefix === firstPrefix);
    });

    // Atualiza badge visual
    cards.forEach(function (card, idx) {
      var badge = card.querySelector('.della-foto-card-principal-badge');
      if (idx === 0) {
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'della-foto-card-principal-badge';
          badge.textContent = 'Principal';
          card.appendChild(badge);
        }
      } else {
        if (badge) badge.remove();
      }
    });
  }

  function isFileDrag(e) {
    if (!e.dataTransfer || !e.dataTransfer.types) return false;
    var types = e.dataTransfer.types;
    for (var i = 0; i < types.length; i++) {
      if (types[i] === 'Files' || types[i] === 'application/x-moz-file') return true;
    }
    return false;
  }

  function setupCardDragAndDrop(track) {
    var dragging = null;

    track.addEventListener('dragstart', function (e) {
      var card = e.target.closest('.della-foto-card');
      if (!card) return;
      dragging = card;
      card.classList.add('is-dragging');
      e.dataTransfer.effectAllowed = 'move';
    });

    track.addEventListener('dragend', function () {
      if (dragging) dragging.classList.remove('is-dragging');
      track.querySelectorAll('.della-foto-card').forEach(function (c) { c.classList.remove('drag-over'); });
      track.classList.remove('is-file-dragover');
      dragging = null;
      refreshOrdemFromStrip(track);
      refreshPrincipalFromStrip(track);
    });

    track.addEventListener('dragover', function (e) {
      e.preventDefault();
      if (dragging) {
        // Reordenação de card-para-card
        var target = e.target.closest('.della-foto-card');
        if (!target || target === dragging) return;
        track.querySelectorAll('.della-foto-card').forEach(function (c) { c.classList.remove('drag-over'); });
        target.classList.add('drag-over');
        var rect = target.getBoundingClientRect();
        if (e.clientX < rect.left + rect.width / 2) {
          track.insertBefore(dragging, target);
        } else {
          track.insertBefore(dragging, target.nextSibling);
        }
      } else if (isFileDrag(e)) {
        // Arquivo vindo do desktop
        track.classList.add('is-file-dragover');
      }
    });

    track.addEventListener('dragleave', function (e) {
      if (!dragging && !track.contains(e.relatedTarget)) {
        track.classList.remove('is-file-dragover');
      }
    });

    track.addEventListener('drop', function (e) {
      e.preventDefault();
      track.classList.remove('is-file-dragover');
      if (!dragging && isFileDrag(e) && e.dataTransfer.files && e.dataTransfer.files.length) {
        var group = findImageInlineGroup();
        if (group) assignFilesToInputs(group, e.dataTransfer.files);
      }
    });
  }

  function buildPhotoCard(row, track) {
    var prefix = getRowPrefix(row);
    var photoUrl = getPhotoUrlForRow(row);
    if (!photoUrl || !prefix) return null;

    var isNew = !row.classList.contains('has_original');

    var card = document.createElement('div');
    card.className = 'della-foto-card' + (isPrincipalRow(row) ? ' is-principal' : '');
    card.draggable = true;
    card.dataset.rowPrefix = prefix;
    card.title = 'Arraste para reordenar';

    var img = document.createElement('img');
    img.src = photoUrl;
    img.alt = '';

    var delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'della-foto-card-delete';
    delBtn.innerHTML = '&times;';
    delBtn.title = 'Remover foto';
    delBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var group = findImageInlineGroup();
      if (!group) return;

      if (isNew) {
        // Foto nova (não salva): esvazia o input de arquivo para Django ignorar a linha
        var fileInput = group.querySelector('input[type="file"][name="' + prefix + '-imagem"]');
        if (fileInput) {
          fileInput.value = '';
          try { fileInput.files = new DataTransfer().files; } catch (ex) {}
        }
        // Remove do cache de data URLs
        delete dataUrlCache[prefix];
        // Tenta também marcar DELETE se existir (Django >= 4.2 com can_delete_extra)
        var deleteChk = group.querySelector('input[type="checkbox"][name="' + prefix + '-DELETE"]');
        if (deleteChk) { deleteChk.checked = true; deleteChk.dispatchEvent(new Event('change', { bubbles: true })); }
      } else {
        // Foto salva: usa checkbox DELETE para o Django deletar no banco
        var deleteChk = group.querySelector('input[type="checkbox"][name="' + prefix + '-DELETE"]');
        if (deleteChk) {
          deleteChk.checked = true;
          deleteChk.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }

      card.remove();
      if (track) {
        refreshOrdemFromStrip(track);
        refreshPrincipalFromStrip(track);
      }
    });

    card.appendChild(img);
    card.appendChild(delBtn);

    if (!isNew) {
      var dl = document.createElement('a');
      dl.className = 'della-foto-card-download';
      dl.href = photoUrl;
      dl.download = '';
      dl.innerHTML = '&#8595;';
      dl.title = 'Baixar';
      dl.addEventListener('click', function (e) { e.stopPropagation(); });
      card.appendChild(dl);
    }

    if (isPrincipalRow(row)) {
      var badge = document.createElement('span');
      badge.className = 'della-foto-card-principal-badge';
      badge.textContent = 'Principal';
      card.appendChild(badge);
    }

    return card;
  }

  function buildPhotoCardStrip() {
    var group = findImageInlineGroup();
    if (!group) return;

    // Garante que o painel existe (cria apenas uma vez)
    var panel = group.querySelector('.della-fotos-panel');
    if (!panel) {
      panel = document.createElement('div');
      panel.className = 'della-fotos-panel';

      var header = document.createElement('div');
      header.className = 'della-fotos-panel-header';

      var btnsDiv = document.createElement('div');
      btnsDiv.style.cssText = 'display:flex;gap:0.5rem;';

      var btnSort = document.createElement('button');
      btnSort.type = 'button';
      btnSort.className = 'della-strip-btn';
      btnSort.innerHTML = '&#8644; Ordenar imagens';
      btnSort.title = 'Arraste os cards para reordenar as fotos';
      btnSort.addEventListener('click', function () {
        var track = panel.querySelector('.della-fotos-track');
        var isOn = track && track.classList.toggle('is-sort-mode');
        btnSort.classList.toggle('is-active', !!isOn);
        btnSort.innerHTML = isOn ? '&#10003; Concluír' : '&#8644; Ordenar imagens';
      });

      var btnChoose = document.createElement('button');
      btnChoose.type = 'button';
      btnChoose.className = 'della-strip-btn';
      btnChoose.innerHTML = '&#8593; Escolher imagens';

      var filePicker = document.createElement('input');
      filePicker.type = 'file';
      filePicker.multiple = true;
      filePicker.accept = 'image/*';
      filePicker.style.display = 'none';

      btnChoose.addEventListener('click', function () { filePicker.click(); });
      filePicker.addEventListener('change', function () {
        if (filePicker.files && filePicker.files.length) {
          assignFilesToInputs(group, filePicker.files);
        }
        filePicker.value = '';
      });

      btnsDiv.appendChild(btnSort);
      btnsDiv.appendChild(btnChoose);
      btnsDiv.appendChild(filePicker);
      header.appendChild(btnsDiv);
      panel.appendChild(header);

      var carousel = document.createElement('div');
      carousel.className = 'della-fotos-carousel';

      var navPrev = document.createElement('button');
      navPrev.type = 'button';
      navPrev.className = 'della-fotos-nav prev';
      navPrev.innerHTML = '&#8249;';

      var navNext = document.createElement('button');
      navNext.type = 'button';
      navNext.className = 'della-fotos-nav next';
      navNext.innerHTML = '&#8250;';

      var track = document.createElement('div');
      track.className = 'della-fotos-track';

      carousel.appendChild(navPrev);
      carousel.appendChild(track);
      carousel.appendChild(navNext);
      panel.appendChild(carousel);

      navPrev.addEventListener('click', function () { track.scrollBy({ left: -170, behavior: 'smooth' }); });
      navNext.addEventListener('click', function () { track.scrollBy({ left: 170, behavior: 'smooth' }); });
      setupCardDragAndDrop(track);

      var heading = group.querySelector('h2.inline-heading');
      var tabular = group.querySelector('.tabular.inline-related');
      var insertRef = heading ? heading.nextSibling : (tabular || null);
      if (insertRef) group.insertBefore(panel, insertRef);
      else group.appendChild(panel);
    }

    var track = panel.querySelector('.della-fotos-track');
    if (!track) return;

    // Lê linhas do formset ordenadas por `ordem`
    var rows = getImagenFormRows().filter(function (r) { return !isDeletedRow(r); });
    rows.sort(function (a, b) {
      var ga = parseInt((a.querySelector('input[name$="-ordem"]') || {}).value || '0', 10);
      var gb = parseInt((b.querySelector('input[name$="-ordem"]') || {}).value || '0', 10);
      return ga - gb;
    });

    // Adiciona cards que ainda não existem
    rows.forEach(function (row) {
      var prefix = getRowPrefix(row);
      if (!prefix) return;
      if (track.querySelector('.della-foto-card[data-row-prefix="' + prefix + '"]')) return;
      if (!getPhotoUrlForRow(row)) return;
      var card = buildPhotoCard(row, track);
      if (card) track.appendChild(card);
    });

    // Estado vazio
    var hasCards = track.querySelector('.della-foto-card');
    var emptyEl = track.querySelector('.della-fotos-empty');
    if (!hasCards && !emptyEl) {
      var empty = document.createElement('div');
      empty.className = 'della-fotos-empty';
      empty.textContent = 'Nenhuma imagem. Clique em “Escolher imagens” para adicionar.';
      track.appendChild(empty);
    } else if (hasCards && emptyEl) {
      emptyEl.remove();
    }
  }

  /* =========================================================================
     COLOR PHOTO PICKER — Seção 23 (Task 4)
     ========================================================================= */

  function getProductPhotosForPicker() {
    var group = findImageInlineGroup();
    var photos = [];
    if (!group) return photos;
    getImagenFormRows().forEach(function (row) {
      if (isDeletedRow(row)) return;
      var prefix = getRowPrefix(row);
      if (!prefix) return;
      var idInput = group.querySelector('input[name="' + prefix + '-id"]');
      var fileInput = group.querySelector('input[type="file"][name="' + prefix + '-imagem"]');
      var thumbImg = row.querySelector('.field-thumb_preview img');
      var value = null;
      var src = null;
      if (idInput && idInput.value) {
        value = idInput.value;
        src = thumbImg ? thumbImg.src : null;
      } else if (fileInput && fileInput.files && fileInput.files[0]) {
        var m = (fileInput.id || fileInput.name || '').match(/imagens-(\d+)/);
        if (m) {
          value = 'pending:imagens-' + m[1];
          src = URL.createObjectURL(fileInput.files[0]);
        }
      }
      if (value && src) photos.push({ value: value, src: src });
    });
    return photos;
  }

  function getPhotoSrcForValue(val) {
    if (!val) return null;
    if (val.indexOf('pending:') === 0) return findPendingImageDataUrl(val.slice('pending:'.length));
    if (/^\d+$/.test(val)) return findExistingImageThumb(val);
    return null;
  }

  function updateCorFotoButton(btn, val) {
    var src = val ? getPhotoSrcForValue(val) : null;
    if (src) {
      btn.innerHTML = '<img src="' + src + '" alt="" />';
    } else {
      btn.innerHTML = '<span class="della-cor-foto-placeholder">&#128247;</span>';
    }
  }

  // Abre o modal de seleção de foto.
  // onSaveCb(selectedValue) — callback opcional; se omitido, atualiza `select` diretamente.
  // onRemoveCb() — callback opcional; quando informado e já existe vínculo,
  //   exibe o botão "Remover vínculo" no rodapé do modal.
  function showColorPhotoPicker(select, btn, onSaveCb, onRemoveCb) {
    var existing = document.querySelector('.della-foto-picker-overlay');
    if (existing) existing.remove();

    var photos = getProductPhotosForPicker();
    var selectedValue = select ? select.value : '';

    var overlay = document.createElement('div');
    overlay.className = 'della-foto-picker-overlay';

    var modal = document.createElement('div');
    modal.className = 'della-foto-picker-modal';

    var header = document.createElement('div');
    header.className = 'della-foto-picker-modal-header';
    var title = document.createElement('h3');
    title.textContent = 'Vincular imagens na variação';
    var closeX = document.createElement('button');
    closeX.type = 'button';
    closeX.className = 'della-foto-picker-modal-close';
    closeX.innerHTML = '&times;';
    header.appendChild(title);
    header.appendChild(closeX);

    var grid = document.createElement('div');
    grid.className = 'della-foto-picker-grid';

    if (photos.length === 0) {
      var empty = document.createElement('p');
      empty.style.cssText = 'grid-column:1/-1;text-align:center;color:var(--da-muted);padding:2rem;';
      empty.textContent = 'Nenhuma foto disponível. Adicione fotos ao produto primeiro.';
      grid.appendChild(empty);
    } else {
      photos.forEach(function (photo) {
        var item = document.createElement('div');
        item.className = 'della-foto-picker-item' + (photo.value === selectedValue ? ' selected' : '');
        item.dataset.value = photo.value;
        var pImg = document.createElement('img');
        pImg.src = photo.src;
        pImg.alt = '';
        item.appendChild(pImg);
        item.addEventListener('click', function () {
          grid.querySelectorAll('.della-foto-picker-item').forEach(function (el) { el.classList.remove('selected'); });
          item.classList.add('selected');
          selectedValue = photo.value;
        });
        grid.appendChild(item);
      });
    }

    var footer = document.createElement('div');
    footer.className = 'della-foto-picker-footer';

    var removeBtn = null;
    if (selectedValue && typeof onRemoveCb === 'function') {
      removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'della-foto-picker-remove';
      removeBtn.textContent = 'Remover vínculo';
      removeBtn.title = 'Desvincula a foto desta cor';
      footer.appendChild(removeBtn);
    }

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'della-foto-picker-cancel';
    cancelBtn.textContent = 'Cancelar';
    var saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'della-foto-picker-save';
    saveBtn.textContent = 'Salvar';
    footer.appendChild(cancelBtn);
    footer.appendChild(saveBtn);

    modal.appendChild(header);
    modal.appendChild(grid);
    modal.appendChild(footer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    function closeModal() { overlay.remove(); }

    function saveAndClose() {
      if (selectedValue !== undefined) {
        if (typeof onSaveCb === 'function') {
          onSaveCb(selectedValue);
        } else if (select) {
          select.value = selectedValue;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          if (btn) updateCorFotoButton(btn, selectedValue);
        }
      }
      closeModal();
    }

    closeX.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    saveBtn.addEventListener('click', saveAndClose);
    if (removeBtn) {
      removeBtn.addEventListener('click', function () {
        onRemoveCb();
        closeModal();
      });
    }
    overlay.addEventListener('click', function (e) { if (e.target === overlay) closeModal(); });

    var escFn = function (e) {
      if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', escFn); }
    };
    document.addEventListener('keydown', escFn);
  }

  /* =========================================================================
     FOTO POR COR NA VARIAÇÃO — integrado na linha de variação (Task 4 v2)
     ========================================================================= */

  // Lê o mapa corId → {value, src} do formset oculto fotos_por_cor
  function getCorFotoMapFromGroup() {
    var map = {};
    var group = document.getElementById('fotos_por_cor-group');
    if (!group) return map;
    group.querySelectorAll('tr.form-row').forEach(function (row) {
      if (row.classList.contains('empty-form') || isDeletedRow(row)) return;
      var corSel = row.querySelector('.field-cor select');
      var imgSel = row.querySelector('.field-imagem select');
      if (!corSel || !imgSel || !corSel.value || !imgSel.value) return;
      var src = getPhotoSrcForValue(imgSel.value);
      map[corSel.value] = { value: imgSel.value, src: src };
    });
    return map;
  }

  // Cria ou atualiza uma linha no formset fotos_por_cor para o corId com imgValue
  function setCorFotoInGroup(corId, imgValue, afterCb) {
    var group = document.getElementById('fotos_por_cor-group');
    if (!group) { if (afterCb) afterCb(); return; }

    var existingRow = null;
    group.querySelectorAll('tr.form-row').forEach(function (row) {
      if (row.classList.contains('empty-form') || isDeletedRow(row)) return;
      var corSel = row.querySelector('.field-cor select');
      if (corSel && corSel.value === corId) existingRow = row;
    });

    function applyValues(row) {
      var corSel = row.querySelector('.field-cor select');
      var imgSel = row.querySelector('.field-imagem select');
      if (corSel && corSel.value !== corId) { corSel.value = corId; corSel.dispatchEvent(new Event('change', { bubbles: true })); }
      if (imgSel) { imgSel.value = imgValue; imgSel.dispatchEvent(new Event('change', { bubbles: true })); }
      if (afterCb) afterCb();
    }

    if (existingRow) {
      applyValues(existingRow);
    } else {
      var addLink = group.querySelector('.add-row a');
      if (!addLink) { if (afterCb) afterCb(); return; }
      addLink.click();
      window.requestAnimationFrame(function () {
        var newRows = Array.from(group.querySelectorAll('tr.form-row')).filter(function (r) {
          return !r.classList.contains('empty-form') && !r.classList.contains('has_original') && !isDeletedRow(r);
        });
        var newRow = newRows[newRows.length - 1];
        if (newRow) applyValues(newRow);
        else if (afterCb) afterCb();
      });
    }
  }

  // Remove o vínculo cor↔foto do formset oculto fotos_por_cor para o corId informado.
  // - Linha já salva (com pk): marca DELETE para o Django remover no banco.
  // - Linha nova (sem pk): marca DELETE também (Django ignora forms com DELETE=True).
  function removeCorFotoFromGroup(corId, afterCb) {
    var group = document.getElementById('fotos_por_cor-group');
    if (!group || !corId) { if (afterCb) afterCb(); return; }

    group.querySelectorAll('tr.form-row').forEach(function (row) {
      if (row.classList.contains('empty-form')) return;
      var corSel = row.querySelector('.field-cor select');
      if (!corSel || corSel.value !== corId) return;

      var deleteChk = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
      if (deleteChk) {
        deleteChk.checked = true;
        deleteChk.dispatchEvent(new Event('change', { bubbles: true }));
      }

      // Limpa o select de imagem para evitar que validações vejam um valor pendente
      var imgSel = row.querySelector('.field-imagem select');
      if (imgSel) {
        imgSel.value = '';
        imgSel.dispatchEvent(new Event('change', { bubbles: true }));
      }

      // Esconde a linha do DOM (o formset oculto já é display:none, mas garante consistência)
      row.style.display = 'none';
    });

    if (afterCb) afterCb();
  }

  // Atualiza o visual do botão na linha de variação
  function updateVarFotoButton(btn, src) {
    if (src) {
      btn.innerHTML = '<img src="' + src + '" alt="" />';
      btn.classList.add('has-photo');
    } else {
      btn.innerHTML = '&#128247;';
      btn.classList.remove('has-photo');
    }
  }

  // Atualiza todos os botões de foto nas linhas de variação com uma determinada cor
  function refreshVarFotoButtonsForCor(corId) {
    var varGroup = getVariationGroup();
    if (!varGroup || !corId) return;
    var map = getCorFotoMapFromGroup();
    var entry = map[corId] || null;
    varGroup.querySelectorAll('tr.form-row').forEach(function (row) {
      if (row.classList.contains('empty-form')) return;
      var corSel = row.querySelector('.field-cor select');
      if (!corSel || corSel.value !== corId) return;
      var btn = row.querySelector('.della-var-foto-btn');
      if (btn) updateVarFotoButton(btn, entry ? entry.src : null);
    });
  }

  function initVariationPhotoButtons() {
    var varGroup = getVariationGroup();
    if (!varGroup) return;

    function attachToRow(row) {
      if (row.classList.contains('empty-form')) return;
      if (row.querySelector('.della-var-foto-btn')) return;

      // Coloca o botão em td.field-cor, ANTES do select da cor.
      // flex-direction:row no CSS garante botão + dropdown lado a lado, sem quebrar.
      var corCell = row.querySelector('td.field-cor');
      if (!corCell) return;

      var corSel = corCell.querySelector('select');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'della-var-foto-btn';
      btn.title = 'Vincular foto a esta cor';

      var corId = corSel ? corSel.value : '';
      var map = getCorFotoMapFromGroup();
      updateVarFotoButton(btn, corId ? (map[corId] ? map[corId].src : null) : null);

      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var currentCorId = corSel ? corSel.value : '';
        if (!currentCorId) return;
        var curMap = getCorFotoMapFromGroup();
        var curEntry = curMap[currentCorId] || null;
        showColorPhotoPicker(
          { value: curEntry ? curEntry.value : '' },
          btn,
          function (selectedValue) {
            setCorFotoInGroup(currentCorId, selectedValue, function () {
              refreshVarFotoButtonsForCor(currentCorId);
            });
          },
          function () {
            removeCorFotoFromGroup(currentCorId, function () {
              refreshVarFotoButtonsForCor(currentCorId);
            });
          }
        );
      });

      // Atualiza o thumb quando o usuário muda a cor no dropdown
      if (corSel) {
        corSel.addEventListener('change', function () {
          var newId = corSel.value;
          var m = getCorFotoMapFromGroup();
          updateVarFotoButton(btn, newId ? (m[newId] ? m[newId].src : null) : null);
        });
      }

      // Insere o botão como PRIMEIRO filho da célula de cor — fica antes do dropdown
      var corWrapper = corCell.querySelector('.related-widget-wrapper') || corSel;
      if (corWrapper && corWrapper.parentNode === corCell) {
        corCell.insertBefore(btn, corWrapper);
      } else {
        corCell.insertBefore(btn, corCell.firstChild);
      }
    }

    varGroup.querySelectorAll('tr.form-row').forEach(attachToRow);

    if (varGroup.dataset.varPhotosBound === '1') return;
    varGroup.dataset.varPhotosBound = '1';
    new MutationObserver(function () {
      varGroup.querySelectorAll('tr.form-row').forEach(attachToRow);
    }).observe(varGroup, { childList: true, subtree: true });
  }

  // Garante que, ao salvar, a 1ª foto na ordem do strip seja marcada como principal
  function initAutoPrincipal() {
    var form = document.querySelector('#produto_form, form');
    if (!form || form.dataset.principalBound === '1') return;
    form.dataset.principalBound = '1';
    form.addEventListener('submit', function () {
      var group = findImageInlineGroup();
      if (!group) return;
      var panel = group.querySelector('.della-fotos-panel');
      var track = panel ? panel.querySelector('.della-fotos-track') : null;
      if (track) {
        refreshOrdemFromStrip(track);
        refreshPrincipalFromStrip(track);
      }
    });
  }

  /* =========================================================================
     CATEGORIA PAI → SUBCATEGORIA (filtro do dropdown no admin)
     ========================================================================= */

  function initCategoriaPaiFiltro() {
    var paiSel = document.getElementById('id_categoria_pai');
    var subSel = document.getElementById('id_categoria');
    if (!paiSel || !subSel) return;
    if (subSel.dataset.dellaCatFiltroBound === '1') return;
    subSel.dataset.dellaCatFiltroBound = '1';

    // Captura todas as opções (com data-parent vindo do widget custom) na inicialização
    var todas = Array.from(subSel.options)
      .filter(function (opt) { return opt.value; })
      .map(function (opt) {
        return {
          value: opt.value,
          text: opt.text,
          parent: opt.dataset.parent || '',
        };
      });

    function filtrar() {
      var paiId = String(paiSel.value || '');
      var valorAtual = String(subSel.value || '');

      // Sem categoria pai selecionada, mantém todas as subcategorias visíveis
      if (!paiId) return;

      // Limpa as opções antigas (mantém só o placeholder vazio se houver)
      Array.from(subSel.options).forEach(function (opt) {
        if (opt.value) opt.remove();
      });
      // Garante um placeholder
      if (!subSel.querySelector('option[value=""]')) {
        var ph = document.createElement('option');
        ph.value = '';
        ph.textContent = '---------';
        subSel.insertBefore(ph, subSel.firstChild);
      }

      // Adiciona apenas as subcategorias do pai selecionado
      todas.forEach(function (opt) {
        if (opt.parent === paiId) {
          var o = document.createElement('option');
          o.value = opt.value;
          o.textContent = opt.text;
          o.dataset.parent = opt.parent;
          if (o.value === valorAtual) o.selected = true;
          subSel.appendChild(o);
        }
      });
    }

    paiSel.addEventListener('change', filtrar);
    filtrar();
  }

  function init() {
    initBulkDropzone();
    initColorPreviewSync();
    initVariationClone();
    initFormScrollPersistence();
    buildVariationStickyScrollbar();
    initPendingImageSync();
    syncPendingOptionsInColorPhotoSelects();
    buildPhotoCardStrip();
    initVariationPhotoButtons();
    initAutoPrincipal();
    initCategoriaPaiFiltro();
    window.addEventListener('resize', refreshInlineEnhancements);
    if (!window.__dellaProdutoAdminObserverStarted) {
      window.__dellaProdutoAdminObserverStarted = true;
      var observer = new MutationObserver(refreshInlineEnhancements);
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
