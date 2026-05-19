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

        # pathlib.Path(os.path.join(config.get("logging", "location"), name)).mkdir(
        #    parents=True, exist_ok=True
        # )
        # logfile = os.path.join(config.get("logging", "location"), name, "asimov.log")

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
        # After all productions are added, update the graph to build dependency edges
        # This ensures dependencies can be resolved regardless of order in the ledger
        self.update_graph()
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

        # Note: Dependencies are resolved dynamically when accessed, so we don't
        # build edges here. Instead, call update_graph() after all productions
        # are added to ensure the graph reflects current dependencies.
        # This fixes the issue where dependencies appearing later in the ledger
        # couldn't be found during initial loading.
    
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

        # Re-resolve SubjectAnalysis dependencies now that all productions are loaded
        # This ensures smart dependencies work correctly regardless of production order
        from asimov.analysis import SubjectAnalysis
        for production in self.productions:
            if isinstance(production, SubjectAnalysis):
                production.resolve_analyses()

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
        # Helper function to get review info from a node
        def get_review_info(node):
            """Extract review status and message from a node."""
            review_status = 'none'
            review_message = ''
            if hasattr(node, 'review') and len(node.review) > 0:
                # Get the latest review message (Review class implements __getitem__)
                latest_review = node.review[-1]
                if latest_review:
                    review_status = latest_review.status.lower() if latest_review.status else 'none'
                    review_message = latest_review.message if latest_review.message else ''
            return review_status, review_message
        
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

        # Generate graph-based workflow visualization (Mermaid + ELK)
        if hasattr(self, 'graph') and self.graph and len(self.graph.nodes()) > 0:
            self.update_graph()

            import re
            import json as _json

            _REVIEW_PREFIX = {'approved': '✓ ', 'rejected': '✗ ', 'deprecated': '⊘ '}

            def _safe_token(name):
                """Sanitise a string into a token for Mermaid/DOM identifiers."""
                return re.sub(r'[^a-zA-Z0-9_]', '_', str(name))

            def _safe_dom_id(*parts):
                dom_id = '-'.join(str(part) for part in parts if part is not None)
                dom_id = re.sub(r'[^a-zA-Z0-9_-]', '-', dom_id).strip('-')
                return dom_id or 'analysis-data'

            def _escape_mermaid_label(value):
                return (str(value)
                        .replace('\\', '\\\\')
                        .replace('"', '\\"')
                        .replace('\r', ' ')
                        .replace('\n', ' '))

            card += f'<div class="workflow-graph" data-event-name="{self.name}">'
            card += '<h4>Workflow Graph</h4>'
            container_id = f'mermaid-{_safe_dom_id(self.name)}'
            card += f'<div id="{container_id}" class="mermaid-container"></div>'

            node_data_id_by_node = {}
            try:
                nodes_data = []
                node_map = {}
                node_mid_by_node = {}
                event_prefix = f'event_{_safe_token(self.name)}'
                for idx, node in enumerate(self.graph.nodes()):
                    mid = f'{event_prefix}_{_safe_token(node.name)}_{idx}'
                    data_id = _safe_dom_id('analysis-data', self.name, node.name, idx)
                    node_mid_by_node[node] = mid
                    node_data_id_by_node[node] = data_id
                    node_map[mid] = data_id
                    status = (node.status or 'unknown') if hasattr(node, 'status') else 'unknown'
                    review_status, _ = get_review_info(node)
                    pipeline_name = (node.pipeline.name
                                     if hasattr(node, 'pipeline') and node.pipeline else '')
                    prefix = _REVIEW_PREFIX.get(review_status, '')
                    label = _escape_mermaid_label(f'{prefix}{node.name}\\n{pipeline_name}')
                    is_subject = (getattr(node, 'category', '') == 'subject_analyses')
                    nodes_data.append({
                        'id': mid,
                        'label': label,
                        'status': status,
                        'review': review_status,
                        'isSubject': is_subject,
                        'dataId': data_id,
                    })

                edges_data = [{'from': node_mid_by_node[s], 'to': node_mid_by_node[t]}
                              for s, t in self.graph.edges()
                              if s in node_mid_by_node and t in node_mid_by_node]

                event_name_js = _json.dumps(self.name)
                container_id_js = _json.dumps(container_id)
                nodes_js = _json.dumps(nodes_data)
                edges_js = _json.dumps(edges_data)
                node_map_js = _json.dumps(node_map)

                card += f"""<script>
window.asimovGraphs = window.asimovGraphs || {{}};
window.asimovGraphs[{event_name_js}] = {{
  containerId: {container_id_js},
  nodes: {nodes_js},
  edges: {edges_js}
}};
window.asimovNodeMap = window.asimovNodeMap || {{}};
Object.assign(window.asimovNodeMap, {node_map_js});
</script>"""

            except Exception as e:
                card += f'<p class="text-muted">Error generating graph data: {str(e)}</p>'

            # Hidden data containers for modal — one per analysis node
            try:
                import os as _os

                for node in self.graph.nodes():
                    status = node.status if hasattr(node, 'status') else 'unknown'
                    review_status, review_message = get_review_info(node)
                    status_badge = status_map.get(status, 'secondary')
                    pipeline_name = (node.pipeline.name
                                     if hasattr(node, 'pipeline') and node.pipeline else '')
                    data_id = node_data_id_by_node.get(
                        node, _safe_dom_id('analysis-data', self.name, node.name)
                    )

                    comment = node.comment if hasattr(node, 'comment') and node.comment else ''
                    rundir = node.rundir if hasattr(node, 'rundir') and node.rundir else ''
                    approximant = (node.meta.get('approximant', '')
                                   if hasattr(node, 'meta') else '')

                    webdir = ''
                    if hasattr(node, 'event') and hasattr(node.event, 'webdir') and node.event.webdir:
                        webdir = node.event.webdir

                    result_pages = []
                    if webdir and rundir:
                        rundir_name = _os.path.basename(rundir.rstrip('/'))
                        base_url = f"{webdir}/{rundir_name}"
                        if pipeline_name.lower() == 'bilby':
                            result_pages.append(f"{base_url}/result/homepage.html|Bilby Results")
                            result_pages.append(f"{base_url}/result/corner.png|Corner Plot")
                        elif pipeline_name.lower() == 'bayeswave':
                            result_pages.append(f"{base_url}/post/megaplot.png|Bayeswave Megaplot")
                        elif pipeline_name.lower() == 'pesummary':
                            result_pages.append(f"{base_url}/home.html|PESummary Results")

                    result_pages_str = ';;'.join(result_pages)
                    dependencies = node.dependencies if hasattr(node, 'dependencies') else []
                    dependencies_str = ', '.join(dependencies) if dependencies else ''
                    review_message_escaped = (review_message
                                              .replace('"', '&quot;')
                                              .replace("'", '&#39;'))

                    card += f"""<div id="{data_id}" style="display:none;"
                         data-name="{node.name}"
                         data-status="{status}"
                         data-status-badge="{status_badge}"
                         data-pipeline="{pipeline_name}"
                         data-rundir="{rundir}"
                         data-approximant="{approximant}"
                         data-comment="{comment}"
                         data-dependencies="{dependencies_str}"
                         data-review-status="{review_status}"
                         data-review-message="{review_message_escaped}"
                         data-result-pages="{result_pages_str}"></div>"""

            except Exception as e:
                card += f'<p class="text-muted">Error generating modal data: {str(e)}</p>'

            card += '</div>'

        # card += """
        # </div></div>
        # """

        return card


Production = GravitationalWaveTransient
