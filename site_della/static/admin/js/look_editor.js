/* ─── Editor Visual de Pontos — Look da Semana ─────────────────────────── */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    // Só executa na página de edição do LookDaSemana
    if (!document.getElementById('id_ponto1_top')) return;

    var pontoAtivo = 1;
    var cores = { 1: '#e74c3c', 2: '#2980b9', 3: '#27ae60' };

    // ── Encontra a URL da imagem atual no campo foto ──────────────────────
    function getImagemUrl() {
      var fotoField = document.querySelector('.field-foto');
      if (!fotoField) return null;
      var img = fotoField.querySelector('img');
      if (img) return img.src;
      var link = fotoField.querySelector('a[href]');
      if (link) return link.href;
      return null;
    }

    // ── Cria o editor visual ──────────────────────────────────────────────
    function criarEditor(imgUrl) {
      var fieldset = document.querySelector('.field-ponto1_top')
        || document.querySelector('[class*="ponto"]');

      // Encontra o fieldset dos pontos pelo legend
      var legends = document.querySelectorAll('fieldset h2, fieldset legend');
      var pontoFieldset = null;
      legends.forEach(function (l) {
        if (l.textContent && l.textContent.indexOf('pontos') !== -1) {
          pontoFieldset = l.closest('fieldset') || l.parentElement;
        }
      });
      if (!pontoFieldset) {
        // Fallback: insere após o campo foto
        pontoFieldset = document.querySelector('.field-foto');
      }

      var editorDiv = document.createElement('div');
      editorDiv.id = 'look-editor-visual';
      editorDiv.style.cssText = [
        'background:#f9f9f9',
        'border:1px solid #ddd',
        'border-radius:4px',
        'padding:16px',
        'margin:16px 0',
      ].join(';');

      editorDiv.innerHTML = [
        '<h3 style="margin:0 0 10px;font-size:14px;color:#333;">',
        '  📍 Clique na foto para posicionar os pontos "+"',
        '</h3>',
        '<p style="font-size:12px;color:#666;margin:0 0 12px;">',
        '  1. Selecione o ponto que quer mover (botão abaixo).<br>',
        '  2. Clique no local exato da peça na foto.<br>',
        '  Pontos com número maior que a quantidade de produtos selecionados não aparecem no site.',
        '</p>',
        '<div id="look-btns-ponto" style="display:flex;gap:8px;margin-bottom:12px;">',
        '  <button type="button" id="look-btn-1" style="padding:6px 16px;border:2px solid #e74c3c;background:#e74c3c;color:white;border-radius:4px;cursor:pointer;font-weight:bold;">',
        '    ① Ponto 1',
        '  </button>',
        '  <button type="button" id="look-btn-2" style="padding:6px 16px;border:2px solid #2980b9;background:white;color:#2980b9;border-radius:4px;cursor:pointer;font-weight:bold;">',
        '    ② Ponto 2',
        '  </button>',
        '  <button type="button" id="look-btn-3" style="padding:6px 16px;border:2px solid #27ae60;background:white;color:#27ae60;border-radius:4px;cursor:pointer;font-weight:bold;">',
        '    ③ Ponto 3',
        '  </button>',
        '</div>',
        '<div id="look-img-wrap" style="position:relative;display:inline-block;cursor:crosshair;max-width:380px;user-select:none;">',
        '  <img id="look-editor-img" src="' + imgUrl + '" ',
        '    style="display:block;max-width:380px;width:100%;pointer-events:none;" ',
        '    draggable="false">',
        '  <div id="look-mk-1" class="look-mk" data-n="1" style="position:absolute;width:28px;height:28px;border-radius:50%;background:#e74c3c;color:white;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:13px;transform:translate(-50%,-50%);pointer-events:none;box-shadow:0 2px 6px rgba(0,0,0,.4);border:2px solid white;">1</div>',
        '  <div id="look-mk-2" class="look-mk" data-n="2" style="position:absolute;width:28px;height:28px;border-radius:50%;background:#2980b9;color:white;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:13px;transform:translate(-50%,-50%);pointer-events:none;box-shadow:0 2px 6px rgba(0,0,0,.4);border:2px solid white;">2</div>',
        '  <div id="look-mk-3" class="look-mk" data-n="3" style="position:absolute;width:28px;height:28px;border-radius:50%;background:#27ae60;color:white;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:13px;transform:translate(-50%,-50%);pointer-events:none;box-shadow:0 2px 6px rgba(0,0,0,.4);border:2px solid white;">3</div>',
        '</div>',
      ].join('');

      pontoFieldset.parentNode.insertBefore(editorDiv, pontoFieldset);

      // Posicionar marcadores com valores atuais dos campos
      atualizarMarcadores();

      // ── Clique na imagem ──────────────────────────────────────────────
      var wrap = document.getElementById('look-img-wrap');
      wrap.addEventListener('click', function (e) {
        var rect = wrap.getBoundingClientRect();
        var x = ((e.clientX - rect.left) / rect.width * 100).toFixed(1);
        var y = ((e.clientY - rect.top) / rect.height * 100).toFixed(1);

        document.getElementById('id_ponto' + pontoAtivo + '_top').value = y;
        document.getElementById('id_ponto' + pontoAtivo + '_esq').value = x;

        atualizarMarcadores();
        // Avança automaticamente para o próximo ponto
        if (pontoAtivo < 3) selecionarPonto(pontoAtivo + 1);
      });

      // ── Botões de seleção ─────────────────────────────────────────────
      [1, 2, 3].forEach(function (n) {
        document.getElementById('look-btn-' + n).addEventListener('click', function () {
          selecionarPonto(n);
        });
      });

      // Quando os campos numéricos mudam, atualiza os marcadores
      [1, 2, 3].forEach(function (n) {
        ['top', 'esq'].forEach(function (lado) {
          var input = document.getElementById('id_ponto' + n + '_' + lado);
          if (input) input.addEventListener('input', atualizarMarcadores);
        });
      });

      selecionarPonto(1);
    }

    function selecionarPonto(n) {
      pontoAtivo = n;
      [1, 2, 3].forEach(function (i) {
        var btn = document.getElementById('look-btn-' + i);
        if (!btn) return;
        var cor = cores[i];
        if (i === n) {
          btn.style.background = cor;
          btn.style.color = 'white';
          btn.style.transform = 'scale(1.08)';
        } else {
          btn.style.background = 'white';
          btn.style.color = cor;
          btn.style.transform = 'scale(1)';
        }
      });
    }

    function atualizarMarcadores() {
      [1, 2, 3].forEach(function (n) {
        var mk = document.getElementById('look-mk-' + n);
        var top = parseFloat(document.getElementById('id_ponto' + n + '_top').value) || 0;
        var esq = parseFloat(document.getElementById('id_ponto' + n + '_esq').value) || 0;
        mk.style.top = top + '%';
        mk.style.left = esq + '%';
      });
    }

    // ── Inicializar ───────────────────────────────────────────────────────
    var imgUrl = getImagemUrl();
    if (imgUrl) {
      criarEditor(imgUrl);
    } else {
      // Se ainda não tem foto, monitora quando o campo de upload mudar
      var fotoInput = document.getElementById('id_foto');
      if (fotoInput) {
        fotoInput.addEventListener('change', function () {
          var file = fotoInput.files[0];
          if (!file) return;
          var reader = new FileReader();
          reader.onload = function (e) { criarEditor(e.target.result); };
          reader.readAsDataURL(file);
        });
      }
    }
  });
})();
