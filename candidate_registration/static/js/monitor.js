/**
 * Exam Monitor Client-side JavaScript
 * 
 * This script provides the following monitoring capabilities:
 * 1. Tab/Window visibility detection
 * 2. Mouse movement tracking
 * 3. Copy-paste/cut prevention
 * 4. Screen capture detection
 */

class ExamMonitor {
    constructor() {
        this.sessionId = this.generateSessionId();
        this.userId = null;
        this.monitorActive = false;
        this.apiEndpoints = {
            tabSwitch: '/log_tab_switch',
            mouseMovement: '/log_mouse_movement',
            screenCapture: '/detect_screen_capture',
            copyPaste: '/log_copy_paste',
            monitorFrame: '/monitor_frame'
        };
        this.intervalIds = {};
        this.mouseThrottleTimeout = null;
        this.mouseMoveThrottleMs = 500; // Only log mouse movement every 500ms
        this.lastMouseX = 0;
        this.lastMouseY = 0;
    }

    /**
     * Generate a unique session ID
     */
    generateSessionId() {
        return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }

    /**
     * Initialize the monitoring system
     * @param {string} userId - The ID of the current user
     */
    init(userId) {
        if (!userId) {
            console.error('ExamMonitor: User ID is required');
            return;
        }

        this.userId = userId;
        this.monitorActive = true;

        // Set up event listeners
        this.setupTabVisibilityMonitoring();
        this.setupMouseMovementTracking();
        this.preventCopyPaste();
        this.detectScreenCapture();

        console.log(`ExamMonitor: Monitoring initialized for user ${userId}, session ${this.sessionId}`);
    }

    /**
     * Stop all monitoring activities
     */
    stop() {
        this.monitorActive = false;
        
        // Clear all interval timers
        Object.values(this.intervalIds).forEach(id => clearInterval(id));
        
        // Remove event listeners
        document.removeEventListener('visibilitychange', this._visibilityChangeHandler);
        document.removeEventListener('mousemove', this._mouseMoveHandler);
        document.removeEventListener('copy', this._copyHandler);
        document.removeEventListener('cut', this._cutHandler);
        document.removeEventListener('paste', this._pasteHandler);
        
        console.log('ExamMonitor: Monitoring stopped');
    }

    /**
     * Display a notice to the user that monitoring is active
     */
    showMonitoringNotice() {
        const notice = document.createElement('div');
        notice.className = 'monitoring-notice';
        notice.innerHTML = `
            <div class="notice-content">
                <h3>⚠️ Monitoring Active</h3>
                <p>This exam is being monitored for security purposes:</p>
                <ul>
                    <li>Switching tabs/windows is not allowed</li>
                    <li>Copy, paste, and cut operations are disabled</li>
                    <li>Screen recording/sharing is prohibited</li>
                    <li>Mouse movements are being tracked</li>
                </ul>
                <button id="acknowledge-btn">I understand</button>
            </div>
        `;
        
        // Style the notice
        Object.assign(notice.style, {
            position: 'fixed',
            top: '0',
            left: '0',
            width: '100%',
            height: '100%',
            backgroundColor: 'rgba(0,0,0,0.8)',
            zIndex: '10000',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontFamily: 'Arial, sans-serif'
        });
        
        document.body.appendChild(notice);
        
        // Close the notice when the button is clicked
        document.getElementById('acknowledge-btn').addEventListener('click', () => {
            document.body.removeChild(notice);
        });
    }

