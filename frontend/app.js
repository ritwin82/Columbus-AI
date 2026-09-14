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
const API_BASE = window.COLUMBUS_API_BASE || '/api/v1';
const USER_ID = loadJSON('tm_user_id', 'demo-user');
const WEATHER_ICON = { clear: '☀️', clouds: '☁️', rain: '🌧️', drizzle: '🌦️', thunderstorm: '⛈️', snow: '❄️', mist: '🌫️', haze: '🌫️' };
let itineraryMap = null;
let itineraryMapLayer = null;

let state = {
  currentTrip: null,
  returnView: 'viewHome',
  replanTarget: null,
  serviceStatus: null,
  pendingQuery: ''
};

function humanizeApiError(body, statusCode) {
  const detail = body && body.detail != null ? body.detail : body;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(item => {
      const field = Array.isArray(item.loc)
        ? item.loc.filter(part => part !== 'body').join(' → ')
        : 'request';
      return `${field || 'request'}: ${item.msg || 'Invalid value'}`;
    }).join('\n');
  }
  if (detail && typeof detail === 'object') {
    const lines = [detail.message || `The trip could not be planned (${statusCode}).`];
    if (Array.isArray(detail.reasons) && detail.reasons.length) {
      lines.push(`Why: ${detail.reasons.join(' ')}`);
    }
    if (Array.isArray(detail.suggestions) && detail.suggestions.length) {
      lines.push(`Try: ${detail.suggestions.join(' ')}`);
    }
    return lines.join('\n');
  }
  return `The trip could not be planned (${statusCode}). Please review the details and try again.`;
}

async function apiRequest(path, options) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options && options.headers) },
    ...options
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = humanizeApiError(body, response.status);
    } catch (_) {
      // Keep the HTTP status when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function apiQuery(path, params) {
  const query = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value == null || value === '') return;
    (Array.isArray(value) ? value : [value]).forEach(item => query.append(key, item));
  });
  return apiRequest(`${path}?${query.toString()}`);
}

function toNumber(value, fallback) {
  if (value == null || value === '') return fallback || 0;
  const number = Number(value);
  return Number.isFinite(number) ? number : (fallback || 0);
}

function escapeHTML(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function dateFromNow(daysAhead) {
  const date = new Date();
  date.setDate(date.getDate() + daysAhead);
  return date.toISOString().slice(0, 10);
}

function formatApiTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value || '')
    : date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

function normalizeCategory(categories) {
  const values = (categories || []).map(value => String(value).toLowerCase());
  return values.find(value => ['food', 'restaurant', 'beach', 'nature', 'culture', 'museum', 'temple', 'indoor'].includes(value)) || values[0] || 'attraction';
}

