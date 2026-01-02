# Improved Dependency Management Implementation

## Overview

This implementation adds flexible dependency specification to Asimov analyses, supporting property-based filtering, AND/OR logic, negation, and staleness tracking.

## Features Implemented

### 1. Property-Based Dependencies
Analyses can now depend on other analyses based on any property, not just names:

```yaml
needs:
  - pipeline: bayeswave
  - waveform.approximant: IMRPhenomXPHM
  - review.status: approved
```

### 2. AND/OR Logic

**OR Logic (default):** Top-level items are OR'd together
```yaml
needs:
  - waveform.approximant: IMRPhenomXPHM
  - waveform.approximant: SEOBNRv5PHM
# Matches analyses with EITHER approximant
```

**AND Logic:** Use nested lists for AND conditions
```yaml
needs:
  - - pipeline: bayeswave
    - status: finished
# Matches ONLY analyses that are both bayeswave AND finished
```

**Complex Combinations:**
```yaml
needs:
  - - pipeline: bayeswave
    - review.status: approved
  - waveform.approximant: IMRPhenomXPHM
# Matches: (bayeswave AND approved) OR IMRPhenomXPHM
```

### 3. Negation
Prefix values with `!` to match everything except that value:

```yaml
needs:
  - pipeline: "!bayeswave"
# Matches all non-bayeswave analyses
```

### 4. Staleness Tracking

When an analysis runs, the resolved dependencies are recorded. If the set of matching analyses changes later (e.g., new analyses added that match the criteria), the analysis is marked as **stale**.

**Stored in meta:**
- `resolved_dependencies`: List of analysis names that were dependencies when run
- `refreshable`: Boolean flag for auto-refresh

**Properties added:**
- `is_stale`: True if current dependencies differ from resolved
- `is_refreshable`: Get/set the refreshable flag

### 5. HTML Report Enhancements

**New Indicators:**
- **Stale badge** (yellow): Dependencies changed since run
- **Stale (will refresh) badge** (blue): Refreshable analysis is stale

**Dependency Display:**
- Current dependencies shown in details section
- Resolved dependencies shown (when different from current)
- Clear visual distinction with colored backgrounds

## Implementation Details

### Core Functions

#### `_parse_single_dependency(need)`
Parses a single dependency string into components:
- Returns: `(attribute_list, match_value, is_negated)`
- Examples:
  - `"Prod1"` → `(['name'], 'Prod1', False)`
  - `"pipeline: bayeswave"` → `(['pipeline'], 'bayeswave', False)`
  - `"pipeline: !bayeswave"` → `(['pipeline'], 'bayeswave', True)`

#### `_process_dependencies(needs)`
Processes the entire needs list:
- Handles nested lists for AND groups
- Returns list of requirements (single or grouped)
- Each requirement is either a tuple or list of tuples

#### `matches_filter(attribute, match, negate=False)`
Enhanced to support negation:
- `negate=True` inverts the match result
- Works with name, status, review, and metadata properties

#### `dependencies` property
Resolves dependencies with AND/OR logic:
- Top-level items: OR (union)
- Nested lists: AND (intersection within, then union)
- Returns list of analysis names

### Data Storage

All new fields are stored in `analysis.meta`:
- `resolved_dependencies`: List[str]
- `refreshable`: bool

These are automatically saved to the ledger via existing `to_dict()` method.

### Backward Compatibility

Simple name-based dependencies still work exactly as before:
```yaml
needs:
  - Prod1
  - Prod2
```

This is internally converted to:
```python
[(['name'], 'Prod1', False), (['name'], 'Prod2', False)]
```

## Testing

### Unit Tests (20 tests, all passing)
Located in `tests/test_dependency_logic.py`:

1. **Parsing Tests:**
   - Simple names
   - Property-based
   - Nested properties
   - Negation

2. **Matching Tests:**
   - By name, status, review
   - Nested properties
   - Negation

3. **Dependency Resolution:**
   - OR logic
   - AND logic
   - Complex combinations
   - Negation

4. **State Management:**
   - Staleness detection
   - Refreshable flag

## Examples

See `examples/dependency-examples.yaml` for complete examples of all features.

### Example 1: OR Logic
```yaml
kind: analysis
name: combiner
pipeline: bilby
needs:
  - waveform.approximant: IMRPhenomXPHM
  - waveform.approximant: SEOBNRv5PHM
# Depends on all IMRPhenomXPHM and SEOBNRv5PHM analyses
```

### Example 2: AND Logic
```yaml
kind: analysis
name: specific-combo
pipeline: bilby
needs:
  - - review.status: approved
    - pipeline: bayeswave
# Depends ONLY on approved bayeswave analyses
```

### Example 3: Refreshable
```yaml
kind: analysis
name: auto-update
pipeline: bilby
refreshable: true
needs:
  - review.status: approved
# Will auto-refresh when new approved analyses are added
```

## HTML Output

The demo script `examples/demo_html_output.py` shows the HTML output for:
1. Analysis with dependencies
2. Stale analysis
3. Refreshable stale analysis

Run it with:
```bash
python examples/demo_html_output.py
```

## Files Modified

### Core Implementation
- `asimov/analysis.py`: Dependency resolution logic
- `asimov/cli/report.py`: HTML report CSS

### Documentation
- `docs/source/blueprints.rst`: User documentation
- `examples/README.md`: Examples guide

### Tests
- `tests/test_dependency_logic.py`: Unit tests (20 tests)
- `tests/test_dependencies.py`: Integration tests

### Examples
- `examples/dependency-examples.yaml`: Example blueprints
- `examples/demo_html_output.py`: HTML demo script

## Migration Guide

### For Existing Projects

No changes required! Old-style dependencies continue to work:
```yaml
needs:
  - Prod1
```

### To Use New Features

Simply update your blueprint needs sections:

**Before:**
```yaml
needs:
  - BayesWave-PSD
```

**After (property-based):**
```yaml
needs:
  - pipeline: bayeswave
```

**After (with conditions):**
```yaml
needs:
  - - pipeline: bayeswave
    - review.status: approved
```

## Future Enhancements

Possible future improvements:
1. Dependency visualization in graph view
2. Automatic dependency validation
3. Dependency change notifications
4. Dependency history tracking
5. More complex query syntax (e.g., ranges, regex)

## Conclusion

This implementation provides a powerful and flexible dependency system while maintaining complete backward compatibility. All 20 unit tests pass, demonstrating robust handling of complex dependency scenarios.
