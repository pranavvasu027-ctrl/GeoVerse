let currentDataset = 't1';
let currentSamples = [];
let currentIndex = 0;
let currentEpoch = 2020;
let currentSampleData = { epochs: {} };
let unsavedChanges = false;
let verifiedImageryConfig = {};
let isMultiEpochView = false;

// Leaflet Map & Layers
const map = L.map('map').setView([18.5204, 73.8567], 12);

const esriLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Tiles &copy; Esri &mdash; Modern Context',
  maxZoom: 19
});

const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 19
});

let landsatLayer = null;
let currentBaseLayer = null;
let polygonLayer = null;
let markerLayer = null;

// Multi-Epoch Maps
let subMaps = {};

document.addEventListener('DOMContentLoaded', async () => {
  await fetchImageryConfig();
  setupEventListeners();
  loadDataset(currentDataset);
});

async function fetchImageryConfig() {
  try {
    const res = await fetch('/api/imagery');
    verifiedImageryConfig = await res.json();
  } catch (err) {
    console.error('Failed to load verified imagery config:', err);
  }
}

function setupEventListeners() {
  // Dataset change
  document.getElementById('datasetSelect').addEventListener('change', (e) => {
    if (unsavedChanges && !confirm('You have unsaved changes. Discard and switch dataset?')) {
      e.target.value = currentDataset;
      return;
    }
    currentDataset = e.target.value;
    loadDataset(currentDataset);
  });

  // Epoch tabs
  document.querySelectorAll('.epoch-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const targetEp = parseInt(tab.dataset.epoch);
      if (targetEp === currentEpoch) return;
      document.querySelectorAll('.epoch-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentEpoch = targetEp;
      updateFormView();
      updateMapHistoricalLayer();
    });
  });

  // Basemap switcher
  document.querySelectorAll('input[name="layerMode"]').forEach(radio => {
    radio.addEventListener('change', () => {
      updateMapHistoricalLayer();
    });
  });

  // Zoom controls
  document.getElementById('zoomCellBtn').addEventListener('click', zoomToCell);
  document.getElementById('zoomNeighborhoodBtn').addEventListener('click', zoomToNeighborhood);

  // Navigation
  document.getElementById('prevSampleBtn').addEventListener('click', () => navigateSample(-1));
  document.getElementById('nextSampleBtn').addEventListener('click', () => navigateSample(1));

  // Search filter
  document.getElementById('searchIdInput').addEventListener('input', renderSampleList);
  document.getElementById('statusFilter').addEventListener('change', renderSampleList);

  // Copy coordinates
  document.getElementById('copyCoordBtn').addEventListener('click', () => {
    const sample = currentSamples[currentIndex];
    if (sample) {
      navigator.clipboard.writeText(`${sample.lat}, ${sample.lon}`);
      showFeedback('Coordinates copied for Google Earth Pro!', 'success');
    }
  });

  // Form submission
  document.getElementById('annotationForm').addEventListener('submit', (e) => {
    e.preventDefault();
    saveCurrentEpoch();
  });

  // Keyboard shortcut: Ctrl + S to save
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault();
      saveCurrentEpoch();
    }
  });

  // Track unsaved changes on input
  document.querySelectorAll('#annotationForm input, #annotationForm select, #annotationForm textarea').forEach(el => {
    el.addEventListener('input', () => {
      unsavedChanges = true;
      const statusBadge = document.getElementById('epochStatusTag');
      statusBadge.textContent = 'Unsaved Changes';
      statusBadge.className = 'status-badge unsaved';
    });
  });

  // Dynamic status field adjustments
  document.getElementById('statusSelect').addEventListener('change', (e) => {
    const val = e.target.value;
    const isDone = val === 'done';
    document.getElementById('dominantClassGroup').style.display = (val === 'skipped') ? 'none' : 'flex';
    document.getElementById('shareGroup').style.display = isDone ? 'flex' : 'none';
    document.getElementById('secondClassGroup').style.display = isDone ? 'flex' : 'none';
    document.getElementById('confidenceGroup').style.display = isDone ? 'flex' : 'none';
  });

  // Export
  document.getElementById('exportBtn').addEventListener('click', exportDatasetCSV);

  // Multi-epoch toggle
  document.getElementById('toggleCompareBtn').addEventListener('click', toggleMultiEpochView);

  // QC modal toggle
  document.getElementById('toggleQcBtn').addEventListener('click', openQcModal);
  document.getElementById('closeQcModalBtn').addEventListener('click', closeQcModal);
}

