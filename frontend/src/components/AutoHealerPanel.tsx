import { useState } from 'react';
import {
    autoDocUpdate,
    detectBugPatterns,
    generateAutoTests,
    suggestFix,
    suggestRefactor,
    type GraphNode,
} from '../api';

interface AutoHealerPanelProps {
    selectedNode?: GraphNode | null;
    onClose: () => void;
}

export default function AutoHealerPanel({ selectedNode, onClose }: AutoHealerPanelProps) {
    const [loading, setLoading] = useState(false);
    const [patterns, setPatterns] = useState<any[]>([]);
    const [fixes, setFixes] = useState<any[]>([]);
    const [tests, setTests] = useState<any | null>(null);
    const [refactor, setRefactor] = useState<any | null>(null);
    const [docDraft, setDocDraft] = useState<any | null>(null);

    const runDetection = async () => {
        setLoading(true);
        try {
            const changes = selectedNode
                ? [{ file: selectedNode.file, diff: `complexity=${selectedNode.complexity} hotspot=${selectedNode.hotspot_score}` }]
                : [];
            const result = await detectBugPatterns(changes);
            setPatterns(result.items || []);
        } finally {
            setLoading(false);
        }
    };

    const handleSuggestFix = async (pattern: any) => {
        const fix = await suggestFix(pattern);
        setFixes((prev) => [fix, ...prev]);
    };

    const handleGenerateTests = async (pattern: any) => {
        const generated = await generateAutoTests(pattern);
        setTests(generated);
    };

    const handleRefactor = async () => {
        if (!selectedNode) return;
        const generated = await suggestRefactor({
            namespace_key: selectedNode.namespace_key,
            complexity: selectedNode.complexity,
            coupling: selectedNode.cbo,
            hotspot_score: selectedNode.hotspot_score,
        });
        setRefactor(generated);
    };

    const handleDocUpdate = async () => {
        const generated = await autoDocUpdate([
            {
                file: selectedNode?.file || 'README.md',
                reason: 'Source changed but docs may be stale',
            },
        ]);
        setDocDraft(generated);
    };

    return (
        <div className="overlay-modal" role="dialog" aria-modal="true">
            <div className="overlay-card" style={{ maxWidth: 980 }}>
                <header className="overlay-header">
                    <h3>Auto Healer</h3>
                    <button className="btn btn-ghost" onClick={onClose}>Fechar</button>
                </header>
                <div className="overlay-body">
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
                        <button className="btn btn-primary" onClick={runDetection} disabled={loading}>
                            {loading ? 'Analisando...' : 'Detectar Padrões'}
                        </button>
                        <button className="btn btn-secondary" onClick={handleRefactor} disabled={!selectedNode}>
                            Sugerir Refatoração
                        </button>
                        <button className="btn btn-secondary" onClick={handleDocUpdate}>
                            Auto-documentação
                        </button>
                    </div>

                    <div className="panel" style={{ marginBottom: 12 }}>
                        <h4>Padrões Detectados</h4>
                        {(patterns || []).map((pattern) => (
                            <div key={pattern.id} style={{ marginBottom: 10 }}>
                                <strong>{pattern.pattern}</strong> — risco {pattern.risk_score}
                                <div style={{ marginTop: 6, display: 'flex', gap: 8 }}>
                                    <button className="btn btn-secondary" onClick={() => handleSuggestFix(pattern)}>
                                        Sugerir correção
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => handleGenerateTests(pattern)}>
                                        Gerar testes
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div className="panel" style={{ marginBottom: 12 }}>
                        <h4>Sugestões de Correção</h4>
                        {fixes.map((fix, idx) => (
                            <pre key={idx} style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(fix, null, 2)}</pre>
                        ))}
                    </div>

                    {tests && (
                        <div className="panel" style={{ marginBottom: 12 }}>
                            <h4>Testes Gerados</h4>
                            <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(tests, null, 2)}</pre>
                        </div>
                    )}
                    {refactor && (
                        <div className="panel" style={{ marginBottom: 12 }}>
                            <h4>Refatoração Recomendada</h4>
                            <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(refactor, null, 2)}</pre>
                        </div>
                    )}
                    {docDraft && (
                        <div className="panel">
                            <h4>Draft de Documentação</h4>
                            <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(docDraft, null, 2)}</pre>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
