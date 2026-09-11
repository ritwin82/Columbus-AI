/* ==========================================================
   TravelMind AI — frontend logic
   ----------------------------------------------------------
   This runs entirely on mock data so the UI is demo-ready with
   no backend. To wire it to the real system: replace the body
   of handleUserMessage()'s setTimeout with a fetch() call to
   the FastAPI /chat endpoint, and feed its JSON response into
   buildItinerary()'s output shape (see the object returned by
   buildItinerary below for the exact fields the UI expects).
========================================================== */

/* ---------------- Mock knowledge base ---------------- */

const LANDMARKS = {
  goa: [
    { t: 'Baga Beach sunrise walk', n: 'Quiet tide, good light for photos.' },
    { t: 'Fort Aguada', n: '17th-century Portuguese fort with lighthouse views.' },
    { t: 'Dudhsagar Falls jeep safari', n: 'A four-tiered waterfall inside a wildlife sanctuary.' },
    { t: 'Spice plantation walk', n: 'Cardamom, pepper and betel nut groves.' },
    { t: 'Fontainhas heritage lanes', n: "Panjim's Latin Quarter, pastel Portuguese houses." },
    { t: 'Anjuna flea market', n: 'Handmade jewellery, music and beach shacks.' },
    { t: 'Chapora Fort viewpoint', n: 'Hilltop fort overlooking the river mouth.' },
    { t: 'Assagao café lunch', n: 'Slow lanes and converted Portuguese villas.' }
  ],
  manali: [
    { t: 'Old Manali riverside walk', n: 'Cafés and craft shops along the Beas.' },
    { t: 'Hadimba Temple', n: 'Cedar-forest temple with 16th-century wooden architecture.' },
    { t: 'Solang Valley', n: 'Paragliding, ropeway rides and mountain views.' },
    { t: 'Vashisht hot springs', n: 'Natural sulphur springs above the village.' },
    { t: 'Naggar Castle', n: 'Timber-and-stone castle with valley views.' },
    { t: 'Local apple orchard visit', n: 'Seasonal fruit and mountain air.' },
    { t: 'Mall Road evening stroll', n: 'Shops, snacks and street music.' },
    { t: 'Jogini Falls short trek', n: 'An easy hike to a forest waterfall.' }
  ],
  jaipur: [
    { t: 'Amber Fort', n: 'Hilltop fort with mirrored halls and courtyards.' },
    { t: 'Hawa Mahal photo stop', n: 'The five-storey pink sandstone façade.' },
    { t: 'City Palace', n: 'Royal courtyards, museums and an armoury.' },
    { t: 'Jantar Mantar', n: '18th-century astronomical instruments.' },
    { t: 'Johari Bazaar shopping', n: 'Jewellery, textiles and lac bangles.' },
    { t: 'Nahargarh Fort at sunset', n: 'Panoramic views over the pink city.' },
    { t: 'Chokhi Dhani cultural evening', n: 'Folk dance, puppet shows and a Rajasthani thali.' },
    { t: 'Jal Mahal viewpoint', n: 'A palace that appears to float on Man Sagar Lake.' }
  ],
  kerala: [
    { t: 'Alleppey backwaters houseboat', n: 'A slow cruise through palm-lined canals.' },
    { t: 'Munnar tea gardens', n: 'Rolling green hills and a tea museum.' },
    { t: 'Fort Kochi heritage walk', n: 'Chinese fishing nets and colonial streets.' },
    { t: 'Periyar Wildlife Sanctuary', n: 'Boat safari past elephants and bison.' },
    { t: 'Kathakali performance', n: 'Traditional dance-drama with elaborate makeup.' },
    { t: 'Mattancherry spice market', n: 'Cardamom, pepper and cloves by the sackful.' },
    { t: 'Ayurvedic massage session', n: 'A traditional treatment to unwind.' },
    { t: 'Varkala cliffside beach', n: 'Red cliffs above a quiet stretch of sand.' }
  ],
  udaipur: [
    { t: 'City Palace complex', n: 'Lakefront palace with courtyards and museums.' },
    { t: 'Lake Pichola boat ride', n: 'Views of floating palaces at dusk.' },
    { t: 'Jagdish Temple', n: 'An ornately carved Indo-Aryan temple.' },
    { t: 'Saheliyon ki Bari gardens', n: 'Fountains and marble kiosks.' },
    { t: 'Bagore ki Haveli dance show', n: 'Rajasthani folk dance by the ghats.' },
    { t: 'Old city bazaar walk', n: 'Miniature paintings and textiles.' }
  ],
  rishikesh: [
    { t: 'Laxman Jhula bridge walk', n: 'A suspension bridge over the Ganges.' },
    { t: 'Triveni Ghat evening aarti', n: 'A riverside prayer ceremony with lamps.' },
    { t: 'White-water rafting', n: 'Rapids on the Ganges through the foothills.' },
    { t: 'Beatles Ashram', n: 'An abandoned ashram covered in murals.' },
    { t: 'Sunrise yoga by the river', n: 'A class on the ghats as the town wakes up.' },
    { t: 'Neer Garh Waterfall hike', n: 'A short trek to a forest waterfall.' }
  ]
};

