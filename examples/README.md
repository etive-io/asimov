# Asimov Dependency Management Examples

This directory contains example blueprint files demonstrating the new flexible dependency management features.

## Features Demonstrated

### dependency-examples.yaml

This file shows examples of:

1. **Simple name-based dependencies** (backward compatible)
   - Traditional style: `needs: - generate-psds`

2. **Property-based dependencies**
   - Filter by any property: `needs: - pipeline: bayeswave`
   - Nested properties: `needs: - waveform.approximant: IMRPhenomXPHM`

3. **OR logic**
   - Multiple conditions are OR'd together by default
   - An analysis depends on anything matching ANY condition

4. **AND logic**
   - Use nested lists for AND conditions
   - Example: `needs: - - pipeline: bayeswave` 
                   `  - status: finished`
   - All conditions in the nested list must match

5. **Negation**
   - Prefix values with `!` to negate
   - Example: `needs: - pipeline: "!bayeswave"`
   - Matches everything except the specified value

6. **Complex combinations**
   - Mix AND and OR logic
   - Nested lists are AND'd internally, then OR'd with other items

7. **Staleness tracking**
   - Dependencies are recorded when an analysis runs
   - If matching analyses change, the analysis is marked as stale

8. **Auto-refresh**
   - Set `refreshable: true` to auto-refresh stale analyses
   - Indicated differently in the HTML report

## Using These Examples

To use these examples in your own project:

1. Copy the relevant sections to your blueprint files
2. Modify the property names and values to match your needs
3. Apply the blueprint with `asimov apply -f your-blueprint.yaml`

## More Information

See the main documentation at `docs/source/blueprints.rst` for complete details on the dependency syntax.
