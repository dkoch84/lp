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
const searchInput = $('#search');

let currentArtist = null;
let statusInterval = null;

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

function coverUrl(artist, folder) {
  return `/api/albums/${encodeURIComponent(artist)}/${encodeURIComponent(folder)}/cover`;
}

// --- Vinyl style ---

vinylBtn.addEventListener('click', () => {
  window.location.href = '/vinyl.html';
});

// --- Search ---

searchInput.addEventListener('input', () => {
  const q = searchInput.value.toLowerCase();
  for (const tile of artistGrid.children) {
    const name = tile.dataset.name || '';
    tile.style.display = name.includes(q) ? '' : 'none';
  }
});

// --- Artist grid ---

async function showArtists() {
  currentArtist = null;
  albumGrid.classList.add('hidden');
  artistGrid.classList.remove('hidden');
  searchInput.classList.remove('hidden');
  searchInput.value = '';
  backBtn.classList.add('hidden');
  headerTitle.textContent = 'lp';

  const artists = await api('/api/artists');
  artistGrid.innerHTML = '';
  for (const a of artists) {
    const tile = document.createElement('div');
    tile.className = 'artist-tile';
    tile.dataset.name = a.name.toLowerCase();

    let collageHtml;
    if (a.covers.length === 0) {
      collageHtml = `<div class="artist-collage-empty">&#9835;</div>`;
    } else {
      const count = a.covers.length >= 4 ? 4 : a.covers.length >= 2 ? 2 : 1;
      const cls = count >= 4 ? 'cols-4' : count >= 2 ? 'cols-2' : 'cols-1';
      const imgs = a.covers.slice(0, count)
        .map(folder => `<img src="${coverUrl(a.name, folder)}" alt="" loading="lazy">`)
        .join('');
      collageHtml = `<div class="artist-collage ${cls}">${imgs}</div>`;
    }

    tile.innerHTML = `
      ${collageHtml}
      <div class="artist-name">${esc(a.name)}</div>
      <div class="artist-count">${a.album_count} album${a.album_count !== 1 ? 's' : ''}</div>
    `;
    tile.addEventListener('click', () => showAlbums(a.name));
    artistGrid.appendChild(tile);
  }
}

// --- Album grid ---

async function showAlbums(artistName) {
  currentArtist = artistName;
  artistGrid.classList.add('hidden');
  searchInput.classList.add('hidden');
  albumGrid.classList.remove('hidden');
  backBtn.classList.remove('hidden');
  headerTitle.textContent = artistName;

  const albums = await api(`/api/artists/${encodeURIComponent(artistName)}/albums`);
  albumGrid.innerHTML = '';
  for (const a of albums) {
    const tile = document.createElement('div');
    tile.className = 'album-tile';

    tile.innerHTML = `
      ${a.has_cover
        ? `<img class="album-cover" src="${coverUrl(artistName, a.folder)}" alt="" loading="lazy">`
        : `<div class="album-cover-placeholder">&#9835;</div>`
      }
      <div class="album-title">${esc(a.name)}</div>
      ${a.year ? `<div class="album-year">${esc(a.year)}</div>` : ''}
    `;
    tile.addEventListener('click', () => playAlbum(artistName, a.folder));
    albumGrid.appendChild(tile);
  }
}

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

// --- Init ---

showArtists();
statusInterval = setInterval(pollStatus, 3000);
pollStatus();
