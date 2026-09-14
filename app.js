const STORE = {
  PREFS: 'tm_preferences',
  SAVED_TRIPS: 'tm_saved_trips',
  SAVED_PLACES: 'tm_saved_places',
  MY_TRIPS: 'tm_my_trips'
};

function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    return fallback;
  }
}
function saveJSON(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

const DEFAULT_PREFS = {
  vegetarian: true,
  lowCrowds: true,
  luxuryFirst: false,
  budget: 15000,
  pace: 'moderate',
  interests: ['beaches', 'culture'],
  accommodation: 'mid'
};
let prefs = loadJSON(STORE.PREFS, DEFAULT_PREFS);

const ACCOMMODATION_RATES = { budget: 800, mid: 1800, luxury: 4500 };
const INTEREST_OPTIONS = ['beaches', 'culture', 'nature', 'food', 'adventure'];
const DEFAULT_WEATHER = { icon: '☀️', temp: '28°C', desc: 'Perfect beach weather.' };
const API_BASE = window.COLUMBUS_API_BASE || 'http://localhost:8000/api/v1';
const PLACE_COORDS = {
  'Basilica of Bom Jesus': [15.5009, 73.9116],
  'Old Goa Exploration': [15.4989, 73.8278],
  'Vegetarian Lunch at Navtara': [15.4909, 73.8278],
  'Quiet Beach — Ashwem': [15.6592, 73.7196],
  'Solang Valley Trek': [32.3161, 77.1570],
  'Vegetarian Himachali Thali': [32.2432, 77.1892],
  'Hidimba Devi Temple': [32.2420, 77.1777],
  'Amber Fort': [26.9855, 75.8513],
  'Vegetarian Rajasthani Thali': [26.9124, 75.7873],
  'City Palace': [26.9258, 75.8237],
  'Local Heritage Walk': [13.0827, 80.2707],
  'Vegetarian Local Thali': [13.0674, 80.2376]
};
const WEATHER_ICON = { clear: '☀️', clouds: '☁️', rain: '🌧️', drizzle: '🌦️', thunderstorm: '⛈️', snow: '❄️', mist: '🌫️', haze: '🌫️' };
let itineraryMap = null;
let itineraryMapLayer = null;

let state = {
  currentTrip: null,
  returnView: 'viewHome',
  replanTarget: null
};

const DESTINATIONS = {
  goa: {
    label: 'GOA',
    weather: { icon: '☀️', temp: '28°C', desc: 'Perfect beach weather.' },
    map: '🌴 🏖️',
    pool: [
      { id: 'goa1', time: '09:00 AM', title: 'Basilica of Bom Jesus', desc: '16th-century church & UNESCO World Heritage site.', cost: 0, travel: '15 min', category: 'culture', veg: true, crowd: 'high', rating: 4.6, hours: '9:00 AM – 6:30 PM', distance: '6 km', why: 'Iconic heritage site, a great way to start the day.' },
      { id: 'goa2', time: '11:00 AM', title: 'Old Goa Exploration', desc: 'Wander the colorful Latin Quarter.', cost: 0, travel: 'Walk', category: 'culture', veg: true, crowd: 'high', rating: 4.4, hours: 'Open 24 hours', distance: '0.5 km', why: 'Walkable from the previous stop, keeps the morning easy.' },
      { id: 'goa3', time: '01:00 PM', title: 'Vegetarian Lunch at Navtara', desc: 'Local Goan veg thali.', cost: 400, travel: '10 min', category: 'food', veg: true, crowd: 'low', rating: 4.3, hours: '12:00 PM – 4:00 PM', distance: '3 km', why: 'Matches your vegetarian preference.' },
      { id: 'goa5', time: '03:30 PM', title: 'Quiet Beach — Ashwem', desc: 'Relax at Ashwem Beach, away from the crowds.', cost: 0, travel: '45 min', category: 'beach', veg: true, crowd: 'low', rating: 4.7, hours: 'Open 24 hours', distance: '22 km', why: 'Matches your low-crowds preference.' }
    ]
  },
  manali: {
    label: 'MANALI',
    weather: { icon: '⛅', temp: '14°C', desc: 'Cool mountain air, light jacket advised.' },
    map: '🏔️ 🌲',
    pool: [
      { id: 'man1', time: '08:00 AM', title: 'Solang Valley Trek', desc: 'Scenic trek with valley & snow-peak views.', cost: 0, travel: '40 min', category: 'adventure', veg: true, crowd: 'high', rating: 4.6, hours: '7:00 AM – 5:00 PM', distance: '14 km', why: 'A must-do adventure activity near Manali.' },
      { id: 'man2', time: '12:30 PM', title: 'Vegetarian Himachali Thali', desc: 'Local dham-style thali.', cost: 350, travel: '10 min', category: 'food', veg: true, crowd: 'low', rating: 4.4, hours: '12:00 PM – 9:00 PM', distance: '2 km', why: 'Matches your vegetarian preference.' },
      { id: 'man3', time: '02:30 PM', title: 'Hidimba Devi Temple', desc: 'Ancient wooden temple in a cedar forest.', cost: 0, travel: '15 min', category: 'culture', veg: true, crowd: 'low', rating: 4.5, hours: '6:00 AM – 8:00 PM', distance: '3 km', why: 'Quieter cultural stop shaded by cedar forest.' }
    ]
  },
  jaipur: {
    label: 'JAIPUR',
    weather: { icon: '🌤️', temp: '31°C', desc: 'Warm & dry, carry water.' },
    map: '🏰 🐫',
    pool: [
      { id: 'jai1', time: '09:00 AM', title: 'Amber Fort', desc: 'Majestic hilltop fort overlooking the city.', cost: 200, travel: '30 min', category: 'culture', veg: true, crowd: 'high', rating: 4.7, hours: '8:00 AM – 5:30 PM', distance: '11 km', why: "Jaipur's most iconic heritage site." },
      { id: 'jai2', time: '01:00 PM', title: 'Vegetarian Rajasthani Thali', desc: 'Dal baati churma & more.', cost: 450, travel: '10 min', category: 'food', veg: true, crowd: 'low', rating: 4.5, hours: '11:00 AM – 11:00 PM', distance: '4 km', why: 'Matches your vegetarian preference.' },
      { id: 'jai3', time: '03:00 PM', title: 'City Palace', desc: 'Royal palace complex & museum.', cost: 300, travel: '15 min', category: 'culture', veg: true, crowd: 'high', rating: 4.6, hours: '9:30 AM – 5:00 PM', distance: '2 km', why: 'Rich royal history at the heart of the city.' }
    ]
  },
  default: {
    label: 'YOUR TRIP',
    weather: { icon: '🌤️', temp: '26°C', desc: 'Pleasant travel weather.' },
    map: '📍',
    pool: [
      { id: 'gen1', time: '09:00 AM', title: 'Local Heritage Walk', desc: 'Explore the historic quarter on foot.', cost: 0, travel: '15 min', category: 'culture', veg: true, crowd: 'high', rating: 4.3, hours: 'Open all day', distance: '2 km', why: 'A gentle way to get oriented on day one.' },
      { id: 'gen2', time: '01:00 PM', title: 'Vegetarian Local Thali', desc: 'A local vegetarian specialty meal.', cost: 350, travel: '10 min', category: 'food', veg: true, crowd: 'low', rating: 4.4, hours: '12:00 PM – 10:00 PM', distance: '3 km', why: 'Matches your vegetarian preference.' }
    ]
  }
};

const INDOOR_ALTERNATIVES = {
  goa: [
    { title: 'Goa State Museum', desc: 'Indoor historical artifacts.', cost: 100, travel: '20 min' },
    { title: 'Fontainhas Café Hop', desc: 'Cozy indoor cafés in the Latin Quarter.', cost: 300, travel: '10 min' }
  ],
  default: [
    { title: 'Local Indoor Museum', desc: 'A cozy indoor spot to wait out the rain.', cost: 100, travel: '15 min' }
  ]
};

const LOADING_STAGES = [
  'Understanding your preferences...',
  'Finding suitable places...',
  'Checking weather...',
  'Optimizing your route...',
  'Building your itinerary...'
];

const navBtns = document.querySelectorAll('.nav-btn');

function showView(viewId) {
  document.querySelectorAll('.view-section').forEach(v => v.classList.remove('active'));
  const target = document.getElementById(viewId);
  if (target) target.classList.add('active');
  navBtns.forEach(b => b.classList.toggle('active', b.dataset.target === viewId));
}

navBtns.forEach(btn => {
  if(btn.dataset.target) {
    btn.addEventListener('click', () => {
      const target = btn.dataset.target;
      showView(target);
      if (target === 'viewSaved') renderSavedPage();
      if (target === 'viewTrips') renderMyTripsPage();
      if (target === 'viewPrefs') renderPreferencesPage();
    });
  }
});

function goHome() {
  document.getElementById('tripInput').value = '';
  document.getElementById('replanAlert').classList.add('hidden');
  state.currentTrip = null;
  state.replanTarget = null;
  resetMapWidget();
  updateWeatherWidget(DEFAULT_WEATHER);
  showView('viewHome');
}

function fillPrompt(btn) {
  const input = document.getElementById('tripInput');
  input.value = btn.innerText.replace(/[^\w\s,₹]/g, '').trim();
  input.focus();
}

function showToast(message, type) {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast toast-' + (type || 'success');
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 2600);
}

