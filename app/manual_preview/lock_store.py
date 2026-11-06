"""Project-attested RPC storage; no SQLite/ephemeral production fallback."""
import json


class DurableLockStore:
    def __init__(self, preview_store):
        self.preview = preview_store

    def _rpc(self, method: str, arguments: dict) -> object:
        self.preview.verify_scope()
        with self.preview.client.stream('POST', self.preview.base + '/rest/v1/rpc/' + method,
                                        json=arguments, timeout=8, follow_redirects=False) as response:
            if response.status_code == 409:
                return None
            if response.status_code != 200:
                raise ValueError('LOCK_STORAGE_UNAVAILABLE')
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 4000000:
                    raise ValueError('LOCK_STORAGE_LIMIT')
            return json.loads(raw)

    def load(self) -> tuple[int, dict]:
        value = self._rpc('aura_preview_lock_load_v1', {})
        if (not isinstance(value, dict) or type(value.get('version')) is not int
                or value['version'] < 0 or not isinstance(value.get('state'), dict)
                or any(not isinstance(value['state'].get(k), dict) for k in ('events', 'notices', 'cooldowns'))):
            raise ValueError('LOCK_STORAGE_FORMAT')
        return value['version'], value['state']

    def compare_and_swap(self, version: int, state: dict) -> bool:
        value = self._rpc('aura_preview_lock_commit_v1', {'p_version': version, 'p_state': state})
        return value is True

    def history(self, before: float, frame: str | None, limit: int, before_id: str = 'f'*64) -> list[dict]:
        result = self._rpc('aura_preview_lock_history_v1', {'p_before': before, 'p_frame': frame, 'p_limit': limit,'p_before_id':before_id})
        if not isinstance(result, list):
            raise ValueError('SIGNAL_HISTORY_FORMAT')
        return result

    def event(self, event_id: str) -> dict | None:
        return self._rpc('aura_preview_lock_event_v1', {'p_id':event_id})


class PushStore(DurableLockStore):
    def call(self, action: str, data: dict | None = None) -> object:
        if action not in {'config', 'bootstrap', 'subscribe', 'preferences', 'unsubscribe',
                          'diagnostics', 'enqueue', 'test', 'claim', 'complete', 'cleanup'}:
            raise ValueError('PUSH_ACTION_FORBIDDEN')
        return self._rpc('aura_preview_push_v1', {'p_action': action, 'p_data': data or {}})
