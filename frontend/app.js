document.addEventListener('DOMContentLoaded', () => {
    // 初始化
    fetchEvents();
    setupEventListeners();
    setupNavigation();
});

function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.view-section');
    const titleText = document.getElementById('page-title-text');
    const subtitleText = document.getElementById('page-subtitle-text');

    const titles = {
        'view-overview': { title: '即時市場事件分析', sub: 'AI 聚合市場事件並預測供應鏈影響力' },
        'view-supplychain': { title: '供應鏈追蹤', sub: '追蹤單一企業受市場波動之影響履歷' },
        'view-report': { title: '深度分析報告', sub: '由 AI 統整今日市場脈動並生成總結' }
    };

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            
            // 移除所有 active 狀態
            navItems.forEach(nav => nav.classList.remove('active'));
            views.forEach(view => {
                view.classList.remove('active');
                view.style.display = 'none';
            });
            
            // 加上新的 active 狀態
            item.classList.add('active');
            const targetId = item.getAttribute('data-target');
            const targetView = document.getElementById(targetId);
            
            if (targetView) {
                targetView.classList.add('active');
                targetView.style.display = 'block';
            }

            // 更新標題
            if (titles[targetId]) {
                titleText.textContent = titles[targetId].title;
                subtitleText.textContent = titles[targetId].sub;
            }

            // 根據不同 View 觸發資料載入
            if (targetId === 'view-supplychain') {
                fetchCompanies();
            }
        });
    });
}

function setupEventListeners() {
    const exportBtn = document.getElementById('export-powerbi-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            window.location.href = `${API_BASE_URL}/export/powerbi`;
        });
    }

    const reportBtn = document.getElementById('generate-report-btn');
    if (reportBtn) {
        reportBtn.addEventListener('click', () => {
            generateReport();
        });
    }
}

/* =========================================================
   View 1: 即時事件監控
   ========================================================= */
async function fetchEvents() {
    try {
        const response = await fetch(`${API_BASE_URL}/events`);
        if (!response.ok) throw new Error('Network response was not ok');
        const events = await response.json();
        
        renderEventsList(events);
        document.getElementById('event-count').textContent = events.length;
        
        if (events.length > 0) {
            selectEvent(events[0].event_id, events[0]);
        }
    } catch (error) {
        console.error('Error fetching events:', error);
        document.getElementById('events-list').innerHTML = `<div class="empty-state"><p>無法載入資料</p></div>`;
    }
}