function toggleProfile() {
  document.getElementById('profileDropdown').classList.toggle('hidden');
}

function openAuth(type) {
  document.getElementById('authTitle').textContent = type;
  document.getElementById('profileDropdown').classList.add('hidden');
  showView('viewAuth');
}

function requestLocation() {
  const mapContent = document.getElementById('mapContent');
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        mapContent.innerHTML = '<iframe src="https://maps.google.com/maps?q=Chennai,Tamil%20Nadu,India&t=&z=13&ie=UTF8&iwloc=&output=embed"></iframe>';
      },
      (err) => {
        mapContent.innerHTML = '<div style="padding: 20px; font-weight: 700; color: #D32F2F;">Turn your location on</div>';
      }
    );
  } else {
    mapContent.innerHTML = '<div style="padding: 20px; font-weight: 700;">Geolocation not supported</div>';
  }
}

function resetMapWidget() {
  document.getElementById('mapContent').innerHTML = `
    <div class="map-initial">
      <span style="font-size: 50px;">🗺️</span>
      <br>
      <small>Click to view map</small>
    </div>
  `;
}

function parseTripInput(text) {
  const lower = text.toLowerCase();
  let destKey = null;
  if (lower.includes('goa')) destKey = 'goa';
  else if (lower.includes('manali')) destKey = 'manali';
  else if (lower.includes('jaipur')) destKey = 'jaipur';
  let days = null;
  const dayMatch = lower.match(/(\d+)\s*-?\s*day/);
  if (dayMatch) days = Math.max(1, Math.min(7, parseInt(dayMatch[1], 10)));
  else if (lower.includes('weekend')) days = 2;
  let vegetarian = null;
  if (lower.includes('non-veg') || lower.includes('non veg')) vegetarian = false;
  else if (lower.includes('veg')) vegetarian = true;
  let lowCrowds = null;
  if (lower.includes('low crowd') || lower.includes('quiet') || lower.includes('peaceful')) lowCrowds = true;
  let budget = null;
  const rupeeMatch = lower.match(/₹\s?([\d,]+)/);
  const kMatch = lower.match(/(\d+)\s?k\b/);
  if (rupeeMatch) budget = parseInt(rupeeMatch[1].replace(/,/g, ''), 10);
  else if (kMatch) budget = parseInt(kMatch[1], 10) * 1000;
  let pace = null;
  if (lower.includes('relax') || lower.includes('chill')) pace = 'relaxed';
  else if (lower.includes('packed')) pace = 'packed';
  return { destKey, days, vegetarian, lowCrowds, budget, pace };
}

