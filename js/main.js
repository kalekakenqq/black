/* ==========================================================================
   Black & Red — site interactions
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {

  /* ---------- Footer year ---------- */
  const yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  /* ---------- Sticky header ---------- */
  const header = document.getElementById('header');
  const onScroll = () => {
    header.classList.toggle('is-scrolled', window.scrollY > 40);
  };
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  /* ---------- Mobile nav ---------- */
  const navToggle = document.getElementById('navToggle');
  const nav = document.getElementById('nav');

  const closeNav = () => {
    nav.classList.remove('is-open');
    navToggle.classList.remove('is-active');
    navToggle.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  };

  navToggle.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('is-open');
    navToggle.classList.toggle('is-active', isOpen);
    navToggle.setAttribute('aria-expanded', String(isOpen));
    document.body.style.overflow = isOpen ? 'hidden' : '';
  });

  nav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', closeNav);
  });

  /* ---------- Reveal on scroll ---------- */
  const revealEls = document.querySelectorAll('[data-reveal]');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

    revealEls.forEach(el => observer.observe(el));
  } else {
    revealEls.forEach(el => el.classList.add('is-visible'));
  }

  /* ---------- Menu tabs ---------- */
  const tabs = document.querySelectorAll('.menu__tab');
  const panels = document.querySelectorAll('.menu__panel');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;

      tabs.forEach(t => {
        t.classList.toggle('is-active', t === tab);
        t.setAttribute('aria-selected', String(t === tab));
      });

      panels.forEach(panel => {
        const isTarget = panel.dataset.panel === target;
        panel.classList.toggle('is-active', isTarget);
        if (isTarget) {
          panel.removeAttribute('hidden');
        } else {
          panel.setAttribute('hidden', '');
        }
      });
    });
  });

  /* ---------- Booking tabs ---------- */
  const btabs = document.querySelectorAll('.booking__tab');
  const bpanels = document.querySelectorAll('.booking__panel');

  btabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.btab;

      btabs.forEach(t => {
        t.classList.toggle('is-active', t === tab);
        t.setAttribute('aria-selected', String(t === tab));
      });

      bpanels.forEach(panel => {
        if (panel.dataset.bpanel === target) {
          panel.removeAttribute('hidden');
        } else {
          panel.setAttribute('hidden', '');
        }
      });
    });
  });

  /* ---------- Gallery lightbox ---------- */
  const galleryItems = Array.from(document.querySelectorAll('.gallery__item'));
  const lightbox = document.getElementById('lightbox');
  const lightboxImg = document.getElementById('lightboxImg');
  const lightboxCaption = document.getElementById('lightboxCaption');
  const lightboxClose = document.getElementById('lightboxClose');
  const lightboxPrev = document.getElementById('lightboxPrev');
  const lightboxNext = document.getElementById('lightboxNext');
  let currentIndex = 0;

  const openLightbox = (index) => {
    currentIndex = (index + galleryItems.length) % galleryItems.length;
    const item = galleryItems[currentIndex];
    lightboxImg.src = item.dataset.img;
    lightboxImg.alt = item.dataset.caption || '';
    lightboxCaption.textContent = item.dataset.caption || '';
    lightbox.classList.add('is-active');
    lightbox.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  };

  const closeLightbox = () => {
    lightbox.classList.remove('is-active');
    lightbox.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  };

  galleryItems.forEach((item, index) => {
    item.addEventListener('click', () => openLightbox(index));
  });

  lightboxClose.addEventListener('click', closeLightbox);
  lightboxPrev.addEventListener('click', () => openLightbox(currentIndex - 1));
  lightboxNext.addEventListener('click', () => openLightbox(currentIndex + 1));

  lightbox.addEventListener('click', (e) => {
    if (e.target === lightbox) closeLightbox();
  });

  document.addEventListener('keydown', (e) => {
    if (!lightbox.classList.contains('is-active')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') openLightbox(currentIndex - 1);
    if (e.key === 'ArrowRight') openLightbox(currentIndex + 1);
  });

  /* ---------- FAQ accordion ---------- */
  document.querySelectorAll('.faq__item').forEach((item) => {
    const question = item.querySelector('.faq__question');
    const answer = item.querySelector('.faq__answer');
    question.addEventListener('click', () => {
      const isOpen = item.classList.contains('is-open');
      if (isOpen) {
        item.classList.remove('is-open');
        question.setAttribute('aria-expanded', 'false');
        answer.style.maxHeight = '0px';
      } else {
        item.classList.add('is-open');
        question.setAttribute('aria-expanded', 'true');
        answer.style.maxHeight = answer.scrollHeight + 'px';
      }
    });
  });

  /* ---------- Hide FAB over footer ---------- */
  const fab = document.querySelector('.fab');
  const footer = document.querySelector('.footer');
  if (fab && footer && 'IntersectionObserver' in window) {
    const fabObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        fab.classList.toggle('is-hidden', entry.isIntersecting);
      });
    });
    fabObserver.observe(footer);
  }

  /* ---------- Booking form -> WhatsApp ---------- */
  const bookingForm = document.getElementById('bookingForm');
  const formHint = document.getElementById('formHint');
  const WHATSAPP_NUMBER = '79261777111';

  const maskDate = (value) => {
    const digits = value.replace(/\D/g, '').slice(0, 8);
    return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)]
      .filter(Boolean).join('.');
  };

  if (bookingForm) {
    const dateInput = bookingForm.querySelector('[name="date"]');

    if (dateInput) {
      dateInput.addEventListener('input', () => {
        dateInput.value = maskDate(dateInput.value);
      });
    }

    bookingForm.addEventListener('submit', (e) => {
      e.preventDefault();

      const data = new FormData(bookingForm);
      const name = (data.get('name') || '').toString().trim();
      const phone = (data.get('phone') || '').toString().trim();
      const date = (data.get('date') || '').toString().trim();
      const time = (data.get('time') || '').toString().trim();
      const guests = (data.get('guests') || '').toString();
      const comment = (data.get('comment') || '').toString().trim();

      if (!/^\d{2}\.\d{2}\.\d{4}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) {
        if (formHint) {
          formHint.textContent = 'Проверьте формат даты (дд.мм.гггг) и времени (чч:мм).';
        }
        return;
      }

      const lines = [
        'Здравствуйте! Хочу забронировать стол в Black & Red.',
        `Имя: ${name}`,
        `Телефон: ${phone}`,
        `Дата: ${date}`,
        `Время: ${time}`,
        `Количество гостей: ${guests}`,
      ];
      if (comment) lines.push(`Комментарий: ${comment}`);

      const message = encodeURIComponent(lines.join('\n'));
      const url = `https://wa.me/${WHATSAPP_NUMBER}?text=${message}`;

      window.open(url, '_blank', 'noopener');

      if (formHint) {
        formHint.textContent = 'Открываем WhatsApp с готовой заявкой — просто нажмите «Отправить».';
      }
    });
  }

  /* ---------- Banquet / hall request -> backend + Telegram ---------- */
  const banquetForm = document.getElementById('banquetForm');
  const banquetHint = document.getElementById('banquetHint');

  if (banquetForm) {
    const dateInput = banquetForm.querySelector('[name="date"]');
    if (dateInput) {
      dateInput.addEventListener('input', () => {
        dateInput.value = maskDate(dateInput.value);
      });
    }

    banquetForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const data = new FormData(banquetForm);
      const payload = {
        name: (data.get('name') || '').toString().trim(),
        phone: (data.get('phone') || '').toString().trim(),
        date: (data.get('date') || '').toString().trim(),
        guests: (data.get('guests') || '').toString().trim(),
        event_type: (data.get('event_type') || '').toString(),
        hall: (data.get('hall') || '').toString(),
        comment: (data.get('comment') || '').toString().trim(),
      };

      if (!payload.name || !payload.phone) {
        if (banquetHint) banquetHint.textContent = 'Заполните имя и телефон.';
        return;
      }
      if (payload.date && !/^\d{2}\.\d{2}\.\d{4}$/.test(payload.date)) {
        if (banquetHint) banquetHint.textContent = 'Проверьте формат даты (дд.мм.гггг).';
        return;
      }

      if (banquetHint) banquetHint.textContent = 'Отправляем заявку…';

      try {
        const res = await fetch('/api/banquet', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('request failed');
        banquetForm.reset();
        if (banquetHint) {
          banquetHint.textContent = 'Заявка отправлена! Мы свяжемся с вами в ближайшее время.';
        }
      } catch (err) {
        if (banquetHint) {
          banquetHint.textContent = 'Не получилось отправить — позвоните нам или напишите в WhatsApp.';
        }
      }
    });
  }
});
