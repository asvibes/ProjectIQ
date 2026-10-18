import { useCallback, useState } from 'react';
import { apiUnavailableMessage } from '../api/connection';

export function useApiNotice() {
  const [message, setMessage] = useState('');
  const reportUnavailable = useCallback((action: string) => setMessage(apiUnavailableMessage(action)), []);
  const clearMessage = useCallback(() => setMessage(''), []);
  return { message, reportUnavailable, clearMessage, clearNotice: clearMessage };
}
