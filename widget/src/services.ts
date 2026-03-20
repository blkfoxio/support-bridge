/**
 * Singleton service instances for the widget.
 * Initialized when SupportBridge.init() is called.
 */

import { SupportBridgeClient } from './api/client';
import { SupportBridgeSse } from './api/sse';
import type { WidgetConfig } from './api/types';

let client: SupportBridgeClient | null = null;
let sse: SupportBridgeSse | null = null;
let config: WidgetConfig | null = null;

export function initServices(widgetConfig: WidgetConfig): void {
  config = widgetConfig;
  const baseUrl = widgetConfig.baseUrl || detectBaseUrl();

  const getToken = () => config!.token;

  client = new SupportBridgeClient(baseUrl, getToken);
  sse = new SupportBridgeSse(baseUrl, getToken);
}

export function getClient(): SupportBridgeClient | null {
  return client;
}

export function getSse(): SupportBridgeSse | null {
  return sse;
}

export function getConfig(): WidgetConfig | null {
  return config;
}

export function updateToken(token: string): void {
  if (config) {
    config.token = token;
  }
}

/**
 * Detect the base URL from the script tag that loaded the widget.
 */
function detectBaseUrl(): string {
  const scripts = document.querySelectorAll('script[src*="widget"]');
  for (const script of scripts) {
    const src = script.getAttribute('src');
    if (src) {
      try {
        const url = new URL(src, window.location.href);
        return `${url.protocol}//${url.host}`;
      } catch {
        continue;
      }
    }
  }
  // Fallback: same origin
  return window.location.origin;
}
