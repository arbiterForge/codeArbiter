/** The 3D viewer's entry point (viewer.js). It stays JavaScript, ported from the standalone explainer;
 *  this declaration is the typed boundary the page controller uses. */
export interface MachineHandle {
  /** Open a part (part-<id>), tour, failure scenario, lane run (run-ca-<command>) or lab (lab-<id>). */
  route(id: string): void;
  /** Start the scripted example session. */
  playSession(): void;
  /** Release the WebGL context, listeners, timers and the shadow content. */
  dispose(): void;
}

export interface MountOptions {
  /** The site base path without a trailing slash, for links back into the docs. */
  base?: string;
  route?: string;
  session?: boolean;
  debug?: boolean;
  onClose?: () => void;
  onRoute?: (id: string) => void;
}

export function mountMachine(host: HTMLElement, model: unknown, options?: MountOptions): Promise<MachineHandle>;
