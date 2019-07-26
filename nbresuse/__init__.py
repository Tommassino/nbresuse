import psutil
from typing import Callable
from tornado import gen, ioloop
from notebook.notebookapp import NotebookApp


from prometheus_client import Gauge


TOTAL_MEMORY_USAGE = Gauge(
    'total_memory_usage',
    'counter for total memory usage',
    []
)

MAX_MEMORY_USAGE = Gauge(
    'max_memory_usage',
    'counter for max memory usage',
    []
)


class MetricsHandler(Callable[[], None]):
    def __init__(self, nbapp: NotebookApp):
        self.session_manager = nbapp.session_manager

    @gen.coroutine
    def __call__(self, *args, **kwargs):
        self.overall_metrics()

    def overall_metrics(self):
        """
        Calculate and publish the notebook memory metrics
        """
        cur_process = psutil.Process()
        all_processes = [cur_process] + cur_process.children(recursive=True)
        rss = sum([p.memory_info().rss for p in all_processes])

        TOTAL_MEMORY_USAGE.set(rss)

        virtual_memory = psutil.virtual_memory()
        MAX_MEMORY_USAGE.set(virtual_memory.total)


def _jupyter_server_extension_paths():
    """
    Set up the server extension for collecting metrics
    """
    return [{
        'module': 'nbresuse',
    }]


def _jupyter_nbextension_paths():
    """
    Set up the notebook extension for displaying metrics
    """
    return [{
        "section": "notebook",
        "dest": "nbresuse",
        "src": "static",
        "require": "nbresuse/main"
    }]


def load_jupyter_server_extension(nbapp: NotebookApp):
    """
    Called during notebook start
    """
    callback = ioloop.PeriodicCallback(MetricsHandler(nbapp), 1000)
    callback.start()

