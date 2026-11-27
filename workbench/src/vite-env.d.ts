/// <reference types="vite/client" />

interface Window {
  __WORKBENCH_CONFIG__?: {
    chat?: string;
    agent?: string;
    api?: string;
    samplesBase?: string;
    terminalWs?: string;
  };
}
