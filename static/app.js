const $ = (sel) => document.querySelector(sel);

const artistGrid = $('#artist-grid');
const recentSection = $('#recent-section');
const recentGrid = $('#recent-grid');
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
const trackSheet = $('#track-sheet');
const trackSheetBackdrop = $('#track-sheet-backdrop');
const trackSheetTitle = $('#track-sheet-title');
const trackSheetList = $('#track-sheet-list');
const brand = $('#brand');
const brandRelease = $('#brand-release');

let currentArtist = null;
let statusInterval = null;
let allArtists = [];
let recentAlbums = [];
let currentAlbums = [];
let currentSort = localStorage.getItem('lp.artistSort') || 'alpha';
sortSelect.value = currentSort;
let albumSortDir = localStorage.getItem('lp.albumSort') || 'asc';
let gridMode = false;        // collage cover-selection mode
let gridSelection = [];      // ordered album folders chosen for the collage
let lastStatus = null;       // most recent /api/status, for the track sheet
let artistsLoaded = false;   // the artist grid has been fetched at least once

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

function hideShareModal() {
  shareModal.classList.add('hidden');
  if (shareModalUrl) {
    URL.revokeObjectURL(shareModalUrl);
    shareModalUrl = null;
  }
  shareModalImg.removeAttribute('src');
}

