/* main.js - Classic 클래식 공연 플랫폼 */

// ══════════════════════════════════════════
// 0. Backend API adapter (모든 페이지 공통)
//    - file://로 HTML을 직접 열면 상대경로 /api가 동작하지 않으므로 localhost 사용
//    - 서버에서 정적 파일로 제공되면 같은 origin의 /api 사용
// ══════════════════════════════════════════
(function initClassicHubAPI() {
    if (window.ClassicHubAPI) return;

    const API_BASE = window.CLASSICHUB_API_BASE ||
        localStorage.getItem('CLASSICHUB_API_BASE') ||
        (window.location.protocol === 'file:' ? 'http://localhost:8000/api' : '/api');

    const toQuery = (params = {}) => {
        const q = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') q.set(key, value);
        });
        return q.toString();
    };

    const displayDate = (date) => date ? String(date).replaceAll('-', '.') : '';
    const todayISO = () => {
        const d = new Date();
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    };
    const escapeHTML = (value) => String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    const runtimeText = (minutes) => {
        if (!minutes) return '';
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        if (h && m) return `${h}시간 ${m}분`;
        if (h) return `${h}시간`;
        return `${m}분`;
    };

    async function request(path, params, options = {}) {
        const query = params ? toQuery(params) : '';
        const url = `${API_BASE}${path}${query ? `?${query}` : ''}`;
        const res = await fetch(url, {
            headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
            ...options,
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok || body.success === false) {
            throw new Error(body.message || `API 요청 실패: ${res.status}`);
        }
        return body;
    }

    function normalizePerformanceSummary(p, fallbackStatus = '공연예정') {
        const dates = Array.isArray(p.dates) ? p.dates : [];
        const start = p.start_date || p.date || dates[0] || '';
        const end = p.end_date || dates[dates.length - 1] || start;
        return {
            id: p.id,
            title: p.title || '',
            startDate: displayDate(start),
            endDate: displayDate(end || start),
            rawStartDate: start,
            rawEndDate: end || start,
            venue: p.venue || '',
            genre: typeof p.genre === 'string' ? p.genre : (p.genre?.name || ''),
            poster: p.poster_url || p.img || '',
            status: p.status || fallbackStatus,
            runtime: p.runtime || runtimeText(p.runtime_min),
            cast: p.artists ? p.artists.map(a => a.artist || a.name).filter(Boolean).join(', ') : '',
            age: p.age_rating || '',
            ticketPrice: p.ticket_price || (p.min_price ? `${p.min_price.toLocaleString()}원~` : ''),
            reservationUrl: p.reservation_url || '',
            programs: p.programs || [],
            kopisUrl: p.reservation_url || ''
        };
    }

    function normalizePerformanceDetail(p) {
        const normalized = normalizePerformanceSummary(p, p.status || '');
        normalized.detailImage = p.detail_image_url || '';
        normalized.runtime = p.runtime || normalized.runtime;
        normalized.age = p.age_rating || '';
        normalized.ticketPrice = p.ticket_price || normalized.ticketPrice;
        normalized.cast = Array.isArray(p.artists)
            ? p.artists.map(a => {
                const roles = Array.isArray(a.roles) && a.roles.length ? `(${a.roles.join('/')})` : '';
                return `${a.artist}${roles}`;
            }).filter(Boolean).join(', ')
            : normalized.cast;
        return normalized;
    }

    window.ClassicHubAPI = {
        base: API_BASE,
        request,
        getPerformances: (params) => request('/performances', params),
        getUpcomingPerformances: (params = {}) => request('/performances', {
            date_from: todayISO(),
            status: '공연예정',
            sort: 'date_asc',
            ...params,
        }),
        getPerformanceDetail: async (id) => {
            const res = await request(`/performances/${encodeURIComponent(id)}`);
            return normalizePerformanceDetail(res.data || {});
        },
        getRecentPerformances: (limit = 10) => request('/performances/recent', { limit }),
        getGenres: () => request('/genres'),
        getVenues: () => request('/venues'),
        getVenuesByRegion: () => request('/venues/by-region'),
        getComposers: (params) => request('/composers', params),
        getArtists: (params) => request('/artists', params),
        addBookmark: (firebase_uid, performance_id) => request('/bookmarks', null, {
            method: 'POST',
            body: JSON.stringify({ firebase_uid, performance_id }),
        }),
        removeBookmark: (firebase_uid, performance_id) => request('/bookmarks', { firebase_uid, performance_id }, { method: 'DELETE' }),
        getBookmarks: (firebase_uid) => request(`/bookmarks/${encodeURIComponent(firebase_uid)}`),
        normalizePerformanceSummary,
        normalizePerformanceDetail,
        displayDate,
        todayISO,
        escapeHTML,
    };
})();

