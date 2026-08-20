(function () {
  var cfg = window.cxListingQuality || {};
  if (!cfg.enabled) return;

  var root = document.querySelector('[data-listing-quality]');
  if (!root) return;

  var form = root.closest('form');
  if (!form) return;

  var scoreEl = root.querySelector('[data-quality-score]');
  var fillEl = root.querySelector('[data-quality-fill]');
  var checksEl = root.querySelector('[data-quality-checks]');
  var minPhotos = parseInt(cfg.min_photos, 10) || 3;
  var minDesc = parseInt(cfg.min_description_chars, 10) || 10;
  var minTitle = parseInt(cfg.min_title_chars, 10) || 10;
  var requirePrice = cfg.require_price_on_sale !== false;
  var keptPhotos = parseInt(cfg.existing_photos, 10) || 0;

  function textLen(el) {
    if (!el) return 0;
    return (el.value || '').trim().length;
  }

  function countPhotos() {
    var keptInputs = form.querySelectorAll('input[name="keep_photos[]"]');
    var keptCount = keptInputs.length;
    var fileInput = form.querySelector('[data-photo-file-input]');
    var newCount = fileInput && fileInput.files ? fileInput.files.length : 0;
    if (form.querySelector('[name="photo_editor"]')) {
      return keptCount + newCount;
    }
    return newCount;
  }

  function saleMode() {
    var mode = form.querySelector('[name="listing_mode"]');
    return mode && mode.value === 'SALE';
  }

  function hasPrice() {
    if (!saleMode()) return true;
    var priceFields = form.querySelectorAll('[data-quality-price]');
    for (var i = 0; i < priceFields.length; i++) {
      var v = parseFloat(priceFields[i].value || '0');
      if (v > 0) return true;
    }
    return false;
  }

  function render() {
    var photoCount = countPhotos();
    var titleOk = textLen(form.querySelector('[name="title"]')) >= minTitle;
    var descOk = textLen(form.querySelector('[name="description"]')) >= minDesc;
    var photosOk = photoCount >= minPhotos;
    var priceOk = !requirePrice || !saleMode() || hasPrice();

    var checks = [
      { ok: titleOk, label: 'Baslik (' + minTitle + '+ karakter)' },
      { ok: descOk, label: 'Aciklama (' + minDesc + '+ karakter)' },
      { ok: photosOk, label: 'Fotograf (' + photoCount + '/' + minPhotos + ')' },
    ];
    if (requirePrice) {
      checks.push({ ok: priceOk, label: saleMode() ? 'Satilik fiyat' : 'Fiyat (satilik modunda)' });
    }

    var score = 0;
    checks.forEach(function (c) { if (c.ok) score += Math.floor(100 / checks.length); });
    if (score > 100) score = 100;

    var cls = score >= 75 ? 'ok' : (score >= 50 ? 'warn' : 'bad');
    scoreEl.textContent = score + '/100';
    scoreEl.className = 'listing-quality__score listing-quality__score--' + cls;
    fillEl.style.width = score + '%';
    fillEl.className = 'listing-quality__fill listing-quality__fill--' + cls;

    checksEl.innerHTML = checks.map(function (c) {
      return '<li class="listing-quality__check' + (c.ok ? ' is-ok' : ' is-miss') + '">' + c.label + '</li>';
    }).join('');
  }

  form.addEventListener('input', render);
  form.addEventListener('change', render);
  document.addEventListener('listingPhotosChanged', render);
  render();
})();
