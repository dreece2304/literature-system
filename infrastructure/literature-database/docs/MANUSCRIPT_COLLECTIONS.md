# Manuscript Collections Guide

Citation management feature for the literature-database service.

**Service Context**: Port 8001 | Run from: `infrastructure/literature-database/`

## Overview

The manuscript collections feature allows you to organize and manage citations for your research papers and manuscripts. This system helps you:

- Collect relevant papers for specific writing projects
- Generate BibTeX bibliographies automatically
- Discover related papers through intelligent suggestions
- Track citation progress and coverage

## Quick Start

### 1. Create a New Collection

```bash
# Create collection interactively
python scripts/manuscript_collections.py --action create

# Or create directly with parameters
python scripts/manuscript_collections.py --action create --title "ALD for Membrane Applications" --description "References for my membrane ALD paper"
```

### 2. Add Papers to Collection

```bash
# Search and add papers interactively
python scripts/manuscript_collections.py --action add --collection-id 1 --search "atomic layer deposition membrane"

# Add multiple search terms
python scripts/manuscript_collections.py --action add --collection-id 1 --search "ALD,membrane technology,selectivity"
```

### 3. View Your Collection

```bash
# View collection contents
python scripts/manuscript_collections.py --action view --collection-id 1

# List all collections
python scripts/manuscript_collections.py --action list
```

### 4. Export Bibliography

```bash
# Export as BibTeX file
python scripts/manuscript_collections.py --action export --collection-id 1
```

This creates a file like `bibliography_ALD_for_Membrane_Applications.bib` with properly formatted BibTeX entries.

## Detailed Workflow

### Collection Management

#### Creating Collections
Each manuscript should have its own collection. Use descriptive names that match your project:

```bash
# Examples of good collection names
python scripts/manuscript_collections.py --action create --title "ALD for Membrane Applications"
python scripts/manuscript_collections.py --action create --title "MLD Hybrid Materials Review"
python scripts/manuscript_collections.py --action create --title "Electrocatalyst Stability Study"
```

#### Viewing Collections
The list command shows all your collections with paper counts:

```bash
python scripts/manuscript_collections.py --action list
```

Output:
```
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID ┃ Manuscript                ┃ Papers ┃ Description               ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1  │ ALD for Membrane Applic… │ 5      │ References for manuscr…   │
└────┴───────────────────────────┴────────┴───────────────────────────┘
```

### Paper Discovery and Addition

#### Search-Based Addition
The most effective way to build collections is through targeted searches:

```bash
# Search for specific techniques
python scripts/manuscript_collections.py --action add --collection-id 1 --search "atomic layer deposition"

# Search for applications
python scripts/manuscript_collections.py --action add --collection-id 1 --search "membrane separation"

# Search for materials
python scripts/manuscript_collections.py --action add --collection-id 1 --search "Al2O3,TiO2,ZnO"
```

#### Interactive Paper Selection
When you run the add command, the system shows search results and lets you choose which papers to include:

```
Search results for 'atomic layer deposition membrane':
  1. Precise pore size tuning and surface modifications of...
     Authors: Fengbin Li, Ling Li, Xingzhi Liao...
     Journal: Journal of Membrane Science (2011)
  
  2. Upgrading polytetrafluoroethylene hollow-fiber membr...
     Authors: Sen Xiong, Xiaojuan Jia, Kai Mi...
     Journal: Journal of Membrane Science (2021)

Select papers to add (1-10, comma-separated, or 'all'): 1,2
```

#### Related Paper Suggestions
Get intelligent suggestions based on your existing collection:

```bash
python scripts/manuscript_collections.py --action suggest --collection-id 1
```

This analyzes your collection's tags and keywords to suggest similar papers you might have missed.

### Bibliography Generation

#### BibTeX Export
Generate publication-ready bibliographies:

```bash
python scripts/manuscript_collections.py --action export --collection-id 1
```

