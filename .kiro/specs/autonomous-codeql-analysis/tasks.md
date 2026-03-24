# Implementation Plan: Autonomous CodeQL Analysis

## Overview

This implementation plan breaks down the autonomous CodeQL analysis system into discrete coding tasks. The system will enable users to trigger security analysis through the frontend UI, automatically managing CodeQL databases, executing analysis, and ingesting results into Neo4j. Implementation will use Python for backend components and TypeScript/React for frontend components.

## Tasks

- [x] 1. Set up backend data models and storage
  - Create Python dataclasses for CodeQLProject, AnalysisJob, and IngestionSummary
  - Implement JSON-based persistence for project registry (codeql_projects.json)
  - Implement JSON-based persistence for analysis history (codeql_history.json)
  - Add utility functions for loading/saving project and history data
  - _Requirements: 6.4, 6.7, 9.2, 9.3, 13.1_

- [ ]* 1.1 Write property test for project persistence
  - **Property 7: Project Configuration Persistence**
  - **Validates: Requirements 6.1, 6.2, 6.7**

- [ ] 2. Implement Database Manager component
  - [x] 2.1 Create DatabaseManager class in backend/codeql_database_manager.py
    - Implement manage_database() method with force_recreate logic
    - Implement create_database() method using subprocess to call CodeQL CLI
    - Implement update_database() method using codeql database upgrade
    - Implement detect_language() method to auto-detect project language
    - Add progress reporting via callback function
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 2.2 Write property test for database consistency
    - **Property 1: Database Consistency**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [ ]* 2.3 Write unit tests for DatabaseManager
    - Test database creation with different languages
    - Test database update logic
    - Test error handling for invalid paths
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

- [ ] 3. Implement Analysis Engine component
  - [x] 3.1 Create AnalysisEngine class in backend/codeql_analysis_engine.py
    - Implement execute_analysis() method to run CodeQL database analyze
    - Add support for different query suites (security-extended, security-and-quality, security-critical)
    - Implement timeout handling (600 seconds default)
    - Add progress reporting via callback function
    - Generate unique SARIF output paths with timestamp
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 14.2, 14.3, 14.5_

  - [ ]* 3.2 Write unit tests for AnalysisEngine
    - Test SARIF generation
    - Test timeout handling
    - Test suite selection
    - _Requirements: 3.1, 3.2, 3.3, 3.7, 14.2_

- [ ] 4. Enhance SARIF Ingestor component
  - [x] 4.1 Extend existing CodeQLBridge in backend/codeql_bridge.py
    - Add progress reporting to ingest_sarif() method
    - Enhance find_entity_by_location() to handle more entity types
    - Add vulnerability counting by severity
    - Improve error handling and logging
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 4.2 Write property test for SARIF ingestion completeness
    - **Property 3: SARIF Ingestion Completeness**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.7**

  - [ ]* 4.3 Write property test for taint path marking
    - **Property 5: Taint Path Marking**
    - **Validates: Requirements 4.4, 4.5**

  - [ ]* 4.4 Write property test for entity mapping accuracy
    - **Property 6: Entity Mapping Accuracy**
    - **Validates: Requirements 4.6, 4.7**

- [x] 5. Checkpoint - Ensure core components work independently
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement CodeQL Orchestrator
  - [x] 6.1 Create CodeQLOrchestrator class in backend/codeql_orchestrator.py
    - Implement job lifecycle management (jobs dict, active_jobs set, job_queue deque)
    - Implement start_analysis() method to create and queue jobs
    - Implement execute_analysis() async method to run full workflow
    - Implement process_queue() to handle concurrent job limits (max 3)
    - Implement update_progress() to track job progress
    - Implement get_status() to retrieve job information
    - Implement cancel_job() to terminate running analyses
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 7.7, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ]* 6.2 Write property test for job status progression
    - **Property 2: Job Status Progression**
    - **Validates: Requirements 7.1, 7.2, 7.3, 12.1**

  - [ ]* 6.3 Write property test for concurrent job limit
    - **Property 4: Concurrent Job Limit**
    - **Validates: Requirements 12.3, 12.4**

  - [ ]* 6.4 Write property test for progress monotonicity
    - **Property 9: Progress Monotonicity**
    - **Validates: Requirements 7.4, 7.5, 7.6**

  - [ ]* 6.5 Write unit tests for CodeQLOrchestrator
    - Test job queueing logic
    - Test concurrent execution limits
    - Test job cancellation
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 7. Implement FastAPI endpoints for project management
  - [x] 7.1 Add project management endpoints to backend/main.py
    - POST /api/codeql/projects - Add new project with validation
    - GET /api/codeql/projects - List all configured projects
    - GET /api/codeql/projects/{project_id} - Get project details
    - DELETE /api/codeql/projects/{project_id} - Remove project
    - Add Pydantic models for request/response validation
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 7.2 Write integration tests for project endpoints
    - Test project creation with valid/invalid paths
    - Test project listing and retrieval
    - Test project deletion
    - _Requirements: 6.1, 6.2, 6.3, 6.6_