function renderEventsList(events) {
    const listContainer = document.getElementById('events-list');
    if (events.length === 0) {
        listContainer.innerHTML = `<div class="empty-state"><p>目前沒有事件資料</p></div>`;
        return;
    }

    listContainer.innerHTML = events.map(event => {
        const timeStr = new Date(event.first_reported_at).toLocaleString('zh-TW', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const impactClass = event.max_impact_score > 75 ? 'high-impact' : '';
        const impactIcon = event.max_impact_score > 75 ? '<i class="bx bxs-hot"></i>' : '';

        return `
            <div class="event-card" data-id="${event.event_id}" onclick="selectEvent('${event.event_id}', ${JSON.stringify(event).replace(/"/g, '&quot;')})">
                <div class="event-time"><i class='bx bx-time-five'></i> ${timeStr}</div>
                <div class="event-title">${event.event_title}</div>
                <div class="event-meta">
                    <div class="meta-item ${impactClass}">${impactIcon} Max Impact: ${event.max_impact_score}</div>
                    <div class="meta-item"><i class='bx bx-buildings'></i> ${event.impact_count} 家公司</div>
                </div>
            </div>
        `;
    }).join('');
}

async function selectEvent(eventId, eventData) {
    document.querySelectorAll('#events-list .event-card').forEach(card => {
        card.classList.remove('selected');
        if (card.dataset.id === eventId) card.classList.add('selected');
    });

    const contentContainer = document.getElementById('impact-content');
    contentContainer.innerHTML = '<div class="loading-spinner">載入影響力分析中...</div>';

    try {
        const response = await fetch(`${API_BASE_URL}/events/${eventId}/impacts`);
        const impacts = await response.json();
        renderImpactDetails(eventData, impacts);
    } catch (error) {
        contentContainer.innerHTML = `<div class="empty-state"><p>無法載入分析</p></div>`;
    }
}

function renderImpactDetails(eventData, impacts) {
    const contentContainer = document.getElementById('impact-content');
    
    // 生成新聞來源連結
    let sourcesHtml = '';
    if (eventData.source_links && eventData.source_links.length > 0) {
        sourcesHtml = '<div style="margin-top: 12px; font-size: 0.85rem; color: var(--text-muted);"><strong>相關新聞來源：</strong>';
        eventData.source_links.forEach(link => {
            sourcesHtml += `<a href="${link.url}" target="_blank" style="color: var(--accent-primary); text-decoration: none; margin-left: 8px;">[${link.source}]</a>`;
        });
        sourcesHtml += '</div>';
    }

    let html = `
        <div class="event-detail-header">
            <h2>${eventData.event_title}</h2>
            <div class="event-detail-summary">${eventData.event_summary}</div>
            ${sourcesHtml}
        </div>
        <div class="impact-list">
    `;

    if (impacts.length === 0) {
        html += `<p style="color: var(--text-muted)">無資料。</p>`;
    } else {
        html += impacts.map(imp => {
            const dirClass = imp.market_direction.toLowerCase();
            const directionIcon = {'Bullish': '<i class="bx bx-trending-up"></i>', 'Bearish': '<i class="bx bx-trending-down"></i>', 'Neutral': '<i class="bx bx-minus"></i>'}[imp.market_direction] || '';

            return `
                <div class="impact-card" data-direction="${imp.market_direction}">
                    <div class="company-info">
                        <span class="ticker">${imp.ticker}</span>
                        <span class="company-name">${imp.company_name}</span>
                    </div>
                    <div class="analysis-details">
                        <div class="scores-row">
                            <span class="score-pill bullish">Positive: ${imp.positive_score}</span>
                            <span class="score-pill neutral">Neutral: ${imp.neutral_score}</span>
                            <span class="score-pill bearish">Negative: ${imp.negative_score}</span>
                        </div>
                        <div class="scores-row">
                            <span class="score-pill ${dirClass}">${directionIcon} ${imp.market_direction}</span>
                            <span class="score-pill">Impact: ${imp.impact_score}</span>
                            <span class="score-pill">Surprise: ${imp.surprise_score}</span>
                            <span class="score-pill" style="opacity: 0.7">${imp.time_horizon}</span>
                            ${imp.classification === 'Signal' ? `<span class="score-pill signal"><i class='bx bx-radar'></i> Signal</span>` : ''}
                        </div>
                        <div class="analysis-text">${imp.analysis_notes}</div>
                    </div>
                </div>
            `;
        }).join('');
    }
    contentContainer.innerHTML = html + `</div>`;
}

/* =========================================================
   View 2: 供應鏈追蹤
   ========================================================= */
let companiesLoaded = false;
async function fetchCompanies() {
    if (companiesLoaded) return; // 避免重複載入
    
    try {
        const response = await fetch(`${API_BASE_URL}/companies`);
        const companies = await response.json();
        renderCompaniesList(companies);
        companiesLoaded = true;
        
        if (companies.length > 0) {
            selectCompany(companies[0].company_id, companies[0].company_name);
        }
    } catch (error) {
        console.error('Error fetching companies:', error);
    }
}

function renderCompaniesList(companies) {
    const listContainer = document.getElementById('companies-list');
    listContainer.innerHTML = companies.map(comp => `
        <div class="event-card company-card" data-id="${comp.company_id}" onclick="selectCompany('${comp.company_id}', '${comp.company_name}')">
            <div class="event-title">${comp.company_name} <span class="ticker">${comp.ticker}</span></div>
            <div class="event-meta">
                <div class="meta-item"><i class='bx bx-category'></i> ${comp.industry}</div>
            </div>
        </div>
    `).join('');
}

async function selectCompany(companyId, companyName) {
    document.querySelectorAll('.company-card').forEach(card => {
        card.classList.remove('selected');
        if (card.dataset.id === companyId) card.classList.add('selected');
    });

    const contentContainer = document.getElementById('company-impact-content');
    contentContainer.innerHTML = '<div class="loading-spinner">載入企業影響紀錄中...</div>';

    try {
        const response = await fetch(`${API_BASE_URL}/companies/${companyId}/impacts`);
        const impacts = await response.json();
        renderCompanyImpacts(companyName, impacts);
    } catch (error) {
        contentContainer.innerHTML = `<div class="empty-state"><p>無法載入紀錄</p></div>`;
    }
}

function renderCompanyImpacts(companyName, impacts) {
    const contentContainer = document.getElementById('company-impact-content');
    
    if (impacts.length === 0) {
        contentContainer.innerHTML = `<div class="empty-state"><p>${companyName} 近期無事件影響紀錄</p></div>`;
        return;
    }

    let html = `
        <div class="event-detail-header">
            <h2>${companyName} 近期影響履歷</h2>
        </div>
        <div class="impact-list">
    `;

    html += impacts.map(imp => {
        const timeStr = new Date(imp.first_reported_at).toLocaleString('zh-TW', { month: 'short', day: 'numeric' });
        const dirClass = imp.market_direction.toLowerCase();
        const directionIcon = {'Bullish': '<i class="bx bx-trending-up"></i>', 'Bearish': '<i class="bx bx-trending-down"></i>', 'Neutral': '<i class="bx bx-minus"></i>'}[imp.market_direction] || '';

        return `
            <div class="impact-card" data-direction="${imp.market_direction}">
                <div class="company-info" style="width: 140px;">
                    <span class="event-time" style="margin-bottom:0;"><i class='bx bx-time'></i> ${timeStr}</span>
                    <span class="score-pill ${dirClass}" style="margin-top:8px; display:inline-block; width:fit-content;">${directionIcon} ${imp.market_direction}</span>
                </div>
                <div class="analysis-details">
                    <div style="font-weight:600; margin-bottom:8px; color:white;">${imp.event_title}</div>
                    <div class="scores-row">
                        <span class="score-pill">Impact: ${imp.impact_score}</span>
                        <span class="score-pill">Surprise: ${imp.surprise_score}</span>
                        ${imp.classification === 'Signal' ? `<span class="score-pill signal"><i class='bx bx-radar'></i> Signal</span>` : ''}
                    </div>
                    <div class="analysis-text" style="margin-top:8px;">${imp.analysis_notes}</div>
                </div>
            </div>
        `;
    }).join('');

    contentContainer.innerHTML = html + `</div>`;
}

/* =========================================================
   View 3: 深度分析報告
   ========================================================= */
async function generateReport() {
    const contentContainer = document.getElementById('report-content');
    const btn = document.getElementById('generate-report-btn');
    
    // UI Loading state
    btn.disabled = true;
    btn.innerHTML = `<i class='bx bx-loader-alt bx-spin'></i> 正在由 Gemini 生成中...`;
    contentContainer.innerHTML = `
        <div class="empty-state">
            <i class='bx bx-loader-alt bx-spin' style="font-size: 3rem; color: var(--accent-primary);"></i>
            <p>Gemini Pro 正在閱讀今日所有新聞與事件，請稍候...</p>
        </div>
    `;

    try {
        const response = await fetch(`${API_BASE_URL}/report/daily`);
        const data = await response.json();
        
        contentContainer.innerHTML = `
            <div class="report-html-content">
                ${data.report_html}
            </div>
        `;
    } catch (error) {
        contentContainer.innerHTML = `<div class="empty-state"><p>生成報告時發生錯誤，請確認後端運行狀態。</p></div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class='bx bx-bot'></i> AI 重新生成報告`;
    }
}
