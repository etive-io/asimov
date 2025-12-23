#!/usr/bin/env python3
"""
Example script demonstrating the use of the asimov scheduler module.

This script shows how to:
1. Create a scheduler instance
2. Create a job description
3. Submit a job
4. Query job status
5. Delete a job
"""

from asimov.scheduler import get_scheduler, JobDescription

def main():
    # Example 1: Using the factory function
    print("Creating HTCondor scheduler...")
    scheduler = get_scheduler("htcondor")
    
    # Example 2: Create a job description
    print("\nCreating job description...")
    job = JobDescription(
        executable="/bin/echo",
        output="echo.out",
        error="echo.err",
        log="echo.log",
        arguments="Hello from asimov scheduler!",
        cpus=1,
        memory="1GB",
        disk="1GB",
        universe="vanilla"
    )
    
    # Example 3: Submit the job
    print("\nSubmitting job...")
    try:
        cluster_id = scheduler.submit(job)
        print(f"Job submitted successfully with cluster ID: {cluster_id}")
    except Exception as e:
        print(f"Failed to submit job: {e}")
        return
    
    # Example 4: Query job status
    print("\nQuerying job status...")
    try:
        status = scheduler.query(cluster_id)
        print(f"Job status: {status}")
    except Exception as e:
        print(f"Failed to query job: {e}")
    
    # Example 5: Delete the job (optional)
    # To delete the job in your own code, you can call:
    #     scheduler.delete(cluster_id)
    # and handle any exceptions as appropriate for your application.
    #
    # This example script leaves the deletion disabled so that
    # submitted jobs remain available for inspection.
    
    print("\nExample completed!")

if __name__ == "__main__":
    main()