function buildTripParams(text) {
  const ex = parseTripInput(text);
  return {
    destKey: ex.destKey || 'default',
    days: ex.days || (prefs.pace === 'relaxed' ? 3 : 4),
    vegetarian: ex.vegetarian !== null ? ex.vegetarian : prefs.vegetarian,
    lowCrowds: ex.lowCrowds !== null ? ex.lowCrowds : prefs.lowCrowds,
    budget: ex.budget || prefs.budget,
    pace: ex.pace || prefs.pace
  };
}

function to24h(t) {
  const [time, mer] = t.split(' ');
  let [h, m] = time.split(':').map(Number);
  if (mer === 'PM' && h !== 12) h += 12;
  if (mer === 'AM' && h === 12) h = 0;
  return h * 60 + m;
}

function generateItinerary(params) {
  const dest = DESTINATIONS[params.destKey] || DESTINATIONS.default;
  let pool = dest.pool
    .filter(act => act.category !== 'food' || !params.vegetarian || act.veg)
    .map(act => ({ ...act }));
  if (params.lowCrowds) {
    pool.sort((a, b) => (a.crowd === 'low' ? 0 : 1) - (b.crowd === 'low' ? 0 : 1));
  }
  const seenTimes = new Set();
  pool = pool.filter(act => {
    if (seenTimes.has(act.time)) return false;
    seenTimes.add(act.time);
    return true;
  });
  pool.sort((a, b) => to24h(a.time) - to24h(b.time));
  const perDay = params.pace === 'relaxed' ? 3 : params.pace === 'packed' ? 5 : 4;
  const days = [];
  for (let d = 1; d <= params.days; d++) {
    const dayActs = [];
    for (let i = 0; i < perDay; i++) {
      const flatIdx = (d - 1) * perDay + i;
      const src = pool.length ? pool[flatIdx % pool.length] : null;
      if (src) dayActs.push({ ...src, id: src.id + '_d' + d + '_' + i });
    }
    days.push({
      day: 'DAY ' + String(d).padStart(2, '0'),
      title: d === 1 ? 'Arrival & First Impressions' : 'Exploring ' + dest.label,
      activities: dayActs
    });
  }
  return {
    destKey: params.destKey,
    destLabel: dest.label,
    days: params.days,
    budget: params.budget,
    vegetarian: params.vegetarian,
    lowCrowds: params.lowCrowds,
    pace: params.pace,
    itinerary: days,
    map: dest.map,
    weather: dest.weather
  };
}

async function getWeather(destKey) {
  const fallback = (DESTINATIONS[destKey] || DESTINATIONS.default).weather;
  const first = (DESTINATIONS[destKey] || DESTINATIONS.default).pool[0];
  const coords = first ? PLACE_COORDS[first.title] : null;
  if (!coords) return fallback;
  try {
    const response = await fetch(`${API_BASE}/weather?latitude=${coords[0]}&longitude=${coords[1]}`);
    if (!response.ok) throw new Error('Weather service unavailable');
    const forecast = await response.json();
    if (!forecast.length) return fallback;
    const current = forecast[0];
    const condition = String(current.condition || '').toLowerCase();
    return {
      icon: WEATHER_ICON[condition] || '🌤️',
      temp: `${Math.round(current.temperature_c)}°C`,
      desc: `${condition.charAt(0).toUpperCase() + condition.slice(1)} · ${Math.round((current.rain_probability || 0) * 100)}% rain · OpenWeather`,
      source: current.source
    };
  } catch (error) {
    return { ...fallback, desc: `${fallback.desc} Demo forecast — start the API for live OpenWeather.` };
  }
}
function getPlaces(destKey) {
  return new Promise(resolve => {
    setTimeout(() => resolve((DESTINATIONS[destKey] || DESTINATIONS.default).pool), 200);
  });
}
function getRoutes(dayActivities) {
  return new Promise(resolve => {
    setTimeout(() => resolve((dayActivities || []).map(a => ({ to: a.title, travelTime: a.travel }))), 150);
  });
}

function runLoadingSequence(callback) {
  const stageEl = document.getElementById('loadingStage');
  let i = 0;
  stageEl.textContent = LOADING_STAGES[0];
  const interval = setInterval(() => {
    i++;
    if (i < LOADING_STAGES.length) stageEl.textContent = LOADING_STAGES[i];
  }, 380);
  setTimeout(() => {
    clearInterval(interval);
    callback();
  }, LOADING_STAGES.length * 380 + 200);
}

document.getElementById('tripForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const input = document.getElementById('tripInput');
  const value = input.value.trim();
  const planBtn = document.getElementById('planTripBtn');
  if (!value) {
    const area = document.querySelector('.input-area');
    area.classList.remove('shake');
    void area.offsetWidth;
    area.classList.add('shake');
    showToast('Tell us where you\u2019d like to go first 🌍', 'error');
    input.focus();
    return;
  }
  planBtn.disabled = true;
  planBtn.textContent = 'PLANNING...';
  showView('viewLoading');
  const params = buildTripParams(value);
  Promise.all([getWeather(params.destKey), getPlaces(params.destKey)]).then(([weather]) => {
    runLoadingSequence(() => {
      const trip = generateItinerary(params);
      trip.weather = weather;
      trip.id = 'trip_' + params.destKey + '_' + Date.now();
      addToMyTrips(trip);
      displayItinerary(trip, { returnView: 'viewHome' });
      planBtn.disabled = false;
      planBtn.textContent = 'PLAN MY TRIP ➔';
    });
  });
});

