# Implementation Plan: Enhanced Scanner with Hand Control

## Overview

This implementation plan covers the development of two major features:
1. Enhanced scanner architecture supporting local and GitHub repository scanning
2. Hand gesture controller (beta) for gesture-based graph manipulation using webcam

The implementation follows an incremental approach, building core infrastructure first, then adding scanning capabilities, followed by hand gesture tracking, and finally integration with the graph canvas.

## Tasks

- [x] 1. Set up enhanced scanner infrastructure
  - [x] 1.1 Create scanner orchestrator with mode selection
    - Implement `ScannerOrchestrator` class in `backend/scanner_orchestrator.py`
    - Add mode selection logic (local vs github)
    - Implement background task execution with asyncio
    - Add scan status tracking and cancellation support
    - _Requirements: 3.1, 3.4, 3.5, 3.8, 3.10_

  - [x] 1.2 Enhance local scanner with progress reporting
    - Extend existing `LocalScanner` in `backend/incremental_scanner.py` or create new module
    - Add recursive directory walking with file filtering (.java, .ts, .tsx, .sql)
    - Implement progress callback mechanism (report every 10 files)
    - Add batch Neo4j writes (accumulate 50 nodes before writing)
    - Implement error collection and recovery (continue on file errors)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [x]* 1.3 Write unit tests for local scanner
    - Test file identification and filtering logic
    - Test progress reporting with mock callbacks
    - Test error handling and recovery
    - _Requirements: 1.9_

- [x] 2. Implement GitHub scanner
  - [x] 2.1 Create GitHub scanner with repository cloning
    - Implement `GitHubScanner` class in `backend/github_scanner.py`
    - Add `GitHubConfig` dataclass with repository, branch, token, shallow_clone fields
    - Implement git clone command construction with authentication
    - Add shallow clone support (--depth=1)
    - Implement temporary directory management with unique names
    - Add cleanup logic for temporary directories (on success and error)
    - Delegate scanning to LocalScanner after clone
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.10_

  - [x] 2.2 Add GitHub scanner error handling
    - Validate repository format (owner/repo)
    - Handle authentication errors with descriptive messages
    - Handle repository not found errors
    - Handle clone timeout (5 minutes)
    - Handle disk space errors
    - _Requirements: 2.8, 2.9_

  - [x]* 2.3 Write unit tests for GitHub scanner
    - Test repository format validation
    - Test git command construction with mocked subprocess
    - Test temporary directory cleanup
    - Test error handling scenarios
    - _Requirements: 2.8, 2.9_

- [x] 3. Create scanner API endpoints
  - [x] 3.1 Implement POST /api/scan endpoint
    - Add endpoint in `backend/main.py`
    - Accept mode, paths, github_config parameters
    - Validate parameters based on mode
    - Start scan in background task
    - Return 202 Accepted with scan_id
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Implement GET /api/scan/status endpoint
    - Add endpoint for progress polling
    - Return current scan status with progress metrics
    - Include scanned_files, total_files, total_nodes, progress_percent
    - _Requirements: 3.6, 1.8_

  - [x] 3.3 Implement POST /api/scan/cancel endpoint
    - Add endpoint for scan cancellation
    - Interrupt running scan task
    - Clean up temporary resources
    - Return cancellation status
    - _Requirements: 3.7, 3.8_

  - [x]* 3.4 Write integration tests for scanner API
    - Test end-to-end local scan with sample project
    - Test end-to-end GitHub scan with public test repository
    - Test scan cancellation and cleanup
    - Verify Neo4j persistence and SSE events
    - _Requirements: 3.1, 3.2, 3.3, 11.1, 11.2, 11.3_

