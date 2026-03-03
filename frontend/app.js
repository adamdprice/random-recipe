(function () {
  const API = '/api';
  var staffCache = [];
  var lastPauseLeadsOptions = [];

  function parseJsonResponse(res) {
    return res.text().then(function (text) {
      var ct = (res.headers.get('content-type') || '').toLowerCase();
      if (ct.indexOf('application/json') !== -1) return JSON.parse(text);
      if (text.trimStart().indexOf('<') === 0) {
        var onLocalhost = /^localhost$|^127\.0\.0\.1$/.test(window.location.hostname);
        throw new Error(onLocalhost
          ? 'Server returned HTML instead of JSON. Open the app from the Flask server (e.g. http://localhost:5001), not from a static file or another dev server.'
          : 'Something went wrong loading data. Try refreshing the page or signing in again.');
      }
      return JSON.parse(text);
    });
  }

  // Redirect to login on 401 (session expired or not authenticated)
  var origFetch = window.fetch;
  window.fetch = function () {
    return origFetch.apply(this, arguments).then(function (res) {
      if (res.status === 401) {
        window.location.href = '/login';
        return Promise.reject(new Error('Unauthorized'));
      }
      return res;
    });
  };

  // Sign out: clear session and go to login
  var signOutEl = document.getElementById('sign-out');
  if (signOutEl) {
    signOutEl.addEventListener('click', function (e) {
      e.preventDefault();
      fetch(API + '/logout', { method: 'POST', credentials: 'same-origin' })
        .then(function () { window.location.href = '/login'; })
        .catch(function () { window.location.href = '/login'; });
    });
  }

  // Show HubSpot connection status: logo + tick (connected) or x (not connected)
  (function () {
    var wrap = document.getElementById('api-status-wrap');
    var okEl = document.getElementById('api-status-ok');
    var failEl = document.getElementById('api-status-fail');
    var loadingEl = document.getElementById('api-status-loading');
    if (!wrap) return;
    function showLoading() {
      if (loadingEl) loadingEl.hidden = false;
      if (okEl) okEl.hidden = true;
      if (failEl) failEl.hidden = true;
    }
    function showResult(connected) {
      if (loadingEl) loadingEl.hidden = true;
      if (okEl) okEl.hidden = !connected;
      if (failEl) failEl.hidden = connected;
    }
    showLoading();
    fetch(API + '/health')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        showResult(!!d.hubspot_configured);
      })
      .catch(function () {
        showResult(false);
      });
  })();

  function staffSearch() {
    var input = document.getElementById('staff-search-input');
    var resultsEl = document.getElementById('staff-search-results');
    if (!input || !resultsEl) return;

    function showResults(matches) {
      resultsEl.innerHTML = '';
      if (matches.length === 0) {
        var empty = document.createElement('button');
        empty.type = 'button';
        empty.className = 'staff-search-result-item';
        empty.textContent = 'No staff found';
        empty.disabled = true;
        resultsEl.appendChild(empty);
      } else {
        matches.forEach(function (s) {
          var name = s.name || s.hubspot_owner_id || 'Staff ' + s.id;
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'staff-search-result-item';
          btn.textContent = name;
          btn.setAttribute('data-staff-id', String(s.id));
          btn.addEventListener('click', function () {
            var id = this.getAttribute('data-staff-id');
            resultsEl.hidden = true;
            input.value = '';
            var staffTab = document.querySelector('.tab[data-tab="staff-mgmt"]');
            if (staffTab) staffTab.click();
            setTimeout(function () {
              var row = document.querySelector('.staff-table tr[data-staff-id="' + id + '"]');
              if (row) {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                row.classList.add('staff-row-highlight');
                setTimeout(function () {
                  row.classList.remove('staff-row-highlight');
                }, 1200);
              }
            }, 150);
          });
          resultsEl.appendChild(btn);
        });
      }
      resultsEl.hidden = false;
    }

    input.addEventListener('input', function () {
      var q = (this.value || '').trim().toLowerCase();
      if (q.length === 0) {
        resultsEl.hidden = true;
        return;
      }
      var matches = staffCache.filter(function (s) {
        var name = (s.name || s.hubspot_owner_id || '').toString().toLowerCase();
        return name.indexOf(q) !== -1;
      });
      showResults(matches.slice(0, 20));
    });

    input.addEventListener('focus', function () {
      var q = (input.value || '').trim().toLowerCase();
      if (q.length > 0) {
        var matches = staffCache.filter(function (s) {
          var name = (s.name || s.hubspot_owner_id || '').toString().toLowerCase();
          return name.indexOf(q) !== -1;
        });
        showResults(matches.slice(0, 20));
      }
    });

    document.addEventListener('click', function (e) {
      if (resultsEl.hidden) return;
      if (e.target !== input && !resultsEl.contains(e.target)) resultsEl.hidden = true;
    });
  }

  function tabs() {
    document.querySelectorAll('.tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const tab = this.getAttribute('data-tab');
        document.querySelectorAll('.tab').forEach(function (b) { b.classList.remove('active'); });
        document.querySelectorAll('.panel').forEach(function (p) {
          p.classList.remove('active');
          p.hidden = p.id !== tab;
        });
        this.classList.add('active');
        document.getElementById(tab).classList.add('active');
        document.getElementById(tab).hidden = false;
        if (tab === 'data' && typeof activityLog === 'function') activityLog();
        if (tab === 'team-mgmt') leadTeamsTable();
        if (tab === 'staff-mgmt') renderUnallocatedGauges();
        if (tab === 'call-activity') loadCallActivityTab();
      });
    });
  }

  function loadCallActivityTab() {
    var loadingEl = document.getElementById('call-activity-loading');
    var container = document.getElementById('call-activity-chart');
    var section = document.getElementById('call-activity-section');
    if (!section || !container) return;
    if (staffCache && staffCache.length > 0) {
      renderCallActivityChart(staffCache);
      return;
    }
    if (loadingEl) loadingEl.hidden = false;
    if (container) container.innerHTML = '';
    fetch(API + '/staff').then(parseJsonResponse).then(function (data) {
      if (data.staff) staffCache = data.staff;
      renderCallActivityChart(staffCache || []);
    }).catch(function (e) {
      if (container) container.innerHTML = '<p class="error">' + (e.message || 'Failed to load').replace(/</g, '&lt;') + '</p>';
    }).finally(function () {
      if (loadingEl) loadingEl.hidden = true;
    });
  }

  var GAUGE_MAX = 200;
  function renderUnallocatedGauges() {
    var container = document.getElementById('unallocated-gauges');
    var loadingEl = document.getElementById('unallocated-gauges-loading');
    var errEl = document.getElementById('unallocated-gauges-error');
    if (!container) return;
    loadingEl.hidden = false;
    errEl.hidden = true;
    container.hidden = true;
    fetch(API + '/lead-teams')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        loadingEl.hidden = true;
        if (data.error) {
          errEl.textContent = data.error;
          errEl.hidden = false;
          return;
        }
        var teams = data.lead_teams || [];
        container.innerHTML = '';
        if (teams.length === 0) {
          errEl.textContent = data.message || 'No lead teams';
          errEl.hidden = false;
          return;
        }
        container.hidden = false;
        teams.forEach(function (t) {
          var name = t.name || t.id || '—';
          var shortName = name.replace(/\s*Lead Team\s*$/i, '') || name;
          var value = t.unallocated != null ? Number(t.unallocated) : 0;
          var el = document.createElement('div');
          el.className = 'gauge-wrap';
          var label = document.createElement('div');
          label.className = 'gauge-title';
          label.textContent = shortName;
          var num = document.createElement('div');
          num.className = 'gauge-value';
          num.textContent = value;
          var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          svg.setAttribute('viewBox', '0 0 120 75');
          svg.setAttribute('class', 'gauge-svg');
          svg.setAttribute('aria-hidden', 'true');
          var cx = 60; var cy = 58; var r = 44;
          var trackWidth = 12;
          var needleVal = Math.min(value, GAUGE_MAX);
          var pct = needleVal / GAUGE_MAX;
          var trackColor;
          if (pct <= 1/6) trackColor = '#22c55e';
          else if (pct <= 2/6) trackColor = '#16a34a';
          else if (pct <= 3/6) trackColor = '#eab308';
          else if (pct <= 4/6) trackColor = '#ea580c';
          else if (pct <= 5/6) trackColor = '#dc2626';
          else trackColor = '#b91c1c';
          var angleDeg = 180 - pct * 180;
          var needleRad = (angleDeg * Math.PI) / 180;
          var xNeedle = cx + r * Math.cos(needleRad);
          var yNeedle = cy - r * Math.sin(needleRad);
          var xLeft = cx - r;
          var yLeft = cy;
          var xRight = cx + r;
          var yRight = cy;
          /* Sweep 1 = arc through bottom in SVG (y-down); we draw arc below baseline so it curves up visually */
          var sweep = 1;
          if (pct <= 0.002) {
            var arcGreyFull = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            arcGreyFull.setAttribute('d', 'M ' + xLeft + ' ' + yLeft + ' A ' + r + ' ' + r + ' 0 0 ' + sweep + ' ' + xRight + ' ' + yRight);
            arcGreyFull.setAttribute('fill', 'none');
            arcGreyFull.setAttribute('stroke', '#d1d5db');
            arcGreyFull.setAttribute('stroke-width', trackWidth);
            arcGreyFull.setAttribute('stroke-linecap', 'round');
            svg.appendChild(arcGreyFull);
          } else {
            var arcColored = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            arcColored.setAttribute('d', 'M ' + xLeft + ' ' + yLeft + ' A ' + r + ' ' + r + ' 0 0 ' + sweep + ' ' + xNeedle + ' ' + yNeedle);
            arcColored.setAttribute('fill', 'none');
            arcColored.setAttribute('stroke', trackColor);
            arcColored.setAttribute('stroke-width', trackWidth);
            arcColored.setAttribute('stroke-linecap', 'round');
            svg.appendChild(arcColored);
            var arcGrey = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            arcGrey.setAttribute('d', 'M ' + xNeedle + ' ' + yNeedle + ' A ' + r + ' ' + r + ' 0 0 ' + sweep + ' ' + xRight + ' ' + yRight);
            arcGrey.setAttribute('fill', 'none');
            arcGrey.setAttribute('stroke', '#d1d5db');
            arcGrey.setAttribute('stroke-width', trackWidth);
            arcGrey.setAttribute('stroke-linecap', 'round');
            svg.appendChild(arcGrey);
          }
          var needleLen = r + 4;
          var nx = cx + needleLen * Math.cos(needleRad);
          var ny = cy - needleLen * Math.sin(needleRad);
          var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line.setAttribute('x1', cx);
          line.setAttribute('y1', cy);
          line.setAttribute('x2', nx);
          line.setAttribute('y2', ny);
          line.setAttribute('stroke', '#111');
          line.setAttribute('stroke-width', '4');
          line.setAttribute('stroke-linecap', 'round');
          var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', cx);
          circle.setAttribute('cy', cy);
          circle.setAttribute('r', '5');
          circle.setAttribute('fill', '#111');
          svg.appendChild(line);
          svg.appendChild(circle);
          el.appendChild(label);
          el.appendChild(num);
          el.appendChild(svg);
          container.appendChild(el);
        });
      })
      .catch(function (e) {
        loadingEl.hidden = true;
        errEl.textContent = e.message || 'Failed to load unallocated counts';
        errEl.hidden = false;
      });
  }

  function leadTeamsTable() {
    const loading = document.getElementById('lead-teams-loading');
    const errEl = document.getElementById('lead-teams-error');
    const table = document.getElementById('lead-teams-table');
    const tbody = table.querySelector('tbody');
    const empty = document.getElementById('lead-teams-empty');

    fetch(API + '/lead-teams')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        loading.hidden = true;
        if (data.error) {
          errEl.textContent = data.error;
          errEl.hidden = false;
          return;
        }
        const teams = data.lead_teams || [];
        if (teams.length === 0) {
          empty.hidden = false;
          if (data.message) empty.textContent = data.message;
          return;
        }
        table.hidden = false;
        tbody.innerHTML = '';
        teams.forEach(function (t) {
          const tr = document.createElement('tr');
          const name = document.createElement('td');
          name.textContent = t.name || t.id || '—';
          const unallocatedCell = document.createElement('td');
          unallocatedCell.className = 'lead-teams-unallocated';
          unallocatedCell.textContent = t.unallocated != null ? t.unallocated : '—';
          const maxCell = document.createElement('td');
          const input = document.createElement('input');
          input.type = 'number';
          input.min = 0;
          input.value = t.max_leads != null ? t.max_leads : '';
          input.placeholder = 'Max leads';
          maxCell.appendChild(input);
          const actions = document.createElement('td');
          const saveBtn = document.createElement('button');
          saveBtn.className = 'btn';
          saveBtn.textContent = 'Save';
          saveBtn.addEventListener('click', function () {
            const val = input.value;
            if (val === '' && val !== 0) return;
            saveBtn.disabled = true;
            fetch(API + '/lead-teams/' + encodeURIComponent(t.id), {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ max_leads: parseInt(val, 10) }),
            })
              .then(function (res) {
                if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
                saveBtn.textContent = 'Saved';
                setTimeout(function () { saveBtn.textContent = 'Save'; }, 1500);
              })
              .catch(function (e) {
                alert('Error: ' + e.message);
              })
              .finally(function () { saveBtn.disabled = false; });
          });
          actions.appendChild(saveBtn);
          tr.appendChild(name);
          tr.appendChild(unallocatedCell);
          tr.appendChild(maxCell);
          tr.appendChild(actions);
          tbody.appendChild(tr);
        });
      })
      .catch(function (e) {
        loading.hidden = true;
        errEl.textContent = e.message || 'Failed to load lead teams';
        errEl.hidden = false;
      });
  }

  var LEAD_TEAM_KEYS = [
    'Inbound Lead Team',
    'PIP Lead Team',
    'Panther Lead Team',
    'Frosties Lead Team'
  ];

  function parseLeadTeams(leadTeamsStr) {
    if (!leadTeamsStr || typeof leadTeamsStr !== 'string') return [];
    return leadTeamsStr.split(';').map(function (t) { return t.trim(); }).filter(Boolean);
  }

  function isInTeam(parsedTeams, teamName) {
    return parsedTeams.some(function (t) {
      return t === teamName || t.indexOf(teamName) !== -1 || teamName.indexOf(t) !== -1;
    });
  }

  function shortTeamName(teamName) {
    return teamName.replace(' Lead Team', '');
  }

  function showConfirm(message) {
    return new Promise(function (resolve) {
      var modal = document.getElementById('confirm-modal');
      var title = document.getElementById('confirm-modal-title');
      var cancelBtn = modal.querySelector('.modal-cancel');
      var confirmBtn = modal.querySelector('.modal-confirm');
      title.textContent = message;
      modal.hidden = false;
      function close(result) {
        modal.hidden = true;
        cancelBtn.removeEventListener('click', onCancel);
        confirmBtn.removeEventListener('click', onConfirm);
        backdrop.removeEventListener('click', onCancel);
        resolve(result);
      }
      function onCancel() { close(false); }
      function onConfirm() { close(true); }
      var backdrop = modal.querySelector('.modal-backdrop');
      cancelBtn.addEventListener('click', onCancel);
      confirmBtn.addEventListener('click', onConfirm);
      backdrop.addEventListener('click', onCancel);
      confirmBtn.focus();
    });
  }

  var CALL_MINUTES_MAX = 120;

  function renderStaffRow(s, tbody, pauseLeadsOptions) {
          const parsed = parseLeadTeams(s.lead_teams);
          const tr = document.createElement('tr');
          tr.setAttribute('data-staff-id', String(s.id));
          const nameCell = document.createElement('td');
          nameCell.textContent = s.name || s.hubspot_owner_id || '—';
          tr.appendChild(nameCell);
          const gaugeCell = document.createElement('td');
          gaugeCell.className = 'temp-gauge-cell';
          var callMins = s.call_minutes_last_120 != null ? Math.min(Number(s.call_minutes_last_120) || 0, CALL_MINUTES_MAX) : 0;
          var hue = Math.round((callMins / CALL_MINUTES_MAX) * 120);
          var gaugeWrap = document.createElement('div');
          gaugeWrap.className = 'temp-gauge-wrap';
          gaugeWrap.title = callMins + ' min on calls (last 2h). Red = available, green = busy.';
          var gaugeBar = document.createElement('div');
          gaugeBar.className = 'temp-gauge-bar';
          gaugeBar.style.backgroundColor = 'hsl(' + hue + ', 70%, 42%)';
          gaugeWrap.appendChild(gaugeBar);
          var gaugeLabel = document.createElement('span');
          gaugeLabel.className = 'temp-gauge-label';
          gaugeLabel.textContent = callMins + ' m';
          gaugeWrap.appendChild(gaugeLabel);
          gaugeCell.appendChild(gaugeWrap);
          tr.appendChild(gaugeCell);
          const staffName = s.name || s.hubspot_owner_id || 'this person';
          LEAD_TEAM_KEYS.forEach(function (teamName) {
            const td = document.createElement('td');
            td.className = 'team-tick';
            const shortName = shortTeamName(teamName);
            if (isInTeam(parsed, teamName)) {
              const tickBtn = document.createElement('button');
              tickBtn.type = 'button';
              tickBtn.className = 'team-tick-btn';
              tickBtn.textContent = '✓';
              tickBtn.setAttribute('aria-label', 'Remove from ' + teamName);
              tickBtn.title = 'Remove from ' + shortName;
              tickBtn.addEventListener('click', function () {
                var msg = 'Do you want to remove ' + staffName + ' from ' + shortName + '?';
                showConfirm(msg).then(function (confirmed) {
                  if (!confirmed) return;
                  tickBtn.disabled = true;
                  tickBtn.textContent = '…';
                  fetch(API + '/staff/' + encodeURIComponent(s.id), {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ remove_team: teamName }),
                  })
                    .then(function (res) {
                      if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
                      td.innerHTML = '';
                      var addBtn = document.createElement('button');
                      addBtn.type = 'button';
                      addBtn.className = 'team-add-btn';
                      addBtn.textContent = '+';
                      addBtn.setAttribute('aria-label', 'Add to ' + teamName);
                      addBtn.title = 'Add to ' + shortName;
                      td.appendChild(addBtn);
                      wireAddButton(addBtn, td, s, staffName, teamName, shortName);
                    })
                    .catch(function (e) {
                      alert('Error: ' + e.message);
                      tickBtn.disabled = false;
                      tickBtn.textContent = '✓';
                    });
                });
              });
              td.appendChild(tickBtn);
            } else {
              const addBtn = document.createElement('button');
              addBtn.type = 'button';
              addBtn.className = 'team-add-btn';
              addBtn.textContent = '+';
              addBtn.setAttribute('aria-label', 'Add to ' + teamName);
              addBtn.title = 'Add to ' + shortName;
              addBtn.addEventListener('click', function () {
                var msg = 'Do you want to add ' + staffName + ' to ' + shortName + '?';
                showConfirm(msg).then(function (confirmed) {
                  if (!confirmed) return;
                  addBtn.disabled = true;
                  addBtn.textContent = '…';
                  fetch(API + '/staff/' + encodeURIComponent(s.id), {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ add_team: teamName }),
                  })
                    .then(function (res) {
                      if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
                      td.innerHTML = '';
                      var tickBtn = document.createElement('button');
                      tickBtn.type = 'button';
                      tickBtn.className = 'team-tick-btn';
                      tickBtn.textContent = '✓';
                      tickBtn.setAttribute('aria-label', 'Remove from ' + teamName);
                      tickBtn.title = 'Remove from ' + shortName;
                      td.appendChild(tickBtn);
                      wireTickButton(tickBtn, td, s, staffName, teamName, shortName);
                    })
                    .catch(function (e) {
                      alert('Error: ' + e.message);
                      addBtn.disabled = false;
                      addBtn.textContent = '+';
                    });
                });
              });
              td.appendChild(addBtn);
            }
            tr.appendChild(td);
          });

          function wireAddButton(addBtn, td, staff, staffName, teamName, shortName) {
            addBtn.addEventListener('click', function () {
              var msg = 'Do you want to add ' + staffName + ' to ' + shortName + '?';
              showConfirm(msg).then(function (confirmed) {
                if (!confirmed) return;
                addBtn.disabled = true;
                addBtn.textContent = '…';
                fetch(API + '/staff/' + encodeURIComponent(staff.id), {
                  method: 'PATCH',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ add_team: teamName }),
                })
                  .then(function (res) {
                    if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
                    td.innerHTML = '';
                    var tickBtn = document.createElement('button');
                    tickBtn.type = 'button';
                    tickBtn.className = 'team-tick-btn';
                    tickBtn.textContent = '✓';
                    tickBtn.setAttribute('aria-label', 'Remove from ' + teamName);
                    tickBtn.title = 'Remove from ' + shortName;
                    td.appendChild(tickBtn);
                    wireTickButton(tickBtn, td, staff, staffName, teamName, shortName);
                  })
                  .catch(function (e) {
                    alert('Error: ' + e.message);
                    addBtn.disabled = false;
                    addBtn.textContent = '+';
                  });
              });
            });
          }

          function wireTickButton(tickBtn, td, staff, staffName, teamName, shortName) {
            tickBtn.addEventListener('click', function () {
              var msg = 'Do you want to remove ' + staffName + ' from ' + shortName + '?';
              showConfirm(msg).then(function (confirmed) {
                if (!confirmed) return;
                tickBtn.disabled = true;
                tickBtn.textContent = '…';
                fetch(API + '/staff/' + encodeURIComponent(staff.id), {
                  method: 'PATCH',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ remove_team: teamName }),
                })
                  .then(function (res) {
                    if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
                    td.innerHTML = '';
                    var addBtn = document.createElement('button');
                    addBtn.type = 'button';
                    addBtn.className = 'team-add-btn';
                    addBtn.textContent = '+';
                    addBtn.setAttribute('aria-label', 'Add to ' + teamName);
                    addBtn.title = 'Add to ' + shortName;
                    td.appendChild(addBtn);
                    wireAddButton(addBtn, td, staff, staffName, teamName, shortName);
                  })
                  .catch(function (e) {
                    alert('Error: ' + e.message);
                    tickBtn.disabled = false;
                    tickBtn.textContent = '✓';
                  });
              });
            });
          }
          const availCell = document.createElement('td');
          availCell.className = 'availability-cell';
          const isAvailable = (s.availability || '').toLowerCase() !== 'unavailable';
          const label = document.createElement('label');
          label.className = 'toggle-switch';
          const input = document.createElement('input');
          input.type = 'checkbox';
          input.checked = isAvailable;
          input.setAttribute('aria-label', 'Availability');
          label.appendChild(input);
          const span = document.createElement('span');
          span.className = 'toggle-slider';
          label.appendChild(span);
          availCell.appendChild(label);
          if (s.on_holiday_today) {
            const holidayIcon = document.createElement('span');
            holidayIcon.className = 'availability-holiday-icon';
            holidayIcon.title = 'On holiday';
            holidayIcon.setAttribute('aria-label', 'On holiday');
            holidayIcon.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01M16 18h.01"/></svg>';
            availCell.appendChild(holidayIcon);
          }
          input.addEventListener('change', function () {
            const value = this.checked ? 'Available' : 'Unavailable';
            var doPatch = function () {
              input.disabled = true;
              fetch(API + '/staff/' + encodeURIComponent(s.id), {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ availability: value }),
              })
                .then(function (res) {
                  if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
                })
                .catch(function (e) {
                  alert('Error: ' + e.message);
                  input.checked = !input.checked;
                })
                .finally(function () { input.disabled = false; });
            };
            if (this.checked && s.on_holiday_today) {
              showConfirm('This staff member is set as away on holiday – are you sure you want to make them active?').then(function (confirmed) {
                if (!confirmed) {
                  input.checked = false;
                  return;
                }
                doPatch();
              });
            } else {
              doPatch();
            }
          });
          tr.appendChild(availCell);
          const pauseCell = document.createElement('td');
          pauseCell.className = 'pause-leads-cell';
          const pauseSelect = document.createElement('select');
          pauseSelect.className = 'pause-leads-select';
          pauseSelect.setAttribute('aria-label', 'Pause leads');
          var currentPause = (s.pause_leads != null && s.pause_leads !== '') ? String(s.pause_leads) : '';
          var opts = (typeof pauseLeadsOptions !== 'undefined' && pauseLeadsOptions) ? pauseLeadsOptions : [];
          var blankOpt = document.createElement('option');
          blankOpt.value = '';
          blankOpt.textContent = '—';
          pauseSelect.appendChild(blankOpt);
          opts.forEach(function (opt) {
            var option = document.createElement('option');
            option.value = opt.value;
            option.textContent = opt.label || opt.value;
            option.selected = opt.value === currentPause;
            pauseSelect.appendChild(option);
          });
          if (currentPause && opts.every(function (o) { return o.value !== currentPause; })) {
            var fallbackOpt = document.createElement('option');
            fallbackOpt.value = currentPause;
            fallbackOpt.textContent = currentPause;
            fallbackOpt.selected = true;
            pauseSelect.appendChild(fallbackOpt);
          }
          pauseSelect.value = currentPause;
          pauseCell.appendChild(pauseSelect);
          pauseSelect.addEventListener('change', function () {
            var value = this.value;
            pauseSelect.disabled = true;
            fetch(API + '/staff/' + encodeURIComponent(s.id), {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ pause_leads: value }),
            })
              .then(function (res) {
                if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
              })
              .catch(function (e) {
                alert('Error: ' + e.message);
                pauseSelect.value = currentPause;
              })
              .finally(function () { pauseSelect.disabled = false; });
          });
          tr.appendChild(pauseCell);
          const actions = document.createElement('td');
          tr.appendChild(actions);
          tbody.appendChild(tr);

          var openInbound = s.open_inbound_leads_n8n != null ? Number(s.open_inbound_leads_n8n) : 0;
          var openPip = s.open_pip_leads_n8n != null ? Number(s.open_pip_leads_n8n) : 0;
          var openPanther = s.open_panther_leads != null ? Number(s.open_panther_leads) : 0;
          var openFrosties = s.open_frosties_leads != null ? Number(s.open_frosties_leads) : 0;
          var subRow = document.createElement('tr');
          subRow.className = 'open-leads-row';
          var labelCell = document.createElement('td');
          labelCell.className = 'open-leads-label';
          labelCell.textContent = 'Open leads';
          subRow.appendChild(labelCell);
          var gaugeEmptyCell = document.createElement('td');
          subRow.appendChild(gaugeEmptyCell);
          [openInbound, openPip, openPanther, openFrosties].forEach(function (num) {
            var cell = document.createElement('td');
            cell.className = 'open-leads-count';
            cell.textContent = num;
            subRow.appendChild(cell);
          });
          var totalOpen = openInbound + openPip + openPanther + openFrosties;
          var totalCell = document.createElement('td');
          totalCell.className = 'open-leads-total';
          totalCell.textContent = totalOpen + ' (total)';
          subRow.appendChild(totalCell);
          var emptyPauseCell = document.createElement('td');
          subRow.appendChild(emptyPauseCell);
          var emptyCell2 = document.createElement('td');
          subRow.appendChild(emptyCell2);
          tbody.appendChild(subRow);

          var reassignRow = document.createElement('tr');
          reassignRow.className = 'reassign-leads-row';
          var reassignLabelCell = document.createElement('td');
          reassignLabelCell.className = 'reassign-leads-label';
          reassignLabelCell.colSpan = 1;
          reassignLabelCell.textContent = 'Re-assign leads';
          reassignRow.appendChild(reassignLabelCell);
          var reassignGaugeEmpty = document.createElement('td');
          reassignRow.appendChild(reassignGaugeEmpty);
          var openCounts = [openInbound, openPip, openPanther, openFrosties];
          LEAD_TEAM_KEYS.forEach(function (teamName, idx) {
            var cell = document.createElement('td');
            cell.className = 'reassign-leads-cell';
            var shareBtn = document.createElement('button');
            shareBtn.type = 'button';
            shareBtn.className = 'btn btn-secondary reassign-share-btn';
            shareBtn.title = 'Re-assign ' + shortTeamName(teamName) + ' leads for this person';
            shareBtn.setAttribute('aria-label', 'Re-assign ' + shortTeamName(teamName) + ' leads');
            shareBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>';
            shareBtn.addEventListener('click', function () { openReassignModal(s, teamName); });
            cell.appendChild(shareBtn);
            reassignRow.appendChild(cell);
          });
          var emptyTd1 = document.createElement('td');
          var emptyTd2 = document.createElement('td');
          var emptyTd3 = document.createElement('td');
          reassignRow.appendChild(emptyTd1);
          reassignRow.appendChild(emptyTd2);
          reassignRow.appendChild(emptyTd3);
          tbody.appendChild(reassignRow);
  }

  var reassignState = { staff: null, team: null, preview: null };

  function openReassignModal(staff, teamName) {
    var modal = document.getElementById('reassign-modal');
    var titleEl = document.getElementById('reassign-modal-title');
    var loadingEl = document.getElementById('reassign-loading');
    var step1El = document.getElementById('reassign-step1');
    var step2El = document.getElementById('reassign-step2');
    var doneEl = document.getElementById('reassign-done');
    var categoriesEl = document.getElementById('reassign-categories');
    var doBtn = document.getElementById('reassign-do-btn');
    var shortName = shortTeamName(teamName);
    var staffName = staff.name || staff.hubspot_owner_id || 'This person';
    reassignState.staff = staff;
    reassignState.team = teamName;
    reassignState.preview = null;
    titleEl.textContent = 'Re-assign leads – ' + staffName + ' – ' + shortName;
    loadingEl.hidden = false;
    step1El.hidden = true;
    step2El.hidden = true;
    doneEl.hidden = true;
    modal.hidden = false;

    fetch(API + '/reassign/preview?owner_id=' + encodeURIComponent(staff.hubspot_owner_id) + '&team=' + encodeURIComponent(teamName))
      .then(parseJsonResponse)
      .then(function (data) {
        loadingEl.hidden = true;
        if (data.error) {
          alert('Error: ' + data.error);
          modal.hidden = true;
          return;
        }
        reassignState.preview = data;
        var counts = data.counts || {};
        var labels = { attempt_1: 'Attempt 1', attempt_2: 'Attempt 2', attempt_3: 'Attempt 3', call_back: 'Call Back' };
        categoriesEl.innerHTML = '';
        ['attempt_1', 'attempt_2', 'attempt_3', 'call_back'].forEach(function (key) {
          var label = document.createElement('label');
          label.className = 'reassign-category-label';
          var cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.className = 'reassign-category-cb';
          cb.setAttribute('data-category', key);
          var n = counts[key] != null ? counts[key] : 0;
          label.appendChild(cb);
          label.appendChild(document.createTextNode(' ' + (labels[key] || key) + ' — ' + n + ' lead(s)'));
          categoriesEl.appendChild(label);
        });
        doBtn.disabled = true;
        categoriesEl.querySelectorAll('.reassign-category-cb').forEach(function (cb) {
          cb.addEventListener('change', function () {
            var any = categoriesEl.querySelectorAll('.reassign-category-cb:checked').length > 0;
            doBtn.disabled = !any;
          });
        });
        step1El.hidden = false;
      })
      .catch(function (e) {
        loadingEl.hidden = true;
        alert('Error: ' + (e.message || 'Failed to load'));
        modal.hidden = true;
      });
  }

  function reassignUpdateConfirmButton() {
    var listEl = document.getElementById('reassign-target-list');
    var confirmBtn = document.getElementById('reassign-confirm-btn');
    if (!listEl || !confirmBtn) return;
    var checked = listEl.querySelectorAll('.reassign-staff-cb:checked');
    confirmBtn.disabled = checked.length === 0;
  }

  function reassignUpdateSelectAll() {
    var listEl = document.getElementById('reassign-target-list');
    var selectAllCb = listEl ? listEl.querySelector('.reassign-select-all-cb') : null;
    if (!selectAllCb) return;
    var staffCbs = listEl.querySelectorAll('.reassign-staff-cb');
    var n = staffCbs.length;
    selectAllCb.checked = n > 0 && listEl.querySelectorAll('.reassign-staff-cb:checked').length === n;
  }

  function reassignShowStep2() {
    var categoriesEl = document.getElementById('reassign-categories');
    var selected = [];
    categoriesEl.querySelectorAll('.reassign-category-cb:checked').forEach(function (cb) {
      selected.push(cb.getAttribute('data-category'));
    });
    if (selected.length === 0) return;
    var preview = reassignState.preview;
    var targetStaff = (preview && preview.target_staff) || [];
    var total = 0;
    var counts = preview.counts || {};
    selected.forEach(function (c) { total += (counts[c] != null ? counts[c] : 0); });
    document.getElementById('reassign-step1').hidden = true;
    document.getElementById('reassign-step2').hidden = false;
    document.getElementById('reassign-done').hidden = true;
    document.getElementById('reassign-confirm-msg').textContent = 'You are about to re-assign ' + total + ' lead(s). Choose who will receive them (sorted by fewest open leads first):';
    var listEl = document.getElementById('reassign-target-list');
    listEl.innerHTML = '';
    if (targetStaff.length === 0) {
      listEl.innerHTML = '<li class="empty">No available staff in this team.</li>';
    } else {
      var selectAllLi = document.createElement('li');
      selectAllLi.className = 'reassign-target-item reassign-select-all-row';
      var selectAllCb = document.createElement('input');
      selectAllCb.type = 'checkbox';
      selectAllCb.className = 'reassign-select-all-cb';
      selectAllCb.checked = false;
      var selectAllLabel = document.createElement('label');
      selectAllLabel.appendChild(selectAllCb);
      selectAllLabel.appendChild(document.createTextNode(' Select all'));
      selectAllLi.appendChild(selectAllLabel);
      listEl.appendChild(selectAllLi);

      targetStaff.forEach(function (s) {
        var li = document.createElement('li');
        li.className = 'reassign-target-item';
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'reassign-staff-cb';
        cb.checked = false;
        cb.setAttribute('data-owner-id', s.hubspot_owner_id || '');
        cb.addEventListener('change', function () {
          reassignUpdateConfirmButton();
          reassignUpdateSelectAll();
        });
        var label = document.createElement('label');
        label.appendChild(cb);
        var n = s.total_open_leads != null ? s.total_open_leads : 0;
        label.appendChild(document.createTextNode(' ' + (s.name || s.hubspot_owner_id) + ' — ' + n + ' open lead(s)'));
        li.appendChild(label);
        listEl.appendChild(li);
      });

      selectAllCb.addEventListener('change', function () {
        var checked = selectAllCb.checked;
        listEl.querySelectorAll('.reassign-staff-cb').forEach(function (cb) { cb.checked = checked; });
        reassignUpdateConfirmButton();
      });
    }
    reassignState.selectedCategories = selected;
    reassignUpdateConfirmButton();
  }

  function reassignExecute() {
    var staff = reassignState.staff;
    var team = reassignState.team;
    var categories = reassignState.selectedCategories;
    if (!staff || !team || !categories || categories.length === 0) return;
    var listEl = document.getElementById('reassign-target-list');
    var targetOwnerIds = [];
    if (listEl) {
      listEl.querySelectorAll('.reassign-staff-cb:checked').forEach(function (cb) {
        var id = cb.getAttribute('data-owner-id');
        if (id) targetOwnerIds.push(id);
      });
    }
    if (targetOwnerIds.length === 0) {
      alert('Select at least one team member to receive leads.');
      return;
    }
    var confirmBtn = document.getElementById('reassign-confirm-btn');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Reassigning…';
    fetch(API + '/reassign/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        owner_id: staff.hubspot_owner_id,
        team: team,
        categories: categories,
        target_owner_ids: targetOwnerIds,
      }),
    })
      .then(parseJsonResponse)
      .then(function (data) {
        document.getElementById('reassign-step2').hidden = true;
        var doneEl = document.getElementById('reassign-done');
        var msgEl = document.getElementById('reassign-done-msg');
        msgEl.textContent = data.error ? ('Error: ' + data.error) : ('Re-assigned ' + (data.reassigned || 0) + ' lead(s).');
        doneEl.hidden = false;
        if (!data.error) staffTable();
      })
      .catch(function (e) {
        alert('Error: ' + (e.message || 'Request failed'));
      })
      .finally(function () {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm';
      });
  }

  (function wireReassignModal() {
    var modal = document.getElementById('reassign-modal');
    if (!modal) return;
    var doBtn = document.getElementById('reassign-do-btn');
    if (doBtn) doBtn.addEventListener('click', reassignShowStep2);
    var cancel1 = document.getElementById('reassign-cancel-1');
    if (cancel1) cancel1.addEventListener('click', function () { modal.hidden = true; });
    var backBtn = document.getElementById('reassign-back-btn');
    if (backBtn) backBtn.addEventListener('click', function () {
      document.getElementById('reassign-step2').hidden = true;
      document.getElementById('reassign-step1').hidden = false;
    });
    var confirmBtn = document.getElementById('reassign-confirm-btn');
    if (confirmBtn) confirmBtn.addEventListener('click', reassignExecute);
    var closeBtn = document.getElementById('reassign-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', function () { modal.hidden = true; staffTable(); });
    var backdrop = modal.querySelector('.modal-backdrop');
    if (backdrop) backdrop.addEventListener('click', function () { modal.hidden = true; });
  })();

  function renderCallActivityChart(staff) {
    const container = document.getElementById('call-activity-chart');
    const section = document.getElementById('call-activity-section');
    if (!container || !section) return;
    if (!staff || staff.length === 0) {
      section.hidden = false;
      container.innerHTML = '<p class="empty">No staff data.</p>';
      return;
    }
    section.hidden = false;
    var sorted = staff.slice().sort(function (a, b) {
      var ma = Math.min(Number(a.call_minutes_last_120) || 0, CALL_MINUTES_MAX);
      var mb = Math.min(Number(b.call_minutes_last_120) || 0, CALL_MINUTES_MAX);
      return mb - ma;
    });
    container.innerHTML = '';
    sorted.forEach(function (s) {
      var mins = Math.min(Number(s.call_minutes_last_120) || 0, CALL_MINUTES_MAX);
      var hue = Math.round((mins / CALL_MINUTES_MAX) * 120);
      var name = s.name || s.hubspot_owner_id || '—';
      var row = document.createElement('div');
      row.className = 'call-activity-row';
      var nameEl = document.createElement('span');
      nameEl.className = 'call-activity-name';
      nameEl.textContent = name;
      var barWrap = document.createElement('div');
      barWrap.className = 'call-activity-bar-wrap';
      var bar = document.createElement('div');
      bar.className = 'call-activity-bar';
      bar.style.width = (mins / CALL_MINUTES_MAX) * 100 + '%';
      bar.style.backgroundColor = 'hsl(' + hue + ', 70%, 42%)';
      barWrap.appendChild(bar);
      var label = document.createElement('span');
      label.className = 'call-activity-label';
      label.textContent = mins + ' m';
      row.appendChild(nameEl);
      row.appendChild(barWrap);
      row.appendChild(label);
      container.appendChild(row);
    });
  }

  function staffTable() {
    const loading = document.getElementById('staff-loading');
    const errEl = document.getElementById('staff-error');
    const activeSection = document.getElementById('staff-active-section');
    const inactiveSection = document.getElementById('staff-inactive-section');
    const activeTbody = document.querySelector('#staff-table-active tbody');
    const inactiveTbody = document.querySelector('#staff-table-inactive tbody');

    Promise.all([
      fetch(API + '/staff').then(parseJsonResponse),
      fetch(API + '/staff/field-options/pause_leads').then(parseJsonResponse),
    ])
      .then(function (results) {
        const data = results[0];
        const optionsData = results[1];
        loading.hidden = true;
        if (data.error) {
          errEl.textContent = data.error;
          errEl.hidden = false;
          return;
        }
        const staff = data.staff || [];
        staffCache = staff;
        lastPauseLeadsOptions = optionsData.options || [];
        const pauseLeadsOptions = lastPauseLeadsOptions;
        const active = staff.filter(function (s) {
          return (s.availability || '').toLowerCase() !== 'unavailable';
        });
        const inactive = staff.filter(function (s) {
          return (s.availability || '').toLowerCase() === 'unavailable';
        });
        activeTbody.innerHTML = '';
        inactiveTbody.innerHTML = '';
        active.forEach(function (s) { renderStaffRow(s, activeTbody, pauseLeadsOptions); });
        inactive.forEach(function (s) { renderStaffRow(s, inactiveTbody, pauseLeadsOptions); });
        activeSection.hidden = active.length === 0;
        inactiveSection.hidden = inactive.length === 0;
      })
      .catch(function (e) {
        loading.hidden = true;
        errEl.textContent = e.message || 'Failed to load staff';
        errEl.hidden = false;
      });
  }

  function renderStaffTableFromCache() {
    var activeSection = document.getElementById('staff-active-section');
    var inactiveSection = document.getElementById('staff-inactive-section');
    var activeTbody = document.querySelector('#staff-table-active tbody');
    var inactiveTbody = document.querySelector('#staff-table-inactive tbody');
    if (!activeTbody || !inactiveTbody) return;
    var staff = staffCache || [];
    var active = staff.filter(function (s) {
      return (s.availability || '').toLowerCase() !== 'unavailable';
    });
    var inactive = staff.filter(function (s) {
      return (s.availability || '').toLowerCase() === 'unavailable';
    });
    activeTbody.innerHTML = '';
    inactiveTbody.innerHTML = '';
    active.forEach(function (s) { renderStaffRow(s, activeTbody, lastPauseLeadsOptions); });
    inactive.forEach(function (s) { renderStaffRow(s, inactiveTbody, lastPauseLeadsOptions); });
    activeSection.hidden = active.length === 0;
    inactiveSection.hidden = inactive.length === 0;
  }

  function dryRunForm() {
    const btn = document.getElementById('run-process-btn');
    const loading = document.getElementById('dry-run-loading');
    const errEl = document.getElementById('dry-run-error');
    const resultBox = document.getElementById('dry-run-result');
    const summary = document.getElementById('dry-run-summary');
    const perOwnerEl = document.getElementById('dry-run-per-owner');

    if (!btn) return;

    function renderDryRunResult(data) {
      loading.hidden = true;
      errEl.hidden = true;
      resultBox.hidden = false;
      var s = data.summary || {};
      summary.textContent = 'Active staff processed: ' + (s.owners_processed || 0) + '. Would assign ' + (s.total_assignments || 0) + ' contact(s), would update staff ' + (s.total_staff_updates || 0) + ' time(s).';
      perOwnerEl.innerHTML = '';
      (data.results || []).forEach(function (one) {
        var name = one.staff_name || one.owner_id || 'Staff';
        var block = document.createElement('div');
        block.className = 'dry-run-owner-block';
        var title = document.createElement('h4');
        title.textContent = name + (one.owner_id ? ' (' + one.owner_id + ')' : '');
        block.appendChild(title);
        if (one.error) {
          var p = document.createElement('p');
          p.className = 'error';
          p.textContent = one.error;
          block.appendChild(p);
        } else {
          var assignList = document.createElement('ul');
          (one.planned_assignments || []).forEach(function (a) {
            var li = document.createElement('li');
            li.textContent = a.description || ('Contact ' + a.contact_id + ' → ' + a.owner_id + ' (' + a.team + ')');
            assignList.appendChild(li);
          });
          if (one.planned_assignments && one.planned_assignments.length) {
            var assignLabel = document.createElement('p');
            assignLabel.className = 'dry-run-label';
            assignLabel.textContent = 'Would assign contacts:';
            block.appendChild(assignLabel);
            block.appendChild(assignList);
          }
          var staffList = document.createElement('ul');
          (one.planned_staff_updates || []).forEach(function (u) {
            var li = document.createElement('li');
            li.textContent = u.description || ('Staff ' + u.staff_id + ': ' + JSON.stringify(u.properties));
            staffList.appendChild(li);
          });
          if (one.planned_staff_updates && one.planned_staff_updates.length) {
            var staffLabel = document.createElement('p');
            staffLabel.className = 'dry-run-label';
            staffLabel.textContent = 'Would update staff:';
            block.appendChild(staffLabel);
            block.appendChild(staffList);
          }
          if (!(one.planned_assignments && one.planned_assignments.length) && !(one.planned_staff_updates && one.planned_staff_updates.length)) {
            var none = document.createElement('p');
            none.className = 'text-muted';
            none.textContent = 'No actions (no capacity or no unallocated contacts).';
            block.appendChild(none);
          }
        }
        perOwnerEl.appendChild(block);
      });
    }

    var pollInterval = null;
    function stopPolling() {
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    }

    function pollDryRunStatus() {
      var deadline = Date.now() + 300000; // 5 min
      pollInterval = setInterval(function () {
        if (Date.now() > deadline) {
          stopPolling();
          loading.hidden = true;
          errEl.textContent = 'Test run is taking longer than expected. Check the Data tab or try again.';
          errEl.hidden = false;
          return;
        }
        fetch(API + '/distribute/test/status', { credentials: 'same-origin' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            if (!data) return;
            if (data.status === 'done' && data.result) {
              stopPolling();
              renderDryRunResult(data.result);
            } else if (data.status === 'error' && data.error) {
              stopPolling();
              loading.hidden = true;
              errEl.textContent = data.error;
              errEl.hidden = false;
            }
          });
      }, 2000);
    }

    btn.addEventListener('click', function () {
      errEl.hidden = true;
      resultBox.hidden = true;
      loading.hidden = false;
      perOwnerEl.innerHTML = '';
      stopPolling();

      fetch(API + '/distribute/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({}),
      })
        .then(function (r) {
          var ct = (r.headers.get('Content-Type') || '').toLowerCase();
          if (!r.ok) {
            return r.text().then(function (text) {
              try {
                var d = JSON.parse(text);
                return Promise.reject(new Error(d.error || 'Request failed'));
              } catch (_) {
                return Promise.reject(new Error('Request timed out or server error. Try again.'));
              }
            });
          }
          if (ct.indexOf('application/json') === -1) {
            return Promise.reject(new Error('Request timed out or server error. Try again.'));
          }
          return r.json();
        })
        .then(function (data) {
          if (data.status === 'started' || data.status === 'already_running') {
            pollDryRunStatus();
            return;
          }
          if (data.error) {
            loading.hidden = true;
            errEl.textContent = data.error;
            errEl.hidden = false;
            return;
          }
          renderDryRunResult(data);
        })
        .catch(function (e) {
          loading.hidden = true;
          errEl.textContent = e.message || 'Request failed';
          errEl.hidden = false;
          stopPolling();
        });
    });
  }

  function holidaysModal() {
    var modal = document.getElementById('holidays-modal');
    var listEl = document.getElementById('holidays-list');
    var emptyEl = document.getElementById('holidays-empty');
    var formWrap = document.getElementById('holiday-form-wrap');
    var form = document.getElementById('holiday-form');
    var editIdInput = document.getElementById('holiday-edit-id');
    var staffInput = document.getElementById('holiday-staff');
    var staffSearchInput = document.getElementById('holiday-staff-search');
    var staffListEl = document.getElementById('holiday-staff-list');
    var staffSelectedEl = document.getElementById('holiday-staff-selected');
    var startInput = document.getElementById('holiday-start');
    var endInput = document.getElementById('holiday-end');
    var labelInput = document.getElementById('holiday-label');
    var formTitle = document.querySelector('.holiday-form-title');
    var addBtn = document.getElementById('holiday-add-btn');
    var formCancelBtn = document.getElementById('holiday-form-cancel');
    var submitBtn = document.getElementById('holiday-form-submit');
    var closeBtn = document.querySelector('.holidays-close');
    var staffCache = [];
    var staffForSelect = [];
    var holidaysCache = [];
    var currentCalendarMonth = new Date();
    var viewMode = 'calendar';

    var loadingEl = document.getElementById('holidays-loading');
    var viewsEl = document.getElementById('holidays-views');
    var tabCalendarBtn = document.getElementById('holidays-tab-calendar');
    var tabListBtn = document.getElementById('holidays-tab-list');
    var calendarWrap = document.getElementById('holidays-calendar-wrap');
    var listWrap = document.getElementById('holidays-list-wrap');
    var prevMonthBtn = document.getElementById('holidays-prev-month');
    var nextMonthBtn = document.getElementById('holidays-next-month');
    var monthLabelEl = document.getElementById('holidays-month-label');
    var calendarGridEl = document.getElementById('holidays-calendar-grid');

    function openModal() {
      modal.hidden = false;
      formWrap.hidden = true;
      if (addBtn) addBtn.disabled = false;
      editIdInput.value = '';
      currentCalendarMonth = new Date();
      loadStaffAndHolidays();
    }

    function closeModal() {
      modal.hidden = true;
      if (addBtn) addBtn.disabled = false;
      staffTable();
    }

    function staffById(id) {
      return staffCache.find(function (s) { return String(s.id) === String(id); }) || null;
    }

    function dedupeAndSortStaff(staffList) {
      var seen = {};
      var deduped = (staffList || []).filter(function (s) {
        var key = (s.hubspot_owner_id != null && s.hubspot_owner_id !== '') ? String(s.hubspot_owner_id) : String(s.id);
        if (seen[key]) return false;
        seen[key] = true;
        return true;
      });
      deduped.sort(function (a, b) {
        var na = (a.name || a.id || '').toString().toLowerCase();
        var nb = (b.name || b.id || '').toString().toLowerCase();
        return na.localeCompare(nb);
      });
      return deduped;
    }

    function renderStaffList(filter) {
      if (!staffListEl) return;
      staffListEl.innerHTML = '';
      var q = (filter || '').toLowerCase().trim();
      var list = staffForSelect.filter(function (s) {
        if (!q) return true;
        var name = (s.name || s.hubspot_owner_id || '').toString().toLowerCase();
        return name.indexOf(q) !== -1;
      });
      list.forEach(function (s) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'create-staff-user-item' + (staffInput.value === String(s.id) ? ' selected' : '');
        btn.setAttribute('data-id', s.id);
        btn.textContent = s.name || s.hubspot_owner_id || 'Staff ' + s.id;
        btn.addEventListener('click', function () {
          staffInput.value = s.id;
          if (staffSelectedEl) {
            staffSelectedEl.textContent = 'Selected: ' + (s.name || s.id);
            staffSelectedEl.hidden = false;
          }
          renderStaffList(staffSearchInput ? staffSearchInput.value : '');
        });
        staffListEl.appendChild(btn);
      });
    }

    function loadStaffAndHolidays() {
      if (loadingEl) loadingEl.hidden = false;
      listEl.hidden = true;
      emptyEl.hidden = true;
      Promise.all([
        fetch(API + '/staff').then(parseJsonResponse),
        fetch(API + '/holidays').then(parseJsonResponse),
      ]).then(function (results) {
        if (loadingEl) loadingEl.hidden = true;
        var staffData = results[0];
        var holidaysData = results[1];
        if (staffData.error) {
          if (viewsEl) viewsEl.hidden = false;
          if (listWrap) listWrap.hidden = false;
          if (calendarWrap) calendarWrap.hidden = true;
          listEl.hidden = false;
          listEl.innerHTML = '<li class="error">' + (staffData.error || 'Failed to load staff') + '</li>';
          if (emptyEl) emptyEl.hidden = true;
          return;
        }
        staffCache = staffData.staff || [];
        staffForSelect = dedupeAndSortStaff(staffCache);
        holidaysCache = holidaysData.holidays || [];
        if (viewsEl) viewsEl.hidden = false;
        listEl.hidden = false;
        renderCalendar();
        renderList();
      }).catch(function (e) {
        if (loadingEl) loadingEl.hidden = true;
        if (viewsEl) viewsEl.hidden = false;
        if (listWrap) listWrap.hidden = false;
        if (calendarWrap) calendarWrap.hidden = true;
        listEl.hidden = false;
        listEl.innerHTML = '<li class="error">' + escapeHtml(e.message || 'Failed to load') + '</li>';
        if (emptyEl) emptyEl.hidden = true;
      });
    }

    function isDateInRange(dayStr, startStr, endStr) {
      if (!dayStr || !startStr || !endStr) return false;
      return dayStr >= startStr && dayStr <= endStr;
    }

    function formatMonthLabel(d) {
      return d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
    }

    function renderCalendar() {
      if (!calendarGridEl || !monthLabelEl) return;
      var y = currentCalendarMonth.getFullYear();
      var m = currentCalendarMonth.getMonth();
      monthLabelEl.textContent = formatMonthLabel(currentCalendarMonth);
      var first = new Date(y, m, 1);
      var last = new Date(y, m + 1, 0);
      var startDay = first.getDay();
      var daysInMonth = last.getDate();
      var grid = [];
      var weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
      weekDays.forEach(function (d) {
        grid.push({ head: true, text: d });
      });
      var pad = startDay;
      while (pad--) grid.push({ other: true, day: 0 });
      for (var d = 1; d <= daysInMonth; d++) {
        var dateStr = y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
        grid.push({ other: false, day: d, dateStr: dateStr });
      }
      var totalCells = Math.ceil(grid.length / 7) * 7;
      while (grid.length < totalCells) grid.push({ other: true, day: 0 });
      calendarGridEl.innerHTML = '';
      grid.forEach(function (cell, idx) {
        if (cell.head) {
          var th = document.createElement('div');
          th.className = 'holidays-calendar-day-head';
          th.textContent = cell.text;
          calendarGridEl.appendChild(th);
          return;
        }
        var cellEl = document.createElement('div');
        cellEl.className = 'holidays-calendar-day' + (cell.other ? ' other-month' : '');
        if (cell.other && cell.day === 0) {
          calendarGridEl.appendChild(cellEl);
          return;
        }
        var dayNum = cell.day;
        var dateStr = cell.dateStr;
        var onThisDay = holidaysCache.filter(function (h) {
          return isDateInRange(dateStr, h.start_date, h.end_date);
        });
        var namesEl = document.createElement('div');
        namesEl.className = 'holidays-calendar-day-names';
        onThisDay.forEach(function (h) {
          var staff = staffById(h.staff_id);
          var name = staff ? staff.name : ('Staff ' + h.staff_id);
          var span = document.createElement('span');
          span.className = 'holidays-calendar-day-name';
          span.textContent = name;
          span.title = (h.label ? h.label + ' – ' : '') + h.start_date + ' to ' + h.end_date;
          namesEl.appendChild(span);
        });
        var numWrap = document.createElement('div');
        numWrap.className = 'holidays-calendar-day-num';
        var numSpan = document.createElement('span');
        numSpan.textContent = dayNum || '';
        numWrap.appendChild(numSpan);
        if (!cell.other) {
          var addBtn = document.createElement('button');
          addBtn.type = 'button';
          addBtn.className = 'holidays-calendar-day-add';
          addBtn.title = 'Add holiday starting this day';
          addBtn.textContent = '+';
          addBtn.addEventListener('click', function () {
            openAddForm(dateStr);
          });
          numWrap.appendChild(addBtn);
        }
        cellEl.appendChild(numWrap);
        cellEl.appendChild(namesEl);
        calendarGridEl.appendChild(cellEl);
      });
    }

    function renderList() {
      listEl.innerHTML = '';
      if (emptyEl) emptyEl.hidden = true;
      var sorted = holidaysCache.slice().sort(function (a, b) {
        var da = (a.start_date || '').localeCompare(b.start_date || '');
        if (da !== 0) return da;
        var na = (staffById(a.staff_id) || {}).name || a.staff_id || '';
        var nb = (staffById(b.staff_id) || {}).name || b.staff_id || '';
        return String(na).toLowerCase().localeCompare(String(nb).toLowerCase());
      });
      if (sorted.length === 0) {
        if (emptyEl) emptyEl.hidden = false;
        return;
      }
      var currentMonthKey = null;
      sorted.forEach(function (h) {
        var startStr = h.start_date || '';
        var monthKey = startStr.length >= 7 ? startStr.slice(0, 7) : '';
        if (monthKey && monthKey !== currentMonthKey) {
          currentMonthKey = monthKey;
          var d = new Date(monthKey + '-01');
          var monthTitle = d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
          var headLi = document.createElement('li');
          headLi.className = 'holidays-list-month-head';
          headLi.textContent = monthTitle;
          listEl.appendChild(headLi);
        }
        var li = document.createElement('li');
        var staff = staffById(h.staff_id);
        var name = staff ? staff.name : ('Staff ' + h.staff_id);
        var labelPart = h.label ? ' – ' + h.label : '';
        var dateRangeText = formatHolidayDateRange(h.start_date, h.end_date);
        li.innerHTML = '<span><strong>' + escapeHtml(name) + '</strong> <span class="holiday-dates">' + dateRangeText + '</span>' + escapeHtml(labelPart) + '</span><span class="holiday-actions"><button type="button" class="btn btn-secondary holiday-edit" data-id="' + escapeHtml(h.id) + '">Edit</button><button type="button" class="btn btn-secondary holiday-delete" data-id="' + escapeHtml(h.id) + '">Delete</button></span>';
        li.querySelector('.holiday-edit').addEventListener('click', function () { openEditForm(h); });
        li.querySelector('.holiday-delete').addEventListener('click', function () { deleteHoliday(h.id); });
        listEl.appendChild(li);
      });
    }

    function formatHolidayDateRange(startStr, endStr) {
      if (!startStr || !endStr) return (startStr || '') + (startStr && endStr ? ' to ' : '') + (endStr || '');
      var start = new Date(startStr.slice(0, 10));
      var end = new Date(endStr.slice(0, 10));
      if (isNaN(start.getTime()) || isNaN(end.getTime())) return escapeHtml(startStr) + ' to ' + escapeHtml(endStr);
      var opts = { day: 'numeric', month: 'long' };
      var sameYear = start.getFullYear() === end.getFullYear();
      var from = start.toLocaleDateString('en-GB', opts);
      var to = end.toLocaleDateString('en-GB', sameYear ? opts : { day: 'numeric', month: 'long', year: 'numeric' });
      return from + (sameYear && from === to ? '' : ' – ' + to);
    }

    function escapeHtml(s) {
      if (s == null) return '';
      var div = document.createElement('div');
      div.textContent = s;
      return div.innerHTML;
    }

    function openAddForm(prefillStartDate) {
      formTitle.textContent = 'Add holiday';
      editIdInput.value = '';
      staffInput.value = '';
      if (staffSearchInput) staffSearchInput.value = '';
      if (staffSearchInput) staffSearchInput.disabled = false;
      if (staffListEl) staffListEl.hidden = false;
      if (staffSelectedEl) { staffSelectedEl.textContent = ''; staffSelectedEl.hidden = true; }
      startInput.value = prefillStartDate || '';
      endInput.value = prefillStartDate || '';
      labelInput.value = '';
      renderStaffList('');
      formWrap.hidden = false;
      if (addBtn) addBtn.disabled = true;
    }

    function openEditForm(h) {
      formTitle.textContent = 'Edit holiday';
      editIdInput.value = h.id;
      staffInput.value = h.staff_id;
      if (staffSearchInput) { staffSearchInput.value = ''; staffSearchInput.disabled = true; }
      if (staffListEl) staffListEl.hidden = true;
      var staff = staffById(h.staff_id);
      var name = staff ? staff.name : ('Staff ' + h.staff_id);
      if (staffSelectedEl) { staffSelectedEl.textContent = 'Staff: ' + name; staffSelectedEl.hidden = false; }
      startInput.value = h.start_date || '';
      endInput.value = h.end_date || '';
      labelInput.value = h.label || '';
      formWrap.hidden = false;
      if (addBtn) addBtn.disabled = true;
    }

    function deleteHoliday(id) {
      showConfirm('Delete this holiday?').then(function (confirmed) {
        if (!confirmed) return;
        fetch(API + '/holidays/' + encodeURIComponent(id), { method: 'DELETE' })
          .then(function (res) {
            if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
            loadStaffAndHolidays();
            staffTable(); // Refresh staff so on_holiday_today is correct
          })
          .catch(function (e) { alert('Error: ' + e.message); });
      });
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var id = editIdInput.value.trim();
      var staffId = staffInput.value.trim();
      var payload = {
        staff_id: staffId,
        start_date: startInput.value,
        end_date: endInput.value,
        label: labelInput.value.trim(),
      };
      if (!payload.start_date || !payload.end_date) {
        alert('Please set From and To dates.');
        return;
      }
      if (!id && !staffId) {
        alert('Please select a staff member.');
        return;
      }
      var url = id ? API + '/holidays/' + encodeURIComponent(id) : API + '/holidays';
      var method = id ? 'PATCH' : 'POST';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving…';
      }
      fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
          formWrap.hidden = true;
          if (addBtn) addBtn.disabled = false;
          loadStaffAndHolidays();
          staffTable();
        })
        .catch(function (e) { alert('Error: ' + e.message); })
        .finally(function () {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Confirm';
          }
        });
    });

    if (staffSearchInput) {
      staffSearchInput.addEventListener('input', function () {
        renderStaffList(staffSearchInput.value);
      });
    }
    function setView(mode) {
      viewMode = mode;
      if (tabCalendarBtn) tabCalendarBtn.classList.toggle('active', mode === 'calendar');
      if (tabListBtn) tabListBtn.classList.toggle('active', mode === 'list');
      if (tabCalendarBtn) tabCalendarBtn.setAttribute('aria-selected', mode === 'calendar');
      if (tabListBtn) tabListBtn.setAttribute('aria-selected', mode === 'list');
      if (calendarWrap) calendarWrap.hidden = mode !== 'calendar';
      if (listWrap) listWrap.hidden = mode !== 'list';
      if (mode === 'list') renderList();
    }

    if (prevMonthBtn) {
      prevMonthBtn.addEventListener('click', function () {
        currentCalendarMonth = new Date(currentCalendarMonth.getFullYear(), currentCalendarMonth.getMonth() - 1);
        renderCalendar();
      });
    }
    if (nextMonthBtn) {
      nextMonthBtn.addEventListener('click', function () {
        currentCalendarMonth = new Date(currentCalendarMonth.getFullYear(), currentCalendarMonth.getMonth() + 1);
        renderCalendar();
      });
    }
    if (tabCalendarBtn) {
      tabCalendarBtn.addEventListener('click', function () { setView('calendar'); });
    }
    if (tabListBtn) {
      tabListBtn.addEventListener('click', function () { setView('list'); });
    }

    formCancelBtn.addEventListener('click', function () {
      formWrap.hidden = true;
      if (addBtn) addBtn.disabled = false;
    });
    addBtn.addEventListener('click', function () { openAddForm(); });
    closeBtn.addEventListener('click', closeModal);
    modal.querySelector('.modal-backdrop').addEventListener('click', closeModal);
    document.getElementById('holidays-btn').addEventListener('click', openModal);
  }

  function refreshLeadsButton() {
    var btn = document.getElementById('refresh-leads-btn');
    if (!btn) return;
    var pollInterval = null;

    function stopPolling() {
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    }

    function pollForCompletion() {
      var deadline = Date.now() + 120000; // stop after 2 min
      pollInterval = setInterval(function () {
        if (Date.now() > deadline) {
          stopPolling();
          btn.textContent = 'Refresh leads';
          btn.disabled = false;
          return;
        }
        fetch(API + '/activity-log?limit=5', { credentials: 'same-origin' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            if (!data || !data.entries || !data.entries.length) return;
            var last = data.entries[data.entries.length - 1];
            if (last.event === 'refresh_leads') {
              stopPolling();
              var updated = (last.details && last.details.updated) || 0;
              btn.textContent = 'Updated ' + updated + ' staff. Done.';
              btn.title = '';
              staffTable();
              if (typeof activityLog === 'function') activityLog();
              setTimeout(function () {
                btn.textContent = 'Refresh leads';
                btn.disabled = false;
              }, 2000);
            } else if (last.event === 'refresh_error') {
              stopPolling();
              btn.textContent = 'Refresh leads';
              btn.disabled = false;
              alert('Refresh failed. Check the Data tab for details.');
              if (typeof activityLog === 'function') activityLog();
            }
          });
      }, 3000);
    }

    btn.addEventListener('click', function () {
      btn.disabled = true;
      btn.textContent = 'Refreshing…';
      stopPolling();
      fetch(API + '/staff/refresh-leads', { method: 'POST', credentials: 'same-origin' })
        .then(function (r) {
          var ct = (r.headers.get('Content-Type') || '').toLowerCase();
          if (!r.ok) {
            if (r.status === 401) return Promise.reject(new Error('Unauthorized'));
            return r.text().then(function (text) {
              try {
                var data = JSON.parse(text);
                return Promise.reject(new Error(data.error || 'Refresh failed (' + r.status + ')'));
              } catch (_) {
                return Promise.reject(new Error('Refresh failed. Try signing in again or try again later.'));
              }
            });
          }
          if (ct.indexOf('application/json') === -1) {
            return Promise.reject(new Error('Refresh failed. The server returned an unexpected response. Try signing in again.'));
          }
          return r.json();
        })
        .then(function (data) {
          if (data.status === 'started' || data.status === 'already_running') {
            btn.textContent = 'Refresh running…';
            pollForCompletion();
            return;
          }
          if (data.error && (data.updated === 0 || data.updated == null) && !data.status) {
            alert('Error: ' + data.error);
            btn.textContent = 'Refresh leads';
            btn.disabled = false;
            return;
          }
          var msg = 'Updated ' + (data.updated || 0) + ' staff member(s).';
          if (data.errors && data.errors.length) {
            msg += ' ' + data.errors.length + ' error(s).';
            var firstErr = data.errors[0] && data.errors[0].error;
            if (firstErr) {
              var short = firstErr.length > 50 ? firstErr.slice(0, 47) + '…' : firstErr;
              msg += ' First: ' + short;
            }
          }
          btn.textContent = msg;
          if (data.errors && data.errors.length > 0) {
            btn.title = data.errors.map(function (e) {
              return (e.owner_id || e.staff_id || '?') + ': ' + (e.error || 'Unknown');
            }).join('\n');
          } else {
            btn.title = '';
          }
          setTimeout(function () {
            btn.textContent = 'Refresh leads';
            btn.disabled = false;
            staffTable();
            activityLog();
          }, 1500);
        })
        .catch(function (e) {
          var msg = e.message || String(e);
          if (msg.indexOf('JSON') !== -1 || msg.indexOf('<') !== -1) {
            msg = 'Refresh failed. Try signing in again or try again later.';
          }
          alert('Error: ' + msg);
          btn.disabled = false;
          btn.textContent = 'Refresh leads';
          stopPolling();
        });
    });
  }

  function activityLog() {
    var listEl = document.getElementById('activity-log-list');
    var loadingEl = document.getElementById('activity-log-loading');
    var errEl = document.getElementById('activity-log-error');
    if (!listEl) return;
    if (loadingEl) loadingEl.hidden = false;
    if (errEl) errEl.hidden = true;
    listEl.innerHTML = '';
    fetch(API + '/activity-log?limit=50', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (loadingEl) loadingEl.hidden = true;
        var entries = data.entries || [];
        if (entries.length === 0) {
          listEl.innerHTML = '<p class="text-muted">No activity yet. Background refresh runs every 6 minutes. Click Refresh leads on Configuration to log manual refreshes.</p>';
          return;
        }
        entries.forEach(function (e) {
          var row = document.createElement('div');
          row.className = 'activity-log-row';
          var time = document.createElement('span');
          time.className = 'activity-log-time';
          time.textContent = e.time || '';
          var msg = document.createElement('span');
          msg.className = 'activity-log-msg';
          msg.textContent = e.message || e.event || '';
          row.appendChild(time);
          row.appendChild(msg);
          if (e.details && Object.keys(e.details).length) {
            var details = document.createElement('span');
            details.className = 'activity-log-details';
            details.textContent = ' ' + JSON.stringify(e.details);
            row.appendChild(details);
          }
          listEl.appendChild(row);
        });
      })
      .catch(function (e) {
        if (loadingEl) loadingEl.hidden = true;
        if (errEl) {
          errEl.textContent = e.message || 'Failed to load activity log';
          errEl.hidden = false;
        }
      });
  }

  function createStaffModal() {
    var modal = document.getElementById('create-staff-modal');
    var formWrap = document.getElementById('create-staff-form-wrap');
    var form = document.getElementById('create-staff-form');
    var ownerInput = document.getElementById('create-staff-owner');
    var searchInput = document.getElementById('create-staff-search');
    var userListEl = document.getElementById('create-staff-user-list');
    var noMatchEl = document.getElementById('create-staff-no-match');
    var teamsWrap = document.getElementById('create-staff-teams-wrap');
    var teamsContainer = document.getElementById('create-staff-teams');
    var loadingEl = document.getElementById('create-staff-loading');
    var emptyEl = document.getElementById('create-staff-empty');
    var errorEl = document.getElementById('create-staff-error');
    var submitBtn = document.getElementById('create-staff-submit');
    var availableOwners = [];
    var selectedTeamsForCreate = [];

    function getDisplayName(o) {
      return [o.firstName, o.lastName].filter(Boolean).join(' ') || o.email || String(o.id);
    }

    function renderUserList() {
      var q = (searchInput && searchInput.value) ? searchInput.value.trim().toLowerCase() : '';
      var filtered = q
        ? availableOwners.filter(function (o) {
            return getDisplayName(o).toLowerCase().indexOf(q) !== -1 || (o.email || '').toLowerCase().indexOf(q) !== -1;
          })
        : availableOwners.slice();
      var selectedId = (ownerInput && ownerInput.value) || '';
      if (!userListEl) return;
      userListEl.innerHTML = '';
      if (noMatchEl) noMatchEl.hidden = filtered.length > 0;
      filtered.forEach(function (o) {
        var id = String(o.id);
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'create-staff-user-item' + (selectedId === id ? ' selected' : '');
        btn.setAttribute('role', 'option');
        btn.setAttribute('aria-selected', selectedId === id ? 'true' : 'false');
        btn.textContent = getDisplayName(o);
        btn.dataset.ownerId = id;
        btn.addEventListener('click', function () {
          ownerInput.value = id;
          var items = userListEl.querySelectorAll('.create-staff-user-item');
          items.forEach(function (el) {
            el.classList.toggle('selected', el.dataset.ownerId === id);
            el.setAttribute('aria-selected', el.dataset.ownerId === id ? 'true' : 'false');
          });
          if (teamsWrap) teamsWrap.hidden = false;
          renderCreateStaffTeams();
        });
        userListEl.appendChild(btn);
      });
    }

    function renderCreateStaffTeams() {
      if (!teamsContainer) return;
      teamsContainer.innerHTML = '';
      LEAD_TEAM_KEYS.forEach(function (teamName) {
        var shortName = shortTeamName(teamName);
        var isSelected = selectedTeamsForCreate.indexOf(teamName) !== -1;
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'create-staff-team-btn' + (isSelected ? ' selected' : '');
        btn.textContent = isSelected ? '\u2713 ' + shortName : '+ ' + shortName;
        btn.title = isSelected ? 'Remove from ' + teamName : 'Add to ' + teamName;
        btn.addEventListener('click', function () {
          var i = selectedTeamsForCreate.indexOf(teamName);
          if (i === -1) {
            selectedTeamsForCreate.push(teamName);
          } else {
            selectedTeamsForCreate.splice(i, 1);
          }
          renderCreateStaffTeams();
        });
        teamsContainer.appendChild(btn);
      });
    }

    function openModal() {
      modal.hidden = false;
      formWrap.hidden = true;
      emptyEl.hidden = true;
      availableOwners = [];
      selectedTeamsForCreate = [];
      if (searchInput) searchInput.value = '';
      if (ownerInput) ownerInput.value = '';
      if (noMatchEl) noMatchEl.hidden = true;
      if (teamsWrap) teamsWrap.hidden = true;
      if (userListEl) userListEl.innerHTML = '';
      if (teamsContainer) teamsContainer.innerHTML = '';
      if (errorEl) { errorEl.hidden = true; errorEl.textContent = ''; }
      if (loadingEl) loadingEl.hidden = false;
      fetch(API + '/owners')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (loadingEl) loadingEl.hidden = true;
          if (data.error) {
            if (userListEl) userListEl.innerHTML = '<p class="create-staff-no-match">Error: ' + (data.error || '').replace(/</g, '&lt;') + '</p>';
            formWrap.hidden = false;
            emptyEl.hidden = true;
            return;
          }
          var owners = data.owners || [];
          var existingOwnerIds = {};
          staffCache.forEach(function (s) {
            var id = s.hubspot_owner_id != null ? String(s.hubspot_owner_id) : '';
            if (id) existingOwnerIds[id] = true;
          });
          availableOwners = owners.filter(function (o) {
            var id = o.id != null ? String(o.id) : '';
            return id && !existingOwnerIds[id];
          });
          availableOwners.sort(function (a, b) {
            var hasNameA = !!(a.firstName || a.lastName);
            var hasNameB = !!(b.firstName || b.lastName);
            if (hasNameA !== hasNameB) return hasNameB ? 1 : -1; // named users first
            var da = getDisplayName(a).toLowerCase();
            var db = getDisplayName(b).toLowerCase();
            return da.localeCompare(db);
          });
          if (availableOwners.length === 0) {
            emptyEl.hidden = false;
            formWrap.hidden = true;
          } else {
            formWrap.hidden = false;
            emptyEl.hidden = true;
            renderUserList();
          }
        })
        .catch(function (e) {
          if (loadingEl) loadingEl.hidden = true;
          if (userListEl) userListEl.innerHTML = '<p class="create-staff-no-match">Failed to load users.</p>';
          formWrap.hidden = false;
          emptyEl.hidden = true;
        });
    }

    function closeModal() {
      modal.hidden = true;
    }

    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var ownerId = ownerInput && ownerInput.value ? ownerInput.value.trim() : '';
        if (!ownerId) {
          alert('Please choose a user from the list.');
          return;
        }
        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating…';
        fetch(API + '/staff', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            hubspot_owner_id: ownerId,
            lead_teams: selectedTeamsForCreate,
          }),
        })
          .then(function (r) {
            return r.json().then(function (d) { return { status: r.status, data: d }; }, function () {
            return { status: r.status, data: { error: 'Request failed (status ' + r.status + ')' } };
          });
          })
          .then(function (res) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Create staff member';
            if (res.status === 201 && res.data.staff) {
              if (errorEl) { errorEl.hidden = true; errorEl.textContent = ''; }
              var newStaff = res.data.staff;
              newStaff.call_minutes_last_120 = newStaff.call_minutes_last_120 != null ? newStaff.call_minutes_last_120 : 0;
              newStaff.on_holiday_today = newStaff.on_holiday_today || false;
              staffCache.push(newStaff);
              renderStaffTableFromCache();
              closeModal();
              staffTable();
              if (res.data.lead_teams_warning) {
                alert('Staff member created, but lead teams could not be saved. Please edit the staff member to assign teams.\n\n' + res.data.lead_teams_warning);
              }
              return;
            }
            var msg = (res.data && res.data.error) ? res.data.error : 'Failed to create staff member';
            if (errorEl) {
              errorEl.textContent = msg;
              errorEl.hidden = false;
            }
            alert(msg);
          })
          .catch(function (e) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Create staff member';
            var msg = 'Error: ' + (e.message || 'Request failed');
            if (errorEl) {
              errorEl.textContent = msg;
              errorEl.hidden = false;
            }
            alert(msg);
          });
      });
    }
    if (searchInput) {
      searchInput.addEventListener('input', renderUserList);
      searchInput.addEventListener('keyup', renderUserList);
    }
    document.getElementById('create-staff-cancel').addEventListener('click', closeModal);
    document.querySelector('.create-staff-close').addEventListener('click', closeModal);
    if (modal.querySelector('.modal-backdrop')) {
      modal.querySelector('.modal-backdrop').addEventListener('click', closeModal);
    }
    document.getElementById('create-staff-btn').addEventListener('click', openModal);
  }

  tabs();
  // Load only the default tab (Staff Management) on init; other tabs load when selected
  staffTable();
  renderUnallocatedGauges();
  staffSearch();
  holidaysModal();
  createStaffModal();
  refreshLeadsButton();
  dryRunForm();
  // activityLog() and leadTeamsTable() run when user clicks Data / Team Management tab

  // Auto-refresh lead teams (Unallocated, etc.), gauges, and staff + call activity every 5 minutes
  setInterval(function () {
    leadTeamsTable();
    staffTable();
    renderUnallocatedGauges();
  }, 5 * 60 * 1000);
})();