function displayItinerary(trip, opts) {
  opts = opts || {};
  state.currentTrip = trip;
  if (opts.returnView) state.returnView = opts.returnView;
  document.getElementById('itineraryTitle').textContent = trip.destLabel + ' — ' + trip.days + ' DAYS';
  document.getElementById('itineraryTags').textContent = buildTagsText(trip);
  document.getElementById('replanAlert').classList.add('hidden');
  document.getElementById('aiSummaryText').textContent = buildAiSummary(trip);
  renderDays(trip);
  renderBudget(trip);
  renderMapTabs(trip);
  renderKnowledgeGraph(trip);
  updateWeatherWidget(trip.weather);
  updateSaveBtnState();
  showView('viewItinerary');
}

function buildAiSummary(trip) {
  const stopCount = trip.itinerary.reduce((sum, day) => sum + day.activities.length, 0);
  return `I’ve planned a ${trip.days}-day ${trip.destLabel.toLowerCase()} escape with ${stopCount} thoughtfully sequenced stops, balancing ${trip.pace} days, ${trip.vegetarian ? 'vegetarian-friendly food' : 'flexible dining'}, ${trip.lowCrowds ? 'quieter experiences' : 'the essential highlights'}, and your ₹${trip.budget.toLocaleString('en-IN')} budget; use the day maps to follow each route and open the knowledge graph to see why the places belong together.`;
}

function activityCoords(activity) {
  return activity.coordinates || PLACE_COORDS[activity.title] || null;
}

function haversineKm(left, right) {
  const toRad = value => value * Math.PI / 180;
  const dLat = toRad(right[0] - left[0]);
  const dLon = toRad(right[1] - left[1]);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(left[0])) * Math.cos(toRad(right[0])) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function routeMetrics(activities) {
  const points = activities.map(activityCoords).filter(Boolean);
  let distance = 0;
  for (let index = 1; index < points.length; index++) distance += haversineKm(points[index - 1], points[index]);
  return { distance, minutes: Math.round(distance / 28 * 60) };
}

function renderMapTabs(trip) {
  document.getElementById('mapDayTabs').innerHTML = trip.itinerary.map((day, index) =>
    `<button type="button" class="map-day-tab ${index === 0 ? 'active' : ''}" onclick="selectMapDay(${index}, this)" role="tab">Day ${index + 1}</button>`
  ).join('');
  setTimeout(() => selectMapDay(0, document.querySelector('.map-day-tab')), 0);
}

function selectMapDay(dayIndex, button) {
  if (!state.currentTrip || !window.L) return;
  document.querySelectorAll('.map-day-tab').forEach(tab => tab.classList.toggle('active', tab === button));
  const day = state.currentTrip.itinerary[dayIndex];
  const located = day.activities.map(activity => ({ activity, coords: activityCoords(activity) })).filter(item => item.coords);
  if (!itineraryMap) {
    itineraryMap = L.map('itineraryMap', { scrollWheelZoom: false });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
    }).addTo(itineraryMap);
  }
  if (itineraryMapLayer) itineraryMapLayer.remove();
  itineraryMapLayer = L.layerGroup().addTo(itineraryMap);
  located.forEach((item, index) => L.marker(item.coords).bindPopup(`<strong>${index + 1}. ${item.activity.title}</strong><br>${item.activity.time}`).addTo(itineraryMapLayer));
  const points = located.map(item => item.coords);
  if (points.length > 1) L.polyline(points, { color: '#ff6b6b', weight: 5, dashArray: '9 8' }).addTo(itineraryMapLayer);
  if (points.length) itineraryMap.fitBounds(L.latLngBounds(points).pad(0.25));
  else itineraryMap.setView([20.5937, 78.9629], 4);
  setTimeout(() => itineraryMap.invalidateSize(), 50);
  const metrics = routeMetrics(day.activities);
  document.getElementById('routeTotals').innerHTML = `<span><strong>${metrics.distance.toFixed(1)} km</strong> total distance</span><span><strong>${formatDuration(metrics.minutes)}</strong> estimated travel time</span><span>${located.length} mapped stops</span>`;
  document.getElementById('mapContent').innerHTML = `<div class="map-initial"><span style="font-size:42px">🗺️</span><strong>Day ${dayIndex + 1}</strong><small>${located.length} stops · ${metrics.distance.toFixed(1)} km</small></div>`;
}

function formatDuration(minutes) {
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
}

function renderKnowledgeGraph(trip) {
  const nodes = trip.itinerary.flatMap((day, dayIndex) => day.activities.map(activity => ({ ...activity, dayIndex })));
  document.getElementById('knowledgeGraph').innerHTML = `<div class="graph-canvas"><div class="graph-hub">${trip.destLabel}</div>${nodes.map((node, index) => `<div class="graph-node" style="--node-index:${index};--node-count:${Math.max(nodes.length, 1)}"><span>${node.title}</span><small>Day ${node.dayIndex + 1} · ${node.category}</small></div>`).join('')}</div><p class="graph-legend">Relationships show how destination, day, activity type, and preferences informed this itinerary.</p>`;
}

function toggleKnowledgeGraph() {
  const graph = document.getElementById('knowledgeGraph');
  const expanded = graph.classList.toggle('hidden') === false;
  document.getElementById('knowledgeToggle').setAttribute('aria-expanded', String(expanded));
  document.getElementById('knowledgeArrow').textContent = expanded ? '↑' : '↓';
}