- [x] 4. Checkpoint - Verify scanner functionality
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement MediaPipe hand tracking backend
  - [x] 5.1 Create MediaPipe handler for hand landmark extraction
    - Implement `MediaPipeHandler` class in `backend/mediapipe_handler.py`
    - Initialize MediaPipe Hands with confidence threshold 0.7
    - Implement frame processing at 640x480 resolution
    - Extract 21 landmarks per hand (up to 2 hands)
    - Calculate fingertip velocities between frames
    - Add thread separation for non-blocking processing
    - Implement resource cleanup on shutdown
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.10_

  - [x] 5.2 Create gesture recognizer for pattern detection
    - Implement `GestureRecognizer` class in `backend/gesture_recognizer.py`
    - Add pinch detection (thumb-index distance < 30px)
    - Add open hand detection (all 5 fingers extended)
    - Add fist detection (all fingers closed)
    - Add V sign detection (index and middle extended)
    - Add closing V detection (V fingers moving together)
    - Add palm forward detection (palm facing camera)
    - Implement debouncing (100ms) to prevent false positives
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x]* 5.3 Write unit tests for gesture recognition
    - Test each gesture pattern with synthetic landmarks
    - Test distance calculations for pinch detection
    - Test finger extension detection for open hand
    - Test debouncing logic
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 6. Implement hand tracking WebSocket endpoint
  - [x] 6.1 Create WebSocket endpoint for hand tracking
    - Implement `/ws/hand-tracking` endpoint in `backend/main.py`
    - Accept WebSocket connections with session validation
    - Receive video frames from client (JPEG bytes)
    - Process frames with MediaPipeHandler
    - Recognize gestures with GestureRecognizer
    - Send landmarks and gestures back to client as JSON
    - Handle connection errors and cleanup
    - _Requirements: 4.8, 4.9_

  - [x] 6.2 Add WebSocket error handling and optimization
    - Implement retry logic with exponential backoff (3 attempts)
    - Add WebSocket message size limits (1MB)
    - Enable permessage-deflate compression
    - Add frame buffer clearing every 60 frames
    - Implement landmark history pruning (keep last 10 frames)
    - _Requirements: 10.4, 10.5, 10.6, 9.8_

  - [x]* 6.3 Write integration tests for WebSocket endpoint
    - Test connection establishment and data flow
    - Test frame processing with recorded video
    - Test error handling and reconnection
    - _Requirements: 4.8, 4.9, 10.4, 10.5_

- [x] 7. Implement frontend hand gesture controller
  - [x] 7.1 Create HandGestureController React component
    - Implement `HandGestureController` class in `frontend/src/components/HandGestureController.tsx`
    - Add webcam permission request via getUserMedia
    - Establish WebSocket connection to `/ws/hand-tracking`
    - Capture and send video frames to backend
    - Receive landmark data and gesture commands
    - Manage preview video element
    - Handle activation/deactivation
    - _Requirements: 4.1, 8.2, 8.3, 8.4, 8.6_

  - [x] 7.2 Add webcam error handling
    - Handle no webcam detected error
    - Handle permission denied with modal instructions
    - Handle webcam in use error
    - Handle webcam disconnected with auto-deactivation
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 8.10_

  - [x] 7.3 Create activation toggle UI
    - Add "Controle por Gestos (Beta)" toggle button
    - Display beta badge
    - Show webcam preview miniature when active
    - Display pulsing neon indicator when active
    - Show tooltip with available gestures
    - Persist activation preference in localStorage
    - _Requirements: 8.1, 8.2, 8.4, 8.5, 8.7, 8.8, 8.9_

  - [x]* 7.4 Write unit tests for HandGestureController
    - Test webcam permission flow with mocked getUserMedia
    - Test WebSocket connection establishment
    - Test activation/deactivation logic
    - Test error handling scenarios
    - _Requirements: 8.1, 8.2, 8.6, 10.1, 10.2, 10.3_

- [x] 8. Implement neon visual effects renderer
  - [x] 8.1 Create NeonRenderer for visual feedback
    - Implement `NeonRenderer` class in `frontend/src/components/NeonRenderer.tsx`
    - Render black background (RGB 0, 0, 0)
    - Draw neon circles at fingertips (radius 8px)
    - Draw glowing lines from fingertips to palm center
    - Add particle trails along lines (fade over 500ms)
    - Implement color cycling: cyan → magenta → blue (3s transitions)
    - Add velocity-based brightness (faster = brighter)
    - Draw thin threads between adjacent fingertips
    - Apply Gaussian blur for glow effect (radius 10px)
    - Maintain 30 FPS minimum with requestAnimationFrame
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10_

  - [x] 8.2 Optimize rendering performance
    - Implement particle pooling (reuse objects)
    - Use requestAnimationFrame for rendering loop
    - Add adaptive quality (reduce FPS if CPU > 80%)
    - Implement lazy canvas operations
    - _Requirements: 9.3, 9.9_

  - [x]* 8.3 Write unit tests for NeonRenderer
    - Test canvas drawing with mock landmarks
    - Test color cycling logic
    - Test particle trail generation
    - Test performance optimizations
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 9. Checkpoint - Verify hand tracking functionality
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Integrate gestures with graph canvas
  - [x] 10.1 Extend GraphCanvas with gesture support
    - Add gesture mode flag to GraphCanvas component
    - Implement coordinate mapping (normalized 0-1 to canvas coordinates)
    - Add exponential moving average smoothing (alpha=0.3) for hand position
    - Implement virtual cursor rendering (neon circle, radius 15px)
    - Add gesture flash effect on recognition (200ms pulse)
    - _Requirements: 7.1, 7.4, 7.6, 7.9, 6.9, 6.10_

  - [x] 10.2 Implement gesture command handlers
    - Add `selectNodeByPosition()` method for pinch gesture
    - Add `moveSelectedNode()` method for drag gesture
    - Add node highlighting with neon border (3px, cyan) on selection
    - Implement zoom control for V sign gestures
    - Add deselection for fist gesture
    - Add pause tracking for palm forward gesture
    - Persist node positions after gesture manipulation
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 7.2, 7.3, 7.4, 7.8_

  - [x] 10.3 Handle multi-hand and edge cases
    - Use right hand as primary when multiple hands detected
    - Ignore gestures outside canvas area
    - Maintain compatibility with mouse/touch events
    - _Requirements: 7.7, 7.8, 7.10_

  - [x]* 10.4 Write integration tests for gesture-graph integration
    - Test node selection by gesture
    - Test node dragging by gesture
    - Test zoom by gesture
    - Test coordinate mapping accuracy
    - Test compatibility with mouse controls
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.10_

