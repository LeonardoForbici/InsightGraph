import { useEffect, useMemo, useState } from 'react';
import {
    addCollaborationAnnotation,
    createWarRoom,
    joinWarRoom,
    listCollaborationMessages,
    listWarRooms,
    sendCollaborationMessage,
    type CollaborationChatMessage,
    type CollaborationSession,
} from '../api';

interface CollaborationUIProps {
    selectedNodeKey?: string | null;
    onClose: () => void;
    currentUserId?: string;
}

export default function CollaborationUI({
    selectedNodeKey,
    onClose,
    currentUserId = 'local-user',
}: CollaborationUIProps) {
    const [sessions, setSessions] = useState<CollaborationSession[]>([]);
    const [activeSession, setActiveSession] = useState<CollaborationSession | null>(null);
    const [messages, setMessages] = useState<CollaborationChatMessage[]>([]);
    const [messageText, setMessageText] = useState('');
    const [annotationText, setAnnotationText] = useState('');
    const [loading, setLoading] = useState(false);

    const canAnnotate = useMemo(() => Boolean(activeSession && selectedNodeKey), [activeSession, selectedNodeKey]);

    const refreshSessions = async () => {
        const data = await listWarRooms(true);
        setSessions(data.items || []);
    };

    const refreshMessages = async (sessionId: string) => {
        const data = await listCollaborationMessages(sessionId, 80);
        setMessages((data.items || []).slice().reverse());
    };

    useEffect(() => {
        refreshSessions().catch(console.error);
    }, []);

    useEffect(() => {
        if (!activeSession) return;
        refreshMessages(activeSession.session_id).catch(console.error);
    }, [activeSession?.session_id]);

    const handleCreate = async () => {
        setLoading(true);
        try {
            const session = await createWarRoom(currentUserId);
            setActiveSession(session);
            await refreshSessions();
        } finally {
            setLoading(false);
        }
    };

    const handleJoin = async (sessionId: string) => {
        setLoading(true);
        try {
            const session = await joinWarRoom(currentUserId, sessionId);
            setActiveSession(session);
            await refreshMessages(session.session_id);
        } finally {
            setLoading(false);
        }
    };

    const handleSend = async () => {
        if (!activeSession || !messageText.trim()) return;
        const sent = await sendCollaborationMessage(
            activeSession.session_id,
            currentUserId,
            messageText.trim(),
            { selected_node: selectedNodeKey }
        );
        setMessages((prev) => [...prev, sent]);
        setMessageText('');
    };

    const handleAnnotation = async () => {
        if (!activeSession || !selectedNodeKey || !annotationText.trim()) return;
        await addCollaborationAnnotation(
            activeSession.session_id,
            selectedNodeKey,
            annotationText.trim(),
            currentUserId,
            'public'
        );
        setAnnotationText('');
    };

    return (
        <div className="overlay-modal" role="dialog" aria-modal="true">
            <div className="overlay-card" style={{ maxWidth: 900 }}>
                <header className="overlay-header">
                    <h3>War Room Collaboration</h3>
                    <button className="btn btn-ghost" onClick={onClose}>Fechar</button>
                </header>
                <div className="overlay-body" style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16 }}>
                    <aside>
                        <button className="btn btn-primary" onClick={handleCreate} disabled={loading}>
                            {loading ? 'Criando...' : 'Criar War Room'}
                        </button>
                        <div style={{ marginTop: 12 }}>
                            {sessions.map((session) => (
                                <button
                                    key={session.session_id}
                                    className={`btn ${activeSession?.session_id === session.session_id ? 'btn-primary' : 'btn-secondary'}`}
                                    style={{ display: 'block', width: '100%', marginBottom: 8 }}
                                    onClick={() => handleJoin(session.session_id)}
                                >
                                    {session.session_id} ({session.participants.length})
                                </button>
                            ))}
                        </div>
                    </aside>

                    <section>
                        <div className="panel">
                            <strong>Participantes:</strong>{' '}
                            {(activeSession?.participants || []).map((p) => p.user_id).join(', ') || 'Nenhum'}
                        </div>
                        <div className="panel" style={{ marginTop: 10, minHeight: 220, maxHeight: 260, overflowY: 'auto' }}>
                            {messages.map((msg) => (
                                <div key={msg.id} style={{ marginBottom: 10 }}>
                                    <strong>{msg.user_id}</strong>
                                    <div>{msg.text}</div>
                                </div>
                            ))}
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                            <input
                                className="input"
                                value={messageText}
                                onChange={(e) => setMessageText(e.target.value)}
                                placeholder="Mensagem da sessão..."
                            />
                            <button className="btn btn-primary" onClick={handleSend}>Enviar</button>
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                            <input
                                className="input"
                                value={annotationText}
                                onChange={(e) => setAnnotationText(e.target.value)}
                                placeholder="Anotação compartilhada para o nó selecionado"
                                disabled={!canAnnotate}
                            />
                            <button className="btn btn-secondary" onClick={handleAnnotation} disabled={!canAnnotate}>
                                Anotar Nó
                            </button>
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}