async function loadDataset(dataset) {
  try {
    const res = await fetch(`/api/manifest?dataset=${dataset}`);
    const data = await res.json();
    currentSamples = data.items || [];
    currentIndex = 0;
    renderSampleList();
    if (currentSamples.length > 0) {
      selectSample(0);
    }
    updateProgressStats();
  } catch (err) {
    console.error('Failed to load dataset:', err);
    showFeedback('Failed to load manifest.', 'error');
  }
}

function renderSampleList() {
  const listEl = document.getElementById('sampleList');
  listEl.innerHTML = '';

  const searchVal = document.getElementById('searchIdInput').value.toLowerCase();
  const filterVal = document.getElementById('statusFilter').value;

  currentSamples.forEach((s, idx) => {
    if (searchVal && !s.anon_id.toLowerCase().includes(searchVal)) return;
    if (filterVal !== 'all' && s.status !== filterVal) return;

    const item = document.createElement('div');
    item.className = `sample-item ${idx === currentIndex ? 'active' : ''}`;
    item.innerHTML = `
      <span><strong>${s.anon_id}</strong> (${s.done_epochs || 0}/4)</span>
      <span class="status-indicator ${s.status}">${s.status}</span>
    `;
    item.addEventListener('click', () => {
      if (unsavedChanges && !confirm('You have unsaved changes. Discard and navigate?')) return;
      selectSample(idx);
    });
    listEl.appendChild(item);
  });
}

async function selectSample(idx) {
  if (idx < 0 || idx >= currentSamples.length) return;
  currentIndex = idx;
  unsavedChanges = false;
  const sample = currentSamples[currentIndex];

  document.getElementById('currentSampleBadge').textContent = sample.anon_id;
  document.getElementById('currentCoordTag').textContent = `Lat: ${sample.lat.toFixed(5)}, Lon: ${sample.lon.toFixed(5)}`;
  document.getElementById('currentIndexDisplay').textContent = `${currentIndex + 1} / ${currentSamples.length}`;

  // Update Main Map Marker and Target Cell
  if (markerLayer) map.removeLayer(markerLayer);
  if (polygonLayer) map.removeLayer(polygonLayer);

  markerLayer = L.circleMarker([sample.lat, sample.lon], {
    radius: 4,
    color: '#38bdf8',
    fillColor: '#0284c7',
    fillOpacity: 1
  }).addTo(map);

  if (sample.polygon && sample.polygon.length > 0) {
    polygonLayer = L.polygon(sample.polygon, {
      color: '#facc15',
      weight: 3,
      fillColor: '#fef08a',
      fillOpacity: 0.25
    }).addTo(map);
    zoomToCell();
  } else {
    map.setView([sample.lat, sample.lon], 17);
  }

  // Load sample annotations
  try {
    const res = await fetch(`/api/annotation/${currentDataset}/${sample.anon_id}`);
    currentSampleData = await res.json();
    if (!currentSampleData.epochs) currentSampleData.epochs = {};
    updateFormView();
    updateTrajectoryAssistant();
  } catch (err) {
    console.error('Error loading annotation:', err);
    currentSampleData = { epochs: {} };
    updateFormView();
    updateTrajectoryAssistant();
  }

  updateMapHistoricalLayer();
  if (isMultiEpochView) updateMultiEpochSubmaps();
  renderSampleList();
}

