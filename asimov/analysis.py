"""
Code to handle the various kinds of analysis which asimov can handle.

Asimov defintes three types of analysis, depending on the inputs of the analysis.

Simple analyses
  These analyses operate only on a single event,
  and will generally use a very specific set of configuration settings.
  An example of a simple analysis is a bilby or RIFT parameter estimation analysis,
  as these only require access to the data for a single event.
  Before version 0.4 these were called `Productions`.

Event analyses
  These analyses can access the results of all of the simple analyses which have been
  performed on a single event, or a subset of them.
  An example of an event analysis is the production of mixed posterior samples from multiple
  PE analyses.

Project analyses
  These are the most general type of analysis, and have access to the results of all analyses
  on all events, including event and simple analyses.
  This type of analysis is useful for defining a population analysis or analysing multiple events together, for example.

"""

import os
import configparser
from copy import deepcopy
import pathlib

from functools import reduce
import operator
from typing import TYPE_CHECKING, Any, Optional, List, cast

from liquid import Liquid

from . import config, logger, LOGGER_LEVEL
from .pipelines import known_pipelines
from .utils import update, diff_dict
from .storage import Store

from .review import Review
from .ini import RunConfiguration

status_map = {
    "cancelled": "light",
    "finished": "success",
    "uploaded": "success",
    "processing": "primary",
    "running": "primary",
    "stuck": "warning",
    "restart": "secondary",
    "ready": "secondary",
    "wait": "light",
    "stop": "danger",
    "manual": "light",
    "stopped": "light",
}

review_map = {
    "deprecated": "warning",
    "none": "default",
    "approved": "success",
    "rejected": "danger",
    "checked": "info",
}