function itineraryFromApi(result, context) {
  context = context || {};
  const firstActivity = result.days.flatMap(day => day.activities)[0];
  const destination = context.destination || (firstActivity && firstActivity.place.destination) || result.title;
  const apiBudget = result.budget || {};
  const activities = result.days.map((day, dayIndex) => ({
    day: `DAY ${String(dayIndex + 1).padStart(2, '0')}`,
    title: new Date(`${day.date}T00:00:00`).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' }),
    date: day.date,
    activities: day.activities.map(activity => {
      const place = activity.place;
      const route = activity.route_from_previous;
      return {
        id: activity.id,
        time: formatApiTime(activity.start_at),
        title: place.name,
        desc: place.description || 'Recommended by Columbus AI.',
        cost: toNumber(activity.estimated_cost_inr),
        travel: route ? `${route.duration_minutes} min` : 'Start',
        category: normalizeCategory(place.categories),
        rating: place.rating,
        ratingSource: place.rating_source,
        hours: `${String(place.opening_time).slice(0, 5)} – ${String(place.closing_time).slice(0, 5)}`,
        distance: route ? `${toNumber(route.distance_km).toFixed(1)} km` : '—',
        why: activity.reason || 'Selected for your preferences, route, budget, and opening hours.',
        coordinates: [place.latitude, place.longitude],
        locked: Boolean(activity.locked),
        warnings: activity.warnings || [],
        citations: place.citations || []
      };
    }),
    restaurant: day.restaurant ? {
      id: day.restaurant.id,
      name: day.restaurant.name,
      destination: day.restaurant.destination,
      area: day.restaurant.area,
      cuisines: day.restaurant.cuisines || [],
      dietary: day.restaurant.dietary || [],
      costForTwo: toNumber(day.restaurant.average_cost_for_two_inr),
      rating: day.restaurant.rating,
      ratingSource: day.restaurant.rating_source,
      sourceNote: day.restaurant.source_note
    } : null
  }));
  return {
    id: result.trip_id,
    tripId: result.trip_id,
    version: result.version,
    destKey: String(destination).toLowerCase().replace(/[^a-z]+/g, '-'),
    destLabel: String(destination).toUpperCase(),
    days: result.days.length,
    budget: toNumber(apiBudget.limit, context.budget),
    vegetarian: context.vegetarian != null ? context.vegetarian : prefs.vegetarian,
    lowCrowds: context.lowCrowds != null ? context.lowCrowds : prefs.lowCrowds,
    pace: context.pace || prefs.pace,
    itinerary: activities,
    weather: DEFAULT_WEATHER,
    summary: result.summary,
    recommendedHotels: result.recommended_hotels || [],
    budgetBreakdown: apiBudget,
    citations: result.citations || [],
    violations: result.violations || [],
    negotiationOptions: result.negotiation_options || [],
    confidence: result.confidence
  };
}

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
  state.pendingQuery = '';
  clearPlannerMessage();
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
  if (lower.includes('chennai')) destKey = 'chennai';
  else if (lower.includes('mamallapuram') || lower.includes('mahabalipuram')) destKey = 'mamallapuram';
  else if (lower.includes('puducherry') || lower.includes('pondicherry')) destKey = 'puducherry';
  let days = null;
  const dayMatch = lower.match(/(\d+)\s*-?\s*day/);
  if (dayMatch) days = Math.max(1, Math.min(5, parseInt(dayMatch[1], 10)));
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

function showPlannerMessage(message, type) {
  const panel = document.getElementById('plannerMessage');
  if (!panel) return;
  panel.className = `planner-message neo-panel-inner ${type || 'question'}`;
  panel.textContent = message;
  panel.classList.remove('hidden');
}

function clearPlannerMessage() {
  const panel = document.getElementById('plannerMessage');
  if (panel) panel.classList.add('hidden');
}

function fallbackDestinations(text) {
  const lower = text.toLowerCase();
  const destinations = [];
  if (lower.includes('chennai')) destinations.push('Chennai');
  if (lower.includes('mamallapuram') || lower.includes('mahabalipuram')) destinations.push('Mamallapuram');
  if (lower.includes('puducherry') || lower.includes('pondicherry')) destinations.push('Puducherry');
  return destinations;
}

