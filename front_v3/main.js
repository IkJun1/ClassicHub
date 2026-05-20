/* main.js - Classic 클래식 공연 플랫폼 */

// ══════════════════════════════════════════
// 0. Backend API adapter (모든 페이지 공통)
//    - file://로 HTML을 직접 열면 상대경로 /api가 동작하지 않으므로 localhost 사용
//    - 서버에서 정적 파일로 제공되면 같은 origin의 /api 사용
// ══════════════════════════════════════════
(function initClassicHubAPI() {
    if (window.ClassicHubAPI) return;

    const isLocalStaticServer = ['localhost', '127.0.0.1', '0.0.0.0'].includes(window.location.hostname)
        && window.location.port
        && window.location.port !== '8000';
    const API_BASE = window.CLASSICHUB_API_BASE ||
        localStorage.getItem('CLASSICHUB_API_BASE') ||
        (window.location.protocol === 'file:' || isLocalStaticServer ? 'http://localhost:8000/api' : '/api');

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
    const normalizeISODate = (date) => {
        if (!date) return '';
        const match = String(date).match(/\d{4}-\d{2}-\d{2}/);
        return match ? match[0] : '';
    };
    const derivePerformanceStatus = (startDate, endDate, fallbackStatus = '') => {
        const start = normalizeISODate(startDate);
        const end = normalizeISODate(endDate) || start;
        if (!start) return fallbackStatus || '';
        const today = todayISO();
        if (today < start) return '공연예정';
        if (today > end) return '공연완료';
        return '공연중';
    };

    async function request(path, params, options = {}) {
        const query = params ? toQuery(params) : '';
        const url = `${API_BASE}${path}${query ? `?${query}` : ''}`;
        const { auth = false, headers: optionHeaders = {}, ...fetchOptions } = options;
        const headers = { ...optionHeaders };
        if (fetchOptions.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
        if (auth) {
            const token = await window.ClassicHubAuth?.getIdToken?.();
            if (!token) throw new Error('로그인이 필요합니다.');
            headers.Authorization = `Bearer ${token}`;
        }
        const res = await fetch(url, {
            ...fetchOptions,
            headers,
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
        const displayStatus = derivePerformanceStatus(start, end, p.status || fallbackStatus);
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
            status: displayStatus,
            rawStatus: p.status || fallbackStatus,
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
        addBookmark: async (firebase_uidOrPerformanceId, maybePerformanceId) => {
            const performance_id = maybePerformanceId ?? firebase_uidOrPerformanceId;
            const firebase_uid = maybePerformanceId ? firebase_uidOrPerformanceId : (window.ClassicHubAuth?.getCurrentUser?.()?.uid || 'firebase-auth-user');
            return request('/bookmarks', null, {
                method: 'POST',
                auth: true,
                body: JSON.stringify({ firebase_uid, performance_id }),
            });
        },
        removeBookmark: (_firebase_uidOrPerformanceId, maybePerformanceId) => {
            const performance_id = maybePerformanceId ?? _firebase_uidOrPerformanceId;
            return request('/bookmarks', { performance_id }, { method: 'DELETE', auth: true });
        },
        getBookmarks: () => request('/bookmarks', null, { auth: true }),
        normalizePerformanceSummary,
        normalizePerformanceDetail,
        derivePerformanceStatus,
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

// ══════════════════════════════════════════
// 0-B. Firebase Auth (프론트 전용 로그인/회원가입)
// ══════════════════════════════════════════
(function initClassicHubAuth() {
    if (window.ClassicHubAuth) return;

    const FIREBASE_VERSION = '10.12.5';
    const state = {
        auth: null,
        user: null,
        ready: false,
        initPromise: null,
        listeners: [],
        modalMode: 'signin',
    };

    const isConfigured = (config) => Boolean(
        config &&
        config.apiKey &&
        config.authDomain &&
        config.projectId &&
        config.appId
    );

    const loadConfig = async () => {
        if (window.CLASSICHUB_FIREBASE_CONFIG) return window.CLASSICHUB_FIREBASE_CONFIG;
        const stored = localStorage.getItem('CLASSICHUB_FIREBASE_CONFIG');
        if (stored) {
            try { return JSON.parse(stored); }
            catch (e) { console.warn('Firebase 설정 JSON 파싱 실패:', e); }
        }
        try {
            const module = await import('./firebase-config.js');
            return module.firebaseConfig || module.default || {};
        } catch (e) {
            console.warn('firebase-config.js 로드 실패:', e);
            return {};
        }
    };

    async function ensureAuth() {
        if (state.initPromise) return state.initPromise;
        state.initPromise = (async () => {
            const config = await loadConfig();
            if (!isConfigured(config)) {
                throw new Error('Firebase Web Config가 아직 설정되지 않았습니다.');
            }

            const appMod = await import(`https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/firebase-app.js`);
            const authMod = await import(`https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/firebase-auth.js`);
            const app = appMod.getApps().length ? appMod.getApp() : appMod.initializeApp(config);
            state.auth = authMod.getAuth(app);
            state.firebase = authMod;

            authMod.onAuthStateChanged(state.auth, (user) => {
                state.user = user;
                state.ready = true;
                updateAccountIcons();
                state.listeners.forEach(listener => listener(user));
            });

            return state.auth;
        })();
        return state.initPromise;
    }

    const authErrorMessage = (error) => {
        const code = error?.code || '';
        if (code.includes('invalid-email')) return '이메일 형식이 올바르지 않습니다.';
        if (code.includes('missing-password')) return '비밀번호를 입력해 주세요.';
        if (code.includes('weak-password')) return '비밀번호는 6자 이상이어야 합니다.';
        if (code.includes('email-already-in-use')) return '이미 가입된 이메일입니다.';
        if (code.includes('user-not-found') || code.includes('wrong-password') || code.includes('invalid-credential')) {
            return '이메일 또는 비밀번호가 올바르지 않습니다.';
        }
        if (code.includes('network-request-failed')) return '네트워크 연결을 확인해 주세요.';
        return error?.message || '인증 처리 중 문제가 발생했습니다.';
    };

    async function signIn(email, password) {
        const auth = await ensureAuth();
        const { signInWithEmailAndPassword } = state.firebase;
        return signInWithEmailAndPassword(auth, email, password);
    }

    async function signUp(email, password, nickname) {
        const auth = await ensureAuth();
        const { createUserWithEmailAndPassword, updateProfile } = state.firebase;
        const credential = await createUserWithEmailAndPassword(auth, email, password);
        if (nickname) await updateProfile(credential.user, { displayName: nickname });
        return credential;
    }

    async function signOut() {
        const auth = await ensureAuth();
        return state.firebase.signOut(auth);
    }

    async function getIdToken(forceRefresh = false) {
        await ensureAuth();
        if (!state.user) return '';
        return state.user.getIdToken(forceRefresh);
    }

    function getCurrentUser() {
        return state.user;
    }

    function onChange(listener) {
        state.listeners.push(listener);
        if (state.ready) listener(state.user);
        return () => {
            state.listeners = state.listeners.filter(item => item !== listener);
        };
    }

    function accountLabel() {
        if (!state.user) return '로그인';
        return state.user.displayName || state.user.email || '내 계정';
    }

    function updateAccountIcons() {
        document.querySelectorAll('.material-symbols-outlined').forEach(el => {
            if (el.textContent.trim() !== 'account_circle') return;
            el.title = state.user ? `${accountLabel()} · 클릭하여 로그아웃` : '로그인 / 회원가입';
            el.classList.toggle('classic-auth-signed-in', Boolean(state.user));
        });
    }

    function setMode(mode) {
        state.modalMode = mode;
        const modal = document.getElementById('classic-auth-modal');
        if (!modal) return;
        modal.querySelectorAll('[data-auth-mode]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.authMode === mode);
        });
        modal.querySelector('#auth-nickname-row').style.display = mode === 'signup' ? 'block' : 'none';
        modal.querySelector('#auth-submit').textContent = mode === 'signup' ? '회원가입' : '로그인';
        modal.querySelector('#auth-helper').textContent = mode === 'signup'
            ? '이메일과 비밀번호로 새 계정을 만듭니다.'
            : 'Firebase 계정으로 로그인합니다.';
        setAuthMessage('');
    }

    function setAuthMessage(message, type = 'info') {
        const el = document.getElementById('auth-message');
        if (!el) return;
        el.textContent = message || '';
        el.dataset.type = type;
    }

    function closeAuthModal() {
        document.getElementById('classic-auth-modal')?.classList.remove('open');
        document.body.style.overflow = '';
    }

    async function openAuthModal() {
        const modal = ensureAuthModal();
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
        setMode(state.modalMode || 'signin');

        if (state.user) {
            setAuthMessage(`${accountLabel()} 계정으로 로그인되어 있습니다.`, 'success');
        } else {
            setAuthMessage('');
        }

        try {
            await ensureAuth();
            modal.classList.toggle('not-configured', false);
            setTimeout(() => modal.querySelector('#auth-email')?.focus(), 40);
        } catch (e) {
            modal.classList.toggle('not-configured', true);
            setAuthMessage('Firebase Web Config를 먼저 설정해 주세요.', 'error');
        }
    }

    function ensureAuthModal() {
        let modal = document.getElementById('classic-auth-modal');
        if (modal) return modal;

        const style = document.createElement('style');
        style.textContent = `
            .classic-auth-signed-in { color: #e9c349; }
            #classic-auth-modal { position: fixed; inset: 0; z-index: 10000; display: none; align-items: center; justify-content: center; padding: 1.25rem; }
            #classic-auth-modal.open { display: flex; }
            .auth-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,.76); backdrop-filter: blur(5px); }
            .auth-panel { position: relative; z-index: 1; width: min(420px, 100%); background: #151515; border: 1px solid rgba(233,195,73,.22); border-radius: 16px; padding: 28px; box-shadow: 0 24px 80px rgba(0,0,0,.42); }
            .auth-close { position: absolute; top: 14px; right: 14px; width: 30px; height: 30px; border-radius: 999px; border: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.05); color: rgba(255,255,255,.58); cursor: pointer; }
            .auth-title { margin: 0 0 6px; color: #fff; font-family: 'Noto Serif KR', serif; font-size: 24px; }
            .auth-subtitle { margin: 0 0 22px; color: rgba(255,255,255,.42); font-size: 12px; line-height: 1.6; }
            .auth-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 18px; }
            .auth-tabs button { padding: 10px 12px; border-radius: 999px; border: 1px solid rgba(255,255,255,.09); background: rgba(255,255,255,.035); color: rgba(255,255,255,.55); cursor: pointer; font-size: 12px; }
            .auth-tabs button.active { background: #e9c349; color: #131313; border-color: #e9c349; }
            .auth-field { margin-bottom: 12px; }
            .auth-field label { display: block; margin-bottom: 6px; color: rgba(255,255,255,.48); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
            .auth-field input { width: 100%; box-sizing: border-box; border: 1px solid rgba(255,255,255,.1); border-radius: 10px; background: rgba(255,255,255,.045); color: #fff; padding: 12px 13px; outline: none; font-size: 14px; }
            .auth-field input:focus { border-color: rgba(233,195,73,.6); }
            .auth-config-warning { display: none; margin: 0 0 14px; padding: 12px; border-radius: 10px; background: rgba(255,180,80,.08); border: 1px solid rgba(255,180,80,.18); color: rgba(255,225,190,.78); font-size: 12px; line-height: 1.6; }
            #classic-auth-modal.not-configured .auth-config-warning { display: block; }
            #auth-message { min-height: 20px; margin: 4px 0 14px; color: rgba(255,255,255,.48); font-size: 12px; line-height: 1.5; }
            #auth-message[data-type="error"] { color: #ffb4ab; }
            #auth-message[data-type="success"] { color: #9ee4b2; }
            .auth-actions { display: flex; gap: 10px; align-items: center; }
            .auth-primary { flex: 1; padding: 12px 16px; border-radius: 999px; border: 1px solid #e9c349; background: #e9c349; color: #131313; cursor: pointer; font-weight: 700; }
            .auth-secondary { padding: 12px 14px; border-radius: 999px; border: 1px solid rgba(255,255,255,.12); background: transparent; color: rgba(255,255,255,.62); cursor: pointer; }
            .auth-foot { margin-top: 16px; color: rgba(255,255,255,.28); font-size: 11px; line-height: 1.6; }
        `;
        document.head.appendChild(style);

        modal = document.createElement('div');
        modal.id = 'classic-auth-modal';
        modal.innerHTML = `
            <div class="auth-backdrop"></div>
            <div class="auth-panel" role="dialog" aria-modal="true" aria-labelledby="auth-title">
                <button type="button" class="auth-close" aria-label="닫기">×</button>
                <h2 id="auth-title" class="auth-title">계정</h2>
                <p id="auth-helper" class="auth-subtitle">Firebase 계정으로 로그인합니다.</p>
                <div class="auth-tabs">
                    <button type="button" data-auth-mode="signin">로그인</button>
                    <button type="button" data-auth-mode="signup">회원가입</button>
                </div>
                <p class="auth-config-warning">
                    <strong>Firebase 설정 필요</strong><br>
                    <code>front_v3/firebase-config.js</code>에 Web Config 값을 채우면 로그인/회원가입을 사용할 수 있습니다.
                </p>
                <form id="auth-form">
                    <div class="auth-field" id="auth-nickname-row">
                        <label for="auth-nickname">닉네임</label>
                        <input id="auth-nickname" type="text" autocomplete="nickname" placeholder="닉네임">
                    </div>
                    <div class="auth-field">
                        <label for="auth-email">이메일</label>
                        <input id="auth-email" type="email" autocomplete="email" placeholder="name@example.com" required>
                    </div>
                    <div class="auth-field">
                        <label for="auth-password">비밀번호</label>
                        <input id="auth-password" type="password" autocomplete="current-password" placeholder="6자 이상" required>
                    </div>
                    <p id="auth-message"></p>
                    <div class="auth-actions">
                        <button id="auth-submit" class="auth-primary" type="submit">로그인</button>
                        <button id="auth-bookmarks" class="auth-secondary" type="button">내 찜</button>
                        <button id="auth-signout" class="auth-secondary" type="button">로그아웃</button>
                    </div>
                </form>
                <p class="auth-foot">로그인 토큰은 북마크처럼 인증이 필요한 API 요청에만 자동으로 첨부됩니다.</p>
            </div>
        `;
        document.body.appendChild(modal);

        modal.querySelector('.auth-backdrop').addEventListener('click', closeAuthModal);
        modal.querySelector('.auth-close').addEventListener('click', closeAuthModal);
        modal.querySelectorAll('[data-auth-mode]').forEach(btn => {
            btn.addEventListener('click', () => setMode(btn.dataset.authMode));
        });
        modal.querySelector('#auth-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const submit = modal.querySelector('#auth-submit');
            const email = modal.querySelector('#auth-email').value.trim();
            const password = modal.querySelector('#auth-password').value;
            const nickname = modal.querySelector('#auth-nickname').value.trim();
            submit.disabled = true;
            setAuthMessage('처리 중입니다...');
            try {
                if (state.modalMode === 'signup') await signUp(email, password, nickname);
                else await signIn(email, password);
                setAuthMessage('로그인되었습니다.', 'success');
                setTimeout(closeAuthModal, 450);
            } catch (error) {
                setAuthMessage(authErrorMessage(error), 'error');
            } finally {
                submit.disabled = false;
            }
        });
        modal.querySelector('#auth-signout').addEventListener('click', async () => {
            try {
                await signOut();
                setAuthMessage('로그아웃되었습니다.', 'success');
                setTimeout(closeAuthModal, 350);
            } catch (error) {
                setAuthMessage(authErrorMessage(error), 'error');
            }
        });
        modal.querySelector('#auth-bookmarks').addEventListener('click', () => {
            closeAuthModal();
            window.ClassicHubBookmarks?.openList?.();
        });
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && modal.classList.contains('open')) closeAuthModal();
        });
        setMode('signin');
        return modal;
    }

    function wireAccountIcons() {
        document.querySelectorAll('.material-symbols-outlined').forEach(el => {
            if (el.textContent.trim() !== 'account_circle') return;
            el.addEventListener('click', openAuthModal);
        });
        updateAccountIcons();
    }

    window.ClassicHubAuth = {
        ensureAuth,
        signIn,
        signUp,
        signOut,
        getIdToken,
        getCurrentUser,
        onChange,
        openAuthModal,
        refreshAccountIcons: updateAccountIcons,
    };

    document.addEventListener('DOMContentLoaded', () => {
        ensureAuthModal();
        wireAccountIcons();
        ensureAuth().catch(() => updateAccountIcons());
    });
})();

// ══════════════════════════════════════════
// 0-C. Bookmark UI (Firebase 인증 기반)
// ══════════════════════════════════════════
(function initClassicHubBookmarks() {
    if (window.ClassicHubBookmarks) return;

    const state = {
        loaded: false,
        loading: false,
        ids: new Set(),
        items: [],
        currentPerformance: null,
    };

    function ensureStyle() {
        if (document.getElementById('classic-bookmark-style')) return;
        const style = document.createElement('style');
        style.id = 'classic-bookmark-style';
        style.textContent = `
            .modal-bookmark-btn { display:inline-flex;align-items:center;gap:8px;padding:10px 18px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.13);color:rgba(255,255,255,.64);font-size:9px;font-weight:500;letter-spacing:.16em;text-transform:uppercase;border-radius:2px;cursor:pointer;text-decoration:none;transition:background .2s,border-color .2s,color .2s;margin-right:10px; }
            .modal-bookmark-btn:hover { border-color:rgba(233,195,73,.55);color:#e9c349;background:rgba(233,195,73,.07); }
            .modal-bookmark-btn.bookmarked { border-color:rgba(233,195,73,.65);color:#e9c349;background:rgba(233,195,73,.1); }
            .modal-bookmark-btn:disabled { opacity:.5;cursor:wait; }
            .classic-bookmark-list-modal { position:fixed;inset:0;z-index:10001;display:none;align-items:center;justify-content:center;padding:1.25rem; }
            .classic-bookmark-list-modal.open { display:flex; }
            .bookmark-list-backdrop { position:absolute;inset:0;background:rgba(0,0,0,.78);backdrop-filter:blur(5px); }
            .bookmark-list-panel { position:relative;z-index:1;width:min(720px,100%);max-height:min(720px,84vh);overflow:hidden;background:#151515;border:1px solid rgba(233,195,73,.22);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.45);display:flex;flex-direction:column; }
            .bookmark-list-head { display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:24px 26px 18px;border-bottom:1px solid rgba(255,255,255,.06); }
            .bookmark-list-head h2 { margin:0 0 6px;color:#fff;font-family:'Noto Serif KR',serif;font-size:24px; }
            .bookmark-list-head p { margin:0;color:rgba(255,255,255,.38);font-size:12px; }
            .bookmark-list-close { width:32px;height:32px;border-radius:999px;border:1px solid rgba(255,255,255,.11);background:rgba(255,255,255,.05);color:rgba(255,255,255,.62);cursor:pointer; }
            .bookmark-list-body { overflow:auto;padding:10px 26px 24px; }
            .bookmark-list-empty { padding:58px 0;text-align:center;color:rgba(255,255,255,.32);font-size:13px; }
            .bookmark-list-item { display:grid;grid-template-columns:58px 1fr auto;gap:14px;align-items:center;padding:14px 0;border-bottom:1px solid rgba(255,255,255,.055); }
            .bookmark-list-poster { width:58px;aspect-ratio:3/4;border-radius:8px;background:rgba(255,255,255,.05);object-fit:cover; }
            .bookmark-list-title { color:rgba(255,255,255,.86);font-family:'Noto Serif KR',serif;font-size:14px;line-height:1.45;margin-bottom:5px; }
            .bookmark-list-meta { color:rgba(255,255,255,.38);font-size:11px;line-height:1.5; }
            .bookmark-list-remove { padding:8px 10px;border:1px solid rgba(255,255,255,.12);border-radius:999px;background:transparent;color:rgba(255,255,255,.55);font-size:11px;cursor:pointer; }
            .bookmark-list-remove:hover { color:#ffb4ab;border-color:rgba(255,180,171,.4); }
        `;
        document.head.appendChild(style);
    }

    async function requireUser() {
        try {
            await window.ClassicHubAuth?.ensureAuth?.();
        } catch (e) {
            window.ClassicHubAuth?.openAuthModal?.();
            return null;
        }
        const user = window.ClassicHubAuth?.getCurrentUser?.();
        if (!user) window.ClassicHubAuth?.openAuthModal?.();
        return user || null;
    }

    async function loadBookmarks(force = false) {
        const user = await requireUser();
        if (!user) return [];
        if (state.loaded && !force) return state.items;
        if (state.loading) return state.items;
        state.loading = true;
        try {
            const res = await window.ClassicHubAPI.getBookmarks();
            state.items = res.data || [];
            state.ids = new Set(state.items.map(item => Number(item.performance_id)));
            state.loaded = true;
            return state.items;
        } finally {
            state.loading = false;
        }
    }

    const isBookmarked = (performanceId) => state.ids.has(Number(performanceId));

    function setButtonState(button, performanceId, loading = false) {
        if (!button) return;
        const bookmarked = isBookmarked(performanceId);
        button.disabled = loading;
        button.classList.toggle('bookmarked', bookmarked);
        button.textContent = loading ? '처리 중...' : (bookmarked ? '♥ 찜됨' : '♡ 찜하기');
        button.setAttribute('aria-pressed', bookmarked ? 'true' : 'false');
    }

    async function toggle(performance) {
        if (!performance?.id) return;
        const user = await requireUser();
        if (!user) return;
        await loadBookmarks();
        const id = Number(performance.id);
        if (isBookmarked(id)) {
            await window.ClassicHubAPI.removeBookmark(id);
            state.ids.delete(id);
            state.items = state.items.filter(item => Number(item.performance_id) !== id);
        } else {
            await window.ClassicHubAPI.addBookmark(id);
            state.ids.add(id);
            state.items.unshift({
                performance_id: id,
                title: performance.title,
                poster_url: performance.poster,
                start_date: performance.rawStartDate || performance.startDate,
                venue: performance.venue,
                status: performance.status,
            });
        }
    }

    function bindModal(performance) {
        if (!performance?.id) return;
        ensureStyle();
        state.currentPerformance = performance;
        const foot = document.querySelector('#concert-modal .modal-foot');
        if (!foot) return;
        let button = document.getElementById('modal-bookmark-btn');
        if (!button) {
            button = document.createElement('button');
            button.type = 'button';
            button.id = 'modal-bookmark-btn';
            button.className = 'modal-bookmark-btn';
            const ticketButton = document.getElementById('modal-kopis-btn');
            foot.insertBefore(button, ticketButton || null);
        }
        button.onclick = async () => {
            setButtonState(button, performance.id, true);
            try {
                await toggle(performance);
                setButtonState(button, performance.id, false);
                renderList();
            } catch (e) {
                console.error('북마크 처리 실패:', e);
                button.disabled = false;
                button.textContent = '다시 시도';
            }
        };
        setButtonState(button, performance.id, false);
        if (window.ClassicHubAuth?.getCurrentUser?.()) {
            loadBookmarks().then(() => setButtonState(button, performance.id, false)).catch(() => {});
        }
    }

    function ensureListModal() {
        ensureStyle();
        let modal = document.getElementById('classic-bookmark-list-modal');
        if (modal) return modal;
        modal = document.createElement('div');
        modal.id = 'classic-bookmark-list-modal';
        modal.className = 'classic-bookmark-list-modal';
        modal.innerHTML = `
            <div class="bookmark-list-backdrop"></div>
            <section class="bookmark-list-panel" role="dialog" aria-modal="true" aria-labelledby="bookmark-list-title">
                <div class="bookmark-list-head">
                    <div>
                        <h2 id="bookmark-list-title">내 찜 목록</h2>
                        <p id="bookmark-list-count">로그인 후 찜한 공연을 확인할 수 있습니다.</p>
                    </div>
                    <button type="button" class="bookmark-list-close" aria-label="닫기">×</button>
                </div>
                <div class="bookmark-list-body" id="bookmark-list-body"></div>
            </section>
        `;
        document.body.appendChild(modal);
        modal.querySelector('.bookmark-list-backdrop').addEventListener('click', closeList);
        modal.querySelector('.bookmark-list-close').addEventListener('click', closeList);
        return modal;
    }

    function closeList() {
        document.getElementById('classic-bookmark-list-modal')?.classList.remove('open');
        document.body.style.overflow = '';
    }

    function renderList() {
        const modal = document.getElementById('classic-bookmark-list-modal');
        if (!modal) return;
        const body = modal.querySelector('#bookmark-list-body');
        const count = modal.querySelector('#bookmark-list-count');
        count.textContent = `${state.items.length.toLocaleString()}개 공연`;
        if (!state.items.length) {
            body.innerHTML = '<div class="bookmark-list-empty">아직 찜한 공연이 없습니다.</div>';
            return;
        }
        body.innerHTML = state.items.map(item => `
            <article class="bookmark-list-item" data-performance-id="${Number(item.performance_id)}">
                ${item.poster_url ? `<img class="bookmark-list-poster" src="${window.ClassicHubAPI.escapeHTML(item.poster_url)}" alt="">` : '<div class="bookmark-list-poster"></div>'}
                <div>
                    <div class="bookmark-list-title">${window.ClassicHubAPI.escapeHTML(item.title || '')}</div>
                    <div class="bookmark-list-meta">${window.ClassicHubAPI.escapeHTML(item.start_date || '')} · ${window.ClassicHubAPI.escapeHTML(item.venue || '')}</div>
                </div>
                <button type="button" class="bookmark-list-remove">삭제</button>
            </article>
        `).join('');
        body.querySelectorAll('.bookmark-list-remove').forEach(btn => {
            btn.addEventListener('click', async () => {
                const item = btn.closest('[data-performance-id]');
                const id = Number(item.dataset.performanceId);
                btn.disabled = true;
                try {
                    await window.ClassicHubAPI.removeBookmark(id);
                    state.ids.delete(id);
                    state.items = state.items.filter(entry => Number(entry.performance_id) !== id);
                    renderList();
                    if (state.currentPerformance?.id === id) {
                        setButtonState(document.getElementById('modal-bookmark-btn'), id, false);
                    }
                } catch (e) {
                    console.error('북마크 삭제 실패:', e);
                    btn.disabled = false;
                }
            });
        });
    }

    async function openList() {
        const modal = ensureListModal();
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
        modal.querySelector('#bookmark-list-body').innerHTML = '<div class="bookmark-list-empty">찜 목록을 불러오는 중입니다.</div>';
        try {
            await loadBookmarks(true);
            renderList();
        } catch (e) {
            console.error('북마크 목록 조회 실패:', e);
            modal.querySelector('#bookmark-list-count').textContent = '조회 실패';
            modal.querySelector('#bookmark-list-body').innerHTML = '<div class="bookmark-list-empty">찜 목록을 불러오지 못했습니다.</div>';
        }
    }

    window.ClassicHubBookmarks = {
        bindModal,
        openList,
        closeList,
        loadBookmarks,
        isBookmarked,
    };

    window.ClassicHubAuth?.onChange?.(() => {
        state.loaded = false;
        state.ids = new Set();
        state.items = [];
        if (state.currentPerformance) bindModal(state.currentPerformance);
    });
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

    window.ClassicHubAuth?.refreshAccountIcons?.();

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