class Analysis:
    """
    The base class for all other types of analysis.
    """

    meta: dict[str, Any] = {}
    meta_defaults: dict[str, Any] = {"scheduler": {}, "sampler": {}, "likelihood": {}}

    # These annotations help static analysis without affecting runtime state
    if TYPE_CHECKING:
        event: Any
        subject: Any
        name: str
        pipeline: Any
        comment: Optional[str]
        _needs: List[Any]
        _reviews: Review
        status_str: str
        repository: Any
        ledger: Any
        analyses: List[Any]
        productions: List[Any]
        _analysis_spec: Any

    @property
    def review(self):
        """
        Return the review information attached to the analysis.
        """
        if "review" in self.meta:
            if len(self.meta["review"]) > 0:
                self._reviews = Review.from_dict(self.meta["review"], production=self)
            # Always remove 'review' from meta since we manage it via _reviews
            self.meta.pop("review")
        return self._reviews

    def _process_dependencies(self, needs):
        """
        Process the dependencies list for this production.

        The dependencies can be provided either as the name of a production,
        or a query against the analysis's attributes.

        The needs list supports complex dependency specifications:
        - Simple name: "Prod1" matches analysis with name "Prod1"
        - Property query: "waveform.approximant: IMRPhenomXPHM" matches analyses
          with that waveform approximant
        - Negation: "review.status: !approved" matches analyses that are NOT approved
        - Nested lists for AND logic: [["review.status: approved", "waveform.approximant: IMRPhenomXPHM"]]
          matches analyses that satisfy ALL conditions in the nested list
        - Top-level items are OR'd together
        - Optional dependencies: {"optional": true, "pipeline": "bilby"} marks dependency as optional

        Parameters
        ----------
        needs : list
           A list of all the requirements. Can contain strings (OR'd together),
           or lists of strings (AND'd together internally, OR'd with other items),
           or dicts with optional flag

        Returns
        -------
        list
           A list of all the requirements processed for evaluation.
           Each item is either a tuple (attribute, match, negate, optional) for simple filters,
           or a list of tuples for AND groups.
        """
        all_requirements = []
        for need in deepcopy(needs):
            # Check if this is an AND group (list of conditions)
            if isinstance(need, list):
                and_group = []
                for condition in need:
                    and_group.append(self._parse_single_dependency(condition))
                all_requirements.append(and_group)
            else:
                # Single condition
                all_requirements.append(self._parse_single_dependency(need))
        return all_requirements
    
    def _parse_single_dependency(self, need):
        """
        Parse a single dependency specification into (attribute, match, negate, optional) tuple.
        
        Handles multiple formats:
        - String: "waveform.approximant: IMRPhenomXPHM" (with quotes in YAML)
        - Dict (simple): {waveform.approximant: IMRPhenomXPHM} (without quotes in YAML)
        - Dict (optional): {optional: true, pipeline: bilby} (marks dependency as optional)
        
        Parameters
        ----------
        need : str or dict
            A single dependency specification
            
        Returns
        -------
        tuple
            (attribute_list, match_value, is_negated, is_optional)
        """
        negate = False
        optional = False
        
        # Handle dict format (when YAML parses without quotes)
        if isinstance(need, dict):
            # Check for optional flag
            if "optional" in need:
                optional = bool(need.get("optional", False))
                # Remove optional key and process remaining as dependency
                dep_dict = {k: v for k, v in need.items() if k != "optional"}
                if len(dep_dict) == 1:
                    key, value = list(dep_dict.items())[0]
                    key_str = str(key).strip()
                    attribute = key_str.split(".")
                    match_value = str(value).strip()
                    
                    # Check for negation
                    if match_value.startswith("!"):
                        negate = True
                        match_value = match_value[1:].strip()
                        
                    return (attribute, match_value, negate, optional)
                else:
                    raise ValueError(
                        f"Invalid optional dependency format: expected one dependency key "
                        f"plus 'optional', got {list(dep_dict.keys())}: {need}"
                    )
            # Handle simple dict format
            elif len(need) == 1:
                key, value = list(need.items())[0]
                key_str = str(key).strip()
                attribute = key_str.split(".")
                match_value = str(value).strip()
                
                # Check for negation
                if match_value.startswith("!"):
                    negate = True
                    match_value = match_value[1:].strip()
                    
                return (attribute, match_value, negate, optional)
            else:
                raise ValueError(
                    f"Invalid dependency dict format: expected a single key-value pair, "
                    f"got {len(need)} entries: {need}"
                )
        
        # Handle string format (with quotes in YAML)
        try:
            # Handle "attribute: value" format
            parts = need.split(":", 1)
            attribute = parts[0].strip().split(".")
            match_value = parts[1].strip()
            
            # Check for negation
            if match_value.startswith("!"):
                negate = True
                match_value = match_value[1:].strip()
            
            return (attribute, match_value, negate, optional)
        except (IndexError, AttributeError):
            # Plain name without colon
            return (["name"], need, False, optional)

    @property
    def job_id(self):
        """
        Get the ID number of this job as it resides in the scheduler.
        """
        if "scheduler" in self.meta:
            if "job id" in self.meta["scheduler"]:
                return self.meta["scheduler"]["job id"]
            else:
                return None

    @job_id.setter
    def job_id(self, value):
        if "scheduler" not in self.meta:
            self.meta["scheduler"] = {}
        self.meta["scheduler"]["job id"] = value

    @property
    def dependencies(self):
        """
        Return a list of analyses which this analysis depends upon.
        
        The dependency resolution supports complex logic:
        - Top-level items in needs are OR'd together
        - Nested lists represent AND conditions (all must match)
        - Individual filters can be negated with !
        
        Returns
        -------
        list
            List of analysis names that this analysis depends on
        """
        all_matches = []
        if len(self._needs) == 0:
            return []
        else:
            matches = set()
            requirements = self._process_dependencies(deepcopy(self._needs))
            
            for requirement in requirements:
                if isinstance(requirement, list):
                    # This is an AND group - all conditions must match
                    and_matches = set(self.event.analyses)
                    for parsed_dep in requirement:
                        # Handle both 3-tuple and 4-tuple formats
                        if len(parsed_dep) == 4:
                            attribute, match, negate, optional = parsed_dep
                        else:
                            attribute, match, negate = parsed_dep
                            optional = False
                        filtered_analyses = list(
                            filter(
                                lambda x: x.matches_filter(attribute, match, negate),
                                and_matches,
                            )
                        )
                        and_matches = set(filtered_analyses)
                    matches = set.union(matches, and_matches)
                else:
                    # Single condition
                    # Handle both 3-tuple and 4-tuple formats
                    if len(requirement) == 4:
                        attribute, match, negate, optional = requirement
                    else:
                        attribute, match, negate = requirement
                        optional = False
                    filtered_analyses = list(
                        filter(
                            lambda x: x.matches_filter(attribute, match, negate),
                            self.event.analyses,
                        )
                    )
                    matches = set.union(matches, set(filtered_analyses))
            
            # Exclude self-dependencies
            for analysis in matches:
                if analysis.name != self.name:
                    all_matches.append(analysis.name)

            return all_matches
    
    @property
    def required_dependencies(self):
        """
        Return a list of required (non-optional) dependencies.
        
        This evaluates the needs specification and returns only dependencies
        that are not marked as optional. If a required dependency is not found
        in the ledger, the analysis should not run.
        
        Returns
        -------
        list
            List of dependency specifications that are required
        """
        if len(self._needs) == 0:
            return []
        
        required_specs = []
        requirements = self._process_dependencies(deepcopy(self._needs))
        
        for requirement in requirements:
            if isinstance(requirement, list):
                # This is an AND group - check if all are optional
                all_optional = all(
                    parsed_dep[3] if len(parsed_dep) == 4 else False
                    for parsed_dep in requirement
                )
                if not all_optional:
                    required_specs.append(requirement)
            else:
                # Single condition - check if optional
                is_optional = requirement[3] if len(requirement) == 4 else False
                if not is_optional:
                    required_specs.append(requirement)
        
        return required_specs
    
    @property
    def has_required_dependencies_satisfied(self):
        """
        Check if all required dependencies are satisfied.
        
        A required dependency is satisfied if at least one analysis in the ledger
        matches its specification. Optional dependencies don't affect this check.
        
        Returns
        -------
        bool
            True if all required dependencies are satisfied (or there are no required deps),
            False if any required dependency has no matches
        """
        required_specs = self.required_dependencies
        
        if len(required_specs) == 0:
            # No required dependencies, so they're all satisfied
            return True
        
        for requirement in required_specs:
            if isinstance(requirement, list):
                # This is an AND group - all conditions must match at least one analysis
                and_matches = set(self.event.analyses)
                for parsed_dep in requirement:
                    if len(parsed_dep) == 4:
                        attribute, match, negate, optional = parsed_dep
                    else:
                        attribute, match, negate = parsed_dep
                        optional = False
                    
                    filtered_analyses = list(
                        filter(
                            lambda x: x.matches_filter(attribute, match, negate),
                            and_matches,
                        )
                    )
                    and_matches = set(filtered_analyses)
                
                # If no analyses match this AND group, requirement not satisfied
                if len(and_matches) == 0:
                    return False
            else:
                # Single condition
                if len(requirement) == 4:
                    attribute, match, negate, optional = requirement
                else:
                    attribute, match, negate = requirement
                    optional = False
                
                filtered_analyses = list(
                    filter(
                        lambda x: x.matches_filter(attribute, match, negate),
                        self.event.analyses,
                    )
                )
                
                # If no analyses match this requirement, it's not satisfied
                if len(filtered_analyses) == 0:
                    return False
        
        # All required dependencies have at least one match
        return True
    
    @property
    def resolved_dependencies(self):
        """
        Get the list of dependencies that were resolved when this analysis was run.
        
        This is used to track if dependencies have changed since the analysis ran,
        which would make the analysis stale.
        
        Returns
        -------
        list or None
            List of analysis names that were dependencies when this ran, or None if not yet run
        """
        if "resolved_dependencies" in self.meta:
            return self.meta["resolved_dependencies"]
        return None
    
    @resolved_dependencies.setter
    def resolved_dependencies(self, value):
        """
        Store the resolved dependencies for this analysis.
        
        Parameters
        ----------
        value : list
            List of analysis names that are current dependencies
        """
        self.meta["resolved_dependencies"] = value
    
    @property
    def is_stale(self):
        """
        Check if this analysis is stale (dependencies have changed since it was run).
        
        An analysis is considered stale if:
        1. It has been run (has resolved_dependencies)
        2. The current dependencies differ from the resolved dependencies
        
        Returns
        -------
        bool
            True if the analysis is stale, False otherwise
        """
        if self.resolved_dependencies is None:
            # Never run, so not stale
            return False
        
        current_deps = set(self.dependencies)
        resolved_deps = set(self.resolved_dependencies)
        
        return current_deps != resolved_deps
    
    @property
    def is_refreshable(self):
        """
        Check if this analysis should be automatically refreshed when stale.
        
        Returns
        -------
        bool
            True if the analysis is marked as refreshable
        """
        if "refreshable" in self.meta:
            return self.meta["refreshable"]
        return False
    
    @is_refreshable.setter
    def is_refreshable(self, value):
        """
        Mark this analysis as refreshable or not.
        
        Parameters
        ----------
        value : bool
            Whether the analysis should be automatically refreshed
        """
        self.meta["refreshable"] = bool(value)

    @property
    def priors(self):
        if "priors" in self.meta:
            priors = self.meta["priors"]
        else:
            priors = None
        return priors
    
    @priors.setter
    def priors(self, value):
        """
        Set priors with validation.
        
        Parameters
        ----------
        value : dict or PriorDict
            The prior specification
        """
        from asimov.priors import PriorDict
        
        if value is None:
            self.meta["priors"] = None
        elif isinstance(value, PriorDict):
            self.meta["priors"] = value.to_dict()
        elif isinstance(value, dict):
            # Validate using pydantic
            validated = PriorDict.from_dict(value)
            self.meta["priors"] = validated.to_dict()
        else:
            raise TypeError(f"priors must be dict or PriorDict, got {type(value)}")

    @property
    def finished(self):
        finished_states = ["finished", "processing", "uploaded"]
        return self.status in finished_states

    @property
    def status(self):
        return self.status_str.lower()

    @status.setter
    def status(self, value):
        self.status_str = value.lower()

    def matches_filter(self, attribute, match, negate=False):
        """
        Checks to see if this analysis matches a given filtering
        criterion.

        A variety of different attributes can be used for filtering.
        The primary attributes are

            - review status

            - processing status

            - pipeline

            - name

        In addition, any quantity contained in the analysis metadata
        may be used by accessing it in the nested structure of this
        data, with levels of the hierarchy separated with period
        characters.  For example, to access the waveform approximant
        the correct attribute would be `waveform.approximant`.

        Parameters
        ----------
        attribute : list
           The attribute path to be tested (e.g., ["waveform", "approximant"])
        match : str
           The string to be matched against the value of the attribute
        negate : bool, optional
           If True, invert the match result (default: False)

        Returns
        -------
        bool
           Returns True if this analysis matches the query,
           otherwise returns False.
        """
        is_review = False
        is_status = False
        is_name = False
        is_pipeline = False
        in_meta = False
        
        if attribute[0] == "review":
            is_review = match.lower() == str(self.review.status).lower()
        elif attribute[0] == "status":
            is_status = match.lower() == self.status.lower()
        elif attribute[0] == "name":
            is_name = match == self.name
        elif attribute[0] == "pipeline":
            # Check pipeline.name attribute first
            if hasattr(self, 'pipeline'):
                if hasattr(self.pipeline, 'name'):
                    is_pipeline = match.lower() == self.pipeline.name.lower()
                elif isinstance(self.pipeline, str):
                    is_pipeline = match.lower() == self.pipeline.lower()
            # Also check in metadata as fallback
            if not is_pipeline and 'pipeline' in self.meta:
                is_pipeline = match.lower() == self.meta['pipeline'].lower()
        else:
            try:
                meta_value = reduce(operator.getitem, attribute, self.meta)
                in_meta = str(meta_value).lower() == str(match).lower()
            except (KeyError, TypeError, AttributeError):
                in_meta = False

        result = is_name | in_meta | is_status | is_review | is_pipeline
        
        # Apply negation if requested
        if negate:
            return not result
        return result

    def results(self, filename=None, handle=False, hash=None):
        store = Store(root=config.get("storage", "results_store"))
        if not filename:
            try:
                items = store.manifest.list_resources(self.subject.name, self.name)
                return items
            except KeyError:
                return None
        elif handle:
            return open(
                store.fetch_file(self.subject.name, self.name, filename, hash), "r"
            )
        else:
            return store.fetch_file(self.subject.name, self.name, filename, hash=hash)

    @property
    def rundir(self):
        """
        Return the run directory for this analysis.
        """
        if "rundir" in self.meta and self.meta["rundir"] is not None:
            return os.path.abspath(self.meta["rundir"])
        elif "working directory" in self.subject.meta:
            value = os.path.join(self.subject.meta["working directory"], self.name)
            self.meta["rundir"] = value
            return os.path.abspath(self.meta["rundir"])
            # TODO: Make sure this is saved back to the ledger
        else:
            return None

    @rundir.setter
    def rundir(self, value):
        """
        Set the run directory.
        """
        if "rundir" not in self.meta:
            self.meta["rundir"] = value
        else:
            self.meta["rundir"] = value

    def get_meta(self, key):
        """
        Get the value of a metadata attribute, or return None if it doesn't
        exist.
        """
        if key in self.meta:
            return self.meta[key]
        else:
            return None

    def set_meta(self, key, value):
        """
        Set a metadata attribute which doesn't currently exist.
        """
        if key not in self.meta:
            self.meta[key] = value
            self.event.ledger.update_event(self.event)
        else:
            raise ValueError

    def make_config(self, filename, template_directory=None, dryrun=False):
        """
        Make the configuration file for this production.

        Parameters
        ----------
        filename : str
           The location at which the config file should be saved.
        template_directory : str, optional
           The path to the directory containing the pipeline config templates.
           Defaults to the directory specified in the asimov configuration file.
        """

        if "template" in self.meta:
            template = f"{self.meta['template']}.ini"

        else:
            template = f"{self.pipeline}.ini"

        pipeline = self.pipeline
        try:
            template_directory = config.get("templating", "directory")
            template_file = os.path.join(f"{template_directory}", template)

        except (configparser.NoOptionError, configparser.NoSectionError):
            if hasattr(pipeline, "config_template"):
                template_file = pipeline.config_template
            else:
                try:
                    from importlib.resources import files
                except ImportError:
                    from importlib_resources import files

                template_file = str(files("asimov").joinpath(f"configs/{template}"))

        liq = Liquid(template_file)
        rendered = liq.render(production=self, analysis=self, config=config)
        with open(filename, "w") as output_file:
            output_file.write(rendered)

    def build_report(self):
        if self.pipeline:
            self.pipeline.build_report()

    def html(self):
        """
        An HTML representation of this production.
        """
        production = self

        card = ""

        card += f"<div class='asimov-analysis asimov-analysis-{self.status}'>"
        
        # Add running indicator for active analyses
        if self.status in ["running", "processing"]:
            card += """<span class="running-indicator"></span>"""
        
        # Add stale indicator if applicable
        if self.is_stale:
            stale_class = "stale-refreshable" if self.is_refreshable else "stale"
            stale_text = "Stale (will refresh)" if self.is_refreshable else "Stale"
            card += f"""<span class="stale-indicator {stale_class}" title="Dependencies have changed since this analysis was run">{stale_text}</span>"""
        
        card += f"<h4>{self.name}"

        if self.comment:
            card += (
                f"""  <small class="asimov-comment text-muted">{self.comment}</small>"""
            )
        card += "</h4>"
        
        if self.status:
            card += f"""<p class="asimov-status">
  <span class="badge badge-pill badge-{status_map[self.status]}">{self.status}</span>
</p>"""

        if self.pipeline:
            card += f"""<p class="asimov-pipeline-name"><strong>Pipeline:</strong> {self.pipeline.name}</p>"""

        # Build collapsible details section
        has_details = bool(
            self.rundir or 
            "approximant" in production.meta or 
            "sampler" in production.meta or
            "quality" in production.meta or
            self.pipeline or
            self.dependencies or
            self.resolved_dependencies or
            (hasattr(self, 'analyses') and self.analyses)
        )
        
        if has_details:
            card += """<a class="toggle-details">▶ Show details</a>"""
            card += """<div class="details-content">"""
            
            # Show source analyses for SubjectAnalysis
            if hasattr(self, 'analyses') and self.analyses:
                if hasattr(self.analyses, "__iter__"):
                    card += """<p class="asimov-source-analyses"><strong>Source Analyses:</strong><br>"""
                    source_analysis_html = []
                    for analysis in self.analyses:
                        status_color = status_map.get(analysis.status, 'secondary')
                        source_analysis_html.append(
                            f"""<span class="badge badge-{status_color}">{analysis.name}</span>"""
                        )
                    card += " ".join(source_analysis_html)
                    card += """</p>"""
            
            # Show dependencies
            if self.dependencies:
                if hasattr(self.dependencies, "__iter__"):
                    card += """<p class="asimov-dependencies"><strong>Current Dependencies:</strong><br>"""
                    card += ", ".join(self.dependencies)
                    card += """</p>"""
            
            # Show resolved dependencies if different from current
            if self.resolved_dependencies and self.resolved_dependencies != self.dependencies:
                if hasattr(self.dependencies, "__iter__"):  
                    card += """<p class="asimov-resolved-dependencies"><strong>Resolved Dependencies (when run):</strong><br>"""
                    card += ", ".join(self.resolved_dependencies)
                    card += """</p>"""
            
            if self.pipeline:
                # self.pipeline.collect_pages()
                card += self.pipeline.html()

            if self.rundir:
                card += f"""<p class="asimov-rundir"><strong>Run directory:</strong><br><code>{production.rundir}</code></p>"""

            if "approximant" in production.meta:
                card += f"""<p class="asimov-attribute"><strong>Waveform approximant:</strong>
   <span class="asimov-approximant">{production.meta['approximant']}</span>
</p>"""

            # Add more metadata if available
            if "sampler" in production.meta and production.meta["sampler"]:
                if isinstance(production.meta["sampler"], dict):
                    for key, value in production.meta["sampler"].items():
                        card += f"""<p class="asimov-attribute"><strong>{key}:</strong> {value}</p>"""
                        
            if "quality" in production.meta:
                card += f"""<p class="asimov-attribute"><strong>Quality:</strong> {production.meta['quality']}</p>"""

            card += """</div>"""
        
        card += """</div>"""

        try:
            if len(self.review) > 0:
                for review in self.review:
                    card += review.html()

        except TypeError:
            # The mocked review object doesn't support len()
            pass
        
        return card

    def to_dict(self, event=True):
        """
        Return this production as a dictionary.

        Parameters
        ----------
        event : bool
           If set to True the output is designed to be included nested within an event.
           The event name is not included in the representation, and the production name is provided as a key.
        """
        dictionary = deepcopy(self.meta)
        if not event:
            dictionary["event"] = self.event.name
            dictionary["name"] = self.name

        if isinstance(self.pipeline, str):
            dictionary["pipeline"] = self.pipeline
        else:
            dictionary["pipeline"] = self.pipeline.name.lower()
        dictionary["comment"] = self.comment

        if self.review:
            dictionary["review"] = self.review.to_dicts()

        dictionary["needs"] = self._needs  # self.dependencies

        if "data" in self.meta:
            dictionary["data"] = self.meta["data"]
        if "likelihood" in self.meta:
            dictionary["likelihood"] = self.meta["likelihood"]
        if "quality" in self.meta:
            dictionary["quality"] = self.meta["quality"]
        if "priors" in self.meta:
            dictionary["priors"] = self.meta["priors"]
        if "waveform" in self.meta:
            dictionary["waveform"] = self.meta["waveform"]
        for key, value in self.meta.items():
            dictionary[key] = value

        dictionary["status"] = self.status
        # dictionary["job id"] = self.job_id

        # Remove duplicates of pipeline defaults
        pipeline_obj = getattr(self, "pipeline", None)
        if (
            hasattr(self, "event")
            and self.event
            and hasattr(self.event, "ledger")
            and self.event.ledger
            and "pipelines" in self.event.ledger.data
            and pipeline_obj is not None
            and hasattr(pipeline_obj, "name")
            and pipeline_obj.name.lower() in self.event.ledger.data["pipelines"]
        ):
            defaults = deepcopy(
                self.event.ledger.data["pipelines"][pipeline_obj.name.lower()]
            )
        else:
            defaults = {}

        # if "postprocessing" in self.event.ledger.data:
        #     defaults["postprocessing"] = deepcopy(
        #         self.event.ledger.data["postprocessing"]
        #     )

        defaults = update(defaults, deepcopy(self.event.meta))
        dictionary = diff_dict(defaults, dictionary)
        
        # Ensure critical fields are always saved, even if they match defaults
        # This is necessary to support old ledgers and ensure status updates persist
        dictionary["status"] = self.status
        if self.job_id is not None:
            dictionary["job id"] = self.job_id

        if "repository" in self.meta:
            dictionary["repository"] = self.repository.url
        if "ledger" in dictionary:
            dictionary.pop("ledger")
        if "pipelines" in dictionary:
            dictionary.pop("pipelines")
        if "productions" in dictionary:
            dictionary.pop("productions")

        if not event:
            output = dictionary
        else:
            output = {self.name: dictionary}
        return output


