/**
 * Panther Security – interakce veřejného webu.
 * Bez externích knihoven (CSP povoluje skripty jen z našeho webu).
 * Při „omezit pohyb“ se animace vynechají a obsah se zobrazí rovnou.
 */
(function () {
    'use strict';

    var root = document.documentElement;
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    root.classList.remove('no-js');

    function onReady(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    var formatCzk = function (value) { return Math.round(value).toLocaleString('cs-CZ') + ' Kč'; };

    // ---- Nadpis hero: rozdělení na slova, aby mohla nabíhat postupně ----
    function splitWords(el) {
        var index = 0;
        Array.prototype.slice.call(el.childNodes).forEach(function (node) {
            if (node.nodeType === 3) {
                var frag = document.createDocumentFragment();
                node.textContent.split(/(\s+)/).forEach(function (part) {
                    if (!part) return;
                    if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(' ')); return; }
                    frag.appendChild(wrap(document.createTextNode(part), index++));
                });
                el.replaceChild(frag, node);
            } else if (node.nodeType === 1) {
                // Zvýrazněná část (např. <span class="text-gradient">) – celá jako jedno „slovo“
                var clone = node.cloneNode(true);
                el.replaceChild(wrap(clone, index++), node);
            }
        });
        function wrap(content, i) {
            var outer = document.createElement('span');
            outer.className = 'word';
            var inner = document.createElement('span');
            inner.style.setProperty('--i', i);
            inner.appendChild(content);
            outer.appendChild(inner);
            return outer;
        }
    }

    // ---- Najetí prvků při scrollu ----
    function initReveal() {
        var items = document.querySelectorAll('[data-reveal]');
        if (reduceMotion || !('IntersectionObserver' in window)) {
            items.forEach(function (el) { el.classList.add('in'); });
            return;
        }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('in');
                    io.unobserve(entry.target);
                }
            });
        }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
        items.forEach(function (el) { io.observe(el); });
    }

    // ---- Načítání čísel (data-count="50") ----
    function initCounters() {
        var counters = document.querySelectorAll('[data-count]');
        function run(el) {
            var target = parseFloat(el.getAttribute('data-count'));
            if (reduceMotion) { el.textContent = target.toLocaleString('cs-CZ'); return; }
            var start = performance.now();
            var duration = 1800;
            (function frame(now) {
                var t = Math.min(1, (now - start) / duration);
                var eased = 1 - Math.pow(1 - t, 4);
                el.textContent = Math.round(target * eased).toLocaleString('cs-CZ');
                if (t < 1) requestAnimationFrame(frame);
            })(start);
        }
        if (!('IntersectionObserver' in window)) { counters.forEach(run); return; }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) { run(entry.target); io.unobserve(entry.target); }
            });
        }, { threshold: 0.6 });
        counters.forEach(function (el) { io.observe(el); });
    }

    // ---- Navigace: zmenšení při scrollu, ukazatel postupu, mobilní lišta ----
    function initScrollUi() {
        var nav = document.querySelector('.site-nav');
        var bar = document.querySelector('.mobile-bar');
        var steps = document.querySelector('.steps');
        var stepItems = steps ? steps.querySelectorAll('.step') : [];
        var lastY = window.scrollY;
        var ticking = false;

        function update() {
            var y = window.scrollY;
            var max = document.documentElement.scrollHeight - window.innerHeight;
            root.style.setProperty('--progress', max > 0 ? (y / max).toFixed(4) : 0);
            if (nav) nav.classList.toggle('scrolled', y > 20);
            if (bar) bar.classList.toggle('hidden', y > lastY && y > 300);

            // Proces: čára se plní podle toho, jak daleko je sekce odscrollovaná
            if (steps) {
                var rect = steps.getBoundingClientRect();
                var mid = window.innerHeight * 0.55;
                var p = Math.min(1, Math.max(0, (mid - rect.top) / rect.height));
                steps.style.setProperty('--steps-progress', p.toFixed(3));
                stepItems.forEach(function (step) {
                    step.classList.toggle('active', step.getBoundingClientRect().top < mid);
                });
            }
            lastY = y;
            ticking = false;
        }
        window.addEventListener('scroll', function () {
            if (!ticking) { requestAnimationFrame(update); ticking = true; }
        }, { passive: true });
        update();
    }

    // ---- Mobilní menu ----
    function initMenu() {
        var toggle = document.querySelector('.menu-toggle');
        var menu = document.getElementById('mobile-menu');
        var nav = document.querySelector('.site-nav');
        if (!toggle || !menu) return;
        function set(open) {
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            toggle.setAttribute('aria-label', open ? 'Zavřít menu' : 'Otevřít menu');
            menu.classList.toggle('open', open);
            menu.setAttribute('aria-hidden', open ? 'false' : 'true');
            nav.classList.toggle('menu-active', open);
            document.body.classList.toggle('menu-open', open);
        }
        toggle.addEventListener('click', function () { set(toggle.getAttribute('aria-expanded') !== 'true'); });
        menu.addEventListener('click', function (e) { if (e.target.closest('a')) set(false); });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') set(false); });
    }

    // ---- Světlo za kurzorem a 3D naklopení karet ----
    function initPointerEffects() {
        if (!finePointer || reduceMotion) return;
        document.querySelectorAll('.spotlight, .glow-border').forEach(function (el) {
            el.addEventListener('pointermove', function (e) {
                var r = el.getBoundingClientRect();
                el.style.setProperty('--mx', (e.clientX - r.left) + 'px');
                el.style.setProperty('--my', (e.clientY - r.top) + 'px');
            });
        });
        document.querySelectorAll('[data-tilt]').forEach(function (el) {
            el.addEventListener('pointermove', function (e) {
                var r = el.getBoundingClientRect();
                var x = (e.clientX - r.left) / r.width - 0.5;
                var y = (e.clientY - r.top) / r.height - 0.5;
                el.style.transform = 'perspective(900px) rotateX(' + (-y * 7) + 'deg) rotateY(' + (x * 9) + 'deg) translateY(-4px)';
            });
            el.addEventListener('pointerleave', function () { el.style.transform = ''; });
        });
        // „Magnetická“ tlačítka – lehce se přitáhnou ke kurzoru
        document.querySelectorAll('[data-magnetic]').forEach(function (el) {
            el.addEventListener('pointermove', function (e) {
                var r = el.getBoundingClientRect();
                var x = e.clientX - r.left - r.width / 2;
                var y = e.clientY - r.top - r.height / 2;
                el.style.transform = 'translate(' + x * 0.18 + 'px,' + y * 0.28 + 'px)';
            });
            el.addEventListener('pointerleave', function () { el.style.transform = ''; });
        });
        // Paralaxa hero pozadí podle pohybu myši
        var hero = document.querySelector('.hero');
        if (hero) {
            var orbs = hero.querySelectorAll('.orb');
            hero.addEventListener('pointermove', function (e) {
                var x = e.clientX / window.innerWidth - 0.5;
                var y = e.clientY / window.innerHeight - 0.5;
                orbs.forEach(function (orb, i) {
                    var depth = (i + 1) * 18;
                    orb.style.translate = (x * depth) + 'px ' + (y * depth) + 'px';
                });
            });
        }
    }

    // ---- Kalkulačka a poptávkový formulář ----
    function initCalculator() {
        var range = document.getElementById('hours-range');
        if (!range) return;
        var hoursOut = document.getElementById('hours-val');
        var priceEl = document.getElementById('total-price');
        var formHours = document.getElementById('form-hours');
        var formEstimate = document.getElementById('form-estimate');
        var rates = document.querySelectorAll('input[name="guard-rate"]');
        var shown = 0;
        var animation = null;

        function animateTo(value) {
            if (reduceMotion) { priceEl.textContent = formatCzk(value); shown = value; return; }
            cancelAnimationFrame(animation);
            var from = shown;
            var start = performance.now();
            (function frame(now) {
                var t = Math.min(1, (now - start) / 600);
                var eased = 1 - Math.pow(1 - t, 3);
                shown = from + (value - from) * eased;
                priceEl.textContent = formatCzk(shown);
                if (t < 1) animation = requestAnimationFrame(frame);
            })(start);
        }

        function calculate() {
            var hours = parseInt(range.value, 10);
            var checked = document.querySelector('input[name="guard-rate"]:checked');
            var rate = parseInt(checked ? checked.value : 260, 10);
            var estimate = Math.round(hours * 4.33 * rate);
            var fill = (hours - range.min) / (range.max - range.min) * 100;
            range.style.setProperty('--fill', fill + '%');
            hoursOut.textContent = hours === 168 ? '168 h · nonstop 24/7' : hours + ' h týdně';
            formHours.value = hours;
            formEstimate.value = estimate;
            animateTo(estimate);
        }

        range.addEventListener('input', calculate);
        rates.forEach(function (r) { r.addEventListener('change', calculate); });
        calculate();

        var form = document.getElementById('inquiry-form');
        var feedback = document.getElementById('form-feedback');
        var button = document.getElementById('submit-btn');
        if (!form) return;
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var label = button.innerHTML;
            button.disabled = true;
            button.textContent = 'Odesílám…';
            feedback.className = 'feedback';
            fetch(form.action, { method: 'POST', body: new FormData(form) })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    feedback.textContent = data.message;
                    feedback.className = 'feedback ' + (data.status === 'success' ? 'ok' : 'err');
                    if (data.status === 'success') { form.reset(); calculate(); }
                })
                .catch(function () {
                    feedback.textContent = 'Spojení se nezdařilo. Zkuste to prosím znovu, nebo nám zavolejte.';
                    feedback.className = 'feedback err';
                })
                .finally(function () {
                    button.disabled = false;
                    button.innerHTML = label;
                });
        });
    }

    // ---- Magazín: hledání bez načtení stránky ----
    function initArticleSearch() {
        var input = document.getElementById('article-search');
        if (!input) return;
        var items = document.querySelectorAll('.article-item');
        var empty = document.getElementById('no-search-results');
        input.addEventListener('input', function () {
            var q = input.value.trim().toLowerCase();
            var visible = 0;
            items.forEach(function (item) {
                var hit = (item.getAttribute('data-search') || '').indexOf(q) !== -1;
                item.style.display = hit ? '' : 'none';
                if (hit) visible++;
            });
            if (empty) empty.style.display = visible === 0 && items.length ? 'block' : 'none';
        });
    }

    // ---- Kontakt: kopírování údajů ----
    function initCopy() {
        document.querySelectorAll('[data-copy]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                navigator.clipboard.writeText(btn.getAttribute('data-copy')).then(function () {
                    var text = btn.textContent;
                    btn.textContent = '✓ Zkopírováno';
                    btn.classList.add('done');
                    setTimeout(function () { btn.textContent = text; btn.classList.remove('done'); }, 1800);
                });
            });
        });
    }

    onReady(function () {
        var title = document.querySelector('[data-split]');
        if (title && !reduceMotion) splitWords(title);
        initReveal();
        initCounters();
        initScrollUi();
        initMenu();
        initPointerEffects();
        initCalculator();
        initArticleSearch();
        initCopy();
        requestAnimationFrame(function () { root.classList.add('is-loaded'); });
    });
})();
