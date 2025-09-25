// Analytics Dashboard JavaScript
class AnalyticsDashboard {
    constructor() {
        this.roomId = new URLSearchParams(window.location.search).get('room') || 'all';
        this.currentHours = 24;
        this.charts = {};
        this.refreshInterval = null;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.initCharts();
        this.loadData();
        
        // Auto-refresh every 60 seconds (reduced frequency to prevent performance issues)
        this.refreshInterval = setInterval(() => {
            if (!document.hidden) {
                this.loadData();
            }
        }, 60000);
        
        // Update page title with room ID
        document.title = `Analytics - Room ${this.roomId}`;
        
        // Add room info to header
        const header = document.querySelector('.app-header');
        if (header) {
            const roomInfo = document.createElement('p');
            roomInfo.className = 'room-info';
            roomInfo.innerHTML = `Room ID: <code>${this.roomId}</code>`;
            roomInfo.style.color = 'var(--muted)';
            roomInfo.style.marginTop = '10px';
            header.appendChild(roomInfo);
        }
    }
    
    setupEventListeners() {
        // Time filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.currentHours = parseInt(e.target.dataset.hours);
                this.loadData();
            });
        });
        
        // Refresh button
        window.refreshData = () => {
            this.loadData();
        };
    }
    
    initCharts() {
        try {
            // Participant activity chart
            const participantCanvas = document.getElementById('participantChart');
            if (!participantCanvas) {
                console.warn('Participant chart canvas not found');
                return;
            }
            const participantCtx = participantCanvas.getContext('2d');
        this.charts.participant = new Chart(participantCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Current Participants',
                    data: [],
                    borderColor: '#34d399',
                    backgroundColor: 'rgba(52, 211, 153, 0.1)',
                    tension: 0.4,
                    fill: true
                }, {
                    label: 'Peak Participants',
                    data: [],
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.05)',
                    tension: 0.4,
                    borderDash: [5, 5]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#f9fafb'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: '#94a3b8'
                        },
                        grid: {
                            color: 'rgba(148, 163, 184, 0.1)'
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: '#94a3b8'
                        },
                        grid: {
                            color: 'rgba(148, 163, 184, 0.1)'
                        }
                    }
                }
            }
        });
        
        // Events chart (doughnut)
        const eventsCtx = document.getElementById('eventsChart').getContext('2d');
        this.charts.events = new Chart(eventsCtx, {
            type: 'doughnut',
            data: {
                labels: ['Joins', 'Leaves'],
                datasets: [{
                    data: [0, 0],
                    backgroundColor: ['#34d399', '#f87171'],
                    borderColor: ['#10b981', '#ef4444'],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#f9fafb'
                        }
                    }
                }
            }
        });
        } catch (error) {
            console.error('Error initializing charts:', error);
        }
    }
    
    async loadData() {
        try {
            this.setLoading(true);
            
            const response = await fetch(`/api/rooms/${this.roomId}/analytics?hours=${this.currentHours}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.updateDashboard(data);
            
        } catch (error) {
            console.error('Error loading analytics data:', error);
            this.showError(`Failed to load data: ${error.message}`);
        } finally {
            this.setLoading(false);
        }
    }
    
    updateDashboard(data) {
        // Update summary stats
        this.updateStats(data.summary);
        
        // Update charts
        this.updateParticipantChart(data.time_series);
        this.updateEventsChart(data.time_series);
        
        // Update events list
        this.updateEventsList(data.events);
        
        console.log('Dashboard updated successfully');
    }
    
    updateStats(summary) {
        document.getElementById('currentParticipants').textContent = summary.current_participants || 0;
        document.getElementById('totalParticipants').textContent = summary.total_participants || 0;
        document.getElementById('peakParticipants').textContent = summary.peak_participants || 0;
        document.getElementById('totalEvents').textContent = summary.total_events || 0;
        
        // Add change indicators (would need historical data for real implementation)
        const changes = [
            { id: 'currentChange', value: '+0' },
            { id: 'totalChange', value: '+0' },
            { id: 'peakChange', value: '+0' },
            { id: 'eventsChange', value: '+0' }
        ];
        
        changes.forEach(change => {
            const element = document.getElementById(change.id);
            element.textContent = `${change.value} (no change)`;
            element.className = 'stat-change';
        });
    }
    
    updateParticipantChart(timeSeries) {
        if (!timeSeries || timeSeries.length === 0) {
            return;
        }
        
        // Limit data points to prevent performance issues (max 100 points)
        const maxDataPoints = 100;
        const limitedTimeSeries = timeSeries.length > maxDataPoints 
            ? timeSeries.slice(-maxDataPoints) 
            : timeSeries;
        
        const labels = limitedTimeSeries.map(item => {
            const date = new Date(item.timestamp);
            return date.toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit' 
            });
        });
        
        const currentData = limitedTimeSeries.map(item => item.current_participants || 0);
        const peakData = limitedTimeSeries.map(item => item.peak_participants || 0);
        
        // Check if chart exists before updating
        if (this.charts.participant) {
            this.charts.participant.data.labels = labels;
            this.charts.participant.data.datasets[0].data = currentData;
            this.charts.participant.data.datasets[1].data = peakData;
            this.charts.participant.update('none');
        }
    }
    
    updateEventsChart(timeSeries) {
        if (!timeSeries || timeSeries.length === 0) {
            return;
        }
        
        const totalJoins = timeSeries.reduce((sum, item) => sum + (item.total_joins || 0), 0);
        const totalLeaves = timeSeries.reduce((sum, item) => sum + (item.total_leaves || 0), 0);
        
        this.charts.events.data.datasets[0].data = [totalJoins, totalLeaves];
        this.charts.events.update('none');
    }
    
    updateEventsList(events) {
        const eventsList = document.getElementById('eventsList');
        
        if (!eventsList) {
            console.warn('Events list element not found');
            return;
        }
        
        if (!events || events.length === 0) {
            eventsList.innerHTML = '<p style="text-align: center; color: var(--muted); padding: 20px;">No recent activity</p>';
            return;
        }
        
        // Limit events to prevent performance issues (max 50 events)
        const maxEvents = 50;
        const limitedEvents = events.length > maxEvents ? events.slice(-maxEvents) : events;
        
        const eventsHTML = limitedEvents.map(event => {
            const time = new Date(event.timestamp).toLocaleTimeString();
            const eventClass = event.event_type === 'join' ? 'event-join' : 'event-leave';
            const icon = event.event_type === 'join' ? '👋' : '👋';
            
            return `
                <div class="event-item">
                    <div>
                        <span class="event-type ${eventClass}">${icon} ${event.event_type}</span>
                        <span style="margin-left: 12px; color: var(--text);">
                            ${event.participant_name || event.participant_id.substr(0, 8)}
                        </span>
                    </div>
                    <div class="event-time">${time}</div>
                </div>
            `;
        }).join('');
        
        eventsList.innerHTML = eventsHTML;
    }
    
    setLoading(loading) {
        const refreshIcon = document.getElementById('refreshIcon');
        if (loading) {
            refreshIcon.innerHTML = '<span class="loading-spinner"></span>';
        } else {
            refreshIcon.textContent = '🔄';
        }
    }
    
    showError(message) {
        // Create error notification
        const notification = document.createElement('div');
        notification.className = 'notification notification-error show';
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-icon">❌</span>
                <span class="notification-message">${message}</span>
            </div>
            <button class="notification-close" onclick="this.parentElement.remove()">✕</button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }
    
    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        // Destroy charts
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
    }
}

// Initialize dashboard when DOM is loaded
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new AnalyticsDashboard();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (dashboard) {
        dashboard.destroy();
    }
});