// Main Application Logic
class CURPApp {
    constructor() {
        this.apiBaseURL = API_CONFIG.baseURL;
        this.wsClient = new WebSocketClient(this.apiBaseURL);
        this.vpsClients = {}; // Track WebSocket clients for each VPS
        this.vpsJobIds = {}; // Track job IDs for each VPS
        this.vpsProgress = {}; // Track progress for each VPS
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
        
        // Date Range (Year + Month)
        this.yearStartInput = document.getElementById('year-start');
        this.yearEndInput = document.getElementById('year-end');
        this.monthStartInput = document.getElementById('month-start');
        this.monthEndInput = document.getElementById('month-end');
        this.rangePreview = document.getElementById('range-preview');
        this.rangeText = document.getElementById('range-text');
        
        // Buttons
        this.startBtn = document.getElementById('start-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.downloadBtn = document.getElementById('download-btn');
        
        // Progress
        this.progressSection = document.getElementById('progress-section');
        // Progress elements will be created dynamically for each VPS
        
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
            const progress = data.progress || data;
            // Determine which VPS this progress is from using job_id
            if (data.job_id) {
                const vpsIP = this.getVPSFromJobId(data.job_id);
                if (vpsIP) {
                    this.updateVPSProgress(vpsIP, progress);
                } else {
                    // Fallback: update primary VPS if job_id not found
                    console.warn(`Job ID ${data.job_id} not found in VPS mapping, using primary VPS`);
                    this.updateVPSProgress(this.apiBaseURL, progress);
                }
            } else {
                // No job_id - update primary VPS
                this.updateVPSProgress(this.apiBaseURL, progress);
            }
        });

        this.wsClient.onComplete((data) => {
            console.log('Primary job completed:', data);
            this.checkAllJobsComplete();
        });