The generated BibTeX file includes:
- Proper citation keys (AuthorYear format)
- Complete metadata (title, authors, journal, year, DOI)
- Consistent formatting for LaTeX documents

Example output (`bibliography_ALD_for_Membrane_Applications.bib`):
```bibtex
% Bibliography for: ALD for Membrane Applications
% Generated from literature database
% 5 references

@article{Li2011,
  title = {Precise pore size tuning and surface modifications of polymeric membranes using the atomic layer deposition technique},
  author = {Fengbin Li and Ling Li and Xingzhi Liao and Yong Wang},
  journal = {Journal of Membrane Science},
  year = {2011},
  volume = {385-386},
  number = {1},
  doi = {10.1016/j.memsci.2011.06.042},
}
```

## Best Practices

### Collection Organization

1. **One Collection per Manuscript**: Create separate collections for each paper you're writing
2. **Descriptive Names**: Use clear, specific titles that match your manuscript topics
3. **Early Creation**: Start collections early in the writing process to capture all relevant papers
4. **Regular Updates**: Periodically search for new papers and update your collections

### Search Strategy

1. **Multiple Search Terms**: Use various keywords to capture different aspects:
   - Techniques: "atomic layer deposition", "ALD", "plasma enhanced"
   - Materials: "Al2O3", "TiO2", "hafnium oxide"
   - Applications: "membrane", "gas separation", "water treatment"

2. **Iterative Refinement**: Start broad, then get more specific:
   ```bash
   # Start broad
   --search "membrane"
   
   # Get specific
   --search "gas separation membrane"
   
   # Very specific
   --search "CO2/N2 separation membrane ALD"
   ```

3. **Use Suggestions**: Leverage the suggestion system to find papers you might miss

### Citation Management

1. **Regular Exports**: Export your bibliography frequently as you add papers
2. **Version Control**: Keep your BibTeX files in version control alongside your manuscript
3. **Consistent Keys**: The system generates consistent citation keys you can rely on
4. **Metadata Validation**: Review exported entries for completeness before submission

## Integration with Writing Tools

### LaTeX Integration
```latex
% In your LaTeX document
\bibliography{bibliography_ALD_for_Membrane_Applications}

% Cite papers using generated keys
\cite{Li2011}
\cite{Xiong2021}
```

### Reference Manager Integration
The BibTeX files can be imported into:
- Zotero
- Mendeley
- EndNote
- JabRef

### Manuscript Tracking
Track your citation progress:

```bash
# View collection status
python scripts/manuscript_collections.py --action view --collection-id 1

# Check for new related papers
python scripts/manuscript_collections.py --action suggest --collection-id 1
```

## Advanced Usage

### Programmatic Access
```python
from scripts.manuscript_collections import ManuscriptCollectionManager

manager = ManuscriptCollectionManager()

# Create collection
collection = manager.create_manuscript_collection("My Paper Title")

# Add papers by search
manager.add_papers_to_collection(collection.id, search_terms=["ALD", "membrane"])

# Export bibliography
manager.export_collection_bibliography(collection.id)
```

### Batch Operations
```bash
# Create multiple collections from a list
for title in "ALD Review" "MLD Applications" "Battery Materials"; do
    python scripts/manuscript_collections.py --action create --title "$title"
done
```

## Troubleshooting

### Common Issues

1. **No Papers Found**: Try broader search terms or check spelling
2. **Duplicate Papers**: The system automatically prevents duplicates within collections
3. **Missing Metadata**: Some papers may have incomplete information - manually verify important citations
4. **Export Errors**: Ensure collection has papers before exporting

### Performance Tips

1. **Limit Search Results**: Use specific terms to get more relevant results
2. **Batch Additions**: Add multiple papers at once rather than one-by-one
3. **Regular Cleanup**: Remove irrelevant papers to keep collections focused

---

This manuscript collection system transforms literature management from a tedious task into an efficient, organized workflow that supports high-quality academic writing.