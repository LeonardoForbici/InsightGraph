import { useState, useEffect, useCallback } from 'react';
import React from 'react';

/* ─── Types ─── */

interface CodeQLProject {
    id: string;
    name: string;
    source_path: string;
    language: string;
    database_path: string;
    created_at: string;
    last_analyzed: string | null;
}

interface AnalysisJob {
    job_id: string;
    project_id: string;
    status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
    stage: 'database_creation' | 'analysis' | 'ingestion';
    progress: number;
    suite: string;
    force_recreate: boolean;
    started_at: string;
    current_file: string | null;
    completed_at: string | null;
    error_message: string | null;
    sarif_path: string | null;
    results_summary: {
        total_issues: number;
        ingested: number;
        skipped: number;
        tainted_paths: number;
        vulnerabilities_by_severity: Record<string, number>;
    } | null;
}

interface CodeQLModalProps {
    onClose: () => void;
}

/* ─── Query Suite Descriptions ─── */

const QUERY_SUITES = [
    {
        value: 'security-extended',
        label: 'Security Extended',
        description: 'Análise de segurança abrangente com queries adicionais',
    },
    {
        value: 'security-and-quality',
        label: 'Security & Quality',
        description: 'Análise de segurança + qualidade de código',
    },
    {
        value: 'security-critical',
        label: 'Security Critical',
        description: 'Apenas vulnerabilidades críticas de segurança',
    },
];

/* ─── Stage Labels ─── */

const STAGE_LABELS: Record<string, string> = {
    database_creation: 'Criando Database',
    analysis: 'Executando Análise',
    ingestion: 'Ingerindo Resultados',
};

/* ─── Component ─── */

