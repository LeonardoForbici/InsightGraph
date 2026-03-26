# Transaction Explanation

## Endpoint overview
- `GET /api/transaction/{node_key}/explain?max_depth={n}` reuses the transaction traversal helper to gather lanes, terminal paths and produce a concise textual summary via `ask_ai` (Qwen chat/fast model fallbacks).
- Response includes the AI text, the model used, the origin node metadata and the first few terminal paths the explainer referenced.

## Frontend integration
- `TransactionPanel` now imports `fetchTransactionExplain` and offers a "Explicar esta transação" button once the swimlanes load.
- The modal shows loading/error states, highlights the Ollama model that answered, and renders the explanation text with preserved whitespace so the summary reads as 3-4 sentences.

## Next steps
1. Reuse `fetchTransactionExplain` wherever transaction context is exposed (e.g. swimlane quick actions).
2. Persist the explanation text per node in SQLite if auditing is required.
