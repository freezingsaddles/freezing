// https://mokole.com/palette.html - 25 / 20% / 80% / 5000
// const track_colors = [
// 	'#c0c0c0', '#2f4f4f', '#556b2f', '#800000', '#483d8b',
// 	'#3cb371', '#000080', '#9acd32', '#8b008b', '#ff0000',
// 	'#00ced1', '#ffa500', '#ffff00', '#7fff00', '#8a2be2',
// 	'#00ff7f', '#00bfff', '#0000ff', '#ff7f50', '#ff00ff',
// 	'#1e90ff', '#db7093', '#f0e68c', '#ff1493', '#ee82ee',
// ];
// https://observablehq.com/@shan/oklab-color-wheel - .65 / 26 / 2 / 0 / .29
const track_colors = [
  'rgb(255, 0, 0)', 'rgb(255, 49, 0)', 'rgb(246, 83, 0)', 'rgb(224, 109, 0)', 'rgb(195, 132, 0)',
  'rgb(157, 151, 0)', 'rgb(106, 166, 0)', 'rgb(0, 178, 0)', 'rgb(0, 186, 3)', 'rgb(0, 191, 99)',
  'rgb(0, 191, 150)', 'rgb(0, 188, 194)', 'rgb(0, 180, 232)', 'rgb(0, 169, 255)', 'rgb(0, 154, 255)',
  'rgb(0, 137, 255)', 'rgb(33, 119, 255)', 'rgb(112, 101, 255)', 'rgb(153, 83, 255)', 'rgb(185, 65, 255)',
  'rgb(212, 44, 252)', 'rgb(234, 10, 218)', 'rgb(252, 0, 179)', 'rgb(255, 0, 136)', 'rgb(255, 0, 87)',
];

