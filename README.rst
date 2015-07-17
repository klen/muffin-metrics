Muffin-Metrics
##############

.. _description:

Muffin-Metrics -- Send data to Graphite from Muffin application.

.. _badges:

.. image:: http://img.shields.io/travis/klen/muffin-metrics.svg?style=flat-square
    :target: http://travis-ci.org/klen/muffin-metrics
    :alt: Build Status

.. image:: http://img.shields.io/pypi/v/muffin-metrics.svg?style=flat-square
    :target: https://pypi.python.org/pypi/muffin-metrics

.. image:: http://img.shields.io/pypi/dm/muffin-metrics.svg?style=flat-square
    :target: https://pypi.python.org/pypi/muffin-metrics

.. image:: http://img.shields.io/gratipay/klen.svg?style=flat-square
    :target: https://www.gratipay.com/klen/
    :alt: Donate

.. _contents:

.. contents::

.. _requirements:

Requirements
=============

- python >= 3.3

.. _installation:

Installation
=============

**Muffin-Metrics** should be installed using pip: ::

    pip install muffin-metrics

.. _usage:

Usage
=====

Add **muffin_metrics** to **PLUGINS** in your Muffin Application configuration.

Options
-------

**METRICS_BACKENDS** -- Graphite backends in format ([]) ::

    METRICS_BACKENDS = (
        ('udp': 'udp://address:port'),
        ('tcp': 'tcp://address:port'),
    )
    METRICS_DEFAULT = 'udp'


**METRICS_DEFAULT**  -- Default backend (None)

**METRICS_FAIL_SILENTLY** -- Don't raise connection's exceptions (False)

**METRICS_MAXUDPSIZE** -- Max size of UDP message (512)

**METRICS_PREFIX** -- Prefix for metrics (muffin.)

Usage
-----

.. code:: python

    @app.register('/my')
    def my_view(request):
        # Context manager (group metrics to pipeline and send them as one message)
        with (yield from app.ps.metrics.client()) as metrics:
            metrics.send(42, path='answer.to.the.ultimate.question')
            # ...
            metrics.send(31, path='some.some')

        # Send data
        yield from app.ps.metrics.send(100, path='one.hungred', backend='mybackend')

        # Create client and send data
        metrics = yield from app.ps.metrics.client(backend='tcp')
        metrics.send(24, path='twenty.four')
        metrics.disconnect()


.. _bugtracker:

Bug tracker
===========

If you have any suggestions, bug reports or
annoyances please report them to the issue tracker
at https://github.com/klen/muffin-metrics/issues

.. _contributing:

Contributing
============

Development of Muffin-Metrics happens at: https://github.com/klen/muffin-metrics


Contributors
=============

* klen_ (Kirill Klenov)

.. _license:

License
=======

Licensed under a `MIT license`_.

.. _links:


.. _klen: https://github.com/klen

.. _MIT license: http://opensource.org/licenses/MIT
