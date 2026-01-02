"""
Trigger handling code.
"""

import os
import subprocess

import networkx as nx
import yaml
from ligo.gracedb.rest import GraceDb, HTTPError

from asimov import config, logger, LOGGER_LEVEL
from asimov.analysis import SubjectAnalysis, GravitationalWaveTransient

from .git import EventRepo

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


class DescriptionException(Exception):
    """Exception for event description problems."""

    def __init__(self, message, production=None):
        super(DescriptionException, self).__init__(message)
        self.message = message
        self.production = production

    def __repr__(self):
        text = f"""
An error was detected with the YAML markup in this issue.
Please fix the error and then remove the `yaml-error` label from this issue.
<p>
  <details>
     <summary>Click for details of the error</summary>
     <p><b>Production</b>: {self.production}</p>
     <p>{self.message}</p>
  </details>
</p>

- [ ] Resolved
"""
        return text


class Event:
    """
    A specific gravitational wave event or trigger.
    """

    def __init__(self, name, repository=None, update=False, **kwargs):
        """
        Parameters
        ----------
        update : bool
           Flag to determine if the event repo should be updated
           when it is loaded. Defaults to False.
        """
        self.name = name

        self.logger = logger.getChild("event").getChild(f"{self.name}")
        self.logger.setLevel(LOGGER_LEVEL)

        # pathlib.Path(os.path.join(config.get("logging", "directory"), name)).mkdir(
        #    parents=True, exist_ok=True
        # )
        # logfile = os.path.join(config.get("logging", "directory"), name, "asimov.log")

        # fh = logging.FileHandler(logfile)
        # formatter = logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        # fh.setFormatter(formatter)
        # self.logger.addHandler(fh)

        if "working_directory" in kwargs:
            self.work_dir = kwargs["working_directory"]
        else:
            self.work_dir = os.path.join(
                config.get("general", "rundir_default"), self.name
            )
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

        if "ledger" in kwargs:
            if kwargs["ledger"]:
                self.ledger = kwargs["ledger"]
        else:
            self.ledger = None

        if "ledger" in kwargs:
            self.ledger = kwargs["ledger"]
        else:
            self.ledger = None

        if repository:
            if "git@" in repository or "https://" in repository:
                self.repository = EventRepo.from_url(
                    repository, self.name, directory=None, update=update
                )
            else:
                self.repository = EventRepo(repository)
        elif not repository:
            # If the repository isn't set you'll need to make one
            location = config.get("general", "git_default")
            location = os.path.join(location, self.name)
            self.repository = EventRepo.create(location)

        else:
            self.repository = repository

        if "psds" in kwargs:
            self.psds = kwargs["psds"]
        else:
            self.psds = {}

        self.meta = kwargs

        self.productions = []
        self.graph = nx.DiGraph()

        if "productions" in kwargs:
            for production in kwargs["productions"]:
                # Normalise stored production structures. They may arrive either as
                # {name: {..metadata..}} (preferred) or a flat dict. Ensure the
                # inner dict carries the production name so downstream factories
                # have the required fields.
                if isinstance(production, dict) and len(production) == 1:
                    prod_name, prod_meta = next(iter(production.items()))
                    if prod_meta is None:
                        prod_meta = {}
                    if "name" not in prod_meta:
                        prod_meta["name"] = prod_name
                elif isinstance(production, dict):
                    prod_meta = dict(production)
                else:
                    # Unknown structure; skip
                    continue

                if ("analyses" in prod_meta) or ("productions" in prod_meta):
                    self.add_production(
                        SubjectAnalysis.from_dict(prod_meta, subject=self)
                    )
                else:
                    self.add_production(
                        Production.from_dict(
                            prod_meta, subject=self, ledger=self.ledger
                        )
                    )
        self._check_required()

        if (
            ("interferometers" in self.meta)
            and ("calibration" in self.meta)
            and ("data" in self.meta)
        ):
            try:
                self._check_calibration()
            except DescriptionException:
                pass

    @property
    def analyses(self):
        return self.productions

    def __eq__(self, other):
        if isinstance(other, Event):
            if other.name == self.name:
                return True
            else:
                return False
        else:
            return False

    def update_data(self):
        if self.ledger:
            self.ledger.update_event(self)
        pass

    def _check_required(self):
        """
        Find all of the required metadata is provided.
        """
        return True

    def _check_calibration(self):
        """
        Find the calibration envelope locations.
        """

        if "calibration" not in self.meta["data"]:
            self.logger.warning("There are no calibration envelopes for this event.")

        elif ("calibration" in self.meta["data"]) and (
            set(self.meta["interferometers"]).issubset(
                set(self.meta["data"]["calibration"].keys())
            )
        ):
            pass

        else:
            self.logger.warning(
                f"""Some of the calibration envelopes are missing from this event. """
                f"""{set(self.meta['interferometers']) - set(self.meta['data']['calibration'].keys())} are absent."""
            )

    def _check_psds(self):
        """
        Find the psd locations.
        """
        if ("calibration" in self.meta) and (
            set(self.meta["interferometers"]) == set(self.psds.keys())
        ):
            pass
        else:
            raise DescriptionException(
                "Some of the required psds are missing from this issue. "
                f"{set(self.meta['interferometers']) - set(self.meta['calibration'].keys())}"
            )

    @property
    def webdir(self):
        """
        Get the web directory for this event.
        """
        if "webdir" in self.meta:
            return self.meta["webdir"]
        else:
            return None

    def add_production(self, production):
        """
        Add an additional production to this event.
        """
        if production.name in [production_o.name for production_o in self.productions]:
            raise ValueError(
                f"A production with this name already exists for {self.name}. New productions must have unique names."
            )

        self.productions.append(production)
        self.graph.add_node(production)

        if production.dependencies:
            for dependency in production.dependencies:
                if dependency == production:
                    continue
                analysis_dict = {
                    production.name: production for production in self.productions
                }
                self.graph.add_edge(analysis_dict[dependency], production)
    
    def update_graph(self):
        """
        Rebuild the dependency graph based on current production dependencies.
        
        This is necessary because dependency queries (e.g., property-based filters)
        are evaluated dynamically and may change as productions are added or modified.
        Call this method before using the graph to ensure edges reflect current state.
        """
        # Clear all edges but keep nodes
        self.graph.clear_edges()
        
        # Rebuild edges based on current dependencies
        analysis_dict = {production.name: production for production in self.productions}
        
        for production in self.productions:
            if production.dependencies:
                for dependency_name in production.dependencies:
                    if dependency_name == production.name:
                        continue
                    if dependency_name in analysis_dict:
                        self.graph.add_edge(analysis_dict[dependency_name], production)

    def __repr__(self):
        return f"<Event {self.name}>"

    @classmethod
    def from_dict(cls, data, update=False, ledger=None):
        """
        Convert a dictionary representation of the event object to an Event object.
        """
        event = cls(**data, update=update, ledger=ledger)
        if ledger:
            ledger.add_event(event)
        return event

    @classmethod
    def from_yaml(cls, data, update=False, repo=True, ledger=None):
        """
                Parse YAML to generate this event.

        |        Parameters
                ----------
                data : str
                   YAML-formatted event specification.
                update : bool
                   Flag to determine if the repository is updated when loaded.
                   Defaults to False.
                ledger : `asimov.ledger.Ledger`
                   An asimov ledger which the event should be included in.

                Returns
                -------
                Event
                   An event.
        """
        data = yaml.safe_load(data)
        if "kind" in data:
            data.pop("kind")
        if (
            not {
                "name",
            }
            <= data.keys()
        ):
            raise DescriptionException(
                "Some of the required parameters are missing from this issue."
            )

        if "productions" in data:
            if isinstance(data["productions"], type(None)):
                data["productions"] = []

        if "working directory" not in data:
            data["working directory"] = os.path.join(
                config.get("general", "rundir_default"), data["name"]
            )

        if not repo and "repository" in data:
            data.pop("repository")
        event = cls.from_dict(data, update=update, ledger=ledger)

        if "productions" in data:
            if isinstance(data["productions"], type(None)):
                data["productions"] = []
        else:
            data["productions"] = []

        if "working directory" not in data:
            data["working directory"] = os.path.join(
                config.get("general", "rundir_default"), data["name"]
            )

        if not repo and "repository" in data:
            data.pop("repository")
        event = cls.from_dict(data, update=update, ledger=ledger)

        return event

    def get_gracedb(self, gfile, destination):
        """
        Get a file from Gracedb, and store it in the event repository.

        Parameters
        ----------
        gfile : str
           The name of the gracedb file, e.g. `coinc.xml`.
        destination : str
           The location in the repository for this file.
        """

        if "preferred event" in self.meta.get("ligo", {}):
            gid = self.meta["ligo"]["preferred event"]
        else:
            raise ValueError("No preferred event GID is included in this event's metadata.")

        try:
            client = GraceDb(service_url=config.get("gracedb", "url"))
            file_obj = client.files(gid, gfile)

            with open("download.file", "w") as dest_file:
                dest_file.write(file_obj.read().decode())

            if "xml" in gfile:
                # Convert to the new xml format
                command = ["ligolw_no_ilwdchar", "download.file"]
                pipe = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                )
                out, err = pipe.communicate()

            self.repository.add_file(
                "download.file",
                destination,
                commit_message=f"Downloaded {gfile} from GraceDB",
            )
            self.logger.info(f"Fetched {gfile} from GraceDB")
        except HTTPError as e:
            self.logger.error(
                f"Unable to connect to GraceDB when attempting to download {gfile}. {e}"
            )
            raise HTTPError(e)

    def to_dict(self, productions=True):
        data = {}
        data["name"] = self.name

        if self.repository.url:
            data["repository"] = self.repository.url
        else:
            data["repository"] = self.repository.directory

        for key, value in self.meta.items():
            data[key] = value
        # try:
        #    data['repository'] = self.repository.url
        # except AttributeError:
        #    pass
        if productions:
            data["productions"] = []
            for production in self.productions:
                # Store production metadata keyed by its name so it can be
                # reconstructed losslessly when reloading the ledger.
                data["productions"].append({production.name: production.to_dict(event=False)})

        data["working directory"] = self.work_dir
        if "ledger" in data:
            data.pop("ledger")
        if "pipelines" in data:
            data.pop("pipelines")
        return data

    def to_yaml(self):
        """Serialise this object as yaml"""
        data = self.to_dict()
        return yaml.dump(data, default_flow_style=False)

    def draw_dag(self):
        """
        Draw the dependency graph for this event.
        """
        return nx.draw(self.graph, labelled=True)

    def get_all_latest(self):
        """
        Get all of the jobs which are not blocked by an unfinished job
        further back in their history.

        Returns
        -------
        set
            A set of independent jobs which are not finished execution.
        """
        # Update graph to reflect current dependencies
        self.update_graph()
        
        unfinished = self.graph.subgraph(
            [
                production
                for production in self.productions
                if (production.finished is False and production.status not in {"wait"})
            ]
        )

        ends = []
        for production in unfinished.reverse().nodes():
            if (
                "needs settings" not in production.meta
                or production.meta["needs settings"] == "default"
            ):
                if (
                    unfinished.reverse().out_degree(production) == 0
                    and production.finished is False
                ):
                    ends.append(production)
            elif "needs settings" in production.meta:
                interested_pipelines = 0

                if (
                    "minimum" in production.meta["needs settings"]
                    and production.meta["needs settings"]["condition"]
                    == "is_interesting"
                ):
                    for prod in unfinished.reverse().nodes():
                        if (
                            prod.pipeline.name != production.pipeline.name
                            and prod.pipeline.name in production._needs
                        ):
                            if prod.meta["interest status"] is True:
                                interested_pipelines += 1

                    if (
                        interested_pipelines
                        >= production.meta["needs settings"]["minimum"]
                    ):
                        ends.append(production)

        ready_values = {end for end in ends if end.status.lower() == "ready"}

        return set(ready_values)  # only want to return one version of each production!

    def build_report(self):
        for production in self.productions:
            production.build_report()

    def html(self):
        card = f"""
        <div class="card event-data" id="card-{self.name}" data-event-name="{self.name}">
        <div class="card-body">
        <h3 class="card-title event-toggle">{self.name}</h3>
        """

        # Add event metadata if available
        if hasattr(self, 'meta') and self.meta:
            if "gps" in self.meta:
                card += f"""<p class="text-muted">GPS Time: {self.meta['gps']}</p>"""
            if "interferometers" in self.meta:
                ifos = ", ".join(self.meta["interferometers"]) if isinstance(self.meta["interferometers"], list) else self.meta["interferometers"]
                card += f"""<p class="text-muted">Interferometers: {ifos}</p>"""

        # Generate graph-based workflow visualization
        if hasattr(self, 'graph') and self.graph and len(self.graph.nodes()) > 0:
            # Update graph to reflect current dependencies (important for property-based queries)
            self.update_graph()
            
            card += """<div class="workflow-graph">"""
            card += """<h4>Workflow Graph</h4>"""
            
            try:
                import networkx as nx
                from asimov.event import status_map
                
                # Organize nodes by dependency layers
                if nx.is_directed_acyclic_graph(self.graph):
                    # Get layers using topological generations
                    layers = list(nx.topological_generations(self.graph))
                    
                    card += """<div class="graph-container">"""
                    
                    for layer_idx, layer in enumerate(layers):
                        card += """<div class="graph-layer">"""
                        
                        for node in layer:
                            # Get status and review for styling
                            status = node.status if hasattr(node, 'status') else 'unknown'
                            review_status = 'none'
                            if hasattr(node, 'review') and len(node.review) > 0:
                                review_status = node.review[0].status if hasattr(node.review[0], 'status') else 'none'
                            
                            status_badge = status_map.get(status, 'secondary')
                            
                            # Get pipeline name
                            pipeline_name = node.pipeline.name if hasattr(node, 'pipeline') and node.pipeline else ''
                            
                            # Get dependencies (predecessors in the graph)
                            predecessors = list(self.graph.predecessors(node))
                            predecessor_names = ','.join([pred.name for pred in predecessors]) if predecessors else ''
                            
                            # Get dependents (successors in the graph)
                            successors = list(self.graph.successors(node))
                            successor_names = ','.join([succ.name for succ in successors]) if successors else ''
                            
                            # Create graph node with click handler
                            # Add running indicator for active analyses
                            running_indicator = ''
                            if status in ['running', 'processing']:
                                running_indicator = '<span class="graph-running-indicator"></span>'
                            
                            card += f"""
                            <div class="graph-node status-{status}" 
                                 id="node-{node.name}"
                                 data-review="{review_status}" 
                                 data-status="{status}"
                                 data-node-name="{node.name}"
                                 data-predecessors="{predecessor_names}"
                                 data-successors="{successor_names}"
                                 onclick="openAnalysisModal('{node.name}')">
                                {running_indicator}
                                <div class="graph-node-title">{node.name}</div>
                                <div class="graph-node-subtitle">{pipeline_name}</div>
                            </div>
                            """
                            
                            # Add hidden data container for modal
                            comment = node.comment if hasattr(node, 'comment') and node.comment else ''
                            rundir = node.rundir if hasattr(node, 'rundir') and node.rundir else ''
                            approximant = node.meta.get('approximant', '') if hasattr(node, 'meta') else ''
                            
                            # Get current dependencies
                            dependencies = node.dependencies if hasattr(node, 'dependencies') else []
                            dependencies_str = ', '.join(dependencies) if dependencies else ''
                            
                            card += f"""
                            <div id="analysis-data-{node.name}" style="display:none;"
                                 data-name="{node.name}"
                                 data-status="{status}"
                                 data-status-badge="{status_badge}"
                                 data-pipeline="{pipeline_name}"
                                 data-rundir="{rundir}"
                                 data-approximant="{approximant}"
                                 data-comment="{comment}"
                                 data-dependencies="{dependencies_str}">
                            </div>
                            """
                        
                        card += """</div>"""
                        
                        # Add arrow between layers
                        if layer_idx < len(layers) - 1:
                            card += """<div class="graph-arrow">→</div>"""
                    
                    card += """</div>"""
                    
                else:
                    # Fallback for non-DAG: just list nodes
                    card += """<div class="graph-container">"""
                    card += """<div class="graph-layer">"""
                    for node in self.graph.nodes():
                        status = node.status if hasattr(node, 'status') else 'unknown'
                        status_badge = status_map.get(status, 'secondary')
                        pipeline_name = node.pipeline.name if hasattr(node, 'pipeline') and node.pipeline else ''
                        
                        review_status = 'none'
                        if hasattr(node, 'review') and len(node.review) > 0:
                            review_status = node.review[0].status if hasattr(node.review[0], 'status') else 'none'
                        
                        # Get dependencies even for non-DAG
                        predecessors = list(self.graph.predecessors(node)) if hasattr(self.graph, 'predecessors') else []
                        predecessor_names = ','.join([pred.name for pred in predecessors]) if predecessors else ''
                        
                        successors = list(self.graph.successors(node)) if hasattr(self.graph, 'successors') else []
                        successor_names = ','.join([succ.name for succ in successors]) if successors else ''
                        
                        # Add running indicator for active analyses
                        running_indicator = ''
                        if status in ['running', 'processing']:
                            running_indicator = '<span class="graph-running-indicator"></span>'
                        
                        card += f"""
                        <div class="graph-node status-{status}" 
                             id="node-{node.name}"
                             data-review="{review_status}"
                             data-status="{status}"
                             data-node-name="{node.name}"
                             data-predecessors="{predecessor_names}"
                             data-successors="{successor_names}"
                             onclick="openAnalysisModal('{node.name}')">
                            {running_indicator}
                            <div class="graph-node-title">{node.name}</div>
                            <div class="graph-node-subtitle">{pipeline_name}</div>
                        </div>
                        """
                        
                        comment = node.comment if hasattr(node, 'comment') and node.comment else ''
                        rundir = node.rundir if hasattr(node, 'rundir') and node.rundir else ''
                        approximant = node.meta.get('approximant', '') if hasattr(node, 'meta') else ''
                        
                        # Get current dependencies
                        dependencies = node.dependencies if hasattr(node, 'dependencies') else []
                        dependencies_str = ', '.join(dependencies) if dependencies else ''
                        
                        card += f"""
                        <div id="analysis-data-{node.name}" style="display:none;"
                             data-name="{node.name}"
                             data-status="{status}"
                             data-status-badge="{status_badge}"
                             data-pipeline="{pipeline_name}"
                             data-rundir="{rundir}"
                             data-approximant="{approximant}"
                             data-comment="{comment}"
                             data-dependencies="{dependencies_str}">
                        </div>
                        """
                    card += """</div>"""
                    card += """</div>"""
                    
            except Exception as e:
                card += f"""<p class="text-muted">Error rendering graph: {str(e)}</p>"""
            
            card += """</div>"""

        # card += """
        # </div></div>
        # """

        return card


Production = GravitationalWaveTransient
