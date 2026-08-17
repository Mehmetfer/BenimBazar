(function () {
  function shareWithImage(payload) {
    var text = payload.text || '';
    var image = payload.image || '';
    var fallback = payload.fallback || '';
    if (navigator.share && image) {
      fetch(image, { credentials: 'same-origin' })
        .then(function (r) { return r.blob(); })
        .then(function (blob) {
          var type = blob.type || 'image/jpeg';
          var file = new File([blob], 'benimbazar-ilan.jpg', { type: type });
          if (navigator.canShare && !navigator.canShare({ files: [file] })) {
            throw new Error('cannot share files');
          }
          return navigator.share({ files: [file], text: text });
        })
        .catch(function () {
          if (fallback) {
            window.open(fallback, '_blank', 'noopener');
          }
        });
      return;
    }
    if (fallback) {
      window.open(fallback, '_blank', 'noopener');
    }
  }

  document.querySelectorAll('.js-wa-share').forEach(function (btn) {
    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      shareWithImage(window.__cxWaShare || {});
    });
  });
})();
