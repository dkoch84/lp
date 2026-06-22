const $ = (sel) => document.querySelector(sel);

const artistGrid = $('#artist-grid');
const albumGrid = $('#album-grid');
const backBtn = $('#back-btn');
const headerTitle = $('#header-title');
const nowPlaying = $('#now-playing');
const npTrack = $('#np-track');
const npArtistAlbum = $('#np-artist-album');
const npStop = $('#np-stop');
const vinylBtn = $('#vinyl-btn');
const shareBtn = $('#share-btn');
const artistControls = $('#artist-controls');
const searchInput = $('#search');
const sortSelect = $('#sort');
const albumControls = $('#album-controls');
const albumSortBtn = $('#album-sort');
const albumGridSelectBtn = $('#album-grid-select');
const brand = $('#brand');
const brandRelease = $('#brand-release');

let currentArtist = null;
let statusInterval = null;
let allArtists = [];
let currentAlbums = [];
let currentSort = localStorage.getItem('lp.artistSort') || 'alpha';
sortSelect.value = currentSort;
let albumSortDir = localStorage.getItem('lp.albumSort') || 'asc';
let gridMode = false;        // collage cover-selection mode
let gridSelection = [];      // ordered album folders chosen for the collage

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

function coverUrl(artist, folder, size) {
  const q = size ? `?size=${encodeURIComponent(size)}` : '';
  return `/api/albums/${encodeURIComponent(artist)}/${encodeURIComponent(folder)}/cover${q}`;
}

// --- Vinyl style ---

vinylBtn.addEventListener('click', () => {
  window.location.href = '/vinyl.html';
});

// --- Share screenshot ---

const shareModal = $('#share-modal');
const shareModalImg = $('#share-modal-img');
const shareModalDownload = $('#share-modal-download');
const shareModalClose = $('#share-modal-close');
const shareModalBackdrop = $('#share-modal-backdrop');
let shareModalUrl = null;

function closeShareModal() {
  shareModal.classList.add('hidden');
  if (shareModalUrl) {
    URL.revokeObjectURL(shareModalUrl);
    shareModalUrl = null;
  }
  shareModalImg.removeAttribute('src');
}

shareBtn.addEventListener('click', async () => {
  shareBtn.disabled = true;
  try {
    const res = await fetch('/api/share', { method: 'POST' });
    if (!res.ok) throw new Error(`${res.status}`);
    const blob = await res.blob();
    const disp = res.headers.get('Content-Disposition') || '';
    const m = disp.match(/filename="([^"]+)"/);
    const name = m ? m[1] : 'lp-share.png';
    if (shareModalUrl) URL.revokeObjectURL(shareModalUrl);
    shareModalUrl = URL.createObjectURL(blob);
    shareModalImg.src = shareModalUrl;
    shareModalDownload.href = shareModalUrl;
    shareModalDownload.download = name;
    shareModal.classList.remove('hidden');
  } catch (e) {
    alert('Share failed: ' + e.message);
  } finally {
    shareBtn.disabled = false;
  }
});

shareModalClose.addEventListener('click', closeShareModal);
shareModalBackdrop.addEventListener('click', closeShareModal);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !shareModal.classList.contains('hidden')) {
    closeShareModal();
  }
});

// --- Search ---

searchInput.addEventListener('input', renderArtists);

sortSelect.addEventListener('change', () => {
  currentSort = sortSelect.value;
  localStorage.setItem('lp.artistSort', currentSort);
  renderArtists();
});

// --- Artist grid ---

