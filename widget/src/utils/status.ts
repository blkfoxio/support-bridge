/**
 * Status display helpers for conversations.
 */

import type { CustomerStatus } from '../api/types';

export function statusLabel(status: CustomerStatus): string {
  switch (status) {
    case 'active':
      return 'Active';
    case 'awaitingYou':
      return 'Awaiting You';
    case 'resolved':
      return 'Resolved';
    case 'closed':
      return 'Closed';
  }
}

export function statusColor(status: CustomerStatus): string {
  switch (status) {
    case 'active':
      return '#22c55e'; // green
    case 'awaitingYou':
      return '#f59e0b'; // amber
    case 'resolved':
      return '#3b82f6'; // blue
    case 'closed':
      return '#9ca3af'; // gray
  }
}

export function severityColor(severity: string): string {
  switch (severity?.toLowerCase()) {
    case 'critical':
      return '#ef4444'; // red
    case 'high':
      return '#f97316'; // orange
    case 'medium':
      return '#f59e0b'; // amber
    case 'low':
      return '#6b7280'; // gray
    default:
      return '#6b7280';
  }
}

export function severityLabel(severity: string): string {
  return (severity || 'medium').toUpperCase();
}