    /**
     * Monitor tab visibility changes (tab switching)
     */
    setupTabVisibilityMonitoring() {
        this._visibilityChangeHandler = () => {
            if (!this.monitorActive) return;
            
            const isVisible = !document.hidden;
            
            // Log the tab visibility change
            this.sendToServer(this.apiEndpoints.tabSwitch, {
                user_id: this.userId,
                session_id: this.sessionId,
                event_data: {
                    visible: isVisible,
                    timestamp: Date.now()
                }
            });
            
            // If tab becomes hidden, show warning when they return
            if (!isVisible) {
                // Store the time when the tab became hidden
                this._tabHiddenAt = Date.now();
            } else if (this._tabHiddenAt) {
                // Calculate how long the tab was hidden
                const hiddenDuration = (Date.now() - this._tabHiddenAt) / 1000;
                this._tabHiddenAt = null;
                
                // Show warning if tab was hidden for more than 2 seconds
                if (hiddenDuration > 2) {
                    this.showTabSwitchWarning(hiddenDuration);
                }
            }
        };
        
        document.addEventListener('visibilitychange', this._visibilityChangeHandler);
        
        // Periodically check if window is in focus
        this.intervalIds.focusCheck = setInterval(() => {
            if (!this.monitorActive) return;
            
            const isWindowFocused = document.hasFocus();
            
            this.sendToServer(this.apiEndpoints.tabSwitch, {
                user_id: this.userId,
                session_id: this.sessionId,
                event_data: {
                    visible: isWindowFocused,
                    is_focus_check: true,
                    timestamp: Date.now()
                }
            });
            
            if (!isWindowFocused) {
                // Flash the title to prompt the user to return
                if (!this._titleFlashInterval) {
                    const originalTitle = document.title;
                    let flashState = false;
                    
                    this._titleFlashInterval = setInterval(() => {
                        document.title = flashState ? 
                            '⚠️ RETURN TO EXAM!' : 
                            originalTitle;
                        flashState = !flashState;
                    }, 500);
                    
                    // Store the original title for restoration
                    this._originalTitle = originalTitle;
                }
            } else if (this._titleFlashInterval) {
                // Stop flashing the title when the window is focused again
                clearInterval(this._titleFlashInterval);
                this._titleFlashInterval = null;
                document.title = this._originalTitle;
            }
        }, 5000);
    }
    
    /**
     * Show warning after tab switching is detected
     * @param {number} duration - How long the tab was hidden (seconds)
     */
    showTabSwitchWarning(duration) {
        const warning = document.createElement('div');
        warning.className = 'tab-switch-warning';
        warning.innerHTML = `
            <div class="warning-content">
                <h3>⚠️ Tab Switching Detected!</h3>
                <p>You left this exam tab for ${duration.toFixed(1)} seconds.</p>
                <p>This incident has been recorded and may be flagged for review.</p>
                <button id="warning-close-btn">Continue Exam</button>
            </div>
        `;
        
        // Style the warning
        Object.assign(warning.style, {
            position: 'fixed',
            top: '0',
            left: '0',
            width: '100%',
            height: '100%',
            backgroundColor: 'rgba(255,0,0,0.9)',
            zIndex: '10000',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontFamily: 'Arial, sans-serif'
        });
        
        document.body.appendChild(warning);
        
        // Close the warning when the button is clicked
        document.getElementById('warning-close-btn').addEventListener('click', () => {
            document.body.removeChild(warning);
        });
    }

    /**
     * Track mouse movements
     */
    setupMouseMovementTracking() {
        this._mouseMoveHandler = (event) => {
            if (!this.monitorActive) return;
            
            // Store the current mouse position
            const x = event.clientX;
            const y = event.clientY;
            
            // Calculate distance moved since last logged position
            const distanceSquared = Math.pow(x - this.lastMouseX, 2) + Math.pow(y - this.lastMouseY, 2);
            
            // Only log significant movements to reduce server load (moved at least 50 pixels)
            if (distanceSquared > 2500) {
                // Throttle to avoid too many requests
                if (!this.mouseThrottleTimeout) {
                    this.mouseThrottleTimeout = setTimeout(() => {
                        this.mouseThrottleTimeout = null;
                        
                        this.sendToServer(this.apiEndpoints.mouseMovement, {
                            user_id: this.userId,
                            session_id: this.sessionId,
                            movement_data: {
                                x: x,
                                y: y,
                                screenWidth: window.innerWidth,
                                screenHeight: window.innerHeight,
                                timestamp: Date.now()
                            }
                        });
                        
                        // Update the last position
                        this.lastMouseX = x;
                        this.lastMouseY = y;
                    }, this.mouseMoveThrottleMs);
                }
            }
        };
        
        document.addEventListener('mousemove', this._mouseMoveHandler);
    }

