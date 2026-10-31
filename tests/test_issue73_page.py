"""Issue #73: read-only mobile shell is isolated from other Aura surfaces."""
from app.manual_preview.page import page, ASSETS


def test_shell_mounts_only_on_isolated_server_signals_preview():
    baseline=page('DUMMY',server_signals=False)
    mobile=page('DUMMY',server_signals=True)
    assert 'aura-mobile-shell.js' not in baseline
    assert 'aura-mobile-shell.css' not in baseline
    assert mobile.count('/static/aura-mobile-shell.js')==1
    assert mobile.count('/static/aura-mobile-shell.css')==1
    assert mobile.index('/static/signal-confidence.js') < mobile.index('/static/aura-mobile-shell.js')
    for current_id in ('aura-confidence','aura-signal-center','chart','timeframes',
                       'drawing-entry','drawing-stop','drawing-target','manual-paper-panel',
                       'aura-live-analyst','aura-analyst','aura-replay-panel','preview-check'):
        assert f'id="{current_id}"' in mobile
    assert '/api/active43' not in mobile
    assert 'id="active43-panel"' not in mobile


def test_new_assets_whitelisted_without_exec_endpoints():
    assert {'aura-mobile-shell.js','aura-mobile-shell.css'} <= ASSETS
    assert 'src="/static/aura-mobile-shell.js"' in page(server_signals=True)
