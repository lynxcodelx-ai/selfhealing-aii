/* ═══════════════════════════════════════════════════════════════════
   Self-Healing AI Dashboard — Frontend Logic
   ═══════════════════════════════════════════════════════════════════ */

// ── State ──
let ws = null;
let reconnectTimer = null;
let currentIncidentId = null;
let incidents = {};

// ── WebSocket Connection ──

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        const el = document.getElementById('connectionStatus');
        el.className = 'connection-status connected';
        el.querySelector('.text').textContent = 'Connected';
        console.log('[WS] Connected');
    };

    ws.onclose = () => {
        const el = document.getElementById('connectionStatus');
        el.className = 'connection-status disconnected';
        el.querySelector('.text').textContent = 'Disconnected';
        console.log('[WS] Disconnected — reconnecting in 2s');
        reconnectTimer = setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error('[WS] Error:', err);
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleEvent(msg);
        } catch (e) {
            console.error('[WS] Parse error:', e);
        }
    };
}

// ── Event Handling ──

function handleEvent(msg) {
    const { type, data, timestamp } = msg;

    switch (type) {
        case 'workflow_started':
            addFeedEvent('info', '▶️ Workflow Started', `${data.name}${data.fault_type ? ` [Fault: ${data.fault_type}]` : ''}`, timestamp, data);
            resetPipeline();
            break;

        case 'step_started':
            addFeedEvent('info', `⏳ Step: ${data.step_name}`, 'Executing...', timestamp);
            break;

        case 'step_completed':
            addFeedEvent('success', `✅ ${data.step_name}`, `Completed in ${data.duration_ms?.toFixed(0)}ms`, timestamp);
            break;

        case 'step_failed':
            addFeedEvent('error', `❌ ${data.step_name} FAILED`, `${data.error_type}: ${data.error_message}`, timestamp, data);
            break;

        case 'workflow_completed':
            addFeedEvent('success', '🎉 Workflow Completed', data.name, timestamp);
            refreshStats();
            break;

        case 'incident_created':
            addFeedEvent('error', '🚨 Incident Created', `${data.workflow_name} — ${data.error_message}`, timestamp, data);
            incidents[data.incident_id] = data;
            setPipelineStage('detect', 'complete');
            setPipelineStage('diagnose', 'active');
            refreshIncidents();
            showIncidentDetail(data.incident_id);
            break;

        case 'incident_updated':
            if (data.status === 'diagnosing') {
                addFeedEvent('info', '🧠 Diagnosing...', 'AI analyzing root cause', timestamp);
                setPipelineStage('diagnose', 'active');
            } else if (data.status === 'healing') {
                addFeedEvent('healing', '💊 Generating Fix...', 'Synthesizing corrective action', timestamp);
                setPipelineStage('heal', 'active');
            } else if (data.status === 'approved') {
                addFeedEvent('success', '👍 Approved', 'Human approved the fix', timestamp);
            }
            refreshIncidentDetail();
            refreshIncidents();
            break;

        case 'incident_diagnosed':
            const diag = data.diagnosis;
            addFeedEvent('info', '🧠 Diagnosis Complete',
                `Root cause: ${diag.root_cause}\nCategory: ${diag.category} | Confidence: ${(diag.confidence * 100).toFixed(0)}%`,
                timestamp, data);
            setPipelineStage('diagnose', 'complete');
            setPipelineStage('heal', 'active');
            refreshIncidentDetail();
            break;

        case 'healing_proposed':
            const action = data.action;
            addFeedEvent('healing', '💊 Fix Proposed',
                `${action.description}\nConfidence: ${(action.confidence * 100).toFixed(0)}%${data.auto_applicable ? ' — Auto-approving' : ' — Awaiting approval'}`,
                timestamp, data);
            setPipelineStage('heal', 'complete');
            if (data.auto_applicable) {
                setPipelineStage('retry', 'active');
            }
            refreshIncidentDetail();
            break;

        case 'retry_started':
            addFeedEvent('info', '🔁 Retrying...', `Attempt #${data.retry_count}`, timestamp);
            setPipelineStage('retry', 'active');
            break;

        case 'retry_payload':
            addFeedEvent('info', '📦 Payload Patched', 'Applying corrected payload', timestamp, data);
            break;

        case 'incident_resolved':
            addFeedEvent('success', '✅ INCIDENT RESOLVED',
                `Healed in ${data.retry_count} attempt(s) | Resolution time: ${(data.resolution_time_ms / 1000).toFixed(1)}s`,
                timestamp);
            setPipelineStage('retry', 'complete');
            showToast('Incident resolved successfully! 🎉', 'success');
            refreshStats();
            refreshIncidents();
            refreshIncidentDetail();
            break;

        case 'retry_failed':
            addFeedEvent('error', '❌ Retry Failed',
                data.error || `Attempt failed. Status: ${data.status}`,
                timestamp);
            if (data.status === 'failed') {
                setPipelineStage('retry', 'failed');
            }
            refreshIncidents();
            refreshIncidentDetail();
            break;

        case 'demo_started':
            addFeedEvent('info', '🎬 Demo Started', data.message, timestamp);
            break;

        default:
            console.log('[Event]', type, data);
    }
}

