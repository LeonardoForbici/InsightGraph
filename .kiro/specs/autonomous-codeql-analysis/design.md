# Design Document: Autonomous CodeQL Analysis

## Overview

This design document specifies the architecture for a fully autonomous CodeQL analysis system that integrates with the existing InsightGraph backend and frontend. The system enables users to trigger security analysis through a UI button, automatically managing CodeQL databases, executing analysis, and ingesting results into Neo4j without manual CLI intervention.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend UI                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ CodeQL Panel │  │ Project Mgmt │  │ Analysis History │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend API (FastAPI)                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              CodeQL Orchestrator                     │  │
│  │  • Job Management                                    │  │
│  │  • Background Task Execution                         │  │
│  │  • Progress Tracking                                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                            │                                │
│         ┌──────────────────┼──────────────────┐            │
│         ▼                  ▼                  ▼             │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Database   │  │   Analysis   │  │    SARIF     │      │
│  │  Manager    │  │   Engine     │  │  Ingestor    │      │
│  └─────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│   CodeQL     │  │   CodeQL     │  │     Neo4j        │
│   Database   │  │   SARIF      │  │   Graph Store    │
└──────────────┘  └──────────────┘  └──────────────────┘
```

### Component Responsibilities

**Frontend UI Components:**
- CodeQL Panel: Trigger analysis, configure options, display progress
- Project Management: Add/remove/configure projects for analysis
- Analysis History: View past analyses and results

**Backend Components:**
- CodeQL Orchestrator: Coordinates analysis workflow, manages jobs
- Database Manager: Creates/updates CodeQL databases
- Analysis Engine: Executes CodeQL queries, generates SARIF
- SARIF Ingestor: Parses SARIF, creates Neo4j nodes/relationships

## Data Models

### Project Configuration

```python
@dataclass
class CodeQLProject:
    id: str                    # UUID
    name: str                  # Display name
    source_path: str           # Absolute path to source code
    language: str              # java | javascript | typescript
    database_path: str         # Path to CodeQL database
    created_at: datetime
    last_analyzed: Optional[datetime]
```

### Analysis Job

```python
@dataclass
class AnalysisJob:
    job_id: str                # UUID
    project_id: str
    status: str                # queued | running | completed | failed
    stage: str                 # database_creation | analysis | ingestion
    progress: int              # 0-100
    current_file: str          # File being processed
    suite: str                 # security-extended | security-and-quality | security-critical
    force_recreate: bool       # Force database recreation
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    sarif_path: Optional[str]
    results_summary: Optional[dict]
```

### SARIF Ingestion Summary

```python
@dataclass
class IngestionSummary:
    total_issues: int
    ingested: int
    skipped: int
    tainted_paths: int
    vulnerabilities_by_severity: dict[str, int]  # error | warning | note
```

## API Endpoints

### Project Management

```
POST   /api/codeql/projects
GET    /api/codeql/projects
GET    /api/codeql/projects/{project_id}
DELETE /api/codeql/projects/{project_id}
```

### Analysis Execution

```
POST   /api/codeql/analyze
GET    /api/codeql/jobs/{job_id}
DELETE /api/codeql/jobs/{job_id}
GET    /api/codeql/history
```

### Results and Configuration

```
GET    /api/codeql/vulnerabilities/{node_key}
GET    /api/codeql/sarif/{job_id}
DELETE /api/codeql/sarif/{job_id}
GET    /api/codeql/config
```

## Implementation Details

### Database Manager

**Responsibilities:**
- Check if CodeQL database exists for project
- Create new database using `codeql database create`
- Update existing database using `codeql database upgrade`
- Detect project language automatically
- Report progress during database creation

**Algorithm:**

```
function manage_database(project, force_recreate):
    db_path = project.database_path
    
    if force_recreate or not exists(db_path):
        return create_database(project)
    
    db_age = now() - last_modified(db_path)
    if db_age > 7 days:
        log_warning("Database older than 7 days, consider recreation")
    
    return update_database(project)

function create_database(project):
    language = detect_language(project.source_path)
    
    command = [
        "codeql", "database", "create",
        project.database_path,
        f"--language={language}",
        f"--source-root={project.source_path}",
        "--threads=0"
    ]
    
    execute_with_progress(command)
    return database_path

function update_database(project):
    command = [
        "codeql", "database", "upgrade",
        project.database_path
    ]
    
    execute_with_progress(command)
    return database_path
