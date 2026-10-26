"""
A built-in pipeline which runs a command (#236).

An analysis which has a ``command`` and no ``pipeline`` uses this one, and
``pipeline: command`` selects it explicitly::

    kind: analysis
    name: fit-r003
    command: [gwaith_fit_sine, --data-file, "{inputs.input_data}", --output, "{outputs.signal}"]
    outputs:
      signal: round_003_signal.hdf
    needs:
      - prep-r002

``{inputs.NAME}`` is filled in from the assets of the analyses this one needs,
and ``{outputs.NAME}`` is where the command should write what it declares. The
command is run in the run directory by the scheduler the project is configured
to use, and is complete when what it declared exists.

Because the command comes from the ledger, what is allowed to run is up to the
project's configuration (see :func:`command_allowed`).
"""
import fnmatch
import os
import re
import shlex
import stat
from configparser import NoOptionError, NoSectionError

from asimov import config
from asimov.pipeline import Pipeline, PipelineException
from asimov.scheduler import JobDescription

#: ``{inputs.NAME}``, ``{inputs.NAME.LABEL}`` and ``{outputs.NAME}``. A name
#: may have spaces (``xml psds``) but not braces or dots.
PLACEHOLDER = re.compile(r"\{(inputs|outputs)\.([^{}.]+)(?:\.([^{}.]+))?\}")

#: The section of the project's configuration which controls this pipeline.
CONFIG_SECTION = "pipelines.command"

#: What the wrapper script writes when the command has run: its exit status.
EXIT_STATUS_FILE = ".asimov-exit-status"


class CommandError(PipelineException):
    """The command of an analysis cannot be built or run."""


class CommandNotAllowed(CommandError):
    """The project's configuration does not allow this command to run."""


def _option(key, fallback=None):
    try:
        return config.get(CONFIG_SECTION, key)
    except (NoSectionError, NoOptionError, KeyError):
        return fallback


def command_allowed(executable):
    """
    Whether the project's configuration lets this executable be run.

    The command pipeline is **off unless the project turns it on**, because the
    command comes from the ledger and so lets whoever writes a blueprint run
    anything as the account which submits jobs. ``asimov init`` turns it on in
    a new project's own configuration, where the person who can write blueprints
    can already run anything from a shell; an instance which serves other
    people leaves it off, or lists what may be run::

        [pipelines.command]
        enabled = true
        allowed_executables = gwaith_*, python

    ``allowed_executables`` are patterns (``*`` and ``?``) for the executable
    exactly as the command gives it, so ``python`` allows ``python`` found on the
    ``PATH`` and not ``/tmp/other/python``. Without it, any executable is allowed.

    Parameters
    ----------
    executable : str
        The first word of the command.

    Raises
    ------
    CommandNotAllowed
        If it may not be run.
    """
    if str(_option("enabled", "false")).strip().lower() not in {"1", "true", "yes", "on"}:
        raise CommandNotAllowed(
            "The command pipeline is not enabled for this project. Set "
            f"'enabled = true' in the [{CONFIG_SECTION}] section of its asimov.conf to allow it."
        )
    patterns = [p.strip() for p in str(_option("allowed_executables", "")).split(",") if p.strip()]
    if patterns and not any(fnmatch.fnmatchcase(executable, p) for p in patterns):
        raise CommandNotAllowed(
            f"'{executable}' may not be run: [{CONFIG_SECTION}] allowed_executables "
            f"is {', '.join(patterns)}."
        )


def asset_paths(value):
    """
    The paths in the value of an asset.

    A pipeline's assets are most often a path, but may be a list of them, or a
    mapping from a label (an interferometer, say) to either, as the ``frames``,
    ``psds`` and ``calibration`` of ``asimov-gwdata`` are.

    Returns
    -------
    list of str
        In order; for a mapping, in the order of its sorted labels.
    """
    if value is None:
        return []
    if isinstance(value, (str, os.PathLike)):
        return [os.fspath(value)]
    if isinstance(value, dict):
        return [path for label in sorted(value) for path in asset_paths(value[label])]
    if isinstance(value, (list, tuple)):
        return [path for item in value for path in asset_paths(item)]
    return [str(value)]


