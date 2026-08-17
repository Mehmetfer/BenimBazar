<script>
window.cxAdminRejectReason = function (form) {
  var existing = form.querySelector('input[name="reject_reason"], textarea[name="reject_reason"]');
  var prefill = existing ? String(existing.value || '').trim() : '';
  if (prefill !== '') {
    if (prefill.length > 500 && existing) {
      existing.value = prefill.slice(0, 500);
    }
    return true;
  }
  var reason = window.prompt('Ret nedeni (kısa bilgi olarak kullanıcıya bildirim gider):', '');
  if (reason === null) {
    return false;
  }
  reason = String(reason).trim();
  if (reason === '') {
    window.alert('Lütfen kısa bir ret nedeni yazın.');
    return false;
  }
  if (reason.length > 500) {
    reason = reason.slice(0, 500);
  }
  if (existing) {
    existing.value = reason;
  } else {
    var input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'reject_reason';
    input.value = reason;
    form.appendChild(input);
  }
  return true;
};
</script>
