document.addEventListener('DOMContentLoaded', () => {
    fetchEvents();
    setupEventListeners();
});

function setupEventListeners() {
    const exportBtn = document.getElementById('export-powerbi-btn');
    exportBtn.addEventListener('click', () => {
        window.location.href = `${API_BASE_URL}/export/powerbi`;
    });
}

async function fetchEvents() {
    try {
        const response = await fetch(`${API_BASE_URL}/events`);
        if (!response.ok) throw new Error('Network response was not ok');
        const events = await response.json();
        
        renderEventsList(events);
        document.getElementById('event-count').textContent = events.length;
        
        // Auto select first event if available
        if (events.length > 0) {
            selectEvent(events[0].event_id, events[0]);
        }
    } catch (error) {
        console.error('Error fetching events:', error);
        document.getElementById('events-list').innerHTML = `
            <div class="empty-state">
                <i class='bx bx-error-circle'></i>
                <p>無法載入事件資料</p>
            </div>
        `;
    }
}

function renderEventsList(events) {
    const listContainer = document.getElementById('events-list');
    
    if (events.length === 0) {
        listContainer.innerHTML = `
            <div class="empty-state">
                <p>目前沒有事件資料</p>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = events.map(event => {
        const timeStr = new Date(event.first_reported_at).toLocaleString('zh-TW', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
        
        const impactClass = event.max_impact_score > 75 ? 'high-impact' : '';
        const impactIcon = event.max_impact_score > 75 ? '<i class="bx bxs-hot"></i>' : '';

        return `
            <div class="event-card" data-id="${event.event_id}" onclick="selectEvent('${event.event_id}', ${JSON.stringify(event).replace(/"/g, '&quot;')})">
                <div class="event-time">
                    <i class='bx bx-time-five'></i> ${timeStr}
                </div>
                <div class="event-title">${event.event_title}</div>
                <div class="event-meta">
                    <div class="meta-item ${impactClass}">
                        ${impactIcon} Max Impact: ${event.max_impact_score}
                    </div>
                    <div class="meta-item">
                        <i class='bx bx-buildings'></i> ${event.impact_count} 家公司
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

async function selectEvent(eventId, eventData) {
    // Update UI selection state
    document.querySelectorAll('.event-card').forEach(card => {
        card.classList.remove('selected');
        if (card.dataset.id === eventId) {
            card.classList.add('selected');
        }
    });

    const contentContainer = document.getElementById('impact-content');
    contentContainer.innerHTML = '<div class="loading-spinner">載入影響力分析中...</div>';

    try {
        const response = await fetch(`${API_BASE_URL}/events/${eventId}/impacts`);
        if (!response.ok) throw new Error('Network response was not ok');
        const impacts = await response.json();
        
        renderImpactDetails(eventData, impacts);
    } catch (error) {
        console.error('Error fetching impacts:', error);
        contentContainer.innerHTML = `
            <div class="empty-state">
                <i class='bx bx-error-circle'></i>
                <p>無法載入影響力分析</p>
            </div>
        `;
    }
}

function renderImpactDetails(eventData, impacts) {
    const contentContainer = document.getElementById('impact-content');
    
    let html = `
        <div class="event-detail-header">
            <h2>${eventData.event_title}</h2>
            <div class="event-detail-summary">
                ${eventData.event_summary}
            </div>
        </div>
        <div class="impact-list">
    `;

    if (impacts.length === 0) {
        html += `<p style="color: var(--text-muted)">無影響力分析資料。</p>`;
    } else {
        html += impacts.map(imp => {
            const dirClass = imp.market_direction.toLowerCase();
            const signalClass = imp.classification === 'Signal' ? 'signal' : '';
            
            const directionIcon = {
                'Bullish': '<i class="bx bx-trending-up"></i>',
                'Bearish': '<i class="bx bx-trending-down"></i>',
                'Neutral': '<i class="bx bx-minus"></i>'
            }[imp.market_direction] || '';

            return `
                <div class="impact-card" data-direction="${imp.market_direction}">
                    <div class="company-info">
                        <span class="ticker">${imp.ticker}</span>
                        <span class="company-name">${imp.company_name}</span>
                    </div>
                    <div class="analysis-details">
                        <div class="scores-row">
                            <span class="score-pill ${dirClass}">
                                ${directionIcon} ${imp.market_direction} (${imp.sentiment_label})
                            </span>
                            <span class="score-pill">
                                Impact: ${imp.impact_score}
                            </span>
                            <span class="score-pill">
                                Surprise: ${imp.surprise_score}
                            </span>
                            ${imp.classification === 'Signal' ? `
                                <span class="score-pill signal">
                                    <i class='bx bx-radar'></i> Signal
                                </span>
                            ` : ''}
                            <span class="score-pill" style="opacity: 0.7">
                                ${imp.time_horizon}
                            </span>
                        </div>
                        <div class="analysis-text">
                            ${imp.analysis_notes}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    html += `</div>`;
    contentContainer.innerHTML = html;
}
