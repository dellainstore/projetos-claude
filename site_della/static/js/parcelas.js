/**
 * Gerador dinâmico de parcelas — regras D'ELLA Instore
 *
 * - 1x–5x : sem juros  (parcela mínima R$ 150,00)
 * - 6x–12x: com juros  (TAXA_MENSAL_JUROS ao mês, parcela mínima R$ 150,00)
 * - Opções onde parcela < R$ 150,00 são ocultadas automaticamente
 *
 * Para ajustar a taxa: altere TAXA_MENSAL_JUROS abaixo (ex: 0.0249 = 2,49% a.m.)
 */

(function (global) {
  'use strict';

  var PARCELA_MINIMA = 150.00;
  var MAX_PARCELAS   = 5;

  /**
   * Gera as options de parcelas (sem juros, máx 5x, mínimo R$150/parcela)
   * e popula o <select> informado.
   */
  function gerarParcelas(selectEl, total, valorAtual) {
    if (!selectEl || !total || total <= 0) return;

    selectEl.innerHTML = '';

    var adicionou = false;

    for (var n = 1; n <= MAX_PARCELAS; n++) {
      var pmt = total / n;
      if (pmt < PARCELA_MINIMA) break;  // parcelas seguintes também serão menores

      var label = n + 'x de R$ ' + pmt.toFixed(2).replace('.', ',') + ' sem juros';
      var opt   = document.createElement('option');
      opt.value       = String(n);
      opt.textContent = label;
      if (String(valorAtual) === String(n)) opt.selected = true;
      selectEl.appendChild(opt);
      adicionou = true;
    }

    // Fallback: pedido abaixo de R$150 — só 1x pelo valor cheio
    if (!adicionou) {
      var opt1 = document.createElement('option');
      opt1.value       = '1';
      opt1.textContent = '1x de R$ ' + total.toFixed(2).replace('.', ',') + ' sem juros';
      selectEl.appendChild(opt1);
    }
  }

  global.DellaParcelas = { gerarParcelas: gerarParcelas };

})(window);
