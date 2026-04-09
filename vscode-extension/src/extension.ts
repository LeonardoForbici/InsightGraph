import * as vscode from 'vscode';
import { InsightGraphClient } from './insightgraph-client';
import { InlineDecorator } from './inline-decorator';
import { InsightGraphHoverProvider } from './hover-provider';
import { ImpactPanel } from './impact-panel';

let healthPollInterval: ReturnType<typeof setInterval> | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration('insightgraph');
  const serverUrl = config.get<string>('serverUrl', 'http://localhost:8000');

  const client = new InsightGraphClient(serverUrl);
  const decorator = new InlineDecorator();
  const hoverProvider = new InsightGraphHoverProvider(client);

  // Status bar item
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBar.text = '$(sync~spin) InsightGraph';
  statusBar.show();
  context.subscriptions.push(statusBar);

  // Health check helper
  async function updateHealthStatus(): Promise<void> {
    const healthy = await client.checkHealth();
    if (healthy) {
      statusBar.text = '$(check) InsightGraph';
      statusBar.tooltip = `Connected to ${serverUrl}`;
    } else {
      statusBar.text = '$(warning) InsightGraph: Offline';
      statusBar.tooltip = `Cannot reach ${serverUrl}`;
    }
  }

  // Initial health check
  updateHealthStatus();

  // Poll every 30 seconds
  healthPollInterval = setInterval(updateHealthStatus, 30_000);

  // Register hover provider for common code file types
  const hoverDisposable = vscode.languages.registerHoverProvider(
    [
      { scheme: 'file', language: 'typescript' },
      { scheme: 'file', language: 'javascript' },
      { scheme: 'file', language: 'java' },
      { scheme: 'file', language: 'python' },
    ],
    hoverProvider
  );
  context.subscriptions.push(hoverDisposable);

  // Command: analyzeImpact
  const analyzeImpactCmd = vscode.commands.registerCommand('insightgraph.analyzeImpact', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('InsightGraph: No active editor.');
      return;
    }

    const selection = editor.selection;
    const selectedText = editor.document.getText(selection).trim();
    const targetKey = selectedText || editor.document.fileName;

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'InsightGraph: Analyzing impact…', cancellable: false },
      async () => {
        try {
          const result = await client.analyzeImpact(targetKey);
          ImpactPanel.show(context, result);
        } catch (err) {
          vscode.window.showErrorMessage(`InsightGraph: Impact analysis failed — ${String(err)}`);
        }
      }
    );
  });
  context.subscriptions.push(analyzeImpactCmd);

  // Command: scanProject
  const scanProjectCmd = vscode.commands.registerCommand('insightgraph.scanProject', async () => {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      vscode.window.showWarningMessage('InsightGraph: No workspace folder open.');
      return;
    }

    const rootPath = workspaceFolders[0].uri.fsPath;

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'InsightGraph: Scanning project…', cancellable: false },
      async () => {
        try {
          const result = await client.scan(rootPath);
          hoverProvider.updateCache(result.nodes);
          vscode.window.showInformationMessage(
            `InsightGraph: Scan complete — ${result.total_nodes} nodes, ${result.total_edges} edges.`
          );
          await updateHealthStatus();
        } catch (err) {
          vscode.window.showErrorMessage(`InsightGraph: Scan failed — ${String(err)}`);
        }
      }
    );
  });
  context.subscriptions.push(scanProjectCmd);

  // Auto-analyze on save
  const onSaveDisposable = vscode.workspace.onDidSaveTextDocument(async (document) => {
    const autoAnalyze = vscode.workspace.getConfiguration('insightgraph').get<boolean>('autoAnalyzeOnSave', true);
    if (!autoAnalyze) {
      return;
    }

    const editor = vscode.window.visibleTextEditors.find((e) => e.document === document);

    try {
      const result = await client.scan(document.fileName);
      hoverProvider.updateCache(result.nodes);

      if (editor) {
        // Find the node for this file
        const fileNode = result.nodes.find((n) => n.file === document.fileName);
        if (fileNode && fileNode.score !== undefined) {
          decorator.apply(editor, fileNode.score, result.total_nodes);
        }

        // Show diagnostics for high-risk nodes
        const diagnosticCollection = vscode.languages.createDiagnosticCollection('insightgraph');
        const diagnostics: vscode.Diagnostic[] = [];

        for (const node of result.nodes) {
          if ((node.score ?? 0) > 60) {
            const range = new vscode.Range(0, 0, 0, 0);
            const diagnostic = new vscode.Diagnostic(
              range,
              `InsightGraph: High-risk node "${node.name}" (score ${node.score}/100)`,
              vscode.DiagnosticSeverity.Warning
            );
            diagnostics.push(diagnostic);
          }
        }

        diagnosticCollection.set(document.uri, diagnostics);
        context.subscriptions.push(diagnosticCollection);
      }
    } catch {
      // Silently ignore scan errors on save to avoid disrupting the developer
    }
  });
  context.subscriptions.push(onSaveDisposable);

  context.subscriptions.push({ dispose: () => decorator.dispose() });
}

export function deactivate(): void {
  if (healthPollInterval !== undefined) {
    clearInterval(healthPollInterval);
    healthPollInterval = undefined;
  }
}