        this.wsClient.onError((data) => {
            this.showMessage(`Error: ${data.error_message}`, 'error');
            // Don't disable buttons on error - other VPSs might still be running
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

    async startSearchOnVPS(vpsIP, filename, yearStart, yearEnd, startRow, endRow, lastPersonYearStart, lastPersonYearEnd, lastPersonMonthStart, lastPersonMonthEnd, monthStart, monthEnd) {
        try {
            const requestBody = {
                filename: filename,
                year_start: yearStart,
                year_end: yearEnd,
                start_row: startRow,
                end_row: endRow
            };
            
            // Parse month values if they're strings
            const monthStartNum = typeof monthStart === 'number' ? monthStart : parseInt(monthStart);
            const monthEndNum = typeof monthEnd === 'number' ? monthEnd : parseInt(monthEnd);
            
            // Add month range (required - part of date range)
            requestBody.month_start = monthStartNum;
            requestBody.month_end = monthEndNum;
            
            // Add year-specific month boundaries for proper range handling
            requestBody.start_year_month = monthStartNum;  // Start month for start year
            requestBody.end_year_month = monthEndNum;      // End month for end year
            
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
        try {
            console.log('Start button clicked');
            
            if (!this.uploadedFile) {
                this.showMessage('Please upload a file first', 'error');
                return;
            }

            // Get and validate year range (required)
            const yearStart = parseInt(this.yearStartInput.value);
            const yearEnd = parseInt(this.yearEndInput.value);
            console.log('Year range:', yearStart, yearEnd);

            if (!yearStart || !yearEnd || isNaN(yearStart) || isNaN(yearEnd)) {
                this.showMessage('Please enter valid year range', 'error');
                return;
            }

            if (yearStart < 1900 || yearEnd > 2100) {
                this.showMessage('Year range must be between 1900 and 2100', 'error');
                return;
            }

            if (yearStart > yearEnd) {
                this.showMessage('Start year must be less than or equal to end year', 'error');
                return;
            }
            
            // Get month range (required - part of date range)
            let monthStart = this.monthStartInput.value.trim();
            let monthEnd = this.monthEndInput.value.trim();
            console.log('Month range (raw):', monthStart, monthEnd);
            
            // Validate month range (required)
            if (!monthStart || !monthEnd) {
                this.showMessage('Please provide both start and end month', 'error');
                return;
            }
            
            const monthStartNum = parseInt(monthStart);
            const monthEndNum = parseInt(monthEnd);
            console.log('Month range (parsed):', monthStartNum, monthEndNum);
            
            if (isNaN(monthStartNum) || isNaN(monthEndNum)) {
                this.showMessage('Month values must be valid numbers', 'error');
                return;
            }
            
            if (monthStartNum < 1 || monthStartNum > 12 || monthEndNum < 1 || monthEndNum > 12) {
                this.showMessage('Month range must be between 1 and 12', 'error');
                return;
            }
            
            // Validate date range logic
            if (yearStart === yearEnd && monthStartNum > monthEndNum) {
                this.showMessage('When years are the same, start month must be <= end month', 'error');
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
            console.log('Starting search on VPSs, month range:', monthStartNum, monthEndNum);
            const promises = rowRanges.map(range => {
                console.log('Starting search on VPS:', range.vpsIP, 'rows:', range.startRow, '-', range.endRow);
                return this.startSearchOnVPS(
                    range.vpsIP, 
                    filename, 
                    yearStart, 
                    yearEnd, 
                    range.startRow, 
                    range.endRow,
                    range.lastPersonYearStart,
                    range.lastPersonYearEnd,
                    range.lastPersonMonthStart,
                    range.lastPersonMonthEnd,
                    monthStartNum,  // Pass parsed month values
                    monthEndNum     // Pass parsed month values
                );
            });
            
            const results = await Promise.allSettled(promises);
            
            // Check results and create progress sections for each VPS
            const successful = results.filter(r => r.status === 'fulfilled').length;
            const failed = results.filter(r => r.status === 'rejected').length;
            
            if (successful > 0) {
                // Create progress sections and WebSocket clients for each VPS
                this.setupVPSProgress(rowRanges, results);
                
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

        } catch (error) {
            this.showMessage(`Error starting search: ${error.message}`, 'error');
        }
    }

    async stopSearch() {
        // Cancel all VPS jobs
        const cancelPromises = [];
        
        for (const [vpsIP, jobId] of Object.entries(this.vpsJobIds)) {
            cancelPromises.push(
                fetch(`${vpsIP}/api/cancel/${jobId}`, {
                    method: 'POST'
                }).catch(error => {
                    console.error(`Error cancelling job on ${vpsIP}:`, error);
                    return { ok: false };
                })
            );
        }
        
        // Also cancel primary job if exists
        if (this.currentJobId) {
            cancelPromises.push(
                fetch(`${this.apiBaseURL}/api/cancel/${this.currentJobId}`, {
                    method: 'POST'
                }).catch(error => {
                    console.error(`Error cancelling primary job:`, error);
                    return { ok: false };
                })
            );
        }

        try {
            const results = await Promise.allSettled(cancelPromises);
            const successful = results.filter(r => r.status === 'fulfilled' && r.value.ok).length;
            
            if (successful > 0) {
                this.showMessage(`Cancelled ${successful} job(s)`, 'info');
                this.startBtn.disabled = false;
                this.stopBtn.disabled = true;
                
                // Disconnect all VPS WebSocket clients
                for (const [vpsIP, wsClient] of Object.entries(this.vpsClients)) {
                    wsClient.disconnect();
                }
                this.vpsClients = {};
                this.vpsJobIds = {};
            }
        } catch (error) {
            this.showMessage(`Error cancelling search: ${error.message}`, 'error');
        }
    }

    setupVPSProgress(rowRanges, results) {
        // Clear existing progress sections
        this.progressSection.innerHTML = '';
        
        // Create progress section for each VPS
        rowRanges.forEach((range, index) => {
            const result = results[index];
            if (result.status === 'fulfilled' && result.value && result.value.job_id) {
                const vpsIP = range.vpsIP;
                const jobId = result.value.job_id;
                
                // Store job ID for this VPS
                this.vpsJobIds[vpsIP] = jobId;
                
                // Create progress section HTML for this VPS
                const vpsIndex = index + 1;
                const vpsName = this.getVPSName(vpsIP);
                const progressHTML = `
                    <div class="vps-progress-container" data-vps="${vpsIP}">
                        <div class="progress-header">
                            <h3 class="progress-title">Search Progress - ${vpsName}</h3>
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar vps-progress-bar" id="progress-bar-${vpsIndex}">
                                <span class="progress-percentage" id="progress-percentage-${vpsIndex}">0%</span>
                            </div>
                        </div>
                        <div class="progress-details">
                            <div class="progress-item">
                                <div class="progress-item-label">Current Person</div>
                                <div class="progress-item-value" id="current-person-${vpsIndex}">N/A</div>
                            </div>
                            <div class="progress-item">
                                <div class="progress-item-label">Current Combination</div>
                                <div class="progress-item-value" id="current-combination-${vpsIndex}">N/A</div>
                            </div>
                            <div class="progress-item">
                                <div class="progress-item-label">Matches Found</div>
                                <div class="progress-item-value" id="matches-found-${vpsIndex}">0</div>
                            </div>
                            <div class="progress-item">
                                <div class="progress-item-label">Estimated Time Remaining</div>
                                <div class="progress-item-value" id="estimated-time-${vpsIndex}">Calculating...</div>
                            </div>
                        </div>
                    </div>
                `;
                
                this.progressSection.insertAdjacentHTML('beforeend', progressHTML);
                
                // Initialize progress tracking for this VPS
                this.vpsProgress[vpsIP] = {
                    startTime: Date.now(),
                    progress: {
                        person_id: 0,
                        person_name: '',
                        combination_index: 0,
                        total_combinations: 0,
                        matches_found: 0,
                        current_combination: null,
                        percentage: 0
                    }
                };
                
                // Create WebSocket client for this VPS
                this.connectVPSWebSocket(vpsIP, jobId);
            }
        });
    }
    
    getVPSName(vpsIP) {
        // Extract VPS identifier from IP
        const match = vpsIP.match(/(\d+\.\d+\.\d+\.\d+)/);
        if (match) {
            const ip = match[1];
            const parts = ip.split('.');
            return `VPS ${parts[parts.length - 1]}`;
        }
        return vpsIP;
    }
    
    connectVPSWebSocket(vpsIP, jobId) {
        // Create WebSocket client for this VPS
        const wsClient = new WebSocketClient(vpsIP);
        
        // Set up progress handler
        wsClient.onProgress((data) => {
            console.log(`VPS ${vpsIP} received progress update:`, data);
            const progress = data.progress || data;
            this.updateVPSProgress(vpsIP, progress);
        });
        
        // Set up completion handler
        wsClient.onComplete((data) => {
            console.log(`VPS ${vpsIP} job completed:`, data);
            this.updateVPSProgress(vpsIP, { percentage: 100 });
            // Mark this VPS as complete
            if (this.vpsProgress[vpsIP]) {
                this.vpsProgress[vpsIP].completed = true;
            }
            // Check if all jobs are complete
            this.checkAllJobsComplete();
        });
        
        // Set up error handler
        wsClient.onError((data) => {
            console.error(`VPS ${vpsIP} error:`, data);
            // Mark this VPS as having an error
            if (this.vpsProgress[vpsIP]) {
                this.vpsProgress[vpsIP].error = true;
            }
        });
        
        // Store job ID before connecting so it can be subscribed on connect
        wsClient.currentJobId = jobId;
        
        // Set up connection handler to subscribe once connected
        wsClient.onConnect(() => {
            console.log(`VPS ${vpsIP} WebSocket connected, subscribing to job ${jobId}`);
            wsClient.subscribeToJob(jobId);
        });
        
        // Connect (subscription will happen automatically on connect)
        wsClient.connect();
        
        // Store client
        this.vpsClients[vpsIP] = wsClient;
    }
    
    checkAllJobsComplete() {
        // Check if all VPS jobs are complete
        const allVPSs = Object.keys(this.vpsProgress);
        if (allVPSs.length === 0) return;
        
        const completed = allVPSs.filter(vpsIP => this.vpsProgress[vpsIP].completed);
        
        if (completed.length === allVPSs.length) {
            // All jobs complete
            this.showMessage('All searches completed successfully!', 'success');
            this.startBtn.disabled = false;
            this.stopBtn.disabled = true;
            this.downloadBtn.disabled = false;
        }
    }
    
    getVPSFromJobId(jobId) {
        // Find which VPS this job ID belongs to
        for (const [vpsIP, storedJobId] of Object.entries(this.vpsJobIds)) {
            if (storedJobId === jobId) {
                return vpsIP;
            }
        }
        return null;
    }
    
    updateVPSProgress(vpsIP, progress) {
        if (!progress) return;
        
        // Find the VPS index
        const vpsContainers = this.progressSection.querySelectorAll('.vps-progress-container');
        let vpsIndex = null;
        for (let i = 0; i < vpsContainers.length; i++) {
            if (vpsContainers[i].getAttribute('data-vps') === vpsIP) {
                vpsIndex = i + 1;
                break;
            }
        }
        
        if (!vpsIndex) return; // VPS not found
        
        // Calculate percentage if not provided
        let percentage = progress.percentage;
        if (percentage === undefined || percentage === null) {
            if (progress.combination_index > 0 && progress.total_combinations > 0) {
                percentage = (progress.combination_index / progress.total_combinations) * 100;
            } else {
                percentage = 0;
            }
        }
        
        // Update progress bar
        const progressBar = document.getElementById(`progress-bar-${vpsIndex}`);
        const progressPercentage = document.getElementById(`progress-percentage-${vpsIndex}`);
        if (progressBar && progressPercentage) {
            progressBar.style.width = `${percentage}%`;
            progressPercentage.textContent = `${percentage.toFixed(1)}%`;
        }
        
        // Update current person
        const currentPerson = document.getElementById(`current-person-${vpsIndex}`);
        if (currentPerson) {
            currentPerson.textContent = progress.person_name || 'N/A';
        }
        
        // Update current combination
        const currentCombination = document.getElementById(`current-combination-${vpsIndex}`);
        if (currentCombination) {
            if (progress.current_combination) {
                const combo = progress.current_combination;
                currentCombination.textContent = 
                    `${combo.day}/${combo.month}/${combo.year} - ${combo.state}`;
            } else {
                currentCombination.textContent = 'N/A';
            }
        }
        
        // Update matches found
        const matchesFound = document.getElementById(`matches-found-${vpsIndex}`);
        if (matchesFound) {
            matchesFound.textContent = progress.matches_found || 0;
        }
        
        // Estimate time remaining
        const estimatedTime = document.getElementById(`estimated-time-${vpsIndex}`);
        if (estimatedTime) {
            if (progress.combination_index > 0 && progress.total_combinations > 0) {
                // Get or set start time for this VPS
                if (!this.vpsProgress[vpsIP]) {
                    this.vpsProgress[vpsIP] = { startTime: Date.now() };
                }
                if (!this.vpsProgress[vpsIP].startTime) {
                    this.vpsProgress[vpsIP].startTime = Date.now();
                }
                
                const remaining = progress.total_combinations - progress.combination_index;
                const elapsedMs = Date.now() - this.vpsProgress[vpsIP].startTime;
                const elapsedSeconds = elapsedMs / 1000;
                const rate = progress.combination_index / elapsedSeconds;
                
                if (rate > 0) {
                    const estimatedSeconds = Math.round(remaining / rate);
                    const hours = Math.floor(estimatedSeconds / 3600);
                    const minutes = Math.floor((estimatedSeconds % 3600) / 60);
                    const seconds = estimatedSeconds % 60;
                    
                    if (hours > 0) {
                        estimatedTime.textContent = `${hours}h ${minutes}m`;
                    } else if (minutes > 0) {
                        estimatedTime.textContent = `${minutes}m ${seconds}s`;
                    } else {
                        estimatedTime.textContent = `${seconds}s`;
                    }
                } else {
                    estimatedTime.textContent = 'Calculating...';
                }
            } else {
                estimatedTime.textContent = 'Calculating...';
            }
        }
        
        // Store progress
        if (this.vpsProgress[vpsIP]) {
            this.vpsProgress[vpsIP].progress = progress;
        }
    }
    
    updateProgress(progress) {
        // Legacy method - now delegates to VPS-specific updates
        // This is kept for backward compatibility
        if (this.vpsClients && Object.keys(this.vpsClients).length > 0) {
            // If we have VPS clients, update the first one (for backward compatibility)
            const firstVPS = Object.keys(this.vpsClients)[0];
            this.updateVPSProgress(firstVPS, progress);
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


    updateRangePreview() {
        if (!this.rangeText) return;
        
        const yearStart = this.yearStartInput.value || '1977';
        const yearEnd = this.yearEndInput.value || '1988';
        const monthStart = this.monthStartInput.value || '1';
        const monthEnd = this.monthEndInput.value || '4';
        
        this.rangeText.textContent = `${yearStart}.${monthStart} - ${yearEnd}.${monthEnd}`;
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
