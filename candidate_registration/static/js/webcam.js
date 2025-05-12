document.addEventListener('DOMContentLoaded', function() {
    // DOM elements
    const registrationForm = document.getElementById('registration-form');
    const registrationSection = document.getElementById('registration-section');
    const videoSection = document.getElementById('video-section');
    const processingSection = document.getElementById('processing-section');
    const webcamElement = document.getElementById('webcam');
    const startCaptureBtn = document.getElementById('start-capture');
    const cancelCaptureBtn = document.getElementById('cancel-capture');
    const recordingProgress = document.getElementById('recording-progress');
    const recordingTimeElement = document.getElementById('recording-time');
    const processingProgressFill = document.querySelector('#processing-progress .progress-fill');
    const processingStepElement = document.getElementById('processing-step');
    const countdownElement = document.getElementById('countdown');
    
    // Global variables
    let stream = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let recordingInterval = null;
    let recordingTime = 0;
    let userId = null;
    
    // Handle registration form submission
    registrationForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const formData = new FormData(registrationForm);
        
        // Submit form data to backend
        fetch('/register', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                userId = data.user_id;
                registrationSection.classList.add('hidden');
                videoSection.classList.remove('hidden');
                initWebcam();
            }
        })
        .catch(error => {
            console.error('Error during registration:', error);
            alert('An error occurred during registration. Please try again.');
        });
    });
    
    // Initialize webcam
    function initWebcam() {
        navigator.mediaDevices.getUserMedia({ video: true, audio: true })
            .then(function(mediaStream) {
                stream = mediaStream;
                webcamElement.srcObject = mediaStream;
                webcamElement.play();
            })
            .catch(function(error) {
                console.error('Error accessing webcam:', error);
                alert('Unable to access webcam. Please ensure you have given permission and try again.');
            });
    }
    
    // Start video capture
    startCaptureBtn.addEventListener('click', function() {
        if (!stream) {
            alert('Webcam is not initialized. Please reload the page and try again.');
            return;
        }
        
        // Show countdown before recording
        showCountdown(3, function() {
            startRecording();
        });
    });
    
    // Show countdown before recording
    function showCountdown(seconds, callback) {
        countdownElement.style.display = 'block';
        countdownElement.textContent = seconds;
        
        const interval = setInterval(function() {
            seconds--;
            countdownElement.textContent = seconds;
            
            if (seconds <= 0) {
                clearInterval(interval);
                countdownElement.style.display = 'none';
                callback();
            }
        }, 1000);
    }
    
    // Start recording video
    function startRecording() {
        recordedChunks = [];
        
        // Set up media recorder
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
        
        mediaRecorder.ondataavailable = function(e) {
            if (e.data.size > 0) {
                recordedChunks.push(e.data);
            }
        };
        
        mediaRecorder.onstop = function() {
            // Stop the recording timer
            clearInterval(recordingInterval);
            
            // Hide video section and show processing section
            videoSection.classList.add('hidden');
            processingSection.classList.remove('hidden');
            
            // Create a blob from the recorded chunks
            const blob = new Blob(recordedChunks, { type: 'video/webm' });
            
            // Convert blob to base64 data URL
            const reader = new FileReader();
            reader.readAsDataURL(blob);
            
            reader.onloadend = function() {
                const base64data = reader.result;
                
                // Send video to server
                sendVideoToServer(base64data);
            };
        };
        
        // Start recording
        mediaRecorder.start(100);
        
        // Show recording progress
        recordingProgress.classList.remove('hidden');
        recordingTime = 0;
        
        // Update recording time every second
        recordingInterval = setInterval(function() {
            recordingTime++;
            recordingTimeElement.textContent = recordingTime;
            
            // Update progress bar
            const progressFill = document.querySelector('#recording-progress .progress-fill');
            progressFill.style.width = (recordingTime / 30 * 100) + '%';
            
            // Stop recording after 30 seconds
            if (recordingTime >= 30) {
                stopRecording();
            }
        }, 1000);
        
        // Disable start button and enable stop button
        startCaptureBtn.disabled = true;
    }
    
    // Stop recording
    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
    }
    
    // Cancel capture
    cancelCaptureBtn.addEventListener('click', function() {
        if (recordingInterval) {
            clearInterval(recordingInterval);
        }
        
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
        
        recordingProgress.classList.add('hidden');
        startCaptureBtn.disabled = false;
        
        // Stop webcam stream
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        
        // Go back to registration form
        videoSection.classList.add('hidden');
        registrationSection.classList.remove('hidden');
    });
    
    // Compress video before sending to server - Fixed version
    async function compressVideo(videoBlob) {
        updateProcessingProgress(10, 'Compressing video...');
        
        // Use fewer frames and a simpler compression approach
        try {
            // Calculate target size (aim for ~2MB max)
            const maxSizeMB = 2;
            const originalSizeMB = videoBlob.size / (1024 * 1024);
            
            // Skip detailed processing if the video is already small enough
            if (originalSizeMB <= maxSizeMB + 0.5) {
                console.log('Video already small enough, minimal processing needed');
                updateProcessingProgress(80, 'Finalizing compressed video...');
                // Convert directly to data URL instead of using URL.createObjectURL
                return new Promise(resolve => {
                    const reader = new FileReader();
                    reader.readAsDataURL(videoBlob);
                    reader.onloadend = () => resolve(reader.result);
                });
            }
            
            // Create a video element to get metadata
            const videoElement = document.createElement('video');
            videoElement.muted = true;
            
            // Set video source
            const videoUrl = URL.createObjectURL(videoBlob);
            videoElement.src = videoUrl;
            
            // Wait for metadata to load
            await new Promise(resolve => {
                videoElement.onloadedmetadata = resolve;
            });
            
            // For very long videos, we'll just take a few key frames
            // instead of processing the entire video
            const duration = videoElement.duration;
            
            // Determine quality reduction based on size
            let qualityReduction = 0.7; // Default medium quality
            if (originalSizeMB > 20) {
                qualityReduction = 0.4; // Lower quality for very large videos
            } else if (originalSizeMB > 10) {
                qualityReduction = 0.5; // Lower quality for large videos
            } else if (originalSizeMB > 5) {
                qualityReduction = 0.6; // Medium-low quality for medium videos
            }
            
            // Extract only key frames - this is much faster
            // We'll take 1 frame per second, which is enough for face recognition
            const frameRate = 1; 
            const totalFrames = Math.min(Math.floor(duration * frameRate), 30); // Cap at 30 frames max
            
            // Calculate frame size - reduce dimensions for larger videos
            const scaleFactor = originalSizeMB > 20 ? 0.3 : (originalSizeMB > 10 ? 0.4 : 0.5);
            
            updateProcessingProgress(20, 'Processing video frames...');
            
            // Create canvas for processing frames
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            
            // Set canvas size - scaling down the video
            const width = Math.floor(videoElement.videoWidth * scaleFactor);
            const height = Math.floor(videoElement.videoHeight * scaleFactor);
            canvas.width = width;
            canvas.height = height;
            
            // Create array to hold compressed frame data
            const frames = [];
            
            // Process the key frames in batches to avoid UI freezing
            const batchSize = 5; // Process 5 frames at a time
            
            for (let batchStart = 0; batchStart < totalFrames; batchStart += batchSize) {
                const batchEnd = Math.min(batchStart + batchSize, totalFrames);
                
                // Process a batch of frames
                for (let i = batchStart; i < batchEnd; i++) {
                    // Calculate frame time position
                    const frameTime = i * (duration / totalFrames);
                    
                    // Set video position
                    videoElement.currentTime = frameTime;
                    
                    // Wait for the frame to be ready
                    await new Promise(resolve => {
                        const timeUpdate = () => {
                            videoElement.removeEventListener('timeupdate', timeUpdate);
                            resolve();
                        };
                        videoElement.addEventListener('timeupdate', timeUpdate);
                    });
                    
                    // Draw frame to canvas at reduced size
                    ctx.drawImage(videoElement, 0, 0, width, height);
                    
                    // Get frame as JPEG at reduced quality
                    const frameDataUrl = canvas.toDataURL('image/jpeg', qualityReduction);
                    frames.push(frameDataUrl);
                    
                    // Update progress
                    const progress = Math.floor(20 + (i / totalFrames) * 60);
                    updateProcessingProgress(progress, 'Compressing video frames...');
                }
                
                // Yield to allow UI updates between batches
                await new Promise(resolve => setTimeout(resolve, 0));
            }
            
            updateProcessingProgress(80, 'Finalizing compressed video...');
            
            // Clean up
            URL.revokeObjectURL(videoUrl);
            
            // Add metadata about the compression
            const metadata = {
                originalSize: videoBlob.size,
                frameCount: frames.length,
                width: width,
                height: height,
                duration: duration,
                timestamp: Date.now()
            };
            
            // Create compressed data object with metadata
            const compressedData = {
                metadata: metadata,
                frames: frames
            };
            
            // Convert to JSON string
            const compressedJson = JSON.stringify(compressedData);
            
            // Log compression stats
            const compressedSize = new Blob([compressedJson]).size;
            console.log(`Original size: ${(videoBlob.size / (1024 * 1024)).toFixed(2)} MB`);
            console.log(`Compressed size: ${(compressedSize / (1024 * 1024)).toFixed(2)} MB`);
            console.log(`Compression ratio: ${(videoBlob.size / compressedSize).toFixed(2)}x`);
            
            // Create data URL with proper format
            return `data:application/json;base64,${btoa(unescape(encodeURIComponent(compressedJson)))}`;
            
        } catch (error) {
            console.error('Error during video compression:', error);
            // If compression fails, still return a proper data URL
            updateProcessingProgress(80, 'Using original video (compression skipped)...');
            return new Promise(resolve => {
                const reader = new FileReader();
                reader.readAsDataURL(videoBlob);
                reader.onloadend = () => resolve(reader.result);
            });
        }
    }
    
    // Send video to server
    async function sendVideoToServer(videoData) {
        try {
            // Extract data URL prefix to re-add later
            const dataUrlPrefix = videoData.substring(0, videoData.indexOf(',') + 1);
            
            // Convert base64 to blob
            const binaryString = atob(videoData.split(',')[1]);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            const videoBlob = new Blob([bytes], { type: 'video/webm' });
            
            // Check if compression is needed (skip for small videos)
            let finalVideoData = videoData;
            if (videoBlob.size > 5 * 1024 * 1024) { // If larger than 5MB
                try {
                    finalVideoData = await compressVideo(videoBlob);
                } catch (compressionError) {
                    console.error('Error compressing video:', compressionError);
                    // Continue with original video if compression fails
                }
            } else {
                console.log('Video is small enough, skipping compression');
            }
            
            updateProcessingProgress(20, 'Uploading video...');
            
            // Add retry mechanism
            let retries = 0;
            const maxRetries = 2;
            
            function attemptSend() {
                fetch('/save_video', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        video_data: finalVideoData,
                        user_id: userId
                    })
                })
                .then(response => {
                    // Check if response is valid
                    if (!response.ok) {
                        throw new Error(`Server returned ${response.status}: ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.status === 'success') {
                        // Complete success - simulate processing steps
                        simulateProcessingSteps();
                    } else if (data.status === 'partial_success') {
                        // Handle partial success (registration ok but model training failed)
                        const message = 'Your registration was completed successfully, but there was an issue with the face recognition training. ' +
                                        'This may affect future recognition accuracy. You can continue with the registration or try again later.';
                        
                        if (confirm(message + '\n\nClick OK to continue or Cancel to try again.')) {
                            // User clicked OK - continue with registration
                            simulateProcessingSteps();
                        } else {
                            // User clicked Cancel - go back to registration
                            processingSection.classList.add('hidden');
                            registrationSection.classList.remove('hidden');
                        }
                    } else {
                        // Handle specific errors with more helpful messages
                        let errorMessage = 'Error processing video: ' + (data.message || 'Unknown error');
                        
                        if (data.message && data.message.includes('frames')) {
                            errorMessage = 'We couldn\'t extract any usable frames from your video. Please ensure your face is clearly visible with good lighting, and try again.';
                        } else if (data.message && data.message.includes('small')) {
                            errorMessage = 'The recorded video is too short or didn\'t capture enough data. Please try recording for the full 30 seconds.';
                        }
                        
                        console.error('Video processing error:', data);
                        
                        // Display a more user-friendly error modal instead of an alert
                        showErrorModal(errorMessage, () => {
                            // Callback when user closes the error modal
                            processingSection.classList.add('hidden');
                            videoSection.classList.remove('hidden');
                            recordingProgress.classList.add('hidden');
                            startCaptureBtn.disabled = false;
                        });
                    }
                })
                .catch(error => {
                    console.error('Error sending video:', error);
                    
                    // If we have retries left, try again
                    if (retries < maxRetries) {
                        retries++;
                        console.log(`Retrying video upload (${retries}/${maxRetries})...`);
                        updateProcessingProgress(10, `Retrying upload (${retries}/${maxRetries})...`);
                        setTimeout(attemptSend, 2000);  // Wait 2 seconds before retrying
                    } else {
                        // Display a user-friendly error modal
                        showErrorModal(
                            'An error occurred while processing your video. This might be due to connection issues or problems with the video format. Please try again.',
                            () => {
                                // Callback when user closes the error modal
                                processingSection.classList.add('hidden');
                                videoSection.classList.remove('hidden');
                                recordingProgress.classList.add('hidden');
                                startCaptureBtn.disabled = false;
                            }
                        );
                    }
                });
            }
            
            // Start the first attempt
            attemptSend();
        } catch (error) {
            console.error('Error preparing video for upload:', error);
            showErrorModal(
                'An error occurred while preparing your video for upload. Please try again.',
                () => {
                    processingSection.classList.add('hidden');
                    videoSection.classList.remove('hidden');
                    recordingProgress.classList.add('hidden');
                    startCaptureBtn.disabled = false;
                }
            );
        }
    }
    
    // Function to show a styled error modal instead of an alert
    function showErrorModal(message, onClose) {
        // Create modal container
        const modalOverlay = document.createElement('div');
        modalOverlay.style.position = 'fixed';
        modalOverlay.style.top = '0';
        modalOverlay.style.left = '0';
        modalOverlay.style.width = '100%';
        modalOverlay.style.height = '100%';
        modalOverlay.style.backgroundColor = 'rgba(0,0,0,0.7)';
        modalOverlay.style.zIndex = '10000';
        modalOverlay.style.display = 'flex';
        modalOverlay.style.alignItems = 'center';
        modalOverlay.style.justifyContent = 'center';
        
        // Create modal content
        const modalContent = document.createElement('div');
        modalContent.style.backgroundColor = '#fff';
        modalContent.style.borderRadius = '8px';
        modalContent.style.padding = '24px';
        modalContent.style.width = '80%';
        modalContent.style.maxWidth = '450px';
        modalContent.style.boxShadow = '0 4px 12px rgba(0,0,0,0.2)';
        
        // Create error icon
        const errorIcon = document.createElement('div');
        errorIcon.innerHTML = '⚠️';
        errorIcon.style.fontSize = '48px';
        errorIcon.style.textAlign = 'center';
        errorIcon.style.marginBottom = '16px';
        
        // Create error title
        const errorTitle = document.createElement('h3');
        errorTitle.textContent = 'Error';
        errorTitle.style.margin = '0 0 16px';
        errorTitle.style.textAlign = 'center';
        errorTitle.style.color = '#d32f2f';
        
        // Create error message
        const errorMessage = document.createElement('p');
        errorMessage.textContent = message;
        errorMessage.style.marginBottom = '24px';
        errorMessage.style.textAlign = 'center';
        errorMessage.style.fontSize = '16px';
        errorMessage.style.lineHeight = '1.5';
        
        // Create close button
        const closeButton = document.createElement('button');
        closeButton.textContent = 'Try Again';
        closeButton.style.display = 'block';
        closeButton.style.width = '100%';
        closeButton.style.padding = '12px';
        closeButton.style.border = 'none';
        closeButton.style.borderRadius = '4px';
        closeButton.style.backgroundColor = '#2196f3';
        closeButton.style.color = '#fff';
        closeButton.style.fontSize = '16px';
        closeButton.style.cursor = 'pointer';
        closeButton.style.fontWeight = 'bold';
        
        // Add hover effect
        closeButton.onmouseover = () => { closeButton.style.backgroundColor = '#0b7dda'; };
        closeButton.onmouseout = () => { closeButton.style.backgroundColor = '#2196f3'; };
        
        // Assemble modal
        modalContent.appendChild(errorIcon);
        modalContent.appendChild(errorTitle);
        modalContent.appendChild(errorMessage);
        modalContent.appendChild(closeButton);
        modalOverlay.appendChild(modalContent);
        
        // Add to document
        document.body.appendChild(modalOverlay);
        
        // Set up close functionality
        closeButton.onclick = () => {
            document.body.removeChild(modalOverlay);
            if (onClose) {
                onClose();
            }
        };
    }
    
    // Update processing progress
    function updateProcessingProgress(percent, step) {
        processingProgressFill.style.width = percent + '%';
        processingStepElement.textContent = step;
    }
    
    // Simulate processing steps (for UI feedback)
    function simulateProcessingSteps() {
        // Start with extraction feedback
        updateProcessingProgress(30, 'Extracting frames...');
        
        // Set up status polling to get real progress from server
        const pollingInterval = setInterval(() => {
            if (!userId) {
                clearInterval(pollingInterval);
                return;
            }
            
            fetch(`/processing_status?user_id=${userId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'completed') {
                        // Processing complete, clear polling and redirect
                        clearInterval(pollingInterval);
                        updateProcessingProgress(100, 'Registration complete!');
                        setTimeout(() => {
                            window.location.href = '/confirmation/' + userId;
                        }, 1000);
                    } else if (data.status === 'failed') {
                        // Processing failed
                        clearInterval(pollingInterval);
                        showErrorModal(data.message || 'Processing failed', () => {
                            processingSection.classList.add('hidden');
                            videoSection.classList.remove('hidden');
                            recordingProgress.classList.add('hidden');
                            startCaptureBtn.disabled = false;
                        });
                    } else {
                        // Update progress based on server response
                        const progress = data.progress || 50;
                        const step = data.step || 'Processing your video...';
                        updateProcessingProgress(progress, step);
                    }
                })
                .catch(err => {
                    console.error('Error checking processing status:', err);
                    // Continue with simulated steps if polling fails
                });
        }, 3000); // Poll every 3 seconds
        
        // Show skip option after 20 seconds
        setTimeout(() => {
            showSkipOption(pollingInterval);
        }, 20000);
    }
    
    // Show an option to skip waiting and proceed to confirmation
    function showSkipOption(pollingInterval) {
        // Only show if we're still in the processing section
        if (processingSection.classList.contains('hidden')) {
            return;
        }
        
        // Create skip button if it doesn't exist
        if (!document.getElementById('skip-processing-btn')) {
            const skipButton = document.createElement('button');
            skipButton.id = 'skip-processing-btn';
            skipButton.textContent = 'Skip Processing and Continue';
            skipButton.className = 'btn-secondary';
            skipButton.style.marginTop = '20px';
            skipButton.style.padding = '10px 15px';
            skipButton.style.backgroundColor = '#6c757d';
            skipButton.style.color = 'white';
            skipButton.style.border = 'none';
            skipButton.style.borderRadius = '4px';
            skipButton.style.cursor = 'pointer';
            
            // Add click handler
            skipButton.addEventListener('click', () => {
                // Clear polling interval
                if (pollingInterval) {
                    clearInterval(pollingInterval);
                }
                
                // Show a message explaining what skipping means
                const message = 'The registration process will continue in the background. ' +
                                'Some features may not be fully ready right away, but you can proceed.';
                
                if (confirm(message)) {
                    // Mark processing as skipped in the database
                    fetch('/skip_processing', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            user_id: userId
                        })
                    }).catch(err => console.error('Error marking processing as skipped:', err));
                    
                    // Redirect to confirmation page
                    window.location.href = '/confirmation/' + userId;
                }
            });
            
            // Add button to processing section
            const container = document.createElement('div');
            container.style.textAlign = 'center';
            container.appendChild(skipButton);
            processingSection.appendChild(container);
            
            // Add an explanation text
            const explanation = document.createElement('p');
            explanation.textContent = 'Processing is taking longer than expected. You can skip and continue.';
            explanation.style.fontSize = '14px';
            explanation.style.color = '#666';
            explanation.style.textAlign = 'center';
            explanation.style.marginTop = '10px';
            container.appendChild(explanation);
        }
    }
});
