export const API_CONNECTION = Object.freeze({
  configured: false,
  baseUrl: null as string | null,
  mode: 'frontend-only' as const,
});

export function isApiConnected(): boolean {
  return API_CONNECTION.configured && Boolean(API_CONNECTION.baseUrl);
}

export function apiUnavailableMessage(action: string): string {
  return `The backend API is not connected. ${action} was not sent or saved; your current form entries remain on screen.`;
}
