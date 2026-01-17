// API Configuration
// VPS API URL - configured for production
const API_CONFIG = {
    // VPS IP address (primary VPS for frontend connection)
    baseURL: 'http://84.247.138.193:5000',
    // For local testing, change to: 'http://localhost:5000'
    
    // List of all VPS IPs for row-based distribution
    // Frontend will calculate row ranges and send to each VPS
    vpsIPs: [
        'http://84.247.138.193:5000',
        'http://84.247.138.186:5000'
    ],
    
    // WebSocket URL (automatically derived from baseURL)
    get wsURL() {
        const url = new URL(this.baseURL);
        // Convert http to ws, https to wss
        const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${url.host}`;
    }
};
