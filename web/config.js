// API Configuration
// Update this with your VPS API URL
const API_CONFIG = {
    // Example: 'http://your-vps-ip:5000' or 'https://your-vps-domain.com'
    // For local testing: 'http://localhost:5000'
    baseURL: 'http://localhost:5000',
    
    // WebSocket URL (automatically derived from baseURL)
    get wsURL() {
        const url = new URL(this.baseURL);
        // Convert http to ws, https to wss
        const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${url.host}`;
    }
};
