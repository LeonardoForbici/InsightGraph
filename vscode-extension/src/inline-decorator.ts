import * as vscode from 'vscode';

export class InlineDecorator {
  private decorationType: vscode.TextEditorDecorationType;

  constructor() {
    this.decorationType = vscode.window.createTextEditorDecorationType({
      after: {
        margin: '0 0 0 2em',
        color: new vscode.ThemeColor('editorCodeLens.foreground'),
      },
    });
  }

  apply(editor: vscode.TextEditor, score: number, affectedCount: number): void {
    const icon = score > 60 ? '⚠️' : '✅';
    const message = `${icon} InsightGraph: impact ${score}/100 · ${affectedCount} affected`;

    const range = new vscode.Range(0, 0, 0, 0);
    const decoration: vscode.DecorationOptions = {
      range,
      renderOptions: {
        after: {
          contentText: message,
        },
      },
    };

    editor.setDecorations(this.decorationType, [decoration]);
  }

  clear(editor: vscode.TextEditor): void {
    editor.setDecorations(this.decorationType, []);
  }

  dispose(): void {
    this.decorationType.dispose();
  }
}
