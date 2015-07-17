""" Measure Muffin application. """
import asyncio
import time
from urllib import parse

from muffin.plugins import BasePlugin, PluginException


# Package information
# ===================

__version__ = "0.0.1"
__project__ = "muffin-metrics"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


class Plugin(BasePlugin):

    """ Connect to Async Mongo. """

    name = 'metrics'
    defaults = {
        'backends': [],  # [(name, url)]
        'default': None,
        'fail_silently': False,
        'maxudpsize': 512,
        'prefix': 'muffin.',
    }

    def setup(self, app):
        """ Initialize Metrics Client. """
        super().setup(app)

        self.enabled = len(self.options.backends)

        self.default = self.options.default
        if not self.options.default and self.enabled:
            self.default = self.options.backends[0][0]

        self.backends_hash = {name: parse.urlparse(loc) for (name, loc) in self.options.backends}
        if self.default not in self.backends_hash:
            raise PluginException('Backend not found: %s' % self.default)

    @asyncio.coroutine
    def client(self, name=None):
        """ Initialize a backend's client. """
        name = name or self.default
        params = self.backends_hash[name]
        ccls = UDPClient if params.scheme == 'udp' else TCPClient
        return (yield from ccls(self, params.hostname, params.port).connect())

    def time(self):
        """ Create and return timer. """
        return Timer()

    @asyncio.coroutine
    def send(self, *messages, path='', backend=None):
        """ Send messages to backend. """
        client = yield from self.client(backend)
        if not client:
            return False
        client.send(*[
            message.encode('ascii') if isinstance(message, str) else message
            for message in messages
        ], path=path)
        client.disconnect()


class UDPClient:

    """ Send UDP data. """

    def __init__(self, plugin, hostname, port):
        """ Parse location. """
        self.parent = plugin
        self.prefix = b''
        if plugin.options.prefix:
            self.prefix = plugin.options.prefix.encode('ascii')
        self.hostname = hostname
        self.port = port
        self.transport = self.connected = None
        self.pipeline = None

    def __enter__(self):
        """ Enter to context. """
        self.pipeline = []
        return self

    def __exit__(self, typ, value, tb):
        """ Exit from context. """
        if value:
            raise
        self._send(*self.pipeline)
        self.disconnect()

    def prepare_message(self, message, path=b''):
        """ Prepare message. """
        if not isinstance(message, bytes):
            message = str(message).encode('ascii')

        ts = str(round(time.time())).encode('ascii')
        return b' '.join((self.prefix + path, message, ts))

    @asyncio.coroutine
    def connect(self):
        """ Connect to socket. """
        self.transport, _ = yield from self.parent.app.loop.create_datagram_endpoint(
            lambda: asyncio.DatagramProtocol(), remote_addr=(self.hostname, self.port))
        return self

    def disconnect(self):
        """ Disconnect from socket. """
        self.transport.close()
        self.transport = self.pipeline = None

    def send(self, *messages, path=''):
        """ Send message. """
        if isinstance(path, str):
            path = path.encode('ascii')

        messages = [self.prepare_message(message, path=path) for message in messages]

        if self.pipeline is None:
            return self._send(*messages)

        self.pipeline += messages

    def _send(self, *messages):
        """ Send message. """
        if not self.transport:
            return False

        messages = list(messages)
        data = b''
        while messages:
            message = messages.pop(0)
            if len(data + message) + 1 > self.parent.options.maxudpsize:
                self.transport.sendto(data)
                data = b''

            data += message + b'\n'

        if data:
            self.transport.sendto(data)


class TCPClient(UDPClient):

    """ Send TCP data. """

    @asyncio.coroutine
    def connect(self):
        """ Connect to socket. """
        try:
            _, self.transport = yield from asyncio.open_connection(
                self.hostname, self.port, loop=self.parent.app.loop)
        except OSError:
            if self.parent.options.fail_silently:
                return False
            raise
        return self

    def _send(self, *messages):
        """ Send messages. """
        if not self.transport:
            return False

        message = b'\n'.join(messages) + b'\n'
        self.transport.write(message)


class Timer:

    """ Measure timing. """

    def __init__(self):
        """ Initialize timer. """
        self.ms = None

    def __enter__(self):
        """ Enter to context. """
        self.ms = None
        self._start = time.time()
        return self

    def __exit__(self, typ, value, tb):
        """ Exit from context. """
        if value:
            raise
        dd = time.time() - self._start
        self.ms = int(round(1000 * dd))
        return self
