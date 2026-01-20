// WebSocket Client for Real-time Progress Updates
class WebSocketClient {
    constructor(baseURL) {
        this.baseURL = baseURL;
        this.socket = null;
        this.connected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.currentJobId = null;
        this.onProgressCallback = null;
        this.onCompleteCallback = null;
        this.onErrorCallback = null;
        this.onConnectCallback = null;
        this.onDisconnectCallback = null;
    }

    connect() {
        try {
            // Convert HTTP URL to WebSocket URL
            const wsURL = this.baseURL.replace(/^http/, 'ws');
            const socketioURL = `${wsURL}/socket.io/?EIO=4&transport=websocket`;
            
            // Use Socket.IO client library
            this.socket = io(this.baseURL, {
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionDelay: 1000,
                reconnectionDelayMax: 5000,
                reconnectionAttempts: this.maxReconnectAttempts
            });

            this.socket.on('connect', () => {
                console.log('WebSocket connected');
                this.connected = true;
                this.reconnectAttempts = 0;
                if (this.onConnectCallback) {
                    this.onConnectCallback();
                }
                
                // Re-subscribe to current job if exists
                if (this.currentJobId) {
                    this.subscribeToJob(this.currentJobId);
                }
            });

            this.socket.on('disconnect', () => {
                console.log('WebSocket disconnected');
                this.connected = false;
                if (this.onDisconnectCallback) {
                    this.onDisconnectCallback();
                }
            });

            this.socket.on('connected', (data) => {
                console.log('Server connection confirmed:', data);
            });

            this.socket.on('subscribed', (data) => {
                console.log('Subscribed to job:', data);
            });
            
            this.socket.on('error', (data) => {
                console.error('WebSocket subscription error:', data);
            });

            this.socket.on('progress_update', (data) => {
                console.log('Progress update:', data);
                if (this.onProgressCallback) {
                    this.onProgressCallback(data);
                }
            });

            this.socket.on('job_complete', (data) => {
                console.log('Job complete:', data);
                if (this.onCompleteCallback) {
                    this.onCompleteCallback(data);
                }
            });

            this.socket.on('job_error', (data) => {
                console.error('Job error:', data);
                if (this.onErrorCallback) {
                    this.onErrorCallback(data);
                }
            });

            this.socket.on('error', (error) => {
                console.error('WebSocket error:', error);
            });

        } catch (error) {
            console.error('Error connecting WebSocket:', error);
            this.connected = false;
            if (this.onDisconnectCallback) {
                this.onDisconnectCallback();
            }
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        this.connected = false;
        this.currentJobId = null;
    }

    subscribeToJob(jobId) {
        if (!this.connected || !this.socket) {
            console.warn('Cannot subscribe: WebSocket not connected');
            return;
        }

        this.currentJobId = jobId;
        this.socket.emit('subscribe_job', { job_id: jobId });
    }

    unsubscribeFromJob(jobId) {
        if (this.socket && this.connected) {
            this.socket.emit('unsubscribe_job', { job_id: jobId });
        }
        if (this.currentJobId === jobId) {
            this.currentJobId = null;
        }
    }

    onProgress(callback) {
        this.onProgressCallback = callback;
    }

    onComplete(callback) {
        this.onCompleteCallback = callback;
    }

    onError(callback) {
        this.onErrorCallback = callback;
    }

    onConnect(callback) {
        this.onConnectCallback = callback;
    }

    onDisconnect(callback) {
        this.onDisconnectCallback = callback;
    }

    isConnected() {
        return this.connected && this.socket && this.socket.connected;
    }
}
