(function () {
  const API = '/api';
  var staffCache = [];

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
            var configTab = document.querySelector('.tab[data-tab="config"]');
            if (configTab) configTab.click();
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
      });
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
  }

  function renderCallActivityChart(staff) {
    const container = document.getElementById('call-activity-chart');
    const section = document.getElementById('call-activity-section');
    if (!container || !section) return;
    if (!staff || staff.length === 0) {
      section.hidden = true;
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
      fetch(API + '/staff').then(function (r) { return r.json(); }),
      fetch(API + '/staff/field-options/pause_leads').then(function (r) { return r.json(); }),
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
        renderCallActivityChart(staff);
        const pauseLeadsOptions = optionsData.options || [];
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
    var staffSelect = document.getElementById('holiday-staff');
    var startInput = document.getElementById('holiday-start');
    var endInput = document.getElementById('holiday-end');
    var labelInput = document.getElementById('holiday-label');
    var formTitle = document.querySelector('.holiday-form-title');
    var addBtn = document.getElementById('holiday-add-btn');
    var formCancelBtn = document.getElementById('holiday-form-cancel');
    var closeBtn = document.querySelector('.holidays-close');
    var staffCache = [];

    var loadingEl = document.getElementById('holidays-loading');

    function openModal() {
      modal.hidden = false;
      formWrap.hidden = true;
      editIdInput.value = '';
      loadStaffAndHolidays();
    }

    function closeModal() {
      modal.hidden = true;
      staffTable(); // Refresh staff so on_holiday_today is up to date when toggling availability
    }

    function staffById(id) {
      return staffCache.find(function (s) { return String(s.id) === String(id); }) || null;
    }

    function loadStaffAndHolidays() {
      if (loadingEl) loadingEl.hidden = false;
      listEl.hidden = true;
      emptyEl.hidden = true;
      Promise.all([
        fetch(API + '/staff').then(function (r) { return r.json(); }),
        fetch(API + '/holidays').then(function (r) { return r.json(); }),
      ]).then(function (results) {
        if (loadingEl) loadingEl.hidden = true;
        listEl.hidden = false;
        var staffData = results[0];
        var holidaysData = results[1];
        if (staffData.error) {
          listEl.innerHTML = '<li class="error">' + (staffData.error || 'Failed to load staff') + '</li>';
          emptyEl.hidden = true;
          return;
        }
        staffCache = staffData.staff || [];
        var holidays = holidaysData.holidays || [];
        while (staffSelect.options.length > 1) staffSelect.remove(1);
        staffCache.forEach(function (s) {
          var opt = document.createElement('option');
          opt.value = s.id;
          opt.textContent = s.name || s.id;
          staffSelect.appendChild(opt);
        });
        listEl.innerHTML = '';
        if (holidays.length === 0) {
          emptyEl.hidden = false;
        } else {
          emptyEl.hidden = true;
          holidays.forEach(function (h) {
            var li = document.createElement('li');
            var staff = staffById(h.staff_id);
            var name = staff ? staff.name : ('Staff ' + h.staff_id);
            var labelPart = h.label ? ' – ' + h.label : '';
            li.innerHTML = '<span><strong>' + escapeHtml(name) + '</strong> <span class="holiday-dates">' + escapeHtml(h.start_date) + ' to ' + escapeHtml(h.end_date) + '</span>' + escapeHtml(labelPart) + '</span><span class="holiday-actions"><button type="button" class="btn btn-secondary holiday-edit" data-id="' + escapeHtml(h.id) + '">Edit</button><button type="button" class="btn btn-secondary holiday-delete" data-id="' + escapeHtml(h.id) + '">Delete</button></span>';
            listEl.appendChild(li);
            li.querySelector('.holiday-edit').addEventListener('click', function () { openEditForm(h); });
            li.querySelector('.holiday-delete').addEventListener('click', function () { deleteHoliday(h.id); });
          });
        }
      }).catch(function (e) {
        if (loadingEl) loadingEl.hidden = true;
        listEl.hidden = false;
        listEl.innerHTML = '<li class="error">' + escapeHtml(e.message || 'Failed to load') + '</li>';
        emptyEl.hidden = true;
      });
    }

    function escapeHtml(s) {
      if (s == null) return '';
      var div = document.createElement('div');
      div.textContent = s;
      return div.innerHTML;
    }

    function openAddForm() {
      formTitle.textContent = 'Add holiday';
      editIdInput.value = '';
      staffSelect.value = staffCache.length ? staffSelect.options[1].value : '';
      startInput.value = '';
      endInput.value = '';
      labelInput.value = '';
      staffSelect.disabled = false;
      formWrap.hidden = false;
    }

    function openEditForm(h) {
      formTitle.textContent = 'Edit holiday';
      editIdInput.value = h.id;
      staffSelect.value = h.staff_id;
      staffSelect.disabled = true;
      startInput.value = h.start_date || '';
      endInput.value = h.end_date || '';
      labelInput.value = h.label || '';
      formWrap.hidden = false;
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
      var payload = {
        staff_id: staffSelect.value,
        start_date: startInput.value,
        end_date: endInput.value,
        label: labelInput.value.trim(),
      };
      if (!payload.start_date || !payload.end_date) {
        alert('Please set From and To dates.');
        return;
      }
      var url = id ? API + '/holidays/' + encodeURIComponent(id) : API + '/holidays';
      var method = id ? 'PATCH' : 'POST';
      fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || res.status); });
          formWrap.hidden = true;
          loadStaffAndHolidays();
          staffTable(); // Refresh staff so on_holiday_today is correct before next availability toggle
        })
        .catch(function (e) { alert('Error: ' + e.message); });
    });

    formCancelBtn.addEventListener('click', function () { formWrap.hidden = true; });
    addBtn.addEventListener('click', openAddForm);
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

  tabs();
  leadTeamsTable();
  staffTable();
  staffSearch();
  holidaysModal();
  refreshLeadsButton();
  dryRunForm();
  activityLog();

  // Auto-refresh lead teams (Unallocated, etc.) and staff + call activity every 5 minutes
  setInterval(function () {
    leadTeamsTable();
    staffTable();
  }, 5 * 60 * 1000);
})();
