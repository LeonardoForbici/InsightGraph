import * as vscode from 'vscode';
import { InsightGraphClient, GraphNode } from './insightgraph-client';

export class InsightGraphHoverProvider implements vscode.HoverProvider {
  private client: InsightGraphClient;
  private nodeCache: Map<string, GraphNode> = new Map();

  constructor(client: InsightGraphClient) {
    this.client = client;
  }

  updateCache(nodes: GraphNode[]): void {
    for (const node of nodes) {
      this.nodeCache.set(node.name, node);
    }
  }

  async provideHover(
    document: vscode.TextDocument,
    position: vscode.Position,
    _token: vscode.CancellationToken
  ): Promise<vscode.Hover | null> {
    const wordRange = document.getWordRangeAtPosition(position);
    if (!wordRange) {
      return null;
    }

    const word = document.getText(wordRange);
    const node = this.nodeCache.get(word);

    if (!node) {
      return null;
    }

    const content = new vscode.MarkdownString();
    content.isTrusted = true;
    content.appendMarkdown(`**InsightGraph — ${node.name}**\n\n`);
    content.appendMarkdown(`- **Layer**: ${node.layer ?? 'unknown'}\n`);
    content.appendMarkdown(`- **Cyclomatic Complexity**: ${node.cyclomatic_complexity ?? 'N/A'}\n`);
    content.appendMarkdown(`- **Dependents**: ${node.dependents_count ?? 0}\n`);

    if (node.score !== undefined) {
      const icon = node.score > 60 ? '⚠️' : '✅';
      content.appendMarkdown(`- **Impact Score**: ${icon} ${node.score}/100\n`);
    }

    return new vscode.Hover(content, wordRange);
  }
}