function zoomToCell() {
  if (polygonLayer) {
    map.fitBounds(polygonLayer.getBounds(), { maxZoom: 18, padding: [60, 60] });
  } else {
    const sample = currentSamples[currentIndex];
    if (sample) map.setView([sample.lat, sample.lon], 18);
  }
}

function zoomToNeighborhood() {
  const sample = currentSamples[currentIndex];
  if (sample) map.setView([sample.lat, sample.lon], 15);
}

function updateMapHistoricalLayer() {
  const mode = document.querySelector('input[name="layerMode"]:checked').value;
  const pill = document.getElementById('historicalPill');
  const pillText = document.getElementById('historicalPillText');

  if (landsatLayer) map.removeLayer(landsatLayer);
  if (currentBaseLayer) map.removeLayer(currentBaseLayer);

  if (mode === 'landsat') {
    const imgInfo = verifiedImageryConfig[currentEpoch];
    if (imgInfo && imgInfo.tile_url) {
      landsatLayer = L.tileLayer(imgInfo.tile_url, { maxZoom: 18, attribution: 'USGS/NASA Landsat' }).addTo(map);
      pill.className = 'historical-pill verified';
      pillText.innerHTML = `<strong>Verified ${imgInfo.sensor}:</strong> ${imgInfo.acquisition_date}`;
      pill.style.display = 'flex';
    } else {
      currentBaseLayer = osmLayer.addTo(map);
      pill.className = 'historical-pill context';
      pillText.innerHTML = `Historical Landsat not mapped for ${currentEpoch}`;
      pill.style.display = 'flex';
    }
  } else if (mode === 'esri') {
    currentBaseLayer = esriLayer.addTo(map);
    pill.className = 'historical-pill context';
    pillText.innerHTML = '<strong>Modern Satellite:</strong> Spatial context only (NOT historical)';
    pill.style.display = 'flex';
  } else {
    currentBaseLayer = osmLayer.addTo(map);
    pill.className = 'historical-pill context';
    pillText.innerHTML = '<strong>OSM Streets:</strong> Reference context';
    pill.style.display = 'flex';
  }

  if (polygonLayer) polygonLayer.bringToFront();
  if (markerLayer) markerLayer.bringToFront();
}

function updateFormView() {
  document.getElementById('epochTitleDisplay').textContent = `Epoch ${currentEpoch} Annotation`;
  const epKey = String(currentEpoch);
  const data = (currentSampleData.epochs && currentSampleData.epochs[epKey]) || {};
  const imgInfo = verifiedImageryConfig[currentEpoch];

  const statusBadge = document.getElementById('epochStatusTag');
  if (data.status) {
    statusBadge.textContent = `Status: ${data.status}`;
    statusBadge.className = 'status-badge saved';
  } else {
    statusBadge.textContent = 'Unsaved';
    statusBadge.className = 'status-badge empty';
  }

  document.getElementById('statusSelect').value = data.status || 'done';
  document.getElementById('statusSelect').dispatchEvent(new Event('change'));

  document.getElementById('dominantClassSelect').value = data.dominant_class || '';
  document.getElementById('shareSelect').value = data.dominant_share_3bins || '>=75';
  document.getElementById('secondClassSelect').value = data.second_class || 'none';
  document.getElementById('confidenceSelect').value = data.confidence_1to3 || '3';
  
  // Set default imagery source & date from verified Landsat if not already populated
  document.getElementById('imagerySourceSelect').value = data.imagery_source || (imgInfo ? 'Landsat_context' : 'GEP_historical');
  document.getElementById('imageryDateInput').value = data.imagery_date || (imgInfo ? imgInfo.acquisition_date : `${currentEpoch}-03-15`);
  document.getElementById('notesInput').value = data.notes || '';

  hideFeedback();
}

