/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

declare global {
  interface Window {
    __galleryReloadDebug?: {
      _active: boolean;
      start: () => void;
      stop: () => void;
      mark: (label: string) => void;
      report: () => void;
      copyReport: () => Promise<void>;
      clear: () => void;
      disable: () => void;
      isActive: () => boolean;
    };
  }
}

export {}