// Dismissing goes back, the same as the track picker, so its history entry is
// consumed and the next back press does not reopen it.
function closeShareModal() {
  if (currentState().share) history.back();
  else hideShareModal();
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
    navigate({...currentState(), share: true});
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

// --- Recently played ---

function renderRecent() {
  // Only meaningful on the top-level artist view with no active search —
  // a filtered/album view shouldn't carry the recent shelf.
  const searching = searchInput.value.trim() !== '';
  if (currentArtist !== null || searching || recentAlbums.length === 0) {
    recentSection.classList.add('hidden');
    recentGrid.innerHTML = '';
    return;
  }

  recentGrid.innerHTML = '';
  for (const a of recentAlbums) {
    const tile = document.createElement('div');
    tile.className = 'album-tile';
    tile.innerHTML = `
      ${a.has_cover
        ? `<img class="album-cover" src="${coverUrl(a.artist, a.folder, 'thumb')}" alt="" loading="lazy">`
        : `<div class="album-cover-placeholder">&#9835;</div>`
      }
      <div class="album-caption">
        <div class="album-title">${esc(a.name)}</div>
        <div class="album-year">${esc(a.artist)}</div>
      </div>
    `;
    tile.addEventListener('click', () => playAlbum(a.artist, a.folder));
    attachCaptionPicker(tile, () => goToTracks(a.artist, a.folder));
    recentGrid.appendChild(tile);
  }
  recentSection.classList.remove('hidden');
}

async function loadRecent() {
  try {
    recentAlbums = await api('/api/recent');
  } catch {
    recentAlbums = [];
  }
  renderRecent();
}

function renderArtists() {
  const q = searchInput.value.toLowerCase();
  const filtered = allArtists.filter(a => a.name.toLowerCase().includes(q));
  const sorted = sortArtists(filtered);
  renderRecent();

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
    tile.addEventListener('click', () => goToArtist(a.name));
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
  artistsLoaded = true;
  renderArtists();
  loadRecent();
}

// --- Album grid ---

async function showAlbums(artistName) {
  currentArtist = artistName;
  gridMode = false;
  artistGrid.classList.add('hidden');
  artistControls.classList.add('hidden');
  albumGrid.classList.remove('hidden');
  albumControls.classList.remove('hidden');
  recentSection.classList.add('hidden');
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
      <div class="album-caption">
        <div class="album-title">${esc(a.name)}</div>
        ${a.year ? `<div class="album-year">${esc(a.year)}</div>` : ''}
      </div>
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
      attachCaptionPicker(tile, () => goToTracks(currentArtist, a.folder));
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

async function playAlbum(artistName, folder, start = 0) {
  const info = await api(`/api/albums/${encodeURIComponent(artistName)}/${encodeURIComponent(folder)}/tracks`);
  await api('/api/play', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path: info.path, start}),
  });
  // Reflect the just-played album in the Recently Played shelf.
  loadRecent();
}

// --- Track sheet ---
// Tapping an album cover plays it from the top, as always. Tapping the caption
// strip underneath opens this instead, to start from a chosen track. No
// affordance, by design: putting the record on is the point, and skipping into
// the middle of one is a build/test escape hatch.
//
// This began as a long press and that was abandoned. On Chrome/Android the
// browser's own long-press wins the race and shows "copy image / save image",
// and it fires pointercancel, so no amount of preventDefault reliably keeps a
// timer-based hold alive. A plain click on a different element cannot be
// intercepted by anything.

function attachCaptionPicker(tile, onPick) {
  const caption = tile.querySelector('.album-caption');
  if (!caption) return;
  caption.addEventListener('click', (e) => {
    // The tile's own click plays the album; this must not also do that.
    e.stopPropagation();
    onPick();
  });
}

function hideTrackSheet() {
  trackSheet.classList.add('hidden');
  trackSheetList.innerHTML = '';
}

// Dismissing is a history move, not a DOM move: the sheet is a history entry,
// so going back is what closes it, and that keeps the back button and the
// backdrop doing the same thing.
function closeTrackSheet() {
  if (routeState().tracks) history.back();
  else hideTrackSheet();
}

function albumNameFor(artistName, folder) {
  const inView = currentAlbums.find(a => a.folder === folder);
  if (inView) return inView.name;
  const inRecent = recentAlbums.find(a => a.artist === artistName && a.folder === folder);
  return inRecent ? inRecent.name : folder;
}

async function renderTrackSheet(artistName, folder, albumName) {
  let info;
  try {
    info = await api(`/api/albums/${encodeURIComponent(artistName)}/${encodeURIComponent(folder)}/tracks`);
  } catch {
    return;
  }
  if (!info.tracks || info.tracks.length === 0) return;

  // Mark the current track when this is the album already spinning, so
  // picking up where it stopped does not mean counting rows.
  const playingHere = lastStatus && lastStatus.playing &&
    lastStatus.artist === artistName && lastStatus.album === albumName;
  const currentIndex = playingHere ? (lastStatus.track_number || 0) - 1 : -1;

  trackSheetTitle.textContent = albumName || folder;
  trackSheetList.innerHTML = '';
  info.tracks.forEach((name, i) => {
    const li = document.createElement('li');
    if (i === currentIndex) li.classList.add('current');
    // Filenames, not tags: when a track misbehaves it is the file you want
    // to see. Only the extension is trimmed.
    const label = name.replace(/\.[^.]+$/, '');
    li.innerHTML = `<span class="track-sheet-no">${i + 1}</span>` +
                   `<span class="track-sheet-name">${esc(label)}</span>`;
    li.addEventListener('click', async () => {
      closeTrackSheet();
      await playAlbum(artistName, folder, i);
    });   // closeTrackSheet() pops the sheet entry, so back does not reopen it
    trackSheetList.appendChild(li);
  });

  trackSheet.classList.remove('hidden');
  if (currentIndex > 0) {
    const li = trackSheetList.children[currentIndex];
    if (li) li.scrollIntoView({block: 'center'});
  }
}

trackSheetBackdrop.addEventListener('click', closeTrackSheet);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !trackSheet.classList.contains('hidden')) closeTrackSheet();
});

// --- Stop ---

npStop.addEventListener('click', async () => {
  await api('/api/stop', {method: 'POST'});
});

// --- Back ---

backBtn.addEventListener('click', () => {
  // Up and back are the same move here, so let history do it: the header
  // button and the browser button can never disagree.
  history.back();
});

// --- Status polling ---

async function pollStatus() {
  try {
    const s = await api('/api/status');
    lastStatus = s;
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
    brandRelease.textContent = v.title || v.release || '';
    if (v.describe) brand.title = `lp ${v.describe} — release notes`;
  } catch {
    brandRelease.textContent = '';  // leave the lp wordmark, drop the release tag
  }
}

// --- Routing ---
//
// The UI is a single page, so without this the back button leaves the site
// instead of going up a level, which is what everyone expects a website to do.
// Each view and the track picker is a history entry described entirely by the
// URL, so back, forward, reload, and a pasted link all behave.
//
//   /                        the artist grid
//   /?artist=Pallbearer      that artist's albums
//   /?artist=X&tracks=Y      the track picker open over them
//
// Query string rather than path segments on purpose: the app is served by
// StaticFiles at "/", so /artist/X would 404 on a reload while /?artist=X
// serves index.html and lets the router sort it out.

function routeState() {
  const p = new URLSearchParams(location.search);
  return {artist: p.get('artist') || null, tracks: p.get('tracks') || null,
          share: false};
}

// The state actually in effect. `share` is carried in the history entry but
// deliberately NOT in the URL: the screenshot is the result of an action, and a
// URL saying "share" would take a fresh one on every reload. So it survives
// back and forward within a session and dies on reload, which is right.
function currentState() {
  return history.state || routeState();
}

function routeUrl(state) {
  const p = new URLSearchParams();      // note: `share` is intentionally absent
  if (state.artist) p.set('artist', state.artist);
  if (state.tracks) p.set('tracks', state.tracks);
  const q = p.toString();
  return q ? `${location.pathname}?${q}` : location.pathname;
}

// Renders whatever the given state describes. The ONLY place that decides what
// is on screen, so pushing history and responding to back run the same code.
async function applyRoute(state) {
  if (state.artist) {
    if (currentArtist !== state.artist) {
      try {
        await showAlbums(state.artist);
      } catch {
        // A stale or hand-typed artist. Fall back rather than showing nothing.
        return navigate({artist: null, tracks: null}, {replace: true});
      }
    }
  } else if (currentArtist !== null || !artistsLoaded) {
    await showArtists();
  }

  if (state.tracks) {
    await renderTrackSheet(state.artist, state.tracks,
                           albumNameFor(state.artist, state.tracks));
  } else {
    hideTrackSheet();
  }

  // Only re-show if the image is still in hand. Going back revokes the blob, so
  // a forward press afterwards has nothing to show and should stay closed.
  if (state.share && shareModalUrl) shareModal.classList.remove('hidden');
  else hideShareModal();
}

function navigate(state, {replace = false} = {}) {
  const url = routeUrl(state);
  if (replace) history.replaceState(state, '', url);
  else history.pushState(state, '', url);
  return applyRoute(state);
}

const goToArtist = (name) => navigate({artist: name, tracks: null});
// The picker is reachable from the Recently Played shelf too, where no artist
// is in view. Naming the artist anyway keeps the URL self-contained, so a
// reload lands on that artist's albums with the picker open.
const goToTracks = (artist, folder) => navigate({artist, tracks: folder});

window.addEventListener('popstate', (e) => {
  applyRoute(e.state || routeState());
});

async function startRouter() {
  const state = routeState();
  if (!state.artist && !state.tracks) {
    return navigate(state, {replace: true});
  }
  // A pasted link lands mid-app with nothing behind it, so back (and the header
  // back button, which is the same thing) would leave the site. Seed the levels
  // underneath as history entries WITHOUT rendering them: no wasted fetch and
  // no flash of the artist grid, and popstate renders each one if you walk back
  // into it.
  const base = {artist: null, tracks: null};
  history.replaceState(base, '', routeUrl(base));
  if (state.tracks && state.artist) {
    const view = {artist: state.artist, tracks: null};
    history.pushState(view, '', routeUrl(view));
  }
  return navigate(state);
}

// --- Init ---

startRouter();
loadVersion();
statusInterval = setInterval(pollStatus, 3000);
pollStatus();
