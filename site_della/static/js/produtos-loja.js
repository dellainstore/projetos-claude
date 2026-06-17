document.addEventListener('DOMContentLoaded', () => {
  const btnFiltrosMobile = document.getElementById('btn-filtros-mobile');
  const sidebar = document.getElementById('loja-sidebar');
  if (!btnFiltrosMobile || !sidebar) return;

  btnFiltrosMobile.addEventListener('click', () => {
    const aberto = sidebar.classList.toggle('aberta');
    btnFiltrosMobile.setAttribute('aria-expanded', aberto);
  });
});