    /**
     * Prevent copy, paste and cut operations
     */
    preventCopyPaste() {
        this._copyHandler = (event) => {
            if (!this.monitorActive) return;
            
            // Get selected text
            const selectedText = window.getSelection().toString();
            
            // Log the copy attempt
            this.sendToServer(this.apiEndpoints.copyPaste, {
                user_id: this.userId,
                session_id: this.sessionId,
                event_data: {
                    type: 'copy',
                    content: selectedText,
                    timestamp: Date.now()
                }
            });
            
            // Prevent the copy operation
            event.preventDefault();
            
            // Show warning
            this.showClipboardWarning('copy');
        };
        
        this._cutHandler = (event) => {
            if (!this.monitorActive) return;
            
            // Get selected text
            const selectedText = window.getSelection().toString();
            
            // Log the cut attempt
            this.sendToServer(this.apiEndpoints.copyPaste, {
                user_id: this.userId,
                session_id: this.sessionId,
                event_data: {
                    type: 'cut',
                    content: selectedText,
                    timestamp: Date.now()
                }
            });
            
            // Prevent the cut operation
            event.preventDefault();
            
            // Show warning
            this.showClipboardWarning('cut');
        };
        
        this._pasteHandler = (event) => {
            if (!this.monitorActive) return;
            
            // Try to get paste content
            let pasteContent = '';
            if (event.clipboardData) {
                pasteContent = event.clipboardData.getData('text/plain');
            }
            
            // Log the paste attempt
            this.sendToServer(this.apiEndpoints.copyPaste, {
                user_id: this.userId,
                session_id: this.sessionId,
                event_data: {
                    type: 'paste',
                    content: pasteContent,
                    timestamp: Date.now()
                }
            });
            
            // Prevent the paste operation
            event.preventDefault();
            
            // Show warning
            this.showClipboardWarning('paste');
        };
        
        document.addEventListener('copy', this._copyHandler);
        document.addEventListener('cut', this._cutHandler);
        document.addEventListener('paste', this._pasteHandler);
        
        // Also prevent context menu to discourage right-click copy
        document.addEventListener('contextmenu', (event) => {
            if (this.monitorActive) {
                event.preventDefault();
                
                this.sendToServer(this.apiEndpoints.copyPaste, {
                    user_id: this.userId,
                    session_id: this.sessionId,
                    event_data: {
                        type: 'contextmenu',
                        timestamp: Date.now()
                    }
                });
            }
        });
    }
    
