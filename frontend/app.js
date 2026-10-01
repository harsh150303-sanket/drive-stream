const state = {
    auth: false,
    folder: null,
    items: [],
    view: 'home',
    history: [],
    favorites: [],
    sort: 'name',
    search: '',
    player: null,
    navPath: [],
    folderCache: new Map(),
    playbackUrls: new Map(),
    lastProgressSave: 0
};

const $ = s => document.querySelector(s);

const esc = s =>
    String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    }[c]));

async function api(url, opt) {
    const r = await fetch(url, opt);

    if (!r.ok) {
        let x = {};
        try {
            x = await r.json();
        } catch {}

        throw Error(x.detail || 'Request failed');
    }

    return r.json();
}

function fmtBytes(n) {
    if (n == null) return '—';

    const u = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;

    while (n >= 1024 && i < 4) {
        n /= 1024;
        i++;
    }

    return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

function fmtDate(x) {
    return x ? new Date(x).toLocaleDateString() : '';
}

function time(s) {
    s = Math.max(0, Math.floor(s || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function toast(m) {
    const d = document.createElement('div');
    d.className = 'toast';
    d.textContent = m;
    document.body.appendChild(d);

    setTimeout(() => d.remove(), 2800);
}


/* =========================
   STARTUP
========================= */

async function boot() {
    try {
        const s = await api('/api/auth/status');

        state.auth = s.authenticated;

        if (state.auth) {
            await loadHistory();
            render();

            const savedFolder = localStorage.getItem('drivestream_last_folder');

            if (savedFolder) {
                await openFolder(savedFolder, false);
            } else {
                await openRoot(false);
            }
        } else {
            render();
        }

        window.addEventListener('popstate', handleBrowserNavigation);

    } catch (e) {
        render(e.message);
    }
}


/* =========================
   MAIN UI
========================= */

function render(err) {
    document.querySelector('#app').innerHTML = `
        <header class="top">
            <div class="brand">Drive<span>Stream</span></div>

            <nav>
                ${[
                    ['home', 'HOME'],
                    ['all', 'ALL VIDEOS'],
                    ['recent', 'RECENT'],
                    ['favorites', 'FAVORITES']
                ].map(x => `
                    <button
                        class="${state.view === x[0] ? 'active' : ''}"
                        onclick="nav('${x[0]}')"
                    >
                        ${x[1]}
                    </button>
                `).join('')}
            </nav>

            ${state.auth ? `
                <input
                    class="search"
                    placeholder="Search Drive videos…"
                    value="${esc(state.search)}"
                    oninput="searchDebounced(this.value)"
                >

                <button class="ghost" onclick="openRoot(true)">
                    My Drive
                </button>
            ` : ''}
        </header>

        <main class="wrap" id="main"></main>
    `;

    if (!state.auth) {
        $('#main').innerHTML = `
            <div class="connect">
                <h1 class="title">Private video library for Google Drive</h1>

                <p class="muted">
                    Stream your Drive videos locally without keeping
                    permanent video copies on your PC.
                </p>

                <button class="primary" onclick="connect()">
                    Connect Google Drive
                </button>

                ${err ? `<p class="muted">${esc(err)}</p>` : ''}
            </div>
        `;
    } else {
        renderView();
    }
}


function stopActivePlayer() {
    const v = $('#video');
    if (!v) return;

    try {
        v.pause();
        v.removeAttribute('src');
        v.load();
    } catch {}
}

function renderView() {
    const m = $('#main');

    if (state.player) {
        m.innerHTML = playerHTML(state.player);
        requestAnimationFrame(wirePlayer);
        return;
    }

    if (state.view === 'home') {
        m.innerHTML = `
            <div class="hero">
                <div>
                    <h1 class="title">My Drive</h1>
                    <div class="muted">
                        Browse your Google Drive videos.
                    </div>
                </div>

                <button class="primary" onclick="refreshCurrentFolder()">
                    Refresh
                </button>
            </div>

            ${historySection()}

            <h2>
                ${state.folder ? esc(state.folder.name || 'My Drive') : 'My Drive'}
            </h2>

            ${breadcrumbHTML()}

            ${folderGrid(state.items)}
        `;

        return;
    }

    if (state.view === 'recent') {
        m.innerHTML = `
            <div class="hero">
                <div>
                    <h1 class="title">Recent</h1>
                </div>
            </div>

            ${videoGrid(
                state.history.map(h => ({
                    id: h.id,
                    name: h.filename,
                    size: null,
                    modifiedTime: h.lastWatched,
                    favorite: false
                }))
            )}
        `;

        return;
    }

    if (state.view === 'favorites') {
        m.innerHTML = `
            <div class="hero">
                <div>
                    <h1 class="title">Favorites</h1>
                </div>
            </div>

            ${videoGrid(state.favorites)}
        `;

        return;
    }

    m.innerHTML = `
        <div class="hero">
            <div>
                <h1 class="title">All Videos</h1>

                <div class="muted">
                    Browse videos in the current Drive folder.
                </div>
            </div>
        </div>

        ${breadcrumbHTML()}

        <div class="toolbar">
            <label class="muted">Sort</label>

            <select
                class="sort"
                onchange="state.sort=this.value;renderView()"
            >
                <option value="name" ${state.sort === 'name' ? 'selected' : ''}>
                    Name
                </option>

                <option value="modified" ${state.sort === 'modified' ? 'selected' : ''}>
                    Date modified
                </option>

                <option value="size" ${state.sort === 'size' ? 'selected' : ''}>
                    File size
                </option>
            </select>

            <button
                class="ghost"
                onclick="state.items.reverse();renderView()"
            >
                Reverse
            </button>
        </div>

        ${folderGrid(state.items)}
    `;
}


/* =========================
   BREADCRUMBS / NAVIGATION
========================= */

function breadcrumbHTML() {
    if (!state.folder) return '';

    const parts = [];

    parts.push(`
        <button onclick="openRoot(true)">
            My Drive
        </button>
    `);

    state.navPath.forEach((p, index) => {
        parts.push('<span>›</span>');

        if (index === state.navPath.length - 1) {
            parts.push(`<span>${esc(p.name)}</span>`);
        } else {
            parts.push(`
                <button onclick="navigateToPath(${index})">
                    ${esc(p.name)}
                </button>
            `);
        }
    });

    return `
        <div class="crumbs">
            ${parts.join('')}
        </div>
    `;
}


async function openRoot(pushHistory = true, force = false) {
    try {
        let items = state.folderCache.get('root');
        if (!items || force) {
            const x = await api('/api/drive/root');
            items = x.items;
            state.folderCache.set('root', items);
        }

        state.folder = {
            id: 'root',
            name: 'My Drive'
        };

        state.items = items;
        state.view = 'home';
        stopActivePlayer();
        state.player = null;
        state.navPath = [];

        localStorage.setItem('drivestream_last_folder', 'root');

        if (pushHistory) {
            history.pushState(
                { folder: 'root' },
                '',
                window.location.pathname
            );
        }

        render();
    } catch (e) {
        toast(e.message);
    }
}


async function openFolder(id, pushHistory = true, folderName = null, force = false) {
    try {
        if (id === 'root') {
            await openRoot(pushHistory, force);
            return;
        }
        let items = state.folderCache.get(id);
        if (!items || force) {
            const x = await api('/api/folders/' + encodeURIComponent(id));
            items = x.items;
            state.folderCache.set(id, items);
        }

        let name = folderName || 'Folder';

        const existingIndex = state.navPath.findIndex(p => p.id === id);

        if (existingIndex >= 0) {
            state.navPath = state.navPath.slice(0, existingIndex + 1);
            name = state.navPath[existingIndex].name;
        } else {
            state.navPath.push({
                id,
                name
            });
        }

        state.folder = {
            id,
            name
        };

        state.items = items;
        state.view = 'all';
        stopActivePlayer();
        state.player = null;

        localStorage.setItem('drivestream_last_folder', id);

        if (pushHistory) {
            history.pushState(
                { folder: id },
                '',
                `?folder=${encodeURIComponent(id)}`
            );
        }

        render();
    } catch (e) {
        toast(e.message);
    }
}


async function navigateToPath(index) {
    if (!state.navPath[index]) return;

    const target = state.navPath[index];

    state.navPath = state.navPath.slice(0, index + 1);

    await openFolder(target.id, true, target.name);
}


async function handleBrowserNavigation(e) {
    const params = new URLSearchParams(window.location.search);
    const folderId = params.get('folder');

    if (!folderId || folderId === 'root') {
        state.navPath = [];
        await openRoot(false);
        return;
    }

    await openFolder(folderId, false);
}


/* =========================
   CARDS
========================= */

function folderGrid(items) {
    return items?.length
        ? `
            <div class="grid">
                ${items.slice().sort(sorter).map(card).join('')}
            </div>
        `
        : `
            <div class="empty">
                No supported videos or folders here.
            </div>
        `;
}


function videoGrid(items) {
    return items?.length
        ? `
            <div class="grid">
                ${items.map(card).join('')}
            </div>
        `
        : `
            <div class="empty">
                Nothing here yet.
            </div>
        `;
}


function card(f) {
    return `
        <div
            class="card ${f.isFolder ? 'folder' : ''}"
            onclick="${
                f.isFolder
                    ? `openFolder('${f.id}', true, '${esc(f.name)}')`
                    : `openVideo('${f.id}')`
            }"
            ${!f.isFolder ? `onmouseenter="schedulePreview('${f.id}', this)" onmouseleave="stopPreview('${f.id}', this)"` : ''}
        >
            <div class="thumb">

                ${
                    f.thumbnail && !f.isFolder
                        ? `
                            <img
                                src="/api/videos/${f.id}/thumbnail"
                                loading="lazy"
                                onerror="this.style.display='none'"
                            >
                        `
                        : ''
                }


                ${!f.isFolder ? `<video class="preview" muted playsinline preload="none" aria-hidden="true"></video>` : ''}

                <div class="icon">
                    ${f.isFolder ? '📁' : '🎬'}
                </div>

                ${
                    !f.isFolder
                        ? `
                            <button
                                class="fav"
                                onclick="
                                    event.stopPropagation();
                                    toggleFav('${f.id}', ${!!f.favorite})
                                "
                            >
                                ${f.favorite ? '★' : '☆'}
                            </button>
                        `
                        : ''
                }

            </div>

            <div class="body">
                <div class="name" title="${esc(f.name)}">
                    ${esc(f.name)}
                </div>

                <div class="meta">
                    <span>
                        ${f.isFolder ? 'Folder' : fmtBytes(f.size)}
                    </span>

                    <span>
                        ${fmtDate(f.modifiedTime)}
                    </span>
                </div>
            </div>
        </div>
    `;
}


function sorter(a, b) {
    let k = state.sort;

    let av =
        k === 'name'
            ? a.name.toLowerCase()
            : k === 'size'
                ? (a.size || 0)
                : new Date(a.modifiedTime || 0).getTime();

    let bv =
        k === 'name'
            ? b.name.toLowerCase()
            : k === 'size'
                ? (b.size || 0)
                : new Date(b.modifiedTime || 0).getTime();

    return av > bv ? 1 : av < bv ? -1 : 0;
}


/* =========================
   GOOGLE AUTH
========================= */

async function connect() {
    try {
        const x = await api('/api/auth/login');
        location.href = x.url;
    } catch (e) {
        toast(e.message);
    }
}


/* =========================
   VIDEO PLAYER
========================= */

async function openVideo(id) {
    try {
        stopActivePlayer();
        let f = state.items.find(x => x.id === id);
        if (!f) f = await api('/api/videos/' + encodeURIComponent(id));

        let playbackUrl = state.playbackUrls.get(id);
        if (!playbackUrl) {
            const x = await api('/api/videos/' + encodeURIComponent(id) + '/playback');
            playbackUrl = x.url;
            state.playbackUrls.set(id, playbackUrl);
        }

        state.player = { ...f, playbackUrl };
        renderView();
    } catch (e) {
        toast(e.message);
    }
}


function getCurrentVideoList() {
    return state.items
        .filter(x => !x.isFolder)
        .slice()
        .sort(sorter);
}


function getVideoIndex() {
    if (!state.player) return -1;

    return getCurrentVideoList().findIndex(
        x => x.id === state.player.id
    );
}


function previousVideo() {
    stopActivePlayer();
    const videos = getCurrentVideoList();
    const index = getVideoIndex();

    if (index <= 0) {
        toast('This is the first video.');
        return;
    }

    openVideo(videos[index - 1].id);
}


function nextVideo() {
    stopActivePlayer();
    const videos = getCurrentVideoList();
    const index = getVideoIndex();

    if (index < 0 || index >= videos.length - 1) {
        toast('This is the last video.');
        return;
    }

    openVideo(videos[index + 1].id);
}


function playerHTML(f) {
    const h = state.history.find(x => x.id === f.id);

    const videos = getCurrentVideoList();
    const index = videos.findIndex(x => x.id === f.id);

    const hasPrevious = index > 0;
    const hasNext = index >= 0 && index < videos.length - 1;

    return `
        <div class="player">

            <div class="crumbs">
                <button onclick="closePlayer()">
                    ← Back to library
                </button>
            </div>

            <video
                id="video"
                class="video"
                controls
                playsinline
                preload="metadata"
                src="${f.playbackUrl || ''}"
            ></video>

            <div class="playerhead">

                <div>
                    <h1>${esc(f.name)}</h1>

                    <div class="muted">
                        ${fmtBytes(f.size)}
                        ·
                        ${esc(f.mimeType || 'video')}
                    </div>
                </div>

                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                    <a
                        class="ghost"
                        href="${esc(f.playbackUrl || '')}"
                        target="_blank"
                        rel="noopener"
                    >
                        ↗ Open in new tab
                    </a>

                    <button
                        class="primary"
                        onclick="toggleFav('${f.id}', ${!!f.favorite})"
                    >
                        ${f.favorite ? '★ Favorited' : '☆ Favorite'}
                    </button>
                </div>

            </div>

            <div
                style="
                    display:flex;
                    gap:10px;
                    align-items:center;
                    margin-top:16px;
                    flex-wrap:wrap;
                "
            >

                <button
                    class="ghost"
                    onclick="previousVideo()"
                    ${hasPrevious ? '' : 'disabled'}
                >
                    ⏮ Previous
                </button>

                <button
                    class="primary"
                    onclick="nextVideo()"
                    ${hasNext ? '' : 'disabled'}
                >
                    Next ⏭
                </button>

            </div>

            ${
                h && h.position > 3
                    ? `
                        <div class="muted" style="margin-top:12px">
                            Saved position:
                            ${time(h.position)}
                            ${h.duration ? ' / ' + time(h.duration) : ''}.
                            Press play to resume.
                        </div>
                    `
                    : ''
            }

        </div>
    `;
}


function closePlayer() {
    stopActivePlayer();
    state.player = null;
    renderView();
}


/* =========================
   HISTORY / FAVORITES
========================= */

function historySection() {
    const arr = state.history
        .filter(
            x =>
                x.position > 3 &&
                (!x.duration || x.position < x.duration - 3)
        )
        .slice(0, 5);

    if (!arr.length) return '';

    return `
        <h2>Continue Watching</h2>

        <div class="grid">
            ${arr.map(h => `
                <div
                    class="card"
                    onclick="openVideo('${h.id}')"
                >
                    <div class="thumb">
                        <div class="icon">▶</div>
                    </div>

                    <div class="body">
                        <div class="name">
                            ${esc(h.filename)}
                        </div>

                        <div class="meta">
                            <span>
                                ${time(h.position)} /
                                ${time(h.duration)}
                            </span>

                            <span>
                                ${Math.round(
                                    h.position /
                                    (h.duration || 1) *
                                    100
                                )}%
                            </span>
                        </div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}


async function loadHistory() {
    try {
        state.history = (await api('/api/history')).items;
    } catch {
        state.history = [];
    }

    try {
        state.favorites = (await api('/api/favorites')).items;
    } catch {
        state.favorites = [];
    }
}


async function toggleFav(id, currently) {
    try {
        await api(
            '/api/favorites/' + id,
            {
                method: currently ? 'DELETE' : 'POST'
            }
        );

        await loadHistory();

        if (state.folder && state.folder.id !== 'root') {
            const x = await api(
                '/api/folders/' + encodeURIComponent(state.folder.id)
            );

            state.items = x.items;
        } else {
            const x = await api('/api/drive/root');
            state.items = x.items;
        }

        if (state.player && state.player.id === id) {
            state.player.favorite = !currently;
        }

        renderView();

    } catch (e) {
        toast(e.message);
    }
}


/* =========================
   SEARCH
========================= */

let st;

function searchDebounced(v) {
    clearTimeout(st);

    state.search = v;

    st = setTimeout(search, 350);
}


async function search() {
    if (!state.search.trim()) {
        if (state.folder) {
            if (state.folder.id === 'root') {
                openRoot(false);
            } else {
                openFolder(state.folder.id, false, state.folder.name);
            }
        }

        return;
    }

    try {
        const x = await api(
            '/api/search?q=' +
            encodeURIComponent(state.search)
        );

        state.items = x.items;
        state.view = 'all';
        stopActivePlayer();
        state.player = null;

        renderView();

    } catch (e) {
        toast(e.message);
    }
}


/* =========================
   PLAYER KEYBOARD CONTROLS
========================= */

function setupKeyboard() {
    document.onkeydown = e => {
        const v = $('#video');

        if (
            !v ||
            (
                state.player &&
                document.activeElement?.tagName === 'INPUT'
            )
        ) {
            return;
        }

        if (e.code === 'Space') {
            e.preventDefault();
            v.paused ? v.play() : v.pause();

        } else if (e.key === 'ArrowLeft') {
            v.currentTime = Math.max(
                0,
                v.currentTime - 5
            );

        } else if (e.key === 'ArrowRight') {
            v.currentTime = Math.min(
                v.duration || Infinity,
                v.currentTime + 5
            );

        } else if (e.key.toLowerCase() === 'm') {
            v.muted = !v.muted;

        } else if (e.key.toLowerCase() === 'f') {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                v.requestFullscreen?.();
            }

        } else if (e.key === 'ArrowUp') {
            v.volume = Math.min(
                1,
                v.volume + 0.1
            );

        } else if (e.key === 'ArrowDown') {
            v.volume = Math.max(
                0,
                v.volume - 0.1
            );

        } else if (e.key === 'n') {
            nextVideo();

        } else if (e.key === 'p') {
            previousVideo();
        }
    };
}


/* =========================
   VIDEO PROGRESS
========================= */

async function saveProgress(force = false) {
    const v = $('#video');

    if (!v || !state.player) return;

    if (!force && v.currentTime < 1) return;

    try {
        state.lastProgressSave = Math.floor(v.currentTime);
        await api(
            '/api/history',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    id: state.player.id,
                    filename: state.player.name,
                    position: v.currentTime,
                    duration: v.duration || 0
                })
            }
        );

        await loadHistory();

    } catch {}
}