function buildTagsText(trip) {
  return [
    '₹' + trip.budget.toLocaleString('en-IN') + ' budget',
    trip.vegetarian ? 'Vegetarian' : 'Non-veg friendly',
    trip.lowCrowds ? 'Low crowds' : 'Popular spots',
    trip.pace.charAt(0).toUpperCase() + trip.pace.slice(1) + ' pace'
  ].join(' · ');
}

function renderDays(trip) {
  const container = document.getElementById('daysContainer');
  container.innerHTML = trip.itinerary.map((day, dayIdx) => `
    <div class="day-block neo-panel-inner">
      <div class="day-header" onclick="toggleDay(this)">
        <span>${day.day}: ${day.title}</span>
        <span class="day-arrow">▼</span>
      </div>
      <div class="day-content">
        ${day.activities.length ? day.activities.map(act => renderActivityRow(act, dayIdx)).join('') : '<p class="empty-day">No activities left for this day — add some from Explore.</p>'}
      </div>
    </div>
  `).join('');
}

function renderActivityRow(act, dayIdx) {
  const saved = isSavedPlace(act.id);
  return `
    <div class="activity" id="act-${act.id}" onclick="openActivityModal('${act.id}')">
      <div class="time">${act.time}</div>
      <div class="details">
        <h4>${act.title} ${act.aiChanged ? '<span class="tag ai-tag">AI Changed</span>' : ''}</h4>
        <p>${act.desc}</p>
      </div>
      <div class="meta">
        <div>💰 ${act.cost ? '₹' + act.cost : 'Free'}</div>
        <div>🚗 ${act.travel}</div>
        <span class="tag">Open</span>
      </div>
      <div class="activity-actions">
        <button class="icon-btn" title="Save place" onclick="event.stopPropagation(); toggleSavePlace('${act.id}')">${saved ? '❤️' : '🤍'}</button>
        <button class="icon-btn" title="Edit" onclick="event.stopPropagation(); openEditActivity(${dayIdx}, '${act.id}')">✏️</button>
        <button class="icon-btn" title="Remove" onclick="event.stopPropagation(); removeActivity(${dayIdx}, '${act.id}')">🗑️</button>
      </div>
    </div>
  `;
}

function toggleDay(header) {
  const content = header.nextElementSibling;
  const icon = header.querySelector('.day-arrow');
  const collapsed = content.classList.contains('collapsed');
  if (!collapsed) {
    content.style.maxHeight = content.scrollHeight + 'px';
    requestAnimationFrame(() => {
      content.classList.add('collapsed');
      content.style.maxHeight = '0px';
    });
    icon.style.transform = 'rotate(-90deg)';
  } else {
    content.classList.remove('collapsed');
    content.style.maxHeight = content.scrollHeight + 'px';
    icon.style.transform = 'rotate(0deg)';
    content.addEventListener('transitionend', function handler() {
      if (!content.classList.contains('collapsed')) content.style.maxHeight = 'none';
      content.removeEventListener('transitionend', handler);
    });
  }
}

function computeBudget(trip) {
  const nights = Math.max(trip.days - 1, 1);
  const stay = ACCOMMODATION_RATES[prefs.accommodation] * nights;
  const transport = trip.days * 300;
  let food = 0, activities = 0;
  trip.itinerary.forEach(day => day.activities.forEach(act => {
    if (act.category === 'food') food += act.cost;
    else activities += act.cost;
  }));
  return { stay, transport, food, activities, total: stay + transport + food + activities };
}

function renderBudget(trip) {
  const b = computeBudget(trip);
  const pct = Math.min(100, Math.round((b.total / trip.budget) * 100));
  const over = b.total > trip.budget;
  document.getElementById('budgetPanel').innerHTML = `
    <div class="budget-top">
      <strong>₹${b.total.toLocaleString('en-IN')} / ₹${trip.budget.toLocaleString('en-IN')}</strong>
      <span class="budget-status ${over ? 'over' : ''}">${over ? 'Over budget' : 'On track'}</span>
    </div>
    <div class="budget-bar"><div class="budget-fill ${over ? 'over' : ''}" style="width:${pct}%;"></div></div>
    <div class="budget-breakdown">
      <span>🏨 Stay ₹${b.stay.toLocaleString('en-IN')}</span>
      <span>🍽️ Food ₹${b.food.toLocaleString('en-IN')}</span>
      <span>🚕 Transport ₹${b.transport.toLocaleString('en-IN')}</span>
      <span>🎟️ Activities ₹${b.activities.toLocaleString('en-IN')}</span>
    </div>
  `;
}

function updateWeatherWidget(weather) {
  document.querySelector('#widgetWeather .widget-body').innerHTML =
    `<span class="text-xl">${weather.icon} ${weather.temp}</span><p>${weather.desc}</p>`;
}

function findActivity(actId) {
  if (!state.currentTrip) return null;
  for (let d = 0; d < state.currentTrip.itinerary.length; d++) {
    const acts = state.currentTrip.itinerary[d].activities;
    const idx = acts.findIndex(a => a.id === actId);
    if (idx !== -1) return { dayIdx: d, actIdx: idx, act: acts[idx] };
  }
  return null;
}

function openActivityModal(actId) {
  const found = findActivity(actId);
  if (!found) return;
  renderModalView(found.act, found.dayIdx);
  document.getElementById('activityModal').classList.remove('hidden');
}

function closeActivityModal() {
  document.getElementById('activityModal').classList.add('hidden');
}

