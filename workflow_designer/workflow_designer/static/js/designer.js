(function () {
    'use strict';

    const nodesLayer = document.getElementById('canvas-nodes');
    const canvasInner = document.getElementById('canvas-inner');
    const canvasSvg = document.getElementById('canvas-svg');
    const freeformCanvas = document.getElementById('freeform-canvas');
    const rubberBand = document.getElementById('rubber-band');
    const propertiesPanelBody = document.getElementById('properties-panel-body');
    const flowIdInput = document.getElementById('flow-id-input');
    const errorContainer = document.getElementById('error-container');
    const emptyCanvasState = document.getElementById('canvas-empty-state');
    const previewBackdrop = document.getElementById('preview-backdrop');

    if (!nodesLayer || !canvasInner || !canvasSvg || !freeformCanvas || !rubberBand || !propertiesPanelBody || !flowIdInput || !errorContainer || !emptyCanvasState || !previewBackdrop) {
        return;
    }

    let nodes = [];   // { id: int, type: string, x: number, y: number, data: {} }
    let edges = [];   // { id: int, from: int, to: int }
    let nextId = 1;
    let selectedNodeId = null;
    let selectedEdgeId = null;
    let dragState = null;
    let connectState = null;
    let nextEdgeId = 1;
    let _rafPending = false;
    let _previewData = null;
    let _activeTab = 'flow';
    let _errorTimer = null;
    const expandedNodes = new Set(); // node IDs whose detail section is open

    const FLOW_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
    const NODE_META = {
        hl7_server: { label: 'HL7 Server', icon: 'bi bi-hdd-network' },
        hl7_transformer: { label: 'Transformer', icon: 'bi bi-shuffle' },
        hl7_sender: { label: 'HL7 Sender', icon: 'bi bi-send' },
        subscription_sender: { label: 'Subscription Sender', icon: 'fas fa-share-alt' },
    };
    const NODE_TYPES = Object.keys(NODE_META);
    const SINK_NODE_TYPES = ['hl7_sender', 'subscription_sender'];

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function defaultData(type) {
        if (type === 'hl7_server') {
            return {
                source_system: '',
                mllp_port: 2575,
                hl7_version: '2.5',
                sending_app: '',
                validation_flow: '',
                health_board: '',
                enable_message_store: true,
            };
        }
        if (type === 'hl7_transformer') {
            return { image_name: '' };
        }
        if (type === 'hl7_sender') {
            return {
                destination: 'MPI',
                mode: 'shared',
                destination_host: '',
                destination_port: 2576,
            };
        }
        if (type === 'subscription_sender') {
            return {
                health_board: '',
                peer_service: 'MPI',
                workflow_id: '',
                receiver_host: '',
                receiver_port: 2576,
                ack_timeout_seconds: 5,
                max_messages_per_minute: 30,
            };
        }
        return {};
    }

    function subtitleForNode(node) {
        if (node.type === 'hl7_server') {
            const source = node.data.source_system || 'Source system not set';
            return `${source} • Port ${node.data.mllp_port || 2575}`;
        }
        if (node.type === 'hl7_transformer') {
            return node.data.image_name || 'Transformer image not set';
        }
        if (node.type === 'hl7_sender') {
            if (node.data.mode === 'dedicated') {
                const host = node.data.destination_host || 'Host not set';
                const port = node.data.destination_port || 2576;
                return `Dedicated sender • ${host}:${port}`;
            }
            return `Shared sender • ${node.data.destination || 'MPI'}`;
        }
        if (node.type === 'subscription_sender') {
            const workflowId = node.data.workflow_id || 'Workflow ID not set';
            const host = node.data.receiver_host || 'Host not set';
            const port = node.data.receiver_port || 2576;
            return `${workflowId} • ${host}:${port}`;
        }
        return '';
    }

    function detailRowsForNode(node) {
        const d = node.data;
        const row = (label, value, missing) => {
            const v = (value == null || String(value).trim() === '') ? null : String(value);
            return `<div class="nd-row">
                <span class="nd-label">${esc(label)}</span>
                <span class="nd-value${v ? '' : ' nd-missing'}">${v ? esc(v) : (missing || '—')}</span>
            </div>`;
        };
        if (node.type === 'hl7_server') {
            return [
                row('Source System',        d.source_system, 'not set'),
                row('MLLP Port',            d.mllp_port),
                row('HL7 Version',          d.hl7_version),
                row('Sending App',          d.sending_app,   'not set'),
                row('Validation Flow',      d.validation_flow,'not set'),
                row('Health Board',         d.health_board,  'not set'),
                row('Enable Message Store', d.enable_message_store ? 'enabled' : 'disabled'),
            ].join('');
        }
        if (node.type === 'hl7_transformer') {
            return row('Image', d.image_name, 'not set');
        }
        if (node.type === 'hl7_sender') {
            const mode = d.mode === 'dedicated' ? 'Dedicated' : 'Shared';
            const dest = d.mode === 'dedicated'
                ? `${d.destination_host || '—'}:${d.destination_port || 2576}`
                : (d.destination || 'MPI');
            return [
                row('Mode', mode),
                row('Destination', dest, 'not set'),
            ].join('');
        }
        if (node.type === 'subscription_sender') {
            return [
                row('Health Board',         d.health_board,  'not set'),
                row('Peer Service',         d.peer_service),
                row('Workflow ID',          d.workflow_id,   'not set'),
                row('Receiver MLLP Host',   d.receiver_host, 'not set'),
                row('Receiver MLLP Port',   d.receiver_port || 2576),
                row('ACK Timeout Seconds',  `${d.ack_timeout_seconds || 5}s`),
                row('Max Messages/Minute',  `${d.max_messages_per_minute || 30}/min`),
            ].join('');
        }
        return '';
    }

    function labelForNode(node) {
        if (node.type === 'subscription_sender') {
            return node.data.health_board || 'Subscription Sender';
        }
        return NODE_META[node.type]?.label || node.type;
    }

    function getNode(id) {
        return nodes.find(node => node.id === id) || null;
    }

    function addNode(type, x, y, preset = null) {
        if (!NODE_TYPES.includes(type)) {
            return null;
        }
        const node = {
            id: nextId++,
            type,
            x: Math.max(10, Math.round(x)),
            y: Math.max(10, Math.round(y)),
            data: Object.assign(defaultData(type), preset || {}),
        };
        nodes.push(node);
        renderNodes();
        renderEdgesRAF();
        selectNode(node.id);
        updateStatusBar();
        return node;
    }

    function removeNode(nodeId) {
        nodes = nodes.filter(node => node.id !== nodeId);
        edges = edges.filter(edge => edge.from !== nodeId && edge.to !== nodeId);
        if (selectedNodeId === nodeId) {
            selectedNodeId = null;
        }
        if (!edges.some(edge => edge.id === selectedEdgeId)) {
            selectedEdgeId = null;
        }
        if (connectState?.fromNodeId === nodeId) {
            cancelConnecting();
        }
        renderNodes();
        renderEdgesRAF();
        renderSelectionPanel();
        updateStatusBar();
    }

    function removeEdge(edgeId) {
        edges = edges.filter(edge => edge.id !== edgeId);
        if (selectedEdgeId === edgeId) {
            selectedEdgeId = null;
        }
        renderEdgesRAF();
        renderSelectionPanel();
        updateStatusBar();
    }

    function selectNode(nodeId) {
        selectedNodeId = nodeId;
        selectedEdgeId = null;
        updateNodeSelectionClasses();
        renderEdgesRAF();
        renderSelectionPanel();
    }

    function selectEdge(edgeId) {
        selectedEdgeId = edgeId;
        selectedNodeId = null;
        updateNodeSelectionClasses();
        renderEdgesRAF();
        renderSelectionPanel();
    }

    function clearSelection() {
        selectedNodeId = null;
        selectedEdgeId = null;
        updateNodeSelectionClasses();
        renderEdgesRAF();
        renderSelectionPanel();
    }

    function updateNodeSelectionClasses() {
        nodesLayer.querySelectorAll('.node-card').forEach(card => {
            card.classList.toggle('selected', Number(card.dataset.nodeId) === selectedNodeId);
        });
    }

    function showEmptyProperties() {
        propertiesPanelBody.innerHTML = `
            <div class="empty-props">
                <i class="bi bi-cursor"></i>
                <span>Select a node or connection to view its details.</span>
            </div>
        `;
    }

    function renderSelectionPanel() {
        if (selectedNodeId != null) {
            renderNodeProperties(selectedNodeId);
            return;
        }
        if (selectedEdgeId != null) {
            renderEdgeProperties(selectedEdgeId);
            return;
        }
        showEmptyProperties();
    }

    function renderNodeProperties(nodeId) {
        const node = getNode(nodeId);
        if (!node) {
            showEmptyProperties();
            return;
        }

        const meta = NODE_META[node.type] || { label: node.type, icon: 'bi bi-box' };
        let fieldsHtml = '';

        if (node.type === 'hl7_server') {
            fieldsHtml = `
                <div class="prop-group">
                    <label for="prop-source-system">Source System</label>
                    <input id="prop-source-system" name="source_system" value="${esc(node.data.source_system)}" required>
                </div>
                <div class="prop-group">
                    <label for="prop-mllp-port">MLLP Port</label>
                    <input id="prop-mllp-port" name="mllp_port" type="number" value="${esc(node.data.mllp_port)}" required>
                </div>
                <div class="prop-group">
                    <label for="prop-hl7-version">HL7 Version</label>
                    <input id="prop-hl7-version" name="hl7_version" value="${esc(node.data.hl7_version)}">
                </div>
                <div class="prop-group">
                    <label for="prop-sending-app">Sending App</label>
                    <input id="prop-sending-app" name="sending_app" value="${esc(node.data.sending_app)}" required>
                </div>
                <div class="prop-group">
                    <label for="prop-validation-flow">Validation Flow</label>
                    <input id="prop-validation-flow" name="validation_flow" value="${esc(node.data.validation_flow)}" required>
                </div>
                <div class="prop-group">
                    <label for="prop-health-board">Health Board</label>
                    <input id="prop-health-board" name="health_board" value="${esc(node.data.health_board)}" required>
                </div>
                <div class="prop-group">
                    <label class="prop-checkbox" for="prop-enable-message-store">
                        <input id="prop-enable-message-store" name="enable_message_store" type="checkbox" ${node.data.enable_message_store ? 'checked' : ''}>
                        <span>Enable message store</span>
                    </label>
                </div>
            `;
        } else if (node.type === 'hl7_transformer') {
            const KNOWN = ['phw-hl7transformer', 'chemo-hl7transformer', 'pims-hl7transformer'];
            const isCustom = !KNOWN.includes(node.data.image_name);
            const opt = (value, label, desc) => {
                const checked = (!isCustom && node.data.image_name === value) ? 'checked' : '';
                const sel = checked ? ' txfm-selected' : '';
                return `<label class="txfm-option${sel}">
                    <input type="radio" name="transformer_preset" value="${value}" ${checked}>
                    <div class="txfm-option-body">
                        <span class="txfm-option-name">${label}</span>
                        <span class="txfm-option-image">${desc}</span>
                    </div>
                </label>`;
            };
            fieldsHtml = `
                <div class="prop-group">
                    <label>Transformer Type</label>
                    <div class="txfm-picker">
                        ${opt('phw-hl7transformer',   'PHW Transformer',       'phw-hl7transformer')}
                        ${opt('chemo-hl7transformer',  'ChemoCare Transformer', 'chemo-hl7transformer')}
                        ${opt('pims-hl7transformer',   'PIMS Transformer',      'pims-hl7transformer')}
                        <label class="txfm-option${isCustom ? ' txfm-selected' : ''}">
                            <input type="radio" name="transformer_preset" value="custom" ${isCustom ? 'checked' : ''}>
                            <div class="txfm-option-body">
                                <span class="txfm-option-name">Custom</span>
                                <span class="txfm-option-image">Enter image name below</span>
                            </div>
                        </label>
                    </div>
                </div>
                <div class="prop-group" id="txfm-custom-group" style="${isCustom ? '' : 'display:none;'}">
                    <label for="prop-image-name">Image Name</label>
                    <input id="prop-image-name" name="image_name" value="${esc(node.data.image_name)}" placeholder="e.g. my-custom-transformer" required>
                    <div class="prop-hint">ACR image name without tag.</div>
                </div>
            `;
        } else if (node.type === 'hl7_sender') {
            const dedicated = node.data.mode === 'dedicated';
            fieldsHtml = `
                <div class="prop-group">
                    <label for="prop-destination">Destination</label>
                    <input id="prop-destination" name="destination" value="${esc(node.data.destination)}">
                </div>
                <div class="prop-group">
                    <label for="prop-mode">Mode</label>
                    <select id="prop-mode" name="mode">
                        <option value="shared" ${node.data.mode === 'shared' ? 'selected' : ''}>shared</option>
                        <option value="dedicated" ${dedicated ? 'selected' : ''}>dedicated</option>
                    </select>
                </div>
                <div id="dedicated-fields" class="dedicated-fields" style="${dedicated ? '' : 'display:none;'}">
                    <div class="prop-group">
                        <label for="prop-destination-host">Destination Host</label>
                        <input id="prop-destination-host" name="destination_host" value="${esc(node.data.destination_host)}">
                    </div>
                    <div class="prop-group">
                        <label for="prop-destination-port">Destination Port</label>
                        <input id="prop-destination-port" name="destination_port" type="number" value="${esc(node.data.destination_port)}">
                    </div>
                </div>
            `;
        } else if (node.type === 'subscription_sender') {
            fieldsHtml = `
                <div class="prop-group">
                    <label for="prop-sub-health-board">Health Board</label>
                    <input id="prop-sub-health-board" name="health_board" value="${esc(node.data.health_board)}" placeholder="e.g. MPI-SWW" required>
                </div>
                <div class="prop-group">
                    <label for="prop-sub-peer-service">Peer Service</label>
                    <input id="prop-sub-peer-service" name="peer_service" value="${esc(node.data.peer_service || 'MPI')}">
                </div>
                <div class="prop-group">
                    <label for="prop-sub-workflow-id">Workflow ID</label>
                    <input id="prop-sub-workflow-id" name="workflow_id" value="${esc(node.data.workflow_id)}" placeholder="e.g. sww-to-chemo" required>
                </div>
                <div class="prop-group">
                    <label for="prop-sub-receiver-host">Receiver MLLP Host</label>
                    <input id="prop-sub-receiver-host" name="receiver_host" value="${esc(node.data.receiver_host)}" required>
                </div>
                <div class="prop-group">
                    <label for="prop-sub-receiver-port">Receiver MLLP Port</label>
                    <input id="prop-sub-receiver-port" name="receiver_port" type="number" value="${esc(node.data.receiver_port)}">
                </div>
                <div class="prop-group">
                    <label for="prop-sub-ack-timeout">ACK Timeout Seconds</label>
                    <input id="prop-sub-ack-timeout" name="ack_timeout_seconds" type="number" value="${esc(node.data.ack_timeout_seconds)}">
                </div>
                <div class="prop-group">
                    <label for="prop-sub-max-rate">Max Messages/Minute</label>
                    <input id="prop-sub-max-rate" name="max_messages_per_minute" type="number" value="${esc(node.data.max_messages_per_minute)}">
                </div>
            `;
        }

        propertiesPanelBody.innerHTML = `
            <div class="props-node-title"><i class="${meta.icon}"></i>${esc(labelForNode(node))}</div>
            <form id="node-props-form" autocomplete="off">${fieldsHtml}</form>
        `;

        const form = document.getElementById('node-props-form');
        if (!form) {
            return;
        }

        form.querySelectorAll('input, select').forEach(element => {
            element.addEventListener('input', () => syncNodeProperties(nodeId));
            element.addEventListener('change', () => syncNodeProperties(nodeId));
        });

        const modeSelect = document.getElementById('prop-mode');
        if (modeSelect) {
            modeSelect.addEventListener('change', () => {
                const dedicatedFields = document.getElementById('dedicated-fields');
                if (dedicatedFields) {
                    dedicatedFields.style.display = modeSelect.value === 'dedicated' ? '' : 'none';
                }
            });
        }

        // Transformer preset picker
        form.querySelectorAll('[name="transformer_preset"]').forEach(radio => {
            radio.addEventListener('change', () => {
                const customGroup = document.getElementById('txfm-custom-group');
                const isCustom = radio.value === 'custom';
                if (customGroup) customGroup.style.display = isCustom ? '' : 'none';
                // Highlight selected card
                form.querySelectorAll('.txfm-option').forEach(el => el.classList.remove('txfm-selected'));
                radio.closest('.txfm-option')?.classList.add('txfm-selected');
                // If a known preset, immediately apply it
                if (!isCustom) {
                    const node = getNode(nodeId);
                    if (node) {
                        node.data.image_name = radio.value;
                        updateNodeCard(node.id);
                        updateStatusBar();
                    }
                }
            });
        });
    }

    function syncNodeProperties(nodeId) {
        const node = getNode(nodeId);
        const form = document.getElementById('node-props-form');
        if (!node || !form) {
            return;
        }

        const formData = new FormData(form);
        if (node.type === 'hl7_server') {
            node.data.source_system = String(formData.get('source_system') || '').trim();
            node.data.mllp_port = parseInt(String(formData.get('mllp_port') || ''), 10) || 2575;
            node.data.hl7_version = String(formData.get('hl7_version') || '').trim() || '2.5';
            node.data.sending_app = String(formData.get('sending_app') || '').trim();
            node.data.validation_flow = String(formData.get('validation_flow') || '').trim();
            node.data.health_board = String(formData.get('health_board') || '').trim();
            node.data.enable_message_store = !!form.querySelector('[name="enable_message_store"]')?.checked;
        }
        if (node.type === 'hl7_transformer') {
            const preset = form.querySelector('[name="transformer_preset"]:checked')?.value;
            if (preset && preset !== 'custom') {
                node.data.image_name = preset;
            } else {
                node.data.image_name = String(formData.get('image_name') || '').trim();
            }
        }
        if (node.type === 'hl7_sender') {
            node.data.destination = String(formData.get('destination') || '').trim() || 'MPI';
            node.data.mode = String(formData.get('mode') || 'shared');
            node.data.destination_host = String(formData.get('destination_host') || '').trim();
            node.data.destination_port = parseInt(String(formData.get('destination_port') || ''), 10) || 2576;
            renderEdgesRAF();
        }
        if (node.type === 'subscription_sender') {
            node.data.health_board = String(formData.get('health_board') || '').trim();
            node.data.peer_service = String(formData.get('peer_service') || '').trim() || 'MPI';
            node.data.workflow_id = String(formData.get('workflow_id') || '').trim();
            node.data.receiver_host = String(formData.get('receiver_host') || '').trim();
            node.data.receiver_port = parseInt(String(formData.get('receiver_port') || ''), 10) || 2576;
            node.data.ack_timeout_seconds = parseInt(String(formData.get('ack_timeout_seconds') || ''), 10) || 5;
            node.data.max_messages_per_minute = parseInt(String(formData.get('max_messages_per_minute') || ''), 10) || 30;
            renderEdgesRAF();
        }

        updateNodeCard(node.id);
        updateStatusBar();
    }

    function renderEdgeProperties(edgeId) {
        const edge = edges.find(item => item.id === edgeId);
        if (!edge) {
            showEmptyProperties();
            return;
        }
        const fromNode = getNode(edge.from);
        const toNode = getNode(edge.to);
        if (!fromNode || !toNode) {
            showEmptyProperties();
            return;
        }

        propertiesPanelBody.innerHTML = `
            <div class="props-edge-title"><i class="bi bi-diagram-3"></i>Connection</div>
            <div class="edge-info-group">
                <div class="edge-info-label">Type</div>
                <div class="edge-info-value">${esc(edgeLabel(fromNode.type, toNode.type, toNode.data))}</div>
            </div>
            <div class="edge-info-group">
                <div class="edge-info-label">From</div>
                <div class="edge-info-value">${esc(NODE_META[fromNode.type]?.label || fromNode.type)}</div>
            </div>
            <div class="edge-info-group">
                <div class="edge-info-label">To</div>
                <div class="edge-info-value">${esc(NODE_META[toNode.type]?.label || toNode.type)}</div>
            </div>
            <div class="edge-info-group">
                <div class="edge-info-label">Queue Description</div>
                <div class="edge-readonly">${esc(getQueueInfo(fromNode, toNode))}</div>
            </div>
            <button id="btn-delete-edge" type="button" class="btn btn-sm btn-outline-danger">
                <i class="bi bi-trash me-1"></i>Delete connection
            </button>
        `;

        document.getElementById('btn-delete-edge')?.addEventListener('click', () => removeEdge(edgeId));
    }

    function makeNodeCard(node) {
        const meta = NODE_META[node.type] || { label: node.type, icon: 'bi bi-box' };
        const card = document.createElement('div');
        const expanded = expandedNodes.has(node.id);
        card.className = `node-card nc-${node.type} node-${node.type.replace(/_/g, '-')}${selectedNodeId === node.id ? ' selected' : ''}${expanded ? ' expanded' : ''}`;
        card.dataset.nodeId = String(node.id);
        card.style.left = `${node.x}px`;
        card.style.top = `${node.y}px`;
        card.style.width = '220px';
        card.innerHTML = `
            <div class="node-header" data-drag-node="${node.id}">
                <i class="${meta.icon}"></i>
                <span class="node-label" id="nl-${node.id}">${esc(labelForNode(node))}</span>
                <button class="node-toggle" type="button" data-toggle-node="${node.id}" title="${expanded ? 'Collapse' : 'Expand'}">
                    <i class="bi ${expanded ? 'bi-chevron-up' : 'bi-chevron-down'}"></i>
                </button>
                <button class="node-del" type="button" data-del-node="${node.id}">×</button>
            </div>
            <div class="node-body">
                <div class="node-subtitle" id="ns-${node.id}">${esc(subtitleForNode(node))}</div>
            </div>
            <div class="node-detail${expanded ? '' : ' node-detail-hidden'}">
                ${detailRowsForNode(node)}
            </div>
            ${node.type === 'hl7_transformer' || SINK_NODE_TYPES.includes(node.type) ? `<div class="port port-in" data-port-in="${node.id}" title="Input"></div>` : ''}
            ${node.type === 'hl7_server' || node.type === 'hl7_transformer' ? `<div class="port port-out" data-port-out="${node.id}" title="Drag to connect"></div>` : ''}
        `;

        card.addEventListener('mousedown', event => {
            if (event.target === card) clearSelection();
        });
        card.addEventListener('click', event => {
            if (event.target.closest('[data-del-node]') || event.target.closest('[data-drag-node]') || event.target.closest('.port') || event.target.closest('[data-toggle-node]')) {
                return;
            }
            selectNode(node.id);
        });

        card.querySelector('[data-del-node]')?.addEventListener('click', event => {
            event.stopPropagation();
            removeNode(node.id);
        });

        card.querySelector('[data-toggle-node]')?.addEventListener('click', event => {
            event.stopPropagation();
            if (expandedNodes.has(node.id)) {
                expandedNodes.delete(node.id);
            } else {
                expandedNodes.add(node.id);
            }
            updateNodeCard(node.id);
            renderEdgesRAF();
        });

        card.querySelector('[data-drag-node]')?.addEventListener('mousedown', event => startNodeDrag(event, node.id));
        card.querySelector('[data-port-out]')?.addEventListener('mousedown', event => startConnecting(event, node.id));
        card.querySelector('[data-port-in]')?.addEventListener('mouseup', event => {
            event.stopPropagation();
            finishConnecting(node.id);
        });
        card.querySelector('[data-port-in]')?.addEventListener('mousedown', event => event.stopPropagation());
        card.querySelector('[data-port-out]')?.addEventListener('click', event => event.stopPropagation());
        card.querySelector('[data-port-in]')?.addEventListener('click', event => event.stopPropagation());

        return card;
    }

    function renderNodes() {
        nodesLayer.innerHTML = '';
        emptyCanvasState.style.display = nodes.length ? 'none' : 'flex';
        nodes.forEach(node => {
            nodesLayer.appendChild(makeNodeCard(node));
        });
        updateNodeSelectionClasses();
    }

    function updateNodeCard(nodeId) {
        const node = getNode(nodeId);
        const card = nodesLayer.querySelector(`[data-node-id="${nodeId}"]`);
        if (!node || !card) {
            return;
        }
        const expanded = expandedNodes.has(node.id);
        card.classList.toggle('expanded', expanded);
        const label = card.querySelector(`#nl-${nodeId}`);
        if (label) label.textContent = labelForNode(node);
        const subtitle = card.querySelector(`#ns-${nodeId}`);
        if (subtitle) subtitle.textContent = subtitleForNode(node);
        const detail = card.querySelector('.node-detail');
        if (detail) {
            detail.innerHTML = detailRowsForNode(node);
            detail.classList.toggle('node-detail-hidden', !expanded);
        }
        const toggleBtn = card.querySelector('[data-toggle-node]');
        if (toggleBtn) {
            toggleBtn.title = expanded ? 'Collapse' : 'Expand';
            const icon = toggleBtn.querySelector('i');
            if (icon) icon.className = `bi ${expanded ? 'bi-chevron-up' : 'bi-chevron-down'}`;
        }
    }

    function startNodeDrag(event, nodeId) {
        if (event.button !== 0) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        const node = getNode(nodeId);
        if (!node) {
            return;
        }
        const rect = canvasInner.getBoundingClientRect();
        dragState = {
            nodeId,
            offsetX: event.clientX - rect.left - node.x,
            offsetY: event.clientY - rect.top - node.y,
        };
        selectNode(nodeId);
    }

    function startConnecting(event, fromNodeId) {
        if (event.button !== 0) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        const rect = canvasInner.getBoundingClientRect();
        connectState = {
            fromNodeId,
            curX: event.clientX - rect.left,
            curY: event.clientY - rect.top,
        };
        selectedEdgeId = null;
        renderSelectionPanel();
        updateRubberBand();
    }

    function finishConnecting(toNodeId) {
        if (!connectState) {
            return;
        }
        const fromNodeId = connectState.fromNodeId;
        if (addEdge(fromNodeId, toNodeId)) {
            const createdEdge = edges.find(edge => edge.from === fromNodeId && edge.to === toNodeId);
            if (createdEdge) {
                selectEdge(createdEdge.id);
            }
        }
        cancelConnecting();
    }

    function cancelConnecting() {
        connectState = null;
        rubberBand.style.display = 'none';
        rubberBand.setAttribute('d', '');
    }

    function addEdge(fromNodeId, toNodeId) {
        const fromNode = getNode(fromNodeId);
        const toNode = getNode(toNodeId);
        if (!fromNode || !toNode) {
            return false;
        }
        if (fromNodeId === toNodeId) {
            showTransientErrors(['Self-loops are not allowed.'], 3000);
            return false;
        }
        if (edges.some(edge => edge.from === fromNodeId && edge.to === toNodeId)) {
            showTransientErrors(['That connection already exists.'], 3000);
            return false;
        }
        if (fromNode.type === 'hl7_sender') {
            showTransientErrors(['HL7 Sender nodes do not have output ports.'], 3000);
            return false;
        }
        if (toNode.type === 'hl7_server') {
            showTransientErrors(['HL7 Server nodes do not accept incoming connections.'], 3000);
            return false;
        }
        const allowMultipleOutgoing = fromNode.type === 'hl7_server' && toNode.type === 'subscription_sender';
        if (!allowMultipleOutgoing && edges.some(edge => edge.from === fromNodeId)) {
            showTransientErrors(['Each node can have at most one outgoing edge.'], 3000);
            return false;
        }
        if (edges.some(edge => edge.to === toNodeId)) {
            showTransientErrors(['Each node can have at most one incoming edge.'], 3000);
            return false;
        }

        edges.push({ id: nextEdgeId++, from: fromNodeId, to: toNodeId });
        renderEdgesRAF();
        updateStatusBar();
        return true;
    }

    function bezierPath(x1, y1, x2, y2) {
        const dx = Math.max(60, Math.abs(x2 - x1) * 0.5);
        return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
    }

    function portPos(nodeId, side) {
        const node = getNode(nodeId);
        const element = nodesLayer.querySelector(`[data-node-id="${nodeId}"]`);
        const height = element ? element.offsetHeight : 88;
        const width = element ? element.offsetWidth : 200;
        return side === 'out'
            ? { x: node.x + width, y: node.y + height / 2 }
            : { x: node.x, y: node.y + height / 2 };
    }

    function edgeLabel(fromType, toType, toData) {
        if (fromType === 'hl7_server' && toType === 'hl7_transformer') {
            return 'Transformer Queue';
        }
        if (fromType === 'hl7_transformer') {
            return toData.mode === 'dedicated' ? 'Sender Queue' : 'Shared Sender Queue';
        }
        if (fromType === 'hl7_server' && toType === 'hl7_sender') {
            return 'Shared Sender Queue';
        }
        if (fromType === 'hl7_server' && toType === 'subscription_sender') {
            return 'Topic Subscription';
        }
        return 'Queue';
    }

    function getQueueInfo(fromNode, toNode) {
        const src = nodes.find(node => node.type === 'hl7_server')?.data?.source_system || '{SOURCE}';
        if (fromNode.type === 'hl7_server' && toNode.type === 'hl7_transformer') {
            return `{namespace}-SBQ-${src}-HL7-Transformer (auto-generated)`;
        }
        if (fromNode.type === 'hl7_transformer' && toNode.data.mode === 'dedicated') {
            return `{namespace}-SBQ-${src}-HL7-Sender (auto-generated)`;
        }
        if (fromNode.type === 'hl7_server' && toNode.type === 'subscription_sender') {
            const hb = toNode.data.health_board || '{HEALTH_BOARD}';
            return `Topic ${src}-HL7-Input → subscription ${hb}-Sender (auto-generated)`;
        }
        return 'Shared sender queue (pre-existing infrastructure)';
    }

    function renderEdgesRAF() {
        if (_rafPending) {
            return;
        }
        _rafPending = true;
        requestAnimationFrame(() => {
            _rafPending = false;
            renderEdges();
        });
    }

    function renderEdges() {
        canvasSvg.querySelectorAll('.edge-group').forEach(group => group.remove());
        edges.forEach(edge => {
            const fromNode = getNode(edge.from);
            const toNode = getNode(edge.to);
            if (!fromNode || !toNode) {
                return;
            }
            const start = portPos(edge.from, 'out');
            const end = portPos(edge.to, 'in');
            const pathValue = bezierPath(start.x, start.y, end.x, end.y);
            const midX = (start.x + end.x) / 2;
            const midY = (start.y + end.y) / 2;
            const selected = edge.id === selectedEdgeId;
            const label = edgeLabel(fromNode.type, toNode.type, toNode.data);
            const labelWidth = Math.max(98, label.length * 6.8);

            const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            group.setAttribute('class', 'edge-group');
            group.setAttribute('data-edge-id', String(edge.id));

            const hitPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            hitPath.setAttribute('d', pathValue);
            hitPath.setAttribute('stroke', 'transparent');
            hitPath.setAttribute('stroke-width', '18');
            hitPath.setAttribute('fill', 'none');
            hitPath.style.pointerEvents = 'stroke';
            hitPath.style.cursor = 'pointer';
            hitPath.addEventListener('click', event => {
                event.stopPropagation();
                selectEdge(edge.id);
            });

            const visiblePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            visiblePath.setAttribute('d', pathValue);
            visiblePath.setAttribute('stroke', selected ? '#f59e0b' : '#3b82f6');
            visiblePath.setAttribute('stroke-width', selected ? '3' : '2');
            visiblePath.setAttribute('fill', 'none');
            visiblePath.setAttribute('marker-end', selected ? 'url(#arrowhead-sel)' : 'url(#arrowhead)');
            visiblePath.style.pointerEvents = 'none';

            const labelBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            labelBg.setAttribute('x', String(midX - labelWidth / 2));
            labelBg.setAttribute('y', String(midY - 11));
            labelBg.setAttribute('width', String(labelWidth));
            labelBg.setAttribute('height', '22');
            labelBg.setAttribute('rx', '11');
            labelBg.setAttribute('fill', '#ffffff');
            labelBg.setAttribute('stroke', selected ? '#f59e0b' : '#cbd5e1');
            labelBg.setAttribute('stroke-width', '1');
            labelBg.style.pointerEvents = 'none';

            const labelText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            labelText.setAttribute('x', String(midX));
            labelText.setAttribute('y', String(midY + 4));
            labelText.setAttribute('text-anchor', 'middle');
            labelText.setAttribute('font-size', '11');
            labelText.setAttribute('font-family', 'Rubik, sans-serif');
            labelText.setAttribute('font-weight', '600');
            labelText.setAttribute('fill', selected ? '#92400e' : '#334155');
            labelText.textContent = label;
            labelText.style.pointerEvents = 'none';

            group.appendChild(hitPath);
            group.appendChild(visiblePath);
            group.appendChild(labelBg);
            group.appendChild(labelText);

            if (selected) {
                const deleteCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                deleteCircle.setAttribute('cx', String(midX + labelWidth / 2 + 16));
                deleteCircle.setAttribute('cy', String(midY));
                deleteCircle.setAttribute('r', '11');
                deleteCircle.setAttribute('fill', '#ef4444');
                deleteCircle.style.pointerEvents = 'all';
                deleteCircle.style.cursor = 'pointer';
                deleteCircle.addEventListener('click', event => {
                    event.stopPropagation();
                    removeEdge(edge.id);
                });

                const deleteText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                deleteText.setAttribute('x', String(midX + labelWidth / 2 + 16));
                deleteText.setAttribute('y', String(midY + 4));
                deleteText.setAttribute('text-anchor', 'middle');
                deleteText.setAttribute('font-size', '13');
                deleteText.setAttribute('font-family', 'Rubik, sans-serif');
                deleteText.setAttribute('font-weight', '700');
                deleteText.setAttribute('fill', '#ffffff');
                deleteText.textContent = '×';
                deleteText.style.pointerEvents = 'all';
                deleteText.style.cursor = 'pointer';
                deleteText.addEventListener('click', event => {
                    event.stopPropagation();
                    removeEdge(edge.id);
                });

                group.appendChild(deleteCircle);
                group.appendChild(deleteText);
            }

            canvasSvg.appendChild(group);
        });
    }

    function updateRubberBand() {
        if (!connectState) {
            rubberBand.style.display = 'none';
            return;
        }
        const start = portPos(connectState.fromNodeId, 'out');
        const pathValue = bezierPath(start.x, start.y, connectState.curX, connectState.curY);
        rubberBand.style.display = 'block';
        rubberBand.setAttribute('d', pathValue);
        rubberBand.setAttribute('stroke', '#f59e0b');
        rubberBand.setAttribute('stroke-width', '2');
        rubberBand.setAttribute('stroke-dasharray', '6 3');
        rubberBand.setAttribute('fill', 'none');
        rubberBand.setAttribute('marker-end', 'url(#arrowhead-sel)');
    }

    function flowEdgeExists(fromType, toType) {
        return edges.some(edge => {
            const fromNode = getNode(edge.from);
            const toNode = getNode(edge.to);
            return fromNode?.type === fromType && toNode?.type === toType;
        });
    }

    function showTransientErrors(errors, duration = 5000) {
        if (_errorTimer) {
            clearTimeout(_errorTimer);
            _errorTimer = null;
        }
        if (!Array.isArray(errors) || !errors.length) {
            errorContainer.innerHTML = '';
            return;
        }
        errorContainer.innerHTML = `
            <div class="alert alert-danger py-2 mb-0">
                <ul class="mb-0 ps-3">${errors.map(error => `<li>${esc(error)}</li>`).join('')}</ul>
            </div>
        `;
        if (_errorTimer) {
            clearTimeout(_errorTimer);
        }
        _errorTimer = window.setTimeout(() => {
            errorContainer.innerHTML = '';
            _errorTimer = null;
        }, duration);
    }

    function validateFlow(showAlerts) {
        const errors = [];
        const servers = nodes.filter(node => node.type === 'hl7_server');
        const senders = nodes.filter(node => node.type === 'hl7_sender');
        const transformers = nodes.filter(node => node.type === 'hl7_transformer');
        const subscriptionSenders = nodes.filter(node => node.type === 'subscription_sender');
        const subscriptionMode = subscriptionSenders.length > 0;
        const flowId = flowIdInput.value.trim().toLowerCase();

        if (servers.length !== 1) {
            errors.push(`Exactly 1 HL7 Server is required (found ${servers.length}).`);
        }

        if (subscriptionMode) {
            if (subscriptionSenders.length < 1) {
                errors.push('At least 1 Subscription Sender is required.');
            }
            if (senders.length) {
                errors.push('Standard HL7 Sender nodes are not allowed in subscription mode.');
            }
            if (transformers.length) {
                errors.push('HL7 Transformer nodes are not allowed in subscription mode.');
            }
        } else {
            if (senders.length !== 1) {
                errors.push(`Exactly 1 HL7 Sender is required (found ${senders.length}).`);
            }
            if (transformers.length > 1) {
                errors.push(`At most 1 HL7 Transformer is supported (found ${transformers.length}).`);
            }
        }

        if (!flowId) {
            errors.push('Flow ID is required.');
        } else if (!FLOW_ID_PATTERN.test(flowId)) {
            errors.push('Flow ID must use lowercase kebab-case (letters, numbers, hyphens).');
        }

        const server = servers[0];
        const sender = senders[0];
        const transformer = transformers[0];

        if (subscriptionMode) {
            if (server) {
                subscriptionSenders.forEach(subscriptionSender => {
                    const connected = edges.some(edge => edge.from === server.id && edge.to === subscriptionSender.id);
                    if (!connected) {
                        errors.push(`Server → ${labelForNode(subscriptionSender)} connection is required in subscription mode.`);
                    }
                });
            }
        } else if (transformer) {
            if (!flowEdgeExists('hl7_server', 'hl7_transformer')) {
                errors.push('Server → Transformer connection is required when a transformer is present.');
            }
            if (!flowEdgeExists('hl7_transformer', 'hl7_sender')) {
                errors.push('Transformer → Sender connection is required when a transformer is present.');
            }
        } else if (server && sender && !flowEdgeExists('hl7_server', 'hl7_sender')) {
            errors.push('Server → Sender connection is required when no transformer is present.');
        }

        if (server) {
            if (!server.data.source_system) {
                errors.push('Server: source_system is required.');
            }
            if (!server.data.sending_app) {
                errors.push('Server: sending_app is required.');
            }
            if (!server.data.validation_flow) {
                errors.push('Server: validation_flow is required.');
            }
            if (!server.data.health_board) {
                errors.push('Server: health_board is required.');
            }
        }

        if (transformer && !transformer.data.image_name) {
            errors.push('Transformer: image_name is required.');
        }

        if (sender && sender.data.mode === 'dedicated' && !sender.data.destination_host) {
            errors.push('Sender: destination_host is required for dedicated mode.');
        }

        if (subscriptionMode) {
            subscriptionSenders.forEach(subscriptionSender => {
                if (!subscriptionSender.data.health_board) {
                    errors.push('Subscription Sender: health_board is required.');
                }
                if (!subscriptionSender.data.workflow_id) {
                    errors.push(`Subscription Sender ${labelForNode(subscriptionSender)}: workflow_id is required.`);
                }
                if (!subscriptionSender.data.receiver_host) {
                    errors.push(`Subscription Sender ${labelForNode(subscriptionSender)}: receiver_host is required.`);
                }
            });
        }

        if (showAlerts) {
            showTransientErrors(errors, 5000);
        }
        return errors;
    }

    function detectPattern() {
        const hasSubscriptionSenders = nodes.some(node => node.type === 'subscription_sender');
        const hasTransformer = nodes.some(node => node.type === 'hl7_transformer');
        const sender = nodes.find(node => node.type === 'hl7_sender');
        if (hasSubscriptionSenders) {
            return 'Subscription Fan-out';
        }
        if (!hasTransformer && sender) {
            return 'Direct Flow (Server → Sender)';
        }
        if (hasTransformer && sender?.data?.mode === 'dedicated') {
            return 'Transform + Dedicated Sender';
        }
        if (hasTransformer) {
            return 'Transform + Shared Sender';
        }
        return 'Unknown';
    }

    function updateStatusBar() {
        const patternEl = document.getElementById('status-bar-pattern');
        const validityEl = document.getElementById('status-bar-validity');
        if (!patternEl || !validityEl) {
            return;
        }
        patternEl.textContent = detectPattern();
        const errors = validateFlow(false);
        if (errors.length === 0) {
            validityEl.textContent = 'Valid';
            validityEl.className = 'status-pill status-valid';
        } else {
            validityEl.textContent = 'Incomplete';
            validityEl.className = 'status-pill status-incomplete';
        }
        updateCanvasOverflow();
    }

    function updateCanvasOverflow() {
        const canvas = document.getElementById('freeform-canvas');
        const inner = document.getElementById('canvas-inner');
        if (!canvas || !inner) return;
        // Check if any node extends beyond the canvas viewport
        const cw = canvas.clientWidth;
        const ch = canvas.clientHeight;
        const NODE_W = 180, NODE_H = 80; // approximate node card dimensions
        const overflow = nodes.some(n => (n.x + NODE_W) > cw || (n.y + NODE_H) > ch);
        canvas.classList.toggle('canvas-overflow', overflow);
    }

    function exportGraph() {
        const data = {};
        nodes.forEach(node => {
            const outEdge = edges.find(edge => edge.from === node.id);
            const inEdge = edges.find(edge => edge.to === node.id);
            data[String(node.id)] = {
                id: node.id,
                name: node.type,
                data: { ...node.data },
                class: node.type,
                pos_x: node.x,
                pos_y: node.y,
                outputs: outEdge ? { output_1: { connections: [{ node: String(outEdge.to), output: 'input_1' }] } } : {},
                inputs: inEdge ? { input_1: { connections: [{ node: String(inEdge.from), output: 'output_1' }] } } : {},
            };
        });
        return { drawflow: { Home: { data } } };
    }

    async function generatePreview() {
        const errors = validateFlow(true);
        if (errors.length) {
            return;
        }

        const button = document.getElementById('btn-generate');
        const graphJson = exportGraph();
        try {
            if (button) {
                button.disabled = true;
                button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Generating…';
            }
            const response = await fetch('/designer/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ flow_id: flowIdInput.value.trim(), graph: graphJson }),
            });
            const data = await response.json();
            if (!response.ok) {
                showTransientErrors(data.errors || ['Unable to generate preview.'], 5000);
                return;
            }
            _previewData = data;
            openPreview(data);
        } catch (error) {
            showTransientErrors([`Preview request failed: ${error.message}`], 5000);
        } finally {
            if (button) {
                button.disabled = false;
                button.innerHTML = '<i class="bi bi-eye me-1"></i>Preview Output';
            }
        }
    }

    function openPreview(data) {
        document.getElementById('preview-flow-title').textContent = `Flow: ${data.flow_id || flowIdInput.value.trim()}`;
        document.getElementById('code-flow').textContent = data.flow_tf || '';
        document.getElementById('code-locals').textContent = data.locals_snippet || '';
        document.getElementById('code-variables').textContent = data.variables_snippet || '';

        const summary = data.summary || {};
        const containerAppCount = Array.isArray(summary.container_apps) ? summary.container_apps.length : 0;
        const queueCount = Array.isArray(summary.service_bus_queues) ? summary.service_bus_queues.length : 0;
        const subscriptionCount = Array.isArray(summary.service_bus_subscriptions) ? summary.service_bus_subscriptions.length : 0;
        const rbacCount = summary.rbac_assignments ?? 0;
        const pattern = summary.pattern ?? detectPattern();
        const subscriptionCard = subscriptionCount || summary.service_bus_subscriptions
            ? `
                <div class="summary-card">
                    <div class="summary-card-num">${subscriptionCount}</div>
                    <div class="summary-card-label">Topic Subscriptions</div>
                    <ul class="summary-card-list">${subscriptionCount ? summary.service_bus_subscriptions.map(item => `<li>${esc(item)}</li>`).join('') : '<li>None</li>'}</ul>
                </div>
            `
            : '';

        document.getElementById('preview-summary').innerHTML = `
            <div class="preview-summary-grid">
                <div class="summary-card">
                    <div class="summary-card-num">${containerAppCount}</div>
                    <div class="summary-card-label">Container Apps</div>
                    <ul class="summary-card-list">${containerAppCount ? summary.container_apps.map(item => `<li>${esc(item)}</li>`).join('') : '<li>None</li>'}</ul>
                </div>
                <div class="summary-card">
                    <div class="summary-card-num">${queueCount}</div>
                    <div class="summary-card-label">Service Bus Queues</div>
                    <ul class="summary-card-list">${queueCount ? summary.service_bus_queues.map(item => `<li>${esc(item)}</li>`).join('') : (subscriptionCount ? '<li>None</li>' : '<li>Shared queue only</li>')}</ul>
                </div>
                ${subscriptionCard}
                <div class="summary-card">
                    <div class="summary-card-num">${rbacCount}</div>
                    <div class="summary-card-label">RBAC Assignments</div>
                </div>
                <div class="summary-card">
                    <div class="summary-card-num" style="font-size:0.95rem;line-height:1.3;">${esc(pattern)}</div>
                    <div class="summary-card-label">Pattern</div>
                </div>
            </div>
        `;

        switchTab('flow');
        previewBackdrop.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }

    async function downloadBlobFromPost(url, payload, fallbackName) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }
        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
        const downloadName = match ? decodeURIComponent(match[1].replace(/"/g, '').trim()) : fallbackName;
        const href = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = href;
        anchor.download = downloadName;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(href);
    }

    window.closePreview = function () {
        previewBackdrop.style.display = 'none';
        document.body.style.overflow = '';
    };

    window.switchTab = function (tab) {
        _activeTab = tab;
        document.querySelectorAll('.preview-tab').forEach(button => {
            button.classList.toggle('active', button.dataset.tab === tab);
        });
        ['flow', 'locals', 'variables'].forEach(name => {
            const panel = document.getElementById(`tab-${name}`);
            if (panel) {
                panel.style.display = name === tab ? 'block' : 'none';
            }
        });
    };

    window.copyCurrentTab = function () {
        if (!_previewData) {
            return;
        }
        const text = _activeTab === 'flow'
            ? _previewData.flow_tf || ''
            : _activeTab === 'locals'
                ? _previewData.locals_snippet || ''
                : _previewData.variables_snippet || '';
        navigator.clipboard.writeText(text).then(() => {
            const button = document.getElementById('btn-copy-tf');
            if (!button) {
                return;
            }
            button.innerHTML = '<i class="bi bi-check2 me-1"></i>Copied';
            window.setTimeout(() => {
                button.innerHTML = '<i class="bi bi-clipboard me-1"></i>Copy';
            }, 1600);
        });
    };

    window.downloadPreviewFile = function (tab) {
        if (!_previewData) {
            return;
        }
        const flowId = (_previewData.flow_id || flowIdInput.value.trim()).replace(/-/g, '_');
        const fileMap = {
            flow: { name: `flow_${flowId}.tf`, text: _previewData.flow_tf || '' },
            locals: { name: 'locals_additions.tf', text: _previewData.locals_snippet || '' },
            variables: { name: 'variables_additions.tf', text: _previewData.variables_snippet || '' },
        };
        const entry = fileMap[tab] || fileMap.flow;
        const href = URL.createObjectURL(new Blob([entry.text], { type: 'text/plain' }));
        const anchor = document.createElement('a');
        anchor.href = href;
        anchor.download = entry.name;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(href);
    };

    window.downloadPreviewZip = async function () {
        const errors = validateFlow(true);
        if (errors.length) {
            return;
        }
        try {
            await downloadBlobFromPost(
                '/designer/preview-zip',
                { flow_id: flowIdInput.value.trim(), graph: exportGraph() },
                `${flowIdInput.value.trim().replace(/-/g, '_') || 'flow'}_terraform_preview.zip`,
            );
        } catch (error) {
            showTransientErrors([`ZIP download failed: ${error.message}`], 5000);
        }
    };

    function bindPaletteDrag() {
        document.querySelectorAll('.palette-item[data-node]').forEach(item => {
            item.addEventListener('dragstart', event => {
                const payload = JSON.stringify({
                    type: item.dataset.node,
                    preset: item.dataset.preset ? JSON.parse(item.dataset.preset) : null,
                });
                event.dataTransfer.setData('text/plain', payload);
                event.dataTransfer.effectAllowed = 'copy';
            });
        });

        canvasInner.addEventListener('dragover', event => {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'copy';
        });

        canvasInner.addEventListener('drop', event => {
            event.preventDefault();
            let parsed;
            try {
                parsed = JSON.parse(event.dataTransfer.getData('text/plain'));
            } catch {
                return;
            }
            const { type, preset } = parsed;
            if (!NODE_TYPES.includes(type)) {
                return;
            }
            const rect = canvasInner.getBoundingClientRect();
            addNode(type, Math.max(10, event.clientX - rect.left - 100), Math.max(10, event.clientY - rect.top - 44), preset);
        });
    }

    function wireCanvasBackgroundSelection() {
        [freeformCanvas, canvasInner, nodesLayer].forEach(element => {
            element.addEventListener('mousedown', event => {
                if (event.target === element) {
                    clearSelection();
                }
            });
        });

        canvasSvg.addEventListener('click', event => {
            if (event.target === canvasSvg) {
                clearSelection();
            }
        });
    }

    document.addEventListener('mousemove', event => {
        if (dragState) {
            const node = getNode(dragState.nodeId);
            if (node) {
                const rect = canvasInner.getBoundingClientRect();
                const maxX = canvasInner.clientWidth - 200;
                const maxY = canvasInner.clientHeight - 70;
                node.x = Math.max(0, Math.min(maxX, Math.round(event.clientX - rect.left - dragState.offsetX)));
                node.y = Math.max(0, Math.min(maxY, Math.round(event.clientY - rect.top - dragState.offsetY)));
                const card = nodesLayer.querySelector(`[data-node-id="${node.id}"]`);
                if (card) {
                    card.style.left = `${node.x}px`;
                    card.style.top = `${node.y}px`;
                }
                renderEdgesRAF();
            }
        }

        if (connectState) {
            const rect = canvasInner.getBoundingClientRect();
            connectState.curX = event.clientX - rect.left;
            connectState.curY = event.clientY - rect.top;
            updateRubberBand();
        }
    });

    document.addEventListener('mouseup', () => {
        if (dragState) {
            dragState = null;
        }
        if (connectState) {
            cancelConnecting();
        }
    });

    document.getElementById('btn-validate')?.addEventListener('click', () => validateFlow(true));
    document.getElementById('btn-generate')?.addEventListener('click', generatePreview);
    document.getElementById('btn-clear')?.addEventListener('click', () => {
        if (!nodes.length || window.confirm('Clear the canvas?')) {
            nodes = [];
            edges = [];
            nextId = 1;
            nextEdgeId = 1;
            selectedNodeId = null;
            selectedEdgeId = null;
            dragState = null;
            cancelConnecting();
            renderNodes();
            renderEdgesRAF();
            renderSelectionPanel();
            updateStatusBar();
            showTransientErrors([], 0);
        }
    });

    flowIdInput.addEventListener('input', updateStatusBar);
    previewBackdrop.addEventListener('click', event => {
        if (event.target === previewBackdrop) {
            window.closePreview();
        }
    });

    bindPaletteDrag();
    wireCanvasBackgroundSelection();
    renderNodes();
    renderSelectionPanel();
    renderEdgesRAF();
    updateStatusBar();
})();

// ── Palette resize handle ────────────────────────────────────────────────────
(function initPaletteResize() {
    const MIN_WIDTH = 180;
    const MAX_WIDTH = 440; // double the default 220px
    const handle = document.getElementById('palette-resize-handle');
    const layout = document.querySelector('.designer-layout');
    if (!handle || !layout) return;

    let dragging = false;
    let startX = 0;
    let startWidth = 0;

    handle.addEventListener('mousedown', e => {
        e.preventDefault();
        dragging = true;
        startX = e.clientX;
        startWidth = parseInt(getComputedStyle(layout).getPropertyValue('--palette-width') || '220', 10);
        handle.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', e => {
        if (!dragging) return;
        const delta = e.clientX - startX;
        const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta));
        layout.style.setProperty('--palette-width', newWidth + 'px');
    });

    document.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        handle.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    });
}());
