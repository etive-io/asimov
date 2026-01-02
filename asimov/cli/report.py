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
            background-color: #f5f7fa;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }

        .review-deprecated.hidden, .status-cancelled.hidden, .review-rejected.hidden {
            display: none !important;
        }

        .event-data {
            margin: 1rem;
            margin-bottom: 2rem;
            border: 1px solid #e1e4e8;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
            background-color: white;
        }

        .asimov-sidebar {
            position: sticky;
            top: 4rem;
            height: calc(100vh - 4rem);
            overflow-y: auto;
            background-color: white;
            padding: 1rem;
            border-right: 1px solid #e1e4e8;
        }

        .asimov-summary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            margin-bottom: 2rem;
            border-radius: 0.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .asimov-summary h2 {
            margin-bottom: 1rem;
            font-weight: 600;
        }

        .summary-stats {
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            margin-top: 1rem;
        }

        .stat-box {
            background: rgba(255,255,255,0.2);
            padding: 1rem;
            border-radius: 0.3rem;
            min-width: 120px;
        }

        .stat-box .stat-number {
            font-size: 2rem;
            font-weight: bold;
            display: block;
        }

        .stat-box .stat-label {
            font-size: 0.9rem;
            opacity: 0.9;
        }

        .filter-controls {
            background-color: white;
            padding: 1rem;
            margin-bottom: 1rem;
            border-radius: 0.5rem;
            border: 1px solid #e1e4e8;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }

        .filter-controls h5 {
            margin-bottom: 0.75rem;
            font-weight: 600;
            color: #24292e;
        }

        .filter-btn {
            margin: 0.25rem;
        }

        .asimov-analysis {
            padding: 1rem;
            background: #ffffff;
            margin: 0.75rem 0;
            border-radius: 0.5rem;
            border-left: 4px solid #6c757d;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            position: relative;
        }

        .asimov-analysis:hover {
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            transform: translateX(2px);
        }

        .asimov-analysis-running, .asimov-analysis-processing {
            background: #e7f3ff;
            border-left-color: #0366d6;
        }

        .asimov-analysis-finished, .asimov-analysis-uploaded {
            background: #e6f7ed;
            border-left-color: #28a745;
        }

        .asimov-analysis-stuck {
            background: #fff8e6;
            border-left-color: #ffc107;
        }

        .asimov-analysis-cancelled, .asimov-analysis-stopped {
            background: #f6f8fa;
            border-left-color: #6c757d;
            opacity: 0.7;
        }

        .asimov-analysis-stop {
            background: #ffe6e6;
            border-left-color: #dc3545;
        }

        .asimov-status {
            position: absolute;
            top: 1rem;
            right: 1rem;
        }

        .asimov-analysis h4 {
            margin-bottom: 0.5rem;
            font-weight: 600;
            color: #24292e;
            padding-right: 120px;
        }

        .asimov-comment {
            font-size: 0.9rem;
            font-style: italic;
        }

        .asimov-details {
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid #e1e4e8;
        }

        .asimov-pipeline-name {
            font-weight: 500;
            color: #586069;
            margin: 0.5rem 0;
        }

        .asimov-rundir {
            font-size: 0.85rem;
            color: #586069;
            background: #f6f8fa;
            padding: 0.5rem;
            border-radius: 0.25rem;
            margin-top: 0.5rem;
        }

        .asimov-attribute {
            font-size: 0.9rem;
            color: #586069;
            margin: 0.25rem 0;
        }

        .toggle-details {
            cursor: pointer;
            color: #0366d6;
            font-size: 0.9rem;
            margin-top: 0.5rem;
            display: inline-block;
        }

        .toggle-details:hover {
            text-decoration: underline;
        }

        .details-content {
            margin-top: 1rem;
            display: none;
        }

        .details-content.show {
            display: block;
        }

        .running-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #28a745;
            animation: pulse 2s ease-in-out infinite;
            margin-right: 0.5rem;
        }

        @keyframes pulse {
            0%, 100% {
                opacity: 1;
            }
            50% {
                opacity: 0.3;
            }
        }

        .workflow-flow {
            margin: 1rem 0;
            padding: 1rem;
            background: #f6f8fa;
            border-radius: 0.5rem;
        }

        .flow-step {
            display: inline-block;
            padding: 0.5rem 1rem;
            background: white;
            border: 1px solid #e1e4e8;
            border-radius: 0.25rem;
            margin: 0.25rem;
            font-size: 0.9rem;
        }

        .flow-arrow {
            display: inline-block;
            margin: 0 0.5rem;
            color: #586069;
        }

        .badge {
            font-size: 0.85rem;
            padding: 0.35em 0.65em;
        }
</style>
        """
        report + style

        script = """