function sortArtists(artists) {
  const byName = (a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  const arr = artists.slice();
  if (currentSort === 'recent') {
    arr.sort((a, b) => {
      const la = a.last_played || 0;
      const lb = b.last_played || 0;
      if (lb !== la) return lb - la;
      return byName(a, b);
    });
  } else if (currentSort === 'favorites') {
    arr.sort((a, b) => {
      if (!!b.favorite !== !!a.favorite) return b.favorite - a.favorite;
      return byName(a, b);
    });
  } else {
    arr.sort(byName);
  }
  return arr;
}

function renderArtists() {
  const q = searchInput.value.toLowerCase();
  const filtered = allArtists.filter(a => a.name.toLowerCase().includes(q));
  const sorted = sortArtists(filtered);

  artistGrid.innerHTML = '';
  for (const a of sorted) {
    const tile = document.createElement('div');
    tile.className = 'artist-tile';
    tile.dataset.name = a.name.toLowerCase();

    let collageHtml;
    if (a.covers.length === 0) {
      collageHtml = `<div class="artist-collage-empty">&#9835;</div>`;
    } else {
      const n = a.covers.length;
      const count = n >= 4 ? 4 : n >= 3 ? 3 : n >= 2 ? 2 : 1;
      const cls = count >= 4 ? 'cols-4' : count === 3 ? 'cols-3' : count >= 2 ? 'cols-2' : 'cols-1';
      const imgs = a.covers.slice(0, count)
        .map(folder => `<img src="${coverUrl(a.name, folder, 'thumb')}" alt="" loading="lazy">`)
        .join('');
      collageHtml = `<div class="artist-collage ${cls}">${imgs}</div>`;
    }

    const favClass = a.favorite ? 'fav-btn is-fav' : 'fav-btn';
    const favSymbol = a.favorite ? '★' : '☆';
    tile.innerHTML = `
      ${collageHtml}
      <button class="${favClass}" aria-label="Favorite" aria-pressed="${a.favorite}">${favSymbol}</button>
      <div class="artist-name">${esc(a.name)}</div>
      <div class="artist-count">${a.album_count} album${a.album_count !== 1 ? 's' : ''}</div>
    `;
    tile.addEventListener('click', () => showAlbums(a.name));
    tile.querySelector('.fav-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFavorite(a);
    });
    artistGrid.appendChild(tile);
  }
}

async function toggleFavorite(artist) {
  const next = !artist.favorite;
  try {
    await api(`/api/artists/${encodeURIComponent(artist.name)}/favorite`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({favorite: next}),
    });
    artist.favorite = next;
    renderArtists();
  } catch (e) {
    console.error('Favorite toggle failed', e);
  }
}

async function showArtists() {
  currentArtist = null;
  gridMode = false;
  albumGrid.classList.add('hidden');
  albumControls.classList.add('hidden');
  artistGrid.classList.remove('hidden');
  artistControls.classList.remove('hidden');
  searchInput.value = '';
  backBtn.classList.add('hidden');
  headerTitle.textContent = '';
  headerTitle.classList.add('hidden');
  brand.classList.remove('hidden');

  allArtists = await api('/api/artists');
  renderArtists();
}

// --- Album grid ---

async function showAlbums(artistName) {
  currentArtist = artistName;
  gridMode = false;
  artistGrid.classList.add('hidden');
  artistControls.classList.add('hidden');
  albumGrid.classList.remove('hidden');
  albumControls.classList.remove('hidden');
  backBtn.classList.remove('hidden');
  headerTitle.textContent = artistName;
  headerTitle.classList.remove('hidden');
  brand.classList.add('hidden');

  currentAlbums = await api(`/api/artists/${encodeURIComponent(artistName)}/albums`);
  renderAlbums();
}

function sortAlbumsByYear(albums) {
  const arr = albums.slice();
  arr.sort((a, b) => {
    const ay = a.year || '', by = b.year || '';
    if (!ay && !by) return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    if (!ay) return 1;   // year-less albums always last
    if (!by) return -1;
    const cmp = ay.localeCompare(by);
    return albumSortDir === 'desc' ? -cmp : cmp;
  });
  return arr;
}