function genericLandmarks(destination) {
  return [
    ['Old town walking tour', 'Get oriented among the historic streets.'],
    ['Local market visit', 'Fresh produce, spices and handicrafts.'],
    ['Signature viewpoint', 'The spot everyone recommends for photos.'],
    ['Regional food tasting', "A sampler of the area's best-known dishes."],
    ['Museum or heritage site', 'A deeper look at local history.'],
    ['Sunset by the water or hills', 'Wind down as the light changes.'],
    ['Neighbourhood café crawl', 'Coffee, pastries and people-watching.'],
    ['Evening cultural show', 'Music, dance or a local performance.']
  ].map(([t, n]) => ({ t: `${t} in ${destination}`, n }));
}

const WEATHER = {
  goa: { temp: 29, cond: 'sunny' },
  manali: { temp: 14, cond: 'cloudy' },
  jaipur: { temp: 33, cond: 'sunny' },
  kerala: { temp: 27, cond: 'rainy' },
  udaipur: { temp: 30, cond: 'sunny' },
  rishikesh: { temp: 24, cond: 'cloudy' },
  default: { temp: 26, cond: 'sunny' }
};

const BUDGET_BASE = {
  goa: 2800, manali: 3200, jaipur: 2600, kerala: 3500,
  udaipur: 3000, rishikesh: 2200, default: 2800
};

const KNOWN_DESTINATIONS = [
  { key: 'goa', names: ['goa'] },
  { key: 'manali', names: ['manali'] },
  { key: 'jaipur', names: ['jaipur'] },
  { key: 'kerala', names: ['kerala', 'munnar', 'alleppey', 'kochi', 'cochin'] },
  { key: 'udaipur', names: ['udaipur'] },
  { key: 'rishikesh', names: ['rishikesh'] }
];
const DISPLAY_NAMES = { goa: 'Goa', manali: 'Manali', jaipur: 'Jaipur', kerala: 'Kerala', udaipur: 'Udaipur', rishikesh: 'Rishikesh' };

const PREFERENCE_PATTERNS = [
  [/veg(etarian)?\b/, 'Vegetarian'],
  [/vegan/, 'Vegan'],
  [/(low|small)\s*budget|cheap|budget-?friendly/, 'Budget-friendly'],
  [/luxury|premium|5-?star/, 'Luxury'],
  [/trek|hik|adventure|rafting/, 'Adventure'],
  [/family|kids/, 'Family friendly'],
  [/solo|alone/, 'Solo travel'],
  [/honeymoon|romantic|couple/, 'Honeymoon'],
  [/beach/, 'Beach'],
  [/heritage|culture|historic/, 'Heritage'],
  [/nightlife|party/, 'Nightlife'],
  [/low crowd|offbeat|less crowd|quiet/, 'Low crowds'],
  [/backwater/, 'Backwaters'],
  [/wildlife|safari/, 'Wildlife'],
  [/accessible|wheelchair/, 'Accessible']
];