function tripRequestFromIntent(text, intent) {
  const local = buildTripParams(text);
  const destinations = intent.destinations && intent.destinations.length
    ? intent.destinations
    : fallbackDestinations(text);
  if (!destinations.length) {
    throw new Error('Please include Chennai, Mamallapuram, or Puducherry in your request.');
  }
  const vegetarian = (intent.dietary || []).includes('vegetarian') || local.vegetarian;
  const lowCrowds = toNumber(intent.crowd_tolerance, 5) <= 3 || local.lowCrowds;
  const pace = intent.pace || local.pace || prefs.pace;
  const budget = toNumber(intent.budget_inr, local.budget || prefs.budget);
  return {
    payload: {
      user_id: USER_ID,
      origin: intent.origin || 'Chennai',
      destinations,
      start_date: dateFromNow(1),
      days: toNumber(intent.days, local.days || 3),
      travellers: toNumber(intent.travellers, 1),
      budget_inr: String(budget),
      preferences: {
        interests: (intent.interests && intent.interests.length) ? intent.interests : prefs.interests,
        dietary: vegetarian ? ['vegetarian'] : (intent.dietary || []),
        accessibility: intent.accessibility || [],
        excluded_categories: [],
        pace,
        travel_mode: intent.travel_mode || 'drive',
        crowd_tolerance: lowCrowds ? 3 : toNumber(intent.crowd_tolerance, 5),
        preferred_language: intent.language || 'en'
      },
      mandatory_place_ids: [],
      locked_activity_ids: []
    },
    context: {
      destination: destinations.join(' · '),
      budget,
      vegetarian,
      lowCrowds,
      pace
    }
  };
}

async function getWeatherForTrip(trip) {
  const first = trip.itinerary.flatMap(day => day.activities).find(activity => activity.coordinates);
  const coords = first && first.coordinates;
  const fallback = DEFAULT_WEATHER;
  if (!coords) return fallback;
  try {
    const forecast = await apiQuery('/weather', { latitude: coords[0], longitude: coords[1] });
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
    return { ...fallback, desc: `${fallback.desc} Weather service unavailable: ${error.message}` };
  }
}

