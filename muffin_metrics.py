""" Measure Muffin application. """
from asyncio import coroutine, DatagramProtocol, open_connection
from time import time
from urllib import parse
from random import random

from muffin.plugins import BasePlugin, PluginException


# Package information
# ===================

__version__ = "0.1.0"
__project__ = "muffin-metrics"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


@coroutine
def statsd_middleware_factory(app, handler):
    """Measure application params with statsd."""
    @coroutine
    def middleware(request):
        """Send results to statsd."""
        with Timer() as timer:
            response = yield from handler(request)

        with (yield from app.ps.metrics.client()) as client:
            client.incr('request.method.%s' % request.method)
            client.timing('response.time', timer.ms)
            client.incr('response.status.%s' % response.status)

        return response

    return middleware


class Plugin(BasePlugin):

    """ Connect to Async Mongo. """

    name = 'metrics'
    defaults = {
        'backends': [],  # [(name, url, (graphite|statsd)]
        'default': None,
        'fail_silently': False,
        'maxudpsize': 512,
        'prefix': 'muffin.',
    }

    def setup(self, app):
        """Parse and prepare the plugin's configuration."""
        super().setup(app)

        self.enabled = len(self.cfg.backends)

        self.default = self.cfg.default
        if not self.cfg.default and self.enabled:
            self.default = self.cfg.backends[0][0]

        self.backends_hash = {name: parse.urlparse(loc) for (name, loc) in self.cfg.backends}
        self.backends_schemas = {
            'tcp': TCPClient,
            'udp': UDPClient,
            'tcp+statsd': TCPStatsdClient,
            'udp+statsd': UDPStatsdClient,
        }
        if self.default not in self.backends_hash:
            raise PluginException('Backend not found: %s' % self.default)

    @coroutine
    def client(self, name=None):
        """Initialize a backend's client with given name or default."""
        name = name or self.default
        params = self.backends_hash[name]
        ccls = self.backends_schemas.get(params.scheme, TCPClient)
        return (yield from ccls(self, params.hostname, params.port).connect())

    def time(self):
        """Create and return a simple timer."""
        return Timer()

    @coroutine
    def send(self, stat, value, backend=None):
        """Send stat to backend."""
        client = yield from self.client(backend)
        if not client:
            return False
        client.send(stat, value)
        client.disconnect()


class AbstractClient:

    """Send metrics to backend."""

    def __init__(self, plugin, hostname, port):
        """Parse location."""
        self.parent = plugin
        self.prefix = plugin.cfg.prefix or ''
        self.hostname = hostname
        self.port = port
        self.transport = self.connected = None
        self.pipeline = None

    def __enter__(self):
        """Enter to context."""
        self.pipeline = []
        return self

    def __exit__(self, typ, value, tb):
        """Exit from context."""
        if value:
            raise
        self._send(*self.pipeline)
        self.disconnect()

    def connect(self):
        """ Connect to socket. """
        raise NotImplemented()

    def disconnect(self):
        """Disconnect from the socket."""
        self.transport.close()
        self.transport = self.pipeline = None

    def build_message(self, stat, value):
        """Build a metric in Graphite format."""
        return ' '.join((self.prefix + str(stat), str(value), str(round(time()))))

    def send(self, stat, value, rate=1):
        """Send message to backend."""
        if rate < 1 and random() > rate:
            return

        message = self.build_message(stat, value)
        if not message:
            return

        if self.pipeline is None:
            return self._send(message)

        self.pipeline.append(message)

    def _send(self, *messages):
        """Send message."""
        raise NotImplemented()


class UDPClient(AbstractClient):

    """Send messages to graphite backend by UDP."""

    @coroutine
    def connect(self):
        """Connect to socket."""
        self.transport, _ = yield from self.parent.app.loop.create_datagram_endpoint(
            lambda: DatagramProtocol(), remote_addr=(self.hostname, self.port))
        return self

    def _send(self, *messages):
        """Send message."""
        if not self.transport:
            return False

        messages = [message.encode('ascii') for message in messages]
        data = b''
        while messages:
            message = messages.pop(0)
            if len(data + message) + 1 > self.parent.cfg.maxudpsize:
                self.transport.sendto(data)
                data = b''

            data += message + b'\n'

        if data:
            self.transport.sendto(data)


class TCPClient(AbstractClient):

    """Send messages to graphite backend by TCP."""

    @coroutine
    def connect(self):
        """Connect to socket."""
        try:
            _, self.transport = yield from open_connection(
                self.hostname, self.port, loop=self.parent.app.loop)
        except OSError:
            if self.parent.cfg.fail_silently:
                return False
            raise
        return self

    def _send(self, *messages):
        """Send messages."""
        if not self.transport:
            return False

        message = '\n'.join(messages) + '\n'
        self.transport.write(message.encode('ascii'))


class StatsDMixin:

    """Send messages to StatsD backend."""

    def incr(self, stat, count=1, rate=1):
        """Increment a stat by `count`."""
        return self.send(stat, "%s|c" % count, rate)

    def decr(self, stat, count=1, rate=1):
        """Decrement a stat by `count`."""
        return self.incr(stat, -count, rate)

    def timing(self, stat, delta, rate=1):
        """Send new timing information. `delta` is in milliseconds."""
        return self.send(stat, "%d|ms" % delta, rate)

    def gauge(self, stat, value, rate=1):
        """Set a gauge value."""
        return self.send(stat, "%s|g" % value)

    def send(self, stat, value, rate=1):
        """Send message to backend."""
        if rate < 1:
            value = "%s|@%s" % (value, rate)
        return super().send(stat, value, rate)

    def build_message(self, stat, value):
        """Build metric for StatsD."""
        return "%s%s:%s" % (self.prefix, stat, value)


class UDPStatsdClient(StatsDMixin, UDPClient):

    """ Support StatsD with UDP. """


class TCPStatsdClient(StatsDMixin, TCPClient):

    """ Support StatsD with TCP. """


class Timer:

    """Measure timing."""

    def __init__(self):
        """Initialize timer."""
        self.ms = None

    def __enter__(self):
        """Enter to context."""
        self.ms = None
        self._start = time()
        return self

    def __exit__(self, typ, value, tb):
        """Exit from context."""
        if value:
            raise
        dd = time() - self._start
        self.ms = int(round(1000 * dd))
        return self