- [x] 11. Implement performance monitoring and optimization
  - [x] 11.1 Add performance monitoring
    - Track FPS and display in UI
    - Track latency (webcam → gesture command)
    - Monitor CPU usage
    - Display warnings when FPS < 15 or latency > 100ms
    - _Requirements: 9.9, 10.7_

  - [x] 11.2 Implement adaptive performance
    - Reduce resolution to 320x240 if out of memory
    - Reduce FPS to 20 if CPU > 80%
    - Gracefully degrade to tracking-only mode if FPS < 15
    - Reduce particle count and disable blur on performance drop
    - _Requirements: 9.5, 9.6, 9.9, 10.8_

  - [x]* 11.3 Write performance tests
    - Measure end-to-end latency (target < 100ms)
    - Verify FPS stays above 30 under normal load
    - Verify CPU usage stays below 50% during tracking
    - Test adaptive quality adjustments
    - _Requirements: 9.1, 9.2, 9.5, 9.9_

- [x] 12. Add frontend configuration and persistence
  - [x] 12.1 Create scanner configuration UI
    - Add mode selector (local/github) in Dashboard
    - Add local paths input with file picker
    - Add GitHub repository input (owner/repo format)
    - Add GitHub branch input (default: main)
    - Add GitHub token input (secure, masked)
    - Add shallow clone toggle
    - Persist configuration in localStorage
    - _Requirements: 3.1, 3.2, 3.3, 2.10_

  - [x] 12.2 Add scan progress UI
    - Display real-time progress bar
    - Show scanned files count and percentage
    - Show current file being processed
    - Display total nodes and relationships created
    - Add cancel button for running scans
    - Show error list if errors occurred
    - _Requirements: 1.8, 3.6_

  - [x]* 12.3 Write UI tests for scanner configuration
    - Test mode switching
    - Test form validation
    - Test localStorage persistence
    - Test progress display updates
    - _Requirements: 3.1, 3.2, 3.3, 2.10_

- [x] 13. Integrate with existing system
  - [x] 13.1 Maintain backward compatibility
    - Ensure existing /api/scan endpoints remain functional
    - Update scan_state global for polling compatibility
    - Emit SSE "graph_updated" events after scan
    - Integrate with IncrementalScanner for watch mode
    - Update memory_nodes and memory_edges
    - Invoke ImpactEngine after scan for metrics
    - Update RagStore with embeddings
    - Register scan history in state_store
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9_

  - [x]* 13.2 Write integration tests for system compatibility
    - Test SSE event emission
    - Test memory graph updates
    - Test RAG store updates
    - Test impact engine integration
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

- [x] 14. Add documentation and demo features
  - [x] 14.1 Create installation and setup documentation
    - Document Python dependencies (mediapipe, opencv-python-headless)
    - Document system dependencies (Linux: libgl1-mesa-glx, macOS: opencv)
    - Document environment variables
    - Document hardware requirements (webcam 720p, quad-core CPU)
    - Document browser requirements (Chrome 87+, Firefox 94+, Safari 15+)
    - _Requirements: 12.1, 12.4, 12.5_

  - [x] 14.2 Create user tutorial and demo mode
    - Create tutorial with screenshots of each gesture
    - Implement demo mode with gesture name overlays
    - Add onboarding tour for first activation
    - Create troubleshooting guide for common webcam issues
    - _Requirements: 12.2, 12.4, 12.6, 12.7_

  - [x] 14.3 Create demonstration video
    - Record 2-minute demo video showing all gestures
    - Show scanner modes (local and GitHub)
    - Show performance comparison
    - Include roadmap section
    - _Requirements: 12.3, 12.9, 12.10_

- [x] 15. Final checkpoint - End-to-end testing
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Backend uses Python with FastAPI, MediaPipe, and OpenCV
- Frontend uses TypeScript with React
- The implementation maintains backward compatibility with existing scanner infrastructure
- Hand gesture controller is marked as beta feature
- Performance optimizations are critical for real-time hand tracking
