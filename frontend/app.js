document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('startBtn');
    const goalInput = document.getElementById('goalInput');
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
    
    const toggleSystemPromptBtn = document.getElementById('toggleSystemPromptBtn');
    const systemPromptPanel = document.getElementById('systemPromptPanel');
    const systemPromptInput = document.getElementById('systemPrompt');
    const downloadBtn = document.getElementById('downloadBtn');
    const historyList = document.getElementById('historyList');
    const newChatBtn = document.getElementById('newChatBtn');

    let currentJobId = null;
    let cachedGoal = "";

    // Toggle System Prompt
    toggleSystemPromptBtn.addEventListener('click', () => {
        systemPromptPanel.classList.toggle('hidden');
    });

    // New Chat
    newChatBtn.addEventListener('click', () => {
        currentJobId = null;
        welcomeScreen.style.display = 'block';
        progressTimeline.style.display = 'none';
        reportSection.style.display = 'none';
        logConsole.innerHTML = '';
        goalInput.value = '';
        goalInput.style.height = 'auto';
        goalInput.disabled = false;
        startBtn.disabled = false;
        goalInput.focus();
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
    });

    // Auto-resize Textarea
    goalInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    goalInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!startBtn.disabled) startBtn.click();
        }
    });

    // Auto-update model placeholders
    const providerDefaults = {
        openrouter: { model: 'qwen/qwen-2.5-72b-instruct', placeholder: 'LLM Key (sk-or-v1-...)' },
        groq:       { model: 'llama-3.3-70b-versatile',    placeholder: 'LLM Key (gsk_...)' },
        openai:     { model: 'gpt-4o',                     placeholder: 'LLM Key (sk-...)' },
    };
    
    providerSelect.addEventListener('change', () => {
        const d = providerDefaults[providerSelect.value];
        if (d) {
            modelInput.value = d.model;
            llmKeyInput.placeholder = d.placeholder;
        }
    });

    // Fetch History on Load
    fetchHistory();

    async function fetchHistory() {
        try {
            const res = await fetch('/api/research');
            if (!res.ok) return;
            const jobs = await res.json();
            historyList.innerHTML = '';
            jobs.forEach(job => {
                const btn = document.createElement('button');
                btn.className = 'history-item';
                btn.innerHTML = `<span class="goal-text">${job.goal}</span> <span class="date">${new Date(job.created_at).toLocaleDateString()}</span>`;
                btn.onclick = () => loadJob(job.id, btn);
                historyList.appendChild(btn);
            });
        } catch (e) {
            console.error("Failed to load history", e);
        }
    }

    async function loadJob(jobId, btnElement) {
        currentJobId = jobId;
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
        if (btnElement) btnElement.classList.add('active');

        welcomeScreen.style.display = 'none';
        progressTimeline.style.display = 'none';
        logConsole.innerHTML = '';
        reportSection.style.display = 'none';
        
        try {
            const res = await fetch(`/api/research/${jobId}`);
            if (!res.ok) return;
            const data = await res.json();
            
            // Do NOT populate goalInput if it's already complete, to mimic ChatGPT
            goalInput.value = '';
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

    startBtn.addEventListener('click', async () => {
        const goal = goalInput.value.trim();
        const llmProvider = providerSelect.value;
        const llmModel = modelInput.value.trim();
        const llmKey = llmKeyInput.value.trim();
        const searchKey = searchKeyInput.value.trim();
        const systemPrompt = systemPromptInput.value.trim() || "You are an expert Research Assistant.";

        if (!goal) return;
        cachedGoal = goal;

        // Reset UI
        welcomeScreen.style.display = 'none';
        logConsole.innerHTML = '';
        reportSection.style.display = 'none';
        progressTimeline.style.display = 'block';
        statusBadge.textContent = 'Processing';
        statusBadge.className = 'status-badge active';
        startBtn.disabled = true;
        downloadBtn.classList.add('hidden');
        
        // Clear textbar
        goalInput.value = '';
        goalInput.style.height = 'auto';
        goalInput.disabled = true;

        try {
            const response = await fetch('/api/research', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ goal, system_prompt: systemPrompt, llm_provider: llmProvider, llm_model: llmModel, llm_api_key: llmKey || null, search_api_key: searchKey || null })
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            currentJobId = data.id;
            
            fetchHistory(); // Refresh sidebar
            connectSSE(data.id);

        } catch (error) {
            appendAgentCard('error', `Error: ${error.message}`);
            startBtn.disabled = false;
            goalInput.disabled = false;
            goalInput.value = cachedGoal; // Restore on error
            goalInput.style.height = (goalInput.scrollHeight) + 'px';
        }
    });

    function connectSSE(jobId) {
        const eventSource = new EventSource(`/api/research/${jobId}/stream`);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            appendAgentCard(data.node, data.status, data.findings);

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
                    if (data.report) displayReport(data.report, jobId);
                } else {
                    statusBadge.textContent = 'Failed';
                    statusBadge.className = 'status-badge error';
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
            const loader = document.getElementById('active-loader');
            if (loader) loader.remove();
        };
    }

    function appendAgentCard(nodeType, message, findings) {
        // Remove existing loader if any
        const loader = document.getElementById('active-loader');
        if (loader) loader.remove();

        // Prevent duplicate spam
        const lastCard = logConsole.lastElementChild;
        if (lastCard && lastCard.dataset.msg === message) {
            // Re-append loader if not end/error
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
        
        // Auto scroll to bottom
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
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
        }
    }

    function displayReport(report, jobId) {
        reportSection.style.display = 'block';
        let markdown = `# ${report.title || 'Research Report'}\n\n`;
        if (report.report_markdown) markdown += `${report.report_markdown}\n\n`;
        if (report.sources_used && report.sources_used.length > 0) {
            markdown += `### Sources\n\n`;
            report.sources_used.forEach(s => markdown += `- [${s}](${s})\n`);
        }

        reportContent.innerHTML = marked.parse(markdown);
        
        const blob = new Blob([markdown], { type: 'text/markdown' });
        downloadBtn.href = URL.createObjectURL(blob);
        downloadBtn.download = `report_${jobId.substring(0,8)}.md`;
        downloadBtn.classList.remove('hidden');

        setTimeout(() => window.scrollTo({ top: reportSection.offsetTop - 80, behavior: 'smooth' }), 100);
    }
});
