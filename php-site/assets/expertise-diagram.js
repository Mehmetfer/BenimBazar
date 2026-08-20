(function () {
  function initDiagram(root) {
    var metaEl = root.querySelector('[data-expertise-meta]');
    var meta = { parts: {}, colors: {}, abbrevs: {}, readonly: false };
    try {
      meta = JSON.parse(metaEl ? metaEl.textContent || '{}' : '{}');
    } catch (e) {}
    var readonly = !!meta.readonly || root.getAttribute('data-expertise-readonly') === '1';
    var colors = meta.colors || {};
    var abbrevs = meta.abbrevs || {};
    var labels = meta.parts || {};
    var picker = root.querySelector('[data-expertise-picker]');
    var pickerTitle = root.querySelector('[data-expertise-picker-title]');
    var summary = root.querySelector('[data-expertise-summary]');
    var selectedPart = null;
    var svgNs = 'http://www.w3.org/2000/svg';

    function statusLabel(status) {
      var abbr = abbrevs[status];
      return abbr ? status + ' (' + abbr + ')' : status;
    }

    function inputFor(part) {
      return root.querySelector('[data-part-input="' + part + '"]');
    }

    function partsFor(part) {
      return root.querySelectorAll('.expertise-part[data-part="' + part + '"]');
    }

    function shapesIn(g) {
      return g.querySelectorAll(':scope > rect, :scope > path, :scope > polygon');
    }

    function shapeCenter(shape) {
      try {
        var box = shape.getBBox();
        return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
      } catch (err) {
        return { x: 0, y: 0 };
      }
    }

    function clearMarker(g) {
      var old = g.querySelector('.expertise-part__marker');
      if (old) old.remove();
    }

    function ensureMarker(g, shape, status) {
      clearMarker(g);
      var c = shapeCenter(shape);
      var abbr = abbrevs[status] || status;
      var color = colors[status] || '#6fbf4a';
      var marker = document.createElementNS(svgNs, 'g');
      marker.setAttribute('class', 'expertise-part__marker');
      marker.setAttribute('pointer-events', 'none');

      var circle = document.createElementNS(svgNs, 'circle');
      circle.setAttribute('cx', String(Math.round(c.x)));
      circle.setAttribute('cy', String(Math.round(c.y)));
      circle.setAttribute('r', abbr.length > 1 ? '14' : '12');
      circle.setAttribute('fill', color);
      circle.setAttribute('stroke', '#fff');
      circle.setAttribute('stroke-width', '2');

      var text = document.createElementNS(svgNs, 'text');
      text.setAttribute('class', 'expertise-part__abbr');
      text.setAttribute('x', String(Math.round(c.x)));
      text.setAttribute('y', String(Math.round(c.y + 1)));
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('dominant-baseline', 'middle');
      text.textContent = abbr;

      marker.appendChild(circle);
      marker.appendChild(text);
      g.appendChild(marker);
    }

    function applyPartVisual(part, status) {
      partsFor(part).forEach(function (g) {
        var shapes = shapesIn(g);
        shapes.forEach(function (shape) {
          if (!status) {
            shape.removeAttribute('data-status');
            shape.style.fill = '';
            shape.style.stroke = '';
            shape.style.fillOpacity = '';
            shape.style.strokeOpacity = '';
            return;
          }
          shape.setAttribute('data-status', status);
          shape.style.fill = colors[status] || '#6fbf4a';
          shape.style.fillOpacity = '0.28';
          shape.style.stroke = colors[status] || '#fff';
          shape.style.strokeOpacity = '0.9';
        });

        if (!status) {
          clearMarker(g);
          g.classList.remove('is-marked');
          return;
        }

        var first = shapes[0];
        if (first) {
          ensureMarker(g, first, status);
        }
        g.classList.add('is-marked');
      });
    }

    function refreshSummary() {
      if (!summary) return;
      summary.innerHTML = '';
      Object.keys(labels).forEach(function (part) {
        var inp = inputFor(part);
        var status = inp ? String(inp.value || '') : '';
        if (!status) return;
        var li = document.createElement('li');
        li.innerHTML = '<strong>' + labels[part] + '</strong> · <span style="color:' + (colors[status] || '#fff') + '">' + statusLabel(status) + '</span>';
        summary.appendChild(li);
      });
      if (!summary.children.length) {
        summary.innerHTML = '<li class="is-empty">Henüz parça işaretlenmedi.</li>';
      }
    }

    function setPartStatus(part, status) {
      var inp = inputFor(part);
      if (!inp) return;
      inp.value = status || '';
      applyPartVisual(part, status || '');
      refreshSummary();
      var hasBox = document.getElementById('expertise_has');
      if (hasBox && status) {
        hasBox.checked = true;
      }
    }

    function selectPart(part) {
      selectedPart = part;
      root.querySelectorAll('.expertise-part').forEach(function (g) {
        g.classList.toggle('is-active', g.getAttribute('data-part') === part);
      });
      if (readonly || !picker) return;
      picker.hidden = false;
      if (pickerTitle) {
        pickerTitle.textContent = labels[part] || part;
      }
      var current = inputFor(part);
      var curVal = current ? current.value : '';
      picker.querySelectorAll('[data-status]').forEach(function (btn) {
        btn.classList.toggle('is-selected', btn.getAttribute('data-status') === curVal);
      });
    }

    Object.keys(labels).forEach(function (part) {
      var inp = inputFor(part);
      if (inp && inp.value) {
        applyPartVisual(part, inp.value);
      }
    });
    refreshSummary();

    root.querySelectorAll('.expertise-part').forEach(function (g) {
      g.addEventListener('click', function () {
        selectPart(g.getAttribute('data-part'));
      });
      g.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          selectPart(g.getAttribute('data-part'));
        }
      });
    });

    if (!readonly && picker) {
      picker.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-status]');
        if (!btn || !selectedPart) return;
        setPartStatus(selectedPart, btn.getAttribute('data-status') || '');
        picker.querySelectorAll('[data-status]').forEach(function (b) {
          b.classList.toggle('is-selected', b === btn);
        });
      });
    }
  }

  document.querySelectorAll('[data-expertise-diagram]').forEach(initDiagram);
})();