// ══════════════════════════════════════════
// 0. 검색 오버레이 (모든 페이지 공통)
// ══════════════════════════════════════════
(function initSearch() {
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

    const style = document.createElement('style');
    style.textContent = `
        #search-overlay { position: fixed; inset: 0; z-index: 9999; display: none; align-items: flex-start; justify-content: center; padding-top: 120px; }
        #search-overlay.open { display: flex; }
        #search-overlay-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.72); backdrop-filter: blur(6px); }
        #search-box { position: relative; z-index: 1; width: 100%; max-width: 620px; margin: 0 1.5rem; animation: searchFadeIn .2s ease; }
        @keyframes searchFadeIn { from { opacity:0; transform:translateY(-12px); } to { opacity:1; transform:translateY(0); } }
        #search-label { font-size: 10px; letter-spacing: .28em; text-transform: uppercase; color: rgba(233,195,73,.55); margin: 0 0 .9rem .2rem; }
        #search-input-wrap { display: flex; align-items: center; background: #1c1b1b; border: 1px solid rgba(233,195,73,.4); border-radius: 10px; padding: .85rem 1rem; gap: .75rem; }
        #search-icon-inner { color: rgba(233,195,73,.6); font-size: 20px; flex-shrink: 0; }
        #search-input { flex: 1; background: none; border: none; outline: none; color: #e5e2e1; font-family: 'Inter', sans-serif; font-size: 17px; letter-spacing: .01em; }
        #search-input::placeholder { color: rgba(255,255,255,.2); }
        #search-clear { background: none; border: none; color: rgba(255,255,255,.25); font-size: 22px; cursor: pointer; padding: 0 .2rem; line-height: 1; transition: color .15s; }
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
        window.location.href = `공연찾기_장르별.html?q=${encodeURIComponent(q)}`;
    }

    document.querySelectorAll('.material-symbols-outlined').forEach(el => {
        if (el.textContent.trim() === 'search') el.addEventListener('click', openSearch);
    });
    searchInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') doSearch();
        if (e.key === 'Escape') closeSearch();
    });
    searchClear.addEventListener('click', () => { searchInput.value = ''; searchInput.focus(); });
    document.getElementById('search-overlay-backdrop').addEventListener('click', closeSearch);
})();

document.addEventListener('DOMContentLoaded', () => {
    const API = window.ClassicHubAPI;

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

    // 계정 아이콘은 백엔드 사용자/인증 플로우가 확정되기 전까지 비활성 안내만 제공
    document.querySelectorAll('.material-symbols-outlined').forEach(el => {
        if (el.textContent.trim() === 'account_circle') {
            el.title = '계정 기능은 준비 중입니다';
        }
    });

    // ══════════════════════════════════════════
    // 2. 메인 포스터 슬라이더
    // ══════════════════════════════════════════
    let featuredTimer = null;
    let featuredCurrent = 0;

    function initFeaturedSlider() {
        const slides = Array.from(document.querySelectorAll('.featured-slide'));
        const dots = Array.from(document.querySelectorAll('.fdot'));
        if (featuredTimer) clearInterval(featuredTimer);
        featuredCurrent = 0;

        const goTo = (idx) => {
            if (!slides.length) return;
            featuredCurrent = (idx + slides.length) % slides.length;
            slides.forEach((s, i) => s.classList.toggle('is-active', i === featuredCurrent));
            dots.forEach((d, i) => d.classList.toggle('is-active', i === featuredCurrent));
        };

        dots.forEach((dot, i) => {
            dot.addEventListener('click', () => {
                goTo(i);
                if (featuredTimer) clearInterval(featuredTimer);
                featuredTimer = setInterval(() => goTo(featuredCurrent + 1), 4000);
            });
        });

        if (slides.length) {
            goTo(0);
            featuredTimer = setInterval(() => goTo(featuredCurrent + 1), 4000);
        }
    }

    initFeaturedSlider();

    // ══════════════════════════════════════════
    // 3. 메인 화면 전체 백엔드 연동
    // ══════════════════════════════════════════
    const featureTrack = document.getElementById('featured-track');
    const featuredDots = document.getElementById('featured-dots');
    const mainGrid = document.querySelector('.main-grid');
    const ddayGrid = document.querySelector('.dday-grid');

    const posterHTML = (p, className, label = 'CLASSIC') => {
        const title = API.escapeHTML(p.title);
        if (p.poster) {
            return `<div class="${className}"><img src="${API.escapeHTML(p.poster)}" alt="${title}" loading="lazy" onerror="this.parentElement.classList.add('poster-ph');this.remove();"></div>`;
        }
        return `<div class="${className} poster-ph"><span class="ph-label">${label}</span></div>`;
    };

    const perfSearchUrl = (p) => `공연찾기_장르별.html?q=${encodeURIComponent(p.title || '')}`;

    async function loadMainPerformances() {
        if (!featureTrack && !mainGrid && !ddayGrid) return;
        try {
            const res = await API.getUpcomingPerformances({ page: 1, per_page: 12 });
            const items = (res.data || []).map(p => API.normalizePerformanceSummary(p, '공연예정'));
            if (!items.length) return;

            if (featureTrack) {
                const featureItems = items.slice(0, 3);
                featureTrack.innerHTML = featureItems.map((p, i) => `
                    <a class="featured-slide ${i === 0 ? 'is-active' : ''}" href="${perfSearchUrl(p)}" aria-label="${API.escapeHTML(p.title)} 상세 검색">
                        ${posterHTML(p, 'featured-img', `concert${i + 1}`)}
                        <div class="featured-gradient"></div>
                        <div class="featured-info">
                            <span class="featured-tag">추천</span>
                            <h2 class="featured-title">${API.escapeHTML(p.title)}</h2>
                            <p class="featured-date">${API.escapeHTML(p.startDate)} · ${API.escapeHTML(p.venue || '공연장 미정')}</p>
                        </div>
                    </a>
                `).join('');
                if (featuredDots) {
                    featuredDots.innerHTML = featureItems.map((_, i) => `<button class="fdot ${i === 0 ? 'is-active' : ''}" data-idx="${i}"></button>`).join('');
                }
                initFeaturedSlider();
            }

            if (mainGrid) {
                const gridItems = items.slice(3, 8);
                mainGrid.innerHTML = `
                    <div class="grid-top">
                        ${gridItems.slice(0, 2).map((p, i) => renderMainGridCard(p, i === 0)).join('')}
                    </div>
                    <div class="grid-bottom">
                        ${gridItems.slice(2, 5).map((p) => renderMainGridCard(p, false)).join('')}
                    </div>
                `;
            }

            if (ddayGrid) renderDday(items.slice(0, 4));
        } catch (err) {
            console.error('메인 공연 데이터 조회 실패:', err);
        }
    }

    function renderMainGridCard(p, wide) {
        return `
            <a class="grid-card ${wide ? 'grid-card--wide' : ''}" href="${perfSearchUrl(p)}" aria-label="${API.escapeHTML(p.title)} 검색 결과 보기">
                ${posterHTML(p, 'grid-img', 'CLASSIC')}
                <div class="grid-gradient"></div>
                <div class="grid-info">
                    <p class="grid-title">${API.escapeHTML(p.title)}</p>
                    <p class="grid-date">${API.escapeHTML(p.startDate)} · ${API.escapeHTML(p.venue || '공연장 미정')}</p>
                </div>
            </a>`;
    }

    function renderDday(items) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        ddayGrid.innerHTML = items.map((p) => {
            const start = p.rawStartDate ? new Date(`${p.rawStartDate}T00:00:00`) : null;
            const diff = start ? Math.ceil((start - today) / 86400000) : null;
            const badgeClass = diff !== null && diff <= 3 ? 'red' : diff !== null && diff <= 7 ? 'gold' : 'dim';
            const badge = diff === 0 ? 'D-DAY' : diff !== null ? `D-${Math.max(0, diff)}` : 'SOON';
            return `
                <a class="dday-card" href="${perfSearchUrl(p)}" aria-label="${API.escapeHTML(p.title)} 검색 결과 보기">
                    <div class="dday-poster">
                        ${p.poster ? `<img class="dday-poster-img" src="${API.escapeHTML(p.poster)}" alt="${API.escapeHTML(p.title)}" onerror="this.style.display='none'">` : ''}
                        <div class="dday-poster-overlay"></div>
                        <div class="dday-badge ${badgeClass}">${badge}</div>
                        <div class="dday-poster-info">
                            <div class="dday-pdate">${API.escapeHTML(p.startDate)}</div>
                            <div class="dday-ptitle">${API.escapeHTML(p.title)}</div>
                        </div>
                    </div>
                    <div class="dday-foot">
                        <div class="dday-foot-dot"></div>
                        <span class="dday-foot-venue">${API.escapeHTML(p.venue || '공연장 미정')}</span>
                    </div>
                </a>`;
        }).join('');
    }

    loadMainPerformances();
});
