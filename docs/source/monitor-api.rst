Programmatic Monitor API
========================

Overview
--------

The asimov monitor can be run programmatically from Python scripts or Jupyter notebooks using the ``asimov.monitor_api`` module. This is useful for:

* Custom automation workflows
* Interactive analysis in Jupyter notebooks
* Integration with other Python tools
* Building custom dashboards or monitoring systems

Quick Start
-----------

Basic Usage
^^^^^^^^^^^

Run the monitor from Python:

.. code-block:: python

    from asimov.monitor_api import run_monitor
    
    # Run monitor on all analyses
    results = run_monitor(verbose=True)
    print(f"Monitored {results['total']} analyses")

Jupyter Notebook Example
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # In a Jupyter notebook cell
    from asimov.monitor_api import run_monitor, list_active_analyses
    import pandas as pd
    
    # Get list of active analyses
    analyses = list_active_analyses()
    df = pd.DataFrame(analyses)
    display(df)
    
    # Run monitor
    results = run_monitor(verbose=True)
    
    # Show results
    pd.DataFrame([results])

API Functions
-------------

run_monitor()
^^^^^^^^^^^^^

Run the complete monitoring cycle programmatically:

.. code-block:: python

    from asimov.monitor_api import run_monitor
    
    # Monitor all analyses (keyword-only arguments)
    results = run_monitor()
    
    # Monitor specific event
    results = run_monitor(event_filter="GW150914")
    
    # Dry run (no changes)
    results = run_monitor(dry_run=True, verbose=True)
    
    # Results dictionary contains:
    # - 'total': Total number of analyses
    # - 'project_analyses': Number of project analyses
    # - 'event_analyses': Number of event analyses
    # - 'active': Number currently active
    # - 'complete': Number completed
    # - 'stuck': Number stuck

get_analysis_status()
^^^^^^^^^^^^^^^^^^^^

Query the current status of analyses:

.. code-block:: python

    from asimov.monitor_api import get_analysis_status
    
    # Get all statuses
    statuses = get_analysis_status()
    for name, status in statuses.items():
        print(f"{name}: {status}")
    
    # Get status for specific event (keyword-only arguments)
    statuses = get_analysis_status(event_name="GW150914")
    
    # Get status for specific analysis
    status = get_analysis_status(analysis_name="bilby_analysis")

list_active_analyses()
^^^^^^^^^^^^^^^^^^^^^^

List all currently active analyses:

.. code-block:: python

    from asimov.monitor_api import list_active_analyses
    
    analyses = list_active_analyses()
    for analysis in analyses:
        print(f"{analysis['name']}: {analysis['status']}")

Use Cases
---------

Custom Monitoring Script
^^^^^^^^^^^^^^^^^^^^^^^

Create a custom monitoring script:

