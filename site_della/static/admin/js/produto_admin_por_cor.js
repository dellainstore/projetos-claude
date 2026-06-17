(function () {
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  ready(function () {
    var imageGroup = document.getElementById('imagens-group');
    if (!imageGroup) return;

    var variationGroup = document.getElementById('variacoes-group');
    var corPrincipalSelect = document.getElementById('id_cor_principal');
    var root = null;
    var draggingCard = null;

    // ── Auto-scroll e scroll-da-roda durante drag ─────────────────────────
    var autoScrollRAF = null;
    var dragClientY = 0;
    var SCROLL_ZONE = 220;  // px da borda que ativa o scroll
    var SCROLL_SPEED = 18;  // px por frame

    function onDragOver(e) { dragClientY = e.clientY; }

    function autoScrollStep() {
      if (!draggingCard) return;
      var vh = window.innerHeight;
      if (dragClientY < SCROLL_ZONE) {
        window.scrollBy(0, -SCROLL_SPEED * (1 - dragClientY / SCROLL_ZONE));
      } else if (dragClientY > vh - SCROLL_ZONE) {
        window.scrollBy(0, SCROLL_SPEED * (1 - (vh - dragClientY) / SCROLL_ZONE));
      }
      autoScrollRAF = requestAnimationFrame(autoScrollStep);
    }

    function onWheelDuringDrag(e) {
      if (!draggingCard) return;
      window.scrollBy(0, e.deltaY);
    }

    function startAutoScroll() {
      document.addEventListener('dragover', onDragOver);
      document.addEventListener('wheel', onWheelDuringDrag, { passive: true });
      autoScrollRAF = requestAnimationFrame(autoScrollStep);
    }

    function stopAutoScroll() {
      document.removeEventListener('dragover', onDragOver);
      document.removeEventListener('wheel', onWheelDuringDrag);
      if (autoScrollRAF) { cancelAnimationFrame(autoScrollRAF); autoScrollRAF = null; }
    }

    function getImageRows() {
      return Array.from(imageGroup.querySelectorAll('tr.form-row')).filter(function (row) {
        return !row.classList.contains('empty-form');
      });
    }

    function getRowPrefix(row) {
      var input = row.querySelector('input[name^="imagens-"]');
      if (!input) return '';
      var match = input.name.match(/^(imagens-\d+)-/);
      return match ? match[1] : '';
    }

    function getRowFileInput(row) {
      return row.querySelector('input[type="file"][name$="-imagem"]');
    }

    function getRowDeleteInput(row) {
      return row.querySelector('input[type="checkbox"][name$="-DELETE"]');
    }

    function getRowPrincipalInput(row) {
      return row.querySelector('input[type="checkbox"][name$="-principal"]');
    }

    function getRowOrderInput(row) {
      return row.querySelector('input[name$="-ordem"]');
    }

    function getRowColorSelect(row) {
      return row.querySelector('select[name$="-cor"]');
    }

    function isDeletedRow(row) {
      var deleteInput = getRowDeleteInput(row);
      return !!(deleteInput && deleteInput.checked);
    }

    function isSavedRow(row) {
      return row.classList.contains('has_original');
    }

    function setRowColor(row, corId) {
      var select = getRowColorSelect(row);
      if (!select) return;
      select.value = corId || '';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function getRowColor(row) {
      var select = getRowColorSelect(row);
      return select ? String(select.value || '') : '';
    }

    function getPhotoUrl(row) {
      var preview = row.querySelector('.field-thumb_preview img');
      if (preview && preview.getAttribute('src')) return preview.getAttribute('src');
      if (row.dataset.previewUrl) return row.dataset.previewUrl;
      var fileInput = getRowFileInput(row);
      if (fileInput && fileInput.files && fileInput.files[0]) {
        return URL.createObjectURL(fileInput.files[0]);
      }
      return '';
    }

    function getOptionMap() {
      var map = {};
      document.querySelectorAll('#variacoes-group select[name$="-cor"] option, #imagens-group select[name$="-cor"] option').forEach(function (option) {
        if (!option.value) return;
        map[String(option.value)] = {
          id: String(option.value),
          nome: option.textContent.trim(),
        };
      });
      return map;
    }

    function getColorsFromVariations() {
      var map = getOptionMap();
      var colors = [];
      var seen = {};
      if (variationGroup) {
        variationGroup.querySelectorAll('tr.form-row:not(.empty-form)').forEach(function (row) {
          var deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
          if (deleteInput && deleteInput.checked) return;
          if (row.classList.contains('della-inline-marked-delete')) return;
          var select = row.querySelector('select[name$="-cor"]');
          if (!select) return;
          var corId = String(select.value || '');
          if (!corId || seen[corId]) return;
          seen[corId] = true;
          colors.push(map[corId] || { id: corId, nome: 'Cor' });
        });
      }

      getImageRows().forEach(function (row) {
        var corId = getRowColor(row);
        if (!corId || seen[corId]) return;
        seen[corId] = true;
        colors.push(map[corId] || { id: corId, nome: 'Cor' });
      });

      if (!colors.length) {
        colors.push({ id: '', nome: 'Fotos do produto' });
      }
      return colors;
    }

    function ensureRoot() {
      if (root) return root;
      root = document.createElement('div');
      root.className = 'della-fotos-cor-root';
      var heading = imageGroup.querySelector('h2.inline-heading');
      if (heading && heading.parentNode) {
        heading.parentNode.insertBefore(root, heading.nextSibling);
      } else {
        imageGroup.appendChild(root);
      }
      return root;
    }

    var MAX_UPLOAD_MB = 15;
    var ALLOWED_EXTS = ['jpg', 'jpeg', 'png', 'webp'];

    function validateFiles(files) {
      var erros = [];
      Array.from(files).forEach(function (file) {
        var ext = file.name.split('.').pop().toLowerCase();
        if (ALLOWED_EXTS.indexOf(ext) === -1) {
          erros.push('"' + file.name + '": formato não permitido. Use JPG, PNG ou WebP.');
        } else if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
          erros.push('"' + file.name + '": arquivo muito grande (' + (file.size / 1024 / 1024).toFixed(1) + ' MB). Máximo: ' + MAX_UPLOAD_MB + ' MB.');
        }
      });
      return erros;
    }

    function showUploadErrors(erros) {
      var banner = imageGroup.querySelector('.della-upload-error-banner');
      if (!erros.length) {
        if (banner) banner.remove();
        return;
      }
      if (!banner) {
        banner = document.createElement('div');
        banner.className = 'della-upload-error-banner';
        var heading = imageGroup.querySelector('h2.inline-heading');
        if (heading && heading.parentNode) {
          heading.parentNode.insertBefore(banner, heading.nextSibling);
        } else {
          imageGroup.insertBefore(banner, imageGroup.firstChild);
        }
      }
      banner.innerHTML = '<strong>Erro no upload:</strong><ul>' +
        erros.map(function (e) { return '<li>' + e + '</li>'; }).join('') + '</ul>';
    }

    function checkHiddenInlineErrors() {
      var errorItems = Array.from(imageGroup.querySelectorAll('.tabular.inline-related .errorlist li'));
      if (!errorItems.length) {
        showUploadErrors([]);
        return;
      }
      var messages = errorItems.map(function (li) { return li.textContent.trim(); });
      var unique = messages.filter(function (m, i) { return messages.indexOf(m) === i; });
      showUploadErrors(unique);
    }

    function hideLegacyUi() {
      imageGroup.querySelectorAll('.della-fotos-panel').forEach(function (panel) {
        panel.style.display = 'none';
      });
    }

    function syncPrincipalCheckboxes() {
      var sections = root ? Array.from(root.querySelectorAll('.della-fotos-cor-section')) : [];
      var corCapa = corPrincipalSelect ? String(corPrincipalSelect.value || '') : '';
      var targetCard = null;

      if (corCapa) {
        var sectionCapa = sections.find(function (section) { return section.dataset.corId === corCapa; });
        if (sectionCapa) {
          targetCard = sectionCapa.querySelector('.della-foto-card');
        }
      }
      if (!targetCard) {
        targetCard = root ? root.querySelector('.della-foto-card') : null;
      }

      getImageRows().forEach(function (row) {
        var input = getRowPrincipalInput(row);
        if (input) input.checked = false;
      });

      if (!targetCard) return;
      var row = imageGroup.querySelector('tr.form-row[data-row-prefix="' + targetCard.dataset.rowPrefix + '"]');
      var input = row ? getRowPrincipalInput(row) : null;
      if (input) input.checked = true;
    }

    function syncRowsFromDom() {
      if (!root) return;
      root.querySelectorAll('.della-fotos-cor-section').forEach(function (section) {
        var corId = section.dataset.corId || '';
        section.querySelectorAll('.della-foto-card').forEach(function (card, index) {
          var row = imageGroup.querySelector('tr.form-row[data-row-prefix="' + card.dataset.rowPrefix + '"]');
          if (!row) return;
          setRowColor(row, corId);
          var orderInput = getRowOrderInput(row);
          if (orderInput) orderInput.value = String(index);
        });
      });
      syncPrincipalCheckboxes();
    }

    function markRowDeleted(row) {
      var deleteInput = getRowDeleteInput(row);
      if (deleteInput) {
        deleteInput.checked = true;
        deleteInput.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    function clearNewRow(row) {
      var fileInput = getRowFileInput(row);
      if (fileInput) fileInput.value = '';
      row.dataset.previewUrl = '';
      // Limpa cor e ordem para que Django trate a linha como vazia (empty_permitted)
      // e não tente validar imagem obrigatória numa linha sem arquivo.
      var colorSelect = getRowColorSelect(row);
      if (colorSelect) colorSelect.value = '';
      var orderInput = getRowOrderInput(row);
      if (orderInput) orderInput.value = '0';
      markRowDeleted(row);
    }

    function createCard(row, index, isCoverGroup) {
      var prefix = getRowPrefix(row);
      var url = getPhotoUrl(row);
      if (!prefix || !url) return null;

      row.dataset.rowPrefix = prefix;

      var card = document.createElement('div');
      card.className = 'della-foto-card';
      card.draggable = true;
      card.dataset.rowPrefix = prefix;

      var img = document.createElement('img');
      img.src = url;
      img.alt = '';
      card.appendChild(img);

      var deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'della-foto-card-delete';
      deleteBtn.innerHTML = '&times;';
      deleteBtn.title = 'Remover foto';
      deleteBtn.addEventListener('click', function (event) {
        event.preventDefault();
        event.stopPropagation();
        if (isSavedRow(row)) {
          markRowDeleted(row);
        } else {
          clearNewRow(row);
        }
        buildGroupedPanels();
      });
      card.appendChild(deleteBtn);

      var badges = [];
      if (index === 0) badges.push('Principal da cor');
      if (index === 1) badges.push('Hover');
      if (index === 0 && isCoverGroup) badges.push('Capa do site');

      badges.forEach(function (text, badgeIndex) {
        var badge = document.createElement('span');
        badge.className = 'della-foto-card-principal-badge';
        if (badgeIndex > 0) badge.classList.add('della-foto-card-principal-badge-alt');
        badge.textContent = text;
        badge.style.bottom = (5 + (badgeIndex * 22)) + 'px';
        card.appendChild(badge);
      });

      card.addEventListener('dragstart', function () {
        draggingCard = card;
        card.classList.add('is-dragging');
        startAutoScroll();
      });
      card.addEventListener('dragend', function () {
        card.classList.remove('is-dragging');
        draggingCard = null;
        stopAutoScroll();
        root.querySelectorAll('.della-fotos-track').forEach(function (track) {
          track.classList.remove('is-file-dragover');
        });
        syncRowsFromDom();
        buildGroupedPanels();
      });

      return card;
    }

    function bindTrackEvents(track) {
      track.addEventListener('dragover', function (event) {
        event.preventDefault();
        var targetCard = event.target.closest('.della-foto-card');
        if (draggingCard) {
          if (targetCard && targetCard !== draggingCard) {
            var rect = targetCard.getBoundingClientRect();
            if (event.clientX < rect.left + (rect.width / 2)) {
              track.insertBefore(draggingCard, targetCard);
            } else {
              track.insertBefore(draggingCard, targetCard.nextSibling);
            }
          } else if (!targetCard && draggingCard.parentNode !== track) {
            track.appendChild(draggingCard);
          }
        } else if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
          track.classList.add('is-file-dragover');
        }
      });

      track.addEventListener('dragleave', function (event) {
        if (!track.contains(event.relatedTarget)) {
          track.classList.remove('is-file-dragover');
        }
      });

      track.addEventListener('drop', function (event) {
        event.preventDefault();
        track.classList.remove('is-file-dragover');
        if (draggingCard) {
          syncRowsFromDom();
          buildGroupedPanels();
          return;
        }
        if (event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
          addFilesToColor(track.dataset.corId || '', event.dataTransfer.files);
        }
      });
    }

    function findReusableRow() {
      return getImageRows().find(function (row) {
        if (isDeletedRow(row) || isSavedRow(row)) return false;
        var fileInput = getRowFileInput(row);
        return !!(fileInput && !fileInput.value && !row.dataset.previewUrl);
      }) || null;
    }

    function addInlineRow() {
      var addLink = imageGroup.querySelector('.add-row a');
      if (!addLink) return null;
      var before = getImageRows().length;
      addLink.click();
      var rows = getImageRows();
      if (rows.length > before) return rows[rows.length - 1];
      return rows[rows.length - 1] || null;
    }

    function assignFileToRow(row, file, corId, ordem) {
      var fileInput = getRowFileInput(row);
      if (!fileInput) return;
      var transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
      fileInput.dispatchEvent(new Event('change', { bubbles: true }));
      row.dataset.previewUrl = URL.createObjectURL(file);
      setRowColor(row, corId);
      var orderInput = getRowOrderInput(row);
      if (orderInput) orderInput.value = String(ordem);
      var deleteInput = getRowDeleteInput(row);
      if (deleteInput) deleteInput.checked = false;
    }

    function addFilesToColor(corId, files) {
      var erros = validateFiles(files);
      if (erros.length) {
        showUploadErrors(erros);
        return;
      }
      showUploadErrors([]);
      var track = root.querySelector('.della-fotos-track[data-cor-id="' + corId + '"]');
      var ordemBase = track ? track.querySelectorAll('.della-foto-card').length : 0;
      Array.from(files).forEach(function (file, index) {
        var row = findReusableRow() || addInlineRow();
        if (!row) return;
        assignFileToRow(row, file, corId, ordemBase + index);
      });
      buildGroupedPanels();
    }

    function buildGroupedPanels() {
      hideLegacyUi();
      ensureRoot();
      root.innerHTML = '';

      var colors = getColorsFromVariations();
      var corCapa = corPrincipalSelect ? String(corPrincipalSelect.value || '') : '';

      colors.forEach(function (color) {
        var corId = String(color.id || '');
        var rows = getImageRows()
          .filter(function (row) { return !isDeletedRow(row) && getRowColor(row) === corId; })
          .sort(function (a, b) {
            var ordemA = parseInt((getRowOrderInput(a) || {}).value || '0', 10);
            var ordemB = parseInt((getRowOrderInput(b) || {}).value || '0', 10);
            return ordemA - ordemB;
          });

        var section = document.createElement('section');
        section.className = 'della-fotos-cor-section';
        section.dataset.corId = corId;

        var header = document.createElement('div');
        header.className = 'della-fotos-cor-header';

        var titleWrap = document.createElement('div');
        titleWrap.className = 'della-fotos-cor-title-wrap';

        var title = document.createElement('h3');
        title.className = 'della-fotos-cor-title';
        title.textContent = color.nome || 'Fotos do produto';
        titleWrap.appendChild(title);

        if (corCapa && corId === corCapa) {
          var tag = document.createElement('span');
          tag.className = 'della-fotos-cor-tag';
          tag.textContent = 'Cor principal do site';
          titleWrap.appendChild(tag);
        }

        var controls = document.createElement('div');
        controls.className = 'della-fotos-cor-controls';

        var radioLabel = document.createElement('label');
        radioLabel.className = 'della-cor-principal-label';
        var radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'cor_principal_radio';
        radio.value = corId;
        radio.className = 'della-cor-principal-radio';
        if (corId === corCapa) radio.checked = true;
        radio.addEventListener('change', function () {
          if (corPrincipalSelect) {
            corPrincipalSelect.value = corId;
            corPrincipalSelect.dispatchEvent(new Event('change', { bubbles: true }));
          }
        });
        radioLabel.appendChild(radio);
        radioLabel.appendChild(document.createTextNode(' Cor principal'));

        var chooseBtn = document.createElement('button');
        chooseBtn.type = 'button';
        chooseBtn.className = 'della-strip-btn';
        chooseBtn.textContent = 'Escolher imagens';

        var picker = document.createElement('input');
        picker.type = 'file';
        picker.accept = 'image/*';
        picker.multiple = true;
        picker.style.display = 'none';

        chooseBtn.addEventListener('click', function () { picker.click(); });
        picker.addEventListener('change', function () {
          if (picker.files && picker.files.length) {
            addFilesToColor(corId, picker.files);
          }
          picker.value = '';
        });

        controls.appendChild(radioLabel);
        controls.appendChild(chooseBtn);
        controls.appendChild(picker);
        header.appendChild(titleWrap);
        header.appendChild(controls);
        section.appendChild(header);

        var track = document.createElement('div');
        track.className = 'della-fotos-track della-fotos-track-por-cor';
        track.dataset.corId = corId;
        bindTrackEvents(track);

        rows.forEach(function (row, index) {
          var card = createCard(row, index, !!corCapa && corId === corCapa);
          if (card) track.appendChild(card);
        });

        if (!rows.length) {
          var empty = document.createElement('div');
          empty.className = 'della-fotos-empty';
          empty.textContent = 'Nenhuma imagem nesta cor ainda. Arraste fotos aqui ou use “Escolher imagens”.';
          track.appendChild(empty);
        }

        section.appendChild(track);
        root.appendChild(section);
      });

      // ── Seção "Arquivo / Fotos sem produto" ──────────────────────────────────
      // Reúne fotos sem cor (cor='') ou com cor que não existe mais nas variações.
      // Não afeta o site público (essas fotos não têm cor vinculada).
      var validCorIds = {};
      colors.forEach(function (c) { if (c.id) validCorIds[String(c.id)] = true; });

      var looseRows = getImageRows().filter(function (row) {
        if (isDeletedRow(row)) return false;
        var corId = getRowColor(row);
        return !corId || !validCorIds[corId];
      }).sort(function (a, b) {
        var ordemA = parseInt((getRowOrderInput(a) || {}).value || '0', 10);
        var ordemB = parseInt((getRowOrderInput(b) || {}).value || '0', 10);
        return ordemA - ordemB;
      });

      var arquivoSection = document.createElement('section');
      arquivoSection.className = 'della-fotos-cor-section della-fotos-arquivo-section';
      arquivoSection.dataset.corId = '';

      var arquivoHeader = document.createElement('div');
      arquivoHeader.className = 'della-fotos-cor-header';

      var arquivoTitleWrap = document.createElement('div');
      arquivoTitleWrap.className = 'della-fotos-cor-title-wrap';

      var arquivoTitle = document.createElement('h3');
      arquivoTitle.className = 'della-fotos-cor-title';
      arquivoTitle.textContent = 'Arquivo — Fotos sem cor vinculada';
      arquivoTitleWrap.appendChild(arquivoTitle);

      var arquivoTag = document.createElement('span');
      arquivoTag.className = 'della-fotos-cor-tag della-fotos-arquivo-tag';
      arquivoTag.textContent = 'Não aparece no site';
      arquivoTitleWrap.appendChild(arquivoTag);

      arquivoHeader.appendChild(arquivoTitleWrap);
      arquivoSection.appendChild(arquivoHeader);

      var arquivoTrack = document.createElement('div');
      arquivoTrack.className = 'della-fotos-track della-fotos-track-por-cor della-fotos-arquivo-track';
      arquivoTrack.dataset.corId = '';

      looseRows.forEach(function (row, index) {
        var card = createCard(row, index, false);
        if (card) arquivoTrack.appendChild(card);
      });

      if (!looseRows.length) {
        var arquivoEmpty = document.createElement('div');
        arquivoEmpty.className = 'della-fotos-empty della-fotos-arquivo-empty';
        arquivoEmpty.textContent = 'Nenhuma foto no arquivo. Fotos de variações excluídas aparecerão aqui automaticamente.';
        arquivoTrack.appendChild(arquivoEmpty);
      }

      arquivoTrack.addEventListener('dragover', function (event) {
        event.preventDefault();
        var targetCard = event.target.closest('.della-foto-card');
        if (draggingCard) {
          if (targetCard && targetCard !== draggingCard) {
            var rect = targetCard.getBoundingClientRect();
            if (event.clientX < rect.left + (rect.width / 2)) {
              arquivoTrack.insertBefore(draggingCard, targetCard);
            } else {
              arquivoTrack.insertBefore(draggingCard, targetCard.nextSibling);
            }
          } else if (!targetCard && draggingCard.parentNode !== arquivoTrack) {
            arquivoTrack.appendChild(draggingCard);
          }
        }
      });
      arquivoTrack.addEventListener('drop', function (event) {
        event.preventDefault();
        if (draggingCard) {
          syncRowsFromDom();
          buildGroupedPanels();
        }
      });

      arquivoSection.appendChild(arquivoTrack);
      root.appendChild(arquivoSection);

      syncPrincipalCheckboxes();
      checkHiddenInlineErrors();
    }

    if (variationGroup) {
      variationGroup.addEventListener('change', function (event) {
        var name = event.target ? (event.target.name || '') : '';
        if (/-cor$/.test(name) || /-DELETE$/.test(name)) {
          buildGroupedPanels();
        }
      });
      // Para linhas NOVAS (sem checkbox DELETE), o × as esconde sem disparar change.
      // Usa setTimeout para rodar após admin_linhas.js marcar a linha como deletada.
      variationGroup.addEventListener('click', function (event) {
        if (event.target && event.target.matches('.della-inline-remove')) {
          setTimeout(buildGroupedPanels, 0);
        }
      });
    }
    if (corPrincipalSelect) {
      corPrincipalSelect.addEventListener('change', buildGroupedPanels);
    }
    imageGroup.addEventListener('change', function (event) {
      if (event.target && /-cor$/.test(event.target.name || '')) {
        buildGroupedPanels();
      }
    });

    // Quando o form falha e é re-renderizado, linhas extra ficam com `cor`
    // preenchida mas sem imagem (browser apaga o file input por segurança).
    // Isso faz has_changed()=True → Django exige imagem → erro permanente.
    // Limpamos essas linhas "fantasmas" uma vez na inicialização.
    function cleanOrphanedNewRows() {
      getImageRows().forEach(function (row) {
        if (isSavedRow(row) || isDeletedRow(row)) return;
        var fileInput = getRowFileInput(row);
        if (!fileInput || fileInput.value || row.dataset.previewUrl) return;
        var colorSelect = getRowColorSelect(row);
        if (colorSelect && colorSelect.value) colorSelect.value = '';
        var orderInput = getRowOrderInput(row);
        if (orderInput && orderInput.value && orderInput.value !== '0') orderInput.value = '0';
      });
    }

    new MutationObserver(function () {
      hideLegacyUi();
    }).observe(imageGroup, { childList: true, subtree: true });

    cleanOrphanedNewRows();
    buildGroupedPanels();
  });
}());
