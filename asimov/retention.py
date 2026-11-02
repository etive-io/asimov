"""
Asset retention: what an analysis has produced, how big it is, and releasing
what nothing needs any more (#237).

Stage 0 is visibility: the size of the outputs of an analysis is recorded when
it finishes (``asimov analysis du``). Stage 1 is an explicit ``asimov analysis
prune``, which releases the outputs which their pipeline says may go once
consumed, and **only when nothing downstream can still need them**.

A pipeline says what may go. Its :meth:`~asimov.pipeline.Pipeline.output_paths`
names what it produced and ``output_retention`` (or, for the command pipeline,
a ``retention`` in the ``outputs:`` of the analysis) gives each output a policy:

``keep``
    Never released. This is what an output is unless it says otherwise, so
    nothing changes for a pipeline which does not say.
``until_consumed``
    May be released when everything which needs this analysis has finished, and
    at least one did. (An output which nothing consumed is not an intermediate.)

A release only ever removes something inside the run directory of the analysis
which made it, never the results store, never a symbolic link, and never from
an analysis which has not finished. Each one is recorded, with its size and
hash, on the analysis (``released``) and in the audit trail.

What may still need an output besides the analyses which exist:

* an analysis which is *not yet finished* and needs it (or may be run again);
* a growing group (:meth:`asimov.strategies.Strategy.extend`), whose later
  analyses do not exist yet. Its strategy says which analyses a later one may
  consume (:meth:`~asimov.strategies.Strategy.may_consume`); ``--done`` says
  the group will not grow any more.
"""
import hashlib
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from asimov import config
from asimov.audit import append_audit, new_record
from asimov.groups import Member, dependents, everything
from asimov.strategies import StrategyContext, read_group, strategy_plugins, strategy_stamp
from asimov.strategies import Strategy

KEEP = "keep"
UNTIL_CONSUMED = "until_consumed"
#: Reserved: copy to the results store, then release the working copy. Not
#: done yet, so it is treated as ``keep``.
STORE = "store"
POLICIES = frozenset({KEEP, UNTIL_CONSUMED, STORE})

#: In an analysis's metadata.
ASSETS_KEY = "assets"
RELEASED_KEY = "released"

#: An analysis whose dependents have all one of these has nothing left to wait for
#: (a skipped analysis will not consume anything).
SETTLED = frozenset({"finished", "complete", "uploaded", "skipped"})
FINISHED = frozenset({"finished", "complete", "uploaded"})

#: Files are hashed in blocks of this size, so a large one is not read into memory at once.
_BLOCK = 1 << 20


def enabled() -> bool:
    """Whether the project lets assets be released (``[retention] release``, true by default)."""
    try:
        value = config.get("retention", "release")
    except Exception:
        return True
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def human(size: Optional[int]) -> str:
    """A size in bytes as ``1.5 GB``."""
    if size is None:
        return "?"
    value = float(size)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} TB"


def policy_of(analysis, name: str) -> str:
    """The retention policy of one output of an analysis."""
    pipeline = getattr(analysis, "pipeline", None)
    try:
        value = pipeline.retention_of(name) if pipeline is not None else KEEP
    except Exception:
        return KEEP
    return value if value in POLICIES and value != STORE else KEEP


def output_paths(analysis) -> Dict[str, List[str]]:
    """What an analysis has produced, by name, as absolute paths which exist."""
    pipeline = getattr(analysis, "pipeline", None)
    if pipeline is None or not getattr(analysis, "rundir", None):
        return {}
    try:
        declared = pipeline.output_paths() or {}
    except Exception:
        return {}
    base = os.path.abspath(analysis.rundir)
    found: Dict[str, List[str]] = {}
    for name, value in declared.items():
        values = value if isinstance(value, (list, tuple)) else [value]
        paths = []
        for path in values:
            path = os.fspath(path)
            path = path if os.path.isabs(path) else os.path.join(base, path)
            if os.path.lexists(path):
                paths.append(path)
        if paths:
            found[str(name)] = paths
    return found


def size_of(path: str) -> Tuple[int, int]:
    """``(bytes, files)`` of a file, or of everything under a directory."""
    if os.path.islink(path) or os.path.isfile(path):
        try:
            return os.lstat(path).st_size, 1
        except OSError:
            return 0, 0
    total, count = 0, 0
    for here, _, names in os.walk(path):
        for name in names:
            try:
                total += os.lstat(os.path.join(here, name)).st_size
                count += 1
            except OSError:
                pass
    return total, count


def hash_of(path: str) -> Optional[str]:
    """The SHA-256 of a file (None for anything else, or if it cannot be read)."""
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(_BLOCK), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def record_sizes(analysis) -> Dict[str, dict]:
    """
    Record how big the outputs of an analysis are, in its metadata (``assets``).

    Called when an analysis finishes. Never raises: knowing the sizes is not
    worth stopping the monitor for.
    """
    try:
        found = {}
        for name, paths in output_paths(analysis).items():
            sizes = [size_of(path) for path in paths]
            found[name] = {"size": sum(s for s, _ in sizes), "files": sum(n for _, n in sizes)}
        if found:
            analysis.meta[ASSETS_KEY] = found
        return found
    except Exception:
        return {}