class SimpleAnalysis(Analysis):
    """
    A single subject, single pipeline analysis.
    """

    def __init__(self, subject, name, pipeline, status=None, comment=None, **kwargs):

        self.ledger = kwargs.get("ledger", None)

        self.event = self.subject = subject
        self.name = name

        pathlib.Path(
            os.path.join(config.get("logging", "location"), self.event.name, name)
        ).mkdir(parents=True, exist_ok=True)

        self.logger = logger.getChild("analysis").getChild(
            f"{self.event.name}/{self.name}"
        )
        self.logger.setLevel(LOGGER_LEVEL)

        # fh = logging.FileHandler(logfile)
        # formatter = logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        # fh.setFormatter(formatter)
        # self.logger.addHandler(fh)

        if status:
            self.status_str = status.lower()
        else:
            self.status_str = "none"

        self.meta = deepcopy(self.meta_defaults)
        
        # Initialize review object for this instance
        self._reviews = Review()

        # Start by adding pipeline defaults
        if "pipelines" in self.event.ledger.data:
            if pipeline in self.event.ledger.data["pipelines"]:
                self.meta = update(
                    self.meta, deepcopy(self.event.ledger.data["pipelines"][pipeline])
                )

        if "postprocessing" in self.event.ledger.data:
            self.meta["postprocessing"] = deepcopy(
                self.event.ledger.data["postprocessing"]
            )

        # self.meta["pipeline"] = pipeline

        # Update with the subject defaults
        self.meta = update(self.meta, deepcopy(self.subject.meta))
        if "productions" in self.meta:
            self.meta.pop("productions")
        self.meta = update(self.meta, deepcopy(kwargs))

        self.pipeline = pipeline.lower()
        self.pipeline = known_pipelines[pipeline.lower()](self)

        if "needs" in self.meta:
            self._needs = cast(List[Any], self.meta.pop("needs"))
        else:
            self._needs = []

        self.comment = kwargs.get("comment", None)

    def _previous_assets(self):
        assets = {}
        if self.dependencies:
            productions = {}
            for production in self.event.productions:
                productions[production.name] = production
            for previous_job in self.dependencies:
                assets.update(productions[previous_job].pipeline.collect_assets())
        return assets

    @classmethod
    def from_dict(cls, parameters, subject=None, ledger=None):
        parameters = deepcopy(parameters)
        # Check that pars is a dictionary
        if not {"pipeline", "name"} <= parameters.keys():
            raise ValueError(
                f"Some of the required parameters are missing."
                f"Found {parameters.keys()}"
            )
        if "status" not in parameters:
            parameters["status"] = "ready"
        if "event" in parameters:
            parameters.pop("event")
        pipeline = parameters.pop("pipeline")
        name = parameters.pop("name")
        if "comment" not in parameters:
            parameters["comment"] = None
        if "ledger" in parameters:
            ledger = parameters.pop("ledger")

        return cls(
            name=name, pipeline=pipeline, ledger=ledger, subject=subject, **parameters
        )