const ICONS = {
  pin: '<svg viewBox="0 0 16 16"><path d="M8 14s5-4.5 5-8a5 5 0 10-10 0c0 3.5 5 8 5 8z"/><circle cx="8" cy="6" r="1.6"/></svg>',
  calendar: '<svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="11" rx="1.5"/><path d="M2 6.5h12M5 1.5v3M11 1.5v3"/></svg>',
  people: '<svg viewBox="0 0 16 16"><circle cx="6" cy="5.5" r="2.3"/><path d="M1.6 14c.5-2.6 2.3-4 4.4-4s3.9 1.4 4.4 4"/><circle cx="11.5" cy="6" r="1.8"/><path d="M10.5 10.3c1.6.2 2.9 1.5 3.3 3.7"/></svg>',
  sun: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.3 3.3l1.4 1.4M11.3 11.3l1.4 1.4M3.3 12.7l1.4-1.4M11.3 4.7l1.4-1.4"/></svg>',
  cloud: '<svg viewBox="0 0 16 16"><path d="M4.5 12h7a2.7 2.7 0 000-5.4 3.6 3.6 0 00-6.9-1.2A3 3 0 004.5 12z"/></svg>',
  rain: '<svg viewBox="0 0 16 16"><path d="M4.5 9h7a2.7 2.7 0 000-5.4 3.6 3.6 0 00-6.9-1.2A3 3 0 004.5 9z"/><path d="M5 12l-1 2M8 12l-1 2M11 12l-1 2"/></svg>'
};
function weatherIcon(cond) {
  if (cond === 'cloudy') return ICONS.cloud;
  if (cond === 'rainy') return ICONS.rain;
  return ICONS.sun;
}

/* ---------------- State ---------------- */

const STORAGE = { history: 'tm_history_v1', saved: 'tm_saved_v1' };

const appState = {
  messages: [],
  history: [],
  savedTrips: [],
  currentItinerary: null,
  rightViewMode: 'summary'
};

function persist(key) {
  try { localStorage.setItem(STORAGE[key], JSON.stringify(appState[key])); }
  catch (err) { console.warn('Could not save to localStorage', err); }
}
function loadPersisted() {
  try {
    appState.history = JSON.parse(localStorage.getItem(STORAGE.history)) || [];
    appState.savedTrips = JSON.parse(localStorage.getItem(STORAGE.saved)) || [];
  } catch (err) {
    appState.history = [];
    appState.savedTrips = [];
  }
}

/* ---------------- Helpers ---------------- */

function escapeHTML(str) {
  return String(str).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}
function cryptoId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}
function inr(n) {
  return n.toLocaleString('en-IN');
}

/* ---------------- Parsing user input into trip details ---------------- */

function detectDestination(text) {
  const lower = text.toLowerCase();
  for (const d of KNOWN_DESTINATIONS) {
    if (d.names.some(n => lower.includes(n))) return { key: d.key, display: DISPLAY_NAMES[d.key] };
  }
  const match = text.match(/(?:to|in|for)\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){0,2})/);
  if (match) return { key: 'default', display: match[1] };
  return { key: 'default', display: 'your destination' };
}

function parseTripDetails(text) {
  const lower = text.toLowerCase();
  const dest = detectDestination(text);

  const dayMatch = lower.match(/(\d+)\s*-?\s*day/);
  let days = dayMatch ? parseInt(dayMatch[1], 10) : 3;
  days = Math.min(Math.max(days, 1), 10);

  let travelers;
  const paxMatch = lower.match(/(\d+)\s*(?:people|pax|persons|travellers|travelers|friends)/);
  if (paxMatch) travelers = parseInt(paxMatch[1], 10);
  else if (/solo|alone|by myself/.test(lower)) travelers = 1;
  else if (/family/.test(lower)) travelers = 4;
  else travelers = 2;
  travelers = Math.min(Math.max(travelers, 1), 12);

  const budgetMatch = text.match(/(?:₹|rs\.?|inr)\s?([\d,]{3,7})/i);
  const budgetOverride = budgetMatch ? parseInt(budgetMatch[1].replace(/,/g, ''), 10) : null;

  const tags = [];
  PREFERENCE_PATTERNS.forEach(([re, label]) => { if (re.test(lower)) tags.push(label); });
  if (!tags.length) tags.push('Personalized');

  return { destinationKey: dest.key, destination: escapeHTML(dest.display), days, travelers, budgetOverride, tags };
}

function buildItinerary(details) {
  const landmarks = LANDMARKS[details.destinationKey] || genericLandmarks(details.destination);
  const times = ['9:00 AM', '12:30 PM', '3:30 PM', '7:00 PM'];
  const schedule = [];
  for (let d = 0; d < details.days; d++) {
    const stops = [];
    for (let s = 0; s < 4; s++) {
      const spot = landmarks[(d * 4 + s) % landmarks.length];
      stops.push({ time: times[s], t: spot.t, n: spot.n });
    }
    schedule.push(stops);
  }
  const weather = WEATHER[details.destinationKey] || WEATHER.default;
  const base = BUDGET_BASE[details.destinationKey] || BUDGET_BASE.default;
  const scaled = base * details.days * (1 + (details.travelers > 1 ? 0.35 * (details.travelers - 1) : 0));
  const budget = details.budgetOverride || Math.round(scaled / 10) * 10;

  return {
    destination: details.destination, days: details.days, travelers: details.travelers,
    budget, weather, tags: details.tags, schedule, activeDay: 0, expanded: false
  };
}