```

### Analysis Engine

**Responsibilities:**
- Execute CodeQL analysis on prepared database
- Generate SARIF output
- Report progress
- Handle timeouts and errors

**Algorithm:**

```
function execute_analysis(database_path, suite, output_path):
    command = [
        "codeql", "database", "analyze",
        database_path,
        suite,
        "--format=sarif-latest",
        f"--output={output_path}",
        "--threads=0"
    ]
    
    result = execute_with_timeout(command, timeout=600)
    
    if result.returncode != 0:
        raise AnalysisError(result.stderr)
    
    return output_path
```

### SARIF Ingestor

**Responsibilities:**
- Parse SARIF JSON
- Map vulnerabilities to existing Neo4j entities
- Create SecurityIssue nodes
- Create HAS_VULNERABILITY relationships
- Mark tainted paths with is_tainted property

**Algorithm:**

```
function ingest_sarif(sarif_path, project_root):
    sarif_data = parse_json(sarif_path)
    issues = extract_issues(sarif_data)
    
    summary = IngestionSummary()
    
    for issue in issues:
        # Normalize file path
        rel_path = normalize_path(issue.file_path, project_root)
        
        # Find affected entity
        entity_key = find_entity_by_location(
            rel_path, 
            issue.start_line, 
            issue.end_line
        )
        
        # Create SecurityIssue node
        issue_key = f"security:{issue.rule_id}:{rel_path}:{issue.start_line}"
        create_security_issue_node(issue_key, issue)
        
        # Link to entity if found
        if entity_key:
            create_relationship(entity_key, issue_key, "HAS_VULNERABILITY")
            summary.ingested += 1
        else:
            summary.skipped += 1
        
        # Mark tainted paths
        if issue.code_flows:
            mark_tainted_paths(issue.code_flows)
            summary.tainted_paths += 1
    
    return summary

function find_entity_by_location(file_path, start_line, end_line):
    # Try exact line range match (methods)
    query = """
        MATCH (e:Entity)
        WHERE e.file = $file
          AND e.start_line IS NOT NULL
          AND e.end_line IS NOT NULL
          AND $start_line >= e.start_line
          AND $end_line <= e.end_line
        RETURN e.namespace_key
        ORDER BY (e.end_line - e.start_line) ASC
        LIMIT 1
    """
    
    result = neo4j.run(query, file=file_path, start_line=start_line, end_line=end_line)
    
    if result:
        return result[0].namespace_key
    
    # Fallback: match by file only (class-level)
    query = """
        MATCH (e:Entity)
        WHERE e.file = $file
        RETURN e.namespace_key
        LIMIT 1
    """
    
    result = neo4j.run(query, file=file_path)
    return result[0].namespace_key if result else None

function mark_tainted_paths(flow_steps):
    for i in range(len(flow_steps) - 1):
        source_step = flow_steps[i]
        target_step = flow_steps[i + 1]
        
        source_key = find_entity_by_location(
            source_step.file_path,
            source_step.start_line,
            source_step.end_line
        )
        
        target_key = find_entity_by_location(
            target_step.file_path,
            target_step.start_line,
            target_step.end_line
        )
        
        if source_key and target_key:
            query = """
                MATCH (a:Entity {namespace_key: $source})-[r]->(b:Entity {namespace_key: $target})
                SET r.is_tainted = true,
                    r.taint_message = $message
            """
            neo4j.run(query, source=source_key, target=target_key, message=target_step.message)