class SubjectAnalysis(Analysis):
    """
    A single subject analysis which requires results from multiple pipelines.
    """

    def __init__(self, subject, name, pipeline, status=None, comment=None, **kwargs):
        self.event = self.subject = subject
        self.name = name

        self.category = "subject_analyses"

        self.logger = logger.getChild("event").getChild(f"{self.name}")
        self.logger.setLevel(LOGGER_LEVEL)

        if status:
            self.status_str = status.lower()
        else:
            self.status_str = "none"

        self.meta = deepcopy(self.meta_defaults)
        
        # Initialize review object for this instance
        self._reviews = Review()
        
        self.meta = update(self.meta, deepcopy(self.subject.meta))
        # Avoid inheriting full productions/analyses blobs from the subject; they bloat the ledger
        for noisy_key in ["productions", "analyses"]:
            if noisy_key in self.meta:
                self.meta.pop(noisy_key)
        self.meta = update(self.meta, deepcopy(kwargs))

        self._analysis_spec = self.meta.get("needs") or self.meta.get("analyses")
        # Store the analysis spec names for refresh checking (if it's just a list of names).
        # This lets us detect when dependencies have changed without blocking submission.
        self._analysis_spec_names = []
        if self._analysis_spec:
            if isinstance(self._analysis_spec, list):
                for spec_item in self._analysis_spec:
                    if isinstance(spec_item, str):
                        self._analysis_spec_names.append(spec_item)
                    elif isinstance(spec_item, dict) and len(spec_item) == 1:
                        # Single-key dict, add the value if it's a string
                        key, val = list(spec_item.items())[0]
                        if isinstance(val, str):
                            self._analysis_spec_names.append(val)
            elif isinstance(self._analysis_spec, str):
                self._analysis_spec_names.append(self._analysis_spec)
        
        # SubjectAnalysis does not participate in the dependency graph.
        # Its _needs remain empty so it doesn't block submission.
        self._needs = []
        
        # Remove needs and analyses from meta to prevent duplication later
        if "needs" in self.meta:
            self.meta.pop("needs")
        if "analyses" in self.meta:
            self.meta.pop("analyses")

        # Initialize analyses lists (will be populated by resolve_analyses)
        self.analyses = []
        self.productions = []

        # Resolve analyses from smart dependencies
        # Note: This may be incomplete if not all analyses are loaded yet.
        # Event.update_graph() will call resolve_analyses() again after all productions are loaded.
        if self._analysis_spec:
            self.resolve_analyses()

        self.pipeline = pipeline.lower()
        self.pipeline = known_pipelines[pipeline.lower()](self)

        if "comment" in kwargs:
            self.comment = kwargs["comment"]
        else:
            self.comment = None

    def resolve_analyses(self):
        """
        Resolve analyses from smart dependencies.

        This method evaluates the _analysis_spec (smart dependencies) against
        the current set of analyses in the subject/event and populates self.analyses
        with the matching analyses.

        This can be called multiple times safely:
        - During __init__ (may be incomplete if not all analyses are loaded)
        - After all productions are loaded (via Event.update_graph)
        - When dependencies change

        Returns
        -------
        None
        """
        if not self._analysis_spec:
            return

        requirements = self._process_dependencies(self._analysis_spec)
        self.analyses = []

        for requirement in requirements:
            if isinstance(requirement, list):
                # This is an AND group - all conditions must match
                and_matches = set(self.subject.analyses)
                for parsed_dep in requirement:
                    # Handle both 3-tuple and 4-tuple formats
                    if len(parsed_dep) == 4:
                        attribute, match, negate, optional = parsed_dep
                    else:
                        attribute, match, negate = parsed_dep
                        optional = False
                    filtered_analyses = list(
                        filter(
                            lambda x: x.matches_filter(attribute, match, negate), and_matches
                        )
                    )
                    and_matches = set(filtered_analyses)
                # Add all matches from this AND group
                for analysis in and_matches:
                    if analysis not in self.analyses:
                        self.analyses.append(analysis)
            else:
                # Single condition
                # Handle both 3-tuple and 4-tuple formats
                if len(requirement) == 4:
                    attribute, match, negate, optional = requirement
                else:
                    attribute, match, negate = requirement
                    optional = False
                filtered_analyses = list(
                    filter(
                        lambda x: x.matches_filter(attribute, match, negate), self.subject.analyses
                    )
                )
                # Add all matches from this single condition
                for analysis in filtered_analyses:
                    if analysis not in self.analyses:
                        self.analyses.append(analysis)

        # Keep productions in sync
        self.productions = self.analyses

    def source_analyses_ready(self):
        """
        Check if all source analyses are finished and ready for processing.
        
        Returns
        -------
        bool
            True if all source analyses have finished status, False otherwise
        """
        if not hasattr(self, 'analyses') or not self.analyses:
            return False
        
        finished_statuses = {"finished", "uploaded", "processing"}
        for analysis in self.analyses:
            if analysis.status not in finished_statuses:
                return False
        return True

    def to_dict(self, event=True):
        """
        Return this production as a dictionary.

        Parameters
        ----------
        event : bool
           If set to True the output is designed to be included nested within an event.
           The event name is not included in the representation, and the production name is provided as a key.
        """
        dictionary = {}
        dictionary = update(dictionary, self.meta)

        # Keep resolved_dependencies in serialization for staleness detection
        # This tracks which analyses were actually used when the job was run,
        # allowing the refresh logic to detect when new analyses match the criteria
        # Note: resolved_dependencies is set by PESummary.submit_dag() during submission

        if not event:
            dictionary["event"] = self.event.name
            dictionary["name"] = self.name

        dictionary["status"] = self.status
        if isinstance(self.pipeline, str):
            dictionary["pipeline"] = self.pipeline
        else:
            dictionary["pipeline"] = self.pipeline.name.lower()
        dictionary["comment"] = self.comment

        # Always persist the original analysis specification (smart dependencies)
        # rather than the resolved list of analysis names.
        # This ensures that smart dependencies are re-evaluated on each load,
        # and the ledger doesn't get polluted with resolved names.
        if hasattr(self, "_analysis_spec") and self._analysis_spec:
            dictionary["analyses"] = self._analysis_spec
        elif hasattr(self, "analyses") and self.analyses:
            # Fallback: if no _analysis_spec but we have analyses, save as names
            dictionary["analyses"] = [analysis.name for analysis in self.analyses]

        if self.review:
            dictionary["review"] = self.review.to_dicts()

        dictionary["needs"] = deepcopy(self._needs)  # self.dependencies

        if "quality" in self.meta:
            dictionary["quality"] = self.meta["quality"]
        if "priors" in self.meta:
            dictionary["priors"] = self.meta["priors"]

        # Include remaining meta fields
        for key, value in self.meta.items():
            # Do not allow a meta-level "analyses" entry to overwrite the
            # explicitly constructed analyses list above.
            if key in ["analyses"]:
                continue
            dictionary[key] = value

        # Remove duplicated defaults to keep the ledger minimal, mirroring Analysis.to_dict
        defaults = {}
        pipeline_obj = getattr(self, "pipeline", None)
        if (
            hasattr(self.event, "ledger")
            and self.event.ledger
            and "pipelines" in self.event.ledger.data
            and pipeline_obj is not None
            and hasattr(pipeline_obj, "name")
            and pipeline_obj.name.lower() in self.event.ledger.data["pipelines"]
        ):
            defaults = deepcopy(
                self.event.ledger.data["pipelines"][pipeline_obj.name.lower()]
            )

        # Subject-level defaults
        defaults = update(defaults, deepcopy(self.subject.meta))

        dictionary = diff_dict(defaults, dictionary)

        if "repository" in dictionary:
            dictionary["repository"] = self.repository.url
        if "ledger" in dictionary:
            dictionary.pop("ledger")
        if "pipelines" in dictionary:
            dictionary.pop("pipelines")

        if not event:
            output = dictionary
        else:
            output = {self.name: dictionary}
        return output

    @classmethod
    def from_dict(cls, parameters, subject):
        parameters = deepcopy(parameters)
        # Check that pars is a dictionary
        if not {"pipeline", "name"} <= parameters.keys():
            raise ValueError(
                f"Some of the required parameters are missing."
                f"Found {parameters.keys()}"
            )
        if "status" not in parameters:
            parameters["status"] = "ready"
        if "event" in parameters:
            parameters.pop("event")
        pipeline = parameters.pop("pipeline")
        name = parameters.pop("name")
        if "comment" not in parameters:
            parameters["comment"] = None

        return cls(subject, name, pipeline, **parameters)

    @property
    def rundir(self):
        """
        Return the run directory for this subject analysis.
        """
        if "rundir" in self.meta:
            return os.path.abspath(self.meta["rundir"])
        elif "working directory" in self.subject.meta:
            value = os.path.join(self.subject.meta["working directory"], self.name)
            self.meta["rundir"] = value
            return os.path.abspath(self.meta["rundir"])
        else:
            return None

    @rundir.setter
    def rundir(self, value):
        """
        Set the run directory.
        """
        self.meta["rundir"] = value


