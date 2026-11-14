import gc
import os

from celery import Celery
from celery.signals import worker_process_init, worker_ready

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Every task, including @shared_task ones, derives from the beta guard, which
# skips tasks that contact connected services when FLOPPY_BETA_MODE is on and
# otherwise delegates unchanged.
app = Celery("floppy", task_cls="app.beta_mode:BetaGuardTask")

app.config_from_object("django.conf:settings", namespace="CELERY")

# The dedicated interactive worker only consumes the task modules listed in
# CELERY_IMPORTS. Avoid autodiscovering every background task and importer into
# that long-lived process. Background and combined workers retain the complete
# task registry.
if os.environ.get("FLOPPY_PROCESS_ROLE") != "interactive":
    app.autodiscover_tasks()


@worker_ready.connect
def _freeze_parent_image(**_kwargs):
    """Move this worker's imported image out of the garbage collector's reach.

    The prefork pool forks its children from this process, so whatever is
    imported here starts shared between them. Collection un-shares it: a pass
    writes to the header of every object it examines, and a written page stops
    being shared.

    Production measured every Python process in the container converging on
    the same ~30 MiB of still-shared memory after three hours, down from
    60-76 MiB. That it is the same floor for the interactive child, the web
    workers and the gunicorn master -- processes with nothing in common but a
    fork and a garbage collector -- is what identifies collection as the
    cause rather than any particular workload.

    Objects created after this point are still collected normally.
    """
    gc.collect()
    gc.freeze()


@worker_process_init.connect
def _freeze_child_image(**_kwargs):
    """Do the same in a pool child, for the pages it inherited.

    Freezing in the parent stops the parent from un-sharing them; this stops
    the child from doing it from its own side. Both are needed, and this also
    covers the children forked before the parent signalled ready.
    """
    gc.collect()
    gc.freeze()