function generateReplyText(details) {
  const tagPhrase = details.tags.filter(t => t !== 'Personalized').join(', ').toLowerCase();
  const focus = tagPhrase ? `, keeping ${tagPhrase} in mind` : '';
  return `Here's a ${details.days}-day plan for ${details.destination}${focus}. I checked the weather and grouped nearby stops together to cut down on travel time.`;
}

/* ---------------- Rendering: chat ---------------- */

const messagesEl = document.getElementById('messages');
const emptyStateTemplate = document.getElementById('emptyState').cloneNode(true);

function itineraryCardHTML(msg) {
  const it = msg.itinerary;
  const dayIdx = it.activeDay || 0;
  const tabs = it.schedule.map((_, i) => `<button class="day-tab ${i === dayIdx ? 'active' : ''}" data-day="${i}">Day ${i + 1}</button>`).join('');

  let body;
  if (it.expanded) {
    body = it.schedule.map((stops, i) => `
      <p class="day-heading">Day ${i + 1}</p>
      <ol class="route">${stops.map(stopHTML).join('')}</ol>
    `).join('');
  } else {
    body = `<div class="day-tabs">${tabs}</div><ol class="route">${it.schedule[dayIdx].map(stopHTML).join('')}</ol>`;
  }

  const saved = isTripSaved(it);
  return `
    <div class="itinerary-card" data-msg-id="${msg.id}">
      <div class="itinerary-head">
        <div>
          <h3>${it.destination}</h3>
          <span class="days-label">${it.days}-day plan for ${it.travelers} ${it.travelers > 1 ? 'travelers' : 'traveler'}</span>
        </div>
        <span class="budget-pill">₹${inr(it.budget)}</span>
      </div>
      ${body}
      <div class="itinerary-foot">
        <button class="ghost-btn view-full">${it.expanded ? 'Show day by day' : 'View full itinerary'}</button>
        <button class="save-btn ${saved ? 'saved' : ''}">
          <svg viewBox="0 0 16 16"><path d="M4 2h8v12l-4-3-4 3z"/></svg>
          ${saved ? 'Saved' : 'Save trip'}
        </button>
      </div>
    </div>`;
}
function stopHTML(s) {
  return `<li class="stop"><span class="stop-time">${s.time}</span><span class="stop-dot"></span><div class="stop-body"><h4>${s.t}</h4><p>${s.n}</p></div></li>`;
}

function renderMessageNode(msg) {
  const wrap = document.createElement('div');
  wrap.className = `msg msg--${msg.role}`;
  wrap.dataset.id = msg.id;
  wrap.innerHTML = `<div class="msg-bubble">${escapeHTML(msg.text)}</div>${msg.itinerary ? itineraryCardHTML(msg) : ''}`;
  return wrap;
}

function renderAllMessages() {
  messagesEl.innerHTML = '';
  if (!appState.messages.length) {
    messagesEl.appendChild(emptyStateTemplate.cloneNode(true));
  } else {
    appState.messages.forEach(m => messagesEl.appendChild(renderMessageNode(m)));
  }
  scrollToBottom();
}
function rerenderMessage(msg) {
  const node = messagesEl.querySelector(`.msg[data-id="${msg.id}"]`);
  if (node) node.replaceWith(renderMessageNode(msg));
}
function findMessage(id) {
  return appState.messages.find(m => String(m.id) === String(id));
}
function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showTyping() {
  const node = document.createElement('div');
  node.className = 'msg msg--ai typing';
  node.id = 'typingIndicator';
  node.innerHTML = '<div class="msg-bubble"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>';
  messagesEl.appendChild(node);
  scrollToBottom();
}
function hideTyping() {
  const node = document.getElementById('typingIndicator');
  if (node) node.remove();
}

/* ---------------- Rendering: trip summary panel ---------------- */

const tripSummaryEl = document.getElementById('tripSummary');

