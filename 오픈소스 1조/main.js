/* main.js - Classic 클래식 공연 플랫폼 */

document.addEventListener('DOMContentLoaded', () => {

    // ══════════════════════════════════════════
    // 1. 헤더 스크롤 배경 강화
    // ══════════════════════════════════════════
    const navBar = document.querySelector('nav');
    const navBarInner = navBar ? navBar.querySelector('div') : null;

    if (navBar && navBarInner) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 10) {
                navBarInner.style.background = 'rgba(13,13,13,0.98)';
                navBarInner.style.borderBottomColor = 'rgba(255,255,255,0.1)';
            } else {
                navBarInner.style.background = '#131313';
                navBarInner.style.borderBottomColor = 'rgba(255,255,255,0.05)';
            }
        });
    }

    // ══════════════════════════════════════════
    // 2. 왼쪽 큰 포스터 슬라이더
    // ══════════════════════════════════════════
    const slides = Array.from(document.querySelectorAll('.featured-slide'));
    const dots   = Array.from(document.querySelectorAll('.fdot'));
    let current  = 0;
    let timer    = null;

    const goTo = (idx) => {
        if (!slides.length) return;
        current = (idx + slides.length) % slides.length;

        slides.forEach((s, i) => s.classList.toggle('is-active', i === current));
        dots.forEach((d, i) => d.classList.toggle('is-active', i === current));
    };

    const startAuto = () => {
        if (timer) clearInterval(timer);
        timer = setInterval(() => goTo(current + 1), 4000);
    };

    dots.forEach((dot, i) => {
        dot.addEventListener('click', () => {
            goTo(i);
            startAuto(); // 클릭 후 타이머 리셋
        });
    });

    if (slides.length) {
        goTo(0);
        startAuto();
    }

});