<script type="text/javascript">
    window.onload = function() {
        setupRefresh();
        initializeFilters();
        initializeToggles();
        calculateStats();
    };

    function setupRefresh() {
      setTimeout("refreshPage();", 1000*60*15); // milliseconds
    }
    
    function refreshPage() {
       window.location = location.href;
    }

    function initializeFilters() {
        // Filter by status
        document.querySelectorAll('.filter-status').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var status = this.getAttribute('data-status');
                var analyses = document.querySelectorAll('.asimov-analysis');
                
                if (this.classList.contains('active')) {
                    // Deactivate filter - show all
                    analyses.forEach(function(analysis) {
                        analysis.style.display = '';
                    });
                    this.classList.remove('active');
                } else {
                    // Activate filter
                    document.querySelectorAll('.filter-status').forEach(function(b) {
                        b.classList.remove('active');
                    });
                    this.classList.add('active');
                    
                    analyses.forEach(function(analysis) {
                        if (analysis.classList.contains('asimov-analysis-' + status)) {
                            analysis.style.display = '';
                        } else {
                            analysis.style.display = 'none';
                        }
                    });
                }
            });
        });

        // Toggle cancelled/rejected
        var hideCancelledBtn = document.getElementById('hide-cancelled');
        if (hideCancelledBtn) {
            hideCancelledBtn.addEventListener('click', function() {
                this.classList.toggle('active');
                var analyses = document.querySelectorAll('.asimov-analysis-cancelled, .asimov-analysis-stopped');
                analyses.forEach(function(analysis) {
                    if (hideCancelledBtn.classList.contains('active')) {
                        analysis.classList.add('hidden');
                    } else {
                        analysis.classList.remove('hidden');
                    }
                });
                var reviews = document.querySelectorAll('.review-deprecated, .review-rejected');
                reviews.forEach(function(review) {
                    if (hideCancelledBtn.classList.contains('active')) {
                        review.classList.add('hidden');
                    } else {
                        review.classList.remove('hidden');
                    }
                });
            });
            // Auto-hide on page load
            hideCancelledBtn.click();
        }

        // Show all button
        var showAllBtn = document.getElementById('show-all');
        if (showAllBtn) {
            showAllBtn.addEventListener('click', function() {
                document.querySelectorAll('.filter-status').forEach(function(b) {
                    b.classList.remove('active');
                });
                document.querySelectorAll('.asimov-analysis').forEach(function(analysis) {
                    analysis.style.display = '';
                    analysis.classList.remove('hidden');
                });
            });
        }
    }

    function initializeToggles() {
        document.querySelectorAll('.toggle-details').forEach(function(toggle) {
            toggle.addEventListener('click', function() {
                var content = this.nextElementSibling;
                if (content && content.classList.contains('details-content')) {
                    content.classList.toggle('show');
                    this.textContent = content.classList.contains('show') ? '▼ Hide details' : '▶ Show details';
                }
            });
        });
    }

    function calculateStats() {
        var stats = {
            total: 0,
            running: 0,
            finished: 0,
            stuck: 0,
            cancelled: 0
        };

        document.querySelectorAll('.asimov-analysis').forEach(function(analysis) {
            stats.total++;
            if (analysis.classList.contains('asimov-analysis-running') || 
                analysis.classList.contains('asimov-analysis-processing')) {
                stats.running++;
            } else if (analysis.classList.contains('asimov-analysis-finished') || 
                       analysis.classList.contains('asimov-analysis-uploaded')) {
                stats.finished++;
            } else if (analysis.classList.contains('asimov-analysis-stuck')) {
                stats.stuck++;
            } else if (analysis.classList.contains('asimov-analysis-cancelled') || 
                       analysis.classList.contains('asimov-analysis-stopped')) {
                stats.cancelled++;
            }
        });

        // Update stat displays if they exist
        if (document.getElementById('stat-total')) {
            document.getElementById('stat-total').textContent = stats.total;
        }
        if (document.getElementById('stat-running')) {
            document.getElementById('stat-running').textContent = stats.running;
        }
        if (document.getElementById('stat-finished')) {
            document.getElementById('stat-finished').textContent = stats.finished;
        }
        if (document.getElementById('stat-stuck')) {
            document.getElementById('stat-stuck').textContent = stats.stuck;
        }
        if (document.getElementById('stat-cancelled')) {
            document.getElementById('stat-cancelled').textContent = stats.cancelled;
        }
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
    
    # Build summary dashboard
    summary = """
    <div class='container-fluid'>
        <div class='asimov-summary'>
            <h2>Project Summary</h2>
            <div class='summary-stats'>
                <div class='stat-box'>
                    <span class='stat-number' id='stat-total'>0</span>
                    <span class='stat-label'>Total Analyses</span>
                </div>
                <div class='stat-box'>
                    <span class='stat-number' id='stat-running'>0</span>
                    <span class='stat-label'>Running</span>
                </div>
                <div class='stat-box'>
                    <span class='stat-number' id='stat-finished'>0</span>
                    <span class='stat-label'>Finished</span>
                </div>
                <div class='stat-box'>
                    <span class='stat-number' id='stat-stuck'>0</span>
                    <span class='stat-label'>Stuck</span>
                </div>
                <div class='stat-box'>
                    <span class='stat-number' id='stat-cancelled'>0</span>
                    <span class='stat-label'>Cancelled</span>
                </div>
            </div>
        </div>
    </div>
    """
    
    # Build filter controls
    filters = """
    <div class='container-fluid'>
        <div class='filter-controls'>
            <h5>Filters</h5>
            <button class='btn btn-sm btn-outline-secondary filter-btn' id='show-all'>Show All</button>
            <button class='btn btn-sm btn-outline-primary filter-btn filter-status' data-status='running'>Running</button>
            <button class='btn btn-sm btn-outline-success filter-btn filter-status' data-status='finished'>Finished</button>
            <button class='btn btn-sm btn-outline-warning filter-btn filter-status' data-status='stuck'>Stuck</button>
            <button class='btn btn-sm btn-outline-danger filter-btn filter-status' data-status='stop'>Stopped</button>
            <button class='btn btn-sm btn-outline-secondary filter-btn' id='hide-cancelled'>Hide Cancelled</button>
        </div>
    </div>
    """
    
    cards = summary + filters
    cards += "<div class='container-fluid'><div class='row'><div class='col-12 col-md-3 col-xl-2  asimov-sidebar'>"

    toc = """<nav><h6>Subjects</h6><ul class="list-unstyled">"""
    for event in events:
        toc += f"""<li><a href="#card-{event.name}">{event.name}</a></li>"""

    toc += "</ul></nav>"

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
