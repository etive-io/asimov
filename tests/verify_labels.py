#!/usr/bin/env python
"""
Verify that labellers have correctly applied labels to analyses.

This script checks that the expected labels have been set on analyses
after the monitor has run with labellers configured.
"""

import sys
from asimov import current_ledger as ledger

def verify_labels():
    """Verify that expected labels are present on analyses."""
    
    print("Verifying labels on analyses...")
    
    # Track results
    analyses_checked = 0
    labels_found = 0
    errors = []
    
    # Check project analyses
    for analysis in ledger.project_analyses:
        analyses_checked += 1
        print(f"\nChecking project analysis: {analysis.name}")
        print(f"  Pipeline: {analysis.pipeline}")
        print(f"  Status: {analysis.status}")
        
        # Check if labels exist
        if hasattr(analysis, 'meta') and 'labels' in analysis.meta:
            labels = analysis.meta['labels']
            print(f"  Labels: {labels}")
            
            # For test pipelines, we expect the 'interesting' label
            pipeline_str = str(analysis.pipeline).lower()
            if 'testpipeline' in pipeline_str:
                if labels.get('interesting'):
                    print(f"  ✓ Found expected 'interesting' label")
                    labels_found += 1
                else:
                    error_msg = f"Analysis {analysis.name} with pipeline {analysis.pipeline} should have 'interesting' label but doesn't"
                    print(f"  ✗ {error_msg}")
                    errors.append(error_msg)
        else:
            print(f"  No labels found")
            # Only error if this is a test pipeline
            pipeline_str = str(analysis.pipeline).lower()
            if 'testpipeline' in pipeline_str:
                error_msg = f"Analysis {analysis.name} with pipeline {analysis.pipeline} should have labels but doesn't"
                print(f"  ✗ {error_msg}")
                errors.append(error_msg)
    
    # Check event analyses
    for event in ledger.get_event(None):
        for production in event.productions:
            analyses_checked += 1
            print(f"\nChecking event analysis: {event.name}/{production.name}")
            print(f"  Pipeline: {production.pipeline}")
            print(f"  Status: {production.status}")
            
            # Check if labels exist
            if hasattr(production, 'meta') and 'labels' in production.meta:
                labels = production.meta['labels']
                print(f"  Labels: {labels}")
                
                # For test pipelines, we expect the 'interesting' label
                pipeline_str = str(production.pipeline).lower()
                if 'testpipeline' in pipeline_str:
                    if labels.get('interesting'):
                        print(f"  ✓ Found expected 'interesting' label")
                        labels_found += 1
                    else:
                        error_msg = f"Analysis {event.name}/{production.name} with pipeline {production.pipeline} should have 'interesting' label but doesn't"
                        print(f"  ✗ {error_msg}")
                        errors.append(error_msg)
            else:
                print(f"  No labels found")
                # Only error if this is a test pipeline
                pipeline_str = str(production.pipeline).lower()
                if 'testpipeline' in pipeline_str:
                    error_msg = f"Analysis {event.name}/{production.name} with pipeline {production.pipeline} should have labels but doesn't"
                    print(f"  ✗ {error_msg}")
                    errors.append(error_msg)
    
    # Print summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    print(f"Total analyses checked: {analyses_checked}")
    print(f"Analyses with expected labels: {labels_found}")
    print(f"Errors: {len(errors)}")
    
    if errors:
        print("\nErrors found:")
        for error in errors:
            print(f"  - {error}")
        print("\n✗ Label verification FAILED")
        return 1
    else:
        print("\n✓ Label verification PASSED")
        return 0

if __name__ == "__main__":
    sys.exit(verify_labels())