    /**
     * Show clipboard operation warning
     * @param {string} operation - Type of clipboard operation attempted
     */
    showClipboardWarning(operation) {
        // Create a temporary message that fades out
        const message = document.createElement('div');
        message.textContent = `${operation.charAt(0).toUpperCase() + operation.slice(1)} operation is not allowed during this exam`;
        
        // Style the message
        Object.assign(message.style, {
            position: 'fixed',
            bottom: '20px',
            left: '50%',
            transform: 'translateX(-50%)',
            backgroundColor: 'rgba(255, 0, 0, 0.9)',
            color: 'white',
            padding: '10px 20px',
            borderRadius: '5px',
            zIndex: '10000',
            fontFamily: 'Arial, sans-serif',
            transition: 'opacity 0.5s ease'
        });
        
        document.body.appendChild(message);
        
        // Fade out and remove after 3 seconds
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => {
                document.body.removeChild(message);
            }, 500);
        }, 3000);
    }

    /**
     * Attempt to detect screen capture and screen sharing
     */
    detectScreenCapture() {
        // Detect Print Screen key (hard to capture, not reliable on all browsers)
        document.addEventListener('keydown', (event) => {
            if (!this.monitorActive) return;
            
            // Key code 44 is Print Screen
            if (event.keyCode === 44) {
                this.sendToServer(this.apiEndpoints.screenCapture, {
                    user_id: this.userId,
                    session_id: this.sessionId,
                    event_data: {
                        type: 'print_screen',
                        timestamp: Date.now()
                    }
                });
                
                this.showScreenCaptureWarning('print screen');
            }
        });
        
        // Try to detect when a MediaRecorder is created (for screen recording)
        // This is an experimental approach and may not work in all browsers
        try {
            const originalMediaRecorder = window.MediaRecorder;
            
            window.MediaRecorder = function(...args) {
                if (window.examMonitor && window.examMonitor.monitorActive) {
                    window.examMonitor.sendToServer(window.examMonitor.apiEndpoints.screenCapture, {
                        user_id: window.examMonitor.userId,
                        session_id: window.examMonitor.sessionId,
                        event_data: {
                            type: 'screen_recording',
                            timestamp: Date.now()
                        }
                    });
                    
                    window.examMonitor.showScreenCaptureWarning('screen recording');
                }
                
                return new originalMediaRecorder(...args);
            };
            
            window.MediaRecorder.prototype = originalMediaRecorder.prototype;
            window.MediaRecorder.isTypeSupported = originalMediaRecorder.isTypeSupported;
        } catch (e) {
            console.log('Screen recording detection not supported in this browser');
        }
        
        // Try to detect getDisplayMedia (used for screen sharing)
        try {
            const originalGetDisplayMedia = navigator.mediaDevices.getDisplayMedia;
            
            navigator.mediaDevices.getDisplayMedia = function(constraints) {
                if (window.examMonitor && window.examMonitor.monitorActive) {
                    window.examMonitor.sendToServer(window.examMonitor.apiEndpoints.screenCapture, {
                        user_id: window.examMonitor.userId,
                        session_id: window.examMonitor.sessionId,
                        event_data: {
                            type: 'screen_sharing',
                            timestamp: Date.now()
                        }
                    });
                    
                    window.examMonitor.showScreenCaptureWarning('screen sharing');
                }
                
                return originalGetDisplayMedia.call(this, constraints);
            };
        } catch (e) {
            console.log('Screen sharing detection not supported in this browser');
        }
    }
    
    /**
     * Show screen capture warning
     * @param {string} captureType - Type of screen capture attempted
     */
    showScreenCaptureWarning(captureType) {
        const warning = document.createElement('div');
        warning.className = 'screen-capture-warning';
        warning.innerHTML = `
            <div class="warning-content">
                <h3>⚠️ Screen Capture Detected!</h3>
                <p>An attempt to use ${captureType} has been detected.</p>
                <p>This incident has been recorded and will be flagged for review.</p>
                <p>Screen capture of any kind is strictly prohibited during exams.</p>
                <button id="capture-warning-btn">Acknowledge</button>
            </div>
        `;
        
        // Style the warning
        Object.assign(warning.style, {
            position: 'fixed',
            top: '0',
            left: '0',
            width: '100%',
            height: '100%',
            backgroundColor: 'rgba(255,0,0,0.9)',
            zIndex: '10000',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontFamily: 'Arial, sans-serif'
        });
        
        document.body.appendChild(warning);
        
        // Close the warning when the button is clicked
        document.getElementById('capture-warning-btn').addEventListener('click', () => {
            document.body.removeChild(warning);
        });
    }

    /**
     * Send data to server endpoint
     * @param {string} endpoint - API endpoint
     * @param {object} data - Data to send
     */
    sendToServer(endpoint, data) {
        if (!this.monitorActive) return;
        
        fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify(data)
        })
        .catch(error => console.error('Error sending monitoring data:', error));
    }
    
    /**
     * Get Django CSRF token
     */
    getCsrfToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        
        return cookieValue || '';
    }
}

// Create a global instance, but DON'T initialize it automatically
window.examMonitor = new ExamMonitor();