class ProjectAnalysis(Analysis):
    """
    A multi-subject analysis.
    """

    meta_defaults = {"scheduler": {}, "sampler": {}}

    def __init__(self, name, pipeline, ledger=None, **kwargs):
        """ """
        super().__init__()
        self.name = name
        self.logger = logger.getChild("project analyses").getChild(f"{self.name}")
        self.logger.setLevel(LOGGER_LEVEL)
        self.ledger = ledger
        self.category = "project_analyses"

        self._subjects = kwargs["subjects"]

        self._events = self._subjects
        if "analyses" in kwargs.keys():
            self._analysis_spec = kwargs["analyses"]
        else:
            self._analysis_spec = {}

        # Initialize analyses list (will be populated by resolve_analyses)
        self.analyses = []

        # set up the working directory
        if "working_directory" in kwargs:
            self.work_dir = kwargs["working_directory"]
        else:
            subj_string = "_".join([f"{subject}" for subject in self._subjects])
            self.work_dir = os.path.join("working", "project-analyses", subj_string, f"{self.name}")

        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

        self.repository = None

        self._subject_obs = []

        # Resolve analyses from smart dependencies across subjects
        if self._analysis_spec:
            self.resolve_analyses()

        if "status" in kwargs:
            self.status_str = kwargs["status"].lower()
        else:
            self.status_str = "none"
        
        self.pipeline = pipeline  # .lower()
        if isinstance(pipeline, str):
            # try:
            self.pipeline = known_pipelines[str(pipeline).lower()](self)
            # except KeyError:
            self.logger.warning(f"The pipeline {pipeline} could not be found.")
        
        if "needs" in self.meta:
            self._needs = cast(List[Any], self.meta.pop("needs"))
        else:
            self._needs = []
        
        if "comment" in kwargs:
            self.comment = kwargs["comment"]
        else:
            self.comment = None

        self.meta = deepcopy(self.meta_defaults)
        
        # Initialize review object for this instance
        self._reviews = Review()

        # Start by adding pipeline defaults
        if "pipelines" in self.ledger.data:
            if pipeline in self.ledger.data["pipelines"]:
                self.meta = update(
                    self.meta, deepcopy(self.ledger.data["pipelines"][pipeline])
                )

        self.meta = update(self.meta, deepcopy(kwargs))
        

    def __repr__(self):
        """
        A human-friendly representation of this project analysis.

        Parameters
        ----------
        None
        """
        return f"<Project analysis for {len(self.events)} events and {len(self.analyses)} analyses>"

    @property
    def subjects(self):
        """Return a list of subjects for this project analysis."""
        return [self.ledger.get_event(subject)[0] for subject in self._subjects]

    @property
    def events(self):
        return self.subjects

    def resolve_analyses(self):
        """
        Resolve analyses from smart dependencies across all subjects.

        This method evaluates the _analysis_spec (smart dependencies) against
        the analyses in each subject and populates self.analyses with matches.

        Returns
        -------
        None
        """
        if not self._analysis_spec:
            return

        requirements = self._process_dependencies(self._analysis_spec)
        self.analyses = []

        for subject in self.subjects:
            for requirement in requirements:
                if isinstance(requirement, list):
                    # This is an AND group - all conditions must match
                    and_matches = set(subject.analyses)
                    for parsed_dep in requirement:
                        # Handle both 3-tuple and 4-tuple formats
                        if len(parsed_dep) == 4:
                            attribute, match, negate, optional = parsed_dep
                        else:
                            attribute, match, negate = parsed_dep
                            optional = False
                        filtered_analyses = list(
                            filter(
                                lambda x: x.matches_filter(attribute, match, negate),
                                and_matches,
                            )
                        )
                        and_matches = set(filtered_analyses)
                    # Add all matches from this AND group
                    for analysis in and_matches:
                        if analysis not in self.analyses:
                            self.analyses.append(analysis)
                else:
                    # Single condition
                    # Handle both 3-tuple and 4-tuple formats
                    if len(requirement) == 4:
                        attribute, match, negate, optional = requirement
                    else:
                        attribute, match, negate = requirement
                        optional = False
                    filtered_analyses = list(
                        filter(
                            lambda x: x.matches_filter(attribute, match, negate),
                            subject.analyses,
                        )
                    )
                    # Add all matches from this single condition
                    for analysis in filtered_analyses:
                        if analysis not in self.analyses:
                            self.analyses.append(analysis)

    @classmethod
    def from_dict(cls, parameters, ledger=None):
        parameters = deepcopy(parameters)
        # Check that pars is a dictionary
        if not {"pipeline", "name"} <= parameters.keys():
            raise ValueError(
                f"Some of the required parameters are missing. "
                f"Found {parameters.keys()}"
            )
        if "status" not in parameters:
            parameters["status"] = "ready"
        if "event" in parameters:
            parameters.pop("event")
        pipeline = parameters.pop("pipeline")
        name = parameters.pop("name")
        if "comment" not in parameters:
            parameters["comment"] = None

        if "analyses" not in parameters:
            parameters["analyses"] = []

        return cls(name=name, pipeline=pipeline, ledger=ledger, **parameters)

    @property
    def dependencies(self):
        """
        Return a list of analyses which this analysis depends upon.
        
        The dependency resolution supports complex logic:
        - Top-level items in needs are OR'd together
        - Nested lists represent AND conditions (all must match)
        - Individual filters can be negated with !
        
        Returns
        -------
        list
            List of analysis names that this analysis depends on
        """
        all_matches = []
        if len(self._needs) == 0:
            return []
        else:
            matches = set()
            requirements = self._process_dependencies(deepcopy(self._needs))
            analyses = []
            for subject in self._subjects:
                sub = self.ledger.get_event(subject)[0]
                self._subject_obs.append(sub)
                for analysis in sub.analyses:
                    analyses.append(analysis)
            
            for requirement in requirements:
                if isinstance(requirement, list):
                    # This is an AND group - all conditions must match
                    and_matches = set(analyses)
                    for parsed_dep in requirement:
                        # Handle both 3-tuple and 4-tuple formats
                        if len(parsed_dep) == 4:
                            attribute, match, negate, optional = parsed_dep
                        else:
                            attribute, match, negate = parsed_dep
                            optional = False
                        filtered_analyses = list(
                            filter(
                                lambda x: x.matches_filter(attribute, match, negate),
                                and_matches,
                            )
                        )
                        and_matches = set(filtered_analyses)
                    matches = set.union(matches, and_matches)
                else:
                    # Single condition
                    # Handle both 3-tuple and 4-tuple formats
                    if len(requirement) == 4:
                        attribute, match, negate, optional = requirement
                    else:
                        attribute, match, negate = requirement
                        optional = False
                    filtered_analyses = list(
                        filter(
                            lambda x: x.matches_filter(attribute, match, negate),
                            analyses,
                        )
                    )
                    matches = set.union(matches, set(filtered_analyses))
            
            for analysis in matches:
                all_matches.append(analysis.name)

            return all_matches

    def to_dict(self, event=True):
        """
        Return this project production as a dictionary.

        Parameters
        ----------
        event : bool
           If set to True the output is designed to be included nested within an event.
           The event name is not included in the representation, and the production name is provided as a key.
        """
        dictionary = {}
        dictionary = update(dictionary, self.meta)

        dictionary["name"] = self.name
        dictionary["status"] = self.status
        if isinstance(self.pipeline, str):
            dictionary["pipeline"] = self.pipeline
        else:
            dictionary["pipeline"] = self.pipeline.name.lower()
        dictionary["comment"] = self.comment

        if self.review:
            dictionary["review"] = self.review.to_dicts()

        dictionary["needs"] = self.dependencies

        if "quality" in self.meta:
            dictionary["quality"] = self.meta["quality"]
        if "priors" in self.meta:
            dictionary["priors"] = self.meta["priors"]

        for key, value in self.meta.items():
            dictionary[key] = value

        if "repository" in self.meta:
            dictionary["repository"] = self.repository.url
        if "ledger" in dictionary:
            dictionary.pop("ledger")
        if "pipelines" in dictionary:
            dictionary.pop("pipelines")

        dictionary["subjects"] = self._subjects
        dictionary["analyses"] = self._analysis_spec

        # Remove duplicated defaults: pipeline defaults + any project-level defaults
        defaults = {}
        pipeline_obj = getattr(self, "pipeline", None)
        if (
            hasattr(self, "ledger")
            and self.ledger
            and "pipelines" in self.ledger.data
            and pipeline_obj is not None
            and hasattr(pipeline_obj, "name")
            and pipeline_obj.name.lower() in self.ledger.data["pipelines"]
        ):
            defaults = deepcopy(
                self.ledger.data["pipelines"][pipeline_obj.name.lower()]
            )

        # Project-level defaults if present
        if hasattr(self, "ledger") and self.ledger and "project" in self.ledger.data:
            defaults = update(defaults, deepcopy(self.ledger.data["project"]))

        dictionary = diff_dict(defaults, dictionary)

        return dictionary

    @property
    def rundir(self):
        """
        Returns the rundir for this project analysis
        """

        if "rundir" in self.meta:
            return os.path.abspath(self.meta["rundir"])
        elif self.work_dir:
            self.meta["rundir"] = self.work_dir
            return os.path.abspath(self.meta["rundir"])
        else:
            return None

    @rundir.setter
    def rundir(self, value):
        """
        Set the run directory.
        """
        if "rundir" not in self.meta:
            self.meta["rundir"] = value
        else:
            self.meta["rundir"] = value


