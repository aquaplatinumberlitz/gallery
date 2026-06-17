/// <reference types="vite/client" />

import type PhotoSwipe from "photoswipe";

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Standard Vue SFC shim keeps component instance details opaque to module imports.
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

declare global {
  interface Document {
    startViewTransition?: (updateCallback: () => void) => unknown;
    wasDiscarded?: boolean;
  }

  interface Window {
    __galleryBootId?: string;
    __galleryLightboxDOMReport?: () => void;
    __loadOriginalForCurrent?: (reason: string) => void;
    __pswp?: PhotoSwipe;
    eruda?: {
      init: () => void;
    };
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
    __galleryReloadBlackBox?: {
      install: () => void;
      log: (tag: string, msg: string) => void;
      report: () => void;
      copyReport: () => Promise<void>;
      clear: () => void;
      status: () => void;
      enable: () => void;
      disable: () => void;
    };
  }
}

export {};