// ── Feed Management ──

function addFeedEvent(type, title, body, timestamp, data = null) {
    const feed = document.getElementById('eventFeed');
    const empty = feed.querySelector('.event-empty');
    if (empty) empty.remove();

    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

    const el = document.createElement('div');
    el.className = `event-item event-${type}`;
    if (data && data.incident_id) {
        el.onclick = () => showIncidentDetail(data.incident_id);
        el.style.cursor = 'pointer';
    }

    el.innerHTML = `
        <div class="event-time">${time}</div>
        <div class="event-title">${title}</div>
        <div class="event-body">${escapeHtml(body).replace(/\n/g, '<br>')}</div>
    `;

    feed.insertBefore(el, feed.firstChild);

    // Keep max 100 events
    while (feed.children.length > 100) {
        feed.removeChild(feed.lastChild);
    }
}

function clearFeed() {
    const feed = document.getElementById('eventFeed');
    feed.innerHTML = '<div class="event-empty"><p>Feed cleared. Run a workflow to begin.</p></div>';
}

// ── Pipeline Visualization ──

function resetPipeline() {
    ['detect', 'diagnose', 'heal', 'retry'].forEach(stage => {
        const el = document.getElementById(`stage-${stage}`);
        if (el) el.className = 'pipeline-stage';
    });
}

function setPipelineStage(stage, state) {
    const el = document.getElementById(`stage-${stage}`);
    if (!el) return;

    // Remove active from all stages if setting a new active
    if (state === 'active') {
        document.querySelectorAll('.pipeline-stage.active').forEach(s => {
            if (s.id !== `stage-${stage}`) {
                // Only remove active if it hasn't been completed
                if (!s.classList.contains('complete')) {
                    s.classList.remove('active');
                }
            }
        });
    }

    el.className = `pipeline-stage ${state}`;
}

// ── API Calls ──

async function runFullDemo() {
    const workflow = document.getElementById('workflowSelect').value;
    const fault = document.getElementById('faultSelect').value;

    const btn = document.getElementById('btnInjectAndRun');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span> Running...';

    try {
        const res = await fetch('/api/demo/full-cycle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})  // params are query string
        });

        // Use query params
        const url = `/api/demo/full-cycle?workflow_type=${workflow}&fault_type=${fault}`;
        const resp = await fetch(url, { method: 'POST' });
        const data = await resp.json();

        if (data.incident_id) {
            currentIncidentId = data.incident_id;
        }
    } catch (e) {
        showToast('Error running demo: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">🧪</span> Inject Fault & Run';
    }
}

async function runNormal() {
    const workflow = document.getElementById('workflowSelect').value;

    const btn = document.getElementById('btnRunNormal');
    btn.disabled = true;

    try {
        const res = await fetch('/api/workflows/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workflow_type: workflow,
                fault_type: '',
                payload: {}
            })
        });
        const data = await res.json();
        refreshStats();
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function quickDemo(workflow, fault) {
    document.getElementById('workflowSelect').value = workflow;
    document.getElementById('faultSelect').value = fault;
    await runFullDemo();
}

