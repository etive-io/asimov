"""
Reporting functions
"""

from datetime import datetime

import os

import click
import pytz
import yaml
try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files

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
        theme_location=str(files("asimov.cli").joinpath("report-theme")),
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
            background-color: #0366d6;
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

        /* Review status indicators */
        .review-indicator {
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            display: inline-block;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            text-align: center;
            line-height: 24px;
            font-weight: bold;
            font-size: 1rem;
            z-index: 10;
        }

        .review-indicator.review-approved {
            background-color: #28a745;
            color: white;
        }

        .review-indicator.review-rejected {
            background-color: #dc3545;
            color: white;
        }

        .review-indicator.review-deprecated {
            background-color: #ffc107;
            color: #333;
        }

        /* Visual indicators for rejected analyses */
        .graph-node.review-rejected::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(to bottom right, transparent 45%, #dc3545 47%, #dc3545 53%, transparent 55%);
            pointer-events: none;
            opacity: 0.5;
        }

        .graph-node.review-deprecated {
            opacity: 0.6;
        }

        .asimov-analysis.review-rejected::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(to bottom right, transparent 45%, #dc3545 47%, #dc3545 53%, transparent 55%);
            pointer-events: none;
            opacity: 0.3;
        }

        .asimov-analysis.review-deprecated {
            opacity: 0.6;
        }

        /* Stale analysis indicators */
        .stale-indicator {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 600;
            margin-left: 0.5rem;
            text-transform: uppercase;
        }

        .stale-indicator.stale {
            background-color: #ffeaa7;
            color: #d63031;
            border: 1px solid #fdcb6e;
        }

        .stale-indicator.stale-refreshable {
            background-color: #74b9ff;
            color: #0984e3;
            border: 1px solid #0984e3;
        }

        /* Dependency information styles */
        .asimov-dependencies,
        .asimov-resolved-dependencies {
            font-size: 0.9rem;
            color: #586069;
            margin: 0.5rem 0;
            padding: 0.5rem;
            background: #f6f8fa;
            border-radius: 0.25rem;
        }

        .asimov-resolved-dependencies {
            background: #fff3cd;
            border-left: 3px solid #ffc107;
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

        /* Graph visualization styles */
        .workflow-graph {
            padding: 2rem 1rem;
            background: white;
            border-radius: 0.5rem;
            margin: 1rem 0;
            min-height: 200px;
            position: relative;
        }

        .graph-node {
            display: inline-block;
            padding: 0.75rem 1.25rem;
            background: white;
            border: 2px solid #e1e4e8;
            border-radius: 0.5rem;
            margin: 0.5rem;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            min-width: 120px;
            text-align: center;
        }

        .graph-node:hover {
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            transform: translateY(-2px);
        }

        .graph-node.status-running,
        .graph-node.status-processing {
            border-color: #0366d6;
            background: #e7f3ff;
        }

        .graph-node.status-finished,
        .graph-node.status-uploaded {
            border-color: #28a745;
            background: #e6f7ed;
        }

        .graph-node.status-stuck {
            border-color: #ffc107;
            background: #fff8e6;
        }

        .graph-node.status-stopped,
        .graph-node.status-cancelled {
            border-color: #6c757d;
            background: #f6f8fa;
            opacity: 0.7;
        }

        .graph-node.hidden {
            display: none;
        }

        .graph-node-title {
            font-weight: 600;
            margin-bottom: 0.25rem;
        }

        .graph-node-subtitle {
            font-size: 0.85rem;
            color: #586069;
        }

        .graph-running-indicator {
            position: absolute;
            top: 0.5rem;
            right: 0.5rem;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background-color: #0366d6;
            animation: pulse 2s ease-in-out infinite;
        }

        .graph-container {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: center;
            gap: 2rem;
            position: relative;
        }

        .graph-layer {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.5rem;
            position: relative;
        }

        .graph-arrow {
            font-size: 2rem;
            color: transparent;
            margin: 0 1rem;
            user-select: none;
        }

        /* SVG connection lines */
        .graph-connections {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 0;
        }

        .graph-node {
            position: relative;
            z-index: 1;
        }

        .connection-line {
            fill: none;
            stroke: #586069;
            stroke-width: 2;
            opacity: 0.6;
        }
        
        /* Subject analysis styling */
        .graph-node-subject {
            border-width: 3px;
            border-style: double;
            background: linear-gradient(135deg, #f5f7fa 0%, #e8eef5 100%);
        }
        
        .graph-node-subject .graph-node-title::before {
            content: '◆ ';
            color: #6f42c1;
            font-weight: bold;
        }
        
        /* Stale analysis styling */
        .graph-node-stale {
            border-color: #fd7e14 !important;
            box-shadow: 0 0 0 2px rgba(253, 126, 20, 0.2);
        }
        
        .stale-badge {
            position: absolute;
            top: 0.25rem;
            left: 0.25rem;
            display: inline-block;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background-color: #fd7e14;
            color: white;
            text-align: center;
            line-height: 20px;
            font-size: 0.9rem;
            font-weight: bold;
            z-index: 10;
            animation: rotate 2s linear infinite;
        }
        
        @keyframes rotate {
            from {
                transform: rotate(0deg);
            }
            to {
                transform: rotate(360deg);
            }
        }
        
        /* Subject analysis connection styling - use purple for dependencies */
        .connection-line-subject {
            stroke: #6f42c1;
            stroke-width: 3;
            opacity: 0.7;
        }

        /* Subject analysis source dependency styling - different styles based on source status */
        .connection-edge {
            transition: opacity 0.3s ease;
        }
        
        .connection-edge:hover {
            opacity: 1 !important;
        }
        
        .connection-edge.connection-included .connection-line {
            stroke: #28a745;
            stroke-dasharray: none;
            stroke-width: 2.5;
            opacity: 0.8;
        }
        
        .connection-edge.connection-pending .connection-line {
            stroke: #ffc107;
            stroke-dasharray: 5,5;
            stroke-width: 2.5;
            opacity: 0.7;
            animation: flow 0.6s linear infinite;
        }
        
        .connection-edge.connection-waiting .connection-line {
            stroke: #586069;
            stroke-dasharray: 2,3;
            stroke-width: 2;
            opacity: 0.4;
        }
        
        @keyframes flow {
            to {
                stroke-dashoffset: 10;
            }
        }

        /* Modal styles */
        .modal-backdrop {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1040;
        }

        .modal-backdrop.show {
            display: block;
        }

        .analysis-modal {
            display: none;
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            border-radius: 0.5rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            z-index: 1050;
            max-width: 800px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }

        .analysis-modal.show {
            display: block;
        }

        .modal-header {
            padding: 1.5rem;
            border-bottom: 1px solid #e1e4e8;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .modal-title {
            font-size: 1.5rem;
            font-weight: 600;
            margin: 0;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 2rem;
            line-height: 1;
            cursor: pointer;
            color: #586069;
        }

        .modal-close:hover {
            color: #24292e;
        }

        .modal-body {
            padding: 1.5rem;
        }

        .modal-section {
            margin-bottom: 1.5rem;
        }

        .modal-section h5 {
            font-weight: 600;
            margin-bottom: 0.75rem;
            color: #24292e;
        }

        .modal-section p {
            margin-bottom: 0.5rem;
            color: #586069;
        }

        /* Search box */
        .search-box {
            width: 100%;
            padding: 0.5rem 1rem;
            border: 1px solid #e1e4e8;
            border-radius: 0.5rem;
            font-size: 1rem;
            margin-bottom: 1rem;
        }

        .search-box:focus {
            outline: none;
            border-color: #0366d6;
            box-shadow: 0 0 0 3px rgba(3,102,214,0.1);
        }

        /* Event collapsing */
        .event-data.collapsed .workflow-graph,
        .event-data.collapsed .asimov-analysis {
            display: none;
        }

        .event-data.collapsed .event-toggle::after {
            content: ' (No visible analyses)';
            font-size: 0.9rem;
            color: #586069;
            font-weight: normal;
        }

        .event-toggle {
            cursor: pointer;
            user-select: none;
        }

        .event-toggle:hover {
            color: #0366d6;
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
      setTimeout(refreshPage, 1000*60*15); // Refresh every 15 minutes (in milliseconds)
    }
    
    function refreshPage() {
       window.location = location.href;
    }

    function initializeFilters() {
        // Filter by status
        document.querySelectorAll('.filter-status').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var status = this.getAttribute('data-status');
                var analyses = document.querySelectorAll('.graph-node, .asimov-analysis');
                
                if (this.classList.contains('active')) {
                    // Deactivate filter - show all
                    analyses.forEach(function(analysis) {
                        analysis.style.display = '';
                        analysis.classList.remove('filtered-hidden');
                    });
                    this.classList.remove('active');
                    
                    // Redraw connections after deactivating filter
                    setTimeout(drawGraphConnections, 50);
                    checkEventVisibility();
                } else {
                    // Activate filter
                    document.querySelectorAll('.filter-status').forEach(function(b) {
                        b.classList.remove('active');
                    });
                    this.classList.add('active');
                    
                    analyses.forEach(function(analysis) {
                        var matchesFilter = false;
                        
                        // Check both graph node status classes and legacy analysis classes
                        if (analysis.classList.contains('status-' + status) || 
                            analysis.classList.contains('asimov-analysis-' + status)) {
                            matchesFilter = true;
                        }
                        
                        if (matchesFilter) {
                            analysis.style.display = '';
                            analysis.classList.remove('filtered-hidden');
                        } else {
                            analysis.style.display = 'none';
                            analysis.classList.add('filtered-hidden');
                            
                            // Hide all downstream dependencies
                            hideDownstreamDependencies(analysis);
                        }
                    });
                    
                    // Redraw connections after filtering
                    setTimeout(drawGraphConnections, 50);
                    checkEventVisibility();
                }
            });
        });

        // Toggle cancelled/rejected
        var hideCancelledBtn = document.getElementById('hide-cancelled');
        if (hideCancelledBtn) {
            hideCancelledBtn.addEventListener('click', function() {
                this.classList.toggle('active');
                var analyses = document.querySelectorAll('.graph-node.status-cancelled, .graph-node.status-stopped, .asimov-analysis-cancelled, .asimov-analysis-stopped');
                analyses.forEach(function(analysis) {
                    if (hideCancelledBtn.classList.contains('active')) {
                        analysis.classList.add('hidden');
                        analysis.style.display = 'none';
                        // Hide downstream dependencies of cancelled analyses
                        hideDownstreamDependencies(analysis);
                    } else {
                        analysis.classList.remove('hidden');
                        analysis.style.display = '';
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
                
                // Redraw connections after hiding cancelled
                setTimeout(drawGraphConnections, 50);
            });
            // Auto-hide on page load
            hideCancelledBtn.click();
        }

        // Show all button
        var showAllBtn = document.getElementById('show-all');
        if (showAllBtn) {
            showAllBtn.addEventListener('click', function() {
                // Clear status filters
                document.querySelectorAll('.filter-status').forEach(function(b) {
                    b.classList.remove('active');
                });

                // Clear review filters
                document.querySelectorAll('.filter-review').forEach(function(b) {
                    b.classList.remove('active');
                });

                // Deactivate "Hide Cancelled" and unhide all related items
                if (hideCancelledBtn) {
                    hideCancelledBtn.classList.remove('active');
                }

                // Show all analyses and remove any hidden state
                document.querySelectorAll('.graph-node, .asimov-analysis').forEach(function(analysis) {
                    analysis.style.display = '';
                    analysis.classList.remove('hidden');
                    analysis.classList.remove('filtered-hidden');
                });

                // Also unhide any reviews that were hidden by "Hide Cancelled"
                document.querySelectorAll('.review-deprecated, .review-rejected').forEach(function(review) {
                    review.classList.remove('hidden');
                });
                
                // Redraw connections after showing all
                setTimeout(drawGraphConnections, 50);
            });
        }
    }

    // Helper function to hide downstream dependencies recursively
    function hideDownstreamDependencies(node) {
        if (!node.dataset || !node.dataset.successors) return;
        
        var successorNames = node.dataset.successors.split(',').filter(function(name) { return name.trim(); });
        var eventName = node.dataset.eventName || '';
        
        successorNames.forEach(function(successorName) {
            var successorNodeId = 'node-' + eventName + '-' + successorName.trim();
            var successorNode = document.getElementById(successorNodeId);
            if (successorNode && successorNode.style.display !== 'none') {
                successorNode.style.display = 'none';
                successorNode.classList.add('filtered-hidden');
                // Recursively hide its dependencies
                hideDownstreamDependencies(successorNode);
            }
        });
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

        // Count both graph nodes and legacy asimov-analysis elements
        var analyses = document.querySelectorAll('.graph-node, .asimov-analysis');
        analyses.forEach(function(analysis) {
            stats.total++;
            
            // Check for graph node status classes
            if (analysis.classList.contains('status-running') || 
                analysis.classList.contains('status-processing') ||
                analysis.classList.contains('asimov-analysis-running') || 
                analysis.classList.contains('asimov-analysis-processing')) {
                stats.running++;
            } else if (analysis.classList.contains('status-finished') || 
                       analysis.classList.contains('status-uploaded') ||
                       analysis.classList.contains('asimov-analysis-finished') || 
                       analysis.classList.contains('asimov-analysis-uploaded')) {
                stats.finished++;
            } else if (analysis.classList.contains('status-stuck') ||
                       analysis.classList.contains('asimov-analysis-stuck')) {
                stats.stuck++;
            } else if (analysis.classList.contains('status-cancelled') || 
                       analysis.classList.contains('status-stopped') ||
                       analysis.classList.contains('asimov-analysis-cancelled') || 
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

    // Modal functionality
    function openAnalysisModal(dataId) {
        var modal = document.getElementById('analysis-modal');
        var backdrop = document.getElementById('modal-backdrop');
        var analysisData = document.getElementById(dataId);
        
        if (modal && backdrop && analysisData) {
            // Populate modal with analysis data
            document.getElementById('modal-analysis-name').textContent = analysisData.dataset.name;
            document.getElementById('modal-analysis-status').textContent = analysisData.dataset.status;
            document.getElementById('modal-analysis-status').className = 'badge badge-' + analysisData.dataset.statusBadge;
            document.getElementById('modal-analysis-pipeline').textContent = analysisData.dataset.pipeline;
            
            // Populate review status
            var reviewStatus = analysisData.dataset.reviewStatus || 'none';
            var reviewMessage = analysisData.dataset.reviewMessage || '';
            var reviewBadge = document.getElementById('modal-review-status');
            var reviewMessageEl = document.getElementById('modal-review-message');
            
            // Map review status to badge classes
            var reviewBadgeMap = {
                'approved': 'badge-success',
                'rejected': 'badge-danger',
                'deprecated': 'badge-warning',
                'checked': 'badge-info',
                'none': 'badge-secondary'
            };
            
            var reviewLabelMap = {
                'approved': 'Approved',
                'rejected': 'Rejected',
                'deprecated': 'Deprecated',
                'checked': 'Checked',
                'none': 'No Review'
            };
            
            reviewBadge.textContent = reviewLabelMap[reviewStatus] || 'No Review';
            reviewBadge.className = 'badge ' + (reviewBadgeMap[reviewStatus] || 'badge-secondary');
            
            if (reviewMessage) {
                reviewMessageEl.textContent = reviewMessage;
                reviewMessageEl.style.display = 'block';
            } else {
                reviewMessageEl.style.display = 'none';
            }
            
            if (analysisData.dataset.rundir) {
                document.getElementById('modal-analysis-rundir').textContent = analysisData.dataset.rundir;
                document.getElementById('modal-rundir-section').style.display = 'block';
            } else {
                document.getElementById('modal-rundir-section').style.display = 'none';
            }
            
            if (analysisData.dataset.approximant) {
                document.getElementById('modal-analysis-approximant').textContent = analysisData.dataset.approximant;
                document.getElementById('modal-approximant-section').style.display = 'block';
            } else {
                document.getElementById('modal-approximant-section').style.display = 'none';
            }
            
            if (analysisData.dataset.comment) {
                document.getElementById('modal-analysis-comment').textContent = analysisData.dataset.comment;
                document.getElementById('modal-comment-section').style.display = 'block';
            } else {
                document.getElementById('modal-comment-section').style.display = 'none';
            }
            
            if (analysisData.dataset.dependencies) {
                document.getElementById('modal-analysis-dependencies').textContent = analysisData.dataset.dependencies;
                document.getElementById('modal-dependencies-section').style.display = 'block';
            } else {
                document.getElementById('modal-analysis-dependencies').textContent = 'None';
                document.getElementById('modal-dependencies-section').style.display = 'block';
            }
            
            // Handle results pages
            if (analysisData.dataset.resultPages) {
                var resultPagesStr = analysisData.dataset.resultPages;
                var resultPages = resultPagesStr.split(';;').filter(function(p) { return p.trim(); });
                
                if (resultPages.length > 0) {
                    var linksHtml = '<ul>';
                    resultPages.forEach(function(page) {
                        var parts = page.split('|');
                        if (parts.length === 2) {
                            var url = parts[0];
                            var label = parts[1];
                            linksHtml += '<li><a href="' + url + '" target="_blank">' + label + '</a></li>';
                        }
                    });
                    linksHtml += '</ul>';
                    document.getElementById('modal-results-links').innerHTML = linksHtml;
                    document.getElementById('modal-results-section').style.display = 'block';
                } else {
                    document.getElementById('modal-results-section').style.display = 'none';
                }
            } else {
                document.getElementById('modal-results-section').style.display = 'none';
            }
            
            modal.classList.add('show');
            backdrop.classList.add('show');
        }
    }

    function closeAnalysisModal() {
        var modal = document.getElementById('analysis-modal');
        var backdrop = document.getElementById('modal-backdrop');
        
        if (modal && backdrop) {
            modal.classList.remove('show');
            backdrop.classList.remove('show');
        }
    }

    // Subject search functionality
    function initializeSearch() {
        var searchBox = document.getElementById('subject-search');
        if (searchBox) {
            searchBox.addEventListener('input', function() {
                var searchTerm = this.value.toLowerCase();
                document.querySelectorAll('.event-data').forEach(function(event) {
                    var eventName = event.dataset.eventName.toLowerCase();
                    if (eventName.includes(searchTerm)) {
                        event.style.display = '';
                    } else {
                        event.style.display = 'none';
                    }
                });
            });
        }
    }

    // Review status filters
    function initializeReviewFilters() {
        document.querySelectorAll('.filter-review').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var reviewStatus = this.dataset.review;
                var analyses = document.querySelectorAll('.graph-node, .asimov-analysis');
                
                if (this.classList.contains('active')) {
                    // Deactivate filter - show all
                    analyses.forEach(function(analysis) {
                        if (!analysis.classList.contains('hidden')) {
                            analysis.style.display = '';
                            analysis.classList.remove('filtered-hidden');
                        }
                    });
                    this.classList.remove('active');
                } else {
                    // Activate filter
                    document.querySelectorAll('.filter-review').forEach(function(b) {
                        b.classList.remove('active');
                    });
                    this.classList.add('active');
                    
                    analyses.forEach(function(analysis) {
                        var analysisReview = analysis.dataset.review || 'none';
                        if (analysisReview === reviewStatus) {
                            analysis.style.display = '';
                            analysis.classList.remove('filtered-hidden');
                        } else {
                            analysis.style.display = 'none';
                            analysis.classList.add('filtered-hidden');
                            // Hide downstream dependencies
                            hideDownstreamDependencies(analysis);
                        }
                    });
                }
                
                // Redraw connections after review filter
                setTimeout(drawGraphConnections, 50);
                checkEventVisibility();
            });
        });
    }

    // Check and collapse events with no visible analyses
    function checkEventVisibility() {
        document.querySelectorAll('.event-data').forEach(function(event) {
            var visibleAnalyses = 0;
            event.querySelectorAll('.graph-node, .asimov-analysis').forEach(function(analysis) {
                if (analysis.style.display !== 'none' && !analysis.classList.contains('hidden')) {
                    visibleAnalyses++;
                }
            });
            
            if (visibleAnalyses === 0) {
                event.classList.add('collapsed');
            } else {
                event.classList.remove('collapsed');
            }
        });
    }

    // Draw SVG connections between graph layers
    function drawGraphConnections() {
        document.querySelectorAll('.workflow-graph').forEach(function(graphContainer) {
            // Create or get SVG element
            var existingSvg = graphContainer.querySelector('.graph-connections');
            if (existingSvg) {
                existingSvg.remove();
            }
            
            var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.classList.add('graph-connections');
            
            var container = graphContainer.querySelector('.graph-container');
            if (!container) return;
            
            // Get all graph nodes (not layers, since we need actual dependencies)
            var allNodes = container.querySelectorAll('.graph-node');
            if (allNodes.length === 0) return;
            
            // Calculate SVG dimensions
            var containerRect = container.getBoundingClientRect();
            svg.setAttribute('width', containerRect.width);
            svg.setAttribute('height', containerRect.height);
            
            // Draw regular connections based on actual dependencies
            allNodes.forEach(function(sourceNode) {
                // Skip if source node is hidden
                if (sourceNode.style.display === 'none' || sourceNode.classList.contains('hidden') || sourceNode.classList.contains('filtered-hidden')) {
                    return;
                }
                
                // Get successors from data attribute
                var successors = sourceNode.dataset.successors;
                if (!successors || !successors.trim()) return;
                
                var successorNames = successors.split(',').map(function(name) { return name.trim(); }).filter(function(name) { return name; });
                
                // Get event name for scoped lookups
                var eventName = sourceNode.dataset.eventName || '';
                
                successorNames.forEach(function(successorName) {
                    // Create scoped node ID using event name
                    var targetNodeId = 'node-' + eventName + '-' + successorName;
                    var targetNode = document.getElementById(targetNodeId);
                    
                    // Skip if target node doesn't exist or is hidden
                    if (!targetNode || targetNode.style.display === 'none' || targetNode.classList.contains('hidden') || targetNode.classList.contains('filtered-hidden')) {
                        return;
                    }
                    
                    var sourceRect = sourceNode.getBoundingClientRect();
                    var targetRect = targetNode.getBoundingClientRect();
                    
                    // Calculate connection points (center right of source, center left of target)
                    var x1 = sourceRect.right - containerRect.left;
                    var y1 = sourceRect.top + sourceRect.height / 2 - containerRect.top;
                    var x2 = targetRect.left - containerRect.left;
                    var y2 = targetRect.top + targetRect.height / 2 - containerRect.top;
                    
                    // Create curved path
                    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    
                    // Calculate control points for bezier curve
                    var controlPointOffset = Math.abs(x2 - x1) / 2;
                    var cx1 = x1 + controlPointOffset;
                    var cy1 = y1;
                    var cx2 = x2 - controlPointOffset;
                    var cy2 = y2;
                    
                    // Create smooth cubic bezier curve
                    var d = 'M ' + x1 + ' ' + y1 + 
                            ' C ' + cx1 + ' ' + cy1 + ', ' + 
                                   cx2 + ' ' + cy2 + ', ' + 
                                   x2 + ' ' + y2;
                    
                    path.setAttribute('d', d);
                    
                    // Use different styling for connections to/from subject analyses
                    var isTargetSubject = targetNode.dataset.isSubject === 'true';
                    if (isTargetSubject) {
                        path.classList.add('connection-line-subject');
                    } else {
                        path.classList.add('connection-line');
                    }
                    
                    svg.appendChild(path);
                });
            });
            
            // Draw subject analysis source dependencies with status-based styling
            allNodes.forEach(function(subjectNode) {
                // Only process subject analyses
                if (subjectNode.dataset.isSubject !== 'true') return;
                
                var sourceAnalyses = subjectNode.dataset.sourceAnalyses;
                if (!sourceAnalyses || !sourceAnalyses.trim()) return;
                
                // Parse source analyses: "name1:status1|name2:status2|..."
                var sourceSpecs = sourceAnalyses.split('|').filter(function(spec) { return spec.trim(); });
                var eventName = subjectNode.dataset.eventName || '';
                
                sourceSpecs.forEach(function(spec) {
                    var parts = spec.split(':');
                    var sourceName = parts[0];
                    var sourceStatus = parts[1] || 'unknown';
                    
                    // Find the source analysis node
                    var sourceNodeId = 'node-' + eventName + '-' + sourceName;
                    var sourceNode = document.getElementById(sourceNodeId);
                    
                    if (!sourceNode || sourceNode.style.display === 'none' || sourceNode.classList.contains('hidden') || sourceNode.classList.contains('filtered-hidden')) {
                        return;
                    }
                    
                    var sourceRect = sourceNode.getBoundingClientRect();
                    var targetRect = subjectNode.getBoundingClientRect();
                    
                    // Calculate connection points
                    var x1 = sourceRect.right - containerRect.left;
                    var y1 = sourceRect.top + sourceRect.height / 2 - containerRect.top;
                    var x2 = targetRect.left - containerRect.left;
                    var y2 = targetRect.top + targetRect.height / 2 - containerRect.top;
                    
                    // Create path for source analysis dependency
                    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    
                    // Calculate control points for bezier curve
                    var controlPointOffset = Math.abs(x2 - x1) / 2;
                    var cx1 = x1 + controlPointOffset;
                    var cy1 = y1;
                    var cx2 = x2 - controlPointOffset;
                    var cy2 = y2;
                    
                    // Create smooth cubic bezier curve
                    var d = 'M ' + x1 + ' ' + y1 + 
                            ' C ' + cx1 + ' ' + cy1 + ', ' + 
                                   cx2 + ' ' + cy2 + ', ' + 
                                   x2 + ' ' + y2;
                    
                    path.setAttribute('d', d);
                    
                    // Determine path styling based on source analysis status
                    if (sourceStatus === 'finished' || sourceStatus === 'uploaded') {
                        path.classList.add('connection-included');
                    } else if (sourceStatus === 'processing' || sourceStatus === 'running') {
                        path.classList.add('connection-pending');
                    } else {
                        path.classList.add('connection-waiting');
                    }
                    
                    // Add title for hover tooltip
                    var title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
                    title.textContent = subjectNode.dataset.nodeName + ' uses ' + sourceName + ' (' + sourceStatus + ')';
                    path.appendChild(title);
                    
                    svg.appendChild(path);
                });
            });
            
            // Insert SVG at the beginning of container so it's behind nodes
            container.insertBefore(svg, container.firstChild);
        });
    }

    // Enhanced initialization
    window.onload = function() {
        setupRefresh();
        initializeFilters();
        initializeToggles();
        initializeSearch();
        initializeReviewFilters();
        calculateStats();
        
        // Draw graph connections after DOM is ready
        setTimeout(drawGraphConnections, 100);
        
        // Add modal close handlers
        var closeBtn = document.getElementById('modal-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', closeAnalysisModal);
        }
        
        var backdrop = document.getElementById('modal-backdrop');
        if (backdrop) {
            backdrop.addEventListener('click', closeAnalysisModal);
        }
        
        // Add filter change listener to check event visibility
        document.querySelectorAll('.filter-status, .filter-review, #hide-cancelled').forEach(function(btn) {
            btn.addEventListener('click', function() {
                setTimeout(checkEventVisibility, 100);
            });
        });
        
        // Redraw connections on window resize
        window.addEventListener('resize', function() {
            setTimeout(drawGraphConnections, 100);
        });
    };

</script>
        """
        report += script
    with report:
        navbar = bt.Navbar(
            f"Asimov  |  {current_ledger.data['project']['name']}",
            background="navbar-dark bg-primary",
        )
        report + navbar

    events = sorted(events, key=lambda a: a.name)
    
    # Build summary dashboard
    summary = """
<div class='container-fluid pt-5'>
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
        <h5>Status Filters</h5>
        <button class='btn btn-sm btn-outline-secondary filter-btn' id='show-all'>Show All</button>
        <button class='btn btn-sm btn-outline-primary filter-btn filter-status' data-status='running'>Running</button>
        <button class='btn btn-sm btn-outline-success filter-btn filter-status' data-status='finished'>Finished</button>
        <button class='btn btn-sm btn-outline-success filter-btn filter-status' data-status='uploaded'>Uploaded</button>
        <button class='btn btn-sm btn-outline-warning filter-btn filter-status' data-status='stuck'>Stuck</button>
        <button class='btn btn-sm btn-outline-danger filter-btn filter-status' data-status='stopped'>Stopped</button>
        <button class='btn btn-sm btn-outline-secondary filter-btn' id='hide-cancelled'>Hide Cancelled</button>
        <br>
        <h5 style="margin-top: 1rem;">Review Status Filters</h5>
        <button class='btn btn-sm btn-outline-success filter-btn filter-review' data-review='approved'>Approved</button>
        <button class='btn btn-sm btn-outline-info filter-btn filter-review' data-review='checked'>Checked</button>
        <button class='btn btn-sm btn-outline-danger filter-btn filter-review' data-review='rejected'>Rejected</button>
        <button class='btn btn-sm btn-outline-warning filter-btn filter-review' data-review='deprecated'>Deprecated</button>
        <button class='btn btn-sm btn-outline-secondary filter-btn filter-review' data-review='none'>No Review</button>
    </div>
</div>
    """
    
    # Build search box
    search_box = """
<div class='container-fluid'>
    <input type='text' id='subject-search' class='search-box' placeholder='Search events/subjects...'>
</div>
    """
    
    cards = summary + filters + search_box
    cards += """
<div class='container-fluid'><div class='row'><div class='col-12 col-md-3 col-xl-2  asimov-sidebar'>
"""

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
    
    # Add modal HTML structure
    modal_html = """
<div id="modal-backdrop" class="modal-backdrop"></div>
<div id="analysis-modal" class="analysis-modal">
    <div class="modal-header">
        <h3 class="modal-title" id="modal-analysis-name">Analysis Details</h3>
        <button class="modal-close" id="modal-close-btn">&times;</button>
    </div>
    <div class="modal-body">
        <div class="modal-section">
            <h5>Status</h5>
            <p><span id="modal-analysis-status" class="badge">Unknown</span></p>
        </div>
        <div class="modal-section" id="modal-review-section">
            <h5>Review Status</h5>
            <p><span id="modal-review-status" class="badge">No Review</span></p>
            <p id="modal-review-message" style="margin-top: 0.5rem; font-style: italic;"></p>
        </div>
        <div class="modal-section">
            <h5>Pipeline</h5>
            <p id="modal-analysis-pipeline">-</p>
        </div>
        <div class="modal-section" id="modal-comment-section">
            <h5>Comment</h5>
            <p id="modal-analysis-comment">-</p>
        </div>
        <div class="modal-section" id="modal-rundir-section">
            <h5>Run Directory</h5>
            <p><code id="modal-analysis-rundir">-</code></p>
        </div>
        <div class="modal-section" id="modal-approximant-section">
            <h5>Waveform Approximant</h5>
            <p id="modal-analysis-approximant">-</p>
        </div>
        <div class="modal-section" id="modal-dependencies-section">
            <h5>Dependencies</h5>
            <p id="modal-analysis-dependencies">-</p>
        </div>
        <div class="modal-section" id="modal-results-section" style="display:none;">
            <h5>Results</h5>
            <div id="modal-results-links"></div>
        </div>
    </div>
</div>
"""
    
    cards += modal_html
    
    with report:
        report += cards

    with report:
        time = f"Report generated at {datetime.now(tz):%Y-%m-%d %H:%M}"
        report += time


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
