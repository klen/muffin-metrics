import muffin
import pytest
import asyncio
import mock


@pytest.fixture(scope='session')
def app(loop):
    app = muffin.Application(
        'metrics', loop=loop,

        PLUGINS=['muffin_metrics'],

        METRICS_BACKENDS=(
            ('udp', 'udp://127.0.0.1:9999'),
            ('tcp', 'tcp://127.0.0.1:9999'),
        )
    )

    @app.register('/')
    def view(request):
        return 'OK'

    return app


def test_base(app, client):
    assert app.ps.metrics
    assert app.ps.metrics.default == 'udp'


@pytest.mark.async
def test_transport(app, client):
    import muffin_metrics
    import time

    ts = int(time.time()) // 100

    transport = mock.MagicMock()

    @asyncio.coroutine
    def connect(client, *args, **kwargs):
        client.transport = transport
        return client

    with mock.patch.object(muffin_metrics.UDPClient, 'connect', connect):
        yield from app.ps.metrics.send(42, path='test.measure')
        assert transport.sendto.called
        assert transport.sendto.call_args[0][0].startswith(
            ('muffin.test.measure 42 %d' % ts).encode('ascii'))

    with mock.patch.object(muffin_metrics.TCPClient, 'connect', connect):
        yield from app.ps.metrics.send(21, path='test.measure', backend='tcp')
        assert transport.write.called
        assert transport.write.call_args[0][0].startswith(
            ('muffin.test.measure 21 %d' % ts).encode('ascii'))

    with app.ps.metrics.time() as timer:
        yield from asyncio.sleep(.1)

    assert timer.ms

    with (yield from app.ps.metrics.client()) as client:
        client.send('12345')
        client.send('12345')
        client.send('12345')
        client.send('12345')

    assert not client.pipeline

    object.__setattr__(app.ps.metrics.cfg, 'fail_silently', True)
    yield from app.ps.metrics.send(21, path='test.measure', backend='tcp')