class GravitationalWaveTransient(SimpleAnalysis):
    """
    A single subject, single pipeline analysis for a gravitational wave transient.
    """

    def __init__(self, subject, name, pipeline, **kwargs):
        """
        A specific analysis on a GW transient event.

        Parameters
        ----------
        subject : `asimov.event`
            The event this analysis is running on.
        name : str
            The name of this analysis.
        status : str
            The status of this analysis.
        pipeline : str
            This analysis's pipeline.
        comment : str
            A comment on this analysis.
        """

        self.category = config.get("general", "calibration_directory")
        super().__init__(subject, name, pipeline, **kwargs)
        self._checks()

        self.psds = self._collect_psds()
        self.xml_psds = self._collect_psds(format="xml")

        if "cip jobs" in self.meta:
            # TODO: Should probably raise a deprecation warning
            self.meta["sampler"]["cip jobs"] = self.meta["cip jobs"]

        if "scheduler" not in self.meta:
            self.meta["scheduler"] = {}

        if "likelihood" not in self.meta:
            self.meta["likelihood"] = {}
        if "marginalization" not in self.meta["likelihood"]:
            self.meta["likelihood"]["marginalization"] = {}

        if "data" not in self.meta:
            self.meta["data"] = {}
        if "data files" not in self.meta["data"]:
            self.meta["data"]["data files"] = {}

        if "lmax" in self.meta:
            # TODO: Should probably raise a deprecation warning
            self.meta["sampler"]["lmax"] = self.meta["lmax"]

        # Check that the upper frequency is included, otherwise calculate it
        if "quality" in self.meta:
            if ("maximum frequency" not in self.meta["quality"]) and (
                "sample rate" in self.meta["likelihood"]
            ):
                self.meta["quality"]["maximum frequency"] = {}
                # Account for the PSD roll-off with the 0.875 factor
                for ifo in self.meta["interferometers"]:
                    self.meta["quality"]["maximum frequency"][ifo] = int(
                        0.875 * self.meta["likelihood"]["sample rate"] / 2
                    )

        if ("quality" in self.meta) and ("event time" in self.meta):
            if ("segment start" not in self.meta["quality"]) and (
                "segment length" in self.meta["data"]
            ):
                self.meta["likelihood"]["segment start"] = (
                    self.meta["event time"] - self.meta["data"]["segment length"] + 2
                )
                # self.event.meta['likelihood']['segment start'] = self.meta['data']['segment start']

        # Update waveform data
        if "waveform" not in self.meta:
            self.logger.info("Didn't find waveform information in the metadata")
            self.meta["waveform"] = {}
        if "approximant" in self.meta:
            self.logger.warning(
                "Found deprecated approximant information, "
                "moving to waveform area of ledger"
            )
            approximant = self.meta.pop("approximant")
            self.meta["waveform"]["approximant"] = approximant
        if "reference frequency" in self.meta["likelihood"]:
            self.logger.warning(
                "Found deprecated ref freq information, "
                "moving to waveform area of ledger"
            )
            ref_freq = self.meta["likelihood"].pop("reference frequency")
            self.meta["waveform"]["reference frequency"] = ref_freq

        # Gather the PSDs for the job
        self.psds = self._collect_psds()

    def _checks(self):
        """
        Carry-out a number of data consistency checks on the information from the ledger.
        """
        # Check that the upper frequency is included, otherwise calculate it
        if self.quality:
            if ("high-frequency" not in self.quality) and (
                "sample-rate" in self.quality
            ):
                # Account for the PSD roll-off with the 0.875 factor
                self.meta["quality"]["high-frequency"] = int(
                    0.875 * self.meta["quality"]["sample-rate"] / 2
                )
            elif ("high-frequency" in self.quality) and ("sample-rate" in self.quality):
                if self.meta["quality"]["high-frequency"] != int(
                    0.875 * self.meta["quality"]["sample-rate"] / 2
                ):
                    self.logger.warn(
                        "The upper-cutoff frequency is not equal to 0.875 times the Nyquist frequency."
                    )

    @property
    def quality(self):
        if "quality" in self.meta:
            return self.meta["quality"]
        else:
            return None

    @property
    def reference_frame(self):
        """
        Calculate the appropriate reference frame.
        """
        ifos = self.meta["interferometers"]
        if len(ifos) == 1:
            return ifos[0]
        else:
            return "".join(ifos[:2])

    def get_timefile(self):
        """
        Find this event's time file.

        Returns
        -------
        str
           The location of the time file.
        """
        return self.event.repository.find_timefile(self.category)

    def get_coincfile(self):
        """
        Find this event's coinc.xml file.

        Returns
        -------
        str
           The location of the time file.
        """
        try:
            coinc = self.event.repository.find_coincfile(self.category)
            return coinc
        except FileNotFoundError:
            self.event.get_gracedb(
                "coinc.xml",
                os.path.join(
                    self.event.repository.directory, self.category, "coinc.xml"
                ),
            )
            coinc = self.event.repository.find_coincfile(self.category)
            return coinc

    def get_configuration(self):
        """
        Get the configuration file contents for this event.
        """
        if "ini" in self.meta:
            ini_loc = self.meta["ini"]
        else:
            # We'll need to search the repository for it.
            try:
                ini_loc = self.subject.repository.find_prods(self.name, self.category)[
                    0
                ]
                if not os.path.exists(ini_loc):
                    raise ValueError("Could not open the ini file.")
            except IndexError:
                raise ValueError("Could not open the ini file.")
        try:
            ini = RunConfiguration(ini_loc)
        except ValueError:
            raise ValueError("Could not open the ini file")
        except configparser.MissingSectionHeaderError:
            raise ValueError("This isn't a valid ini file")

        return ini

    def _check_compatible(self, previous_analysis):
        """
        Placeholder compatibility check between analyses.
        Extend when additional metadata comparisons are needed.
        """
        return True

    def _collect_psds(self, format="ascii"):
        """
        Collect the required psds for this production.
        """
        psds = {}
        # If the PSDs are specifically provided in the ledger,
        # use those.

        if format == "ascii":
            keyword = "psds"
        elif format == "xml":
            keyword = "xml psds"
        else:
            raise ValueError(f"This PSD format ({format}) is not recognised.")

        if keyword in self.meta:
            # if self.meta["likelihood"]["sample rate"] in self.meta[keyword]:
            psds = self.meta[keyword]  # [self.meta["likelihood"]["sample rate"]]

        # First look through the list of the job's dependencies
        # to see if they're provided by a job there.
        elif self.dependencies:
            productions = {}
            for production in self.event.productions:
                productions[production.name] = production

            for previous_job in self.dependencies:
                try:
                    # Check if the job provides PSDs as an asset and were produced with compatible settings
                    if keyword in productions[previous_job].pipeline.collect_assets():
                        if self._check_compatible(productions[previous_job]):
                            psds = productions[previous_job].pipeline.collect_assets()[
                                keyword
                            ]
                            break
                        else:
                            self.logger.info(
                                f"The PSDs from {previous_job} are not compatible with this job."
                            )
                    else:
                        psds = {}
                except Exception:
                    psds = {}
        # Otherwise return no PSDs
        else:
            psds = {}

        for ifo, psd in psds.items():
            self.logger.debug(f"PSD-{ifo}: {psd}")

        return psds