function wirePlayer() {
    const v = $('#video');

    if (!v || v.dataset.wired === '1') return;
    v.dataset.wired = '1';
    setupKeyboard();

    const h = state.history.find(
        x => x.id === state.player.id
    );

    if (
        h?.position > 3 &&
        h.position < (h.duration || Infinity) - 3
    ) {
        setTimeout(() => {
            v.currentTime = h.position;
        }, 400);
    }

    v.addEventListener(
        'timeupdate',
        () => {
            const second = Math.floor(v.currentTime);
            if (second > 0 && second % 10 === 0 && second !== state.lastProgressSave) saveProgress();
        }
    );

    v.addEventListener(
        'pause',
        () => saveProgress(true)
    );

    v.addEventListener(
        'ended',
        async () => {
            await saveProgress(true);

            const videos = getCurrentVideoList();
            const index = getVideoIndex();

            if (
                index >= 0 &&
                index < videos.length - 1
            ) {
                nextVideo();
            }
        }
    );

    v.addEventListener(
        'error',
        () => toast(
            'This video may use a codec your browser cannot play.'
        )
    );
}


/* =========================
   REFRESH
========================= */

async function refreshCurrentFolder() {
    try {
        if (!state.folder || state.folder.id === 'root') {
            await openRoot(false);
        } else {
            await openFolder(
                state.folder.id,
                false,
                state.folder.name
            );
        }

        toast('Library refreshed.');

    } catch (e) {
        toast(e.message);
    }
}


