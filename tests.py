import asyncio
import time

import mock
import muffin
import pytest

import muffin_metrics


@pytest.fixture(scope='session')
def app(loop):
    app = muffin.Application(
        'metrics', loop=loop,

        PLUGINS=['muffin_metrics'],

        METRICS_BACKENDS=(
            ('statsd', 'udp+statsd://127.0.0.1:9999'),
            ('udp', 'udp://127.0.0.1:9999'),
            ('tcp', 'tcp://127.0.0.1:9999'),
        )
    )

    app.middlewares.append(muffin_metrics.statsd_middleware_factory)

    @app.register('/')
    def view(request):
        return 'OK'

    return app


def test_base(app, client):
    assert app.ps.metrics
    assert app.ps.metrics.default == 'statsd'


@pytest.mark.async
def test_transport(app, client):

    ts = int(time.time()) // 100

    transport = mock.MagicMock()

    @asyncio.coroutine
    def connect(client, *args, **kwargs):
        client.transport = transport
        return client

    with mock.patch.object(muffin_metrics.UDPClient, 'connect', connect):
        yield from app.ps.metrics.send('test.measure', 42, 'udp')
        assert transport.sendto.called
        assert transport.sendto.call_args[0][0].startswith(
            ('muffin.test.measure 42 %d' % ts).encode('ascii'))

    with mock.patch.object(muffin_metrics.TCPClient, 'connect', connect):
        yield from app.ps.metrics.send('test.measure', 21, backend='tcp')
        assert transport.write.called
        assert transport.write.call_args[0][0].startswith(
            ('muffin.test.measure 21 %d' % ts).encode('ascii'))

    with app.ps.metrics.time() as timer:
        yield from asyncio.sleep(.1)

    assert timer.ms

    with (yield from app.ps.metrics.client()) as client:
        client.send('test', '12345')
        client.send('test', '12345')
        client.send('test', '12345')
        client.send('test', '12345')

    assert not client.pipeline

    object.__setattr__(app.ps.metrics.cfg, 'fail_silently', True)
    yield from app.ps.metrics.send('test.measure', 21, backend='tcp')


@pytest.mark.async
def test_statsd(app, client):

    transport = mock.MagicMock()

    @asyncio.coroutine
    def connect(client, *args, **kwargs):
        client.transport = transport
        return client

    with mock.patch.object(muffin_metrics.UDPStatsdClient, 'connect', connect):
        client = yield from app.ps.metrics.client('statsd')
        assert isinstance(client, muffin_metrics.UDPStatsdClient)

        client.send('stats', 21)
        client.incr('count', 3)
        client.timing('run', 30)

    assert transport.sendto.call_count == 3
    assert transport.sendto.call_args_list[0][0][0] == b'muffin.stats:21\n'
    assert transport.sendto.call_args_list[1][0][0] == b'muffin.count:3|c\n'
    assert transport.sendto.call_args_list[2][0][0] == b'muffin.run:30|ms\n'


def test_statsd_middleware(client):
    transport = mock.MagicMock()

    @asyncio.coroutine
    def connect(client, *args, **kwargs):
        client.transport = transport
        return client

    with mock.patch.object(muffin_metrics.UDPStatsdClient, 'connect', connect):
        response = client.get('/')

    assert response.status_code == 200
    assert transport.sendto.call_args[0][0] == b'muffin.request.method.GET:1|c\nmuffin.response.time:0|ms\nmuffin.response.status.200:1|c\n' # noqa
