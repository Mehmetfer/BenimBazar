(function () {
  function syncCoverStyles(root) {
    root.querySelectorAll('[data-photo-item]').forEach(function (item) {
      var radio = item.querySelector('[data-photo-cover-existing], [data-photo-cover-new]');
      item.classList.toggle('listing-photo-editor__item--cover', !!(radio && radio.checked));
    });
  }

  function clearNewCover(form) {
    var hidden = form && form.querySelector('[data-cover-photo-new]');
    if (hidden) hidden.value = '';
  }

  function clearExistingCover(form) {
    if (!form) return;
    form.querySelectorAll('[data-photo-cover-existing]').forEach(function (r) {
      r.checked = false;
    });
  }

  function ensureExistingCover(root) {
    var checked = root.querySelector('[data-photo-cover-existing]:checked');
    if (checked) return;
    var first = root.querySelector('[data-photo-cover-existing]');
    if (first) {
      first.checked = true;
      syncCoverStyles(root);
    }
  }

  function initPhotoEditor(root) {
    var form = root.closest('form');
    root.addEventListener('click', function (e) {
      var removeBtn = e.target.closest('[data-photo-remove]');
      if (removeBtn) {
        var item = removeBtn.closest('[data-photo-item]');
        if (item) item.remove();
        if (!root.querySelector('[data-photo-item]')) {
          var empty = document.createElement('p');
          empty.className = 'listing-photo-editor__empty';
          empty.textContent = 'Tum fotograflar kaldirildi. Yeni ekleyebilir veya kaydedebilirsiniz.';
          root.appendChild(empty);
        } else {
          ensureExistingCover(root);
        }
        syncCoverStyles(root);
        document.dispatchEvent(new CustomEvent('listingPhotosChanged'));
        return;
      }
    });

    root.addEventListener('change', function (e) {
      var radio = e.target.closest('[data-photo-cover-existing]');
      if (!radio) return;
      clearNewCover(form);
      syncCoverStyles(root);
    });

    syncCoverStyles(root);
  }

  function buildNewPreviewItem(file, index) {
    var item = document.createElement('div');
    item.className = 'listing-photo-editor__item' + (index === 0 ? ' listing-photo-editor__item--cover' : '');
    item.setAttribute('data-photo-item', '1');
    item.setAttribute('data-photo-new-index', String(index));

    var label = document.createElement('label');
    label.className = 'listing-photo-editor__cover-btn';
    var radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'cover_photo_new_radio';
    radio.className = 'listing-photo-editor__cover-input';
    radio.setAttribute('data-photo-cover-new', '1');
    radio.value = '__new_' + index + '__';
    if (index === 0) radio.checked = true;
    var span = document.createElement('span');
    span.textContent = 'Ana foto';
    label.appendChild(radio);
    label.appendChild(span);

    var thumb = document.createElement('div');
    thumb.className = 'listing-photo-editor__thumb';
    var img = document.createElement('img');
    img.alt = 'Onizleme';
    img.src = URL.createObjectURL(file);
    thumb.appendChild(img);

    item.appendChild(label);
    item.appendChild(thumb);
    return item;
  }

  function initPhotoUpload(root) {
    var input = root.querySelector('[data-photo-file-input]');
    var grid = root.querySelector('[data-photo-upload-grid]');
    var hidden = root.querySelector('[data-cover-photo-new]');
    var form = root.closest('form');
    if (!input || !grid) return;

    input.addEventListener('change', function () {
      grid.innerHTML = '';
      var files = Array.prototype.slice.call(input.files || []);
      if (files.length === 0) {
        grid.hidden = true;
        if (hidden) hidden.value = '';
        document.dispatchEvent(new CustomEvent('listingPhotosChanged'));
        return;
      }
      grid.hidden = false;
      files.forEach(function (file, index) {
        grid.appendChild(buildNewPreviewItem(file, index));
      });
      if (hidden) hidden.value = '__new_0__';
      clearExistingCover(form);
      syncCoverStyles(grid);
      document.dispatchEvent(new CustomEvent('listingPhotosChanged'));
    });

    grid.addEventListener('change', function (e) {
      var radio = e.target.closest('[data-photo-cover-new]');
      if (!radio || !hidden) return;
      hidden.value = radio.value;
      clearExistingCover(form);
      syncCoverStyles(grid);
    });
  }

  document.querySelectorAll('[data-photo-editor]').forEach(initPhotoEditor);
  document.querySelectorAll('[data-photo-upload]').forEach(initPhotoUpload);
})();
