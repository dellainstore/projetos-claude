document.addEventListener('DOMContentLoaded', () => {
  const configEl = document.getElementById('checkout-config');
  if (!configEl) return;

  let config = null;
  try {
    config = JSON.parse(configEl.textContent || '{}');
  } catch (_) {
    return;
  }

  let subtotal = parseFloat(config.subtotal || 0);
  window.SUBTOTAL = subtotal;
  let descontoAtual = 0;
  window._descontoAtualCheckout = 0;

  const secoes = document.querySelectorAll('.checkout-secao');
  const steppers = document.querySelectorAll('.stepper-item');
  const cepInput = document.getElementById('id_cep');
  const btnCep = document.getElementById('btn-buscar-cep');
  const camposEnd = document.getElementById('campos-endereco');

  function irParaEtapa(n) {
    secoes.forEach((s, i) => {
      s.classList.toggle('bloqueada', i + 1 !== n);
      s.classList.toggle('ativa', i + 1 === n);
    });
    steppers.forEach((s, i) => {
      s.classList.toggle('ativo', i + 1 === n);
      s.classList.toggle('concluido', i + 1 < n);
    });
    const secaoAtiva = document.getElementById('secao-' + n);
    if (secaoAtiva) {
      const offsetTopo = secaoAtiva.getBoundingClientRect().top + window.scrollY - 110;
      window.scrollTo({ top: offsetTopo, behavior: 'smooth' });
    }
  }

  function validarEtapa1() {
    const obrigatorios = [
      'id_nome_completo', 'id_email', 'id_cpf',
      'id_cep', 'id_logradouro', 'id_numero_entrega',
      'id_bairro', 'id_cidade', 'id_estado',
    ];
    let ok = true;
    obrigatorios.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      const vazio = !el.value.trim();
      el.closest('.checkout-campo')?.classList.toggle('erro', vazio);
      if (vazio) ok = false;
    });
    if (!ok) {
      document.getElementById('id_nome_completo')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return ok;
  }

  function validarFrete() {
    const opcaoFrete = document.getElementById('id_opcao_frete')?.value;
    if (!opcaoFrete) {
      const erroEl = document.getElementById('frete-erro');
      erroEl?.classList.remove('hidden');
      if (erroEl) erroEl.textContent = 'Selecione uma opção de frete.';
      return false;
    }
    return true;
  }

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
        document.getElementById('id_bairro').value = dados.bairro;
        document.getElementById('id_cidade').value = dados.cidade;
        document.getElementById('id_estado').value = dados.estado;
        // Ao trocar CEP: limpa número e complemento para preenchimento manual
        const numInput = document.getElementById('id_numero_entrega');
        const semNumCheck = document.getElementById('id_sem_numero');
        if (semNumCheck) { semNumCheck.checked = false; }
        if (numInput) { numInput.value = ''; numInput.readOnly = false; numInput.classList.remove('campo-readonly'); }
        document.getElementById('id_complemento').value = '';
        camposEnd?.classList.remove('hidden');
        numInput?.focus();
      } else if (!silencioso) {
        alert('CEP não encontrado. Verifique e tente novamente.');
      }
    } catch (_) {
      if (!silencioso) {
        alert('Não foi possível consultar o CEP. Preencha o endereço manualmente.');
      }
      camposEnd?.classList.remove('hidden');
    } finally {
      if (btnCep) {
        btnCep.disabled = false;
        btnCep.innerHTML = '<i class="fas fa-search"></i>';
      }
    }
  }

  async function carregarFrete() {
    const cep = document.getElementById('id_cep').value.replace(/\D/g, '');
    const loading = document.getElementById('frete-loading');
    const opcoesEl = document.getElementById('frete-opcoes');
    const erroEl = document.getElementById('frete-erro');

    loading?.classList.remove('hidden');
    if (opcoesEl) opcoesEl.innerHTML = '';
    erroEl?.classList.add('hidden');

    try {
      const res = await fetch(`/carrinho/frete/?cep=${cep}`);
      const dados = await res.json();
      loading?.classList.add('hidden');

      if (dados.status !== 'ok' || !dados.opcoes?.length) {
        erroEl?.classList.remove('hidden');
        return;
      }

      const freteMeta = parseFloat(config.frete_meta || '0');
      const freteGratis = freteMeta > 0 && subtotal >= freteMeta;

      if (opcoesEl) {
        opcoesEl.innerHTML = dados.opcoes.map((op, i) => {
          if (op.id === 'retirada_loja') {
            return `
          <label class="frete-opcao" for="frete_${op.id}">
            <input type="radio" name="_frete_visual" id="frete_${op.id}"
                   value="${op.id}" ${i === 0 ? 'checked' : ''}
                   data-preco="${op.preco}" data-nome="Retirada na Loja"
                   data-prazo="0" data-frete-radio="1">
            <span class="frete-opcao-info">
              <span class="frete-opcao-nome">Retire na Loja - Rua Visconde da Luz, 183 - Vila Nova Conceição - São Paulo/SP</span>
              <span class="frete-opcao-prazo">Disponível em até 2h após confirmação do pagamento</span>
            </span>
            <span class="frete-opcao-preco">Grátis</span>
          </label>`;
          }
          const precoEfetivo = freteGratis ? '0' : op.preco;
          const precoLabel = parseFloat(precoEfetivo) === 0
            ? 'Grátis'
            : `R$ ${parseFloat(precoEfetivo).toFixed(2).replace('.', ',')}`;
          return `
          <label class="frete-opcao" for="frete_${op.id}">
            <input type="radio" name="_frete_visual" id="frete_${op.id}"
                   value="${op.id}" ${i === 0 ? 'checked' : ''}
                   data-preco="${precoEfetivo}" data-nome="${op.nome} ${op.empresa}"
                   data-prazo="${op.prazo}" data-frete-radio="1">
            <span class="frete-opcao-info">
              <span class="frete-opcao-nome">${op.nome} <small>${op.empresa}</small></span>
              <span class="frete-opcao-prazo">${op.descricao}</span>
            </span>
            <span class="frete-opcao-preco">${precoLabel}</span>
          </label>`;
        }).join('');
      }

      const primeiroRadio = opcoesEl?.querySelector('input[type="radio"]');
      if (primeiroRadio) selecionarFrete(primeiroRadio);
    } catch (_) {
      loading?.classList.add('hidden');
      erroEl?.classList.remove('hidden');
    }
  }

  function fmtBRL(v) {
    return 'R$ ' + v.toFixed(2).replace('.', ',');
  }

  function atualizarResumoTotal() {
    const freteVal = parseFloat(document.getElementById('id_valor_frete')?.value || '0') || 0;
    const freteEl = document.getElementById('resumo-frete-valor');
    const opcaoSelecionada = document.getElementById('id_opcao_frete')?.value;
    if (freteEl && opcaoSelecionada) {
      freteEl.textContent = freteVal === 0 ? 'Grátis' : fmtBRL(freteVal);
    }
    const total = Math.max(0, subtotal - descontoAtual + freteVal);
    document.getElementById('resumo-total').textContent = fmtBRL(total);
  }

  function selecionarFrete(radio) {
    document.getElementById('id_opcao_frete').value = radio.value;
    document.getElementById('id_servico_frete_nome').value = radio.dataset.nome;
    document.getElementById('id_valor_frete').value = radio.dataset.preco;
    document.getElementById('id_prazo_frete').value = radio.dataset.prazo;
    const frete = parseFloat(radio.dataset.preco);
    const freteEl = document.getElementById('resumo-frete-valor');
    if (freteEl) freteEl.textContent = frete === 0 ? 'Grátis' : fmtBRL(frete);
    atualizarResumoTotal();
  }

  async function aplicarCupom() {
    const input = document.getElementById('id_cupom_codigo');
    const feedback = document.getElementById('cupom-feedback');
    const codigo = (input?.value || '').trim().toUpperCase();
    if (!codigo) return;
    input.value = codigo;

    try {
      const res = await fetch(`/carrinho/validar-cupom/?codigo=${encodeURIComponent(codigo)}&subtotal=${subtotal}`);
      const data = await res.json();
      feedback.classList.remove('hidden', 'cupom-ok', 'cupom-erro');

      if (data.status === 'ok') {
        descontoAtual = parseFloat(data.desconto);
        window._descontoAtualCheckout = descontoAtual;
        if (window._atualizarParcelasCheckout) window._atualizarParcelasCheckout();
        feedback.textContent = '✓ ' + data.descricao + ' aplicado!';
        feedback.classList.add('cupom-ok');
        document.getElementById('resumo-desconto-valor').textContent = '−' + fmtBRL(descontoAtual);
        document.getElementById('resumo-desconto-linha')?.classList.remove('hidden');
        atualizarResumoTotal();
      } else {
        descontoAtual = 0;
        feedback.textContent = '✗ ' + data.erro;
        feedback.classList.add('cupom-erro');
        document.getElementById('resumo-desconto-linha')?.classList.add('hidden');
        atualizarResumoTotal();
      }
    } catch (_) {
      feedback.classList.remove('hidden');
      feedback.textContent = 'Erro ao validar cupom.';
      feedback.classList.add('cupom-erro');
    }
  }

  async function aplicarVendedor() {
    const input = document.getElementById('id_codigo_vendedor_codigo');
    const feedback = document.getElementById('vendedor-feedback');
    const codigo = (input?.value || '').trim().toUpperCase();
    if (!codigo) return;
    input.value = codigo;
    feedback.classList.remove('hidden', 'cupom-ok', 'cupom-erro');

    try {
      const res = await fetch(`/carrinho/validar-vendedor/?codigo=${encodeURIComponent(codigo)}`);
      const data = await res.json();
      if (data.status === 'ok') {
        feedback.textContent = '✓ Vendedor ' + data.nome + ' vinculado ao pedido.';
        feedback.classList.add('cupom-ok');
      } else {
        feedback.textContent = '✗ ' + data.erro;
        feedback.classList.add('cupom-erro');
      }
    } catch (_) {
      feedback.textContent = 'Erro ao validar código.';
      feedback.classList.add('cupom-erro');
    }
  }

  function initPagamentoTabs() {
    document.querySelectorAll('.pagamento-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.pagamento-tab').forEach((t) => {
          t.classList.remove('ativa');
          t.setAttribute('aria-selected', 'false');
        });
        document.querySelectorAll('.pagamento-tabpanel').forEach((p) => p.classList.remove('ativo'));

        tab.classList.add('ativa');
        tab.setAttribute('aria-selected', 'true');

        const tabId = tab.dataset.tab;
        document.getElementById(`tab-${tabId}`)?.classList.add('ativo');
        if (tabId === 'pix') {
          document.getElementById('radio_pix').checked = true;
        } else if (tabId === 'cartao') {
          document.getElementById('radio_cartao')?.click();
        }

        const paymentType = tabId === 'pix' ? 'PIX' : 'Credit Card';
        const valor = parseFloat(document.getElementById('id_valor_frete')?.value || '0') + subtotal - (window._descontoAtualCheckout || 0);
        if (window.dellaTrackGA) {
          window.dellaTrackGA('add_payment_info', { currency: 'BRL', value: valor, payment_type: paymentType });
        }
        if (window.dellaTrackMeta) {
          window.dellaTrackMeta('AddPaymentInfo', { currency: 'BRL', value: valor, content_category: paymentType });
        }
      });
    });
  }

  function atualizarParcelas() {
    const selectParcelas = document.getElementById('id_parcelas');
    if (!selectParcelas || typeof DellaParcelas === 'undefined') return;
    let total = parseFloat(document.getElementById('id_valor_frete')?.value || '0') || 0;
    total = Math.max(0, subtotal - (window._descontoAtualCheckout || 0) + total);
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
    document.querySelectorAll('.pagamento-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        if (tab.dataset.tab === 'cartao') setTimeout(atualizarParcelas, 50);
      });
    });
    window._atualizarParcelasCheckout = atualizarParcelas;
  }

  function initCartoesSalvos() {
    const blocoSalvos = document.getElementById('bloco-cartoes-salvos');
    const blocoNovo = document.getElementById('bloco-cartao-novo');
    const inputSalvoId = document.getElementById('cartao-salvo-id');
    if (!blocoSalvos) return;

    function atualizarSelecao() {
      const selecionado = document.querySelector('input[name="_cartao_salvo_radio"]:checked');
      if (!selecionado) return;

      if (selecionado.value === 'novo') {
        blocoNovo?.classList.remove('hidden');
        if (inputSalvoId) inputSalvoId.value = '';
      } else {
        blocoNovo?.classList.add('hidden');
        if (inputSalvoId) inputSalvoId.value = selecionado.value;
      }
    }

    document.querySelectorAll('input[name="_cartao_salvo_radio"]').forEach((radio) => {
      radio.addEventListener('change', atualizarSelecao);
    });

    // Define estado inicial baseado no radio marcado no load
    atualizarSelecao();
  }

  function initCheckoutSubmit() {
    document.getElementById('form-checkout')?.addEventListener('submit', async function(e) {
      const formaAtual = document.querySelector('[name="forma_pagamento"]:checked')?.value;
      const btn = document.getElementById('btn-confirmar');

      if (formaAtual !== 'cartao_credito') {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando…';
        return;
      }

      e.preventDefault();
      const erroEl = document.getElementById('cartao-erro');
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando…';
      erroEl?.classList.add('hidden');

      function mostrarErroCartao(msg) {
        if (erroEl) {
          erroEl.textContent = msg;
          erroEl.classList.remove('hidden');
          erroEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-lock"></i> Confirmar pedido';
      }

      // Se há cartão salvo selecionado, submete direto sem encrypted_card
      const cartaoSalvoId = document.getElementById('cartao-salvo-id')?.value || '';
      if (cartaoSalvoId) {
        this.submit();
        return;
      }

      const holder = (document.getElementById('card-holder')?.value || '').trim().toUpperCase();
      const number = (document.getElementById('card-number')?.value || '').replace(/\s/g, '');
      const expiry = document.getElementById('card-expiry')?.value || '';
      const cvv = (document.getElementById('card-cvv')?.value || '').trim();

      if (!holder || !number || !expiry || !cvv) {
        mostrarErroCartao('Preencha todos os dados do cartão.');
        return;
      }

      const partes = expiry.split('/');
      const expMonth = (partes[0] || '').trim();
      const expYear = '20' + (partes[1] || '').trim();

      if (typeof PagSeguro === 'undefined' || typeof PagSeguro.encryptCard !== 'function') {
        mostrarErroCartao('SDK de pagamento não carregou. Recarregue a página e tente novamente.');
        return;
      }

      try {
        const { hasErrors, errors, encryptedCard } = PagSeguro.encryptCard({
          publicKey: config.pagseguro_public_key || '',
          holder,
          number,
          expMonth,
          expYear,
          securityCode: cvv,
        });

        if (hasErrors) {
          const msgs = {
            INVALID_NUMBER: 'Número do cartão inválido.',
            INVALID_SECURITY_CODE: 'CVV inválido.',
            INVALID_EXPIRATION_MONTH: 'Mês de validade inválido.',
            INVALID_EXPIRATION_YEAR: 'Ano de validade inválido.',
            INVALID_PUBLIC_KEY: 'Erro de configuração do gateway. Tente mais tarde.',
          };
          const msg = (errors || []).map((c) => msgs[c] || c).join(' ');
          mostrarErroCartao(msg || 'Dados do cartão inválidos.');
          return;
        }

        document.getElementById('pagseguro-card-encrypted').value = encryptedCard;
        this.submit();
      } catch (err) {
        console.error('PagSeguro.encryptCard error:', err);
        mostrarErroCartao('Erro ao encriptar cartão: ' + (err?.message || String(err)));
      }
    });
  }

  function initResumoItens() {
    document.querySelectorAll('.resumo-item').forEach((itemEl) => {
      const chave = itemEl.dataset.chave;
      const qtyEl = itemEl.querySelector('.resumo-qty-valor');
      const subtotalEl = itemEl.querySelector('.resumo-item-subtotal');

      itemEl.querySelectorAll('.resumo-qty-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const acao = btn.dataset.acao;
          const atual = parseInt(qtyEl.textContent, 10) || 1;
          const nova = acao === 'mais' ? atual + 1 : acao === 'remover' ? 0 : atual - 1;
          const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

          try {
            const res = await fetch('/carrinho/atualizar/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
              body: JSON.stringify({ chave, quantidade: nova }),
            });
            const dados = await res.json();
            if (dados.status !== 'ok') return;

            if (nova <= 0) itemEl.remove();
            else qtyEl.textContent = nova;

            const itemDados = (dados.itens || []).find((i) => i.chave === chave);
            if (itemDados && subtotalEl) {
              subtotalEl.textContent = parseFloat(itemDados.subtotal).toFixed(2).replace('.', ',');
            }

            const novoSubtotal = parseFloat(dados.total_valor) || 0;
            subtotal = novoSubtotal;
            window.SUBTOTAL = novoSubtotal;

            const subtotalResumo = document.getElementById('resumo-subtotal-valor');
            if (subtotalResumo) subtotalResumo.textContent = 'R$ ' + novoSubtotal.toFixed(2).replace('.', ',');

            atualizarResumoTotal();

            const badge = document.querySelector('.badge-carrinho');
            if (badge) badge.textContent = dados.total_itens;

            if (window._atualizarParcelasCheckout) window._atualizarParcelasCheckout();
          } catch (_) {}
        });
      });
    });
  }

  document.getElementById('btn-ir-frete')?.addEventListener('click', () => {
    if (!validarEtapa1()) return;
    irParaEtapa(2);
    carregarFrete();
  });
  document.getElementById('btn-voltar-dados')?.addEventListener('click', () => irParaEtapa(1));
  document.getElementById('btn-ir-pagamento')?.addEventListener('click', () => {
    if (!validarFrete()) return;
    const freteRadio = document.querySelector('input[name="_frete_visual"]:checked');
    const tier = freteRadio?.dataset.nome || '';
    const valor = parseFloat(freteRadio?.dataset.preco || '0') + subtotal - (window._descontoAtualCheckout || 0);
    if (window.dellaTrackGA) {
      window.dellaTrackGA('add_shipping_info', { currency: 'BRL', value: valor, shipping_tier: tier });
    }
    irParaEtapa(3);
  });
  document.getElementById('btn-voltar-frete')?.addEventListener('click', () => irParaEtapa(2));
  btnCep?.addEventListener('click', () => buscarCep(cepInput?.value || '', false));
  cepInput?.addEventListener('blur', () => {
    const v = cepInput.value.replace(/\D/g, '');
    if (v.length === 8) buscarCep(v, true);
  });
  cepInput?.addEventListener('input', () => {
    let v = cepInput.value.replace(/\D/g, '').slice(0, 8);
    if (v.length > 5) v = v.slice(0, 5) + '-' + v.slice(5);
    cepInput.value = v;
  });
  document.getElementById('id_cpf')?.addEventListener('input', (e) => {
    let v = e.target.value.replace(/\D/g, '').slice(0, 11);
    if (v.length > 9) v = v.slice(0, 3) + '.' + v.slice(3, 6) + '.' + v.slice(6, 9) + '-' + v.slice(9);
    else if (v.length > 6) v = v.slice(0, 3) + '.' + v.slice(3, 6) + '.' + v.slice(6);
    else if (v.length > 3) v = v.slice(0, 3) + '.' + v.slice(3);
    e.target.value = v;
  });
  document.querySelector('input[name="telefone"]')?.addEventListener('input', (e) => {
    let v = e.target.value.replace(/\D/g, '').slice(0, 11);
    if (v.length > 6) v = '(' + v.slice(0, 2) + ') ' + v.slice(2, 7) + '-' + v.slice(7);
    else if (v.length > 2) v = '(' + v.slice(0, 2) + ') ' + v.slice(2);
    e.target.value = v;
  });
  document.getElementById('btn-aplicar-cupom')?.addEventListener('click', aplicarCupom);
  document.getElementById('id_cupom_codigo')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); aplicarCupom(); }
  });
  document.getElementById('btn-aplicar-vendedor')?.addEventListener('click', aplicarVendedor);
  document.getElementById('id_codigo_vendedor_codigo')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); aplicarVendedor(); }
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
    if (v.length > 2) v = v.slice(0, 2) + '/' + v.slice(2);
    e.target.value = v;
  });
  document.addEventListener('change', (e) => {
    const radio = e.target.closest('[data-frete-radio]');
    if (radio) selecionarFrete(radio);
  });

  function initEnderecosSalvos() {
    const fmtCep = (cep) => cep.length === 8 ? cep.slice(0, 5) + '-' + cep.slice(5) : cep;
    const blocoNovo = document.getElementById('bloco-endereco-novo');

    function aplicarEnderecoSalvo(radio) {
      const numInput = document.getElementById('id_numero_entrega');
      const semNumCheck = document.getElementById('id_sem_numero');

      document.getElementById('id_cep').value = fmtCep(radio.dataset.cep || '');
      document.getElementById('id_logradouro').value = radio.dataset.logradouro || '';
      document.getElementById('id_bairro').value = radio.dataset.bairro || '';
      document.getElementById('id_cidade').value = radio.dataset.cidade || '';
      document.getElementById('id_estado').value = radio.dataset.estado || '';
      document.getElementById('id_complemento').value = radio.dataset.complemento || '';

      const numero = radio.dataset.numero || '';
      const isSN = numero.toUpperCase() === 'S/N';
      if (semNumCheck) semNumCheck.checked = isSN;
      if (numInput) {
        numInput.value = numero;
        numInput.readOnly = isSN;
        numInput.classList.toggle('campo-readonly', isSN);
      }
    }

    document.querySelectorAll('input[name="_endereco_salvo"]').forEach((radio) => {
      radio.addEventListener('change', () => {
        const numInput = document.getElementById('id_numero_entrega');
        const semNumCheck = document.getElementById('id_sem_numero');

        if (radio.value === 'novo') {
          ['id_cep', 'id_logradouro', 'id_numero_entrega', 'id_complemento',
           'id_bairro', 'id_cidade', 'id_estado'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) { el.value = ''; el.readOnly = false; el.classList.remove('campo-readonly'); }
          });
          if (semNumCheck) semNumCheck.checked = false;
          camposEnd?.classList.add('hidden');
          blocoNovo?.classList.remove('hidden');
          cepInput?.focus();
        } else {
          aplicarEnderecoSalvo(radio);
          camposEnd?.classList.remove('hidden');
          blocoNovo?.classList.add('hidden');
        }
      });
    });

    // Aplica o endereço já selecionado no carregamento (radio com `checked`)
    const selecionado = document.querySelector('input[name="_endereco_salvo"]:checked');
    if (selecionado && selecionado.value !== 'novo') {
      aplicarEnderecoSalvo(selecionado);
    }

    initEditInline();
  }

  function initEditInline() {
    const csrf =
      document.querySelector('meta[name="csrf-token"]')?.content ||
      document.cookie.match(/csrftoken=([^;]+)/)?.[1] ||
      '';
    const onlyDigits = (s) => (s || '').replace(/\D/g, '');
    const fmtCep = (cep) => cep.length === 8 ? cep.slice(0, 5) + '-' + cep.slice(5) : cep;

    document.querySelectorAll('.checkout-endereco-card[data-endereco-pk]').forEach((card) => {
      const toggle = card.querySelector('.endereco-card-toggle');
      const editBox = card.querySelector('.endereco-card-edit');
      const btnSalvar = card.querySelector('.endereco-edit-salvar');
      const btnCancelar = card.querySelector('.endereco-edit-cancelar');
      const erroEl = card.querySelector('.endereco-edit-erro');
      const radio = card.querySelector('input[name="_endereco_salvo"]');
      if (!toggle || !editBox || !radio) return;

      function abrirEdit() {
        editBox.hidden = false;
        toggle.setAttribute('aria-expanded', 'true');
      }
      function fecharEdit() {
        editBox.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
        if (erroEl) { erroEl.hidden = true; erroEl.textContent = ''; }
      }

      toggle.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (editBox.hidden) abrirEdit(); else fecharEdit();
      });

      // Enter dentro do form inline = Salvar (evita submeter o form-checkout)
      editBox.querySelectorAll('input').forEach((inp) => {
        inp.addEventListener('keydown', (ev) => {
          if (ev.key === 'Enter') {
            ev.preventDefault();
            btnSalvar?.click();
          }
        });
      });

      btnCancelar?.addEventListener('click', (e) => {
        e.preventDefault();
        // Restaura valores originais a partir dos data-* do radio
        card.querySelectorAll('[data-edit-field]').forEach((inp) => {
          const campo = inp.dataset.editField;
          if (campo === 'cep') {
            inp.value = fmtCep(radio.dataset.cep || '');
          } else {
            inp.value = radio.dataset[campo] || '';
          }
        });
        fecharEdit();
      });

      btnSalvar?.addEventListener('click', async (e) => {
        e.preventDefault();
        if (erroEl) { erroEl.hidden = true; erroEl.textContent = ''; }
        btnSalvar.disabled = true;
        const labelOriginal = btnSalvar.textContent;
        btnSalvar.textContent = 'Salvando...';

        const dados = new FormData();
        card.querySelectorAll('[data-edit-field]').forEach((inp) => {
          let valor = inp.value.trim();
          if (inp.dataset.editField === 'cep') valor = onlyDigits(valor);
          if (inp.dataset.editField === 'estado') valor = valor.toUpperCase();
          dados.append(inp.dataset.editField, valor);
        });

        try {
          const res = await fetch(card.dataset.editUrl, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
            body: dados,
          });
          const json = await res.json();

          if (json.status !== 'ok') {
            if (erroEl) {
              const erros = json.erros || {};
              const msgs = Object.values(erros).flat();
              erroEl.textContent = msgs.length ? msgs.join(' ') : 'Não foi possível salvar.';
              erroEl.hidden = false;
            }
            return;
          }

          const end = json.endereco || {};
          radio.dataset.cep = end.cep || '';
          radio.dataset.logradouro = end.logradouro || '';
          radio.dataset.numero = end.numero || '';
          radio.dataset.complemento = end.complemento || '';
          radio.dataset.bairro = end.bairro || '';
          radio.dataset.cidade = end.cidade || '';
          radio.dataset.estado = end.estado || '';

          const linha1 = card.querySelector('[data-campo="linha1"]');
          const linha2 = card.querySelector('[data-campo="linha2"]');
          if (linha1) {
            linha1.textContent = `${end.logradouro}, ${end.numero}` +
              (end.complemento ? `, ${end.complemento}` : '');
          }
          if (linha2) {
            linha2.textContent = `${end.bairro} — ${end.cidade}/${end.estado} · ${end.cep_fmt}`;
          }

          if (radio.checked) {
            radio.dispatchEvent(new Event('change', { bubbles: true }));
          }

          fecharEdit();
        } catch (err) {
          if (erroEl) {
            erroEl.textContent = 'Erro de conexão. Tente novamente.';
            erroEl.hidden = false;
          }
        } finally {
          btnSalvar.disabled = false;
          btnSalvar.textContent = labelOriginal;
        }
      });
    });
  }

  document.getElementById('id_sem_numero')?.addEventListener('change', (e) => {
    toggleSemNumero(e.target.checked);
  });

  initPagamentoTabs();
  initCartoesSalvos();
  initCheckoutSubmit();
  initResumoItens();
  initParcelas();
  initEnderecosSalvos();

  // Pré-preenche cupom/vendedor a partir do sessionStorage (set no PDP)
  try {
    const pdpCupom = sessionStorage.getItem('della_pdp_cupom');
    const pdpVendedor = sessionStorage.getItem('della_pdp_vendedor');
    const inputCupom = document.getElementById('id_cupom_codigo');
    const inputVendedor = document.getElementById('id_codigo_vendedor_codigo');
    if (pdpCupom && inputCupom && !inputCupom.value.trim()) {
      inputCupom.value = pdpCupom;
      setTimeout(aplicarCupom, 200);
    }
    if (pdpVendedor && inputVendedor && !inputVendedor.value.trim()) {
      inputVendedor.value = pdpVendedor;
      setTimeout(aplicarVendedor, 400);
    }
  } catch (_) {}

  // Limpa sessionStorage ao confirmar pedido
  document.getElementById('form-checkout')?.addEventListener('submit', () => {
    try {
      sessionStorage.removeItem('della_pdp_cupom');
      sessionStorage.removeItem('della_pdp_vendedor');
    } catch (_) {}
  }, { once: true });

  if (config.form_errors) irParaEtapa(1);
  if (config.messages) window.scrollTo({ top: 0, behavior: 'smooth' });
});
