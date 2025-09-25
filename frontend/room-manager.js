// Room Management JavaScript for Live Seminar Platform

class RoomManager {
  constructor() {
    this.elements = {
      createRoomBtn: document.getElementById('createRoomBtn'),
      roomCreation: document.getElementById('roomCreation'),
      roomTitleInput: document.getElementById('roomTitleInput'),
      confirmCreateBtn: document.getElementById('confirmCreateBtn'),
      cancelCreateBtn: document.getElementById('cancelCreateBtn'),
      roomList: document.getElementById('roomList'),
      transcriptionSection: document.getElementById('transcriptionSection')
    };
    
    this.rooms = [];
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.loadRooms();
    
    // Refresh room list every 10 seconds
    setInterval(() => this.loadRooms(), 10000);
  }

  setupEventListeners() {
    this.elements.createRoomBtn.addEventListener('click', () => {
      this.showCreateForm();
    });

    this.elements.confirmCreateBtn.addEventListener('click', () => {
      this.createRoom();
    });

    this.elements.cancelCreateBtn.addEventListener('click', () => {
      this.hideCreateForm();
    });

    this.elements.roomTitleInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        this.createRoom();
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
    this.elements.createRoomBtn.style.display = 'inline-block';
  }

  async createRoom() {
    const title = this.elements.roomTitleInput.value.trim();
    
    if (!title) {
      alert('Please enter a seminar title');
      return;
    }

    try {
      this.elements.confirmCreateBtn.disabled = true;
      this.elements.confirmCreateBtn.textContent = 'Creating...';

      const response = await fetch('/api/rooms', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ title })
      });

      if (!response.ok) {
        throw new Error('Failed to create room');
      }

      const room = await response.json();
      
      // Show success and redirect to presenter interface
      alert(`Room created successfully!\n\nRoom ID: ${room.room_id}\nParticipant URL: ${room.participant_url}`);
      
      // Optionally auto-open presenter interface
      window.open(room.presenter_url, '_blank');
      
      this.hideCreateForm();
      this.loadRooms();

    } catch (error) {
      console.error('Error creating room:', error);
      alert('Failed to create room: ' + error.message);
    } finally {
      this.elements.confirmCreateBtn.disabled = false;
      this.elements.confirmCreateBtn.textContent = 'Create Room';
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
          <a href="${room.presenter_url}" class="room-btn btn-present" target="_blank">
            🎤 Present
          </a>
          <a href="${room.participant_url}" class="room-btn btn-join" target="_blank">
            👥 Join as Participant  
          </a>
          <button class="room-btn btn-copy" onclick="roomManager.copyUrl('${room.participant_url}', this)">
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
}

// Initialize room manager when DOM is loaded
let roomManager;
document.addEventListener('DOMContentLoaded', () => {
  roomManager = new RoomManager();
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