.. code-block:: python

    #!/usr/bin/env python
    """Custom monitoring script for asimov."""
    
    import time
    from asimov.monitor_api import run_monitor
    
    def monitor_loop(interval=300):
        """Run monitor in a loop."""
        while True:
            print(f"Running monitor at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            try:
                results = run_monitor(verbose=True)
                
                # Custom logic based on results
                if results['stuck'] > 0:
                    print(f"WARNING: {results['stuck']} analyses are stuck!")
                
            except Exception as e:
                print(f"Error during monitoring: {e}")
            
            print(f"Waiting {interval} seconds...")
            time.sleep(interval)
    
    if __name__ == "__main__":
        monitor_loop(interval=300)  # Run every 5 minutes

Jupyter Dashboard
^^^^^^^^^^^^^^^^^

Create an interactive dashboard in Jupyter:

.. code-block:: python

    # Jupyter notebook cells
    
    # Cell 1: Imports
    from asimov.monitor_api import run_monitor, list_active_analyses, get_analysis_status
    import pandas as pd
    import matplotlib.pyplot as plt
    from IPython.display import display, HTML
    
    # Cell 2: Show active analyses
    analyses = list_active_analyses()
    df = pd.DataFrame(analyses)
    display(HTML("<h3>Active Analyses</h3>"))
    display(df)
    
    # Cell 3: Status distribution
    status_counts = df['status'].value_counts()
    status_counts.plot(kind='bar', title='Analysis Status Distribution')
    plt.ylabel('Count')
    plt.show()
    
    # Cell 4: Run monitor
    display(HTML("<h3>Running Monitor</h3>"))
    results = run_monitor(verbose=True)
    
    # Cell 5: Show results
    display(HTML("<h3>Monitor Results</h3>"))
    results_df = pd.DataFrame([results])
    display(results_df)

Integration with Analysis Workflow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Integrate monitoring into your analysis workflow:

.. code-block:: python

    from asimov.monitor_api import run_monitor, get_analysis_status
    
    # Submit your analysis
    # ... your code to submit analysis ...
    
    # Monitor until complete
    analysis_name = "my_bilby_analysis"
    
    while True:
        status = get_analysis_status(analysis_name=analysis_name)
        
        if status.get(f"GW150914/{analysis_name}") == "finished":
            print("Analysis complete!")
            break
        elif status.get(f"GW150914/{analysis_name}") == "stuck":
            print("Analysis is stuck, needs attention")
            break
        
        # Run monitor
        run_monitor()
        
        # Wait before checking again
        time.sleep(300)  # 5 minutes

Scheduled Monitoring
^^^^^^^^^^^^^^^^^^^^

Use with task schedulers like cron or systemd:

.. code-block:: python

    #!/usr/bin/env python
    """
    Scheduled monitor script.
    Run with: python monitor_scheduled.py
    Or schedule with cron: */15 * * * * /path/to/python monitor_scheduled.py
    """
    
    import logging
    from asimov.monitor_api import run_monitor
    from datetime import datetime
    
    # Set up logging
    logging.basicConfig(
        filename='/path/to/monitor.log',
        level=logging.INFO,
        format='%(asctime)s - %(message)s'
    )
    
    def main():
        logging.info("Starting scheduled monitor run")
        
        try:
            results = run_monitor()
            logging.info(
                f"Monitor complete: {results['total']} analyses, "
                f"{results['active']} active, {results['stuck']} stuck"
            )
        except Exception as e:
            logging.error(f"Monitor failed: {e}", exc_info=True)
    
    if __name__ == "__main__":
        main()

Error Handling
--------------

The monitor API raises exceptions for errors:

.. code-block:: python

    from asimov.monitor_api import run_monitor
    
    try:
        results = run_monitor()
    except RuntimeError as e:
        print(f"Monitor error: {e}")
        # Handle error (e.g., condor not available)
    except Exception as e:
        print(f"Unexpected error: {e}")
        # Handle other errors

Comparison with CLI
-------------------

The programmatic API provides the same functionality as the CLI but with Python interfaces:

+----------------------------------+------------------------------------------+
| CLI Command                      | Programmatic Equivalent                  |
+==================================+==========================================+
| ``asimov monitor``               | ``run_monitor()``                        |
+----------------------------------+------------------------------------------+
| ``asimov monitor --dry-run``     | ``run_monitor(dry_run=True)``            |
+----------------------------------+------------------------------------------+
| ``asimov monitor GW150914``      | ``run_monitor(event_filter="GW150914")`` |
+----------------------------------+------------------------------------------+

Best Practices
--------------

1. **Use dry runs for testing**: Always test with ``dry_run=True`` first
2. **Handle exceptions**: Wrap monitor calls in try-except blocks
3. **Log results**: Keep logs of monitoring runs for debugging
4. **Limit frequency**: Don't run too frequently (recommended: 5-15 minutes minimum)
5. **Check stuck analyses**: Monitor the 'stuck' count and investigate issues
6. **Use filters**: Filter by event when working with specific analyses

See Also
--------

* :doc:`monitor-state-machine` - State machine architecture
* :doc:`user-guide/monitoring` - CLI monitoring guide
* :doc:`api/asimov` - Full API reference