function updateTrajectoryAssistant() {
  const body = document.getElementById('trajectoryBody');
  const alertBadge = document.getElementById('transitionAlertBadge');
  body.innerHTML = '';

  const epochs = [1990, 2000, 2010, 2020];
  const classesRecorded = [];

  epochs.forEach(ep => {
    const epData = (currentSampleData.epochs && currentSampleData.epochs[String(ep)]) || null;
    const row = document.createElement('div');
    row.className = 'trajectory-row';
    if (epData && epData.dominant_class) {
      classesRecorded.push(epData.dominant_class);
      row.innerHTML = `
        <span><strong>${ep}:</strong> ${epData.dominant_class} (${epData.dominant_share_3bins || 'N/A'})</span>
        <span style="color:#86efac;">conf: ${epData.confidence_1to3}/3</span>
      `;
    } else {
      row.innerHTML = `<span><strong>${ep}:</strong> <em style="color:#64748b;">Not annotated</em></span>`;
    }
    body.appendChild(row);
  });

  const uniqueClasses = new Set(classesRecorded.filter(c => !['unavailable', 'uncertain', 'ambiguous'].includes(c)));
  if (uniqueClasses.size > 1) {
    alertBadge.textContent = 'Transition Detected';
    alertBadge.style.background = '#854d0e';
    alertBadge.style.color = '#fde047';
  } else if (uniqueClasses.size === 1) {
    alertBadge.textContent = 'Stable';
    alertBadge.style.background = '#166534';
    alertBadge.style.color = '#86efac';
  } else {
    alertBadge.textContent = 'Pending';
    alertBadge.style.background = '#334155';
    alertBadge.style.color = '#cbd5e1';
  }
}

