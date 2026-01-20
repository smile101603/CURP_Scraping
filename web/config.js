// API Configuration
// VPS API URL - configured for production with 2 VPSs
const API_CONFIG = {
    // VPS IP address (primary VPS for frontend connection and WebSocket)
    // This is the VPS that the frontend connects to for real-time updates
    // Use VPS 1 (index 0) as primary connection point
    baseURL: 'http://84.247.138.193:5000',  // VPS 1 - Primary connection
    
    // List of all VPS IPs for row-based distribution
    // Frontend will calculate row ranges and send to each VPS
    // Both VPSs will process their assigned portions of work
    vpsIPs: [
        'http://84.247.138.193:5000',  // VPS 1 (index 0)
        'http://84.247.138.186:5000'   // VPS 2 (index 1)
    ],
    
    // WebSocket URL (automatically derived from baseURL)
    // Real-time progress updates come from the primary VPS (baseURL)
    get wsURL() {
        const url = new URL(this.baseURL);
        // Convert http to ws, https to wss
        const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${url.host}`;
    }
};
