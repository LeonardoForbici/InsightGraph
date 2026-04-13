declare module '@mediapipe/hands' {
  export interface HandLandmark {
    x: number;
    y: number;
    z: number;
  }

  export interface HandsResults {
    multiHandLandmarks?: HandLandmark[][];
  }

  export class Hands {
    constructor(config: { locateFile: (file: string) => string });
    setOptions(options: Record<string, unknown>): void;
    onResults(cb: (results: HandsResults) => void): void;
    send(input: { image: HTMLVideoElement }): Promise<void>;
    close(): void;
  }
}
