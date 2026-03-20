/**
 * Support Bridge Widget entry point.
 * Self-mounts into the DOM and exposes a global SupportBridge API.
 */

import { render, h } from 'preact';
import { Widget } from './widget';
import { initServices, updateToken } from './services';
import { widgetConfig, openWidget, navigateToNew } from './state/store';
import type { WidgetConfig } from './api/types';
import widgetStyles from './styles/widget.css?inline';

// Global API exposed to the host application
interface SupportBridgeAPI {
  init: (config: WidgetConfig) => void;
  open: () => void;
  openNewConversation: (caseId?: string, caseSubject?: string) => void;
  updateToken: (token: string) => void;
  destroy: () => void;
}

let root: HTMLDivElement | null = null;
let styleEl: HTMLStyleElement | null = null;

function injectStyles(): void {
  if (styleEl) return;
  styleEl = document.createElement('style');
  styleEl.id = 'support-bridge-widget-styles';
  styleEl.textContent = widgetStyles;
  document.head.appendChild(styleEl);
}

function removeStyles(): void {
  if (styleEl) {
    styleEl.remove();
    styleEl = null;
  }
}

function mount(): void {
  if (root) return;
  injectStyles();
  root = document.createElement('div');
  root.id = 'support-bridge-widget-root';
  document.body.appendChild(root);
  render(h(Widget, null), root);
}

function destroy(): void {
  if (root) {
    render(null, root);
    root.remove();
    root = null;
  }
  removeStyles();
}

const SupportBridge: SupportBridgeAPI = {
  init(config: WidgetConfig) {
    widgetConfig.value = config;
    initServices(config);
    mount();
  },

  open() {
    openWidget();
  },

  openNewConversation(_caseId?: string, _caseSubject?: string) {
    openWidget();
    navigateToNew();
    // TODO: wire caseId/caseSubject through store when ticket integration is built
  },

  updateToken(token: string) {
    updateToken(token);
    if (widgetConfig.value) {
      widgetConfig.value = { ...widgetConfig.value, token };
    }
  },

  destroy,
};

// Expose globally
(window as any).SupportBridge = SupportBridge;

// Auto-init if data attributes are present on the script tag
const currentScript = document.currentScript;
if (currentScript) {
  const token = currentScript.getAttribute('data-token');
  const orgId = currentScript.getAttribute('data-org-id');
  const userName = currentScript.getAttribute('data-user-name');
  const userEmail = currentScript.getAttribute('data-user-email');

  if (token && orgId && userName && userEmail) {
    SupportBridge.init({
      token,
      orgId,
      userName,
      userEmail,
    });
  }
}