async function approveIncident(incidentId) {
    try {
        const res = await fetch(`/api/incidents/${incidentId}/approve`, { method: 'POST' });
        const data = await res.json();
        showToast(data.success ? 'Fix approved — retrying!' : 'Retry failed', data.success ? 'success' : 'error');
        refreshIncidentDetail();
        refreshIncidents();
        refreshStats();
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

async function rejectIncident(incidentId) {
    try {
        await fetch(`/api/incidents/${incidentId}/reject`, { method: 'POST' });
        showToast('Fix rejected', 'info');
        refreshIncidentDetail();
        refreshIncidents();
        refreshStats();
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

// ── Stats ──

async function refreshStats() {
    try {
        const res = await fetch('/api/stats');
        const stats = await res.json();
        document.getElementById('statWorkflows').textContent = stats.total_workflows_run;
        document.getElementById('statIncidents').textContent = stats.total_incidents;
        document.getElementById('statResolved').textContent = stats.total_resolved;
        document.getElementById('statFailed').textContent = stats.total_failed;
        document.getElementById('statUptime').textContent = stats.uptime_percentage + '%';
    } catch (e) {
        console.error('Failed to refresh stats:', e);
    }
}

// ── Incidents Table ──

async function refreshIncidents() {
    try {
        const res = await fetch('/api/incidents');
        const data = await res.json();
        const tbody = document.getElementById('incidentTableBody');

        if (!data.incidents || data.incidents.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-row">No incidents yet</td></tr>';
            return;
        }

        tbody.innerHTML = data.incidents.map(inc => `
            <tr>
                <td class="id-cell" onclick="showIncidentDetail('${inc.id}')">${inc.id}</td>
                <td>${escapeHtml(inc.workflow_name)}</td>
                <td>${escapeHtml(inc.failed_step)}</td>
                <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(inc.error_message)}">${escapeHtml(inc.error_message)}</td>
                <td><span class="status-badge status-${inc.status}">${inc.status}</span></td>
                <td>
                    ${inc.status === 'awaiting_approval' ?
                        `<button class="btn btn-success btn-sm" onclick="approveIncident('${inc.id}')">Approve</button>
                         <button class="btn btn-ghost btn-sm" onclick="rejectIncident('${inc.id}')">Reject</button>`
                        : '—'}
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to refresh incidents:', e);
    }
}

// ── Incident Detail ──

async function showIncidentDetail(incidentId) {
    currentIncidentId = incidentId;
    await refreshIncidentDetail();
}

async function refreshIncidentDetail() {
    if (!currentIncidentId) return;

    try {
        const res = await fetch(`/api/incidents/${currentIncidentId}`);
        if (!res.ok) return;
        const inc = await res.json();

        const detail = document.getElementById('incidentDetail');

        let html = `
            <div class="detail-section">
                <h4>Incident Info</h4>
                <div class="detail-field">
                    <span class="label">ID</span>
                    <span class="value">${inc.id}</span>
                </div>
                <div class="detail-field">
                    <span class="label">Status</span>
                    <span class="status-badge status-${inc.status}">${inc.status}</span>
                </div>
                <div class="detail-field">
                    <span class="label">Workflow</span>
                    <span class="value">${escapeHtml(inc.workflow_name)}</span>
                </div>
                <div class="detail-field">
                    <span class="label">Failed Step</span>
                    <span class="value">${escapeHtml(inc.failed_step)}</span>
                </div>
                <div class="detail-field">
                    <span class="label">Error</span>
                    <span class="value" style="color:var(--accent-red)">${escapeHtml(inc.error_message)}</span>
                </div>
                <div class="detail-field">
                    <span class="label">Retries</span>
                    <span class="value">${inc.retry_count}</span>
                </div>
            </div>
        `;

        // Diagnosis
        if (inc.diagnosis) {
            const d = inc.diagnosis;
            html += `
                <div class="detail-section">
                    <h4>🧠 Diagnosis</h4>
                    <div class="detail-field">
                        <span class="label">Root Cause</span>
                        <span class="value">${escapeHtml(d.root_cause)}</span>
                    </div>
                    <div class="detail-field">
                        <span class="label">Category</span>
                        <span class="status-badge status-diagnosed">${d.category}</span>
                    </div>
                    <div class="detail-field">
                        <span class="label">Confidence</span>
                        <span class="value" style="color:${d.confidence >= 0.8 ? 'var(--accent-green)' : 'var(--accent-yellow)'}">${(d.confidence * 100).toFixed(0)}%</span>
                    </div>
                    ${d.affected_field ? `<div class="detail-field"><span class="label">Affected Field</span><span class="value">${escapeHtml(d.affected_field)}</span></div>` : ''}
                    <div style="margin-top:8px;font-size:12px;color:var(--text-secondary);line-height:1.5">${escapeHtml(d.explanation)}</div>
                </div>
            `;
        }

        // Healing Action
        if (inc.healing_action) {
            const a = inc.healing_action;
            html += `
                <div class="detail-section">
                    <h4>💊 Healing Action</h4>
                    <div class="detail-field">
                        <span class="label">Type</span>
                        <span class="value">${escapeHtml(a.action_type)}</span>
                    </div>
                    <div class="detail-field">
                        <span class="label">Confidence</span>
                        <span class="value">${(a.confidence * 100).toFixed(0)}%</span>
                    </div>
                    <div style="margin-top:8px;font-size:12px;color:var(--text-secondary)">${escapeHtml(a.description)}</div>
            `;

            // Show payload diff
            if (Object.keys(a.payload_patch).length > 0) {
                html += `
                    <div style="margin-top:10px">
                        <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">PAYLOAD PATCH:</div>
                        <div class="json-block">${syntaxHighlight(JSON.stringify(a.payload_patch, null, 2))}</div>
                    </div>
                `;
            }

            if (a.patched_payload && Object.keys(a.patched_payload).length > 0) {
                html += `
                    <div style="margin-top:10px">
                        <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">CORRECTED PAYLOAD:</div>
                        <div class="json-block">${syntaxHighlight(JSON.stringify(a.patched_payload, null, 2))}</div>
                    </div>
                `;
            }

            html += `</div>`;
        }

        // Approval buttons
        if (inc.status === 'awaiting_approval') {
            html += `
                <div class="approval-buttons">
                    <button class="btn btn-success" onclick="approveIncident('${inc.id}')">✅ Approve & Retry</button>
                    <button class="btn btn-danger" onclick="rejectIncident('${inc.id}')">❌ Reject</button>
                </div>
            `;
        }

        // Timeline
        if (inc.timeline && inc.timeline.length > 0) {
            html += `
                <div class="detail-section" style="margin-top:16px">
                    <h4>📜 Timeline</h4>
                    <div class="timeline">
                        ${inc.timeline.map(t => {
                            let cls = '';
                            if (t.event.includes('✅') || t.event.includes('Resolved') || t.event.includes('Approved')) cls = 'tl-success';
                            else if (t.event.includes('❌') || t.event.includes('Failed') || t.event.includes('Rejected')) cls = 'tl-error';
                            else if (t.event.includes('Await') || t.event.includes('Warning')) cls = 'tl-warning';
                            return `
                                <div class="timeline-item ${cls}">
                                    <div class="timeline-time">${new Date(t.timestamp).toLocaleTimeString()}</div>
                                    <div class="timeline-event">${escapeHtml(t.event)}</div>
                                    ${t.details ? `<div class="timeline-details">${escapeHtml(t.details)}</div>` : ''}
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;
        }

        detail.innerHTML = html;
    } catch (e) {
        console.error('Failed to load incident detail:', e);
    }
}

// ── Utilities ──

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function syntaxHighlight(json) {
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        let cls = 'color: var(--accent-cyan)'; // number
        if (/^"/.test(match)) {
            if (/:$/.test(match)) {
                cls = 'color: var(--accent-purple)'; // key
            } else {
                cls = 'color: var(--accent-green)'; // string
            }
        } else if (/true|false/.test(match)) {
            cls = 'color: var(--accent-yellow)'; // boolean
        } else if (/null/.test(match)) {
            cls = 'color: var(--accent-red)'; // null
        }
        return `<span style="${cls}">${match}</span>`;
    });
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// ── Initialization ──

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    refreshStats();
    refreshIncidents();
});