function renderTripSummary(it) {
  appState.rightViewMode = 'summary';
  if (!it) {
    tripSummaryEl.innerHTML = '<p class="rail-empty">Start a conversation to build your trip summary here.</p>';
    return;
  }
  tripSummaryEl.innerHTML = `
    <div class="summary-row">${ICONS.pin}<div><span class="label">Destination</span><strong>${it.destination}</strong></div></div>
    <div class="summary-row">${ICONS.calendar}<div><span class="label">Duration</span><strong>${it.days} day${it.days > 1 ? 's' : ''}</strong></div></div>
    <div class="summary-row">${ICONS.people}<div><span class="label">Travelers</span><strong>${it.travelers} ${it.travelers > 1 ? 'people' : 'person'}</strong></div></div>
    <div class="summary-row"><span class="budget-pill">₹${inr(it.budget)} estimated</span></div>
    <div class="summary-divider"></div>
    <div class="weather-row">${weatherIcon(it.weather.cond)}<div><span class="weather-temp">${it.weather.temp}°C</span><br><span class="weather-cond">${it.weather.cond}</span></div></div>
    <div class="tag-group">${it.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>
    <p class="summary-note">Balanced by the Budget and Weather agents to match what you asked for. Ask for changes anytime and I'll only replan what's affected.</p>
  `;
}

function renderSavedListView() {
  appState.rightViewMode = 'list';
  if (!appState.savedTrips.length) {
    tripSummaryEl.innerHTML = '<p class="rail-empty">No saved trips yet. Tap "Save trip" on a plan to keep it here.</p>';
    return;
  }
  tripSummaryEl.innerHTML = appState.savedTrips.map(t => `
    <button class="saved-list-item" data-trip-key="${t.tripKey}">
      <strong>${t.destination}</strong>
      <span>${t.days} days, ₹${inr(t.budget)}</span>
    </button>`).join('');
  tripSummaryEl.querySelectorAll('.saved-list-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const trip = appState.savedTrips.find(t => t.tripKey === btn.dataset.tripKey);
      if (trip) renderTripSummary(trip);
    });
  });
}

/* ---------------- Rendering: history rail ---------------- */

const historyListEl = document.getElementById('historyList');
const historyEmptyEl = document.getElementById('historyEmpty');

function renderHistory() {
  historyListEl.innerHTML = '';
  historyEmptyEl.style.display = appState.history.length ? 'none' : 'block';
  appState.history.forEach(h => {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'history-item';
    btn.textContent = h.title;
    btn.addEventListener('click', () => {
      appState.messages = JSON.parse(JSON.stringify(h.messages));
      const withItinerary = [...appState.messages].reverse().find(m => m.itinerary);
      appState.currentItinerary = withItinerary ? withItinerary.itinerary : null;
      renderAllMessages();
      renderTripSummary(appState.currentItinerary);
      closeMobileRails();
    });
    li.appendChild(btn);
    historyListEl.appendChild(li);
  });
}

/* ---------------- Saving trips ---------------- */

function isTripSaved(it) {
  return appState.savedTrips.some(t => t.tripKey === it.tripKey);
}
function toggleSaveTrip(it) {
  const idx = appState.savedTrips.findIndex(t => t.tripKey === it.tripKey);
  if (idx > -1) appState.savedTrips.splice(idx, 1);
  else appState.savedTrips.push(JSON.parse(JSON.stringify(it)));
  persist('saved');
  if (appState.rightViewMode === 'list') renderSavedListView();
}

/* ---------------- Sending a message ---------------- */

function handleUserMessage(rawText) {
  const text = (rawText || '').trim();
  if (!text) return;

  appState.messages.push({ id: cryptoId(), role: 'user', text });
  renderAllMessages();
  showTyping();

  setTimeout(() => {
    hideTyping();
    const details = parseTripDetails(text);
    const itinerary = buildItinerary(details);
    itinerary.tripKey = `${itinerary.destination}|${itinerary.days}|${itinerary.travelers}`;
    appState.messages.push({ id: cryptoId(), role: 'ai', text: generateReplyText(details), itinerary });
    appState.currentItinerary = itinerary;
    renderAllMessages();
    renderTripSummary(itinerary);
  }, 650 + Math.random() * 500);
}

/* ---------------- Toast ---------------- */