- [ ] 8. Implement FastAPI endpoints for analysis execution
  - [x] 8.1 Add analysis endpoints to backend/main.py
    - POST /api/codeql/analyze - Start analysis with BackgroundTasks
    - GET /api/codeql/jobs/{job_id} - Get job status and progress
    - DELETE /api/codeql/jobs/{job_id} - Cancel running job
    - GET /api/codeql/history - List analysis history with filters
    - Add Pydantic models for analysis requests/responses
    - Wire orchestrator to endpoints
    - _Requirements: 3.1, 7.1, 7.2, 7.3, 9.1, 9.2, 9.3, 9.4, 12.1, 12.2, 12.6_

  - [ ]* 8.2 Write integration tests for analysis endpoints
    - Test analysis triggering and job creation
    - Test status polling
    - Test job cancellation
    - Test history retrieval
    - _Requirements: 7.1, 7.2, 9.2, 12.1, 12.2, 12.6_

- [ ] 9. Implement FastAPI endpoints for results and configuration
  - [x] 9.1 Add results endpoints to backend/main.py
    - GET /api/codeql/vulnerabilities/{node_key} - Get vulnerabilities for node
    - GET /api/codeql/sarif/{job_id} - Download SARIF file
    - DELETE /api/codeql/sarif/{job_id} - Delete SARIF file
    - GET /api/codeql/config - Get CodeQL configuration and CLI version
    - Update /api/health endpoint to include CodeQL CLI status
    - _Requirements: 10.7, 11.4, 11.5, 11.7, 13.3, 13.5_

  - [ ]* 9.2 Write integration tests for results endpoints
    - Test vulnerability retrieval
    - Test SARIF download
    - Test configuration endpoint
    - _Requirements: 10.7, 11.7, 13.3_

- [x] 10. Checkpoint - Ensure backend API is complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implement frontend CodeQL modal component
  - [x] 11.1 Create CodeQLModal.tsx in frontend/src/components/
    - Create modal component with project selection dropdown
    - Add query suite selection (security-extended, security-and-quality, security-critical)
    - Add "Force Database Recreation" checkbox
    - Implement "Start Analysis" button with loading state
    - Add real-time progress display for each project
    - Display stage (database_creation, analysis, ingestion) and progress percentage
    - Show completion summary with vulnerability counts
    - Add error display with copy-to-clipboard functionality
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 7.3, 7.4, 7.5, 14.1, 14.7, 15.1_

  - [ ]* 11.2 Write unit tests for CodeQLModal
    - Test project selection
    - Test analysis triggering
    - Test progress display
    - Test error handling
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 12. Implement frontend project management UI
  - [x] 12.1 Create ProjectManagement.tsx in frontend/src/components/
    - Create project list view with add/remove functionality
    - Add form for adding new projects (name, source path, language)
    - Display project details (last analyzed, database age)
    - Show database age warnings (>7 days)
    - Integrate with backend project endpoints
    - _Requirements: 6.5, 6.6, 15.6, 15.7_

  - [ ]* 12.2 Write unit tests for ProjectManagement
    - Test project addition
    - Test project removal
    - Test project listing
    - _Requirements: 6.5, 6.6_

- [x] 13. Implement frontend analysis history view
  - [x] 13.1 Create AnalysisHistory.tsx in frontend/src/components/
    - Create table view with columns: timestamp, project, duration, results
    - Add filters for project and date range
    - Display vulnerability counts by severity
    - Add detail view for past analyses
    - Implement pagination for large history
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 13.2 Write unit tests for AnalysisHistory
    - Test history display
    - Test filtering
    - Test detail view
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

- [ ] 14. Integrate CodeQL with existing frontend features
  - [x] 14.1 Enhance GraphCanvas.tsx to display tainted edges
    - Add edge coloring logic for is_tainted property (red color)
    - Add tooltip showing taint_message on hover
    - Highlight tainted paths when node with vulnerabilities is selected
    - _Requirements: 10.3, 10.6_

  - [x] 14.2 Add Security tab to ImpactAnalysisPanel.tsx
    - Create SecurityTab component to display vulnerabilities for selected node
    - Fetch vulnerabilities using /api/codeql/vulnerabilities/{node_key}
    - Display vulnerability cards with severity, rule_id, message, location
    - Show code flows for vulnerabilities with taint paths
    - Add badge showing vulnerability count on panel header
    - _Requirements: 10.2, 10.7_

  - [x] 14.3 Update StatsBar.tsx to show vulnerability counts
    - Fetch vulnerability statistics from /api/stats
    - Display total vulnerabilities by severity
    - Add click handler to open CodeQL modal
    - _Requirements: 10.4_

  - [ ]* 14.4 Write integration tests for frontend enhancements
    - Test tainted edge rendering
    - Test security tab display
    - Test stats bar vulnerability counts
    - _Requirements: 10.2, 10.3, 10.4, 10.6, 10.7_