function CodeQLModal({ onClose }: CodeQLModalProps) {
    const [projects, setProjects] = useState<CodeQLProject[]>([]);
    const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>([]);
    const [suite, setSuite] = useState('security-extended');
    const [forceRecreate, setForceRecreate] = useState(false);
    const [analyzing, setAnalyzing] = useState(false);
    const [jobs, setJobs] = useState<Map<string, AnalysisJob>>(new Map());
    const [loadingProjects, setLoadingProjects] = useState(true);
    const [error, setError] = useState('');

    // Load projects on mount
    useEffect(() => {
        loadProjects();
    }, []);

    // Clear selection when projects change
    useEffect(() => {
        // Remove selected IDs that no longer exist in projects
        setSelectedProjectIds(prev => 
            prev.filter(id => projects.some(p => p.id === id))
        );
    }, [projects]);

    // Poll job status while analyzing
    useEffect(() => {
        if (analyzing) {
            const interval = setInterval(pollJobStatus, 2000);
            return () => clearInterval(interval);
        }
    }, [analyzing, jobs]);

    const loadProjects = async () => {
        setLoadingProjects(true);
        setError('');
        try {
            const res = await fetch('/api/codeql/projects');
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            setProjects(data);
        } catch (err: any) {
            setError(err.message || 'Erro ao carregar projetos');
        } finally {
            setLoadingProjects(false);
        }
    };

    const handleStartAnalysis = async () => {
        if (selectedProjectIds.length === 0) {
            setError('Selecione pelo menos um projeto');
            return;
        }

        // Validate that all selected IDs exist in current projects
        const validIds = selectedProjectIds.filter(id => 
            projects.some(p => p.id === id)
        );
        
        if (validIds.length === 0) {
            setError('Nenhum projeto válido selecionado. Recarregue a página.');
            setSelectedProjectIds([]);
            return;
        }
        
        if (validIds.length < selectedProjectIds.length) {
            setSelectedProjectIds(validIds);
            setError('Alguns projetos selecionados não existem mais. Seleção atualizada.');
            return;
        }

        setAnalyzing(true);
        setError('');
        const newJobs = new Map<string, AnalysisJob>();

        for (const projectId of validIds) {
            try {
                const res = await fetch('/api/codeql/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        project_id: projectId,
                        suite: suite,
                        force_recreate: forceRecreate,
                    }),
                });

                if (!res.ok) throw new Error(await res.text());

                const { job_id } = await res.json();
                newJobs.set(job_id, {
                    job_id,
                    project_id: projectId,
                    status: 'queued',
                    stage: 'database_creation',
                    progress: 0,
                    suite,
                    force_recreate: forceRecreate,
                    started_at: new Date().toISOString(),
                    current_file: null,
                    completed_at: null,
                    error_message: null,
                    sarif_path: null,
                    results_summary: null,
                });
            } catch (err: any) {
                setError(`Erro ao iniciar análise: ${err.message}`);
            }
        }

        setJobs(newJobs);
    };

    const pollJobStatus = useCallback(async () => {
        const updatedJobs = new Map(jobs);
        let allComplete = true;

        for (const [jobId, job] of jobs.entries()) {
            if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
                continue;
            }

            allComplete = false;

            try {
                const res = await fetch(`/api/codeql/jobs/${jobId}`);
                if (res.status === 404) {
                    // Job no longer exists (e.g. backend restarted) — mark as failed and stop polling
                    updatedJobs.set(jobId, {
                        ...job,
                        status: 'failed',
                        error_message: 'Job não encontrado. O backend pode ter sido reiniciado.',
                        completed_at: new Date().toISOString(),
                    });
                    continue;
                }
                if (!res.ok) continue;

                const updatedJob = await res.json();
                updatedJobs.set(jobId, updatedJob);
            } catch (err) {
                console.error(`Failed to poll job ${jobId}:`, err);
            }
        }

        setJobs(updatedJobs);

        // Check if all jobs are now in a terminal state
        const allDone = [...updatedJobs.values()].every(
            j => j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled'
        );
        if (allDone && updatedJobs.size > 0) {
            setAnalyzing(false);
        }
    }, [jobs]);

    const handleProjectToggle = (projectId: string) => {
        setSelectedProjectIds((prev) =>
            prev.includes(projectId)
                ? prev.filter((id) => id !== projectId)
                : [...prev, projectId]
        );
    };

    const handleSelectAll = () => {
        if (selectedProjectIds.length === projects.length) {
            setSelectedProjectIds([]);
        } else {
            setSelectedProjectIds(projects.map((p) => p.id));
        }
    };

    const copyErrorToClipboard = (errorMessage: string) => {
        navigator.clipboard.writeText(errorMessage);
    };

    return (
        <div
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(0, 0, 0, 0.7)',
                backdropFilter: 'blur(4px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 2000,
            }}
            onClick={onClose}
        >
            <div
                style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius)',
                    width: '90vw',
                    maxWidth: 800,
                    maxHeight: '85vh',
                    display: 'flex',
                    flexDirection: 'column',
                    overflow: 'hidden',
                    boxShadow: 'var(--shadow-float)',
                }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div
                    style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '20px 24px',
                        borderBottom: '1px solid var(--border-subtle)',
                        background: 'var(--bg-glass)',
                    }}
                >
                    <div>
                        <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                            🔍 Análise CodeQL
                        </h2>
                        <p style={{ margin: '4px 0 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                            Execute análise de segurança automatizada em seus projetos
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={onClose} className="btn btn-ghost">
                            ✕ Fechar
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div style={{ padding: 24, overflowY: 'auto', flex: 1 }}>
                    {error && (
                        <div
                            style={{
                                padding: 12,
                                background: 'rgba(239, 68, 68, 0.1)',
                                border: '1px solid rgba(239, 68, 68, 0.3)',
                                borderRadius: 'var(--radius-sm)',
                                color: '#ef4444',
                                marginBottom: 16,
                                fontSize: '0.9rem',
                            }}
                        >
                            ⚠ {error}
                        </div>
                    )}

                    {loadingProjects ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            Carregando projetos...
                        </div>
                    ) : projects.length === 0 ? (
                        <div>
                            <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)', marginBottom: 24 }}>
                                Nenhum projeto configurado. Adicione um projeto para começar.
                            </div>
                            <AddProjectForm onProjectAdded={loadProjects} />
                        </div>
                    ) : (
                        <>
                            {/* Project Selection */}
                            <div style={{ marginBottom: 20 }}>
                                <div
                                    style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        marginBottom: 12,
                                    }}
                                >
                                    <label style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                                        Selecionar Projetos
                                    </label>
                                    <button onClick={handleSelectAll} className="btn btn-ghost" style={{ fontSize: '0.85rem' }}>
                                        {selectedProjectIds.length === projects.length ? 'Desmarcar Todos' : 'Selecionar Todos'}
                                    </button>
                                </div>
                                <div
                                    style={{
                                        display: 'flex',
                                        flexDirection: 'column',
                                        gap: 8,
                                        maxHeight: 200,
                                        overflowY: 'auto',
                                        padding: 12,
                                        background: 'var(--bg-card)',
                                        border: '1px solid var(--border-subtle)',
                                        borderRadius: 'var(--radius-sm)',
                                    }}
                                >
                                    {projects.map((project) => (
                                        <ProjectCard
                                            key={project.id}
                                            project={project}
                                            selected={selectedProjectIds.includes(project.id)}
                                            onToggle={() => handleProjectToggle(project.id)}
                                            onProjectUpdated={loadProjects}
                                        />
                                    ))}
                                </div>
                            </div>

                            {/* Query Suite Selection */}
                            <div style={{ marginBottom: 20 }}>
                                <label style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: 8 }}>
                                    Suite de Queries
                                </label>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    {QUERY_SUITES.map((qs) => (
                                        <label
                                            key={qs.value}
                                            style={{
                                                display: 'flex',
                                                alignItems: 'flex-start',
                                                gap: 10,
                                                padding: 12,
                                                background: suite === qs.value ? 'rgba(79, 143, 247, 0.08)' : 'var(--bg-card)',
                                                border: `1px solid ${suite === qs.value ? 'var(--border-active)' : 'var(--border-subtle)'}`,
                                                borderRadius: 'var(--radius-sm)',
                                                cursor: 'pointer',
                                                transition: 'all var(--transition-fast)',
                                            }}
                                        >
                                            <input
                                                type="radio"
                                                name="suite"
                                                value={qs.value}
                                                checked={suite === qs.value}
                                                onChange={(e) => setSuite(e.target.value)}
                                                style={{ accentColor: 'var(--accent-blue)', marginTop: 2 }}
                                            />
                                            <div style={{ flex: 1 }}>
                                                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                                                    {qs.label}
                                                </div>
                                                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 2 }}>
                                                    {qs.description}
                                                </div>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            {/* Force Database Recreation */}
                            <div style={{ marginBottom: 24 }}>
                                <label
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 10,
                                        padding: 12,
                                        background: 'var(--bg-card)',
                                        border: '1px solid var(--border-subtle)',
                                        borderRadius: 'var(--radius-sm)',
                                        cursor: 'pointer',
                                    }}
                                >
                                    <input
                                        type="checkbox"
                                        checked={forceRecreate}
                                        onChange={(e) => setForceRecreate(e.target.checked)}
                                        style={{ accentColor: 'var(--accent-blue)', width: 16, height: 16 }}
                                    />
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                                            Forçar Recriação de Database
                                        </div>
                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 2 }}>
                                            Recriar database do zero ao invés de reutilizar existente
                                        </div>
                                    </div>
                                </label>
                                
                                {/* Info message when not forcing recreation */}
                                {!forceRecreate && (
                                    <div style={{
                                        marginTop: 8,
                                        padding: 10,
                                        background: 'rgba(59, 130, 246, 0.1)',
                                        border: '1px solid rgba(59, 130, 246, 0.3)',
                                        borderRadius: 'var(--radius-sm)',
                                        fontSize: '0.8rem',
                                        color: 'var(--accent-blue)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 8,
                                    }}>
                                        <span>ℹ️</span>
                                        <span>
                                            <strong>Modo Rápido:</strong> Banco de dados existente será reutilizado (muito mais rápido). 
                                            Marque a opção acima apenas se o código mudou significativamente.
                                        </span>
                                    </div>
                                )}
                            </div>

                            {/* Start Analysis Button */}
                            <button
                                onClick={handleStartAnalysis}
                                disabled={analyzing || selectedProjectIds.length === 0}
                                className="btn btn-primary"
                                style={{ width: '100%', height: 44, fontSize: '0.95rem' }}
                            >
                                {analyzing ? '⏳ Analisando...' : '🚀 Iniciar Análise'}
                            </button>

                            {/* Progress Display */}
                            {jobs.size > 0 && (
                                <div style={{ marginTop: 24 }}>
                                    <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
                                        Progresso da Análise
                                    </h3>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                        {Array.from(jobs.values()).map((job) => {
                                            const project = projects.find((p) => p.id === job.project_id);
                                            return (
                                                <JobProgressCard
                                                    key={job.job_id}
                                                    job={job}
                                                    projectName={project?.name || 'Unknown'}
                                                    onCopyError={copyErrorToClipboard}
                                                />
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ─── Job Progress Card Component ─── */

interface JobProgressCardProps {
    job: AnalysisJob;
    projectName: string;
    onCopyError: (error: string) => void;
}

function JobProgressCard({ job, projectName, onCopyError }: JobProgressCardProps) {
    const getStatusColor = (status: string) => {
        switch (status) {
            case 'completed':
                return '#34d399';
            case 'failed':
                return '#ef4444';
            case 'cancelled':
                return '#8b93b0';
            default:
                return '#4f8ff7';
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'completed':
                return '✓';
            case 'failed':
                return '✗';
            case 'cancelled':
                return '⊘';
            case 'running':
                return '⏳';
            default:
                return '⋯';
        }
    };

    return (
        <div
            style={{
                padding: 16,
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
            }}
        >
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: '1.2rem' }}>{getStatusIcon(job.status)}</span>
                    <div>
                        <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>{projectName}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {STAGE_LABELS[job.stage] || job.stage}
                        </div>
                    </div>
                </div>
                <div
                    style={{
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        padding: '4px 8px',
                        borderRadius: 'var(--radius-xs)',
                        background: `${getStatusColor(job.status)}22`,
                        color: getStatusColor(job.status),
                    }}
                >
                    {job.status.toUpperCase()}
                </div>
            </div>

            {/* Progress Bar */}
            {(job.status === 'queued' || job.status === 'running') && (
                <div style={{ marginBottom: 12 }}>
                    <div
                        style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            fontSize: '0.75rem',
                            color: 'var(--text-muted)',
                            marginBottom: 4,
                        }}
                    >
                        <span>{STAGE_LABELS[job.stage]}</span>
                        <span>{job.progress}%</span>
                    </div>
                    <div
                        style={{
                            height: 6,
                            background: 'rgba(139, 147, 176, 0.15)',
                            borderRadius: 3,
                            overflow: 'hidden',
                        }}
                    >
                        <div
                            style={{
                                height: '100%',
                                width: `${job.progress}%`,
                                background: 'var(--gradient-brand)',
                                borderRadius: 3,
                                transition: 'width 0.5s ease',
                            }}
                        />
                    </div>
                    {job.current_file && (
                        <div
                            style={{
                                fontSize: '0.7rem',
                                color: 'var(--text-muted)',
                                marginTop: 4,
                                fontFamily: 'var(--font-mono)',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                            }}
                        >
                            {job.current_file}
                        </div>
                    )}
                </div>
            )}

            {/* Completion Summary */}
            {job.status === 'completed' && job.results_summary && (
                <div
                    style={{
                        padding: 12,
                        background: 'rgba(52, 211, 153, 0.08)',
                        border: '1px solid rgba(52, 211, 153, 0.2)',
                        borderRadius: 'var(--radius-xs)',
                        fontSize: '0.85rem',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Total de Vulnerabilidades:</span>
                        <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                            {job.results_summary.total_issues}
                        </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Ingeridas:</span>
                        <span style={{ fontWeight: 600, color: '#34d399' }}>{job.results_summary.ingested}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Ignoradas:</span>
                        <span style={{ fontWeight: 600, color: '#fb923c' }}>{job.results_summary.skipped}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Caminhos Contaminados:</span>
                        <span style={{ fontWeight: 600, color: '#f87171' }}>{job.results_summary.tainted_paths}</span>
                    </div>
                </div>
            )}

            {/* Error Display */}
            {job.status === 'failed' && job.error_message && (
                <div
                    style={{
                        padding: 12,
                        background: 'rgba(239, 68, 68, 0.08)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                        borderRadius: 'var(--radius-xs)',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#ef4444' }}>Erro:</span>
                        <button
                            onClick={() => onCopyError(job.error_message!)}
                            style={{
                                padding: '4px 8px',
                                background: 'rgba(239, 68, 68, 0.15)',
                                border: '1px solid rgba(239, 68, 68, 0.3)',
                                borderRadius: 'var(--radius-xs)',
                                color: '#ef4444',
                                fontSize: '0.7rem',
                                cursor: 'pointer',
                                transition: 'all var(--transition-fast)',
                            }}
                        >
                            📋 Copiar
                        </button>
                    </div>
                    <div
                        style={{
                            fontSize: '0.75rem',
                            color: '#fca5a5',
                            fontFamily: 'var(--font-mono)',
                            maxHeight: 100,
                            overflowY: 'auto',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                        }}
                    >
                        {job.error_message}
                    </div>
                </div>
            )}
        </div>
    );
}

/* ─── Project Card Component ─── */

interface ProjectCardProps {
    project: CodeQLProject;
    selected: boolean;
    onToggle: () => void;
    onProjectUpdated: () => void;
}

function ProjectCard({ project, selected, onToggle, onProjectUpdated }: ProjectCardProps) {
    const [showActions, setShowActions] = useState(false);
    const [editing, setEditing] = useState(false);
    const [sourcePath, setSourcePath] = useState(project.source_path);
    const [deleting, setDeleting] = useState(false);
    const [deletingDatabase, setDeletingDatabase] = useState(false);

    const handleUpdateProject = async () => {
        try {
            const res = await fetch(`/api/codeql/projects/${project.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_path: sourcePath }),
            });
            if (!res.ok) throw new Error(await res.text());
            setEditing(false);
            onProjectUpdated();
        } catch (err) {
            alert(`Erro ao atualizar projeto: ${err}`);
        }
    };

    const handleDeleteProject = async () => {
        if (!confirm(`Tem certeza que deseja deletar o projeto "${project.name}"?`)) return;
        
        setDeleting(true);
        try {
            const res = await fetch(`/api/codeql/projects/${project.id}`, {
                method: 'DELETE',
            });
            if (!res.ok) throw new Error(await res.text());
            onProjectUpdated();
        } catch (err) {
            alert(`Erro ao deletar projeto: ${err}`);
        } finally {
            setDeleting(false);
        }
    };

    const handleDeleteDatabase = async () => {
        if (!confirm(`Tem certeza que deseja deletar o banco de dados de "${project.name}"? Isso vai forçar a recriação na próxima análise.`)) return;
        
        setDeletingDatabase(true);
        try {
            const res = await fetch(`/api/codeql/projects/${project.id}/database`, {
                method: 'DELETE',
            });
            if (!res.ok) throw new Error(await res.text());
            alert('Banco de dados deletado com sucesso!');
            onProjectUpdated();
        } catch (err) {
            alert(`Erro ao deletar banco: ${err}`);
        } finally {
            setDeletingDatabase(false);
        }
    };

    if (editing) {
        return (
            <div
                style={{
                    padding: 12,
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-active)',
                    borderRadius: 'var(--radius-xs)',
                }}
            >
                <div style={{ marginBottom: 8 }}>
                    <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                        Caminho do Código Fonte
                    </label>
                    <input
                        type="text"
                        value={sourcePath}
                        onChange={(e) => setSourcePath(e.target.value)}
                        style={{
                            width: '100%',
                            padding: '6px 8px',
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 'var(--radius-xs)',
                            color: 'var(--text-primary)',
                            fontSize: '0.8rem',
                            fontFamily: 'var(--font-mono)',
                        }}
                    />
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                    <button
                        onClick={handleUpdateProject}
                        style={{
                            flex: 1,
                            padding: '6px 12px',
                            background: 'var(--accent-blue)',
                            border: 'none',
                            borderRadius: 'var(--radius-xs)',
                            color: 'white',
                            fontSize: '0.8rem',
                            cursor: 'pointer',
                        }}
                    >
                        ✓ Salvar
                    </button>
                    <button
                        onClick={() => {
                            setEditing(false);
                            setSourcePath(project.source_path);
                        }}
                        style={{
                            flex: 1,
                            padding: '6px 12px',
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 'var(--radius-xs)',
                            color: 'var(--text-secondary)',
                            fontSize: '0.8rem',
                            cursor: 'pointer',
                        }}
                    >
                        ✕ Cancelar
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div
            style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: 8,
                borderRadius: 'var(--radius-xs)',
                transition: 'background var(--transition-fast)',
                background: selected ? 'rgba(79, 143, 247, 0.08)' : 'transparent',
                position: 'relative',
            }}
            onMouseEnter={() => setShowActions(true)}
            onMouseLeave={() => setShowActions(false)}
        >
            <input
                type="checkbox"
                checked={selected}
                onChange={onToggle}
                style={{ accentColor: 'var(--accent-blue)', width: 16, height: 16, cursor: 'pointer' }}
            />
            <div style={{ flex: 1 }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {project.name}
                </div>
                <div
                    style={{
                        fontSize: '0.75rem',
                        color: 'var(--text-muted)',
                        fontFamily: 'var(--font-mono)',
                    }}
                >
                    {project.language} • {project.source_path}
                </div>
            </div>
            {project.last_analyzed && (
                <div
                    style={{
                        fontSize: '0.7rem',
                        color: 'var(--text-muted)',
                        padding: '2px 6px',
                        background: 'rgba(139, 147, 176, 0.1)',
                        borderRadius: 'var(--radius-xs)',
                    }}
                >
                    Última análise: {new Date(project.last_analyzed).toLocaleDateString()}
                </div>
            )}
            
            {/* Action Buttons */}
            {showActions && (
                <div style={{ display: 'flex', gap: 4 }}>
                    <button
                        onClick={() => setEditing(true)}
                        title="Editar caminho"
                        style={{
                            padding: '4px 8px',
                            background: 'rgba(79, 143, 247, 0.15)',
                            border: '1px solid rgba(79, 143, 247, 0.3)',
                            borderRadius: 'var(--radius-xs)',
                            color: 'var(--accent-blue)',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            transition: 'all var(--transition-fast)',
                        }}
                    >
                        ✏️
                    </button>
                    <button
                        onClick={handleDeleteDatabase}
                        disabled={deletingDatabase}
                        title="Deletar banco de dados"
                        style={{
                            padding: '4px 8px',
                            background: 'rgba(251, 146, 60, 0.15)',
                            border: '1px solid rgba(251, 146, 60, 0.3)',
                            borderRadius: 'var(--radius-xs)',
                            color: '#fb923c',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            transition: 'all var(--transition-fast)',
                        }}
                    >
                        {deletingDatabase ? '⏳' : '🗑️'}
                    </button>
                    <button
                        onClick={handleDeleteProject}
                        disabled={deleting}
                        title="Deletar projeto"
                        style={{
                            padding: '4px 8px',
                            background: 'rgba(239, 68, 68, 0.15)',
                            border: '1px solid rgba(239, 68, 68, 0.3)',
                            borderRadius: 'var(--radius-xs)',
                            color: '#ef4444',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            transition: 'all var(--transition-fast)',
                        }}
                    >
                        {deleting ? '⏳' : '✕'}
                    </button>
                </div>
            )}
        </div>
    );
}

/* ─── Add Project Form Component ─── */

function AddProjectForm({ onProjectAdded }: { onProjectAdded: () => void }) {
    const [name, setName] = useState('');
    const [sourcePath, setSourcePath] = useState('');
    const [language, setLanguage] = useState('python');
    const [adding, setAdding] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setAdding(true);
        setError('');
        setSuccess('');

        try {
            const res = await fetch('/api/codeql/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name.trim(),
                    source_path: sourcePath.trim(),
                    language: language,
                }),
            });

            if (!res.ok) {
                const errorText = await res.text();
                throw new Error(errorText);
            }

            setSuccess('Projeto adicionado com sucesso!');
            setName('');
            setSourcePath('');
            setLanguage('python');
            
            // Reload projects after a short delay
            setTimeout(() => {
                onProjectAdded();
                setSuccess('');
            }, 1500);
        } catch (err: any) {
            setError(err.message || 'Erro ao adicionar projeto');
        } finally {
            setAdding(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} style={{ maxWidth: 600, margin: '0 auto' }}>
            {error && (
                <div
                    style={{
                        padding: 12,
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        borderRadius: 'var(--radius-sm)',
                        color: '#ef4444',
                        marginBottom: 16,
                        fontSize: '0.9rem',
                    }}
                >
                    ⚠ {error}
                </div>
            )}

            {success && (
                <div
                    style={{
                        padding: 12,
                        background: 'rgba(52, 211, 153, 0.1)',
                        border: '1px solid rgba(52, 211, 153, 0.3)',
                        borderRadius: 'var(--radius-sm)',
                        color: '#34d399',
                        marginBottom: 16,
                        fontSize: '0.9rem',
                    }}
                >
                    ✓ {success}
                </div>
            )}

            <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
                    Nome do Projeto
                </label>
                <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="meu-projeto"
                    required
                    style={{
                        width: '100%',
                        padding: '10px 12px',
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                    }}
                />
            </div>

            <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
                    Caminho do Código Fonte
                </label>
                <input
                    type="text"
                    value={sourcePath}
                    onChange={(e) => setSourcePath(e.target.value)}
                    placeholder="C:\caminho\do\projeto"
                    required
                    style={{
                        width: '100%',
                        padding: '10px 12px',
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                        fontFamily: 'var(--font-mono)',
                    }}
                />
            </div>

            <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
                    Linguagem
                </label>
                <select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    style={{
                        width: '100%',
                        padding: '10px 12px',
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--text-primary)',
                        fontSize: '0.9rem',
                    }}
                >
                    <option value="python">Python</option>
                    <option value="java">Java</option>
                    <option value="javascript">JavaScript</option>
                    <option value="typescript">TypeScript</option>
                    <option value="csharp">C#</option>
                    <option value="cpp">C++</option>
                    <option value="go">Go</option>
                    <option value="ruby">Ruby</option>
                </select>
            </div>

            <button
                type="submit"
                disabled={adding || !name.trim() || !sourcePath.trim()}
                className="btn btn-primary"
                style={{ width: '100%', height: 44, fontSize: '0.95rem' }}
            >
                {adding ? '⏳ Adicionando...' : '+ Adicionar Projeto'}
            </button>
        </form>
    );
}

/* ─── Main Export ─── */

export default CodeQLModal;