function create_ride_map(id, url, ride_color = null, recenter = false) {
  const map = L.map(id, {gestureHandling: true, maxZoom: 20}).setView([38.9072, -77.0369], 9);
  const style = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark-matter-gl-style" : "positron-gl-style";
  const basemap = L.maplibreGL({
    style: 'https://basemaps.cartocdn.com/gl/' + style + '/style.json?key=cb1_25fo_1_2f0e687e9c1f7729ab0666b9',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(map);
  fetch(url).then(r => r.json()).then(data => {
    if (recenter) {
      let minlat = 90, maxlat = -90, minlon = 180, maxlon = -180;
      for (const {track} of data.tracks) {
        for (const [lat, lon] of track) {
          if (lat < minlat) minlat = lat;
          if (lat > maxlat) maxlat = lat;
          if (lon < minlon) minlon = lon;
          if (lon > maxlon) maxlon = lon;
        }
      }
      if (minlat < maxlat) {
        const bounds = new L.LatLngBounds([[maxlat, maxlon], [minlat, minlon]]);
        map.fitBounds(bounds, {padding: [20, 20]});
      }
    }
    // the absence of teams is for legacy cached responses that will rapidly expire.
    const teams = {};
    data.teams?.forEach(({id, name}, index) => teams[id] = {name, index});
    const colors = Object.keys(teams).length > 1 ? track_colors : ['#00a4e4'];
    data.tracks.forEach(({team, track}, index) => {
      const team_info = teams[team];
      const polyline = L.polyline([track], {
        color: ride_color ?? colors[(team_info?.index ?? team) % colors.length],
        opacity: .2 + .4 * (index + 1) / data.tracks.length,
        weight: 2
      });
      if (team_info && !ride_color)
        polyline.bindTooltip(team_info.name);
      polyline.addTo(map);
    });
  });
  return map;
}

// Playing the season back, a window of rides at a time: the window slides from
// before the first ride to after the last, so the map fills, runs and empties.
//
// Pages arrive in order and are appended to one stream, because a page holds a
// fixed number of rides and a ride can contribute more than one track, so the
// track a position refers to is only known once the pages before it are in.
const WINDOW_TRACKS = 1000;
const RIDES_PER_SECOND = 250;
const FADE_IN_SECONDS = .8;
const DIMMEST = 0, BRIGHTEST = .6;

function animate_ride_map(id, manifest_url) {
  const map = L.map(id, {gestureHandling: true, maxZoom: 20}).setView([38.9072, -77.0369], 9);
  const style = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark-matter-gl-style" : "positron-gl-style";
  L.maplibreGL({
    style: 'https://basemaps.cartocdn.com/gl/' + style + '/style.json?key=cb1_25fo_1_2f0e687e9c1f7729ab0666b9',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(map);

  const stream = [];            // every track of every page loaded so far
  const waiting = new Map();    // page -> its tracks, when it came out of turn
  const drawn = new Map();      // position in the stream -> its polyline
  let teams = {}, colors = ['#00a4e4'], pages = 0, next = 0, asked = 0;
  let page_url = () => null;
  let start = -WINDOW_TRACKS, previous = 0, frame = 0;

  function take(page, data) {
    if (page !== next) { waiting.set(page, data); return; }
    for (let p = page; waiting.has(p) || p === page; p = next) {
      for (const track of p === page ? data.tracks : waiting.get(p)) stream.push(track);
      waiting.delete(p);
      next = p + 1;
    }
  }

  function request() {
    // One window of rides beyond what is being shown, so a page is asked for
    // long before the window reaches it.
    while (asked < pages && stream.length - start < WINDOW_TRACKS * 2) {
      const page = asked++;
      fetch(page_url(page)).then(r => r.json()).then(data => {
        if (!Object.keys(teams).length && data.teams?.length > 1) {
          data.teams.forEach(({id: team, name}, index) => teams[team] = {name, index});
          colors = track_colors;
        }
        take(page, data);
      });
    }
  }

  function opacity(i) {
    // Counted in seconds: a ride appearing is something the eye judges against
    // the clock, so it should not change when the season is played faster.
    const arriving = Math.min(FADE_IN_SECONDS * RIDES_PER_SECOND, WINDOW_TRACKS - 1);
    const newness = (i - start + 1) / WINDOW_TRACKS;
    const full = 1 - arriving / WINDOW_TRACKS;
    const fraction = newness > full ? (1 - newness) / (1 - full) : newness / full;
    return Math.max(0, Math.min(BRIGHTEST, DIMMEST + (BRIGHTEST - DIMMEST) * fraction));
  }

  function draw(i) {
    const {team, track} = stream[i];
    const team_info = teams[team];
    const line = L.polyline([track], {
      color: colors[(team_info?.index ?? team ?? 0) % colors.length],
      opacity: opacity(i),
      weight: 2,
    });
    if (team_info) line.bindTooltip(team_info.name);
    line.addTo(map);
    drawn.set(i, line);
  }

  function step(rides) {
    const done = next >= pages;
    if (done && start >= stream.length) {
      // The window has passed the last ride; put it back before the first.
      for (const line of drawn.values()) map.removeLayer(line);
      drawn.clear();
      start = -WINDOW_TRACKS;
      return;
    }
    const leaving = Math.min(start + rides, stream.length);
    for (let i = Math.max(0, start); i < leaving; i++) {
      const line = drawn.get(i);
      if (line) { map.removeLayer(line); drawn.delete(i); }
    }
    start = leaving;

    // The window hangs over nothing before the first ride and after the last,
    // so it simply holds fewer tracks at either end.
    const from = Math.max(0, start), to = Math.min(start + WINDOW_TRACKS, stream.length);
    for (let i = from; i < to; i++) if (!drawn.has(i)) draw(i);
    for (const [i, line] of drawn) line.setStyle({opacity: opacity(i)});
    request();
  }

  function tick(now) {
    if (previous) {
      // A tab left in the background reports an enormous gap, and stepping by
      // it would cross most of a season in one frame.
      const elapsed = Math.min(now - previous, 250);
      step(Math.max(1, Math.round(RIDES_PER_SECOND * elapsed / 1000)));
    }
    previous = now;
    frame = requestAnimationFrame(tick);
  }

  map.playing = () => !!frame;
  map.play = () => { if (!frame) frame = requestAnimationFrame(tick); };
  map.pause = () => { cancelAnimationFrame(frame); frame = previous = 0; };

  fetch(manifest_url).then(r => r.json()).then(manifest => {
    pages = manifest.pages;
    // The season is in the path so that a page cached from one year cannot be
    // served for the next, when the ride ids have all been reused.
    page_url = page => manifest_url.replace(/pages\.json$/, `${manifest.season}/${page}.json`);
    request();
    map.play();
  });
  return map;
}