/* =========================
   TOP NAVIGATION
========================= */

function nav(v) {
    stopActivePlayer();
    state.view = v;
    state.player = null;

    if (v === 'home' || v === 'all') {
        if (state.folder) {
            if (state.folder.id === 'root') {
                openRoot(false);
            } else {
                openFolder(
                    state.folder.id,
                    false,
                    state.folder.name
                );
            }
        } else {
            openRoot(false);
        }

    } else {
        loadHistory().then(render);
    }
}





/* =========================
   30-SECOND PREVIEWS
========================= */

const previewTimers = new Map();

function schedulePreview(id, cardEl) {
    if (previewTimers.has(id)) return;
    previewTimers.set(id, setTimeout(() => startPreview(id, cardEl), 500));
}

async function startPreview(id, cardEl) {
    previewTimers.delete(id);
    const video = cardEl.querySelector('.preview');
    if (!video) return;

    try {
        let url = state.playbackUrls.get(id);
        if (!url) {
            const x = await api('/api/videos/' + encodeURIComponent(id) + '/playback');
            url = x.url;
            state.playbackUrls.set(id, url);
        }

        if (!document.body.contains(cardEl)) return;

        video.src = url;
        video.currentTime = 0;
        video.muted = true;

        const stop = () => {
            if (video.currentTime >= 30) stopPreview(id, cardEl);
        };
        video.ontimeupdate = stop;
        video.play().catch(() => {});
    } catch {}
}

function stopPreview(id, cardEl) {
    const timer = previewTimers.get(id);
    if (timer) {
        clearTimeout(timer);
        previewTimers.delete(id);
    }

    const video = cardEl?.querySelector('.preview');
    if (video) {
        video.pause();
        video.ontimeupdate = null;
        video.removeAttribute('src');
        video.load();
    }
}

/* =========================
   START
========================= */

boot();