function renderModalView(act, dayIdx) {
  const saved = isSavedPlace(act.id);
  document.getElementById('activityModalContent').innerHTML = `
    <h3>${act.title}</h3>
    <p class="modal-desc">${act.desc}</p>
    <div class="modal-grid">
      <div>⭐ Rating<br><strong>${act.rating != null ? act.rating : '—'}</strong></div>
      <div>🕒 Hours<br><strong>${act.hours || '—'}</strong></div>
      <div>💰 Cost<br><strong>${act.cost ? '₹' + act.cost : 'Free'}</strong></div>
      <div>🚗 Travel<br><strong>${act.travel}</strong></div>
      <div>📏 Distance<br><strong>${act.distance || '—'}</strong></div>
    </div>
    <p class="modal-why">💡 <em>${act.why || 'Selected to fit your preferences.'}</em></p>
    <div class="modal-actions">
      <button class="neo-btn ${saved ? 'primary-btn' : 'secondary-btn'}" onclick="toggleSavePlace('${act.id}')">${saved ? '❤️ Saved' : '🤍 Save place'}</button>
      <button class="neo-btn secondary-btn" onclick="openEditActivity(${dayIdx}, '${act.id}')">✏️ Edit</button>
      <button class="ghost-btn" onclick="removeActivity(${dayIdx}, '${act.id}'); closeActivityModal();">🗑️ Remove</button>
    </div>
  `;
}

function openEditActivity(dayIdx, actId) {
  const found = findActivity(actId);
  if (!found) return;
  const act = found.act;
  document.getElementById('activityModalContent').innerHTML = `
    <h3>Edit Activity</h3>
    <div class="edit-form">
      <label>Title<input type="text" id="editTitle" value="${act.title.replace(/"/g, '&quot;')}"></label>
      <label>Time<input type="text" id="editTime" value="${act.time}"></label>
      <label>Cost (₹)<input type="number" id="editCost" value="${act.cost}" min="0"></label>
      <label>Notes<textarea id="editDesc" rows="2">${act.desc}</textarea></label>
    </div>
    <div class="modal-actions">
      <button class="neo-btn primary-btn" onclick="saveActivityEdit(${dayIdx}, '${actId}')">Save changes</button>
      <button class="ghost-btn" onclick="renderModalView(findActivity('${actId}').act, ${dayIdx})">Cancel</button>
    </div>
  `;
  document.getElementById('activityModal').classList.remove('hidden');
}

function saveActivityEdit(dayIdx, actId) {
  const found = findActivity(actId);
  if (!found) return;
  const act = state.currentTrip.itinerary[dayIdx].activities[found.actIdx];
  act.title = document.getElementById('editTitle').value.trim() || act.title;
  act.time = document.getElementById('editTime').value.trim() || act.time;
  act.cost = parseInt(document.getElementById('editCost').value, 10) || 0;
  act.desc = document.getElementById('editDesc').value.trim() || act.desc;
  renderDays(state.currentTrip);
  renderBudget(state.currentTrip);
  closeActivityModal();
  showToast('✓ Activity updated');
}

function removeActivity(dayIdx, actId) {
  if (!state.currentTrip) return;
  const day = state.currentTrip.itinerary[dayIdx];
  day.activities = day.activities.filter(a => a.id !== actId);
  renderDays(state.currentTrip);
  renderBudget(state.currentTrip);
  showToast('✓ Activity removed');
}

function isSavedPlace(actId) {
  return loadJSON(STORE.SAVED_PLACES, []).some(p => p.id === actId);
}

function toggleSavePlace(actId) {
  const found = findActivity(actId);
  if (!found) return;
  let places = loadJSON(STORE.SAVED_PLACES, []);
  const exists = places.some(p => p.id === actId);
  if (exists) {
    places = places.filter(p => p.id !== actId);
    showToast('Removed from saved places');
  } else {
    const act = found.act;
    places.push({ id: act.id, title: act.title, desc: act.desc, cost: act.cost, travel: act.travel, rating: act.rating, destLabel: state.currentTrip.destLabel });
    showToast('❤️ Place saved');
  }
  saveJSON(STORE.SAVED_PLACES, places);
  renderDays(state.currentTrip);
  if (!document.getElementById('activityModal').classList.contains('hidden')) {
    renderModalView(found.act, found.dayIdx);
  }
}

function saveTrip() {
  if (!state.currentTrip) return;
  let trips = loadJSON(STORE.SAVED_TRIPS, []);
  const exists = trips.some(t => t.id === state.currentTrip.id);
  if (exists) {
    trips = trips.filter(t => t.id !== state.currentTrip.id);
    showToast('Removed from saved trips');
  } else {
    trips.push(state.currentTrip);
    showToast('✓ Trip saved');
  }
  saveJSON(STORE.SAVED_TRIPS, trips);
  updateSaveBtnState();
}
function toggleSave() { saveTrip(); }

function updateSaveBtnState() {
  const btn = document.getElementById('saveTripBtn');
  if (!state.currentTrip) {
    btn.innerHTML = '🤍 Save Trip';
    btn.style.background = 'var(--accent-yellow)';
    btn.style.color = 'var(--black)';
    return;
  }
  const saved = loadJSON(STORE.SAVED_TRIPS, []).some(t => t.id === state.currentTrip.id);
  btn.innerHTML = saved ? '❤️ Saved' : '🤍 Save Trip';
  btn.style.background = saved ? 'var(--primary)' : 'var(--accent-yellow)';
  btn.style.color = saved ? 'white' : 'var(--black)';
}

function loadTrip(id, returnView) {
  const trip = loadJSON(STORE.SAVED_TRIPS, []).find(t => t.id === id);
  if (trip) displayItinerary(trip, { returnView: returnView || 'viewSaved' });
}

