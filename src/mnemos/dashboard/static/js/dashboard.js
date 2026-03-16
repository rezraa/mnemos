/* ======================================================================
   Mnemos Dashboard — Main application logic
   ====================================================================== */

(function () {
  'use strict';

  /* ── State ──────────────────────────────────────────────────────── */
  let ws = null;
  let reconnectTimer = null;
  let currentSection = 'dashboard';
  let currentTimeRange = 'All';

  // Chart instances
  let volumeChart = null;
  let patternDonut = null;
  let heatmapChart = null;
  let accuracyChart = null;
  let dsDonut = null;

  /* ── DOM helpers ────────────────────────────────────────────────── */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function formatTime(ts) {
    if (!ts) return '--';
    const d = new Date(ts);
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return diffMin + 'm ago';
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return diffHr + 'h ago';
    const diffDay = Math.floor(diffHr / 24);
    return diffDay + 'd ago';
  }

  function formatDate(ts) {
    if (!ts) return '--';
    return new Date(ts).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  function badge(text, cls) {
    return '<span class="badge badge-' + cls + '">' + text + '</span>';
  }

  function showEmpty(id, show) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('visible', show);
  }

  /* ── API fetch helper ───────────────────────────────────────────── */
  async function api(path, params) {
    let url = '/api' + path;
    if (params) {
      const qs = new URLSearchParams(params).toString();
      if (qs) url += '?' + qs;
    }
    try {
      const resp = await fetch(url);
      return await resp.json();
    } catch (err) {
      console.error('API error:', path, err);
      return null;
    }
  }

  /* ── WebSocket ──────────────────────────────────────────────────── */
  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(proto + '//' + location.host + '/ws/live');

    ws.onopen = function () {
      setWSStatus('connected');
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    ws.onmessage = function (event) {
      try {
        const msg = JSON.parse(event.data);
        handleLiveEvent(msg);
      } catch (e) {
        // ignore non-JSON
      }
    };

    ws.onclose = function () {
      setWSStatus('disconnected');
      scheduleReconnect();
    };

    ws.onerror = function () {
      setWSStatus('disconnected');
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(function () {
      reconnectTimer = null;
      connectWS();
    }, 3000);
  }

  function setWSStatus(state) {
    const dot = $('.ws-dot');
    const label = $('.ws-label');
    if (!dot || !label) return;

    dot.className = 'ws-dot ' + state;
    if (state === 'connected') {
      label.textContent = 'Connected';
    } else if (state === 'disconnected') {
      label.textContent = 'Reconnecting...';
    } else {
      label.textContent = 'Connecting...';
    }
  }

  /* ── Live event handler ─────────────────────────────────────────── */
  function handleLiveEvent(msg) {
    // Add to activity feed
    addActivityItem(msg);

    // Refresh KPIs
    loadStats();

    // If on dashboard, refresh decisions table
    if (currentSection === 'dashboard') {
      loadRecentDecisions();
    }
  }

  function addActivityItem(msg) {
    const feed = $('#activityFeed');
    if (!feed) return;

    // Remove empty state
    const empty = feed.querySelector('.empty-state');
    if (empty) empty.remove();

    const type = msg.type || 'decision';
    const text = msg.summary || msg.description || JSON.stringify(msg);
    const time = msg.timestamp || new Date().toISOString();

    const item = document.createElement('div');
    item.className = 'activity-item';
    item.innerHTML =
      '<div class="activity-dot ' + type + '"></div>' +
      '<div>' +
        '<div class="activity-text">' + escapeHtml(text) + '</div>' +
        '<div class="activity-time">' + formatTime(time) + '</div>' +
      '</div>';

    feed.insertBefore(item, feed.firstChild);

    // Keep max 50 items
    while (feed.children.length > 50) {
      feed.removeChild(feed.lastChild);
    }
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ── Navigation ─────────────────────────────────────────────────── */
  function initNav() {
    $$('.nav-item').forEach(function (item) {
      item.addEventListener('click', function (e) {
        e.preventDefault();
        const section = this.dataset.section;
        if (!section) return;
        switchSection(section);
      });
    });
  }

  function switchSection(section) {
    currentSection = section;

    // Update nav
    $$('.nav-item').forEach(function (item) {
      item.classList.toggle('active', item.dataset.section === section);
    });

    // Update sections
    $$('.content-section').forEach(function (sec) {
      sec.classList.toggle('active', sec.id === 'section-' + section);
    });

    // Update title
    const titles = {
      dashboard: 'Dashboard',
      decisions: 'Decision History',
      patterns: 'Pattern Analytics',
      projects: 'Projects',
      memory: 'Memory & Health',
    };
    setText('pageTitle', titles[section] || 'Dashboard');

    // Load section data
    loadSectionData(section);
  }

  function loadSectionData(section) {
    switch (section) {
      case 'dashboard':
        loadStats();
        loadRecentDecisions();
        loadCharts();
        break;
      case 'decisions':
        loadFullDecisions();
        break;
      case 'patterns':
        loadPatterns();
        break;
      case 'projects':
        loadProjects();
        break;
      case 'memory':
        loadMemoryHealth();
        break;
    }
  }

  /* ── Time range ─────────────────────────────────────────────────── */
  function initTimeRange() {
    $$('.time-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        $$('.time-btn').forEach(function (b) { b.classList.remove('active'); });
        this.classList.add('active');
        currentTimeRange = this.dataset.range;
        loadSectionData(currentSection);
      });
    });
  }

  /* ── Load stats (KPI) ──────────────────────────────────────────── */
  async function loadStats() {
    const data = await api('/stats', { time_range: currentTimeRange });
    if (!data) return;

    setText('kpiTotal', data.total_decisions || 0);
    setText('kpiAccuracy', (data.accuracy_rate || 0) + '%');
    setText('kpiRegressions', data.regressions_avoided || 0);
    setText('kpiProjects', data.active_projects || 0);
    setText('kpiResponseTime', (data.avg_response_ms || 0) + ' ms');

    // Trend indicators
    if (data.total_decisions > 0) {
      setTrend('kpiAccuracyTrend', data.accuracy_rate, 50);
    }
  }

  function setTrend(id, value, baseline) {
    const el = document.getElementById(id);
    if (!el) return;
    const diff = value - baseline;
    if (diff > 0) {
      el.className = 'kpi-trend up';
      el.textContent = '+' + diff.toFixed(1) + '%';
    } else if (diff < 0) {
      el.className = 'kpi-trend down';
      el.textContent = diff.toFixed(1) + '%';
    } else {
      el.className = 'kpi-trend neutral';
      el.textContent = '--';
    }
  }

  /* ── Recent decisions table (dashboard) ─────────────────────────── */
  async function loadRecentDecisions() {
    const data = await api('/decisions', { time_range: currentTimeRange, limit: 10 });
    if (!data) return;

    const tbody = $('#decisionsBody');
    if (!tbody) return;

    tbody.innerHTML = '';
    const items = data.items || [];
    showEmpty('decisionsEmpty', items.length === 0);

    items.forEach(function (d) {
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + formatTime(d.timestamp) + '</td>' +
        '<td>' + escapeHtml(d.pattern_chosen || '--') + '</td>' +
        '<td>' + escapeHtml(d.ds_chosen || '--') + '</td>' +
        '<td>' + badge(d.mode || '--', d.mode || 'plan') + '</td>' +
        '<td>' + badge(d.outcome || '--', d.outcome || 'accepted') + '</td>' +
        '<td>' + escapeHtml(d.project_id || '--') + '</td>';
      tbody.appendChild(tr);
    });
  }

  /* ── Full decisions table ───────────────────────────────────────── */
  async function loadFullDecisions() {
    const outcome = ($('#decFilterOutcome') || {}).value || '';
    const pattern = ($('#decFilterPattern') || {}).value || '';

    const params = { time_range: currentTimeRange, limit: 100 };
    if (outcome) params.outcome = outcome;
    if (pattern) params.pattern = pattern;

    const data = await api('/decisions', params);
    if (!data) return;

    const tbody = $('#fullDecisionsBody');
    if (!tbody) return;

    tbody.innerHTML = '';
    const items = data.items || [];
    showEmpty('fullDecisionsEmpty', items.length === 0);

    items.forEach(function (d) {
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td style="font-family: var(--font-mono); font-size: 11px;">' + escapeHtml(d.id || '--') + '</td>' +
        '<td>' + formatDate(d.timestamp) + '</td>' +
        '<td title="' + escapeHtml(d.problem_description || '') + '">' + escapeHtml((d.problem_description || '--').substring(0, 40)) + '</td>' +
        '<td>' + escapeHtml(d.pattern_chosen || '--') + '</td>' +
        '<td>' + escapeHtml(d.ds_chosen || '--') + '</td>' +
        '<td>' + badge(d.mode || '--', d.mode || 'plan') + '</td>' +
        '<td>' + badge(d.outcome || '--', d.outcome || 'accepted') + '</td>' +
        '<td>' + escapeHtml(d.project_id || '--') + '</td>';
      tbody.appendChild(tr);
    });

    // Populate pattern filter from data
    populatePatternFilter(items);
  }

  function populatePatternFilter(items) {
    const sel = $('#decFilterPattern');
    if (!sel || sel.options.length > 1) return;
    const patterns = new Set();
    items.forEach(function (d) {
      if (d.pattern_chosen) patterns.add(d.pattern_chosen);
    });
    patterns.forEach(function (p) {
      const opt = document.createElement('option');
      opt.value = p;
      opt.textContent = p;
      sel.appendChild(opt);
    });
  }

  function initDecisionFilters() {
    const outcomeEl = $('#decFilterOutcome');
    const patternEl = $('#decFilterPattern');
    if (outcomeEl) outcomeEl.addEventListener('change', loadFullDecisions);
    if (patternEl) patternEl.addEventListener('change', loadFullDecisions);
  }

  /* ── Charts ─────────────────────────────────────────────────────── */
  async function loadCharts() {
    const [decisions, patterns] = await Promise.all([
      api('/decisions', { time_range: currentTimeRange, limit: 500 }),
      api('/patterns', { time_range: currentTimeRange }),
    ]);

    // Build volume chart data
    const volumeData = buildVolumeData(decisions ? decisions.items : []);
    volumeChart = renderVolumeChart('volumeChart', volumeData);

    // Pattern distribution donut
    const dsDistrib = (patterns && patterns.ds_distribution) || {};
    patternDonut = renderPatternDistribution('patternDonut', dsDistrib);

    // Heatmap
    const heatmapData = buildHeatmapData(decisions ? decisions.items : []);
    heatmapChart = renderHeatmap('heatmapChart', heatmapData);
  }

  function buildVolumeData(items) {
    // Group by date and mode
    const dateMap = {};
    items.forEach(function (d) {
      const date = (d.timestamp || '').substring(0, 10);
      if (!date) return;
      if (!dateMap[date]) dateMap[date] = { plan: 0, review: 0, maintain: 0 };
      const mode = d.mode || 'plan';
      dateMap[date][mode] = (dateMap[date][mode] || 0) + 1;
    });

    const dates = Object.keys(dateMap).sort();
    return {
      dates: dates,
      plan: dates.map(function (d) { return dateMap[d].plan; }),
      review: dates.map(function (d) { return dateMap[d].review; }),
      maintain: dates.map(function (d) { return dateMap[d].maintain; }),
    };
  }

  function buildHeatmapData(items) {
    // pattern x ds matrix
    const matrix = {};
    const allDS = new Set();
    items.forEach(function (d) {
      const pat = d.pattern_chosen || 'unknown';
      const ds = d.ds_chosen || 'unknown';
      allDS.add(ds);
      if (!matrix[pat]) matrix[pat] = {};
      matrix[pat][ds] = (matrix[pat][ds] || 0) + 1;
    });

    const dsList = Array.from(allDS).sort();
    const series = Object.keys(matrix).map(function (pat) {
      return {
        name: pat,
        data: dsList.map(function (ds) {
          return { x: ds, y: matrix[pat][ds] || 0 };
        }),
      };
    });

    return { series: series };
  }

  /* ── Patterns section ───────────────────────────────────────────── */
  async function loadPatterns() {
    const [patterns, decisions] = await Promise.all([
      api('/patterns', { time_range: currentTimeRange }),
      api('/decisions', { time_range: currentTimeRange, limit: 500 }),
    ]);

    if (!patterns) return;

    // Accuracy trend chart
    const accuracyData = buildAccuracyTrend(decisions ? decisions.items : []);
    accuracyChart = renderAccuracyTrend('accuracyTrendChart', accuracyData);

    // DS donut
    dsDonut = renderPatternDistribution('dsDonut', patterns.ds_distribution || {});

    // Pattern performance table
    const tbody = $('#patternsBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const usage = patterns.pattern_usage || {};
    const outcomes = patterns.pattern_outcomes || {};
    const patternNames = Object.keys(usage);

    showEmpty('patternsEmpty', patternNames.length === 0);

    patternNames.forEach(function (pat) {
      const total = usage[pat] || 0;
      const o = outcomes[pat] || {};
      const acc = o.accepted || 0;
      const rej = o.rejected || 0;
      const reg = o.regressed || 0;
      const accuracy = total > 0 ? ((acc / total) * 100).toFixed(1) : '0.0';

      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td><strong>' + escapeHtml(pat) + '</strong></td>' +
        '<td>' + total + '</td>' +
        '<td style="color: var(--accent-green);">' + acc + '</td>' +
        '<td style="color: var(--accent-red);">' + rej + '</td>' +
        '<td style="color: var(--accent-yellow);">' + reg + '</td>' +
        '<td>' + accuracy + '%</td>';
      tbody.appendChild(tr);
    });
  }

  function buildAccuracyTrend(items) {
    // Compute running accuracy by date
    const dateMap = {};
    items.forEach(function (d) {
      const date = (d.timestamp || '').substring(0, 10);
      if (!date) return;
      if (!dateMap[date]) dateMap[date] = { accepted: 0, total: 0 };
      dateMap[date].total++;
      if (d.outcome === 'accepted') dateMap[date].accepted++;
    });

    const dates = Object.keys(dateMap).sort();
    let runAcc = 0;
    let runTotal = 0;
    const values = dates.map(function (d) {
      runAcc += dateMap[d].accepted;
      runTotal += dateMap[d].total;
      return runTotal > 0 ? parseFloat(((runAcc / runTotal) * 100).toFixed(1)) : 0;
    });

    return { dates: dates, values: values };
  }

  /* ── Projects section ───────────────────────────────────────────── */
  async function loadProjects() {
    const data = await api('/projects');
    if (!data) return;

    const tbody = $('#projectsBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const items = data.items || [];
    showEmpty('projectsEmpty', items.length === 0);

    items.forEach(function (p) {
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td><strong>' + escapeHtml(p.project_id || '--') + '</strong></td>' +
        '<td>' + escapeHtml(p.language || '--') + '</td>' +
        '<td>' + (p.total_decisions || 0) + '</td>' +
        '<td>' + (p.structures_count || 0) + '</td>' +
        '<td>' + (p.patterns_count || 0) + '</td>' +
        '<td>' + formatTime(p.last_updated) + '</td>';
      tbody.appendChild(tr);
    });
  }

  /* ── Memory & Health section ────────────────────────────────────── */
  async function loadMemoryHealth() {
    const [health, coverage, regressions, corrections] = await Promise.all([
      api('/memory/health'),
      api('/knowledge/coverage'),
      api('/regressions', { time_range: currentTimeRange }),
      api('/corrections', { time_range: currentTimeRange }),
    ]);

    if (health) {
      setText('memHealth', health.health_status || '--');
      setText('memDecisions', health.decisions_count || 0);
      setText('memRegressions', health.regressions_count || 0);
      setText('memCorrections', health.corrections_count || 0);

      const healthEl = $('#memHealth');
      if (healthEl) {
        healthEl.style.color = health.health_status === 'healthy'
          ? 'var(--accent-green)' : 'var(--accent-yellow)';
      }
    }

    // Coverage grid
    if (coverage) {
      const grid = $('#coverageGrid');
      if (grid) {
        grid.innerHTML = '';
        const decPat = coverage.decision_patterns || {};
        const decDS = coverage.decision_ds || {};

        let hasData = false;

        Object.keys(decPat).forEach(function (p) {
          hasData = true;
          const div = document.createElement('div');
          div.className = 'coverage-item';
          div.innerHTML =
            '<div class="coverage-item-label">Pattern: ' + escapeHtml(p) + '</div>' +
            '<div class="coverage-item-value">' + decPat[p] + ' uses</div>';
          grid.appendChild(div);
        });

        Object.keys(decDS).forEach(function (ds) {
          hasData = true;
          const div = document.createElement('div');
          div.className = 'coverage-item';
          div.innerHTML =
            '<div class="coverage-item-label">DS: ' + escapeHtml(ds) + '</div>' +
            '<div class="coverage-item-value">' + decDS[ds] + ' uses</div>';
          grid.appendChild(div);
        });

        showEmpty('coverageEmpty', !hasData);
      }
    }

    // Regressions table
    if (regressions) {
      const tbody = $('#regressionsBody');
      if (tbody) {
        tbody.innerHTML = '';
        const items = regressions.items || [];
        showEmpty('regressionsEmpty', items.length === 0);

        items.forEach(function (r) {
          const tr = document.createElement('tr');
          tr.innerHTML =
            '<td>' + formatTime(r.timestamp) + '</td>' +
            '<td>' + escapeHtml(r.pattern || '--') + '</td>' +
            '<td>' + escapeHtml(r.ds || '--') + '</td>' +
            '<td>' + badge(r.severity || 'medium', r.severity || 'medium') + '</td>' +
            '<td title="' + escapeHtml(r.description || '') + '">' + escapeHtml((r.description || '--').substring(0, 50)) + '</td>' +
            '<td>' + escapeHtml(r.project_id || '--') + '</td>';
          tbody.appendChild(tr);
        });
      }
    }

    // Corrections table
    if (corrections) {
      const tbody = $('#correctionsBody');
      if (tbody) {
        tbody.innerHTML = '';
        const items = corrections.items || [];
        showEmpty('correctionsEmpty', items.length === 0);

        items.forEach(function (c) {
          const tr = document.createElement('tr');
          tr.innerHTML =
            '<td>' + formatTime(c.timestamp) + '</td>' +
            '<td>' + escapeHtml(c.original_pattern || '--') + '</td>' +
            '<td>' + escapeHtml(c.corrected_pattern || '--') + '</td>' +
            '<td title="' + escapeHtml(c.reason || '') + '">' + escapeHtml((c.reason || '--').substring(0, 40)) + '</td>';
          tbody.appendChild(tr);
        });
      }
    }
  }

  /* ── Init ────────────────────────────────────────────────────────── */
  function init() {
    initNav();
    initTimeRange();
    initDecisionFilters();
    connectWS();
    loadSectionData('dashboard');

    // Periodic refresh every 30 seconds
    setInterval(function () {
      loadSectionData(currentSection);
    }, 30000);
  }

  // Start when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
