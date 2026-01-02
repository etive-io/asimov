"""
Reporting functions
"""

from datetime import datetime

import os

import click
import pytz
import yaml
from pkg_resources import resource_filename

import otter
import otter.bootstrap as bt

from asimov import config, current_ledger

tz = pytz.timezone("Europe/London")


@click.group()
def report():
    """Produce reports about the state of the project."""
    pass


@click.option(
    "--location", "webdir", default=None, help="The place to save the report to"
)
@click.argument("event", default=None, required=False)
@report.command()
def html(event, webdir):
    """
    Return the ledger for a given event.
    If no event is specified then the entire production ledger is returned.
    """

    events = current_ledger.get_event(event)

    if not webdir:
        webdir = config.get("general", "webroot")

    report = otter.Otter(
        f"{webdir}/index.html",
        author="Asimov",
        title="Asimov project report",
        theme_location=resource_filename("asimov.cli", "report-theme"),
        config_file=os.path.join(".asimov", "asimov.conf"),
    )
    with report:

        style = """
<style>
        body {
        background-color: #f2f2f2;
        }

        .event-data {
        margin: 1rem;
        margin-bottom: 2rem;
        }

        .asimov-sidebar {
        position: sticky;
        top: 4rem;
        height: calc(100vh - 4rem);
        overflow-y: auto;
        }

        .asimov-analysis {
        padding: 1rem;
        background: lavenderblush;
        margin: 0.5rem;
        border-radius: 0.5rem;
        position: relative;
        }

        .asimov-analysis-running, .asimov-analysis-processing {
        background: #DEEEFF;
        }

        .asimov-analysis-finished, .asimov-analysis-uploaded {
        background: #E1EDE4;
        }
        .asimov-analysis-stuck {
        background: #FFF5D9;
        }

        .asimov-status {
        float: right;
        clear: both;
        }

        /* Review status visual indicators */
        .review-approved-badge {
        position: absolute;
        top: 10px;
        right: 10px;
        width: 30px;
        height: 30px;
        background-color: #28a745;
        color: white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        font-weight: bold;
        z-index: 10;
        }

        .review-rejected-overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: repeating-linear-gradient(
            45deg,
            transparent,
            transparent 10px,
            rgba(220, 53, 69, 0.1) 10px,
            rgba(220, 53, 69, 0.1) 20px
        );
        pointer-events: none;
        border-radius: 0.5rem;
        }

        .review-rejected-overlay::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(to bottom right, 
            transparent calc(50% - 2px), 
            rgba(220, 53, 69, 0.8) calc(50% - 2px), 
            rgba(220, 53, 69, 0.8) calc(50% + 2px), 
            transparent calc(50% + 2px));
        }

        /* Filter controls */
        .review-filters {
        margin: 1rem 0;
        padding: 1rem;
        background-color: white;
        border-radius: 0.5rem;
        }

        .review-filters .btn {
        margin: 0.25rem;
        }

        /* Filter states - hidden by default based on active filters */
        .asimov-analysis.filter-hidden {
        display: none !important;
        }
</style>
        """
        report + style

        script = """
<script type="text/javascript">
    window.onload = function() {
        setupRefresh();
        setupFilters();
    };

    function setupRefresh() {
      setTimeout("refreshPage();", 1000*60*15); // milliseconds
    }
    function refreshPage() {
       window.location = location.href;
    }

    function setupFilters() {
        // Get all filter buttons
        const filterButtons = document.querySelectorAll('.filter-btn');
        
        filterButtons.forEach(button => {
            button.addEventListener('click', function() {
                const filter = this.getAttribute('data-filter');
                
                // Update active button state
                filterButtons.forEach(btn => btn.classList.remove('active'));
                this.classList.add('active');
                
                // Get all analyses
                const analyses = document.querySelectorAll('.asimov-analysis');
                
                analyses.forEach(analysis => {
                    if (filter === 'all') {
                        analysis.classList.remove('filter-hidden');
                    } else if (filter === 'approved') {
                        if (analysis.classList.contains('review-approved')) {
                            analysis.classList.remove('filter-hidden');
                        } else {
                            analysis.classList.add('filter-hidden');
                        }
                    } else if (filter === 'rejected') {
                        if (analysis.classList.contains('review-rejected')) {
                            analysis.classList.remove('filter-hidden');
                        } else {
                            analysis.classList.add('filter-hidden');
                        }
                    } else if (filter === 'deprecated') {
                        if (analysis.classList.contains('review-deprecated')) {
                            analysis.classList.remove('filter-hidden');
                        } else {
                            analysis.classList.add('filter-hidden');
                        }
                    } else if (filter === 'no-review') {
                        // Show analyses that don't have any review class
                        if (!analysis.classList.contains('review-approved') && 
                            !analysis.classList.contains('review-rejected') && 
                            !analysis.classList.contains('review-deprecated')) {
                            analysis.classList.remove('filter-hidden');
                        } else {
                            analysis.classList.add('filter-hidden');
                        }
                    }
                });
            });
        });
    }
</script>
        """
        report + script
    with report:
        navbar = bt.Navbar(
            f"Asimov  |  {current_ledger.data['project']['name']}",
            background="navbar-dark bg-primary",
        )
        report + navbar

    events = sorted(events, key=lambda a: a.name)
    cards = "<div class='container-fluid'><div class='row'><div class='col-12 col-md-3 col-xl-2  asimov-sidebar'>"

    toc = """<nav><h6>Subjects</h6><ul class="list-unstyled">"""
    for event in events:
        toc += f"""<li><a href="#card-{event.name}">{event.name}</a></li>"""

    toc += """</ul></nav>"""
    
    # Add review filter buttons
    toc += """
    <div class="review-filters">
        <h6>Review Filters</h6>
        <button class="btn btn-sm btn-primary filter-btn active" data-filter="all">All</button>
        <button class="btn btn-sm btn-success filter-btn" data-filter="approved">Approved</button>
        <button class="btn btn-sm btn-danger filter-btn" data-filter="rejected">Rejected</button>
        <button class="btn btn-sm btn-warning filter-btn" data-filter="deprecated">Deprecated</button>
        <button class="btn btn-sm btn-secondary filter-btn" data-filter="no-review">No Review</button>
    </div>
    """

    cards += toc
    cards += """</div><div class='events col-md-9 col-xl-10'
    data-isotope='{ "itemSelector": ".production-item", "layoutMode": "fitRows" }'>"""

    for event in events:
        card = ""
        # This is a quick test to try and improve readability
        card += event.html()

        # card += """<p class="card-text">Card text</p>""" #
        card += """
</div>
</div>"""
        cards += card

    cards += "</div></div>"
    with report:
        report + cards

    with report:
        time = f"Report generated at {datetime.now(tz):%Y-%m-%d %H:%M}"
        report + time


