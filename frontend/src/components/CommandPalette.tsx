import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';

export type CommandItem = {
    id: string;
    label: string;
    description?: string;
    category?: string;
    action: () => void;
};

interface CommandPaletteProps {
    isOpen: boolean;
    onClose: () => void;
    items: CommandItem[];
    placeholder?: string;
}

export default function CommandPalette({ isOpen, onClose, items, placeholder = 'Buscar ação ou nó...' }: CommandPaletteProps) {
    const [query, setQuery] = useState('');
    const [highlighted, setHighlighted] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);

    const filtered = useMemo(() => {
        const normalized = query.toLowerCase();
        if (!normalized) return items;
        return items.filter((item) => {
            return (
                item.label.toLowerCase().includes(normalized) ||
                (item.description || '').toLowerCase().includes(normalized) ||
                (item.category || '').toLowerCase().includes(normalized)
            );
        });
    }, [items, query]);

    useEffect(() => {
        if (isOpen) {
            setQuery('');
            setHighlighted(0);
            setTimeout(() => inputRef.current?.focus(), 10);
        }
    }, [isOpen]);

    useEffect(() => {
        if (highlighted >= filtered.length) {
            setHighlighted(Math.max(0, filtered.length - 1));
        }
    }, [filtered.length, highlighted]);

    const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlighted((prev) => Math.min(filtered.length - 1, prev + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlighted((prev) => Math.max(0, prev - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      filtered[highlighted]?.action();
      onClose();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
    }
  };

    if (!isOpen) return null;

    return (
        <div className="command-palette-overlay" role="dialog" aria-modal="true">
            <div className="command-palette" onKeyDown={handleKeyDown}>
                <input
                    ref={inputRef}
                    className="command-palette-input"
                    placeholder={placeholder}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                />
                <div className="command-palette-list">
                    {filtered.length === 0 && (
                        <div className="command-palette-empty">Nenhuma ação encontrada.</div>
                    )}
                    {filtered.map((item, index) => (
                        <button
                            key={item.id}
                            className={`command-palette-item ${index === highlighted ? 'highlighted' : ''}`}
                            onClick={() => {
                                item.action();
                                onClose();
                            }}
                            type="button"
                        >
                            <div className="command-palette-item-label">
                                {item.label}
                                {item.category && <span className="command-palette-item-category">{item.category}</span>}
                            </div>
                            {item.description && <div className="command-palette-item-desc">{item.description}</div>}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