class CommandPipeline(Pipeline):
    """
    Run the command which an analysis declares.

    Subclass this for a tool whose inputs, outputs and options are known, so
    that an analysis does not have to say them: override :meth:`command_template`
    (and set :attr:`arbitrary_command` to False, since the executable is then
    fixed by the class and not by the ledger), :meth:`output_specs` and
    :meth:`input_names`, and, for a stricter check than the existence of the
    outputs, :meth:`command_succeeded`. Submission, completion, logs and assets
    are inherited.
    """

    name = "command"

    #: Whether the command comes from the ledger, and so is subject to the
    #: project's configuration. A subclass which fixes the executable sets False.
    arbitrary_command = True

    #: The status of an analysis whose command has completed. A subclass which
    #: has post-processing sets ``"finished"``.
    final_status = "complete"

    # What the command reads and writes

    def command_template(self):
        """
        The command, as a list of words, with its placeholders not yet filled in.
        """
        command = self.production.meta.get("command")
        if isinstance(command, str):
            command = shlex.split(command)
        if not isinstance(command, (list, tuple)) or not command:
            raise CommandError(
                f"{self.production.name} has no command to run: give 'command' as a list "
                "of words, like [gwaith_fit, --output, '{outputs.result}']."
            )
        return [str(word) for word in command]

    def output_specs(self):
        """
        What the command writes, as ``{name: {"path": ..., ...}}``.

        An output is declared as a path (relative to the run directory), or as
        a mapping with a ``path`` and, in time, other attributes.
        """
        specs = {}
        for name, spec in (self.production.meta.get("outputs") or {}).items():
            if isinstance(spec, dict):
                spec = dict(spec)
            else:
                spec = {"path": spec}
            if not spec.get("path"):
                raise CommandError(f"The output '{name}' of {self.production.name} has no path.")
            specs[str(name)] = spec
        return specs

    def input_names(self):
        """The products which the command takes from the analyses it needs."""
        names = []
        for word in self.command_template():
            for kind, name, _ in PLACEHOLDER.findall(word):
                if kind == "inputs" and name not in names:
                    names.append(name)
        return names

    # The declarations asimov reads (#94)

    def get_actual_outputs(self, production):
        declared = list(super().get_actual_outputs(production))
        try:
            return sorted(set(declared) | set(self.output_specs()))
        except CommandError as error:
            self.logger.warning(str(error))
            return declared

    def get_actual_inputs(self, production):
        declared = list(super().get_actual_inputs(production))
        try:
            return sorted(set(declared) | set(self.input_names()))
        except CommandError as error:
            self.logger.warning(str(error))
            return declared

    def run_directory(self):
        if not self.production.rundir:
            raise CommandError(f"{self.production.name} has no run directory to run in.")
        return os.path.abspath(self.production.rundir)

    def output_path(self, name):
        """Where an output is, as an absolute path."""
        path = self.output_specs()[name]["path"]
        return path if os.path.isabs(path) else os.path.join(self.run_directory(), path)

    # Filling in the placeholders

    def _providers(self):
        """``(name, assets)`` for each analysis this one needs, in order."""
        providers = []
        for dependency in self.production.dependency_objects:
            try:
                assets = dependency.pipeline.collect_assets() or {}
            except Exception as error:
                self.logger.warning(
                    f"Could not collect the assets of {dependency.name}: {error}"
                )
                assets = {}
            providers.append((self.production._qualified_name(dependency), assets))
        return providers

    def _values(self, kind, name, label, providers):
        if kind == "outputs":
            if name not in self.output_specs():
                raise CommandError(
                    f"{self.production.name} uses {{outputs.{name}}} but declares no output "
                    f"called '{name}'."
                )
            if label:
                raise CommandError(f"{{outputs.{name}.{label}}}: an output has no labels.")
            return [self.output_path(name)]

        found = []
        for _, assets in providers:
            value = assets.get(name)
            if value in (None, {}, [], ""):
                continue
            if label:
                value = value.get(label) if isinstance(value, dict) else None
            found.extend(asset_paths(value))
        if not found:
            where = f"{{inputs.{name}.{label}}}" if label else f"{{inputs.{name}}}"
            needs = ", ".join(n for n, _ in providers) or "nothing"
            raise CommandError(
                f"{self.production.name} uses {where} but no analysis it needs provides it "
                f"(it needs: {needs})."
            )
        return found

    def resolve_command(self):
        """
        The command, with its placeholders filled in, as a list of words.

        A word which is only a placeholder becomes as many words as there are
        paths. Inside a longer word it must be a single path. The executable
        (the first word) is never a placeholder, so what is run cannot depend on
        what another analysis produced.
        """
        template = self.command_template()
        if PLACEHOLDER.search(template[0]):
            raise CommandError("The first word of a command, the executable, cannot be a placeholder.")
        providers = self._providers()
        words = []
        for word in template:
            whole = PLACEHOLDER.fullmatch(word)
            if whole:
                words.extend(self._values(*whole.groups(), providers))
                continue

            def fill(match):
                values = self._values(*match.groups(), providers)
                if len(values) != 1:
                    raise CommandError(
                        f"{match.group(0)} is {len(values)} paths and is part of a longer word "
                        f"({word}): use it as a word of its own."
                    )
                return values[0]

            words.append(PLACEHOLDER.sub(fill, word))
        return words

    # Building and submitting

    def _check_allowed(self, template):
        if self.arbitrary_command:
            command_allowed(template[0])

    def build_dag(self, user=None, dryrun=False):
        """
        Check that the command may run, fill in its placeholders, and write the
        script which runs it.

        Raises
        ------
        CommandNotAllowed
            If the project's configuration does not allow the command.
        CommandError
            If it cannot be built, for instance because an input is not provided.
        """
        self._check_allowed(self.command_template())
        command = self.resolve_command()
        if dryrun:
            self.logger.info(f"Dry run: would run {shlex.join(command)}")
            return command

        rundir = self.run_directory()
        os.makedirs(rundir, exist_ok=True)
        script = os.path.join(rundir, "command.sh")
        with open(script, "w") as handle:
            handle.write("#!/bin/bash\n")
            handle.write(f"# The command of {self.production.event.name}/{self.production.name}, written by asimov.\n")
            handle.write(f"cd {shlex.quote(rundir)} || exit 1\n")
            handle.write(f"rm -f {EXIT_STATUS_FILE}\n")
            handle.write(shlex.join(command) + "\n")
            handle.write("status=$?\n")
            handle.write(f"echo $status > {EXIT_STATUS_FILE}\n")
            handle.write("exit $status\n")
        os.chmod(script, os.stat(script).st_mode | stat.S_IXUSR)
        self.logger.info(f"Built {script}: {shlex.join(command)}")
        return command

    def _resources(self):
        """The resources the analysis asks the scheduler for."""
        asked = self.production.meta.get("scheduler", {}) or {}
        resources = {}
        for generic in ("cpus", "memory", "disk", "gpus"):
            for spelling in (f"request {generic}", f"request_{generic}", generic):
                if asked.get(spelling) is not None:
                    resources[generic] = asked[spelling]
                    break
        accounting = asked.get("accounting group") or asked.get("accounting_group")
        if accounting:
            resources["accounting_group"] = accounting
        return resources

    def submit_dag(self, dryrun=False):
        """
        Submit the command to the project's scheduler.

        Returns
        -------
        int
            The identifier the scheduler gave the job.
        """
        command = self.build_dag(dryrun=dryrun)
        self.before_submit(dryrun=dryrun)
        if dryrun:
            return 12345

        rundir = self.run_directory()
        name = self.production.name
        job = JobDescription(
            executable=os.path.join(rundir, "command.sh"),
            output=os.path.join(rundir, f"{name}.out"),
            error=os.path.join(rundir, f"{name}.err"),
            log=os.path.join(rundir, f"{name}.log"),
            batch_name=f"command/{self.production.event.name}/{name}",
            **self._resources(),
        )
        original = os.getcwd()
        os.chdir(rundir)
        try:
            job_id = self.scheduler.submit(job)
        finally:
            os.chdir(original)
        self.logger.info(f"Submitted {shlex.join(command)} as {job_id}")
        return job_id

    # Knowing how it went

    def exit_status(self):
        """The exit status of the command, or None if it has not finished."""
        path = os.path.join(self.run_directory(), EXIT_STATUS_FILE)
        try:
            with open(path) as handle:
                return int(handle.read().strip())
        except (OSError, ValueError):
            return None

    def command_succeeded(self):
        """
        Whether the command ran successfully, as far as asimov can tell.

        Override this for a stricter check than the existence of the outputs.
        """
        return True

    def detect_completion(self):
        """
        True when the command did not fail, what it declared exists, and (if
        it declares nothing) it is known to have finished.
        """
        if not self.production.rundir:
            return False
        status = self.exit_status()
        if status not in (None, 0):
            return False
        outputs = self.output_specs()
        if not outputs and status is None:
            return False
        if not all(os.path.exists(self.output_path(name)) for name in outputs):
            return False
        return bool(self.command_succeeded())

    def resurrect(self):
        """
        Report a command which failed, rather than leave it looking as if it were
        still running. (One that has vanished without a trace is left alone: the
        scheduler may still have it.)
        """
        status = self.exit_status()
        if status not in (None, 0):
            raise CommandError(
                f"The command of {self.production.name} exited with status {status}; "
                f"see {self.production.name}.err in its run directory."
            )

    def after_completion(self):
        self.production.status = self.final_status

    def collect_assets(self):
        """
        The outputs which exist, as ``{name: absolute path}``.
        """
        if not self.production.rundir:
            return {}
        return {
            name: self.output_path(name)
            for name in self.output_specs()
            if os.path.exists(self.output_path(name))
        }
