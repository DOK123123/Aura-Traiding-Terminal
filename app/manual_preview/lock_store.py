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
