/**
 * Authentication utilities for the Seminar Platform
 */

class AuthManager {
    constructor() {
        this.baseUrl = window.location.origin;
        this.currentUser = null;
        this.checkAuthOnLoad();
    }

    /**
     * Check authentication status when page loads
     */
    checkAuthOnLoad() {
        const token = this.getAccessToken();
        const currentPath = window.location.pathname;

        const protectedPaths = ['/dashboard', '/dashboard.html', '/settings'];
        const authPages = ['/login', '/login.html'];

        if (protectedPaths.includes(currentPath)) {
            if (!token) {
                this.redirectToLogin(currentPath);
                return;
            }

            this.validateToken().catch(() => {
                this.clearAuth();
                this.redirectToLogin(currentPath);
            });
            return;
        }

        if (authPages.includes(currentPath) && token) {
            this.validateToken()
                .then(() => {
                    const returnUrl = new URLSearchParams(window.location.search)
                        .get('redirect') || '/dashboard';
                    window.location.replace(returnUrl);
                })
                .catch(() => this.clearAuth());
        }
    }

    /**
     * Get stored access token
     */
    getAccessToken() {
        return localStorage.getItem('access_token');
    }

    /**
     * Get stored refresh token
     */
    getRefreshToken() {
        return localStorage.getItem('refresh_token');
    }

    /**
     * Get stored user info
     */
    getUserInfo() {
        const userInfo = localStorage.getItem('user_info');
        return userInfo ? JSON.parse(userInfo) : null;
    }

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        return !!this.getAccessToken();
    }

    /**
     * Check if user is admin
     */
    isAdmin() {
        const userInfo = this.getUserInfo();
        return userInfo && userInfo.is_admin;
    }

    /**
     * Make authenticated API request
     */
    async authenticatedFetch(url, options = {}) {
        const token = this.getAccessToken();
        
        if (!token) {
            throw new Error('No access token available');
        }

        const headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        };

        const response = await fetch(url, {
            ...options,
            headers
        });

        // If unauthorized, try to refresh token
        if (response.status === 401) {
            const refreshed = await this.refreshToken();
            if (refreshed) {
                // Retry with new token
                headers['Authorization'] = `Bearer ${this.getAccessToken()}`;
                return fetch(url, {
                    ...options,
                    headers
                });
            } else {
                // Redirect to login
                this.redirectToLogin();
                throw new Error('Authentication expired');
            }
        }

        return response;
    }

    /**
     * Refresh access token using refresh token
     */
    async refreshToken() {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) {
            return false;
        }

        try {
            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('access_token', data.access_token);
                return true;
            } else {
                this.clearAuth();
                return false;
            }
        } catch (error) {
            console.error('Token refresh failed:', error);
            this.clearAuth();
            return false;
        }
    }

    /**
     * Validate current token
     */
    async validateToken() {
        try {
            const response = await this.authenticatedFetch('/api/auth/me');
            if (response.ok) {
                const userInfo = await response.json();
                localStorage.setItem('user_info', JSON.stringify(userInfo));
                this.currentUser = userInfo;
                return true;
            } else {
                throw new Error('Token validation failed');
            }
        } catch (error) {
            console.error('Token validation error:', error);
            this.clearAuth();
            return false;
        }
    }

    /**
     * Clear authentication data
     */
    clearAuth() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_info');
        this.currentUser = null;
    }

    /**
     * Logout user
     */
    async logout() {
        this.clearAuth();
        this.redirectToLogin('/dashboard');
    }

    /**
     * Redirect to login page
     */
    redirectToLogin(returnUrl = null) {
        const fallback = '/dashboard';
        const currentUrl =
            returnUrl || `${window.location.pathname}${window.location.search}` || fallback;
        const loginUrl = `/login?redirect=${encodeURIComponent(currentUrl || fallback)}`;
        window.location.href = loginUrl;
    }

    /**
     * Require authentication (redirect if not authenticated)
     */
    requireAuth() {
        if (!this.isAuthenticated()) {
            const target = `${window.location.pathname}${window.location.search}` || '/dashboard';
            this.redirectToLogin(target);
            return false;
        }
        return true;
    }

    /**
     * Require admin access (redirect if not admin)
     */
    requireAdmin() {
        if (!this.requireAuth()) {
            return false;
        }
        
        if (!this.isAdmin()) {
            alert('Admin access required');
            this.redirectToLogin('/dashboard');
            return false;
        }
        return true;
    }

    /**
     * Initialize user info display
     */
    initUserInfo() {
        const welcomeText = document.getElementById('welcomeText');
        const logoutBtn = document.getElementById('logoutBtn');
        const userInfo = this.getUserInfo();
        
        if (welcomeText && userInfo) {
            const adminBadge = userInfo.is_admin ? ' <span style="background: #4caf50; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">Admin</span>' : '';
            welcomeText.innerHTML = `Welcome, ${userInfo.username}${adminBadge}`;
        }
        
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.logout());
        }
    }

    /**
     * Update room creation to require authentication
     */
    async createRoom(roomData) {
        if (!this.requireAuth()) {
            return null;
        }

        try {
            const response = await this.authenticatedFetch('/api/rooms', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(roomData)
            });

            if (response.ok) {
                return await response.json();
            } else {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to create room');
            }
        } catch (error) {
            console.error('Room creation error:', error);
            throw error;
        }
    }

    /**
     * Show/hide admin features based on authentication
     */
    updateUIForAuth() {
        const adminPanel = document.querySelector('.admin-panel');
        const createRoomForm = document.querySelector('.create-room-form');
        const authStatus = document.querySelector('.auth-status');
        
        if (this.isAuthenticated()) {
            const userInfo = this.getUserInfo();
            
            // Show user info
            if (authStatus) {
                authStatus.innerHTML = `
                    <span class="user-info">
                        Welcome, ${userInfo.username}
                        ${userInfo.is_admin ? '<span class="admin-badge">Admin</span>' : ''}
                    </span>
                    <button class="logout-btn" onclick="authManager.logout()">Logout</button>
                `;
                authStatus.style.display = 'block';
            }
            
            // Show admin features if admin
            if (this.isAdmin() && adminPanel) {
                adminPanel.style.display = 'block';
            }
        } else {
            // Hide admin features and show login prompt
            if (adminPanel) {
                adminPanel.style.display = 'none';
            }
            
            if (authStatus) {
                authStatus.innerHTML = `
                    <button class="login-btn" onclick="authManager.redirectToLogin()">
                        Login for Admin Access
                    </button>
                `;
                authStatus.style.display = 'block';
            }
        }
    }

    /**
     * Initialize authentication UI components
     */
    initAuthUI() {
        // Check if we're on the admin page (index.html)
        const adminPaths = ['/dashboard', '/dashboard.html'];
        if (adminPaths.includes(window.location.pathname)) {
            // Initialize user info in header
            this.initUserInfo();
        }
        
        this.updateUIForAuth();
    }
}

// Global auth manager instance
const authManager = new AuthManager();

// Initialize auth UI when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    authManager.initAuthUI();
});

// Export for use in other scripts
window.authManager = authManager;