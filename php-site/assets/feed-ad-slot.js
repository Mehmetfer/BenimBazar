(function () {
  'use strict';

  function initSlot(slot) {
    var slides = slot.querySelectorAll('[data-feed-ad-slide]');
    if (slides.length < 2) {
      return;
    }

    var interval = parseInt(slot.getAttribute('data-feed-ad-rotate') || '7000', 10);
    if (!interval || interval < 3000) {
      interval = 7000;
    }

    var dots = slot.querySelectorAll('.market-feed-ad__dot');
    var index = 0;

    function show(next) {
      slides[index].classList.remove('is-active');
      if (dots[index]) {
        dots[index].classList.remove('is-active');
      }
      index = next;
      slides[index].classList.add('is-active');
      if (dots[index]) {
        dots[index].classList.add('is-active');
      }
    }

    setInterval(function () {
      show((index + 1) % slides.length);
    }, interval);
  }

  document.querySelectorAll('[data-feed-ad-slot]').forEach(initSlot);
})();
