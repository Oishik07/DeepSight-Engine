document.addEventListener('DOMContentLoaded', () => {
    // Navigation Elements
    const appContainer = document.getElementById('appContainer');
    
    // Mobile Responsive Navigation Elements
    const sidebar = document.getElementById('sidebar');
    const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
    const drawerOverlay = document.getElementById('drawerOverlay');

    // Main App UI Elements
    const startBtn = document.getElementById('startBtn');
    const goalInput = document.getElementById('goalInput');
    const micBtn = document.getElementById('micBtn');
    const progressTimeline = document.getElementById('progressTimeline');
    const reportSection = document.getElementById('reportSection');
    const logConsole = document.getElementById('logConsole');
    const statusBadge = document.getElementById('statusBadge');
    const reportContent = document.getElementById('reportContent');
    const providerSelect = document.getElementById('llmProvider');
    const modelInput = document.getElementById('llmModel');
    const llmKeyInput = document.getElementById('llmKey');
    const searchKeyInput = document.getElementById('searchKey');
    const welcomeScreen = document.getElementById('welcomeScreen');
    
    const toggleSettingsBtn = document.getElementById('toggleSettingsBtn');
    const settingsDropdownPanel = document.getElementById('settingsDropdownPanel');
    const toggleSystemPromptBtn = document.getElementById('toggleSystemPromptBtn');
    const systemPromptPanel = document.getElementById('systemPromptPanel');
    const systemPromptInput = document.getElementById('systemPrompt');
    const historyList = document.getElementById('historyList');
    const newChatBtn = document.getElementById('newChatBtn');

    // Toggle Settings Dropdown Panel
    toggleSettingsBtn.addEventListener('click', () => {
        settingsDropdownPanel.classList.toggle('hidden');
    });

    // Toolbar Action Buttons
    const copyBtn = document.getElementById('copyBtn');
    const likeBtn = document.getElementById('likeBtn');
    const unlikeBtn = document.getElementById('unlikeBtn');
    const readerBtn = document.getElementById('readerBtn');
    const regenerateBtn = document.getElementById('regenerateBtn');
    const speakBtn = document.getElementById('speakBtn');

    let currentJobId = null;
    let cachedGoal = "";
    let googleClientId = null;
    let userToken = "mock:user@deepsight.ai";
    let userEmail = "user@deepsight.ai";

    // Speech Synthesis states
    let synth = window.speechSynthesis;
    let utterance = null;
    let isSpeaking = false;

    // Translucent Popup Warning Guardrail
    function showWarningPopup(message) {
        let popup = document.getElementById('guardrailPopup');
        if (!popup) {
            popup = document.createElement('div');
            popup.id = 'guardrailPopup';
            popup.className = 'guardrail-popup hidden';
            document.body.appendChild(popup);
        }
        popup.innerHTML = `
            <div class="guardrail-popup-content">
                <div class="guardrail-popup-icon">⚠️</div>
                <h3>Word Limit Exceeded</h3>
                <p>${message}</p>
                <button id="closeGuardrailPopupBtn" class="guardrail-popup-btn">Got it</button>
            </div>
        `;
        popup.classList.remove('hidden');
        
        document.getElementById('closeGuardrailPopupBtn').addEventListener('click', () => {
            popup.classList.add('hidden');
        });
    }

    // Toggle System Prompt
    toggleSystemPromptBtn.addEventListener('click', () => {
        systemPromptPanel.classList.toggle('hidden');
    });

    // Speech Recognition for Voice Input
    let recognition = null;
    let isRecording = false;

    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        recognition.onstart = () => {
            isRecording = true;
            micBtn.classList.add('recording');
            micBtn.title = "Recording... Speak now";
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            const words = transcript.trim().split(/\s+/).filter(w => w.length > 0);
            if (words.length > 200) {
                showWarningPopup("Please limit your search query to a maximum of 200 words.");
                goalInput.value = words.slice(0, 200).join(" ");
            } else {
                goalInput.value = transcript;
            }
            goalInput.dispatchEvent(new Event('input'));
        };

        recognition.onerror = (e) => {
            console.error("Speech recognition error:", e);
            stopRecording();
        };

        recognition.onend = () => {
            stopRecording();
        };
    } else {
        micBtn.style.display = 'none';
    }

    function stopRecording() {
        isRecording = false;
        micBtn.classList.remove('recording');
        micBtn.title = "Voice Search";
        if (recognition) {
            try { recognition.stop(); } catch (e) {}
        }
    }

    micBtn.addEventListener('click', () => {
        if (!recognition) return;
        if (isRecording) {
            stopRecording();
        } else {
            recognition.start();
        }
    });

    // Auto-hide mic button when user types text in searchbar
    goalInput.addEventListener('input', () => {
        if (goalInput.value.trim().length > 0) {
            micBtn.classList.add('hidden');
        } else {
            micBtn.classList.remove('hidden');
        }
    });

    // New Chat
    newChatBtn.addEventListener('click', () => {
        currentJobId = null;
        welcomeScreen.style.display = 'block';
        progressTimeline.style.display = 'none';
        reportSection.style.display = 'none';
        logConsole.innerHTML = '';
        goalInput.value = '';
        goalInput.dispatchEvent(new Event('input'));
        goalInput.style.height = 'auto';
        goalInput.disabled = false;
        startBtn.disabled = false;
        goalInput.focus();
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
        
        // Mobile layout: close drawer if open
        closeSidebarDrawer();
    });

    // Auto-resize Textarea & Enforce 200 word count limit
    goalInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';

        const words = this.value.trim().split(/\s+/).filter(w => w.length > 0);
        if (words.length > 200) {
            showWarningPopup("Please limit your search query to a maximum of 200 words.");
            this.value = words.slice(0, 200).join(" ");
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        }
    });

    goalInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!startBtn.disabled) startBtn.click();
        }
    });

    // Auto-update model placeholders
    const providerDefaults = {
        groq:       { model: 'llama-3.1-8b-instant',       placeholder: 'Groq API Key' },
        gemini:     { model: 'gemini-2.5-flash',           placeholder: 'Google API Key' },
        claude:     { model: 'claude-3-5-sonnet-latest',   placeholder: 'Anthropic API Key' },
        openai:     { model: 'gpt-4o',                     placeholder: 'OpenAI API Key' },
        openrouter: { model: 'qwen/qwen-2.5-72b-instruct', placeholder: 'OpenRouter API Key' },
    };
    
    // Set initial placeholder on startup
    const initialDefault = providerDefaults['groq'];
    if (initialDefault) {
        llmKeyInput.placeholder = initialDefault.placeholder;
    }
    
    providerSelect.addEventListener('change', () => {
        const d = providerDefaults[providerSelect.value];
        if (d) {
            modelInput.value = d.model;
            llmKeyInput.placeholder = d.placeholder;
        }
    });

    // ----------------------------------------------------
    // Initialize application immediately
    fetchHistory();

    // Helper to inject Auth Header to all API requests
    function getAuthHeaders() {
        return {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${userToken}`
        };
    }

    // ----------------------------------------------------
    // SIDEBAR NAVIGATION & HISTORY
    // ----------------------------------------------------

    async function fetchHistory() {
        try {
            const res = await fetch('/api/research', {
                headers: getAuthHeaders()
            });
            if (!res.ok) return;
            const jobs = await res.json();
            historyList.innerHTML = '';

            let sessionIds = [];
            try {
                sessionIds = JSON.parse(sessionStorage.getItem('sessionResearchIds')) || [];
            } catch (e) {
                sessionIds = [];
            }

            const sessionJobs = jobs.filter(job => sessionIds.includes(job.id));

            if (sessionJobs.length === 0) {
                const placeholder = document.createElement('div');
                placeholder.className = 'no-history-placeholder';
                placeholder.textContent = 'No history of research yet';
                historyList.appendChild(placeholder);
            } else {
                sessionJobs.forEach(job => {
                    const btn = document.createElement('button');
                    btn.className = 'history-item';
                    btn.innerHTML = `<span class="goal-text">${job.goal}</span> <span class="date">${new Date(job.created_at).toLocaleDateString()}</span>`;
                    btn.onclick = () => loadJob(job.id, btn);
                    historyList.appendChild(btn);
                });
            }
        } catch (e) {
            console.error("Failed to load history", e);
        }
    }

    async function loadJob(jobId, btnElement) {
        currentJobId = jobId;
        settingsDropdownPanel.classList.add('hidden');
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
        if (btnElement) btnElement.classList.add('active');

        welcomeScreen.style.display = 'none';
        progressTimeline.style.display = 'none';
        logConsole.innerHTML = '';
        reportSection.style.display = 'none';
        
        // Mobile Drawer: Close on selection
        closeSidebarDrawer();

        // Cancel reading
        if (isSpeaking) {
            synth.cancel();
            isSpeaking = false;
            speakBtn.classList.remove('active');
        }

        try {
            const res = await fetch(`/api/research/${jobId}`, {
                headers: getAuthHeaders()
            });
            if (!res.ok) return;
            const data = await res.json();
            
            goalInput.value = '';
            goalInput.dispatchEvent(new Event('input'));
            goalInput.style.height = 'auto';
            goalInput.disabled = false;
            startBtn.disabled = false;

            if (data.final_report) {
                displayReport(data.final_report, jobId);
            } else if (data.status === 'IN_PROGRESS' || data.status === 'PENDING') {
                progressTimeline.style.display = 'block';
                statusBadge.textContent = 'Reconnecting...';
                connectSSE(jobId);
            }
        } catch (e) {
            console.error(e);
        }
    }
    // Sidebar Toggles & Collapsing
    const closeSidebarBtn = document.getElementById('closeSidebarBtn');
    
    // Check initial sidebar collapsed state on desktop
    const sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (sidebarCollapsed && window.innerWidth > 768) {
        sidebar.classList.add('collapsed');
    }

    sidebarToggleBtn.addEventListener('click', () => {
        if (window.innerWidth > 768) {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
        } else {
            sidebar.classList.toggle('open');
            drawerOverlay.style.display = sidebar.classList.contains('open') ? 'block' : 'none';
        }
    });

    if (closeSidebarBtn) {
        closeSidebarBtn.addEventListener('click', () => {
            if (window.innerWidth > 768) {
                sidebar.classList.add('collapsed');
                localStorage.setItem('sidebarCollapsed', 'true');
            } else {
                closeSidebarDrawer();
            }
        });
    }

    drawerOverlay.addEventListener('click', closeSidebarDrawer);

    function closeSidebarDrawer() {
        sidebar.classList.remove('open');
        drawerOverlay.style.display = 'none';
    }

    // Progress Dashboard controls
    const progressDashboard = document.getElementById('progressDashboard');
    const dashboardTimer = document.getElementById('dashboardTimer');
    const activeAgentName = document.getElementById('activeAgentName');
    const progressBarFill = document.getElementById('progressBarFill');
    const completedStepsCount = document.getElementById('completedStepsCount');
    
    let dashboardTimerInterval = null;
    let etaSecondsLeft = 510; // default estimated time of 8.5 minutes (8:30)

    function startProgressDashboard() {
        if (progressDashboard) {
            progressDashboard.classList.remove('hidden');
        }
        etaSecondsLeft = 510;
        updateDashboardTimerDisplay();
        
        if (dashboardTimerInterval) clearInterval(dashboardTimerInterval);
        
        dashboardTimerInterval = setInterval(() => {
            if (etaSecondsLeft > 5) {
                etaSecondsLeft--;
                updateDashboardTimerDisplay();
            }
        }, 1000);
        
        updateDashboardProgress('planner', 0);
    }

    function stopProgressDashboard(isSuccess) {
        if (dashboardTimerInterval) {
            clearInterval(dashboardTimerInterval);
            dashboardTimerInterval = null;
        }
        if (isSuccess) {
            if (progressBarFill) progressBarFill.style.width = '100%';
            if (completedStepsCount) completedStepsCount.textContent = 'Step 9 of 9';
            if (activeAgentName) activeAgentName.textContent = 'Completed';
            if (dashboardTimer) {
                dashboardTimer.textContent = '00:00';
                dashboardTimer.style.background = 'rgba(16, 185, 129, 0.1)';
                dashboardTimer.style.color = '#10b981';
            }
            updatePerimeterProgress(100);
            setTimeout(() => {
                if (progressDashboard) progressDashboard.classList.add('hidden');
            }, 3000);
        } else {
            if (progressDashboard) progressDashboard.classList.add('hidden');
        }
    }

    function updateDashboardTimerDisplay() {
        if (!dashboardTimer) return;
        const mins = String(Math.floor(etaSecondsLeft / 60)).padStart(2, '0');
        const secs = String(etaSecondsLeft % 60).padStart(2, '0');
        dashboardTimer.textContent = `${mins}:${secs}`;
    }

    function updatePerimeterProgress(progressPercent) {
        const card = document.getElementById('progressDashboard');
        if (!card) return;
        
        card.dataset.progressPercent = progressPercent;
        
        const rect = card.getBoundingClientRect();
        const W = rect.width;
        const H = rect.height;
        if (W === 0 || H === 0) return;
        
        const R = 16;
        const inset = 1.5;
        
        let svg = document.getElementById('progressPerimeterSvg');
        if (!svg) {
            svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('id', 'progressPerimeterSvg');
            svg.style.position = 'absolute';
            svg.style.top = '0';
            svg.style.left = '0';
            svg.style.width = '100%';
            svg.style.height = '100%';
            svg.style.pointerEvents = 'none';
            svg.style.overflow = 'visible';
            svg.style.borderRadius = '16px';
            
            const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
            const grad = document.createElementNS('http://www.w3.org/2000/svg', 'linearGradient');
            grad.setAttribute('id', 'perimeterGrad');
            grad.setAttribute('x1', '0%');
            grad.setAttribute('y1', '0%');
            grad.setAttribute('x2', '100%');
            grad.setAttribute('y2', '100%');
            
            const stop1 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
            stop1.setAttribute('offset', '0%');
            stop1.setAttribute('stop-color', '#38bdf8');
            
            const stop2 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
            stop2.setAttribute('offset', '100%');
            stop2.setAttribute('stop-color', '#a78bfa');
            
            grad.appendChild(stop1);
            grad.appendChild(stop2);
            defs.appendChild(grad);
            svg.appendChild(defs);
            
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('id', 'progressPerimeterPath');
            path.setAttribute('fill', 'none');
            path.setAttribute('stroke', 'url(#perimeterGrad)');
            path.setAttribute('stroke-width', '3');
            path.setAttribute('stroke-linecap', 'round');
            
            svg.appendChild(path);
            card.appendChild(svg);
        }
        
        const path = document.getElementById('progressPerimeterPath');
        if (path) {
            const r_in = R - inset;
            const w_in = W - inset;
            const h_in = H - inset;
            
            const d = `M ${R} ${inset} ` +
                      `A ${r_in} ${r_in} 0 0 0 ${inset} ${R} ` +
                      `L ${inset} ${H - R} ` +
                      `A ${r_in} ${r_in} 0 0 0 ${R} ${h_in} ` +
                      `L ${W - R} ${h_in} ` +
                      `A ${r_in} ${r_in} 0 0 0 ${w_in} ${H - R} ` +
                      `L ${w_in} ${R} ` +
                      `A ${r_in} ${r_in} 0 0 0 ${W - R} ${inset} ` +
                      `Z`;
            
            path.setAttribute('d', d);
            
            const totalLength = path.getTotalLength();
            path.style.strokeDasharray = totalLength;
            
            const progress = Math.max(0, Math.min(100, progressPercent));
            const offset = totalLength - (progress / 100) * totalLength;
            path.style.strokeDashoffset = offset;
        }
    }

    if (progressDashboard) {
        progressDashboard.dataset.progressPercent = "0";
        const resizeObserver = new ResizeObserver(() => {
            const pct = parseFloat(progressDashboard.dataset.progressPercent || "0");
            updatePerimeterProgress(pct);
        });
        resizeObserver.observe(progressDashboard);
    }

    function updateDashboardProgress(nodeType, findingsCount) {
        if (!progressDashboard) return;
        
        let stepName = "Planning";
        let stepCountStr = "Step 1 of 9";
        let progressPercent = 10;
        
        if (nodeType === 'planner') {
            stepName = "Planning Task Breakdown";
            stepCountStr = "Step 1 of 9";
            progressPercent = 10;
        } else if (nodeType === 'researcher') {
            const count = findingsCount || 0;
            const stepNum = Math.min(6, 2 + count);
            stepName = `Researching (Query #${count + 1})`;
            stepCountStr = `Step ${stepNum} of 9`;
            progressPercent = 10 + stepNum * 10;
            if (etaSecondsLeft > 120) etaSecondsLeft = Math.max(120, etaSecondsLeft - 60);
        } else if (nodeType === 'critic') {
            stepName = "Evaluating Quality & Score";
            stepCountStr = "Step 7 of 9";
            progressPercent = 75;
            etaSecondsLeft = Math.min(60, etaSecondsLeft);
        } else if (nodeType === 'editor' || nodeType === 'reporter') {
            stepName = "Writing & Formatting Report";
            stepCountStr = "Step 8 of 9";
            progressPercent = 90;
            etaSecondsLeft = Math.min(30, etaSecondsLeft);
        } else if (nodeType === 'end') {
            stepName = "Finalizing Report";
            stepCountStr = "Step 9 of 9";
            progressPercent = 100;
            etaSecondsLeft = 0;
        }
        
        if (activeAgentName) activeAgentName.textContent = stepName;
        if (completedStepsCount) completedStepsCount.textContent = stepCountStr;
        if (progressBarFill) progressBarFill.style.width = `${progressPercent}%`;
        
        updatePerimeterProgress(progressPercent);
    }

    // ----------------------------------------------------
    // RESEARCH RUNS & SSE EVENT PROGRESS
    // ----------------------------------------------------

    startBtn.addEventListener('click', async () => {
        const goal = goalInput.value.trim();
        const llmProvider = providerSelect.value;
        const llmModel = modelInput.value.trim();
        const llmKey = llmKeyInput.value.trim();
        const searchKey = searchKeyInput.value.trim();
        const systemPrompt = systemPromptInput.value.trim() || "You are an expert Research Assistant.";

        if (!goal) return;

        // Front-end Guardrail Check
        const lowerGoal = goal.toLowerCase();
        const sensitiveKeywords = [
            'race', 'sex', 'nudity', 'adult content', 'pornography', 'porn', 
            'hate speech', 'discrimination', 'discriminate', 'discriminatory', 
            'explicit content', 'nude', 'sexual'
        ];
        const hasSensitive = sensitiveKeywords.some(keyword => {
            const regex = new RegExp('\\b' + keyword + '\\b', 'i');
            return regex.test(lowerGoal);
        });

        if (hasSensitive) {
            welcomeScreen.style.display = 'none';
            logConsole.innerHTML = '';
            reportSection.style.display = 'none';
            progressTimeline.style.display = 'block';
            statusBadge.textContent = 'Refused';
            statusBadge.className = 'status-badge error';
            
            appendAgentCard('error', "I cannot answer this query due to safety guidelines.");
            
            const loader = document.getElementById('active-loader');
            if (loader) loader.remove();
            
            displayReport({
                title: "Safety Refusal",
                report_markdown: "I cannot answer this query due to safety guidelines."
            });
            
            stopProgressDashboard(false);
            return;
        }

        const words = goal.split(/\s+/).filter(w => w.length > 0);
        if (words.length > 200) {
            showWarningPopup("Please limit your search query to a maximum of 200 words before submitting.");
            return;
        }
        cachedGoal = goal;

        // Auto-collapse settings
        settingsDropdownPanel.classList.add('hidden');

        // Reset UI
        welcomeScreen.style.display = 'none';
        logConsole.innerHTML = '';
        reportSection.style.display = 'none';
        progressTimeline.style.display = 'block';
        statusBadge.textContent = 'Processing';
        statusBadge.className = 'status-badge active';
        startBtn.disabled = true;
        
        // Clear textbar
        goalInput.value = '';
        goalInput.dispatchEvent(new Event('input'));
        goalInput.style.height = 'auto';
        goalInput.disabled = true;

        if (isSpeaking) {
            synth.cancel();
            isSpeaking = false;
            speakBtn.classList.remove('active');
        }

        try {
            const response = await fetch('/api/research', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ goal, system_prompt: systemPrompt, llm_provider: llmProvider, llm_model: llmModel, llm_api_key: llmKey || null, search_api_key: searchKey || null })
            });

            if (!response.ok) {
                let errMsg = `HTTP error! status: ${response.status}`;
                try {
                    const errData = await response.json();
                    if (errData && errData.detail) errMsg = errData.detail;
                } catch(e) {}
                throw new Error(errMsg);
            }
            const data = await response.json();
            currentJobId = data.id;
            
            let sessionIds = [];
            try {
                sessionIds = JSON.parse(sessionStorage.getItem('sessionResearchIds')) || [];
            } catch (e) {
                sessionIds = [];
            }
            if (!sessionIds.includes(data.id)) {
                sessionIds.push(data.id);
                sessionStorage.setItem('sessionResearchIds', JSON.stringify(sessionIds));
            }
            
            fetchHistory(); // Refresh sidebar history
            connectSSE(data.id);

        } catch (error) {
            appendAgentCard('error', `${error.message}`);
            startBtn.disabled = false;
            goalInput.disabled = false;
            goalInput.value = cachedGoal; // Restore input on error
            goalInput.style.height = (goalInput.scrollHeight) + 'px';
        }
    });

    function connectSSE(jobId) {
        // EventSource does not support authorization headers natively. 
        // We append the authorization token as a query parameter!
        const eventSource = new EventSource(`/api/research/${jobId}/stream?token=${userToken}`);
        
        startProgressDashboard();

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            appendAgentCard(data.node, data.status, data.findings);
            
            updateDashboardProgress(data.node, data.findings ? data.findings.length : 0);

            if (data.node === 'end' || data.node === 'error') {
                eventSource.close();
                startBtn.disabled = false;
                goalInput.disabled = false;
                
                // Remove active loader
                const loader = document.getElementById('active-loader');
                if (loader) loader.remove();
                
                if (data.node === 'end') {
                    statusBadge.textContent = 'Completed';
                    statusBadge.className = 'status-badge success';
                    stopProgressDashboard(true);
                    if (data.report) displayReport(data.report, jobId);
                } else {
                    statusBadge.textContent = 'Failed';
                    statusBadge.className = 'status-badge error';
                    stopProgressDashboard(false);
                    if (cachedGoal && goalInput.value === '') {
                        goalInput.value = cachedGoal;
                        goalInput.style.height = (goalInput.scrollHeight) + 'px';
                    }
                }
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
            startBtn.disabled = false;
            goalInput.disabled = false;
            stopProgressDashboard(false);
            const loader = document.getElementById('active-loader');
            if (loader) loader.remove();
        };
    }

    function appendAgentCard(nodeType, message, findings) {
        // Remove existing loader if any
        const loader = document.getElementById('active-loader');
        if (loader) loader.remove();

        // Prevent duplicate logs
        const lastCard = logConsole.lastElementChild;
        if (lastCard && lastCard.dataset.msg === message) {
            addLoader(nodeType);
            return;
        }

        const div = document.createElement('div');
        div.className = 'agent-card';
        div.dataset.msg = message;
        
        let icon = '⚡';
        let title = nodeType ? nodeType.charAt(0).toUpperCase() + nodeType.slice(1) : 'System';
        
        if (nodeType === 'planner') icon = '📋';
        if (nodeType === 'researcher') icon = '🔍';
        if (nodeType === 'reporter') icon = '✍️';
        if (nodeType === 'critic') icon = '⚖️';
        if (nodeType === 'editor') icon = '✨';
        if (nodeType === 'end') icon = '✅';
        if (nodeType === 'error') icon = '❌';

        const timeStr = new Date().toLocaleTimeString();

        let subQueriesHtml = '';
        if (nodeType === 'researcher' && findings && findings.length > 0) {
            const latestFinding = findings[findings.length - 1];
            if (latestFinding.sub_queries) {
                const tags = latestFinding.sub_queries.map(q => `<span class="subquery-tag">${q}</span>`).join('');
                subQueriesHtml = `<div class="agent-card-subqueries">${tags}</div>`;
            }
        }

        div.innerHTML = `
            <div class="agent-card-header">
                <div class="agent-icon bg-${nodeType}">${icon}</div>
                ${title}
                <span style="font-size: 0.75rem; color: #9ca3af; margin-left: auto;">[${timeStr}]</span>
            </div>
            <div class="agent-card-body">
                ${message}
                ${subQueriesHtml}
            </div>
        `;
        logConsole.appendChild(div);
        
        addLoader(nodeType);
        
        // Auto scroll to bottom of chatContainer
        chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
    }

    function addLoader(nodeType) {
        if (nodeType !== 'end' && nodeType !== 'error') {
            const loaderDiv = document.createElement('div');
            loaderDiv.id = 'active-loader';
            loaderDiv.className = 'agent-card pulsing-loader';
            loaderDiv.style.opacity = '0.6';
            loaderDiv.innerHTML = `
                <div class="agent-card-header" style="color: #6b7280; font-weight: 500;">
                    <div class="agent-icon" style="background: #e5e7eb; color: #6b7280;">🔄</div>
                    Agent is thinking...
                </div>
            `;
            logConsole.appendChild(loaderDiv);
            chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
        }
    }

    function cleanUrl(url) {
        return String(url || '').trim().replace(/[.,;:\])}>]+$/g, '');
    }

    function collectReportUrls(markdown, sources) {
        const urls = [];
        const seen = new Set();
        const addUrl = (url) => {
            const clean = cleanUrl(url);
            if (clean && !seen.has(clean)) {
                seen.add(clean);
                urls.push(clean);
            }
        };

        (sources || []).forEach(addUrl);
        const matches = String(markdown || '').match(/https?:\/\/[^\s\)\]\}>"']+/g) || [];
        matches.forEach(addUrl);
        return urls;
    }

    function stripReferenceSections(markdown) {
        const lines = String(markdown || '').split(/\r?\n/);
        const kept = [];
        let skipping = false;
        let skipLevel = 7;

        lines.forEach((line) => {
            const heading = line.match(/^(#{1,6})\s+/);
            const referenceHeading = line.match(/^(#{1,6})\s*(references|sources|source list|bibliography|works cited)\b.*$/i);

            if (referenceHeading) {
                skipping = true;
                skipLevel = referenceHeading[1].length;
                return;
            }

            if (skipping && heading && heading[1].length <= skipLevel) {
                skipping = false;
            }

            if (skipping) return;

            if (/^\s*(?:\*\*)?(references|sources|source list|bibliography|works cited)(?:\*\*)?\s*:?\s*$/i.test(line)) return;
            if (/^\s*(?:[-*]|\d+[.)])?\s*(?:\[\d+\]\s*)?(?:https?:\/\/|\[[^\]]+\]\(https?:\/\/)/i.test(line)) return;

            kept.push(line);
        });

        return kept.join('\n');
    }

    function normalizeReportMarkdown(markdown, sources, title) {
        const referenceUrls = collectReportUrls(markdown, sources);
        let cleaned = stripReferenceSections(markdown);

        cleaned = cleaned.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '$1');
        cleaned = cleaned.replace(/https?:\/\/[^\s\)\]\}>"']+/g, '');
        cleaned = cleaned.replace(/\s*\[\d+(?:,\s*\d+)*\]/g, '');
        cleaned = cleaned.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();

        if (!/^\s*#\s+/i.test(cleaned)) {
            cleaned = `# ${title}\n\n${cleaned}`;
        }

        if (referenceUrls.length > 0) {
            cleaned += `\n\n### References\n\n`;
            referenceUrls.slice(0, 8).forEach((url) => {
                cleaned += `- [${url}](${url})\n`;
            });
        }

        return cleaned;
    }

    function displayReport(report, jobId) {
        reportSection.style.display = 'block';
        
        let reportObj = report;
        
        // Handle stringified JSON formats safely
        if (typeof reportObj === 'string') {
            try {
                reportObj = JSON.parse(reportObj);
            } catch (e) {
                // Ignore, keep as string
            }
        }
        
        let title = "Research Report";
        let markdown = "";
        let sources = [];
        
        if (reportObj && typeof reportObj === 'object') {
            title = reportObj.title || 'Research Report';
            markdown = reportObj.report_markdown || reportObj.markdown || "";
            sources = reportObj.sources_used || [];
            
            // Handle double-serialized JSON case inside report_markdown field
            if (markdown.trim().startsWith('{')) {
                try {
                    const parsedMarkdown = JSON.parse(markdown.trim());
                    if (parsedMarkdown.report_markdown) {
                        markdown = parsedMarkdown.report_markdown;
                        if (parsedMarkdown.title) title = parsedMarkdown.title;
                        if (parsedMarkdown.sources_used) sources = parsedMarkdown.sources_used;
                    }
                } catch (err) {
                    // Ignore, use original markdown string
                }
            }
        } else {
            // It's a plain text string
            markdown = String(report);
        }
        
        const finalMarkdown = normalizeReportMarkdown(markdown, sources, title);

        reportContent.innerHTML = marked.parse(finalMarkdown);
        
        // Save the raw text for copy/read action helpers
        reportContent.dataset.rawMarkdown = finalMarkdown;
        reportContent.dataset.rawText = reportContent.innerText || reportContent.textContent;
        
        // Scroll to output
        setTimeout(() => window.scrollTo({ top: reportSection.offsetTop - 80, behavior: 'smooth' }), 100);
    }

    // ----------------------------------------------------
    // REPORT TOOLBAR CONTROL ACTIONS
    // ----------------------------------------------------

    // Copy Content
    copyBtn.addEventListener('click', async () => {
        const textToCopy = reportContent.dataset.rawMarkdown || reportContent.innerText;
        if (!textToCopy) return;

        try {
            await navigator.clipboard.writeText(textToCopy);
            // Dynamic feedback
            const originalHtml = copyBtn.innerHTML;
            copyBtn.innerHTML = '✅';
            setTimeout(() => { copyBtn.innerHTML = originalHtml; }, 1500);
        } catch (err) {
            console.error("Could not copy text", err);
        }
    });

    // Like Report
    likeBtn.addEventListener('click', () => {
        likeBtn.classList.toggle('active');
        unlikeBtn.classList.remove('active');
    });

    // Unlike Report
    unlikeBtn.addEventListener('click', () => {
        unlikeBtn.classList.toggle('active');
        likeBtn.classList.remove('active');
    });

    // Fullscreen reader window
    readerBtn.addEventListener('click', () => {
        const reportHtml = reportContent.innerHTML;
        if (!reportHtml) return;

        const readerWindow = window.open(
            '',
            '_blank',
            `popup=yes,width=${screen.availWidth},height=${screen.availHeight},left=0,top=0`
        );
        if (!readerWindow) return;

        const title = reportContent.querySelector('h1')?.textContent || 'Research Report';
        const safeTitle = title.replace(/[<>&"]/g, '');

        readerWindow.document.write(`
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>${safeTitle}</title>
                <style>
                    :root { color-scheme: dark; }
                    * { box-sizing: border-box; }
                    body {
                        margin: 0;
                        background: #030304;
                        color: #edf0f4;
                        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                        font-size: 18px;
                        line-height: 1.85;
                        font-weight: 400;
                    }
                    main {
                        width: min(860px, calc(100vw - 40px));
                        margin: 0 auto;
                        padding: 56px 0 72px;
                    }
                    h1, h2, h3 {
                        color: #f8fafc;
                        line-height: 1.25;
                        font-weight: 650;
                    }
                    h1 {
                        font-size: clamp(2rem, 4vw, 3.2rem);
                        margin: 0 0 2rem;
                        padding-bottom: 1rem;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.12);
                    }
                    h2 { font-size: 1.55rem; margin: 2.75rem 0 1rem; }
                    h3 { font-size: 1.2rem; margin: 2rem 0 0.8rem; color: #e5e7eb; }
                    p, li { color: #e8ebef; }
                    p { margin: 0 0 1.35rem; }
                    ul, ol { padding-left: 1.45rem; margin: 0 0 1.35rem; }
                    li { margin: 0.45rem 0; }
                    a { color: #d8b4fe; text-decoration-thickness: 1px; text-underline-offset: 4px; }
                    code {
                        background: rgba(255, 255, 255, 0.08);
                        border-radius: 6px;
                        padding: 0.12rem 0.35rem;
                    }
                    @media (max-width: 640px) {
                        body { font-size: 16.5px; line-height: 1.75; }
                        main { width: min(100vw - 28px, 860px); padding-top: 32px; }
                    }
                </style>
            </head>
            <body>
                <main>${reportHtml}</main>
                <script>
                    window.moveTo(0, 0);
                    window.resizeTo(screen.availWidth, screen.availHeight);
                    const fullscreenRequest = document.documentElement.requestFullscreen?.();
                    fullscreenRequest?.catch?.(() => {});
                <\/script>
            </body>
            </html>
        `);
        readerWindow.document.close();
    });

    // Regenerate current query
    regenerateBtn.addEventListener('click', () => {
        if (!cachedGoal && currentJobId) {
            // Find current research goal from UI if not cached
            const activeItem = document.querySelector('.history-item.active .goal-text');
            if (activeItem) {
                cachedGoal = activeItem.textContent.trim();
            }
        }

        if (cachedGoal) {
            goalInput.value = cachedGoal;
            startBtn.click();
        }
    });

    // Read Out Loud (Browser Speech Synthesis)
    speakBtn.addEventListener('click', () => {
        if (isSpeaking) {
            synth.cancel();
            isSpeaking = false;
            speakBtn.classList.remove('active');
            speakBtn.title = "Read Out Loud";
        } else {
            const textToRead = reportContent.dataset.rawText;
            if (!textToRead) return;

            utterance = new SpeechSynthesisUtterance(textToRead.slice(0, 12000)); // Cap length
            utterance.onend = () => {
                isSpeaking = false;
                speakBtn.classList.remove('active');
                speakBtn.title = "Read Out Loud";
            };
            utterance.onerror = () => {
                isSpeaking = false;
                speakBtn.classList.remove('active');
            };

            isSpeaking = true;
            speakBtn.classList.add('active');
            speakBtn.title = "Stop Reading";
            synth.speak(utterance);
        }
    });
});
