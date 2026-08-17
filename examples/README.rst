Examples
========

This directory contains example scripts demonstrating the usage of asimov features.

Scheduler Examples
------------------

``scheduler_example.py``
    Demonstrates how to use the asimov scheduler module to submit, query, and delete jobs.
    
    Usage::
    
        python scheduler_example.py
        
    This example shows:
    
    - Creating a scheduler instance using the factory function
    - Creating a JobDescription object
    - Submitting a job to HTCondor
    - Querying job status
    - Deleting a job (commented out by default)
    
    Note: This example requires a working HTCondor installation and configuration.
