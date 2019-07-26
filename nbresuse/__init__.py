import psutil
from typing import Callable
from tornado import gen, ioloop
from notebook.utils import maybe_future
from notebook.notebookapp import NotebookApp
from psutil import process_iter, AccessDenied, NoSuchProcess


from prometheus_client import Gauge

KERNEL_MEMORY_USAGE = Gauge(
    'kernel_memory_usage',
    'counter for kernel memory usage',
    ['kernel_id']
)

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
        yield self.kernel_metrics()
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

    @gen.coroutine
    def kernel_metrics(self):
        kernels = yield maybe_future(self._list_kernel_memory())
        for kernel_id, data in kernels.items():
            KERNEL_MEMORY_USAGE.labels(
                kernel_id=kernel_id
            ).set(data['rss'])

    @gen.coroutine
    def _list_kernel_memory(self):
        kernel_memory = dict()

        session_manager = self.session_manager
        sessions = yield maybe_future(session_manager.list_sessions())
        kernel_processes = self._kernel_processes()

        def find_process(session_id):
            for proc in kernel_processes:
                cmd = proc.cmdline()
                if cmd:
                    last_arg = cmd[-1]
                    if session_id in last_arg:
                        return proc
            return None

        for session in sessions:
            kernel = session['kernel']
            kernel_id = kernel['id']
            kernel_process = find_process(kernel_id)
            if kernel_process:
                mem_info = kernel_process.memory_full_info()
                kernel_memory[kernel_id] = mem_info._asdict()

        raise gen.Return(kernel_memory)

    def _kernel_processes(self):
        for proc in process_iter():
            try:
                if 'ipykernel_launcher' in proc.cmdline():
                    yield proc
            except (AccessDenied, NoSuchProcess, OSError):
                pass


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

