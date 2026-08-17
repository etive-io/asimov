# Modal Dependencies Feature - Visual Guide

## How It Works

When you click on an analysis node in the workflow graph, a modal popup appears with detailed information about the analysis. With the new update, this modal now includes a **Dependencies** section.

## Example Modal Content

```
┌─────────────────────────────────────────────────────────┐
│  Analysis Details                                    ×  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Status                                                 │
│  ┌─────────┐                                           │
│  │ ready   │                                           │
│  └─────────┘                                           │
│                                                         │
│  Pipeline                                               │
│  bilby                                                  │
│                                                         │
│  Comment                                                │
│  Combines IMRPhenomXPHM and SEOBNRv5PHM results       │
│                                                         │
│  Run Directory                                          │
│  /path/to/combiner/run                                 │
│                                                         │
│  Dependencies                           ← NEW!          │
│  IMRPhenomXPHM-PE, SEOBNRv5PHM-PE                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## What Gets Displayed

### For analyses WITH dependencies:
- Shows comma-separated list of dependency names
- Example: `IMRPhenomXPHM-PE, SEOBNRv5PHM-PE`
- Example: `BayesWave-PSD`

### For analyses WITHOUT dependencies:
- Shows: `None`

## Property-Based Dependencies

The dependencies shown are the **resolved** dependencies - the actual analysis names that match the property-based queries.

### Example 1: Simple name dependency
```yaml
needs:
  - BayesWave-PSD
```
Modal shows: `BayesWave-PSD`

### Example 2: Property-based OR dependencies
```yaml
needs:
  - waveform.approximant: IMRPhenomXPHM
  - waveform.approximant: SEOBNRv5PHM
```
Modal shows: `IMRPhenomXPHM-PE, SEOBNRv5PHM-PE`

### Example 3: Property-based AND dependencies
```yaml
needs:
  - - pipeline: bayeswave
    - review.status: approved
```
Modal shows: `Approved-BayesWave-1, Approved-BayesWave-2` (all approved bayeswave analyses)

## Implementation Details

### Data Flow

1. **Event HTML Generation** (`event.py`)
   - Calls `update_graph()` to ensure edges are current
   - For each node, evaluates `node.dependencies` 
   - Stores as `data-dependencies` attribute in hidden div

2. **Modal Population** (`report.py`)
   - JavaScript reads `data-dependencies` from hidden div
   - Populates modal section with dependency names
   - Shows/hides section based on presence of data

3. **User Experience**
   - Click analysis node → Modal opens
   - Dependencies section automatically populated
   - Clear indication of what this analysis depends on

## Technical Changes

### Files Modified

**asimov/event.py:**
- Added `update_graph()` method to rebuild edges dynamically
- Enhanced HTML generation to include dependencies data
- Calls `update_graph()` before using graph in `html()` and `get_all_latest()`

**asimov/cli/report.py:**
- Added dependencies section to modal HTML structure
- Updated JavaScript to populate dependencies from data attribute
- Section always shows (displays "None" if no dependencies)

## Benefits

1. **Transparency**: Users can see exactly what an analysis depends on
2. **Debugging**: Quickly identify dependency relationships
3. **Property-based clarity**: See resolved names from property queries
4. **Graph consistency**: Connections in graph match displayed dependencies
