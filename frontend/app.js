document.addEventListener('DOMContentLoaded', () => {
    // Auth & Navigation Elements
    const authContainer = document.getElementById('authContainer');
    const appContainer = document.getElementById('appContainer');
    const userEmailSpan = document.getElementById('userEmail');
    const signOutBtn = document.getElementById('signOutBtn');
    const demoSignInBtn = document.getElementById('demoSignInBtn');
    const authWarning = document.getElementById('authWarning');
    
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
    let userToken = localStorage.getItem('deepsight_user_token');
    let userEmail = localStorage.getItem('deepsight_user_email');

    // Speech Synthesis states
    let synth = window.speechSynthesis;
    let utterance = null;
    let isSpeaking = false;

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
            goalInput.value = transcript;
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
    // AUTHENTICATION LOGIC (Google & Demo Fallback)
    // ----------------------------------------------------

    // Initialize Auth state
    initAuth();

    async function initAuth() {
        try {
            const configRes = await fetch('/api/config');
            if (configRes.ok) {
                const configData = await configRes.json();
                googleClientId = configData.google_client_id;
            }
        } catch (err) {
            console.error("Failed to fetch App Configuration", err);
        }

        if (userToken && userEmail) {
            // Already signed in
            showAppWorkspace(userEmail);
        } else {
            // Signed out, show landing sign-in page
            showAuthScreen();
        }
    }

    function showAuthScreen() {
        authContainer.style.display = 'flex';
        appContainer.style.display = 'none';

        if (googleClientId) {
            authWarning.classList.add('hidden');
            // Load Google Sign-In SDK
            if (window.google) {
                google.accounts.id.initialize({
                    client_id: googleClientId,
                    callback: handleGoogleCredentialResponse
                });
                google.accounts.id.renderButton(
                    document.getElementById("googleSignInBtn"),
                    { theme: "outline", size: "large", width: 250 }
                );
            }
        } else {
            // No client ID, show developer warning info
            authWarning.classList.remove('hidden');
        }
    }

    function showAppWorkspace(email) {
        authContainer.style.display = 'none';
        appContainer.style.display = 'flex';
        userEmailSpan.textContent = email;
        fetchHistory();
    }

    // Google Sign-In callback
    function handleGoogleCredentialResponse(response) {
        // credential is the JWT payload returned by Google
        const token = response.credential;
        // Parse email from JWT payload roughly to show in user profile
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            const payload = JSON.parse(jsonPayload);
            
            localStorage.setItem('deepsight_user_token', token);
            localStorage.setItem('deepsight_user_email', payload.email);
            userToken = token;
            userEmail = payload.email;

            showAppWorkspace(payload.email);
        } catch (e) {
            console.error("Failed to parse Google JWT", e);
        }
    }

    // Demo Sign-in fallback
    demoSignInBtn.addEventListener('click', () => {
        const demoEmail = "demo@deepsight.ai";
        const demoToken = "mock:demo@deepsight.ai";
        localStorage.setItem('deepsight_user_token', demoToken);
        localStorage.setItem('deepsight_user_email', demoEmail);
        userToken = demoToken;
        userEmail = demoEmail;
        showAppWorkspace(demoEmail);
    });

    // Sign Out
    signOutBtn.addEventListener('click', () => {
        if (isSpeaking) {
            synth.cancel();
        }
        localStorage.removeItem('deepsight_user_token');
        localStorage.removeItem('deepsight_user_email');
        userToken = null;
        userEmail = null;
        currentJobId = null;
        welcomeScreen.style.display = 'block';
        progressTimeline.style.display = 'none';
        reportSection.style.display = 'none';
        logConsole.innerHTML = '';
        goalInput.value = '';
        showAuthScreen();
    });

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
            if (!res.ok) {
                if (res.status === 401) signOutBtn.click();
                return;
            }
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

    // Mobile drawer toggles
    sidebarToggleBtn.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        drawerOverlay.style.display = sidebar.classList.contains('open') ? 'block' : 'none';
    });

    drawerOverlay.addEventListener('click', closeSidebarDrawer);

    function closeSidebarDrawer() {
        sidebar.classList.remove('open');
        drawerOverlay.style.display = 'none';
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

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            currentJobId = data.id;
            
            fetchHistory(); // Refresh sidebar history
            connectSSE(data.id);

        } catch (error) {
            appendAgentCard('error', `Error: ${error.message}`);
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