async function saveCurrentEpoch() {
  const sample = currentSamples[currentIndex];
  if (!sample) return;

  const epKey = String(currentEpoch);
  const status = document.getElementById('statusSelect').value;
  const domClass = document.getElementById('dominantClassSelect').value;
  const share = document.getElementById('shareSelect').value;
  const secondClass = document.getElementById('secondClassSelect').value;
  const conf = parseInt(document.getElementById('confidenceSelect').value) || 2;
  const source = document.getElementById('imagerySourceSelect').value;
  const imgDate = document.getElementById('imageryDateInput').value.trim();
  const notes = document.getElementById('notesInput').value.trim();

  // Client-side pre-validation: scoped strictly to the active epoch being saved
  if (status === 'done') {
    if (!domClass) {
      showFeedback(`Epoch ${currentEpoch}: Please select a Dominant Class before saving.`, 'error');
      document.getElementById('dominantClassSelect').focus();
      return;
    }
    if (source === 'Landsat_context' && conf > 2) {
      showFeedback(`Epoch ${currentEpoch}: Protocol rule: with 'Landsat_context', confidence must be at most 2.`, 'error');
      document.getElementById('confidenceSelect').focus();
      return;
    }
    // Protocol rule: notes are mandatory for 'other' and 'ambiguous' only; 'uncertain' does not require notes
    if ((domClass === 'other' || domClass === 'ambiguous') && !notes) {
      showFeedback(`Epoch ${currentEpoch}: Notes are mandatory when dominant_class is '${domClass}'.`, 'error');
      document.getElementById('notesInput').focus();
      return;
    }
    if (secondClass && secondClass !== 'none' && secondClass === domClass) {
      showFeedback(`Epoch ${currentEpoch}: Secondary Class cannot be identical to Dominant Class.`, 'error');
      document.getElementById('secondClassSelect').focus();
      return;
    }
    if (!imgDate) {
      showFeedback(`Epoch ${currentEpoch}: Acquisition Date (YYYY-MM-DD) is required.`, 'error');
      document.getElementById('imageryDateInput').focus();
      return;
    }
  }

  const payload = {
    status: status,
    dominant_class: domClass,
    dominant_share_3bins: share,
    second_class: secondClass,
    confidence_1to3: conf,
    imagery_source: source,
    imagery_date: imgDate,
    notes: notes
  };

  // Consistent save request: submit specifically the active epoch being validated & saved
  const savePayload = {
    epochs: {
      [epKey]: payload
    }
  };

  try {
    const res = await fetch(`/api/annotation/${currentDataset}/${sample.anon_id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(savePayload)
    });
    const result = await res.json();

    if (!res.ok) {
      let errorMessages = [];
      if (result.errors) {
        // First look for errors on the epoch being validated
        if (result.errors[epKey] && Array.isArray(result.errors[epKey].errors) && result.errors[epKey].errors.length > 0) {
          errorMessages.push(...result.errors[epKey].errors);
        } else {
          for (const [ep, report] of Object.entries(result.errors)) {
            if (report && Array.isArray(report.errors) && report.errors.length > 0) {
              errorMessages.push(...report.errors);
            }
          }
        }
      }
      if (errorMessages.length === 0) {
        errorMessages = [result.error || `Epoch ${currentEpoch}: Validation failed. Please verify required fields.`];
      }
      showFeedback(errorMessages.join('<br>'), 'error');
      return;
    }

    // Merge saved epoch into in-memory sample data
    if (result.epochs) {
      currentSampleData.epochs = result.epochs;
    } else {
      currentSampleData.epochs[epKey] = payload;
    }

    unsavedChanges = false;
    showFeedback(`Epoch ${currentEpoch} saved successfully!`, 'success');
    updateFormView();
    updateTrajectoryAssistant();

    const doneEpochs = Object.values(currentSampleData.epochs).filter(e => e.status === 'done' || e.status === 'unavailable').length;
    sample.done_epochs = doneEpochs;
    sample.status = (doneEpochs === 4) ? 'completed' : (doneEpochs > 0 ? 'in_progress' : 'unlabeled');

    updateProgressStats();
    renderSampleList();

  } catch (err) {
    console.error('Save failed:', err);
    showFeedback(`Epoch ${currentEpoch}: Network or server error while saving.`, 'error');
  }
}

function navigateSample(step) {
  if (unsavedChanges && !confirm('You have unsaved changes. Discard and navigate?')) return;
  const nextIdx = currentIndex + step;
  if (nextIdx >= 0 && nextIdx < currentSamples.length) {
    selectSample(nextIdx);
  }
}

function updateProgressStats() {
  const total = currentSamples.length;
  const completed = currentSamples.filter(s => s.status === 'completed').length;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  document.getElementById('progressText').textContent = `${completed} / ${total} (${pct}%)`;
  document.getElementById('progressBar').style.width = `${pct}%`;
}

// Multi-Epoch Comparison Workspace
function toggleMultiEpochView() {
  isMultiEpochView = !isMultiEpochView;
  const mapContainer = document.getElementById('mapContainer');
  const multiContainer = document.getElementById('multiEpochContainer');
  const btn = document.getElementById('toggleCompareBtn');

  if (isMultiEpochView) {
    mapContainer.style.display = 'none';
    multiContainer.style.display = 'grid';
    btn.innerHTML = '<i class="fa-solid fa-map"></i> Single Map View';
    btn.className = 'btn btn-primary';
    initMultiEpochSubmaps();
  } else {
    multiContainer.style.display = 'none';
    mapContainer.style.display = 'flex';
    btn.innerHTML = '<i class="fa-solid fa-table-cells-large"></i> Multi-Epoch View';
    btn.className = 'btn btn-outline';
    map.invalidateSize();
  }
}

function initMultiEpochSubmaps() {
  const sample = currentSamples[currentIndex];
  if (!sample) return;

  const epochs = [1990, 2000, 2010, 2020];
  epochs.forEach(ep => {
    const elId = `map${ep}`;
    if (!subMaps[ep]) {
      const subMap = L.map(elId, { zoomControl: false }).setView([sample.lat, sample.lon], 16);
      const imgInfo = verifiedImageryConfig[ep];
      if (imgInfo && imgInfo.tile_url) {
        L.tileLayer(imgInfo.tile_url, { maxZoom: 18 }).addTo(subMap);
      } else {
        osmLayer.addTo(subMap);
      }
      if (sample.polygon && sample.polygon.length > 0) {
        L.polygon(sample.polygon, { color: '#facc15', weight: 2 }).addTo(subMap);
      }
      subMaps[ep] = subMap;
    } else {
      subMaps[ep].setView([sample.lat, sample.lon], 16);
      subMaps[ep].invalidateSize();
    }
  });
}

function updateMultiEpochSubmaps() {
  const sample = currentSamples[currentIndex];
  if (!sample) return;
  [1990, 2000, 2010, 2020].forEach(ep => {
    if (subMaps[ep]) {
      subMaps[ep].setView([sample.lat, sample.lon], 16);
    }
  });
}

// Quality Control Modal
async function openQcModal() {
  document.getElementById('qcModal').style.display = 'flex';
  const body = document.getElementById('qcModalBody');
  body.innerHTML = '<p>Loading Quality-Control Analytics...</p>';

  try {
    const res = await fetch(`/api/qc?dataset=${currentDataset}`);
    const qc = await res.json();
    body.innerHTML = `
      <div class="qc-grid">
        <div class="qc-card"><div class="number">${qc.total_samples}</div><div class="label">Total Samples</div></div>
        <div class="qc-card"><div class="number" style="color:#22c55e;">${qc.completed_samples}</div><div class="label">Fully Completed</div></div>
        <div class="qc-card"><div class="number" style="color:#eab308;">${qc.in_progress_samples}</div><div class="label">In Progress</div></div>
        <div class="qc-card"><div class="number" style="color:#94a3b8;">${qc.unlabeled_samples}</div><div class="label">Unlabeled</div></div>
        <div class="qc-card"><div class="number" style="color:#f97316;">${qc.low_confidence_count}</div><div class="label">Weak Confidence (1)</div></div>
        <div class="qc-card"><div class="number" style="color:#ef4444;">${qc.unavailable_count}</div><div class="label">Unavailable Imagery</div></div>
      </div>

      <h4 style="margin-top:10px; font-size:0.85rem; color:#38bdf8;">Epoch Progress Breakdown</h4>
      <table class="epoch-table">
        <thead>
          <tr><th>Epoch</th><th>Done</th><th>Unavailable</th><th>Skipped</th><th>Unlabeled</th></tr>
        </thead>
        <tbody>
          ${[1990, 2000, 2010, 2020].map(ep => `
            <tr>
              <td><strong>${ep}</strong></td>
              <td style="color:#86efac;">${qc.epoch_progress[String(ep)].done}</td>
              <td style="color:#fca5a5;">${qc.epoch_progress[String(ep)].unavailable}</td>
              <td>${qc.epoch_progress[String(ep)].skipped}</td>
              <td>${qc.epoch_progress[String(ep)].unlabeled}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (err) {
    body.innerHTML = '<p style="color:#ef4444;">Failed to calculate QC analytics.</p>';
  }
}

function closeQcModal() {
  document.getElementById('qcModal').style.display = 'none';
}

async function exportDatasetCSV() {
  try {
    const res = await fetch(`/api/export/${currentDataset}`, { method: 'POST' });
    const result = await res.json();
    if (res.ok) {
      alert(`Export Successful!\nSaved to: ${result.export_path}\nCompleted: ${result.summary.fully_labeled}/${result.summary.total_samples}`);
    } else {
      alert(`Export failed: ${result.error || 'Unknown error'}`);
    }
  } catch (err) {
    alert(`Export error: ${err.message}`);
  }
}

function showFeedback(msg, type) {
  const box = document.getElementById('validationFeedback');
  box.className = `feedback-box ${type}`;
  box.innerHTML = msg;
  box.style.display = 'block';
}

function hideFeedback() {
  const box = document.getElementById('validationFeedback');
  box.className = 'feedback-box';
  box.style.display = 'none';
  box.innerHTML = '';
}