```

### CodeQL Orchestrator

**Responsibilities:**
- Manage analysis job lifecycle
- Execute analysis in background
- Track progress and status
- Handle concurrent analysis limits
- Maintain job queue

**Algorithm:**

```
class CodeQLOrchestrator:
    def __init__(self):
        self.jobs: dict[str, AnalysisJob] = {}
        self.active_jobs: set[str] = set()
        self.job_queue: deque[str] = deque()
        self.max_concurrent = 3
    
    async def start_analysis(self, project_id, suite, force_recreate):
        job = AnalysisJob(
            job_id=generate_uuid(),
            project_id=project_id,
            status="queued",
            stage="database_creation",
            progress=0,
            suite=suite,
            force_recreate=force_recreate,
            started_at=now()
        )
        
        self.jobs[job.job_id] = job
        
        if len(self.active_jobs) < self.max_concurrent:
            background_tasks.add_task(self.execute_analysis, job.job_id)
            self.active_jobs.add(job.job_id)
        else:
            self.job_queue.append(job.job_id)
        
        return job.job_id
    
    async def execute_analysis(self, job_id):
        job = self.jobs[job_id]
        project = get_project(job.project_id)
        
        try:
            # Stage 1: Database Management
            job.status = "running"
            job.stage = "database_creation"
            job.progress = 0
            
            db_path = database_manager.manage_database(
                project,
                job.force_recreate,
                progress_callback=lambda p: self.update_progress(job_id, p)
            )
            
            # Stage 2: Analysis Execution
            job.stage = "analysis"
            job.progress = 0
            
            sarif_path = f"./codeql-results/{project.name}_{now().isoformat()}.sarif"
            analysis_engine.execute_analysis(
                db_path,
                job.suite,
                sarif_path,
                progress_callback=lambda p: self.update_progress(job_id, p)
            )
            
            job.sarif_path = sarif_path
            
            # Stage 3: SARIF Ingestion
            job.stage = "ingestion"
            job.progress = 0
            
            summary = sarif_ingestor.ingest_sarif(
                sarif_path,
                project.source_path,
                progress_callback=lambda p: self.update_progress(job_id, p)
            )
            
            job.results_summary = asdict(summary)
            job.status = "completed"
            job.progress = 100
            job.completed_at = now()
            
            # Update project last_analyzed
            project.last_analyzed = now()
            save_project(project)
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            logger.error(f"Analysis job {job_id} failed: {e}")
        
        finally:
            self.active_jobs.remove(job_id)
            self.process_queue()
    
    def process_queue(self):
        if self.job_queue and len(self.active_jobs) < self.max_concurrent:
            next_job_id = self.job_queue.popleft()
            background_tasks.add_task(self.execute_analysis, next_job_id)
            self.active_jobs.add(next_job_id)
    
    def update_progress(self, job_id, progress):
        if job_id in self.jobs:
            self.jobs[job_id].progress = progress
    
    def get_status(self, job_id):
        return self.jobs.get(job_id)
    
    def cancel_job(self, job_id):
        if job_id in self.jobs:
            job = self.jobs[job_id]
            if job.status in ("queued", "running"):
                job.status = "cancelled"
                if job_id in self.active_jobs:
                    # Terminate CodeQL process
                    terminate_process(job_id)
                    self.active_jobs.remove(job_id)
                elif job_id in self.job_queue:
                    self.job_queue.remove(job_id)
```

## Frontend Implementation

### CodeQL Panel Component

```typescript
interface CodeQLPanelProps {
    onClose: () => void;
}

interface AnalysisConfig {
    projectIds: string[];
    suite: string;
    forceRecreate: boolean;
}