def recorded_size(analysis) -> int:
    """The total size recorded for the outputs of an analysis, in bytes."""
    assets = (getattr(analysis, "meta", None) or {}).get(ASSETS_KEY)
    if not isinstance(assets, dict):
        return 0
    return sum(int(a.get("size", 0) or 0) for a in assets.values() if isinstance(a, dict))


def released(analysis) -> List[dict]:
    """The releases recorded for an analysis."""
    found = (getattr(analysis, "meta", None) or {}).get(RELEASED_KEY)
    return found if isinstance(found, list) else []


def released_names(analysis) -> set:
    """The names of the outputs of an analysis which were released."""
    return {r.get("asset") for r in released(analysis) if isinstance(r, dict)}


def released_when(analysis, name: str) -> str:
    for record in released(analysis):
        if record.get("asset") == name:
            return f"{record.get('released', 'at some time')}, {human(record.get('size'))}"
    return "at some time"


def clear(analysis) -> None:
    """Forget the sizes and releases of an analysis, as when it is run again."""
    for key in (ASSETS_KEY, RELEASED_KEY):
        analysis.meta.pop(key, None)


@dataclass
class Item:
    """An output which may be released."""

    member: Member
    asset: str
    paths: List[str]
    size: int
    reason: str


@dataclass
class Plan:
    """What ``prune`` would do, and what it leaves and why."""

    items: List[Item] = field(default_factory=list)
    #: ``(analysis label, asset, why it stays)`` for outputs which would go if it were not for that.
    kept: List[Tuple[str, str, str]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(item.size for item in self.items)


def _store_root() -> Optional[str]:
    try:
        from asimov.context import resolve_path

        return os.path.realpath(resolve_path(config.get("storage", "results_store")))
    except Exception:
        return None


def _inside(path: str, directory: str) -> bool:
    """Whether a path is strictly inside a directory (not the directory itself)."""
    directory = os.path.join(os.path.realpath(directory), "")
    return os.path.realpath(path).startswith(directory)


def _overlap(a: str, b: str) -> bool:
    """Whether two paths are the same, or one is inside the other."""
    a, b = os.path.realpath(a), os.path.realpath(b)
    return a == b or _inside(a, b) or _inside(b, a)


def _may_consume(ledger, analysis, done: bool) -> bool:
    """
    Whether an analysis which a strategy made may yet be needed by one which
    the strategy has not made. False for one which no strategy made, and for
    every analysis of a group which is done; True if the strategy cannot be asked.
    """
    stamp = strategy_stamp(getattr(analysis, "meta", None) or {})
    if not stamp or done:
        return False
    plugin_class = strategy_plugins().get(stamp["type"])
    if plugin_class is None:
        # Not installed, or it failed to load: that says nothing about whether the
        # group will grow, so what it made is kept (--done overrides this).
        return True
    try:
        plugin = plugin_class()
        context = StrategyContext(
            ledger=ledger,
            event=getattr(getattr(analysis, "event", None), "name", None),
            group=read_group(ledger, stamp["id"]),
        )
        return bool(plugin.may_consume(analysis, context))
    except Exception:
        return True  # when in doubt, keep it


def plan(ledger, members: Optional[List[Member]] = None, scope: Optional[Iterable[Member]] = None, done: bool = False) -> Plan:
    """
    Work out what may be released.

    Parameters
    ----------
    ledger : Ledger
    members : list of Member, optional
        Every analysis in the project (read if not given); what depends on what
        is worked out from all of them, whatever the scope.
    scope : iterable of Member, optional
        Only release outputs of these analyses. Default: all.
    done : bool
        The groups in scope will not grow any more.
    """
    members = everything(ledger) if members is None else members
    by_key = {member.key: member for member in members}
    after = dependents(members)
    result = Plan()
    store = _store_root()
    # What may not be touched, from any analysis: a directory which holds a kept output,
    # or a second name for the same file, must not be released with its neighbour.
    protected = [
        (path, f"{m.label} {name}")
        for m in members
        for name, paths in output_paths(m.analysis).items()
        if policy_of(m.analysis, name) != UNTIL_CONSUMED
        for path in paths
    ]

    for member in (members if scope is None else list(scope)):
        analysis = member.analysis
        outputs = output_paths(analysis)
        already = released_names(analysis)
        for name, paths in outputs.items():
            if name in already or policy_of(analysis, name) != UNTIL_CONSUMED:
                continue
            label = member.label

            def keep(why):
                result.kept.append((label, name, why))

            if member.status not in FINISHED:
                keep(f"{label} has not finished")
                continue
            consumers = [by_key[key] for key in after.get(member.key, []) if key in by_key]
            if not consumers:
                keep("nothing has consumed it")
                continue
            waiting = [c.label for c in consumers if c.status not in SETTLED]
            if waiting:
                keep(f"{', '.join(waiting[:3])}{' ...' if len(waiting) > 3 else ''} still to finish")
                continue
            if _may_consume(ledger, analysis, done):
                keep("its strategy may still add analyses which consume it (--done says it will not)")
                continue
            unsafe = None
            for path in paths:
                if os.path.islink(path):
                    unsafe = "it is a symbolic link"
                elif not _inside(path, analysis.rundir):
                    unsafe = "it is outside the run directory"
                elif store and _overlap(path, store):
                    unsafe = "it is in the results store"
                else:
                    clash = next((who for other, who in protected if _overlap(path, other)), None)
                    if clash:
                        unsafe = f"it overlaps {clash}, which is kept"
                if unsafe:
                    break
            if unsafe:
                keep(unsafe)
                continue
            total = sum(size_of(path)[0] for path in paths)
            result.items.append(
                Item(
                    member,
                    name,
                    paths,
                    total,
                    f"{UNTIL_CONSUMED}: all {len(consumers)} analyses which need it have finished",
                )
            )
    return result


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _save(ledger, member: Member):
    if member.subject is None:
        ledger.update_analysis_in_project_analysis(member.analysis)
    else:
        ledger.update_event(member.analysis.event)


def release(ledger, items: List[Item]) -> List[dict]:
    """
    Release outputs: remove them, and record each (what, how big, its hash, why, when)
    on the analysis and in the audit trail.

    Each output is recorded as soon as it has been removed, in a transaction of its
    own, so that a failure part of the way through (a file which cannot be removed)
    does not lose the record of what was already gone. What was removed is
    recorded, a failure is reported once every output has been tried, and an output
    only some of whose files could be removed is recorded as released with the
    ones which were.

    Raises
    ------
    RuntimeError
        If the project does not allow it (``[retention] release = false``), or if
        something could not be removed (after all the rest has been done).
    """
    if not enabled():
        raise RuntimeError("Releasing assets is switched off for this project ([retention] release = false).")
    records, failures = [], []
    for item in items:
        analysis = item.member.analysis
        gone, hashes, freed, error = [], {}, 0, None
        for path in item.paths:
            size = size_of(path)[0]
            digest = hash_of(path)
            try:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                elif os.path.lexists(path):
                    os.remove(path)
            except OSError as problem:
                error = problem
                failures.append(f"{item.member.label} {item.asset}: {problem}")
                break
            gone.append(path)
            freed += size
            if digest:
                hashes[path] = digest
        if not gone:
            continue
        record = {
            "asset": item.asset,
            "paths": [os.path.relpath(p, analysis.rundir) for p in gone],
            "size": freed,
            "hash": hashes or None,
            "reason": item.reason,
            "released": _now(),
        }
        if error is not None:
            record["partial"] = True
        with ledger.transaction():
            current = analysis.meta.get(RELEASED_KEY)
            analysis.meta[RELEASED_KEY] = (current if isinstance(current, list) else []) + [record]
            _save(ledger, item.member)
            append_audit(
                ledger,
                new_record("release", "analysis", item.member.label, content=record, outcome="released"),
            )
        records.append(record)
    if failures:
        raise RuntimeError("Some outputs could not be released: " + "; ".join(failures))
    return records


def pruned_inputs(chosen: List[Member], members: List[Member]) -> List[Tuple[str, str, str]]:
    """
    What the analyses to be run again need which was released, from analyses
    which are not among them.

    Returns
    -------
    list of tuple
        ``(analysis which needs it, analysis which made it, asset)``.
    """
    chosen_keys = {m.key for m in chosen}
    problems = []
    for member in chosen:
        try:
            dependencies = member.analysis._dependency_analyses()
        except Exception:
            continue
        pipeline = member.analysis.pipeline
        try:
            wanted = set(pipeline.get_actual_inputs(member.analysis))
        except Exception:
            wanted = set()
        # A pipeline which declares its inputs (the command pipeline does) has told us what
        # it needs, which may be nothing. For one which does not, we do not know, so we
        # take it that it may need anything.
        declares = bool(getattr(pipeline, "declares_inputs", False))
        for dependency in dependencies:
            event = getattr(dependency, "event", None)
            if (getattr(event, "name", None), dependency.name) in chosen_keys:
                continue
            for name in sorted(released_names(dependency)):
                if name in wanted or not (declares or wanted):
                    provider = Member(dependency, getattr(event, "name", None)).label
                    problems.append((member.label, provider, name))
    return problems


def regenerate(chosen: List[Member], members: List[Member]) -> List[Member]:
    """
    ``chosen`` and the analyses which have to be run again to make what was
    released and is needed (and so, in turn, what those need).
    """
    by_label = {m.label: m for m in members}
    result = list(chosen)
    present = {m.key for m in result}
    for _ in range(len(members) + 1):
        added = False
        for _, provider, _ in pruned_inputs(result, members):
            member = by_label.get(provider)
            if member is not None and member.key not in present:
                result.append(member)
                present.add(member.key)
                added = True
        if not added:
            break
    return result