function renderAlbums() {
  albumSortBtn.innerHTML = `Year ${albumSortDir === 'asc' ? '↑' : '↓'}`;
  albumGridSelectBtn.classList.toggle('active', gridMode);
  albumGridSelectBtn.innerHTML = gridMode ? 'Done' : '&#9638;';

  albumGrid.innerHTML = '';
  for (const a of sortAlbumsByYear(currentAlbums)) {
    const tile = document.createElement('div');
    tile.className = 'album-tile';

    tile.innerHTML = `
      ${a.has_cover
        ? `<img class="album-cover" src="${coverUrl(currentArtist, a.folder, 'thumb')}" alt="" loading="lazy">`
        : `<div class="album-cover-placeholder">&#9835;</div>`
      }
      <div class="album-title">${esc(a.name)}</div>
      ${a.year ? `<div class="album-year">${esc(a.year)}</div>` : ''}
    `;

    if (gridMode) {
      tile.classList.add('selecting');
      if (a.has_cover) {
        tile.classList.add('selectable');
        const idx = gridSelection.indexOf(a.folder);
        if (idx >= 0) {
          tile.classList.add('selected');
          const badge = document.createElement('div');
          badge.className = 'grid-badge';
          badge.textContent = String(idx + 1);
          tile.appendChild(badge);
        }
        tile.addEventListener('click', () => toggleGridSelect(a.folder));
      }
      // Albums with no cover art can't appear in the collage — not selectable.
    } else {
      tile.addEventListener('click', () => playAlbum(currentArtist, a.folder));
    }
    albumGrid.appendChild(tile);
  }
}

function toggleGridSelect(folder) {
  const i = gridSelection.indexOf(folder);
  if (i >= 0) gridSelection.splice(i, 1);        // deselect → others renumber
  else if (gridSelection.length < 4) gridSelection.push(folder);
  else return;                                   // cap at 4
  renderAlbums();
}

albumSortBtn.addEventListener('click', () => {
  albumSortDir = albumSortDir === 'asc' ? 'desc' : 'asc';
  localStorage.setItem('lp.albumSort', albumSortDir);
  renderAlbums();
});

albumGridSelectBtn.addEventListener('click', async () => {
  if (!gridMode) {
    // Enter selection mode, pre-seeded with the current collage.
    const art = allArtists.find(a => a.name === currentArtist);
    gridSelection = art && art.covers ? art.covers.slice(0, 4) : [];
    gridMode = true;
    renderAlbums();
  } else {
    // Save the chosen covers (tap order) and exit.
    try {
      const res = await api(`/api/artists/${encodeURIComponent(currentArtist)}/grid`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({folders: gridSelection}),
      });
      const art = allArtists.find(a => a.name === currentArtist);
      if (art) art.covers = res.covers;
    } catch (e) {
      console.error('Grid save failed', e);
    }
    gridMode = false;
    renderAlbums();
  }
});

// --- Play ---

async function playAlbum(artistName, folder) {
  const info = await api(`/api/albums/${encodeURIComponent(artistName)}/${encodeURIComponent(folder)}/tracks`);
  await api('/api/play', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path: info.path}),
  });
}

// --- Stop ---

npStop.addEventListener('click', async () => {
  await api('/api/stop', {method: 'POST'});
});

// --- Back ---

backBtn.addEventListener('click', () => {
  showArtists();
});

// --- Status polling ---

async function pollStatus() {
  try {
    const s = await api('/api/status');
    if (s.playing) {
      nowPlaying.classList.remove('hidden');
      npTrack.textContent = s.track_title || `Track ${s.track_number}`;
      npArtistAlbum.textContent = [s.artist, s.album].filter(Boolean).join(' \u2014 ');
    } else {
      nowPlaying.classList.add('hidden');
    }
  } catch {
    // ignore transient errors
  }
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// --- Release badge ---

async function loadVersion() {
  try {
    const v = await api('/api/version');
    brandRelease.textContent = v.release || '';
    if (v.describe) brand.title = `lp ${v.describe} — release notes`;
  } catch {
    brandRelease.textContent = '';  // leave the lp wordmark, drop the release tag
  }
}

// --- Init ---

showArtists();
loadVersion();
statusInterval = setInterval(pollStatus, 3000);
pollStatus();