const CodeQLPanel: React.FC<CodeQLPanelProps> = ({ onClose }) => {
    const [projects, setProjects] = useState<CodeQLProject[]>([]);
    const [selectedProjects, setSelectedProjects] = useState<string[]>([]);
    const [suite, setSuite] = useState('security-extended');
    const [forceRecreate, setForceRecreate] = useState(false);
    const [analyzing, setAnalyzing] = useState(false);
    const [jobs, setJobs] = useState<Map<string, AnalysisJob>>(new Map());
    
    useEffect(() => {
        loadProjects();
    }, []);
    
    useEffect(() => {
        if (analyzing) {
            const interval = setInterval(pollJobStatus, 2000);
            return () => clearInterval(interval);
        }
    }, [analyzing]);
    
    const handleStartAnalysis = async () => {
        setAnalyzing(true);
        const newJobs = new Map();
        
        for (const projectId of selectedProjects) {
            const response = await fetch('/api/codeql/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: projectId,
                    suite: suite,
                    force_recreate: forceRecreate
                })
            });
            
            const { job_id } = await response.json();
            newJobs.set(job_id, {
                job_id,
                project_id: projectId,
                status: 'queued',
                stage: 'database_creation',
                progress: 0
            });
        }
        
        setJobs(newJobs);
    };
    
    const pollJobStatus = async () => {
        const updatedJobs = new Map(jobs);
        let allComplete = true;
        
        for (const [jobId, job] of jobs.entries()) {
            if (job.status === 'completed' || job.status === 'failed') {
                continue;
            }
            
            allComplete = false;
            
            const response = await fetch(`/api/codeql/jobs/${jobId}`);
            const updatedJob = await response.json();
            updatedJobs.set(jobId, updatedJob);
        }
        
        setJobs(updatedJobs);
        
        if (allComplete) {
            setAnalyzing(false);
        }
    };
    
    return (
        <div className="codeql-panel">
            <h2>CodeQL Analysis</h2>
            
            <div className="project-selection">
                <label>Select Projects:</label>
                <select multiple value={selectedProjects} onChange={handleProjectChange}>
                    {projects.map(p => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                </select>
            </div>
            
            <div className="suite-selection">
                <label>Query Suite:</label>
                <select value={suite} onChange={e => setSuite(e.target.value)}>
                    <option value="security-extended">Security Extended</option>
                    <option value="security-and-quality">Security & Quality</option>
                    <option value="security-critical">Security Critical</option>
                </select>
            </div>
            
            <div className="options">
                <label>
                    <input
                        type="checkbox"
                        checked={forceRecreate}
                        onChange={e => setForceRecreate(e.target.checked)}
                    />
                    Force Database Recreation
                </label>
            </div>
            
            <button
                onClick={handleStartAnalysis}
                disabled={analyzing || selectedProjects.length === 0}
            >
                {analyzing ? 'Analyzing...' : 'Start Analysis'}
            </button>
            
            {analyzing && (
                <div className="progress-section">
                    {Array.from(jobs.values()).map(job => (
                        <JobProgress key={job.job_id} job={job} />
                    ))}
                </div>
            )}
        </div>
    );
};
```

### Integration with Existing Features

**GraphCanvas Enhancement:**
```typescript
// Color tainted edges red
const getEdgeColor = (edge: Edge) => {
    if (edge.is_tainted) {
        return '#f87171'; // Red for tainted paths
    }
    return getDefaultEdgeColor(edge.type);
};
```

**ImpactAnalysisPanel Enhancement:**
```typescript
// Add Security tab
const SecurityTab = ({ nodeKey }: { nodeKey: string }) => {
    const [vulnerabilities, setVulnerabilities] = useState<SecurityIssue[]>([]);
    
    useEffect(() => {
        fetch(`/api/codeql/vulnerabilities/${nodeKey}`)
            .then(r => r.json())
            .then(setVulnerabilities);
    }, [nodeKey]);
    
    return (
        <div>
            {vulnerabilities.map(vuln => (
                <VulnerabilityCard key={vuln.namespace_key} vulnerability={vuln} />
            ))}
        </div>
    );
};
```

**FragilityCalculator Enhancement:**
```python
def calculate_fragility_score(node_key: str) -> float:
    # Existing factors
    complexity_score = get_complexity_score(node_key)
    coupling_score = get_coupling_score(node_key)
    
    # New: vulnerability factor
    vuln_count = count_vulnerabilities(node_key)
    vuln_score = min(vuln_count * 10, 30)  # Cap at 30 points
    
    total = complexity_score + coupling_score + vuln_score
    return min(total, 100)
```

## Configuration

### Environment Variables

```bash
# CodeQL CLI path
CODEQL_PATH=/path/to/codeql/codeql

# Database storage
CODEQL_DB_DIR=./codeql-databases

# SARIF output directory
CODEQL_RESULTS_DIR=./codeql-results

# Analysis limits
CODEQL_MAX_CONCURRENT=3
CODEQL_TIMEOUT=600
```

### Project Registry Storage

Projects are stored in `codeql_projects.json`:

```json
{
    "projects": [
        {
            "id": "uuid-1",
            "name": "Backend API",
            "source_path": "/path/to/backend",
            "language": "java",
            "database_path": "./codeql-databases/backend-api",
            "created_at": "2024-01-15T10:30:00Z",
            "last_analyzed": "2024-01-20T14:22:00Z"
        }
    ]
}
```

### Analysis History Storage

Analysis history is stored in `codeql_history.json`:

```json
{
    "analyses": [
        {
            "job_id": "uuid-1",
            "project_id": "uuid-1",
            "started_at": "2024-01-20T14:20:00Z",
            "completed_at": "2024-01-20T14:22:00Z",
            "duration_seconds": 120,
            "suite": "security-extended",
            "results_summary": {
                "total_issues": 15,
                "ingested": 12,
                "skipped": 3,
                "tainted_paths": 5
            }
        }
    ]
}
```

## Error Handling

### Error Categories

1. **Configuration Errors:**
   - CodeQL CLI not found
   - Invalid project path
   - Invalid database path

2. **Database Errors:**
   - Database creation failed
   - Database upgrade failed
   - Unsupported language

3. **Analysis Errors:**
   - Analysis timeout
   - Invalid query suite
   - SARIF generation failed

4. **Ingestion Errors:**
   - Invalid SARIF format
   - Neo4j connection failed
   - Entity mapping failed

### Error Response Format

```json
{
    "error": "Analysis failed",
    "details": "CodeQL CLI returned exit code 1",
    "stderr": "Error: Database not found",
    "job_id": "uuid-1",
    "stage": "analysis"
}
```

## Performance Considerations

### Database Creation Optimization

- Use `--threads=0` to utilize all CPU cores
- Cache databases and use upgrade when possible
- Recommend recreation only when database is >7 days old

### Analysis Optimization

- Limit concurrent analyses to 3 to prevent resource exhaustion
- Use background tasks to avoid blocking API
- Implement job queue for excess requests

### SARIF Ingestion Optimization

- Batch Neo4j operations
- Use MERGE instead of CREATE to avoid duplicates
- Index SecurityIssue nodes by namespace_key

## Security Considerations

### Path Validation

- Validate all file paths to prevent directory traversal
- Ensure project paths are within allowed directories
- Sanitize SARIF file paths before processing

### Process Isolation

- Run CodeQL CLI with limited permissions
- Implement timeout to prevent runaway processes
- Validate CodeQL CLI binary before execution

### Data Privacy

- Do not log sensitive source code
- Sanitize error messages before returning to frontend
- Implement access control for analysis results

## Testing Strategy

### Unit Tests

- Test each component in isolation
- Mock CodeQL CLI interactions
- Test error handling paths

### Integration Tests

- Test full analysis workflow
- Test concurrent analysis handling
- Test SARIF ingestion with sample files

### End-to-End Tests

- Test UI → Backend → Neo4j flow
- Test multi-project analysis
- Test error recovery

## Correctness Properties

### Property 1: Database Consistency
**For all projects P, if analysis completes successfully, then database exists at P.database_path**

Validates: Requirements 2.1, 2.2, 2.3

### Property 2: Job Status Progression
**For all jobs J, status transitions follow: queued → running → (completed | failed)**

Validates: Requirements 7.1, 7.2, 7.3, 12.1

### Property 3: SARIF Ingestion Completeness
**For all SARIF files S, ingested + skipped = total_issues**

Validates: Requirements 4.1, 4.2, 4.3, 4.7

### Property 4: Concurrent Job Limit
**At any time T, count(active_jobs) ≤ max_concurrent**

Validates: Requirements 12.3, 12.4

### Property 5: Taint Path Marking
**For all code flows F with length > 1, all edges in F are marked is_tainted = true**

Validates: Requirements 4.4, 4.5

### Property 6: Entity Mapping Accuracy
**For all vulnerabilities V with valid location, either entity_key is found OR V is marked orphan**

Validates: Requirements 4.6, 4.7

### Property 7: Project Configuration Persistence
**For all projects P added via API, P exists in project registry after restart**

Validates: Requirements 6.1, 6.2, 6.7

### Property 8: Analysis History Retention
**History contains at most 100 entries, oldest entries removed first**

Validates: Requirements 9.6, 9.7

### Property 9: Progress Monotonicity
**For all jobs J in running state, progress is non-decreasing over time**

Validates: Requirements 7.4, 7.5, 7.6

### Property 10: Error Message Propagation
**For all failed jobs J, error_message is non-empty and contains actionable information**

Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6

## Deployment Checklist

- [ ] Install CodeQL CLI at configured path
- [ ] Create database and results directories
- [ ] Configure environment variables
- [ ] Initialize project registry file
- [ ] Initialize history file
- [ ] Test Neo4j connectivity
- [ ] Verify CodeQL CLI version
- [ ] Test sample analysis end-to-end
- [ ] Configure frontend API endpoints
- [ ] Deploy frontend components

## Future Enhancements

1. **Custom Query Support:** Allow users to upload custom CodeQL queries
2. **Scheduled Analysis:** Periodic automatic analysis
3. **Differential Analysis:** Compare results between analyses
4. **Vulnerability Prioritization:** ML-based risk scoring
5. **Remediation Suggestions:** AI-generated fix recommendations
6. **Multi-Language Projects:** Support projects with multiple languages
7. **Cloud Integration:** Support for cloud-based CodeQL execution
8. **Notification System:** Email/Slack notifications on completion
