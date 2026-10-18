const menuToggle = document.querySelector('.menu-toggle');
const primaryNav = document.querySelector('#primary-nav');
const navLinks = primaryNav ? [...primaryNav.querySelectorAll('a[href^="#"]')] : [];
const dialog = document.querySelector('.contact-dialog');
const closeDialogButton = document.querySelector('.dialog-close');
const interestForm = document.querySelector('#interest-form');
const formStatus = document.querySelector('.form-status');

function closeMenu() {
  if (!menuToggle || !primaryNav) return;
  menuToggle.setAttribute('aria-expanded', 'false');
  menuToggle.setAttribute('aria-label', 'Open navigation');
  primaryNav.classList.remove('is-open');
}

menuToggle?.addEventListener('click', () => {
  const isOpen = menuToggle.getAttribute('aria-expanded') === 'true';
  menuToggle.setAttribute('aria-expanded', String(!isOpen));
  menuToggle.setAttribute('aria-label', isOpen ? 'Open navigation' : 'Close navigation');
  primaryNav?.classList.toggle('is-open', !isOpen);
});

navLinks.forEach((link) => link.addEventListener('click', closeMenu));
window.addEventListener('resize', () => {
  if (window.innerWidth > 800) closeMenu();
});

const openDialog = () => {
  if (!dialog) return;
  closeMenu();
  dialog.showModal();
  closeDialogButton?.focus();
};

document.querySelectorAll('[data-dialog-open]').forEach((button) => {
  button.addEventListener('click', openDialog);
});

closeDialogButton?.addEventListener('click', () => dialog?.close());
dialog?.addEventListener('click', (event) => {
  if (event.target === dialog) dialog.close();
});
dialog?.addEventListener('close', () => {
  formStatus.textContent = '';
});

interestForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  if (!interestForm.reportValidity()) return;
  formStatus.textContent = 'Preview only: no message was sent or stored. Connect a contact service to receive inquiries.';
  interestForm.reset();
});

const year = document.querySelector('#current-year');
if (year) year.textContent = String(new Date().getFullYear());

const revealItems = [...document.querySelectorAll('.reveal')];
if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const observer = new IntersectionObserver((entries, currentObserver) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      currentObserver.unobserve(entry.target);
    });
  }, { threshold: 0.08, rootMargin: '0px 0px -24px 0px' });
  revealItems.forEach((item) => observer.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add('is-visible'));
}

const sections = [...document.querySelectorAll('main section[id]')];
if ('IntersectionObserver' in window && sections.length) {
  const sectionObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => {
        const active = link.hash === `#${entry.target.id}`;
        if (active) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    });
  }, { rootMargin: '-30% 0px -60% 0px' });
  sections.forEach((section) => sectionObserver.observe(section));
}