function removeSavedTrip(id) {
  const trips = loadJSON(STORE.SAVED_TRIPS, []).filter(t => t.id !== id);
  saveJSON(STORE.SAVED_TRIPS, trips);
  renderSavedPage();
  updateSaveBtnState();
  showToast('Trip removed');
}
function removeSavedPlace(id) {
  const places = loadJSON(STORE.SAVED_PLACES, []).filter(p => p.id !== id);
  saveJSON(STORE.SAVED_PLACES, places);
  renderSavedPage();
  showToast('Place removed');
}

function emptyStateHTML(title, msg) {
  return `
    <div class="empty-state">
      <h3>${title}</h3>
      <p>${msg}</p>
      <button class="neo-btn primary-btn" onclick="showView('viewHome')">Explore destinations →</button>
    </div>
  `;
}

function renderSavedPage() {
  const trips = loadJSON(STORE.SAVED_TRIPS, []);
  const places = loadJSON(STORE.SAVED_PLACES, []);
  document.getElementById('savedTripsContainer').innerHTML = trips.length ? trips.map(t => `
    <div class="day-block neo-panel-inner" style="padding:20px;">
      <h3 style="margin-bottom:10px;">${t.destLabel} — ${t.days} DAYS</h3>
      <p style="color:var(--text-muted); margin-bottom:15px;">₹${t.budget.toLocaleString('en-IN')} budget · ${t.vegetarian ? 'Vegetarian' : 'Non-veg friendly'} · ${t.lowCrowds ? 'Low crowds' : 'Popular spots'}</p>
      <div style="display:flex; gap:10px; flex-wrap:wrap;">
        <button class="neo-btn primary-btn" onclick="loadTrip('${t.id}','viewSaved')">Open Itinerary</button>
        <button class="ghost-btn" onclick="removeSavedTrip('${t.id}')">Remove</button>
      </div>
    </div>
  `).join('') : emptyStateHTML('Nothing saved yet', 'Save trips while exploring and they\u2019ll appear here.');
  document.getElementById('savedPlacesContainer').innerHTML = places.length ? places.map(p => `
    <div class="day-block neo-panel-inner" style="padding:16px;">
      <h4>${p.title}</h4>
      <p style="color:var(--text-muted); font-size:14px; margin:6px 0;">${p.desc}</p>
      <div style="display:flex; justify-content:space-between; align-items:center; font-size:13px; font-weight:600;">
        <span>💰 ${p.cost ? '₹' + p.cost : 'Free'} · 🚗 ${p.travel}</span>
        <button class="ghost-btn" onclick="removeSavedPlace('${p.id}')">Remove</button>
      </div>
    </div>
  `).join('') : emptyStateHTML('No saved places yet', 'Save places while exploring and they\u2019ll appear here.');
}

function seedMyTripsIfEmpty() {
  const existing = loadJSON(STORE.MY_TRIPS, null);
  if (existing === null) {
    saveJSON(STORE.MY_TRIPS, [
      { id: 'trip_seed_jaipur', destKey: 'jaipur', label: 'Jaipur Heritage Walk', days: 3, budget: 22000, vegetarian: false, lowCrowds: false, pace: 'moderate', tags: 'Family Trip', historical: true }
    ]);
  }
}

function addToMyTrips(trip) {
  const trips = loadJSON(STORE.MY_TRIPS, []);
  trips.unshift({
    id: trip.id,
    destKey: trip.destKey,
    label: trip.destLabel + ' Trip',
    days: trip.days,
    budget: trip.budget,
    vegetarian: trip.vegetarian,
    lowCrowds: trip.lowCrowds,
    pace: trip.pace,
    tags: trip.vegetarian ? 'Vegetarian' : 'Flexible',
    historical: false,
    fullTrip: trip
  });
  saveJSON(STORE.MY_TRIPS, trips.slice(0, 10));
}

function renderMyTripsPage() {
  const trips = loadJSON(STORE.MY_TRIPS, []);
  document.getElementById('myTripsContainer').innerHTML = trips.length ? trips.map(t => `
    <div class="day-block neo-panel-inner" style="padding:20px;">
      <h3 style="margin-bottom:10px;">${t.label}</h3>
      <p style="color:var(--text-muted); margin-bottom:15px;">${t.days} Days · ₹${t.budget.toLocaleString('en-IN')} · ${t.tags}</p>
      <div style="display:flex; gap:10px; flex-wrap:wrap;">
        <button class="neo-btn secondary-btn" onclick="openMyTrip('${t.id}')">View Details</button>
        <button class="ghost-btn" onclick="deleteMyTrip('${t.id}')">Delete</button>
      </div>
    </div>
  `).join('') : emptyStateHTML('No trips yet', 'Plan a trip from Explore and it will show up here.');
}

function openMyTrip(id) {
  const record = loadJSON(STORE.MY_TRIPS, []).find(t => t.id === id);
  if (!record) return;
  let trip = record.fullTrip;
  if (!trip) {
    trip = generateItinerary({ destKey: record.destKey, days: record.days, vegetarian: record.vegetarian, lowCrowds: record.lowCrowds, budget: record.budget, pace: record.pace || 'moderate' });
    trip.id = record.id;
  }
  displayItinerary(trip, { returnView: 'viewTrips' });
  showToast('✓ Trip loaded');
}

function deleteMyTrip(id) {
  const trips = loadJSON(STORE.MY_TRIPS, []).filter(t => t.id !== id);
  saveJSON(STORE.MY_TRIPS, trips);
  renderMyTripsPage();
  showToast('Trip deleted');
}

