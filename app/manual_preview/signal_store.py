"""Separate private signal journal; never routes to wallet RPCs."""
import json


class SignalStore:
    def __init__(self, preview_store):
        self.preview_store = preview_store

    def rpc(self, action: str, data: dict | None = None):
        store = self.preview_store
        store.verify_scope()
        try:
            with store.slots:
                with store.client.stream('POST', store.base+'/rest/v1/rpc/aura5_signals_rpc',
                                         json={'p_action': action, 'p_data': data or {}}) as response:
                    if response.status_code != 200:
                        raise ValueError('SIGNAL_STORAGE_UNAVAILABLE')
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2000000:
                            raise ValueError('SIGNAL_STORAGE_LIMIT')
                    return json.loads(raw)
        except Exception:
            raise ValueError('SIGNAL_STORAGE_UNAVAILABLE') from None
