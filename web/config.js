// API Configuration
// VPS API URL - configured for production
const API_CONFIG = {
    // VPS IP address (primary VPS for frontend connection)
    // For local testing, change to: 'http://localhost:5000'
    baseURL: 'http://localhost:5000',  // Changed to localhost for local testing
    
    // List of all VPS IPs for row-based distribution
    // Frontend will calculate row ranges and send to each VPS
    // For local testing with single server, use: ['http://localhost:5000']
    vpsIPs: [
        'http://localhost:5000'  // Changed to localhost for local testing
    ],
    
    // WebSocket URL (automatically derived from baseURL)
    get wsURL() {
        const url = new URL(this.baseURL);
        // Convert http to ws, https to wss
        const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${url.host}`;
    }
};