@click.argument("event", default=None, required=False)
@report.command()
def status(event):
    """
    Provide a simple summary of the status of a given event.

    Arguments
    ---------
    name : str, optional
       The name of the event.

    """
    for event in sorted(current_ledger.get_event(event), key=lambda e: e.name):
        click.secho(f"{event.name:30}", bold=True)
        if len(event.productions) > 0:
            click.secho("\tAnalyses", bold=True)
            if len(event.productions) == 0:
                click.echo("\t<NONE>")
            for production in event.productions:
                click.echo(
                    f"\t- {production.name} "
                    + click.style(f"{production.pipeline}")
                    + " "
                    + click.style(f"{production.status}")
                )
        if len(event.get_all_latest()) > 0:
            click.secho(
                "\tAnalyses waiting: ",
                bold=True,
            )
            waiting = event.get_all_latest()
            for awaiting in waiting:
                click.echo(
                    f"{awaiting.name} ",
                )
            click.echo("")


@click.option(
    "--yaml", "yaml_f", default=None, help="A YAML file to save the ledger to."
)
@click.argument("event", default=None, required=False)
@report.command()
def ledger(event, yaml_f):
    """
    Return the ledger for a given event.
    If no event is specified then the entire production ledger is returned.
    """
    total = []
    for event in current_ledger.get_event(event):
        total.append(yaml.safe_load(event.to_yaml()))

    click.echo(yaml.dump(total))

    if yaml_f:
        with open(yaml_f, "w") as f:
            f.write(yaml.dump(total))
