(function () {
  var manualOpt = window.cxVehicleModelCustomOption || '__manual__';
  var segmentSel = document.getElementById('vehicle_segment');
  var vehicleDetails = document.getElementById('vehicle_detail_fields');
  var subcatSel = document.getElementById('listing_subcat');
  var makeSel = document.getElementById('vehicle_make_select');
  var modelSel = document.getElementById('vehicle_model_select');
  var customInput = document.getElementById('vehicle_model_custom');
  var fieldset = document.getElementById('vehicle_fields');
  var relaxed = fieldset && fieldset.getAttribute('data-vehicle-relaxed') === '1';
  var prefill = window.cxVehicleFormPrefill || {};

  function fieldValue(el) {
    if (!el || el.disabled) return '';
    return String(el.value || '').trim();
  }

  function isFilled(el) {
    if (!el || el.disabled || el.hidden) return false;
    if (el.closest('[hidden]')) return false;
    return fieldValue(el) !== '';
  }

  function syncCustomModelField() {
    if (!customInput || !modelSel) return;
    var show = modelSel.value === manualOpt;
    customInput.hidden = !show;
    customInput.required = show && !relaxed && !customInput.closest('[hidden]');
    if (!show) {
      customInput.required = false;
    }
  }

  function appendManualOption() {
    if (!modelSel || !makeSel || !makeSel.value || makeSel.value === 'Diğer') return;
    var exists = false;
    for (var i = 0; i < modelSel.options.length; i++) {
      if (modelSel.options[i].value === manualOpt) {
        exists = true;
        break;
      }
    }
    if (!exists) {
      var o = document.createElement('option');
      o.value = manualOpt;
      o.textContent = 'Listede yok — elle yaz';
      modelSel.appendChild(o);
    }
  }

  function refreshModelOptions(seg, make, keepValue) {
    if (!modelSel) return;
    var data = window.cxVehicleBrandModels && window.cxVehicleBrandModels[seg];
    var saved = keepValue ? (prefill.vehicle_model || modelSel.value) : '';
    if (saved === manualOpt || (prefill.vehicle_model_custom && prefill.vehicle_model === manualOpt)) {
      saved = manualOpt;
    }
    modelSel.innerHTML = '<option value="">Model secin</option>';
    modelSel.disabled = !make;
    if (!make || !data || !data.models) {
      syncCustomModelField();
      return;
    }
    var list = data.models[make] || [];
    var seen = {};
    list.forEach(function (m) {
      seen[m] = true;
      var o = document.createElement('option');
      o.value = m;
      o.textContent = m;
      modelSel.appendChild(o);
    });
    var extra = prefill.vehicle_model || '';
    if (extra && extra !== manualOpt && !seen[extra]) {
      var ox = document.createElement('option');
      ox.value = extra;
      ox.textContent = extra;
      modelSel.appendChild(ox);
    }
    appendManualOption();
    if (saved) {
      var found = false;
      for (var j = 0; j < modelSel.options.length; j++) {
        if (modelSel.options[j].value === saved) {
          found = true;
          break;
        }
      }
      if (!found && saved !== manualOpt && window.cxVehicleModelCustomOption) {
        modelSel.value = manualOpt;
        if (customInput && prefill.vehicle_model_custom) {
          customInput.value = prefill.vehicle_model_custom;
        } else if (customInput && prefill.vehicle_model) {
          customInput.value = prefill.vehicle_model;
        }
      } else {
        modelSel.value = saved;
      }
    }
    syncCustomModelField();
  }

  function refreshMakeModelFields(seg, isVehicle) {
    if (!makeSel) return;
    var data = window.cxVehicleBrandModels && window.cxVehicleBrandModels[seg];
    var savedMake = prefill.vehicle_make || makeSel.value;
    makeSel.innerHTML = '<option value="">Marka secin</option>';
    if (data && data.brands) {
      data.brands.forEach(function (b) {
        var o = document.createElement('option');
        o.value = b;
        o.textContent = b;
        makeSel.appendChild(o);
      });
    }
    if (savedMake) makeSel.value = savedMake;
    refreshModelOptions(seg, makeSel.value, true);
    if (modelSel) {
      modelSel.disabled = !makeSel.value;
      modelSel.required = isVehicle && !relaxed && !modelSel.closest('[hidden]');
    }
  }

  function applyPrefill() {
    Object.keys(prefill).forEach(function (name) {
      if (name === 'vehicle_model_custom') return;
      var val = prefill[name];
      if (val === '' || val === null || val === undefined) return;
      var el = document.querySelector('[name="' + name + '"]');
      if (el && !el.closest('[hidden]')) {
        el.value = String(val);
      }
    });
    if (customInput && prefill.vehicle_model_custom) {
      customInput.value = String(prefill.vehicle_model_custom);
    }
    syncCustomModelField();
  }

  function fillVisibleOptions(seg) {
    var opts = window.cxVehicleFormOptions && window.cxVehicleFormOptions[seg];
    if (!opts) return;
    document.querySelectorAll('[data-veh-options]').forEach(function (sel) {
      if (sel.closest('[hidden]')) return;
      var key = sel.getAttribute('data-veh-options');
      var group = opts[key];
      if (!group || !group.options) return;
      var current = prefill[sel.name] || sel.value;
      sel.innerHTML = '<option value="">Secin</option>';
      group.options.forEach(function (optVal) {
        var o = document.createElement('option');
        o.value = String(optVal);
        o.textContent = String(optVal);
        sel.appendChild(o);
      });
      if (current) sel.value = String(current);
    });
  }

  function syncRequiredFlags(seg, isVehicle) {
    document.querySelectorAll('[data-vehicle-required]').forEach(function (el) {
      var hideFuel = seg === 'bisiklet' && (el.name === 'vehicle_fuel' || el.name === 'vehicle_transmission');
      el.required = isVehicle && !relaxed && !hideFuel && !el.closest('[hidden]');
    });
    var ccReq = document.querySelector('[data-veh-cc-req]');
    var ccInput = document.querySelector('[data-veh-cc]');
    if (ccReq && ccInput) {
      var motoCc = seg === 'motosiklet';
      ccReq.hidden = !motoCc;
      ccInput.required = isVehicle && !relaxed && motoCc && !ccInput.closest('[hidden]');
    }
    var kmInput = document.querySelector('[data-veh-km]');
    var kmLabel = document.querySelector('[data-veh-km-label]');
    if (kmInput && kmLabel) {
      var bike = seg === 'bisiklet';
      if (relaxed) {
        kmLabel.textContent = 'Kilometre (opsiyonel)';
        kmInput.required = false;
      } else {
        kmLabel.textContent = bike ? 'Kullanim (km, opsiyonel)' : 'Kilometre *';
        kmInput.required = isVehicle && !bike && !kmInput.closest('[hidden]');
      }
    }
    var yearInput = document.querySelector('input[name="vehicle_year"]');
    if (yearInput) {
      yearInput.min = seg === 'antika-arac' ? '1900' : '1980';
      if (relaxed) {
        yearInput.required = false;
      } else {
        yearInput.required = isVehicle && !yearInput.closest('[hidden]');
      }
    }
    if (modelSel) {
      modelSel.required = isVehicle && !relaxed && !modelSel.closest('[hidden]');
    }
  }

  function step1Ready(seg) {
    var makeOk = isFilled(makeSel);
    var modelOk = isFilled(modelSel);
    if (modelSel && modelSel.value === manualOpt) {
      modelOk = isFilled(customInput);
    }
    var yearOk = isFilled(document.querySelector('input[name="vehicle_year"]'));
    var kmEl = document.querySelector('[data-veh-km]');
    var kmOk = seg === 'bisiklet' ? true : isFilled(kmEl);
    var commercialOk = true;
    if (seg === 'ticari') {
      commercialOk = isFilled(document.querySelector('[name="vehicle_commercial_type"]'));
    }
    return makeOk && modelOk && yearOk && kmOk && commercialOk;
  }

  function step2Ready(seg) {
    if (seg === 'bisiklet') {
      return isFilled(document.querySelector('[name="vehicle_bike_type"]'));
    }
    var fuelOk = isFilled(document.querySelector('[name="vehicle_fuel"]'));
    var transOk = isFilled(document.querySelector('[name="vehicle_transmission"]'));
    return fuelOk && transOk;
  }

  function setStepOpen(stepEl, open) {
    if (!stepEl) return;
    stepEl.hidden = !open;
    stepEl.classList.toggle('is-open', open);
  }

  function syncFormSteps() {
    if (!fieldset || !vehicleDetails || vehicleDetails.hidden) {
      document.querySelectorAll('[data-listing-step]').forEach(function (el) {
        el.hidden = true;
      });
      return;
    }
    var seg = segmentSel ? segmentSel.value : '';
    var open2 = relaxed || step1Ready(seg);
    var open3 = relaxed || (open2 && step2Ready(seg));

    var step2 = fieldset.querySelector('[data-veh-step="2"]');
    var step3 = fieldset.querySelector('[data-veh-step="3"]');
    var was2 = step2 && !step2.hidden;
    var was3 = step3 && !step3.hidden;

    setStepOpen(fieldset.querySelector('[data-veh-step="1"]'), true);
    setStepOpen(step2, open2);
    setStepOpen(step3, open3);

    var gate2 = fieldset.querySelector('[data-step-gate="2"]');
    var gate3 = fieldset.querySelector('[data-step-gate="3"]');
    if (gate2) gate2.hidden = open2;
    if (gate3) gate3.hidden = !open2 || open3;

    if (fieldset) {
      fieldset.setAttribute('data-vehicle-steps', open3 ? '3' : open2 ? '2' : '1');
    }

    // İlan formu: şehir/fiyat = step2, foto/ekspertiz = step2+
    document.querySelectorAll('[data-listing-step="offer"]').forEach(function (el) {
      el.hidden = !open2;
    });
    document.querySelectorAll('[data-listing-step="media"]').forEach(function (el) {
      el.hidden = !open2;
    });
    document.querySelectorAll('[data-listing-step="submit"]').forEach(function (el) {
      el.hidden = !open2;
    });

    if ((open2 && !was2) || (open3 && !was3)) {
      fillVisibleOptions(seg);
      syncRequiredFlags(seg, true);
    } else {
      syncRequiredFlags(seg, true);
    }
  }

  function toggleVehicle() {
    var opt = subcatSel && subcatSel.options[subcatSel.selectedIndex];
    var seg = opt ? (opt.getAttribute('data-veh') || '') : (segmentSel ? segmentSel.value : '');
    if (segmentSel) segmentSel.value = seg;
    var isVehicle = seg !== '';
    if (vehicleDetails) vehicleDetails.hidden = !isVehicle;

    document.querySelectorAll('[data-veh-segment]').forEach(function (el) {
      var allowed = (el.getAttribute('data-veh-segment') || '').split(/\s+/);
      var show = isVehicle && (allowed.indexOf('all') >= 0 || allowed.indexOf(seg) >= 0);
      el.hidden = !show;
    });

    var yearLabel = document.querySelector('[data-veh-year-label]');
    if (yearLabel) {
      yearLabel.textContent = relaxed ? 'Model yili (opsiyonel)' : 'Model yili *';
    }
    var transLabel = document.querySelector('[data-veh-trans-label]');
    if (transLabel) {
      transLabel.textContent = seg === 'motosiklet' ? 'Sanziman *' : 'Vites *';
    }

    fillVisibleOptions(seg);
    refreshMakeModelFields(seg, isVehicle);
    applyPrefill();
    syncRequiredFlags(seg, isVehicle);
    prefill = {};
    syncCustomModelField();
    syncFormSteps();
  }

  makeSel && makeSel.addEventListener('change', function () {
    var seg = segmentSel ? segmentSel.value : '';
    prefill = {};
    refreshModelOptions(seg, makeSel.value, false);
    if (modelSel) {
      modelSel.required = seg !== '' && !relaxed && !modelSel.closest('[hidden]');
    }
    syncFormSteps();
  });

  modelSel && modelSel.addEventListener('change', function () {
    syncCustomModelField();
    syncFormSteps();
  });

  subcatSel && subcatSel.addEventListener('change', toggleVehicle);

  if (fieldset) {
    fieldset.addEventListener('change', function (e) {
      if (e.target && e.target.matches('select, input, textarea')) {
        syncFormSteps();
      }
    });
    fieldset.addEventListener('input', function (e) {
      if (e.target && e.target.matches('input, textarea')) {
        syncFormSteps();
      }
    });
  }

  if (subcatSel && subcatSel.value) {
    var initialOpt = subcatSel.options[subcatSel.selectedIndex];
    if (segmentSel && initialOpt) {
      segmentSel.value = initialOpt.getAttribute('data-veh') || '';
    }
  }

  if (fieldset) {
    toggleVehicle();
  }
})();