function renderPreferencesPage() {
  document.getElementById('prefsForm').innerHTML = `
    <label class="pref-check"><input type="checkbox" id="prefVeg" ${prefs.vegetarian ? 'checked' : ''}> Always prefer vegetarian food</label>
    <label class="pref-check"><input type="checkbox" id="prefLuxury" ${prefs.luxuryFirst ? 'checked' : ''}> Show luxury accommodations first</label>
    <label class="pref-check"><input type="checkbox" id="prefLowCrowds" ${prefs.lowCrowds ? 'checked' : ''}> Prioritize low-crowd destinations</label>
    <div class="pref-row">
      <label>Budget per trip (₹)</label>
      <input type="number" id="prefBudget" value="${prefs.budget}" min="1000" step="500">
    </div>
    <div class="pref-row">
      <label>Travel pace</label>
      <select id="prefPace">
        <option value="relaxed" ${prefs.pace === 'relaxed' ? 'selected' : ''}>Relaxed (fewer activities/day)</option>
        <option value="moderate" ${prefs.pace === 'moderate' ? 'selected' : ''}>Moderate</option>
        <option value="packed" ${prefs.pace === 'packed' ? 'selected' : ''}>Packed (more activities/day)</option>
      </select>
    </div>
    <div class="pref-row">
      <label>Accommodation</label>
      <select id="prefAccommodation">
        <option value="budget" ${prefs.accommodation === 'budget' ? 'selected' : ''}>Budget</option>
        <option value="mid" ${prefs.accommodation === 'mid' ? 'selected' : ''}>Mid-range</option>
        <option value="luxury" ${prefs.accommodation === 'luxury' ? 'selected' : ''}>Luxury</option>
      </select>
    </div>
    <div class="pref-row">
      <label>Interests</label>
      <div class="suggestions" id="interestPills">
        ${INTEREST_OPTIONS.map(i => `<button type="button" class="pill ${prefs.interests.includes(i) ? 'active' : ''}" onclick="this.classList.toggle('active')">${i}</button>`).join('')}
      </div>
    </div>
    <button class="neo-btn primary-btn" style="width: fit-content; margin-top: 10px;" onclick="savePreferencesFromForm()">Save Preferences</button>
  `;
}

function savePreferencesFromForm() {
  updatePreferences({
    vegetarian: document.getElementById('prefVeg').checked,
    luxuryFirst: document.getElementById('prefLuxury').checked,
    lowCrowds: document.getElementById('prefLowCrowds').checked,
    budget: parseInt(document.getElementById('prefBudget').value, 10) || prefs.budget,
    pace: document.getElementById('prefPace').value,
    accommodation: document.getElementById('prefAccommodation').value,
    interests: Array.from(document.querySelectorAll('#interestPills .pill.active')).map(b => b.textContent)
  });
}

function updatePreferences(newPrefs) {
  prefs = { ...prefs, ...newPrefs };
  saveJSON(STORE.PREFS, prefs);
  showToast('✓ Preferences updated');
}

function replanItinerary(trip) {
  for (let d = 0; d < trip.itinerary.length; d++) {
    const acts = trip.itinerary[d].activities;
    for (let i = 0; i < acts.length; i++) {
      if ((acts[i].category === 'beach' || acts[i].category === 'nature') && !acts[i].aiChanged) {
        return { dayIdx: d, actIdx: i, act: acts[i] };
      }
    }
  }
  return null;
}

function triggerReplan() {
  if (!state.currentTrip) {
    showToast('Generate a trip first.', 'error');
    return;
  }
  const target = replanItinerary(state.currentTrip);
  if (!target) {
    showToast('No weather-sensitive activities left to replan.', 'error');
    return;
  }
  state.replanTarget = target;
  const alts = INDOOR_ALTERNATIVES[state.currentTrip.destKey] || INDOOR_ALTERNATIVES.default;
  document.getElementById('replanAlert').innerHTML = `
    <div class="alert-header">
      <h3>⚠️ AI WEATHER UPDATE</h3>
      <p>Rain expected this afternoon. I suggest swapping your outdoor plan for something indoors.</p>
    </div>
    <div class="compare-box">
      <div class="compare-col original">
        <span>Original</span>
        <strike>${target.act.time} → ${target.act.title}</strike>
      </div>
      <div class="arrow">↓</div>
      <div class="compare-col suggested">
        <span>Suggested</span>
        <strong>${target.act.time} → ${alts[0].title}</strong>
      </div>
    </div>
    <div class="alert-actions">
      <button class="neo-btn primary-btn" onclick="applyChanges(0)">Apply changes</button>
      <button class="neo-btn secondary-btn" onclick="closeReplan()">Keep original</button>
    </div>
  `;
  document.getElementById('replanAlert').classList.remove('hidden');
  document.getElementById('viewItinerary').scrollTo({ top: 0, behavior: 'smooth' });
}

function closeReplan() {
  document.getElementById('replanAlert').classList.add('hidden');
}

function applyChanges(optionIndex) {
  if (!state.replanTarget || !state.currentTrip) return;
  const alts = INDOOR_ALTERNATIVES[state.currentTrip.destKey] || INDOOR_ALTERNATIVES.default;
  const chosen = alts[optionIndex] || alts[0];
  const { dayIdx, actIdx } = state.replanTarget;
  const act = state.currentTrip.itinerary[dayIdx].activities[actIdx];
  act.title = chosen.title;
  act.desc = chosen.desc;
  act.cost = chosen.cost;
  act.travel = chosen.travel;
  act.category = 'indoor';
  act.aiChanged = true;
  renderDays(state.currentTrip);
  renderBudget(state.currentTrip);
  closeReplan();
  showToast('✓ Itinerary updated — your afternoon is now rain-safe.');
  state.replanTarget = null;
}

function init() {
  seedMyTripsIfEmpty();
  renderPreferencesPage();
  renderSavedPage();
  renderMyTripsPage();
  updateSaveBtnState();
  document.getElementById('activityModal').addEventListener('click', (e) => {
    if (e.target.id === 'activityModal') closeActivityModal();
  });
}
init();
