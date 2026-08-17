(function () {
  var KEY = 'cx_theme';
  var root = document.documentElement;

  function current() {
    return root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  }

  function apply(theme) {
    var next = theme === 'light' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try {
      localStorage.setItem(KEY, next);
    } catch (e) {}
    syncButton();
  }

  function syncButton() {
    var btn = document.getElementById('cx-theme-toggle');
    if (!btn) return;
    var isLight = current() === 'light';
    btn.setAttribute('aria-label', isLight ? 'Karanlık moda geç' : 'Aydınlık moda geç');
    btn.setAttribute('title', isLight ? 'Karanlık mod' : 'Aydınlık mod');
    btn.setAttribute('data-theme-state', isLight ? 'light' : 'dark');
    var sun = btn.querySelector('[data-icon="sun"]');
    var moon = btn.querySelector('[data-icon="moon"]');
    if (sun) sun.hidden = !isLight;
    if (moon) moon.hidden = isLight;
  }

  function init() {
    syncButton();
    var btn = document.getElementById('cx-theme-toggle');
    if (!btn || btn.dataset.bound === '1') return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', function () {
      apply(current() === 'light' ? 'dark' : 'light');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
