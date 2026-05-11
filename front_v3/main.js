/* main.js - Classic 클래식 공연 플랫폼 */

// ══════════════════════════════════════════
// 0. 검색 오버레이 (모든 페이지 공통)
//    - 돋보기 아이콘 클릭 → 오버레이 열림
//    - 키워드 입력 후 엔터/검색 버튼 → 공연찾기_장르별.html?q=키워드 이동
//    - ESC 또는 배경 클릭 → 닫힘
// ══════════════════════════════════════════
(function initSearch() {
    // 오버레이 HTML 삽입
    const overlay = document.createElement('div');
    overlay.id = 'search-overlay';
    overlay.innerHTML = `
        <div id="search-overlay-backdrop"></div>
        <div id="search-box">
            <p id="search-label">공연명 · 작곡가 · 아티스트 검색</p>
            <div id="search-input-wrap">
                <span class="material-symbols-outlined" id="search-icon-inner">search</span>
                <input id="search-input" type="text" placeholder="검색어를 입력하세요" autocomplete="off" />
                <button id="search-clear" aria-label="지우기">×</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    // 스타일 삽입
    const style = document.createElement('style');
    style.textContent = `
        #search-overlay {
            position: fixed; inset: 0; z-index: 9999;
            display: none; align-items: flex-start; justify-content: center;
            padding-top: 120px;
        }
        #search-overlay.open { display: flex; }
        #search-overlay-backdrop {
            position: absolute; inset: 0;
            background: rgba(0,0,0,0.72);
            backdrop-filter: blur(6px);
        }
        #search-box {
            position: relative; z-index: 1;
            width: 100%; max-width: 620px;
            margin: 0 1.5rem;
            animation: searchFadeIn .2s ease;
        }
        @keyframes searchFadeIn {
            from { opacity:0; transform:translateY(-12px); }
            to   { opacity:1; transform:translateY(0); }
        }
        #search-label {
            font-size: 10px; letter-spacing: .28em; text-transform: uppercase;
            color: rgba(233,195,73,.55); margin: 0 0 .9rem .2rem;
        }
        #search-input-wrap {
            display: flex; align-items: center;
            background: #1c1b1b;
            border: 1px solid rgba(233,195,73,.4);
            border-radius: 10px;
            padding: .85rem 1rem;
            gap: .75rem;
        }
        #search-icon-inner {
            color: rgba(233,195,73,.6); font-size: 20px; flex-shrink: 0;
        }
        #search-input {
            flex: 1; background: none; border: none; outline: none;
            color: #e5e2e1; font-family: 'Inter', sans-serif;
            font-size: 17px; letter-spacing: .01em;
        }
        #search-input::placeholder { color: rgba(255,255,255,.2); }
        #search-clear {
            background: none; border: none; color: rgba(255,255,255,.25);
            font-size: 22px; cursor: pointer; padding: 0 .2rem;
            line-height: 1; transition: color .15s;
        }
        #search-clear:hover { color: rgba(233,195,73,.7); }
    `;
    document.head.appendChild(style);

    const searchInput = document.getElementById('search-input');
    const searchClear = document.getElementById('search-clear');

    function openSearch() {
        overlay.classList.add('open');
        setTimeout(() => searchInput.focus(), 80);
    }
    function closeSearch() {
        overlay.classList.remove('open');
        searchInput.value = '';
    }
    function doSearch(query) {
        const q = (query || searchInput.value).trim();
        if (!q) return;
        // 백엔드 연동 후: /api/concerts?q=... 로 변경
        // 현재: 장르별 페이지로 이동하며 쿼리 파라미터 전달
        window.location.href = `공연찾기_장르별.html?q=${encodeURIComponent(q)}`;
    }

    // 돋보기 아이콘 클릭 (모든 페이지의 search 아이콘)
    document.querySelectorAll('.material-symbols-outlined').forEach(el => {
        if (el.textContent.trim() === 'search') {
            el.addEventListener('click', openSearch);
        }
    });

    // 입력창 엔터
    searchInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') doSearch();
        if (e.key === 'Escape') closeSearch();
    });

    // X 버튼
    searchClear.addEventListener('click', () => { searchInput.value = ''; searchInput.focus(); });

    // 배경 클릭 → 닫기
    document.getElementById('search-overlay-backdrop').addEventListener('click', closeSearch);
})();

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