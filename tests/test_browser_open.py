"""Browser pop-up chain: the exe must open the browser VISIBLY.

Every side effect is injected, so the chain logic is unit-testable
without spawning real processes."""
import server as gui


def _boom(cmd, **kw):
    raise OSError('popen failed')


def test_windows_pops_via_cmd_start_first():
    calls = []

    def popen(cmd, **kw):
        calls.append(cmd)
        return object()

    res = gui.browser_open_chain('http://127.0.0.1:1/', popen=popen,
                                 startfile=lambda u: None,
                                 wb_open=lambda u: False, is_nt=True)
    assert res == 'cmd-start'
    assert calls[0][:3] == ['cmd', '/c', 'start']
    assert calls[0][-1] == 'http://127.0.0.1:1/'


def test_windows_falls_back_to_startfile():
    seen = []
    res = gui.browser_open_chain('http://u/', popen=_boom,
                                 startfile=lambda u: seen.append(u),
                                 wb_open=lambda u: False, is_nt=True)
    assert res == 'startfile'
    assert seen == ['http://u/']


def test_webbrowser_returning_false_means_failure():
    # webbrowser.open() reports False instead of raising -> keep falling
    res = gui.browser_open_chain('http://u/', popen=_boom,
                                 startfile=_boom_as_callable(),
                                 wb_open=lambda u: False, is_nt=True)
    assert res is None


def test_linux_uses_xdg_open():
    seen = []
    res = gui.browser_open_chain('http://u/', popen=lambda c, **kw: seen.append(c) or object(),
                                 startfile=None,
                                 wb_open=lambda u: False, is_nt=False)
    assert res == 'xdg-open'
    assert seen[0][0] == 'xdg-open'


def _boom_as_callable():
    def f(*a, **kw):
        raise OSError('nope')
    return f
