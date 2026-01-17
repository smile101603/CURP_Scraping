// Main Application Logic
class CURPApp {
    constructor() {
        this.apiBaseURL = API_CONFIG.baseURL;
        this.wsClient = new WebSocketClient(this.apiBaseURL);
        this.currentJobId = null;
        this.uploadedFile = null;
        this.searchStartTime = null; // Track search start time for time estimation
        
        this.initializeElements();
        this.initializeEventListeners();
        this.connectWebSocket();
    }

    initializeElements() {
        // API Config
        this.apiURLInput = document.getElementById('api-url');
        this.apiURLInput.value = this.apiBaseURL;
        
        // Connection Status
        this.connectionStatus = document.getElementById('connection-status');
        
        // File Upload
        this.uploadArea = document.getElementById('upload-area');
        this.fileInput = document.getElementById('file-input');
        this.fileInfo = document.getElementById('file-info');
        this.fileName = document.getElementById('file-name');
        
        // Year Range
        this.yearStartInput = document.getElementById('year-start');
        this.yearEndInput = document.getElementById('year-end');
        
        // Buttons
        this.startBtn = document.getElementById('start-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.downloadBtn = document.getElementById('download-btn');
        
        // Progress
        this.progressSection = document.getElementById('progress-section');
        this.progressBar = document.getElementById('progress-bar');
        this.progressPercentage = document.getElementById('progress-percentage');
        this.currentPerson = document.getElementById('current-person');
        this.currentCombination = document.getElementById('current-combination');
        this.matchesFound = document.getElementById('matches-found');
        this.estimatedTime = document.getElementById('estimated-time');
        
        // Messages
        this.messageDiv = document.getElementById('message');
    }

    initializeEventListeners() {
        // API URL change
        this.apiURLInput.addEventListener('change', () => {
            this.apiBaseURL = this.apiURLInput.value;
            API_CONFIG.baseURL = this.apiBaseURL;
            this.disconnectWebSocket();
            this.connectWebSocket();
        });

        // File Upload
        this.uploadArea.addEventListener('click', () => this.fileInput.click());
        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.uploadArea.classList.add('dragover');
        });
        this.uploadArea.addEventListener('dragleave', () => {
            this.uploadArea.classList.remove('dragover');
        });
        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFileSelect(files[0]);
            }
        });
        this.fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFileSelect(e.target.files[0]);
            }
        });

        // Start Button
        this.startBtn.addEventListener('click', () => this.startSearch());
        
        // Stop Button
        this.stopBtn.addEventListener('click', () => this.stopSearch());
        
        // Download Button
        this.downloadBtn.addEventListener('click', () => this.downloadResults());
    }

    connectWebSocket() {
        this.wsClient.onConnect(() => {
            this.updateConnectionStatus('connected', 'Connected');
        });

        this.wsClient.onDisconnect(() => {
            this.updateConnectionStatus('disconnected', 'Disconnected');
        });

        this.wsClient.onProgress((data) => {
            // Handle nested progress structure
            if (data.progress) {
                this.updateProgress(data.progress);
            } else {
                // Fallback: data might be the progress object directly
                this.updateProgress(data);
            }
        });

        this.wsClient.onComplete((data) => {
            this.showMessage('Search completed successfully!', 'success');
            this.startBtn.disabled = false;
            this.stopBtn.disabled = true;
            this.downloadBtn.disabled = false;
        });

        this.wsClient.onError((data) => {
            this.showMessage(`Error: ${data.error_message}`, 'error');
            this.startBtn.disabled = false;
            this.stopBtn.disabled = true;
        });

        this.wsClient.connect();
        this.updateConnectionStatus('connecting', 'Connecting...');
    }

    disconnectWebSocket() {
        this.wsClient.disconnect();
    }

    updateConnectionStatus(status, text) {
        this.connectionStatus.className = `connection-status ${status}`;
        this.connectionStatus.textContent = text;
    }

    handleFileSelect(file) {
        if (!file.name.match(/\.(xlsx|xls)$/i)) {
            this.showMessage('Please select an Excel file (.xlsx or .xls)', 'error');
            return;
        }

        this.uploadedFile = file;
        this.fileName.textContent = file.name;
        this.fileInfo.classList.add('show');
    }

    async uploadFile() {
        if (!this.uploadedFile) {
            this.showMessage('Please select a file first', 'error');
            return null;
        }

        const formData = new FormData();
        formData.append('file', this.uploadedFile);

        // Upload to all VPSs
        const vpsIPs = API_CONFIG.vpsIPs || [this.apiBaseURL];
        const uploadPromises = vpsIPs.map(async (vpsIP) => {
            try {
                const response = await fetch(`${vpsIP}/api/upload`, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || `Upload failed on ${vpsIP}`);
                }

                return { vpsIP, filename: data.filename, success: true };
            } catch (error) {
                console.error(`Upload error on ${vpsIP}:`, error);
                return { vpsIP, error: error.message, success: false };
            }
        });

        try {
            const results = await Promise.all(uploadPromises);
            const failed = results.filter(r => !r.success);
            
            if (failed.length > 0) {
                const failedVPSs = failed.map(r => r.vpsIP).join(', ');
                throw new Error(`Upload failed on: ${failedVPSs}`);
            }

            // All uploads succeeded - use filename from first VPS (should be same for all)
            const filename = results[0].filename;
            this.showMessage(`File uploaded successfully to ${results.length} VPS(s)`, 'success');
            return filename;
        } catch (error) {
            this.showMessage(`Upload error: ${error.message}`, 'error');
            return null;
        }
    }

    async getFileRowCount(filename) {
        try {
            const response = await fetch(`${this.apiBaseURL}/api/file-info?filename=${encodeURIComponent(filename)}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to get file info');
            }

            return data.row_count;
        } catch (error) {
            console.error(`Error getting file row count: ${error.message}`);
            return null;
        }
    }

    async startSearchOnVPS(vpsIP, filename, yearStart, yearEnd, startRow, endRow, lastPersonYearStart, lastPersonYearEnd, lastPersonMonthStart, lastPersonMonthEnd) {
        try {
            const requestBody = {
                filename: filename,
                year_start: yearStart,
                year_end: yearEnd,
                start_row: startRow,
                end_row: endRow
            };
            
            // Add last person year range if provided (for odd number split)
            if (lastPersonYearStart !== undefined && lastPersonYearEnd !== undefined) {
                requestBody.last_person_year_start = lastPersonYearStart;
                requestBody.last_person_year_end = lastPersonYearEnd;
            }
            
            // Add last person month range if provided (for 1-year range split)
            if (lastPersonMonthStart !== undefined && lastPersonMonthEnd !== undefined) {
                requestBody.last_person_month_start = lastPersonMonthStart;
                requestBody.last_person_month_end = lastPersonMonthEnd;
            }
            
            const response = await fetch(`${vpsIP}/api/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            const data = await response.json();

            if (!response.ok) {
                const errorMsg = data.error || `Failed to start search on ${vpsIP}`;
                console.error(`Error from ${vpsIP}:`, errorMsg);
                console.error(`Request body was:`, JSON.stringify(requestBody, null, 2));
                throw new Error(errorMsg);
            }

            let yearRangeInfo = '';
            if (lastPersonYearStart !== undefined) {
                yearRangeInfo = ` (last person: ${lastPersonYearStart}-${lastPersonYearEnd}`;
                if (lastPersonMonthStart !== undefined) {
                    yearRangeInfo += `, months ${lastPersonMonthStart}-${lastPersonMonthEnd}`;
                }
                yearRangeInfo += ')';
            }
            console.log(`Started job ${data.job_id} on ${vpsIP} for rows ${startRow}-${endRow}${yearRangeInfo}`);
            return data;
        } catch (error) {
            console.error(`Error starting search on ${vpsIP}: ${error.message}`);
            throw error;
        }
    }

    async startSearch() {
        if (!this.uploadedFile) {
            this.showMessage('Please upload a file first', 'error');
            return;
        }

        const yearStart = parseInt(this.yearStartInput.value);
        const yearEnd = parseInt(this.yearEndInput.value);

        if (!yearStart || !yearEnd) {
            this.showMessage('Please enter valid year range', 'error');
            return;
        }

        if (yearStart > yearEnd) {
            this.showMessage('Start year must be less than or equal to end year', 'error');
            return;
        }

        // Upload file
        const filename = await this.uploadFile();
        if (!filename) {
            return;
        }

        // Get file row count for VPS distribution
        const totalRows = await this.getFileRowCount(filename);
        if (!totalRows || totalRows === 0) {
            this.showMessage('Could not determine file row count', 'error');
            return;
        }

        // Calculate row ranges for each VPS
        const vpsIPs = API_CONFIG.vpsIPs || [this.apiBaseURL];
        const isOdd = totalRows % 2 !== 0;
        const rowRanges = [];
        
        // If odd number of persons and exactly 2 VPSs, split last person's year range
        if (isOdd && vpsIPs.length === 2) {
            const personsPerVPS = Math.floor(totalRows / 2);
            const lastPersonIndex = totalRows;
            const yearRange = yearEnd - yearStart + 1;
            
            // Handle edge case: if year range is 1, split by months (6 months each)
            if (yearRange === 1) {
                // VPS 1: First half persons + first 6 months of last person's year
                rowRanges.push({
                    startRow: 1,
                    endRow: lastPersonIndex,
                    vpsIP: vpsIPs[0],
                    rowCount: lastPersonIndex,
                    lastPersonYearStart: yearStart,
                    lastPersonYearEnd: yearEnd,
                    lastPersonMonthStart: 1,
                    lastPersonMonthEnd: 6
                });
                // VPS 2: Second half persons + last 6 months of last person's year
                rowRanges.push({
                    startRow: lastPersonIndex,
                    endRow: lastPersonIndex,
                    vpsIP: vpsIPs[1],
                    rowCount: 1,
                    lastPersonYearStart: yearStart,
                    lastPersonYearEnd: yearEnd,
                    lastPersonMonthStart: 7,
                    lastPersonMonthEnd: 12
                });
                this.showMessage(`Distributing ${totalRows} rows (odd, 1-year range): Split by months (1-6 / 7-12)`, 'info');
            } else {
                const midYear = Math.floor(yearRange / 2) + yearStart;
                
                // VPS 1: First half persons + first half of last person's year range
                rowRanges.push({
                    startRow: 1,
                    endRow: lastPersonIndex, // Include last person
                    vpsIP: vpsIPs[0],
                    rowCount: lastPersonIndex,
                    lastPersonYearStart: yearStart,
                    lastPersonYearEnd: midYear - 1
                });
                
                // VPS 2: Second half persons + second half of last person's year range
                rowRanges.push({
                    startRow: lastPersonIndex,
                    endRow: lastPersonIndex, // Only last person
                    vpsIP: vpsIPs[1],
                    rowCount: 1,
                    lastPersonYearStart: midYear,
                    lastPersonYearEnd: yearEnd
                });
                
                this.showMessage(`Distributing ${totalRows} rows (odd): ${personsPerVPS} persons each + last person split (${yearStart}-${midYear-1} / ${midYear}-${yearEnd})`, 'info');
            }
        } else {
            // Normal distribution (even number or more than 2 VPSs)
            const rowsPerVPS = Math.ceil(totalRows / vpsIPs.length);
            
            for (let i = 0; i < vpsIPs.length; i++) {
                const startRow = i * rowsPerVPS + 1; // 1-based indexing
                const endRow = Math.min((i + 1) * rowsPerVPS, totalRows);
                rowRanges.push({ 
                    startRow, 
                    endRow, 
                    vpsIP: vpsIPs[i],
                    rowCount: endRow - startRow + 1
                });
            }
            
            this.showMessage(`Distributing ${totalRows} rows across ${vpsIPs.length} VPS(s)...`, 'info');
        }

        // Send start request to each VPS with its row range
        try {
            const promises = rowRanges.map(range => 
                this.startSearchOnVPS(
                    range.vpsIP, 
                    filename, 
                    yearStart, 
                    yearEnd, 
                    range.startRow, 
                    range.endRow,
                    range.lastPersonYearStart,
                    range.lastPersonYearEnd,
                    range.lastPersonMonthStart,
                    range.lastPersonMonthEnd
                )
            );
            
            const results = await Promise.allSettled(promises);
            
            // Check results
            const successful = results.filter(r => r.status === 'fulfilled').length;
            const failed = results.filter(r => r.status === 'rejected').length;
            
            if (successful > 0) {
                // Use first successful job ID for WebSocket subscription
                const firstSuccess = results.find(r => r.status === 'fulfilled');
                if (firstSuccess && firstSuccess.value && firstSuccess.value.job_id) {
                    this.currentJobId = firstSuccess.value.job_id;
                    this.wsClient.subscribeToJob(this.currentJobId);
                }
                
                if (failed > 0) {
                    this.showMessage(`Started ${successful} job(s), ${failed} failed`, 'warning');
                } else {
                    this.showMessage(`Successfully started ${successful} job(s) across ${vpsIPs.length} VPS(s)`, 'success');
                }
            } else {
                throw new Error('All VPS start requests failed');
            }
            
            // Reset search start time
            this.searchStartTime = Date.now();
            
            this.showMessage('Search started', 'success');
            this.progressSection.classList.add('show');
            this.startBtn.disabled = true;
            this.stopBtn.disabled = false;
            this.downloadBtn.disabled = true;
            
            // Reset progress
            this.updateProgress({
                person_id: 0,
                person_name: '',
                combination_index: 0,
                total_combinations: 0,
                matches_found: 0,
                current_combination: null,
                percentage: 0
            });

        } catch (error) {
            this.showMessage(`Error starting search: ${error.message}`, 'error');
        }
    }

    async stopSearch() {
        if (!this.currentJobId) {
            return;
        }

        try {
            const response = await fetch(`${this.apiBaseURL}/api/cancel/${this.currentJobId}`, {
                method: 'POST'
            });

            const data = await response.json();

            if (response.ok) {
                this.showMessage('Search cancelled', 'info');
                this.startBtn.disabled = false;
                this.stopBtn.disabled = true;
            }
        } catch (error) {
            this.showMessage(`Error cancelling search: ${error.message}`, 'error');
        }
    }

    updateProgress(progress) {
        if (!progress) return;

        // Calculate percentage if not provided
        let percentage = progress.percentage;
        if (percentage === undefined || percentage === null) {
            if (progress.combination_index > 0 && progress.total_combinations > 0) {
                percentage = (progress.combination_index / progress.total_combinations) * 100;
            } else {
                percentage = 0;
            }
        }

        this.progressBar.style.width = `${percentage}%`;
        this.progressPercentage.textContent = `${percentage.toFixed(1)}%`;

        this.currentPerson.textContent = progress.person_name || 'N/A';
        
        if (progress.current_combination) {
            const combo = progress.current_combination;
            this.currentCombination.textContent = 
                `${combo.day}/${combo.month}/${combo.year} - ${combo.state}`;
        } else {
            this.currentCombination.textContent = 'N/A';
        }

        this.matchesFound.textContent = progress.matches_found || 0;

        // Estimate time remaining based on actual progress rate
        if (progress.combination_index > 0 && progress.total_combinations > 0) {
            // Track start time if not already set
            if (!this.searchStartTime) {
                this.searchStartTime = Date.now();
            }
            
            const remaining = progress.total_combinations - progress.combination_index;
            
            // Calculate elapsed time
            const elapsedMs = Date.now() - this.searchStartTime;
            const elapsedSeconds = elapsedMs / 1000;
            
            // Calculate rate (combinations per second)
            const rate = progress.combination_index / elapsedSeconds;
            
            // Estimate remaining time based on current rate
            if (rate > 0) {
                const estimatedSeconds = Math.round(remaining / rate);
                const hours = Math.floor(estimatedSeconds / 3600);
                const minutes = Math.floor((estimatedSeconds % 3600) / 60);
                const seconds = estimatedSeconds % 60;
                
                if (hours > 0) {
                    this.estimatedTime.textContent = `${hours}h ${minutes}m`;
                } else if (minutes > 0) {
                    this.estimatedTime.textContent = `${minutes}m ${seconds}s`;
                } else {
                    this.estimatedTime.textContent = `${seconds}s`;
                }
            } else {
                this.estimatedTime.textContent = 'Calculating...';
            }
        } else {
            this.estimatedTime.textContent = 'Calculating...';
        }
    }

    async downloadResults() {
        if (!this.currentJobId) {
            this.showMessage('No job selected', 'error');
            return;
        }

        try {
            const response = await fetch(`${this.apiBaseURL}/api/download/${this.currentJobId}`);
            
            if (!response.ok) {
                throw new Error('Download failed');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `curp_results_${this.currentJobId}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            this.showMessage('Results downloaded', 'success');
        } catch (error) {
            this.showMessage(`Download error: ${error.message}`, 'error');
        }
    }


    showMessage(text, type) {
        this.messageDiv.textContent = text;
        this.messageDiv.className = `message ${type} show`;
        
        setTimeout(() => {
            this.messageDiv.classList.remove('show');
        }, 5000);
    }
}

// Initialize app when DOM is ready
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new CURPApp();
});
