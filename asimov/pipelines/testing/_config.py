"""
Configuration files for asimov's bundled testing pipelines.

A real pipeline is driven by a configuration file which asimov renders from
the pipeline's template, and the settings in it are the ones which matter: the
waveform approximant, the priors, the frequency range and so on. The testing
pipelines do no analysis, but they render a configuration file in the same way
so that end-to-end tests can check those settings reach the job:

* :data:`CONFIG_FILENAME` is copied into the run directory when the DAG is
  built, from where ``asimov manage build`` left it (or, if it has not been
  built that way, rendered there from the template);
* the job prints that file and the ledger dump (see :mod:`._dump`) to its
  standard output, so the job's output shows what it was given.

:class:`TemplateHelpers` gives the templates in ``asimov/configs`` a way to
read settings which may not be there, since a missing key is an error in a
Liquid template.
"""

import os
import shlex
import shutil

from ._dump import DUMP_FILENAME, _plain, _subject_name, encompassed_analyses

#: Name of the configuration file in each analysis's run directory.
CONFIG_FILENAME = "config.ini"

#: What a template shows for a setting the analysis does not have.
UNSET = "<not set>"


def built_config_path(production):
    """
    Where ``asimov manage build`` writes ``production``'s configuration.

    An analysis of a subject has its configuration committed to the subject's
    repository; a project analysis has it written under
    ``checkouts/project-analyses``.

    Returns
    -------
    str or None
        The path, or ``None`` if it cannot be worked out (for example if the
        subject has no repository).
    """
    subjects = getattr(production, "_subjects", None)
    if subjects:
        from asimov.analysis import subjects_dirname
        from asimov.context import resolve_path

        return resolve_path(
            os.path.join(
                "checkouts",
                "project-analyses",
                subjects_dirname(subjects),
                f"{production.name}.ini",
            )
        )
    try:
        repository = production.event.repository
        return repository.find_prods(production.name, production.category)[0]
    except Exception:  # no repository, or no subject: nothing was built there
        return None


def stage_config(production):
    """
    Put ``production``'s configuration into its run directory.

    The file ``asimov manage build`` made is copied if there is one, since it
    is what a real pipeline would read. Otherwise (the DAG is being built
    directly, as the unit tests do) it is rendered from the template now.

    Parameters
    ----------
    production : :class:`asimov.analysis.Analysis`

    Returns
    -------
    tuple of (str, str)
        The path of the staged file, and where it came from: the path it was
        copied from, or ``"rendered when the DAG was built"``.
    """
    destination = os.path.join(production.rundir, CONFIG_FILENAME)
    source = built_config_path(production)
    if source and os.path.exists(source):
        if os.path.abspath(source) != os.path.abspath(destination):
            shutil.copyfile(source, destination)
        return destination, source
    production.make_config(destination)
    return destination, "rendered when the DAG was built"


def _flatten(value, prefix=""):
    if isinstance(value, dict) and value:
        rows = []
        for key in sorted(value, key=str):
            name = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten(value[key], name))
        return rows
    return [(prefix, value)]


def job_report_lines(config_path, config_source, rundir):
    """
    Shell lines which print the configuration and the ledger dump.

    Every testing pipeline's job runs these first, so that its standard output
    shows what it was given, with each file between marker lines.

    Returns
    -------
    list of str
        Newline-terminated lines.
    """
    dump = os.path.join(rundir, DUMP_FILENAME)
    quote = shlex.quote
    return [
        f"echo '===== BEGIN {CONFIG_FILENAME} ====='\n",
        f"echo {quote(f'# source: {config_source}')}\n",
        f"cat {quote(str(config_path))}\n",
        f"echo '===== END {CONFIG_FILENAME} ====='\n",
        f"echo '===== BEGIN {DUMP_FILENAME} ====='\n",
        f"cat {quote(dump)}\n",
        f"echo '===== END {DUMP_FILENAME} ====='\n",
    ]


class TemplateHelpers:
    """
    Methods the testing pipelines' configuration templates call.

    The templates receive the pipeline as ``pipeline``, so these are used as,
    for example, ``{{ pipeline.setting("waveform", "approximant") }}``.
    """

    def setting(self, *keys):
        """
        The effective setting at ``keys``, or :data:`UNSET`.

        A dictionary (such as a per-detector minimum frequency) is shown as
        ``H1: 20, L1: 20``, and a list as comma-separated values.
        """
        value = self.production.meta
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return UNSET
            value = value[key]
        return _format(value)

    def settings_under(self, *keys):
        """
        Every setting below ``keys``, as ``(dotted name, value)`` pairs.

        Nested dictionaries are flattened, so the chirp mass prior's bounds
        come out as ``chirp mass.minimum`` and ``chirp mass.maximum``.
        """
        value = self.production.meta
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return []
            value = value[key]
        if not isinstance(value, dict):
            return []
        return [(name, _format(item)) for name, item in _flatten(_plain(value))]

    def all_settings(self):
        """Every effective setting of the analysis, flattened."""
        return [
            (name, _format(item))
            for name, item in _flatten(_plain(self.production.meta))
        ]

    def combined_analyses(self):
        """
        The analyses this analysis combines, as dictionaries with ``label``
        (``subject/name``), ``pipeline``, ``status`` and ``review``.
        """
        rows = []
        for analysis in encompassed_analyses(self.production):
            review = getattr(analysis, "review", None)
            rows.append(
                {
                    "label": f"{_subject_name(analysis)}/{analysis.name}",
                    "pipeline": getattr(analysis.pipeline, "name", analysis.pipeline),
                    "status": getattr(analysis, "status", None),
                    "review": getattr(review, "status", None) or "none",
                }
            )
        return rows


def _format(value):
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_format(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(_format(item) for item in value)
    if value is None:
        return UNSET
    return str(value)