- [x] 15. Enhance FragilityCalculator with vulnerability scoring
  - [x] 15.1 Update backend/fragility_calculator.py
    - Add count_vulnerabilities() helper function
    - Modify calculate_fragility_score() to include vulnerability factor
    - Weight vulnerabilities: +10 points per vulnerability, capped at 30
    - Update /api/fragility/{node_key} endpoint to include vulnerability count
    - _Requirements: 10.5_

  - [ ]* 15.2 Write unit tests for enhanced fragility calculation
    - Test vulnerability scoring
    - Test score capping
    - Test integration with existing factors
    - _Requirements: 10.5_

- [x] 16. Implement configuration and environment setup
  - [x] 16.1 Add configuration management to backend/main.py
    - Read CODEQL_PATH from environment variable with fallback to default
    - Read CODEQL_DB_DIR, CODEQL_RESULTS_DIR from environment
    - Read CODEQL_MAX_CONCURRENT, CODEQL_TIMEOUT from environment
    - Validate CodeQL CLI exists at startup (warning if not found)
    - Log configuration on startup
    - _Requirements: 11.1, 11.2, 11.3, 11.5, 11.6_

  - [ ]* 16.2 Write unit tests for configuration loading
    - Test environment variable reading
    - Test default fallbacks
    - Test validation logic
    - _Requirements: 11.1, 11.2, 11.3, 11.6_

- [x] 17. Implement error handling and logging
  - [x] 17.1 Add comprehensive error handling across all components
    - Add try-catch blocks with specific error messages for each error category
    - Implement error response format with error, details, stderr, job_id, stage
    - Add ERROR-level logging for all failures
    - Validate paths to prevent directory traversal
    - Sanitize error messages before returning to frontend
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 17.2 Write property test for error message propagation
    - **Property 10: Error Message Propagation**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**

  - [ ]* 17.3 Write unit tests for error handling
    - Test CodeQL CLI not found error
    - Test invalid project path error
    - Test Neo4j disconnection error
    - Test analysis failure error
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 18. Implement SARIF file management
  - [x] 18.1 Add SARIF persistence and cleanup logic
    - Create SARIF output directory on startup
    - Implement file naming with pattern {project_name}_{timestamp}.sarif
    - Add cleanup logic to remove SARIFs older than 30 days
    - Implement disk space check and automatic cleanup of oldest files
    - Add file size calculation for history responses
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

  - [ ]* 18.2 Write unit tests for SARIF management
    - Test file naming
    - Test cleanup logic
    - Test disk space handling
    - _Requirements: 13.1, 13.2, 13.4, 13.6_

- [x] 19. Implement analysis history management
  - [x] 19.1 Add history tracking and retention logic
    - Store analysis metadata on job completion
    - Implement history retrieval with filtering by project and date
    - Add retention logic to keep only last 100 analyses
    - Remove oldest entries when limit exceeded
    - _Requirements: 9.1, 9.2, 9.3, 9.6, 9.7_

  - [ ]* 19.2 Write property test for history retention
    - **Property 8: Analysis History Retention**
    - **Validates: Requirements 9.6, 9.7**

  - [ ]* 19.3 Write unit tests for history management
    - Test history storage
    - Test filtering
    - Test retention logic
    - _Requirements: 9.2, 9.3, 9.6, 9.7_

- [x] 20. Checkpoint - Ensure all features are integrated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 21. Add API documentation and update frontend API client
  - [x] 21.1 Update frontend/src/api.ts with CodeQL endpoints
    - Add TypeScript interfaces for all CodeQL data types
    - Add API functions for all CodeQL endpoints
    - Add error handling for network failures
    - _Requirements: 1.1, 6.1, 7.1, 9.1, 10.7_

  - [ ]* 21.2 Write integration tests for API client
    - Test all endpoint functions
    - Test error handling
    - _Requirements: 1.1, 6.1, 7.1, 9.1_

- [x] 22. Wire CodeQL modal trigger to main UI
  - [x] 22.1 Add CodeQL button to TopBar.tsx or Dashboard.tsx
    - Add "CodeQL Analysis" button with icon
    - Wire button to open CodeQL modal
    - Show badge with recent vulnerability count
    - _Requirements: 1.1, 1.2_

  - [ ]* 22.2 Write integration test for modal trigger
    - Test button click opens modal
    - Test badge display
    - _Requirements: 1.1, 1.2_

- [ ] 23. Final integration and end-to-end testing
  - [x] 23.1 Perform end-to-end testing of complete workflow
    - Test adding a project through UI
    - Test triggering analysis through UI
    - Test progress tracking in real-time
    - Test viewing results in graph and impact panel
    - Test viewing analysis history
    - Test error scenarios (invalid paths, CLI not found, etc.)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 10.1, 10.2, 10.3, 10.6_

  - [ ]* 23.2 Write end-to-end tests
    - Test full analysis workflow
    - Test multi-project analysis
    - Test error recovery
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ] 24. Final checkpoint - Ensure system is production-ready
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Backend implementation uses Python with FastAPI
- Frontend implementation uses TypeScript with React
- Integration builds on existing codeql_bridge.py module
