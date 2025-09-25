// Enhanced Room Management for Live Seminar Platform

class RoomManager {
  constructor() {
    this.elements = {
      createRoomBtn: document.getElementById('createRoomBtn'),
      roomCreation: document.getElementById('roomCreation'),
      roomTitleInput: document.getElementById('roomTitle'),
      roomDescInput: document.getElementById('roomDescription'),
      maxParticipantsInput: document.getElementById('maxParticipants'),
      roomPasswordInput: document.getElementById('roomPassword'),
      confirmCreateBtn: document.getElementById('createRoomSubmitBtn'),
      cancelCreateBtn: document.getElementById('cancelCreateBtn'),
      roomList: document.getElementById('roomList')
    };
    
    this.rooms = [];
    this.currentTab = 'rooms';
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.loadRooms();
    
    // Refresh room list every 10 seconds
    setInterval(() => this.loadRooms(), 10000);
  }

  setupEventListeners() {
    // Main action buttons
    this.elements.createRoomBtn.addEventListener('click', () => {
      this.showCreateForm();
    });

    // Room creation form
    this.elements.confirmCreateBtn.addEventListener('click', () => {
      this.createRoom();
    });

    this.elements.cancelCreateBtn.addEventListener('click', () => {
      this.hideCreateForm();
    });

    this.elements.roomTitleInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        this.createRoom();
      }
    });

    // Close admin panel on ESC key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.elements.adminPanel.style.display !== 'none') {
        this.hideAdminPanel();
      }
    });
  }

  showCreateForm() {
    this.elements.roomCreation.style.display = 'block';
    this.elements.roomTitleInput.focus();
    this.elements.createRoomBtn.style.display = 'none';
  }

  hideCreateForm() {
    this.elements.roomCreation.style.display = 'none';
    this.elements.roomTitleInput.value = '';
    this.elements.roomDescInput.value = '';
    this.elements.maxParticipantsInput.value = '50'; // Reset to default
    this.elements.roomPasswordInput.value = '';
    this.elements.createRoomBtn.style.display = 'inline-block';
  }

  async createRoom() {
    // Check authentication first
    if (!window.authManager || !window.authManager.requireAuth()) {
      this.showNotification('Please login to create rooms', 'error');
      return;
    }

    const title = this.elements.roomTitleInput.value.trim();
    const description = this.elements.roomDescInput.value.trim();
    const maxParticipants = parseInt(this.elements.maxParticipantsInput.value) || null;
    const password = this.elements.roomPasswordInput.value.trim() || null;
    
    if (!title) {
      this.showNotification('Please enter a room title', 'error');
      this.elements.roomTitleInput.focus();
      return;
    }

    // Disable button to prevent double-submission
    this.elements.confirmCreateBtn.disabled = true;
    this.elements.confirmCreateBtn.innerHTML = '<span class="spinner"></span> Creating...';

    try {
      // Use authenticated fetch
      const response = await window.authManager.authenticatedFetch('/api/rooms', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
          title,
          description: description || null,
          max_participants: maxParticipants,
          password: password
        })
      });

      if (response.ok) {
        const room = await response.json();
        console.log('Room created:', room);
        this.hideCreateForm();
        this.loadRooms(); // Refresh the list
        
        // Show success message with room ID
        this.showNotification(
          `🎉 Room "${title}" created successfully!\nRoom ID: ${room.room_id}`, 
          'success'
        );

        // Auto-navigate to presenter interface
        setTimeout(() => {
          window.open(`/room/${room.room_id}`, '_blank');
        }, 1500);
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create room');
      }
    } catch (error) {
      console.error('Error creating room:', error);
      this.showNotification(`Failed to create room: ${error.message}`, 'error');
    } finally {
      // Re-enable button
      this.elements.confirmCreateBtn.disabled = false;
      this.elements.confirmCreateBtn.innerHTML = '<span class="icon">🚀</span><span>Create & Start Room</span>';
    }
  }

  async loadRooms() {
    try {
      const response = await fetch('/api/rooms');
      
      if (!response.ok) {
        throw new Error('Failed to load rooms');
      }

      this.rooms = await response.json();
      this.renderRooms();

    } catch (error) {
      console.error('Error loading rooms:', error);
      this.elements.roomList.innerHTML = `
        <div class="loading">Error loading rooms: ${error.message}</div>
      `;
    }
  }

  renderRooms() {
    if (this.rooms.length === 0) {
      this.elements.roomList.innerHTML = `
        <div class="no-rooms">
          No seminar rooms created yet. Click "Create New Room" to get started!
        </div>
      `;
      return;
    }

    const roomsHTML = this.rooms.map(room => this.renderRoom(room)).join('');
    this.elements.roomList.innerHTML = roomsHTML;

    // Add event listeners for room actions
    this.addRoomEventListeners();
  }

  renderRoom(room) {
    const createdDate = new Date(room.created_at).toLocaleDateString();
    const createdTime = new Date(room.created_at).toLocaleTimeString();
    
    let statusHTML = '';
    if (room.is_live) {
      statusHTML = `
        <div class="room-status status-live">
          <span style="width: 8px; height: 8px; background: currentColor; border-radius: 50%; animation: pulse 2s infinite;"></span>
          LIVE
        </div>
      `;
    } else {
      statusHTML = `<div class="room-status status-offline">Offline</div>`;
    }

    let durationHTML = '';
    if (room.duration_ms) {
      const minutes = Math.floor(room.duration_ms / 60000);
      const seconds = Math.floor((room.duration_ms % 60000) / 1000);
      durationHTML = `Duration: ${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    return `
      <div class="room-card" data-room-id="${room.room_id}">
        <div class="room-header">
          <h3 class="room-title">${this.escapeHtml(room.title)}</h3>
          ${statusHTML}
        </div>
        
        <div class="room-info">
          <span>Room ID: ${room.room_id}</span>
          <span>Created: ${createdDate} ${createdTime}</span>
          <span>Participants: ${room.participant_count}</span>
          ${durationHTML ? `<span>${durationHTML}</span>` : ''}
        </div>

        <div class="room-actions">
          <a href="${room.presenter_url}" class="room-btn btn-primary" target="_blank">
            🎤 Present
          </a>
          <a href="${room.participant_url}" class="room-btn btn-secondary" target="_blank">
            👥 Join as Participant  
          </a>
          <button class="room-btn btn-secondary" onclick="roomManager.viewAnalytics('${room.room_id}')">
            📊 Analytics
          </button>
          <button class="room-btn btn-secondary" onclick="roomManager.copyUrl('${room.participant_url}', this)">
            📋 Copy URL
          </button>
        </div>
      </div>
    `;
  }

  addRoomEventListeners() {
    // Room cards are clickable (could open room details)
    const roomCards = document.querySelectorAll('.room-card');
    roomCards.forEach(card => {
      card.addEventListener('click', (e) => {
        // Only trigger if not clicking on buttons/links
        if (e.target.tagName !== 'BUTTON' && e.target.tagName !== 'A') {
          const roomId = card.dataset.roomId;
          this.showRoomDetails(roomId);
        }
      });
    });
  }

  copyUrl(url, button) {
    navigator.clipboard.writeText(url).then(() => {
      const originalText = button.textContent;
      button.textContent = '✅ Copied!';
      button.style.background = 'rgba(34, 197, 94, 0.2)';
      button.style.color = '#22c55e';
      
      setTimeout(() => {
        button.textContent = originalText;
        button.style.background = '';
        button.style.color = '';
      }, 2000);
    }).catch((error) => {
      console.error('Failed to copy URL:', error);
      alert('Failed to copy URL to clipboard');
    });
  }

  showRoomDetails(roomId) {
    const room = this.rooms.find(r => r.room_id === roomId);
    if (!room) return;

    // Could implement a modal or detailed view here
    console.log('Show details for room:', room);
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Legacy function to show original transcription interface
  showLegacyMode() {
    this.elements.transcriptionSection.style.display = 'block';
    document.getElementById('roomManagement').style.display = 'none';
  }

  hideLegacyMode() {
    this.elements.transcriptionSection.style.display = 'none';
    document.getElementById('roomManagement').style.display = 'block';
  }

  // Analytics Panel Methods
  showAnalyticsPanel() {
    this.elements.adminPanel.style.display = 'flex';
    this.loadAnalyticsData();
  }

  hideAdminPanel() {
    this.elements.adminPanel.style.display = 'none';
  }

  switchAdminTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // Update tab content  
    document.querySelectorAll('.tab-content').forEach(content => {
      const expectedId = `admin${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`;
      content.classList.toggle('active', content.id === expectedId);
    });

    this.currentTab = tabName;
    this.loadAnalyticsData();
  }

  async loadAnalyticsData() {
    switch (this.currentTab) {
      case 'analytics':
        await this.loadPlatformStats();
        await this.loadRoomAnalytics();
        break;
      case 'files':
        await this.loadMediaFiles();
        break;
      case 'transcripts':
        await this.loadExportHistory();
        break;
      case 'settings':
        // Settings tab is static, no loading needed
        break;
    }
  }

  async loadPlatformStats() {
    try {
      const response = await fetch('/api/rooms');
      if (response.ok) {
        const data = await response.json();
        const rooms = data.rooms || [];
        
        document.getElementById('totalRooms').textContent = rooms.length;
        document.getElementById('activeRooms').textContent = rooms.filter(r => r.is_live).length;
        document.getElementById('totalParticipants').textContent = rooms.reduce((sum, r) => sum + (r.participant_count || 0), 0);
        document.getElementById('totalSessions').textContent = rooms.filter(r => !r.is_live && r.ended_at).length;
      }
    } catch (error) {
      console.error('Error loading platform stats:', error);
    }
  }

  async loadRoomAnalytics() {
    const container = document.getElementById('roomAnalyticsList');
    container.innerHTML = '<div class="loading">Loading room analytics...</div>';
    
    try {
      const response = await fetch('/api/rooms');
      if (response.ok) {
        const data = await response.json();
        const rooms = data.rooms || [];
        
        if (rooms.length === 0) {
          container.innerHTML = '<div class="no-data">No rooms found</div>';
          return;
        }
        
        const roomsHtml = rooms.map(room => `
          <div class="analytics-room-card">
            <div class="room-header">
              <h5>${this.escapeHtml(room.title)}</h5>
              <span class="room-status ${room.is_live ? 'status-live' : 'status-ended'}">
                ${room.is_live ? 'LIVE' : 'ENDED'}
              </span>
            </div>
            <div class="room-stats">
              <div class="stat-item">
                <span class="stat-label">Participants:</span>
                <span class="stat-value">${room.participant_count || 0}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">Duration:</span>
                <span class="stat-value">${this.formatDuration(room.duration_ms || 0)}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">Created:</span>
                <span class="stat-value">${new Date(room.created_at).toLocaleDateString()}</span>
              </div>
            </div>
            <div class="room-actions">
              <button class="view-analytics-btn" onclick="roomManager.viewRoomAnalytics('${room.room_id}')">
                View Details
              </button>
              <a href="/room/${room.room_id}" target="_blank" class="join-link">Visit Room</a>
            </div>
          </div>
        `).join('');
        
        container.innerHTML = roomsHtml;
      }
    } catch (error) {
      console.error('Error loading room analytics:', error);
      container.innerHTML = '<div class="error">Failed to load room analytics</div>';
    }
  }

  async loadAdminRooms() {
    try {
      const response = await fetch('/api/rooms');
      const rooms = await response.json();
      
      const adminRoomsHTML = rooms.map(room => `
        <div class="admin-room-item">
          <div class="admin-room-info">
            <h4>${room.title}</h4>
            <div class="admin-room-meta">
              <span>ID: ${room.room_id}</span>
              <span>Created: ${new Date(room.created_at).toLocaleString()}</span>
              <span>Status: ${room.is_live ? 'Live' : 'Offline'}</span>
            </div>
          </div>
          <div class="admin-room-actions">
            <button onclick="roomManager.viewAnalytics('${room.room_id}')" class="btn-primary">
              📊 Analytics
            </button>
            <button onclick="roomManager.downloadRoomData('${room.room_id}')" class="btn-secondary">
              📁 Download Data
            </button>
            <button onclick="roomManager.deleteRoom('${room.room_id}')" class="btn-danger">
              🗑️ Delete
            </button>
          </div>
        </div>
      `).join('');

      document.querySelector('.admin-room-list').innerHTML = adminRoomsHTML || '<p>No rooms found.</p>';
    } catch (error) {
      console.error('Error loading admin rooms:', error);
    }
  }

  async loadAdminFiles() {
    // TODO: Implement file browser for audio files
    document.querySelector('.file-browser').innerHTML = `
      <div class="admin-section">
        <h4>📂 Audio Files</h4>
        <p>Audio files are automatically saved during live sessions.</p>
        <div class="file-stats">
          <div class="stat-card">
            <span class="stat-number">-</span>
            <span class="stat-label">Total Files</span>
          </div>
          <div class="stat-card">
            <span class="stat-number">-</span>
            <span class="stat-label">Total Size</span>
          </div>
        </div>
        <button onclick="roomManager.downloadAllAudio()" class="btn-primary">
          💾 Download All Audio Files
        </button>
      </div>
    `;
  }

  async loadAdminTranscripts() {
    // TODO: Implement transcript browser
    document.querySelector('.transcript-list').innerHTML = `
      <div class="admin-section">
        <h4>📝 Transcripts</h4>
        <p>Transcripts are automatically generated during live sessions.</p>
        <div class="transcript-stats">
          <div class="stat-card">
            <span class="stat-number">-</span>
            <span class="stat-label">Total Transcripts</span>
          </div>
          <div class="stat-card">
            <span class="stat-number">-</span>
            <span class="stat-label">Languages</span>
          </div>
        </div>
        <button onclick="roomManager.downloadAllTranscripts()" class="btn-primary">
          📄 Download All Transcripts
        </button>
      </div>
    `;
  }

  // Room Management Actions
  viewAnalytics(roomId) {
    window.open(`/static/analytics.html?room=${roomId}`, '_blank');
  }

  async downloadRoomData(roomId) {
    try {
      const response = await fetch(`/api/rooms/${roomId}/export`);
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `room-${roomId}-data.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        this.showNotification('Room data downloaded successfully!', 'success');
      } else {
        throw new Error('Failed to download room data');
      }
    } catch (error) {
      console.error('Error downloading room data:', error);
      this.showNotification('Failed to download room data', 'error');
    }
  }

  async deleteRoom(roomId) {
    if (!confirm('Are you sure you want to delete this room? This action cannot be undone.')) {
      return;
    }

    try {
      const response = await fetch(`/api/rooms/${roomId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        this.showNotification('Room deleted successfully', 'success');
        this.loadRooms();
        this.loadAdminData();
      } else {
        throw new Error('Failed to delete room');
      }
    } catch (error) {
      console.error('Error deleting room:', error);
      this.showNotification('Failed to delete room', 'error');
    }
  }

  // Notification System
  showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
      <div class="notification-content">
        <span class="notification-icon">${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</span>
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

    // Animate in
    setTimeout(() => {
      notification.classList.add('show');
    }, 10);
  }

  async loadMediaFiles() {
    const container = document.getElementById('mediaFileList');
    container.innerHTML = '<div class="loading">Loading media files...</div>';
    
    // Placeholder for media files - would need backend endpoint
    container.innerHTML = '<div class="no-data">Media file management coming soon</div>';
  }

  async loadExportHistory() {
    const container = document.getElementById('exportHistory');
    container.innerHTML = '<div class="loading">Loading export history...</div>';
    
    // Placeholder for export history - would need backend endpoint
    container.innerHTML = '<div class="no-data">Export history coming soon</div>';
  }

  async viewRoomAnalytics(roomId) {
    try {
      const response = await fetch(`/api/rooms/${roomId}/analytics`);
      if (response.ok) {
        const analytics = await response.json();
        
        // Open analytics in new window
        const analyticsWindow = window.open('', '_blank', 'width=800,height=600');
        analyticsWindow.document.write(`
          <html>
            <head><title>Room Analytics - ${analytics.room_title}</title></head>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
              <h1>Analytics for ${analytics.room_title}</h1>
              <pre style="background: #f5f5f5; padding: 20px; border-radius: 8px;">${JSON.stringify(analytics, null, 2)}</pre>
            </body>
          </html>
        `);
      }
    } catch (error) {
      console.error('Error loading room analytics:', error);
      this.showNotification('Failed to load room analytics', 'error');
    }
  }

  formatDuration(ms) {
    if (!ms) return '0m';
    
    const minutes = Math.floor(ms / 60000);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else {
      return `${minutes}m`;
    }
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize room manager when DOM is loaded
let roomManager;
document.addEventListener('DOMContentLoaded', () => {
  roomManager = new RoomManager();
  window.roomManager = roomManager;
});

// CSS animation for live indicator
const style = document.createElement('style');
style.textContent = `
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
`;
document.head.appendChild(style);