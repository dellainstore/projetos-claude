document.addEventListener('DOMContentLoaded', () => {
  const configEl = document.getElementById('checkout-config');
  if (!configEl) return;

  let config = null;
  try {
    config = JSON.parse(configEl.textContent || '{}');
  } catch (_) { return; }

  let subtotal = parseFloat(config.subtotal || 0);
  window.SUBTOTAL = subtotal;
  let descontoAtual = 0;
  window._descontoAtualCheckout = 0;

  const cepInput = document.getElementById('id_cep');
  const btnCep   = document.getElementById('btn-buscar-cep');
  const camposEnd = document.getElementById('campos-endereco');

  // ── Utilitários ────────────────────────────────────────────────────────────

  function fmtBRL(v) {
    return 'R$ ' + v.toFixed(2).replace('.', ',');
  }

  function atualizarResumoTotal() {
    const freteVal = parseFloat(document.getElementById('id_valor_frete')?.value || '0') || 0;
    const freteEl  = document.getElementById('resumo-frete-valor');
    const opcao    = document.getElementById('id_opcao_frete')?.value;
    if (freteEl && opcao) {
      freteEl.textContent = freteVal === 0 ? 'Grátis' : fmtBRL(freteVal);
      freteEl.style.color = '';
    }
    const total = Math.max(0, subtotal - descontoAtual + freteVal);
    const el = document.getElementById('resumo-total');
    if (el) el.textContent = fmtBRL(total);
  }

  function selecionarFrete(radio) {
    document.getElementById('id_opcao_frete').value        = radio.value;
    document.getElementById('id_servico_frete_nome').value = radio.dataset.nome || '';
    document.getElementById('id_valor_frete').value        = radio.dataset.preco || '0';
    document.getElementById('id_prazo_frete').value        = radio.dataset.prazo || '0';
    const frete = parseFloat(radio.dataset.preco || '0');
    const freteEl = document.getElementById('resumo-frete-valor');
    if (freteEl) freteEl.textContent = frete === 0 ? 'Grátis' : fmtBRL(frete);
    atualizarResumoTotal();
    if (window._atualizarParcelasCheckout) window._atualizarParcelasCheckout();
  }

  // ── CEP e Endereço ────────────────────────────────────────────────────────

  function toggleSemNumero(checked) {
    const numInput = document.getElementById('id_numero_entrega');
    if (!numInput) return;
    if (checked) {
      numInput.value = 'S/N';
      numInput.readOnly = true;
      numInput.classList.add('campo-readonly');
    } else {
      if (numInput.value === 'S/N') numInput.value = '';
      numInput.readOnly = false;
      numInput.classList.remove('campo-readonly');
    }
  }

  async function buscarCep(cep, silencioso = false) {
    const cepLimpo = cep.replace(/\D/g, '');
    if (cepLimpo.length !== 8) return;

    if (btnCep) {
      btnCep.disabled = true;
      btnCep.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    }

    try {
      const res = await fetch(`/carrinho/cep/${cepLimpo}/`);
      const dados = await res.json();
      if (dados.status === 'ok') {
        document.getElementById('id_logradouro').value = dados.logradouro;
        document.getElementById('id_bairro').value     = dados.bairro;
        document.getElementById('id_cidade').value     = dados.cidade;
        document.getElementById('id_estado').value     = dados.estado;
        const numInput    = document.getElementById('id_numero_entrega');
        const semNumCheck = document.getElementById('id_sem_numero');
        if (semNumCheck) semNumCheck.checked = false;
        if (numInput) { numInput.value = ''; numInput.readOnly = false; numInput.classList.remove('campo-readonly'); }
        document.getElementById('id_complemento').value = '';
        camposEnd?.style.removeProperty('display');
        numInput?.focus();
        // Carrega frete automaticamente
        await carregarFrete();
      } else if (!silencioso) {
        alert('CEP não encontrado. Verifique e tente novamente.');
        camposEnd?.style.removeProperty('display');
      }
    } catch (_) {
      if (!silencioso) {
        alert('Não foi possível consultar o CEP. Preencha o endereço manualmente.');
        camposEnd?.style.removeProperty('display');
      }
    } finally {
      if (btnCep) {
        btnCep.disabled = false;
        btnCep.innerHTML = '<i class="fas fa-search"></i>';
      }
    }
  }

  // ── Frete ─────────────────────────────────────────────────────────────────

  async function carregarFrete() {
    const cep = (document.getElementById('id_cep')?.value || '').replace(/\D/g, '');
    if (cep.length !== 8) return;

    const skEl    = document.getElementById('frete-skeleton');
    const opcoesEl = document.getElementById('frete-opcoes');
    const erroEl  = document.getElementById('frete-erro');
    const vazioEl = document.getElementById('frete-vazio');

    if (skEl)    skEl.style.display = 'flex';
    if (opcoesEl) opcoesEl.innerHTML = '';
    if (erroEl)  erroEl.classList.remove('visivel');
    if (vazioEl) vazioEl.style.display = 'none';

    try {
      const res   = await fetch(`/carrinho/frete/?cep=${cep}`);
      const dados = await res.json();

      if (skEl) skEl.style.display = 'none';

      if (dados.status !== 'ok' || !dados.opcoes?.length) {
        if (erroEl) erroEl.classList.add('visivel');
        return;
      }

      const freteMeta  = parseFloat(config.frete_meta || '0');
      const freteGratis = freteMeta > 0 && subtotal >= freteMeta;

      if (opcoesEl) {
        opcoesEl.innerHTML = dados.opcoes.map((op, i) => {
          if (op.id === 'retirada_loja') {
            return `
          <label class="co-frete-item" for="frete_${op.id}">
            <input type="radio" id="frete_${op.id}" name="_frete_visual" value="${op.id}"
                   ${i === 0 ? 'checked' : ''} data-preco="0"
                   data-nome="Retirada na Loja" data-prazo="0" data-frete-radio="1">
            <div class="co-frete-info">
              <div class="co-frete-nome">Retirar na Loja</div>
              <div class="co-frete-prazo">Rua Visconde da Luz, 183 — disponível ~2h após pagamento</div>
            </div>
            <div class="co-frete-preco">Grátis</div>
          </label>`;
          }
          const precoEfetivo = freteGratis ? '0' : op.preco;
          const precoLabel   = parseFloat(precoEfetivo) === 0
            ? 'Grátis'
            : `R$ ${parseFloat(precoEfetivo).toFixed(2).replace('.', ',')}`;
          return `
          <label class="co-frete-item" for="frete_${op.id}">
            <input type="radio" id="frete_${op.id}" name="_frete_visual" value="${op.id}"
                   ${i === 0 ? 'checked' : ''} data-preco="${precoEfetivo}"
                   data-nome="${op.nome} ${op.empresa}" data-prazo="${op.prazo}"
                   data-frete-radio="1">
            <div class="co-frete-info">
              <div class="co-frete-nome">${op.nome} <small style="color:#888">${op.empresa}</small></div>
              <div class="co-frete-prazo">${op.descricao}</div>
            </div>
            <div class="co-frete-preco">${precoLabel}</div>
          </label>`;
        }).join('');
      }

      const primeiro = opcoesEl?.querySelector('input[type="radio"]');
      if (primeiro) selecionarFrete(primeiro);
    } catch (_) {
      if (skEl)   skEl.style.display = 'none';
      if (erroEl) erroEl.classList.add('visivel');
    }
  }

  // ── Cupom / Vendedor ──────────────────────────────────────────────────────

  async function aplicarCupom() {
    const input    = document.getElementById('id_cupom_codigo');
    const feedback = document.getElementById('cupom-feedback');
    const codigo   = (input?.value || '').trim().toUpperCase();
    if (!codigo) return;
    input.value = codigo;

    try {
      const res  = await fetch(`/carrinho/validar-cupom/?codigo=${encodeURIComponent(codigo)}&subtotal=${subtotal}`);
      const data = await res.json();
      feedback.style.display = 'block';
      feedback.classList.remove('ok', 'erro');

      if (data.status === 'ok') {
        descontoAtual = parseFloat(data.desconto);
        window._descontoAtualCheckout = descontoAtual;
        if (window._atualizarParcelasCheckout) window._atualizarParcelasCheckout();
        feedback.textContent = '✓ ' + data.descricao + ' aplicado!';
        feedback.classList.add('ok');
        document.getElementById('resumo-desconto-valor').textContent = '-' + fmtBRL(descontoAtual);
        document.getElementById('resumo-desconto-linha')?.style.removeProperty('display');
        atualizarResumoTotal();
      } else {
        descontoAtual = 0;
        window._descontoAtualCheckout = 0;
        feedback.textContent = '✗ ' + data.erro;
        feedback.classList.add('erro');
        document.getElementById('resumo-desconto-linha')?.style.setProperty('display', 'none');
        atualizarResumoTotal();
      }
    } catch (_) {
      if (feedback) {
        feedback.style.display = 'block';
        feedback.textContent = 'Erro ao validar cupom.';
        feedback.classList.add('erro');
      }
    }
  }

  async function aplicarVendedor() {
    const input    = document.getElementById('id_codigo_vendedor_codigo');
    const feedback = document.getElementById('vendedor-feedback');
    const codigo   = (input?.value || '').trim().toUpperCase();
    if (!codigo) return;
    input.value = codigo;
    feedback.style.display = 'block';
    feedback.classList.remove('ok', 'erro');

    try {
      const res  = await fetch(`/carrinho/validar-vendedor/?codigo=${encodeURIComponent(codigo)}`);
      const data = await res.json();
      if (data.status === 'ok') {
        feedback.textContent = '✓ Vendedor ' + data.nome + ' vinculado.';
        feedback.classList.add('ok');
      } else {
        feedback.textContent = '✗ ' + data.erro;
        feedback.classList.add('erro');
      }
    } catch (_) {
      feedback.textContent = 'Erro ao validar código.';
      feedback.classList.add('erro');
    }
  }

  // ── Pagamento (radio cards) ───────────────────────────────────────────────

  function initPagamentoRadio() {
    const pagItems = document.querySelectorAll('.co-pag-item');

    function selecionarPagItem(itemAtivo) {
      pagItems.forEach(item => item.classList.remove('co-pag-item--ativo'));
      itemAtivo.classList.add('co-pag-item--ativo');
      const radio = itemAtivo.querySelector('input[type="radio"][name="forma_pagamento"]');
      if (radio) {
        radio.checked = true;
        const tipo       = radio.value === 'pix' ? 'PIX' : 'Credit Card';
        const freteVal   = parseFloat(document.getElementById('id_valor_frete')?.value || '0') || 0;
        const valorTotal = Math.max(0, subtotal - descontoAtual + freteVal);
        if (window.dellaTrackGA)   window.dellaTrackGA('add_payment_info', { currency: 'BRL', value: valorTotal, payment_type: tipo });
        if (window.dellaTrackMeta) window.dellaTrackMeta('AddPaymentInfo', { currency: 'BRL', value: valorTotal, content_category: tipo });
        if (window.dellaTrack)     window.dellaTrack('pagamento_selecionado', { metodo: radio.value });
        if (radio.value === 'cartao_credito') setTimeout(atualizarParcelas, 50);
      }
    }

    pagItems.forEach(item => {
      const header = item.querySelector('.co-pag-header');
      if (header) {
        header.addEventListener('click', (e) => {
          e.preventDefault();
          selecionarPagItem(item);
        });
      }
    });
  }

  // ── Parcelas ──────────────────────────────────────────────────────────────

  function atualizarParcelas() {
    const selectParcelas = document.getElementById('id_parcelas');
    if (!selectParcelas || typeof DellaParcelas === 'undefined') return;
    const freteVal = parseFloat(document.getElementById('id_valor_frete')?.value || '0') || 0;
    const total    = Math.max(0, subtotal - descontoAtual + freteVal);
    DellaParcelas.gerarParcelas(selectParcelas, total, selectParcelas.value || '1');
  }

  function initParcelas() {
    if (typeof DellaParcelas === 'undefined') return;
    const freteInput = document.getElementById('id_valor_frete');
    if (freteInput) {
      const obs = new MutationObserver(atualizarParcelas);
      obs.observe(freteInput, { attributes: true, attributeFilter: ['value'] });
      freteInput.addEventListener('change', atualizarParcelas);
    }
    window._atualizarParcelasCheckout = atualizarParcelas;
    atualizarParcelas();
  }

  // ── Cartões salvos ────────────────────────────────────────────────────────

  function initCartoesSalvos() {
    const blocoSalvos  = document.getElementById('bloco-cartoes-salvos');
    const blocoNovo    = document.getElementById('bloco-cartao-novo');
    const inputSalvoId = document.getElementById('cartao-salvo-id');
    if (!blocoSalvos) return;

    function atualizarSelecao() {
      const sel = document.querySelector('input[name="_cartao_salvo_radio"]:checked');
      if (!sel) return;
      if (sel.value === 'novo') {
        blocoNovo?.style.removeProperty('display');
        if (inputSalvoId) inputSalvoId.value = '';
      } else {
        if (blocoNovo) blocoNovo.style.display = 'none';
        if (inputSalvoId) inputSalvoId.value = sel.value;
      }
    }

    document.querySelectorAll('input[name="_cartao_salvo_radio"]').forEach((r) =>
      r.addEventListener('change', atualizarSelecao)
    );
    atualizarSelecao();
  }

  // ── Validação completa (single-page) ──────────────────────────────────────

  function validarTudo() {
    const campos = [
      'id_email', 'id_nome_completo',
      'id_cep', 'id_logradouro', 'id_numero_entrega',
      'id_bairro', 'id_cidade', 'id_estado',
      'id_cpf',
    ];
    let ok = true;
    let primeiroErro = null;

    campos.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      const wrapper = el.closest('.co-field');
      const vazio   = !el.value.trim();
      wrapper?.classList.toggle('co-field--error', vazio);
      if (vazio) {
        ok = false;
        if (!primeiroErro) primeiroErro = el;
      }
    });

    // Valida frete selecionado
    const freteId = document.getElementById('id_opcao_frete')?.value;
    if (!freteId) {
      const erroEl = document.getElementById('frete-erro');
      if (erroEl) {
        erroEl.textContent = 'Selecione uma opção de frete.';
        erroEl.classList.add('visivel');
      }
      if (!primeiroErro) {
        primeiroErro = document.getElementById('secao-frete');
      }
      ok = false;
    }

    if (primeiroErro) {
      primeiroErro.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return ok;
  }

  // ── Submit ────────────────────────────────────────────────────────────────

  function initCheckoutSubmit() {
    document.getElementById('form-checkout')?.addEventListener('submit', async function (e) {
      const forma = document.querySelector('[name="forma_pagamento"]:checked')?.value;
      const btn   = document.getElementById('btn-confirmar');

      if (!validarTudo()) {
        e.preventDefault();
        return;
      }

      if (forma !== 'cartao_credito') {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando…';
        return;
      }

      e.preventDefault();
      btn.disabled  = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando…';

      const erroEl = document.getElementById('cartao-erro');
      if (erroEl) erroEl.style.display = 'none';

      function mostrarErroCartao(msg) {
        if (erroEl) {
          erroEl.textContent = msg;
          erroEl.style.display = 'block';
          erroEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        btn.disabled  = false;
        btn.innerHTML = '<i class="fas fa-lock"></i> Pagar agora';
      }

      // Cartão salvo — submete direto
      const cartaoSalvoId = document.getElementById('cartao-salvo-id')?.value || '';
      if (cartaoSalvoId) {
        this.submit();
        return;
      }

      const holder = (document.getElementById('card-holder')?.value || '').trim().toUpperCase();
      const number = (document.getElementById('card-number')?.value || '').replace(/\s/g, '');
      const expiry = document.getElementById('card-expiry')?.value || '';
      const cvv    = (document.getElementById('card-cvv')?.value || '').trim();

      if (!holder || !number || !expiry || !cvv) {
        mostrarErroCartao('Preencha todos os dados do cartão.');
        return;
      }

      const partes   = expiry.split('/');
      const expMonth = (partes[0] || '').trim();
      const expYear  = '20' + (partes[1] || '').trim();

      if (typeof PagSeguro === 'undefined' || typeof PagSeguro.encryptCard !== 'function') {
        mostrarErroCartao('SDK de pagamento não carregou. Recarregue a página e tente novamente.');
        return;
      }

      try {
        const { hasErrors, errors, encryptedCard } = PagSeguro.encryptCard({
          publicKey:    config.pagseguro_public_key || '',
          holder,
          number,
          expMonth,
          expYear,
          securityCode: cvv,
        });

        if (hasErrors) {
          const msgs = {
            INVALID_NUMBER:           'Número do cartão inválido.',
            INVALID_SECURITY_CODE:    'CVV inválido.',
            INVALID_EXPIRATION_MONTH: 'Mês de validade inválido.',
            INVALID_EXPIRATION_YEAR:  'Ano de validade inválido.',
            INVALID_PUBLIC_KEY:       'Erro de configuração do gateway.',
          };
          const msg = (errors || []).map((c) => msgs[c] || c).join(' ');
          mostrarErroCartao(msg || 'Dados do cartão inválidos.');
          return;
        }

        document.getElementById('pagseguro-card-encrypted').value = encryptedCard;
        this.submit();
      } catch (err) {
        mostrarErroCartao('Erro ao encriptar cartão: ' + (err?.message || String(err)));
      }
    });
  }

  // ── Resumo: qtd dos itens ────────────────────────────────────────────────

  function initResumoItens() {
    document.querySelectorAll('.co-resumo-item').forEach((itemEl) => {
      const chave      = itemEl.dataset.chave;
      const qtyEl      = itemEl.querySelector('.co-qty-val');
      const subtotalEl = itemEl.querySelector('.co-item-subtotal');
      const badgeEl    = itemEl.querySelector('.co-item-badge');

      itemEl.querySelectorAll('.co-qty-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const acao  = btn.dataset.acao;
          const atual = parseInt(qtyEl?.textContent, 10) || 1;
          const nova  = acao === 'mais' ? atual + 1 : acao === 'remover' ? 0 : atual - 1;
          const csrf  = document.querySelector('meta[name="csrf-token"]')?.content ||
                        document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

          try {
            const res   = await fetch('/carrinho/atualizar/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
              body: JSON.stringify({ chave, quantidade: nova }),
            });
            const dados = await res.json();
            if (dados.status !== 'ok') return;

            if (nova <= 0) {
              itemEl.remove();
            } else {
              if (qtyEl)    qtyEl.textContent    = nova;
              if (badgeEl)  badgeEl.textContent  = nova;
            }

            const itemDados = (dados.itens || []).find((i) => i.chave === chave);
            if (itemDados && subtotalEl) {
              subtotalEl.textContent = parseFloat(itemDados.subtotal).toFixed(2).replace('.', ',');
            }

            subtotal = parseFloat(dados.total_valor) || 0;
            window.SUBTOTAL = subtotal;
            const subEl = document.getElementById('resumo-subtotal-valor');
            if (subEl) subEl.textContent = fmtBRL(subtotal);
            atualizarResumoTotal();

            const badge = document.querySelector('.badge-carrinho');
            if (badge) badge.textContent = dados.total_itens;

            if (window._atualizarParcelasCheckout) window._atualizarParcelasCheckout();
          } catch (_) {}
        });
      });
    });
  }

  // ── Endereços salvos ──────────────────────────────────────────────────────

  function initEnderecosSalvos() {
    const fmtCep    = (cep) => cep.length === 8 ? cep.slice(0, 5) + '-' + cep.slice(5) : cep;
    const blocoNovo = document.getElementById('bloco-endereco-novo');

    function aplicarEnderecoSalvo(radio) {
      const numInput    = document.getElementById('id_numero_entrega');
      const semNumCheck = document.getElementById('id_sem_numero');

      document.getElementById('id_cep').value        = fmtCep(radio.dataset.cep || '');
      document.getElementById('id_logradouro').value = radio.dataset.logradouro || '';
      document.getElementById('id_bairro').value     = radio.dataset.bairro || '';
      document.getElementById('id_cidade').value     = radio.dataset.cidade || '';
      document.getElementById('id_estado').value     = radio.dataset.estado || '';
      document.getElementById('id_complemento').value = radio.dataset.complemento || '';

      const numero = radio.dataset.numero || '';
      const isSN   = numero.toUpperCase() === 'S/N';
      if (semNumCheck) semNumCheck.checked = isSN;
      if (numInput) {
        numInput.value   = numero;
        numInput.readOnly = isSN;
        numInput.classList.toggle('campo-readonly', isSN);
      }

      camposEnd?.style.removeProperty('display');
    }

    document.querySelectorAll('input[name="_endereco_salvo"]').forEach((radio) => {
      radio.addEventListener('change', () => {
        if (radio.value === 'novo') {
          ['id_cep','id_logradouro','id_numero_entrega','id_complemento',
           'id_bairro','id_cidade','id_estado'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) { el.value = ''; el.readOnly = false; el.classList.remove('campo-readonly'); }
          });
          const semNum = document.getElementById('id_sem_numero');
          if (semNum) semNum.checked = false;
          if (camposEnd) camposEnd.style.display = 'none';
          if (blocoNovo) blocoNovo.style.removeProperty('display');
          cepInput?.focus();
        } else {
          aplicarEnderecoSalvo(radio);
          if (blocoNovo) blocoNovo.style.removeProperty('display');
          carregarFrete();
        }
      });
    });

    const selecionado = document.querySelector('input[name="_endereco_salvo"]:checked');
    if (selecionado && selecionado.value !== 'novo') {
      aplicarEnderecoSalvo(selecionado);
      carregarFrete();
    }

    initEditInline();
  }

  function initEditInline() {
    const csrf     = document.querySelector('meta[name="csrf-token"]')?.content ||
                     document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    const onlyDigits = (s) => (s || '').replace(/\D/g, '');
    const fmtCep   = (cep) => cep.length === 8 ? cep.slice(0, 5) + '-' + cep.slice(5) : cep;

    document.querySelectorAll('.checkout-endereco-card[data-endereco-pk]').forEach((card) => {
      const toggle    = card.querySelector('.endereco-card-toggle');
      const editBox   = card.querySelector('.endereco-card-edit');
      const btnSalvar = card.querySelector('.endereco-edit-salvar');
      const btnCancel = card.querySelector('.endereco-edit-cancelar');
      const erroEl    = card.querySelector('.endereco-edit-erro');
      const radio     = card.querySelector('input[name="_endereco_salvo"]');
      if (!toggle || !editBox || !radio) return;

      const abrir  = () => { editBox.hidden = false; toggle.setAttribute('aria-expanded', 'true'); };
      const fechar = () => {
        editBox.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
        if (erroEl) { erroEl.hidden = true; erroEl.textContent = ''; }
      };

      toggle.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); editBox.hidden ? abrir() : fechar(); });
      editBox.querySelectorAll('input').forEach((inp) => {
        inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); btnSalvar?.click(); } });
      });
      btnCancel?.addEventListener('click', (e) => {
        e.preventDefault();
        card.querySelectorAll('[data-edit-field]').forEach((inp) => {
          inp.value = inp.dataset.editField === 'cep' ? fmtCep(radio.dataset.cep || '') : radio.dataset[inp.dataset.editField] || '';
        });
        fechar();
      });
      btnSalvar?.addEventListener('click', async (e) => {
        e.preventDefault();
        if (erroEl) { erroEl.hidden = true; erroEl.textContent = ''; }
        btnSalvar.disabled = true;
        const orig = btnSalvar.textContent;
        btnSalvar.textContent = 'Salvando...';
        const dados = new FormData();
        card.querySelectorAll('[data-edit-field]').forEach((inp) => {
          let val = inp.value.trim();
          if (inp.dataset.editField === 'cep')    val = onlyDigits(val);
          if (inp.dataset.editField === 'estado') val = val.toUpperCase();
          dados.append(inp.dataset.editField, val);
        });
        try {
          const res  = await fetch(card.dataset.editUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
            body: dados,
          });
          const json = await res.json();
          if (json.status !== 'ok') {
            if (erroEl) {
              const msgs = Object.values(json.erros || {}).flat();
              erroEl.textContent = msgs.length ? msgs.join(' ') : 'Não foi possível salvar.';
              erroEl.hidden = false;
            }
            return;
          }
          const end = json.endereco || {};
          radio.dataset.cep        = end.cep        || '';
          radio.dataset.logradouro = end.logradouro || '';
          radio.dataset.numero     = end.numero     || '';
          radio.dataset.complemento = end.complemento || '';
          radio.dataset.bairro     = end.bairro     || '';
          radio.dataset.cidade     = end.cidade     || '';
          radio.dataset.estado     = end.estado     || '';
          const l1 = card.querySelector('[data-campo="linha1"]');
          const l2 = card.querySelector('[data-campo="linha2"]');
          if (l1) l1.textContent = `${end.logradouro}, ${end.numero}${end.complemento ? ', ' + end.complemento : ''}`;
          if (l2) l2.textContent = `${end.bairro} - ${end.cidade}/${end.estado} - ${end.cep_fmt}`;
          if (radio.checked) radio.dispatchEvent(new Event('change', { bubbles: true }));
          fechar();
        } catch (_) {
          if (erroEl) { erroEl.textContent = 'Erro de conexão.'; erroEl.hidden = false; }
        } finally {
          btnSalvar.disabled = false;
          btnSalvar.textContent = orig;
        }
      });
    });
  }

  // ── "Salvar informações" (localStorage) ──────────────────────────────────

  function initSalvarInfo() {
    const chk = document.getElementById('id_salvar_info');
    if (!chk) return;

    const campos = ['id_nome_completo','id_email','id_telefone','id_cep',
                    'id_logradouro','id_numero_entrega','id_complemento',
                    'id_bairro','id_cidade','id_estado'];

    try {
      const saved = JSON.parse(localStorage.getItem('della_checkout_info') || 'null');
      if (saved) {
        campos.forEach((id) => {
          const el = document.getElementById(id);
          if (el && !el.value && saved[id]) el.value = saved[id];
        });
      }
    } catch (_) {}

    document.getElementById('form-checkout')?.addEventListener('submit', () => {
      if (!chk.checked) return;
      try {
        const obj = {};
        campos.forEach((id) => {
          const el = document.getElementById(id);
          if (el) obj[id] = el.value;
        });
        localStorage.setItem('della_checkout_info', JSON.stringify(obj));
      } catch (_) {}
    });
  }

  // ── Máscaras ──────────────────────────────────────────────────────────────

  cepInput?.addEventListener('input', () => {
    let v = cepInput.value.replace(/\D/g, '').slice(0, 8);
    if (v.length > 5) v = v.slice(0, 5) + '-' + v.slice(5);
    cepInput.value = v;
  });
  cepInput?.addEventListener('blur', () => {
    const v = cepInput.value.replace(/\D/g, '');
    if (v.length === 8) buscarCep(v, true);
  });
  btnCep?.addEventListener('click', () => buscarCep(cepInput?.value || '', false));

  document.getElementById('id_cpf')?.addEventListener('input', (e) => {
    let v = e.target.value.replace(/\D/g, '');
    if (v.length > 14) v = v.slice(0, 14);
    if (v.length <= 11) {
      if (v.length > 9) v = v.slice(0,3)+'.'+v.slice(3,6)+'.'+v.slice(6,9)+'-'+v.slice(9);
      else if (v.length > 6) v = v.slice(0,3)+'.'+v.slice(3,6)+'.'+v.slice(6);
      else if (v.length > 3) v = v.slice(0,3)+'.'+v.slice(3);
    } else {
      if (v.length > 12) v = v.slice(0,2)+'.'+v.slice(2,5)+'.'+v.slice(5,8)+'/'+v.slice(8,12)+'-'+v.slice(12);
      else if (v.length > 8) v = v.slice(0,2)+'.'+v.slice(2,5)+'.'+v.slice(5,8)+'/'+v.slice(8);
      else if (v.length > 5) v = v.slice(0,2)+'.'+v.slice(2,5)+'.'+v.slice(5);
      else if (v.length > 2) v = v.slice(0,2)+'.'+v.slice(2);
    }
    e.target.value = v;
  });

  document.querySelector('[name="telefone"]')?.addEventListener('input', (e) => {
    let v = e.target.value.replace(/\D/g, '').slice(0, 11);
    if (v.length > 6) v = '(' + v.slice(0,2) + ') ' + v.slice(2,7) + '-' + v.slice(7);
    else if (v.length > 2) v = '(' + v.slice(0,2) + ') ' + v.slice(2);
    e.target.value = v;
  });

  document.getElementById('card-number')?.addEventListener('input', (e) => {
    let v = e.target.value.replace(/\D/g, '').slice(0, 16);
    e.target.value = v.replace(/(.{4})/g, '$1 ').trim();
  });
  document.getElementById('card-holder')?.addEventListener('input', (e) => {
    e.target.value = e.target.value.toUpperCase();
  });
  document.getElementById('card-expiry')?.addEventListener('input', (e) => {
    let v = e.target.value.replace(/\D/g, '').slice(0, 4);
    if (v.length > 2) v = v.slice(0,2) + '/' + v.slice(2);
    e.target.value = v;
  });

  // ── Frete: evento change nos radios gerados dinamicamente ─────────────────

  document.addEventListener('change', (e) => {
    const radio = e.target.closest('[data-frete-radio]');
    if (radio) selecionarFrete(radio);
  });

  // ── Cupom / Vendedor eventos ──────────────────────────────────────────────

  document.getElementById('btn-aplicar-cupom')?.addEventListener('click', aplicarCupom);
  document.getElementById('id_cupom_codigo')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); aplicarCupom(); }
  });
  document.getElementById('btn-aplicar-vendedor')?.addEventListener('click', aplicarVendedor);
  document.getElementById('id_codigo_vendedor_codigo')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); aplicarVendedor(); }
  });

  // ── Sem numero ────────────────────────────────────────────────────────────

  document.getElementById('id_sem_numero')?.addEventListener('change', (e) => {
    toggleSemNumero(e.target.checked);
  });

  // ── Pré-preenche cupom/vendedor do PDP ────────────────────────────────────

  try {
    const pdpCupom    = sessionStorage.getItem('della_pdp_cupom');
    const pdpVendedor = sessionStorage.getItem('della_pdp_vendedor');
    const inCupom     = document.getElementById('id_cupom_codigo');
    const inVendedor  = document.getElementById('id_codigo_vendedor_codigo');
    if (pdpCupom    && inCupom    && !inCupom.value.trim())    { inCupom.value = pdpCupom; setTimeout(aplicarCupom, 200); }
    if (pdpVendedor && inVendedor && !inVendedor.value.trim()) { inVendedor.value = pdpVendedor; setTimeout(aplicarVendedor, 400); }
  } catch (_) {}

  document.getElementById('form-checkout')?.addEventListener('submit', () => {
    try {
      sessionStorage.removeItem('della_pdp_cupom');
      sessionStorage.removeItem('della_pdp_vendedor');
    } catch (_) {}
  }, { once: true });

  // ── Guest: captura de e-mail e desbloqueio de campos ────────────────────

  function initGuestEmailCapture() {
    const overlay = document.getElementById('co-lock-overlay');
    if (!overlay) return;

    const emailInput = document.getElementById('id_email');
    if (!emailInput) return;

    let emailCapturado = false;

    function validarEmail(email) {
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    function desbloquear() {
      overlay.style.display = 'none';
      emailCapturado = true;
    }

    async function capturarEmail() {
      const email = emailInput.value.trim();
      if (!validarEmail(email)) return;
      const nome     = (document.getElementById('id_nome_completo')?.value || '').trim();
      const telefone = (document.getElementById('id_telefone')?.value || '').trim();
      const csrf     = document.querySelector('meta[name="csrf-token"]')?.content ||
                       document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      try {
        const res  = await fetch('/carrinho/checkout/capturar-email/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
          body: JSON.stringify({ email, nome, telefone }),
        });
        const data = await res.json();
        if (data.status === 'ok') desbloquear();
      } catch (_) {
        desbloquear();
      }
    }

    async function atualizarDadosGuest() {
      if (!emailCapturado) return;
      const email = emailInput.value.trim();
      if (!validarEmail(email)) return;
      const nome     = (document.getElementById('id_nome_completo')?.value || '').trim();
      const telefone = (document.getElementById('id_telefone')?.value || '').trim();
      const csrf     = document.querySelector('meta[name="csrf-token"]')?.content ||
                       document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      try {
        await fetch('/carrinho/checkout/capturar-email/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
          body: JSON.stringify({ email, nome, telefone }),
        });
      } catch (_) {}
    }

    emailInput.addEventListener('blur', capturarEmail);
    document.getElementById('id_nome_completo')?.addEventListener('blur', atualizarDadosGuest);
    document.getElementById('id_telefone')?.addEventListener('blur', atualizarDadosGuest);

    // Se o formulario foi submetido com erro e o e-mail ja esta preenchido, desbloqueia
    if (validarEmail(emailInput.value.trim())) desbloquear();
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  initPagamentoRadio();
  initCartoesSalvos();
  initCheckoutSubmit();
  initResumoItens();
  initParcelas();
  initEnderecosSalvos();
  initSalvarInfo();
  initGuestEmailCapture();

  // Rola para topo em caso de erros do servidor
  if (config.form_errors || config.messages) {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
});
