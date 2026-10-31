/* ==========================================================================
   PANTHER SECURITY - SDÍLENÉ EFEKTY VEŘEJNÉHO WEBU
   Scroll reveal, tilt karty, magnetická tlačítka, počítadla, progress bar.
   Při prefers-reduced-motion nebo dotykovém ovládání se těžké efekty vypnou.
   ========================================================================== */

(function () {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

    // SCROLL: PROGRESS BAR, NAVBAR, MOBILNÍ LIŠTA
    const progress = document.querySelector('.scroll-progress');
    const navbar = document.querySelector('.public-navbar');
    const mobileBar = document.querySelector('.mobile-bottom-bar');
    let lastY = window.scrollY;
    let ticking = false;

    function onScroll() {
        const y = window.scrollY;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        if (progress) progress.style.setProperty('--progress', max > 0 ? (y / max).toFixed(4) : 0);
        if (navbar) navbar.classList.toggle('is-scrolled', y > 20);
        // Mobilní lišta se schová při rychlém posunu dolů a vrátí se při posunu nahoru
        if (mobileBar) mobileBar.classList.toggle('is-hidden', y > lastY + 4 && y > 300);
        lastY = y;
        ticking = false;
    }

    window.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(onScroll);
            ticking = true;
        }
    }, { passive: true });
    onScroll();

    // AKTIVNÍ POLOŽKA MENU
    const path = window.location.pathname;
    document.querySelectorAll('.nav-links a[data-match]').forEach(link => {
        if (path.startsWith(link.dataset.match)) link.classList.add('is-active');
    });

    // SCROLL REVEAL SE STAGGEREM PRO SKUPINY
    document.querySelectorAll('[data-stagger]').forEach(group => {
        const step = parseInt(group.dataset.stagger, 10) || 90;
        group.querySelectorAll(':scope > [data-reveal]').forEach((el, i) => {
            el.style.setProperty('--delay', `${i * step}ms`);
        });
    });

    const revealEls = document.querySelectorAll('[data-reveal], .process-step');
    if ('IntersectionObserver' in window && !reduceMotion) {
        const io = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
        revealEls.forEach(el => io.observe(el));
    } else {
        revealEls.forEach(el => el.classList.add('is-visible'));
    }

    // ANIMOVANÁ POČÍTADLA
    function animateCount(el) {
        const target = parseFloat(el.dataset.count);
        const duration = 1600;
        const start = performance.now();
        function frame(now) {
            const t = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - t, 4);
            el.textContent = Math.round(target * eased).toLocaleString('cs-CZ');
            if (t < 1) requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    }

    const counters = document.querySelectorAll('[data-count]');
    if ('IntersectionObserver' in window && !reduceMotion) {
        const counterIo = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    animateCount(entry.target);
                    counterIo.unobserve(entry.target);
                }
            });
        }, { threshold: 0.6 });
        counters.forEach(el => counterIo.observe(el));
    }

    // Vše níže je čistě dekorativní a jen pro myš
    if (reduceMotion || !finePointer) return;

    document.body.classList.add('has-pointer');

    // REFLEKTOR SLEDUJÍCÍ KURZOR
    const glow = document.querySelector('.cursor-glow');
    let gx = window.innerWidth / 2, gy = window.innerHeight / 3;
    let cx = gx, cy = gy;
    window.addEventListener('pointermove', e => { gx = e.clientX; gy = e.clientY; }, { passive: true });
    (function glowLoop() {
        cx += (gx - cx) * 0.12;
        cy += (gy - cy) * 0.12;
        if (glow) glow.style.transform = `translate3d(${cx}px, ${cy}px, 0)`;
        requestAnimationFrame(glowLoop);
    })();

    // SPOTLIGHT + 3D TILT NA KARTÁCH
    document.querySelectorAll('.fx-card').forEach(card => {
        const maxTilt = card.hasAttribute('data-tilt') ? parseFloat(card.dataset.tilt) || 6 : 0;
        card.addEventListener('pointermove', e => {
            const r = card.getBoundingClientRect();
            const px = (e.clientX - r.left) / r.width;
            const py = (e.clientY - r.top) / r.height;
            card.style.setProperty('--mx', `${px * 100}%`);
            card.style.setProperty('--my', `${py * 100}%`);
            if (maxTilt) {
                card.classList.add('is-tilting');
                card.style.setProperty('--rx', `${(0.5 - py) * maxTilt}deg`);
                card.style.setProperty('--ry', `${(px - 0.5) * maxTilt}deg`);
            }
        });
        card.addEventListener('pointerleave', () => {
            card.classList.remove('is-tilting');
            card.style.setProperty('--rx', '0deg');
            card.style.setProperty('--ry', '0deg');
        });
    });

    // MAGNETICKÁ TLAČÍTKA
    document.querySelectorAll('[data-magnetic]').forEach(btn => {
        const strength = 0.25;
        btn.addEventListener('pointermove', e => {
            const r = btn.getBoundingClientRect();
            const dx = e.clientX - (r.left + r.width / 2);
            const dy = e.clientY - (r.top + r.height / 2);
            btn.style.transform = `translate(${dx * strength}px, ${dy * strength}px)`;
        });
        btn.addEventListener('pointerleave', () => { btn.style.transform = ''; });
    });

    // JEMNÝ PARALAX
    const parallaxEls = document.querySelectorAll('[data-parallax]');
    if (parallaxEls.length) {
        let px = 0, py = 0;
        window.addEventListener('pointermove', e => {
            px = e.clientX / window.innerWidth - 0.5;
            py = e.clientY / window.innerHeight - 0.5;
        }, { passive: true });
        (function parallaxLoop() {
            parallaxEls.forEach(el => {
                const depth = parseFloat(el.dataset.parallax) || 10;
                el.style.translate = `${px * depth}px ${py * depth}px`;
            });
            requestAnimationFrame(parallaxLoop);
        })();
    }
})();