function showToast(msg) {
  let toast = document.getElementById('tmToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'tmToast';
    Object.assign(toast.style, {
      position: 'fixed', left: '50%', bottom: '28px', transform: 'translateX(-50%) translateY(20px)',
      background: '#262738', color: '#EAF3EE', border: '1px solid #34364a', padding: '10px 18px',
      borderRadius: '10px', fontFamily: "'League Spartan', sans-serif", fontWeight: '500', fontSize: '13px',
      opacity: '0', transition: 'opacity .2s, transform .2s', zIndex: '999', pointerEvents: 'none'
    });
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  requestAnimationFrame(() => { toast.style.opacity = '1'; toast.style.transform = 'translateX(-50%) translateY(0)'; });
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(20px)';
  }, 2200);
}

/* ---------------- Mobile rails ---------------- */

function openRail(side) {
  document.getElementById(side === 'left' ? 'railLeft' : 'railRight').classList.add('open');
  document.getElementById('scrim').classList.add('open');
  document.getElementById(side === 'left' ? 'leftToggle' : 'rightToggle').setAttribute('aria-expanded', 'true');
}
function closeMobileRails() {
  document.getElementById('railLeft').classList.remove('open');
  document.getElementById('railRight').classList.remove('open');
  document.getElementById('scrim').classList.remove('open');
  document.getElementById('leftToggle').setAttribute('aria-expanded', 'false');
  document.getElementById('rightToggle').setAttribute('aria-expanded', 'false');
}

/* ---------------- Event wiring ---------------- */

const composerForm = document.getElementById('composerForm');
const composerInput = document.getElementById('composerInput');

composerForm.addEventListener('submit', e => {
  e.preventDefault();
  const val = composerInput.value;
  composerInput.value = '';
  composerInput.style.height = 'auto';
  handleUserMessage(val);
});
composerInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    composerForm.requestSubmit();
  }
});
composerInput.addEventListener('input', () => {
  composerInput.style.height = 'auto';
  composerInput.style.height = Math.min(composerInput.scrollHeight, 140) + 'px';
});

messagesEl.addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if (chip) { handleUserMessage(chip.dataset.fill); return; }

  const tab = e.target.closest('.day-tab');
  if (tab) {
    const msg = findMessage(tab.closest('.itinerary-card').dataset.msgId);
    if (msg) { msg.itinerary.activeDay = Number(tab.dataset.day); rerenderMessage(msg); }
    return;
  }

  const viewBtn = e.target.closest('.ghost-btn');
  if (viewBtn) {
    const msg = findMessage(viewBtn.closest('.itinerary-card').dataset.msgId);
    if (msg) { msg.itinerary.expanded = !msg.itinerary.expanded; rerenderMessage(msg); }
    return;
  }

  const saveBtn = e.target.closest('.save-btn');
  if (saveBtn) {
    const msg = findMessage(saveBtn.closest('.itinerary-card').dataset.msgId);
    if (msg) { toggleSaveTrip(msg.itinerary); rerenderMessage(msg); }
  }
});

document.getElementById('newChatBtn').addEventListener('click', () => {
  if (appState.messages.length) {
    const firstUser = appState.messages.find(m => m.role === 'user');
    appState.history.unshift({
      id: cryptoId(),
      title: firstUser ? firstUser.text.slice(0, 42) : 'New trip',
      messages: JSON.parse(JSON.stringify(appState.messages))
    });
    appState.history = appState.history.slice(0, 12);
    persist('history');
    renderHistory();
  }
  appState.messages = [];
  appState.currentItinerary = null;
  renderAllMessages();
  renderTripSummary(null);
  closeMobileRails();
});

document.querySelectorAll('[data-view]').forEach(el => {
  el.addEventListener('click', () => {
    const view = el.dataset.view;
    if (el.classList.contains('rail-item')) {
      document.querySelectorAll('.rail-item[data-view]').forEach(b => b.classList.remove('active'));
      el.classList.add('active');
    }
    if (view === 'trips' || view === 'saved') {
      renderSavedListView();
      if (window.innerWidth <= 940) openRail('right');
    } else if (view === 'explore') {
      showToast('Explore is coming soon.');
    } else if (view === 'prefs') {
      showToast('Preferences are coming soon.');
    }
  });
});

document.getElementById('leftToggle').addEventListener('click', () => openRail('left'));
document.getElementById('rightToggle').addEventListener('click', () => openRail('right'));
document.getElementById('scrim').addEventListener('click', closeMobileRails);

/* ---------------- Init ---------------- */

loadPersisted();
renderHistory();
renderAllMessages();
renderTripSummary(null);