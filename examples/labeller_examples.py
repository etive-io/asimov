#!/usr/bin/env python
"""
Example script demonstrating the labeller plugin system.

This script shows how to create and register custom labellers
that automatically mark analyses as interesting during monitoring.
"""

from asimov.labellers import Labeller, register_labeller, get_labellers
from asimov.example_labellers import (
    PipelineInterestLabeller,
    FinishedAnalysisLabeller,
    ConditionalLabeller,
)


def example_basic_labeller():
    """Example 1: Create a basic labeller."""
    print("Example 1: Basic Labeller")
    print("-" * 50)
    
    class SimpleLabeller(Labeller):
        """Mark all analyses as interesting."""
        
        @property
        def name(self):
            return "simple_labeller"
        
        def label(self, analysis, context=None):
            return {"interest status": True}
    
    # Register the labeller
    labeller = SimpleLabeller()
    register_labeller(labeller)
    
    print(f"✓ Registered labeller: {labeller.name}")
    print()


def example_pipeline_labeller():
    """Example 2: Label specific pipelines as interesting."""
    print("Example 2: Pipeline-based Labelling")
    print("-" * 50)
    
    # Create a labeller for bilby and RIFT pipelines
    labeller = PipelineInterestLabeller(["bilby", "RIFT"])
    register_labeller(labeller)
    
    print(f"✓ Registered labeller: {labeller.name}")
    print(f"  Interesting pipelines: {labeller.interesting_pipelines}")
    print()


def example_finished_labeller():
    """Example 3: Only label finished analyses."""
    print("Example 3: Finished Analysis Labelling")
    print("-" * 50)
    
    labeller = FinishedAnalysisLabeller()
    register_labeller(labeller)
    
    print(f"✓ Registered labeller: {labeller.name}")
    print("  Only labels analyses with status: finished, uploaded")
    print()


def example_conditional_labeller():
    """Example 4: Use custom logic for labelling."""
    print("Example 4: Conditional Labelling")
    print("-" * 50)
    
    # Custom condition: mark high-mass analyses as interesting
    def is_high_mass(analysis):
        if hasattr(analysis, 'meta') and 'mass' in analysis.meta:
            return analysis.meta['mass'] > 50
        return False
    
    labeller = ConditionalLabeller(
        condition_func=is_high_mass,
        labeller_name="high_mass"
    )
    register_labeller(labeller)
    
    print(f"✓ Registered labeller: {labeller.name}")
    print("  Condition: mass > 50")
    print()


def example_custom_metadata_labeller():
    """Example 5: Add custom metadata beyond interest status."""
    print("Example 5: Custom Metadata Labeller")
    print("-" * 50)
    
    class MetadataLabeller(Labeller):
        """Add custom metadata to analyses."""
        
        @property
        def name(self):
            return "metadata_labeller"
        
        def label(self, analysis, context=None):
            # Return multiple metadata fields
            return {
                "interest status": True,
                "priority": 10,
                "category": "high_priority",
                "auto_labelled": True,
            }
    
    labeller = MetadataLabeller()
    register_labeller(labeller)
    
    print(f"✓ Registered labeller: {labeller.name}")
    print("  Adds: interest status, priority, category, auto_labelled")
    print()


def example_context_aware_labeller():
    """Example 6: Use monitor context in labelling logic."""
    print("Example 6: Context-Aware Labeller")
    print("-" * 50)
    
    class JobStatusLabeller(Labeller):
        """Label based on job status from context."""
        
        @property
        def name(self):
            return "job_status_labeller"
        
        def label(self, analysis, context=None):
            if context is None:
                return {}
            
            # Access job information from context
            job = context.job if hasattr(context, 'job') else None
            
            if job and hasattr(job, 'status'):
                return {
                    "interest status": True,
                    "job_status": str(job.status),
                }
            
            return {}
    
    labeller = JobStatusLabeller()
    register_labeller(labeller)
    
    print(f"✓ Registered labeller: {labeller.name}")
    print("  Uses: MonitorContext to access job information")
    print()


def main():
    """Run all examples."""
    print("=" * 50)
    print("Labeller Plugin System Examples")
    print("=" * 50)
    print()
    
    # Run examples
    example_basic_labeller()
    example_pipeline_labeller()
    example_finished_labeller()
    example_conditional_labeller()
    example_custom_metadata_labeller()
    example_context_aware_labeller()
    
    # Show all registered labellers
    print("Summary: Registered Labellers")
    print("-" * 50)
    labellers = get_labellers()
    print(f"Total labellers registered: {len(labellers)}")
    for name in labellers:
        print(f"  • {name}")
    print()
    
    print("=" * 50)
    print("How to use these labellers:")
    print("=" * 50)
    print()
    print("1. During monitoring, labellers are automatically applied")
    print("2. They update analysis.meta with labels")
    print("3. Use 'interest status' in workflow dependencies:")
    print()
    print("   needs settings:")
    print("     condition: is_interesting")
    print("     minimum: 1")
    print()
    print("4. Access labels in custom code:")
    print()
    print("   if analysis.meta.get('interest status'):")
    print("       print('This analysis is interesting!')")
    print()
    print("For more information, see:")
    print("  docs/source/labeller-plugins.rst")
    print("=" * 50)


if __name__ == "__main__":
    main()
