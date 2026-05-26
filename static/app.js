document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const apiKeyStatusDot = document.getElementById('apiKeyStatusDot');
    const apiKeyStatusText = document.getElementById('apiKeyStatusText');
    const toggleApiBtn = document.getElementById('toggleApiBtn');
    const apiDrawer = document.getElementById('apiDrawer');
    const apiKeyInput = document.getElementById('apiKeyInput');
    const saveApiKeyBtn = document.getElementById('saveApiKeyBtn');
    const clearApiKeyBtn = document.getElementById('clearApiKeyBtn');
    
    const searchForm = document.getElementById('searchForm');
    const urlInput = document.getElementById('urlInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const heroSection = document.getElementById('heroSection');
    const exampleBtns = document.querySelectorAll('.example-btn');
    
    const loadingSection = document.getElementById('loadingSection');
    const loadingStatusText = document.getElementById('loadingStatusText');
    const step1 = document.getElementById('step1');
    const step2 = document.getElementById('step2');
    const step3 = document.getElementById('step3');
    const step4 = document.getElementById('step4');
    
    const dashboard = document.getElementById('dashboard');
    const siteTitle = document.getElementById('siteTitle');
    const siteUrl = document.getElementById('siteUrl');
    const siteDescription = document.getElementById('siteDescription');
    const siteOverview = document.getElementById('siteOverview');
    
    const servicesList = document.getElementById('servicesList');
    const techStackContainer = document.getElementById('techStackContainer');
    const totalCost = document.getElementById('totalCost');
    const costTimeline = document.getElementById('costTimeline');
    const costBreakdownBody = document.getElementById('costBreakdownBody');
    const audienceDesc = document.getElementById('audienceDesc');
    const audienceSegments = document.getElementById('audienceSegments');
    const improvementsList = document.getElementById('improvementsList');
    const crawlerMapRoot = document.getElementById('crawlerMapRoot');
    
    const chatMessages = document.getElementById('chatMessages');
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChatBtn');
    const clearChatBtn = document.getElementById('clearChatBtn');
    const quickQuestionsContainer = document.getElementById('quickQuestionsContainer');
    
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toastMessage');

    // App State
    let localApiKey = localStorage.getItem('gemini_api_key') || '';
    let currentAnalysisData = null;
    let chatHistory = [];
    let loadingInterval = null;

    // Initialize API Key UI
    updateApiKeyUI();

    // Check if the backend has an API key configured
    checkServerKeyStatus();

    // Event Listeners
    toggleApiBtn.addEventListener('click', () => {
        apiDrawer.classList.toggle('open');
    });

    saveApiKeyBtn.addEventListener('click', () => {
        const key = apiKeyInput.value.trim();
        if (key) {
            localApiKey = key;
            localStorage.setItem('gemini_api_key', key);
            updateApiKeyUI();
            apiDrawer.classList.remove('open');
            showToast('API Key saved locally!', 'success');
        } else {
            showToast('Please enter a valid API Key', 'error');
        }
    });

    clearApiKeyBtn.addEventListener('click', () => {
        localApiKey = '';
        localStorage.removeItem('gemini_api_key');
        apiKeyInput.value = '';
        updateApiKeyUI();
        apiDrawer.classList.remove('open');
        showToast('Local API Key cleared.', 'info');
        checkServerKeyStatus();
    });

    // Quick examples
    exampleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            urlInput.value = btn.getAttribute('data-url');
            searchForm.dispatchEvent(new Event('submit'));
        });
    });

    // Form Submit (Analyze Website)
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (!url) return;

        // Reset UI
        heroSection.classList.add('hidden');
        dashboard.classList.add('hidden');
        loadingSection.classList.remove('hidden');
        resetLoadingSteps();
        
        // Disable search input
        analyzeBtn.disabled = true;

        // Start step-by-step progress simulation (Visual UI flow)
        runProgressSteps();

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    apiKey: localApiKey
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to analyze website');
            }

            // Stop animations and mark all done
            clearInterval(loadingInterval);
            completeAllSteps();

            // Store result
            currentAnalysisData = data;
            
            // Populating layout data
            setTimeout(() => {
                renderDashboard(data);
                loadingSection.classList.add('hidden');
                dashboard.classList.remove('hidden');
                analyzeBtn.disabled = false;
                
                // Reset Chat panel for the new analysis
                resetChatSession(data);
            }, 800);

        } catch (error) {
            clearInterval(loadingInterval);
            loadingSection.classList.add('hidden');
            heroSection.classList.remove('hidden');
            analyzeBtn.disabled = false;
            showToast(error.message, 'error');
        }
    });

    // Chat Events
    chatInput.addEventListener('input', () => {
        // Auto grow textarea
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight) + 'px';
        
        sendChatBtn.disabled = chatInput.value.trim() === '';
    });

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendChatBtn.addEventListener('click', sendMessage);
    clearChatBtn.addEventListener('click', () => {
        if (currentAnalysisData) {
            resetChatSession(currentAnalysisData);
            showToast('Chat history cleared', 'info');
        }
    });

    // Helper functions for UI
    function updateApiKeyUI() {
        if (localApiKey) {
            apiKeyStatusDot.classList.add('active');
            apiKeyStatusText.textContent = 'API Key: Active (Local)';
            apiKeyInput.value = localApiKey;
        } else {
            apiKeyStatusDot.classList.remove('active');
            apiKeyStatusText.textContent = 'API Key: Missing';
            apiKeyInput.value = '';
        }
    }

    async function checkServerKeyStatus() {
        // If local key exists, no need to check server
        if (localApiKey) return;
        
        // We will make a silent attempt to check if .env has it by analyzing a dummy or checking server config
        // For simplicity, we assume if local key is missing, it will check the dot indicator.
        apiKeyStatusText.textContent = 'API Key: Checking server...';
        
        // We can check this by examining if the dot should stay active
        // Let's call the analyze endpoint with a dummy to see if it complains about key missing.
        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: 'http://test-key-check.com', apiKey: 'CHECK_STATUS_ONLY' })
            });
            // If it returns a 500 or 400 with "crawl failed" or similar, it means the key exists!
            // If it returns "Gemini API key not found", it means key is missing.
            const data = await response.json();
            if (data.error && data.error.includes('key not found')) {
                apiKeyStatusDot.classList.remove('active');
                apiKeyStatusText.textContent = 'API Key: Missing';
            } else {
                apiKeyStatusDot.classList.add('active');
                apiKeyStatusText.textContent = 'API Key: Active (Server)';
            }
        } catch (e) {
            apiKeyStatusDot.classList.remove('active');
            apiKeyStatusText.textContent = 'API Key: Configure in UI';
        }
    }

    function resetLoadingSteps() {
        step1.className = 'progress-step active';
        step2.className = 'progress-step';
        step3.className = 'progress-step';
        step4.className = 'progress-step';
        loadingStatusText.textContent = 'Connecting to target website...';
    }

    function runProgressSteps() {
        let step = 1;
        clearInterval(loadingInterval);

        loadingInterval = setInterval(() => {
            if (step === 1) {
                step1.className = 'progress-step done';
                step2.className = 'progress-step active';
                loadingStatusText.textContent = 'Crawling subpages (About, Services, Contact)...';
                step = 2;
            } else if (step === 2) {
                step2.className = 'progress-step done';
                step3.className = 'progress-step active';
                loadingStatusText.textContent = 'Running deep signatures checks on headers & scripts...';
                step = 3;
            } else if (step === 3) {
                loadingStatusText.textContent = 'Performing strictly grounded Gemini AI analysis...';
                step = 4;
            } else if (step === 4) {
                step3.className = 'progress-step done';
                step4.className = 'progress-step active';
                loadingStatusText.textContent = 'Compiling budget breakdowns and final consultant node...';
                clearInterval(loadingInterval);
            }
        }, 2200);
    }

    function completeAllSteps() {
        step1.className = 'progress-step done';
        step2.className = 'progress-step done';
        step3.className = 'progress-step done';
        step4.className = 'progress-step done';
        loadingStatusText.textContent = 'Analysis Completed!';
    }

    // Helper to parse numbers from range e.g. "₹1,50,000 - ₹2,00,000" -> 150000
    function extractCostValue(costStr) {
        if (!costStr) return 100000;
        const clean = costStr.replace(/[^0-9-]/g, '');
        const parts = clean.split('-');
        if (parts.length > 0 && parts[0]) {
            return parseInt(parts[0], 10);
        }
        return 100000;
    }

    // Render Dashboard Elements
    function renderDashboard(data) {
        siteTitle.textContent = data.title || 'Parsed Website';
        siteUrl.textContent = data.url;
        siteUrl.href = data.url;
        siteUrl.target = '_blank';
        siteDescription.textContent = data.description || 'No description extracted';
        siteOverview.textContent = data.overview || '';

        // 1. Render Interactive Crawler map tree
        crawlerMapRoot.innerHTML = '';
        
        // Add Homepage Node
        const homeNode = document.createElement('div');
        homeNode.className = 'map-node root';
        const parsedBase = new URL(data.url);
        homeNode.innerHTML = `
            <div class="node-circle"><i class="fa-solid fa-house"></i></div>
            <span class="node-label">Homepage</span>
            <span class="node-url">${parsedBase.hostname}</span>
        `;
        crawlerMapRoot.appendChild(homeNode);

        // Add subpage nodes if crawled
        if (data.crawled_pages && data.crawled_pages.length > 1) {
            // Skips the first page (homepage)
            data.crawled_pages.slice(1).forEach(pageUrl => {
                // Add connector line
                const connector = document.createElement('div');
                connector.className = 'map-connection active';
                crawlerMapRoot.appendChild(connector);

                // Add Node
                const subNode = document.createElement('div');
                subNode.className = 'map-node subpage';
                const parsedSub = new URL(pageUrl);
                
                // Get label from path name
                let pathLabel = parsedSub.pathname.replace(/^\/|\/$/g, '');
                if (pathLabel.length > 12) pathLabel = pathLabel.substring(0, 10) + '...';
                if (!pathLabel) pathLabel = 'Subpage';

                subNode.innerHTML = `
                    <div class="node-circle"><i class="fa-solid fa-file-code"></i></div>
                    <span class="node-label">${pathLabel}</span>
                    <span class="node-url">${parsedSub.pathname}</span>
                `;
                crawlerMapRoot.appendChild(subNode);
            });
        } else {
            // Just add one warning/info node if SPA or only single page crawled
            const connector = document.createElement('div');
            connector.className = 'map-connection';
            crawlerMapRoot.appendChild(connector);

            const singleNode = document.createElement('div');
            singleNode.className = 'map-node subpage';
            singleNode.innerHTML = `
                <div class="node-circle" style="border-color: var(--accent-tertiary); color: var(--accent-tertiary);">
                    <i class="fa-solid fa-circle-nodes"></i>
                </div>
                <span class="node-label">Single-Page SPA</span>
                <span class="node-url">Dynamic Router</span>
            `;
            crawlerMapRoot.appendChild(singleNode);
        }

        // Render Services
        servicesList.innerHTML = '';
        if (data.services && data.services.length > 0) {
            data.services.forEach(service => {
                const item = document.createElement('div');
                item.className = 'service-item';
                item.innerHTML = `
                    <h3>${service.name}</h3>
                    <p>${service.description}</p>
                `;
                servicesList.appendChild(item);
            });
        } else {
            servicesList.innerHTML = '<p class="site-overview">No distinct service modules found.</p>';
        }

        // Render Tech Stack
        techStackContainer.innerHTML = '';
        if (data.tech_stack && data.tech_stack.length > 0) {
            data.tech_stack.forEach(stack => {
                const catDiv = document.createElement('div');
                catDiv.className = 'tech-category';
                
                const title = document.createElement('span');
                title.className = 'tech-category-title';
                title.textContent = stack.category;
                catDiv.appendChild(title);

                const badgesDiv = document.createElement('div');
                badgesDiv.className = 'tech-badges';
                stack.technologies.forEach(tech => {
                    const badge = document.createElement('span');
                    badge.className = 'tech-badge';
                    badge.textContent = tech;
                    badgesDiv.appendChild(badge);
                });
                catDiv.appendChild(badgesDiv);
                
                techStackContainer.appendChild(catDiv);
            });
        } else {
            techStackContainer.innerHTML = '<p class="site-overview">No tech stack details analyzed.</p>';
        }

        // Cost estimation & dynamic budget weights
        totalCost.textContent = data.cost_estimation?.total_estimated_range || 'N/A';
        costTimeline.textContent = data.cost_estimation?.timeline || 'N/A';
        
        costBreakdownBody.innerHTML = '';
        if (data.cost_estimation?.breakdown && data.cost_estimation.breakdown.length > 0) {
            
            // First step: Calculate max cost to set percentages relatively
            const costs = data.cost_estimation.breakdown.map(item => extractCostValue(item.cost_range));
            const maxCost = Math.max(...costs);
            const sumCost = costs.reduce((a, b) => a + b, 0);

            data.cost_estimation.breakdown.forEach((item, index) => {
                const tr = document.createElement('tr');
                const costVal = costs[index];
                
                // Calculate percentage relative to the sum budget
                let percent = sumCost > 0 ? Math.round((costVal / sumCost) * 100) : 25;
                if (percent < 5) percent = 5; // minimum width to show indicator

                tr.innerHTML = `
                    <td><strong>${item.module}</strong></td>
                    <td>
                        <div class="progress-track" title="${percent}% budget weight">
                            <div class="progress-fill" style="width: ${percent}%"></div>
                        </div>
                    </td>
                    <td><span class="text-accent">${item.cost_range}</span></td>
                    <td class="site-overview">${item.explanation}</td>
                `;
                costBreakdownBody.appendChild(tr);
            });
        } else {
            costBreakdownBody.innerHTML = '<tr><td colspan="4" style="text-align:center">No breakdown data available</td></tr>';
        }

        // Audience
        audienceDesc.textContent = data.target_audience?.description || 'No target audience description available.';
        audienceSegments.innerHTML = '';
        if (data.target_audience?.segments && data.target_audience.segments.length > 0) {
            data.target_audience.segments.forEach(seg => {
                const pill = document.createElement('span');
                pill.className = 'segment-pill';
                pill.textContent = seg;
                audienceSegments.appendChild(pill);
            });
        }

        // Actionable Improvements with Priority indicators
        improvementsList.innerHTML = '';
        if (data.improvements && data.improvements.length > 0) {
            data.improvements.forEach(imp => {
                const item = document.createElement('div');
                const typeLower = (imp.type || 'uiux').toLowerCase();
                
                let typeClass = 'imp-uiux';
                if (typeLower.includes('seo')) typeClass = 'imp-seo';
                else if (typeLower.includes('perf') || typeLower.includes('speed')) typeClass = 'imp-performance';
                else if (typeLower.includes('sec')) typeClass = 'imp-security';

                item.className = `improvement-item ${typeClass}`;
                item.innerHTML = `
                    <div style="display:flex; flex-direction:column; gap: 0.25rem;">
                        <div><span class="improvement-tag">${imp.type || 'UX'}</span></div>
                        <div class="improvement-content">${imp.suggestion}</div>
                    </div>
                `;
                improvementsList.appendChild(item);
            });
        } else {
            improvementsList.innerHTML = '<p class="site-overview">No recommendations proposed.</p>';
        }
    }

    // Reset Chat panel with initial website welcome state
    function resetChatSession(data) {
        chatHistory = [];
        chatMessages.innerHTML = '';

        // Add welcome message
        const welcome = document.createElement('div');
        welcome.className = 'message system-message';
        welcome.innerHTML = `
            <div class="message-content">
                <p><strong>AI Technical Consultant</strong> is ready to discuss <strong>${data.title || 'this site'}</strong>. Ask me details on cloning the architecture, reducing costs, or optimizing SEO.</p>
                <div class="chat-chips" id="quickQuestionsContainer"></div>
            </div>
        `;
        chatMessages.appendChild(welcome);

        // Populate quick questions chips
        const chipsContainer = welcome.querySelector('#quickQuestionsContainer');
        const defaultQuestions = [
            "What database model matches this site?",
            "How can we reduce clone costs by 30%?",
            "What hosting infrastructure would you recommend?",
            "Critique their technical SEO weaknesses"
        ];
        
        const questions = data.quick_questions && data.quick_questions.length > 0 
            ? data.quick_questions 
            : defaultQuestions;

        questions.forEach(question => {
            const chip = document.createElement('button');
            chip.className = 'chat-chip';
            chip.textContent = question;
            chip.addEventListener('click', () => {
                chatInput.value = question;
                sendMessage();
            });
            chipsContainer.appendChild(chip);
        });

        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Send Message
    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text || !currentAnalysisData) return;

        // Clear input box
        chatInput.value = '';
        chatInput.style.height = 'auto';
        sendChatBtn.disabled = true;

        // Append User Bubble
        appendChatBubble('user', text);

        // Append Typing Bubble
        const typingBubble = appendChatBubble('assistant', '<i class="fa-solid fa-ellipsis fa-fade"></i> AI is thinking...');

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: text,
                    history: chatHistory,
                    websiteData: currentAnalysisData,
                    apiKey: localApiKey
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to connect');
            }

            // Remove typing bubble
            typingBubble.remove();

            // Append AI response
            appendChatBubble('assistant', data.response);

            // Save history
            chatHistory.push({ role: 'user', content: text });
            chatHistory.push({ role: 'assistant', content: data.response });

        } catch (error) {
            typingBubble.remove();
            appendChatBubble('assistant', `⚠️ **Error:** ${error.message}. Make sure your Gemini API Key is entered correctly.`);
            showToast(error.message, 'error');
        }
    }

    function appendChatBubble(role, content) {
        const msg = document.createElement('div');
        msg.className = `message ${role}`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        if (role === 'user') {
            contentDiv.textContent = content;
        } else {
            // AI responses can be markdown
            contentDiv.innerHTML = parseMarkdown(content);
        }

        msg.appendChild(contentDiv);
        chatMessages.appendChild(msg);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return msg;
    }

    // Tiny markdown parser for beautiful rendering without external dependencies
    function parseMarkdown(text) {
        let html = text;
        
        // Escape HTML tags to prevent XSS except the ones we create
        html = html
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Restore formatting code brackets
        html = html.replace(/&lt;i class=&quot;(.*?)&quot;&gt;&lt;\/i&gt;/g, '<i class="$1"></i>');

        // Bold: **text**
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Headings: ### text, ## text
        html = html.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.*?)$/gm, '<h1>$1</h1>');
        
        // Unordered lists: - item, * item
        html = html.replace(/^\s*[-*]\s+(.*?)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*?<\/li>)+/g, '<ul>$&</ul>');

        // Ordered lists: 1. item
        html = html.replace(/^\s*\d+\.\s+(.*?)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*?<\/li>)+/g, '<ul>$&</ul>');
        
        // Paragraph newlines
        html = html.replace(/\n\n/g, '</p><p>');
        html = html.replace(/\n/g, '<br>');
        
        // Wrap in single paragraph if it doesn't start with block element
        if (!html.startsWith('<h') && !html.startsWith('<u') && !html.startsWith('<p')) {
            html = '<p>' + html + '</p>';
        }
        
        return html;
    }

    // Toast system
    function showToast(message, type = 'error') {
        toastMessage.textContent = message;
        
        const icon = toast.querySelector('.toast-icon');
        if (type === 'success') {
            toast.style.borderColor = 'var(--accent-success)';
            icon.className = 'fa-solid fa-circle-check toast-icon';
            icon.style.color = 'var(--accent-success)';
        } else if (type === 'info') {
            toast.style.borderColor = 'var(--accent-tertiary)';
            icon.className = 'fa-solid fa-circle-info toast-icon';
            icon.style.color = 'var(--accent-tertiary)';
        } else {
            toast.style.borderColor = 'var(--accent-danger)';
            icon.className = 'fa-solid fa-circle-exclamation toast-icon';
            icon.style.color = 'var(--accent-danger)';
        }

        toast.classList.remove('hidden');
        
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 4000);
    }
});
