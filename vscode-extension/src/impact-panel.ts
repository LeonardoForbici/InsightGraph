import * as vscode from 'vscode';
import { ImpactResult } from './insightgraph-client';

export class ImpactPanel {
  private static currentPanel: ImpactPanel | undefined;
  private readonly panel: vscode.WebviewPanel;

  private constructor(panel: vscode.WebviewPanel) {
    this.panel = panel;
    this.panel.onDidDispose(() => {
      ImpactPanel.currentPanel = undefined;
    });
  }

  static show(context: vscode.ExtensionContext, result: ImpactResult): void {
    if (ImpactPanel.currentPanel) {
      ImpactPanel.currentPanel.panel.reveal(vscode.ViewColumn.Beside);
      ImpactPanel.currentPanel.update(result);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'insightgraphImpact',
      'InsightGraph — Impact Analysis',
      vscode.ViewColumn.Beside,
      { enableScripts: false }
    );

    ImpactPanel.currentPanel = new ImpactPanel(panel);
    ImpactPanel.currentPanel.update(result);
  }

  private update(result: ImpactResult): void {
    this.panel.webview.html = this.buildHtml(result);
  }

  private buildHtml(result: ImpactResult): string {
    const scoreColor = result.impact_score > 60 ? '#e74c3c' : result.impact_score > 30 ? '#f39c12' : '#27ae60';

    const affectedRows = result.affected_nodes
      .map(
        (n) => `
        <tr>
          <td>${this.escape(n.name)}</td>
          <td>${this.escape(n.layer ?? '')}</td>
          <td>${n.cyclomatic_complexity ?? 'N/A'}</td>
          <td>${n.dependents_count ?? 0}</td>
        </tr>`
      )
      .join('');

    const antipatternRows = result.antipatterns
      .map(
        (a) => `
        <tr>
          <td>${this.escape(a.node_key)}</td>
          <td>${this.escape(a.type)}</td>
          <td>${this.escape(a.severity)}</td>
          <td>${this.escape(a.description)}</td>
        </tr>`
      )
      .join('');

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>InsightGraph — Impact Analysis</title>
  <style>
    body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); background: var(--vscode-editor-background); padding: 16px; }
    h1 { font-size: 1.2em; margin-bottom: 8px; }
    h2 { font-size: 1em; margin-top: 24px; margin-bottom: 8px; border-bottom: 1px solid var(--vscode-panel-border); padding-bottom: 4px; }
    .score { font-size: 2.5em; font-weight: bold; color: ${scoreColor}; }
    .meta { color: var(--vscode-descriptionForeground); margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
    th { text-align: left; padding: 6px 8px; background: var(--vscode-list-hoverBackground); }
    td { padding: 5px 8px; border-bottom: 1px solid var(--vscode-panel-border); }
    .empty { color: var(--vscode-descriptionForeground); font-style: italic; }
  </style>
</head>
<body>
  <h1>Impact Analysis</h1>
  <div class="score">${result.impact_score}<span style="font-size:0.4em;font-weight:normal">/100</span></div>
  <div class="meta">
    Target: <strong>${this.escape(result.target_key)}</strong> &nbsp;|&nbsp;
    Affected nodes: <strong>${result.affected_count}</strong> &nbsp;|&nbsp;
    Max depth: <strong>${result.max_depth}</strong>
  </div>

  <h2>Affected Nodes</h2>
  ${
    result.affected_nodes.length === 0
      ? '<p class="empty">No affected nodes found.</p>'
      : `<table>
    <thead><tr><th>Name</th><th>Layer</th><th>Complexity</th><th>Dependents</th></tr></thead>
    <tbody>${affectedRows}</tbody>
  </table>`
  }

  <h2>Antipatterns</h2>
  ${
    result.antipatterns.length === 0
      ? '<p class="empty">No antipatterns detected.</p>'
      : `<table>
    <thead><tr><th>Node</th><th>Type</th><th>Severity</th><th>Description</th></tr></thead>
    <tbody>${antipatternRows}</tbody>
  </table>`
  }
</body>
</html>`;
  }

  private escape(str: string): string {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}