async function enrichTripFromServices(trip, context) {
  const query = [context.destination, ...(prefs.interests || [])].join(' ');
  const [weather, knowledgeHits, hotels] = await Promise.all([
    getWeatherForTrip(trip),
    apiQuery('/knowledge/search', { query, limit: 8 }).catch(() => []),
    apiQuery('/hotels/search', {
      destination: context.destination.split(' · ')[0],
      max_price_inr: Math.max(1000, Math.floor(context.budget / Math.max(trip.days, 1))),
      limit: 6
    }).catch(() => trip.recommendedHotels || [])
  ]);
  trip.weather = weather;
  trip.knowledgeHits = knowledgeHits;
  if (hotels.length) trip.recommendedHotels = hotels;
  return trip;
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

document.getElementById('tripForm').addEventListener('submit', async (e) => {
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
  clearPlannerMessage();
  showView('viewLoading');
  try {
    const fullQuery = state.pendingQuery
      ? `${state.pendingQuery}\nAdditional information: ${value}`
      : value;
    const intent = await apiRequest('/intent', {
      method: 'POST',
      body: JSON.stringify({ text: fullQuery })
    });
    if (intent.missing_required_fields && intent.missing_required_fields.length) {
      state.pendingQuery = fullQuery;
      showView('viewHome');
      showPlannerMessage(
        intent.clarification_question || 'I need a few more trip details before I can plan it.',
        'question'
      );
      input.value = '';
      input.placeholder = 'Reply with the missing information here…';
      input.focus();
      return;
    }
    state.pendingQuery = '';
    input.placeholder = 'e.g. "Plan a 4-day Chennai, Mamallapuram and Puducherry trip with vegetarian food, heritage sites and a ₹25,000 budget."';
    const request = tripRequestFromIntent(fullQuery, intent);
    const result = await apiRequest('/trips/generate', {
      method: 'POST',
      body: JSON.stringify(request.payload)
    });
    const trip = await enrichTripFromServices(itineraryFromApi(result, request.context), request.context);
    await new Promise(resolve => runLoadingSequence(resolve));
    addToMyTrips(trip);
    displayItinerary(trip, { returnView: 'viewHome' });
  } catch (error) {
    showView('viewHome');
    showPlannerMessage(error.message, 'error');
    showToast('I could not create that trip. See the explanation below the planner.', 'error');
  } finally {
    planBtn.disabled = false;
    planBtn.textContent = 'PLAN MY TRIP ➔';
  }
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
  renderHotels(trip);
  updateWeatherWidget(trip.weather);
  updateSaveBtnState();
  showView('viewItinerary');
}

function buildAiSummary(trip) {
  if (trip.summary) return trip.summary;
  const stopCount = trip.itinerary.reduce((sum, day) => sum + day.activities.length, 0);
  return `I’ve planned a ${trip.days}-day ${trip.destLabel.toLowerCase()} escape with ${stopCount} thoughtfully sequenced stops, balancing ${trip.pace} days, ${trip.vegetarian ? 'vegetarian-friendly food' : 'flexible dining'}, ${trip.lowCrowds ? 'quieter experiences' : 'the essential highlights'}, and your ₹${trip.budget.toLocaleString('en-IN')} budget; use the day maps to follow each route and open the knowledge graph to see why the places belong together.`;
}

function activityCoords(activity) {
  return activity.coordinates || null;
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
  document.getElementById('knowledgeGraph').innerHTML = `<div class="graph-canvas"><div class="graph-hub">${escapeHTML(trip.destLabel)}</div>${nodes.map((node, index) => `<div class="graph-node" style="--node-index:${index};--node-count:${Math.max(nodes.length, 1)}"><span>${escapeHTML(node.title)}</span><small>Day ${node.dayIndex + 1} · ${escapeHTML(node.category)}</small></div>`).join('')}</div><p class="graph-legend">Relationships show how destination, day, activity type, and preferences informed this itinerary. Raw retrieval chunks are intentionally kept out of this view.</p>`;
}

function renderHotels(trip) {
  const panel = document.getElementById('hotelRecommendations');
  if (!panel) return;
  const hotels = trip.recommendedHotels || [];
  panel.innerHTML = hotels.length ? hotels.map(hotel => `
    <article class="hotel-card">
      <strong>${escapeHTML(hotel.name)}</strong>
      <span>${escapeHTML(hotel.area)} · ${escapeHTML(hotel.accommodation_type)}</span>
      <span>₹${toNumber(hotel.estimated_price_from_inr).toLocaleString('en-IN')}–₹${toNumber(hotel.estimated_price_to_inr).toLocaleString('en-IN')} per night</span>
      <small>${escapeHTML((hotel.amenities || []).slice(0, 4).join(' · '))}</small>
    </article>`).join('') : '<p>No matching hotels were found for this budget.</p>';
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
        ${renderRestaurantCard(day.restaurant)}
      </div>
    </div>
  `).join('');
}

function renderRestaurantCard(restaurant) {
  if (!restaurant) {
    return '<p class="restaurant-card unavailable">🍽️ No verified restaurant match is available for this day.</p>';
  }
  const rating = restaurant.rating != null
    ? `${Number(restaurant.rating).toFixed(1)} / 5`
    : 'Rating unavailable';
  return `
    <article class="restaurant-card">
      <div class="restaurant-icon">🍽️</div>
      <div>
        <small>RECOMMENDED MEAL</small>
        <h4>${escapeHTML(restaurant.name)}</h4>
        <p>${escapeHTML(restaurant.area)} · ${escapeHTML(restaurant.cuisines.join(', '))}</p>
        <p>${escapeHTML(restaurant.dietary.join(' · '))}</p>
      </div>
      <div class="restaurant-meta">
        <strong>⭐ ${rating}</strong>
        <span>Approx. ₹${restaurant.costForTwo.toLocaleString('en-IN')} for two</span>
        <small>${escapeHTML(restaurant.sourceNote || 'Verify current details before visiting.')}</small>
      </div>
    </article>`;
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
        <div>⭐ ${act.rating != null ? Number(act.rating).toFixed(1) : 'Not rated'}</div>
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
  if (trip.budgetBreakdown) {
    return {
      stay: toNumber(trip.budgetBreakdown.accommodation),
      transport: toNumber(trip.budgetBreakdown.transport),
      food: toNumber(trip.budgetBreakdown.food),
      activities: toNumber(trip.budgetBreakdown.attractions),
      contingency: toNumber(trip.budgetBreakdown.contingency),
      total: toNumber(trip.budgetBreakdown.total)
    };
  }
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
      ${b.contingency ? `<span>🛟 Contingency ₹${b.contingency.toLocaleString('en-IN')}</span>` : ''}
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
    saveJSON(STORE.MY_TRIPS, []);
  } else if (existing.some(trip => trip.historical)) {
    saveJSON(STORE.MY_TRIPS, existing.filter(trip => !trip.historical));
  }
}

function addToMyTrips(trip) {
  const trips = loadJSON(STORE.MY_TRIPS, []).filter(item => item.id !== trip.id);
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

async function openMyTrip(id) {
  const record = loadJSON(STORE.MY_TRIPS, []).find(t => t.id === id);
  if (!record) return;
  try {
    const [result, versions] = await Promise.all([
      apiRequest(`/trips/${encodeURIComponent(id)}`),
      apiRequest(`/trips/${encodeURIComponent(id)}/versions`)
    ]);
    const context = {
      destination: record.label.replace(/ Trip$/i, ''),
      budget: record.budget,
      vegetarian: record.vegetarian,
      lowCrowds: record.lowCrowds,
      pace: record.pace || 'moderate'
    };
    const trip = await enrichTripFromServices(itineraryFromApi(result, context), context);
    displayItinerary(trip, { returnView: 'viewTrips' });
    showToast(`✓ Trip loaded · ${versions.length} saved version${versions.length === 1 ? '' : 's'}`);
  } catch (error) {
    if (record.fullTrip) {
      displayItinerary(record.fullTrip, { returnView: 'viewTrips' });
      showToast('Backend unavailable; showing the locally cached trip.', 'error');
    } else {
      showToast(`Could not load trip: ${error.message}`, 'error');
    }
  }
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
    <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:10px;">
      <button class="neo-btn primary-btn" type="button" onclick="savePreferencesFromForm()">Save Preferences</button>
      <button class="ghost-btn" type="button" onclick="resetPreferences()">Reset travel memory</button>
    </div>
  `;
}

async function savePreferencesFromForm() {
  const updated = {
    vegetarian: document.getElementById('prefVeg').checked,
    luxuryFirst: document.getElementById('prefLuxury').checked,
    lowCrowds: document.getElementById('prefLowCrowds').checked,
    budget: parseInt(document.getElementById('prefBudget').value, 10) || prefs.budget,
    pace: document.getElementById('prefPace').value,
    accommodation: document.getElementById('prefAccommodation').value,
    interests: Array.from(document.querySelectorAll('#interestPills .pill.active')).map(b => b.textContent)
  };
  updatePreferences(updated);
  try {
    await apiRequest(`/users/${encodeURIComponent(USER_ID)}/preferences`, {
      method: 'PUT',
      body: JSON.stringify(preferencesToApi(prefs))
    });
    showToast('✓ Preferences saved to your travel memory');
  } catch (error) {
    showToast(`Saved locally; server memory unavailable: ${error.message}`, 'error');
  }
}

function updatePreferences(newPrefs) {
  prefs = { ...prefs, ...newPrefs };
  saveJSON(STORE.PREFS, prefs);
}

function preferencesToApi(values) {
  return {
    interests: values.interests || [],
    dietary: values.vegetarian ? ['vegetarian'] : [],
    accessibility: values.accessibility || [],
    excluded_categories: [],
    pace: values.pace || 'moderate',
    travel_mode: values.travelMode || 'drive',
    crowd_tolerance: values.lowCrowds ? 3 : 7,
    preferred_language: values.preferredLanguage || 'en'
  };
}

function preferencesFromApi(values) {
  return {
    ...prefs,
    interests: values.interests || prefs.interests,
    vegetarian: (values.dietary || []).includes('vegetarian'),
    lowCrowds: toNumber(values.crowd_tolerance, 5) <= 3,
    pace: values.pace || prefs.pace,
    accessibility: values.accessibility || [],
    travelMode: values.travel_mode || 'drive',
    preferredLanguage: values.preferred_language || 'en'
  };
}

async function loadRemotePreferences() {
  try {
    const remote = await apiRequest(`/users/${encodeURIComponent(USER_ID)}/preferences`);
    prefs = preferencesFromApi(remote);
    saveJSON(STORE.PREFS, prefs);
    renderPreferencesPage();
  } catch (_) {
    // A 404 is expected before the user's first generated trip or preference save.
  }
}

async function resetPreferences() {
  try {
    await apiRequest(`/users/${encodeURIComponent(USER_ID)}/preferences`, { method: 'DELETE' });
  } catch (error) {
    if (!String(error.message).includes('404')) showToast(error.message, 'error');
  }
  prefs = { ...DEFAULT_PREFS };
  saveJSON(STORE.PREFS, prefs);
  renderPreferencesPage();
  showToast('Travel memory and local preferences reset');
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

async function triggerReplan() {
  if (!state.currentTrip) {
    showToast('Generate a trip first.', 'error');
    return;
  }
  const button = document.getElementById('replanBtn');
  button.disabled = true;
  button.textContent = 'Replanning…';
  document.getElementById('replanAlert').innerHTML = `
    <div class="alert-header">
      <h3>✦ AGENTIC REPLANNING</h3>
      <p>The planner is preserving locked activities and recalculating weather, routes, budget, and feasibility.</p>
    </div>
  `;
  document.getElementById('replanAlert').classList.remove('hidden');
  document.getElementById('viewItinerary').scrollTo({ top: 0, behavior: 'smooth' });
  try {
    const current = state.currentTrip;
    const result = await apiRequest(`/trips/${encodeURIComponent(current.tripId)}/replan`, {
      method: 'POST',
      body: JSON.stringify({
        reason: 'Re-evaluate this itinerary using the latest weather, route, budget, and knowledge information.',
        locked_activity_ids: current.itinerary.flatMap(day => day.activities).filter(activity => activity.locked).map(activity => activity.id),
        preference_changes: preferencesToApi(prefs)
      })
    });
    const context = {
      destination: current.destLabel,
      budget: current.budget,
      vegetarian: current.vegetarian,
      lowCrowds: current.lowCrowds,
      pace: current.pace
    };
    const replanned = await enrichTripFromServices(itineraryFromApi(result, context), context);
    addToMyTrips(replanned);
    displayItinerary(replanned, { returnView: state.returnView });
    showToast(`✓ Itinerary updated to version ${replanned.version}`);
  } catch (error) {
    closeReplan();
    showToast(`Could not replan: ${error.message}`, 'error');
  } finally {
    button.disabled = false;
    button.textContent = '🌦️ Replan with AI';
  }
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

async function refreshServiceStatus() {
  const tip = document.querySelector('#widgetTip .widget-body p');
  try {
    state.serviceStatus = await apiRequest('/status');
    const models = state.serviceStatus.dependencies.models;
    const provider = models.last_chat_provider || models.provider_order.find(name => models.providers[name] && models.providers[name].enabled) || 'offline';
    tip.textContent = `Backend ready · ${state.serviceStatus.mode} travel data · ${provider} model route`;
  } catch (_) {
    tip.textContent = 'Backend offline — start FastAPI to plan trips.';
  }
}

async function init() {
  seedMyTripsIfEmpty();
  renderPreferencesPage();
  renderSavedPage();
  renderMyTripsPage();
  updateSaveBtnState();
  document.getElementById('activityModal').addEventListener('click', (e) => {
    if (e.target.id === 'activityModal') closeActivityModal();
  });
  await Promise.all([refreshServiceStatus(), loadRemotePreferences()]);
}
init();
