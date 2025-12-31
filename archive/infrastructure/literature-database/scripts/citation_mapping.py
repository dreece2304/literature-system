#!/usr/bin/env python3
"""
CLI for citation mapping and BibTeX operations.

Citation Commands:
    register    Register a new manuscript project
    scan        Scan a manuscript for citations
    check       Validate citation consistency
    report      Show citation summary for a manuscript
    export      Export citation registry
    suggest     Suggest citation keys for papers without one
    set-key     Set citation key for a paper

BibTeX Commands:
    bib-analyze   Analyze a .bib file for issues
    bib-generate  Generate .bib from database papers
    bib-fix       Fix and standardize a .bib file
    bib-missing   Show citations missing from .bib file
    bib-unused    Show .bib entries not cited in manuscript

Usage:
    # Citation commands
    python scripts/citation_mapping.py register "Paper2" --path /home/user/Paper2 --tex paper/tex
    python scripts/citation_mapping.py scan Paper2
    python scripts/citation_mapping.py check Paper2
    python scripts/citation_mapping.py report Paper2

    # BibTeX commands
    python scripts/citation_mapping.py bib-analyze Paper2 --bib paper/tex/bibliography/references.bib
    python scripts/citation_mapping.py bib-generate Paper2 -o clean_refs.bib
    python scripts/citation_mapping.py bib-fix Paper2 --bib refs.bib --dry-run
    python scripts/citation_mapping.py bib-missing Paper2 --bib refs.bib
"""
import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import get_engine
from src.models import Base, Paper, Manuscript
from src.services.citation_service import CitationService
from src.services.bibtex_service import BibtexService
from sqlalchemy.orm import sessionmaker


def get_session():
    """Get a database session."""
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def cmd_register(args):
    """Register a new manuscript."""
    session = get_session()
    service = CitationService(session)

    try:
        manuscript = service.register_manuscript(
            name=args.name,
            project_path=args.path,
            tex_directory=args.tex,
            bib_file=args.bib,
            description=args.description
        )
        print(f"Registered manuscript: {manuscript.name} (ID: {manuscript.id})")
        print(f"  Project path: {manuscript.project_path}")
        print(f"  TeX directory: {manuscript.tex_directory}")
        if manuscript.bib_file:
            print(f"  BibTeX file: {manuscript.bib_file}")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_list(args):
    """List all registered manuscripts."""
    session = get_session()
    service = CitationService(session)

    manuscripts = service.list_manuscripts()

    if not manuscripts:
        print("No manuscripts registered.")
        return

    print(f"\nRegistered manuscripts ({len(manuscripts)}):\n")
    for ms in manuscripts:
        print(f"  [{ms.id}] {ms.name}")
        print(f"      Path: {ms.project_path}")
        print(f"      TeX: {ms.tex_directory}")
        if ms.last_scanned:
            print(f"      Last scan: {ms.last_scanned.strftime('%Y-%m-%d %H:%M')}")
        print()

    session.close()


def cmd_scan(args):
    """Scan a manuscript for citations."""
    session = get_session()
    service = CitationService(session)

    # Handle ID or name
    if args.manuscript.isdigit():
        manuscript = service.get_manuscript(int(args.manuscript))
    else:
        manuscript = service.get_manuscript_by_name(args.manuscript)

    if not manuscript:
        print(f"Error: Manuscript '{args.manuscript}' not found")
        sys.exit(1)

    print(f"Scanning '{manuscript.name}'...")
    print(f"  TeX directory: {Path(manuscript.project_path) / manuscript.tex_directory}")

    try:
        result = service.scan_citations(manuscript.id, clear_existing=not args.append)

        print(f"\nScan complete!")
        print(f"  Total citations found: {result.total_citations}")
        print(f"  Unique citation keys: {result.unique_keys}")
        print(f"  Matched to papers: {result.matched_to_papers}")
        print(f"  Unmatched keys: {len(result.unmatched_keys)}")

        if result.unmatched_keys and args.verbose:
            print(f"\n  Unmatched citation keys:")
            for key in sorted(result.unmatched_keys):
                print(f"    - {key}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_check(args):
    """Check citation consistency."""
    session = get_session()
    service = CitationService(session)

    # Handle ID or name
    if args.manuscript.isdigit():
        manuscript = service.get_manuscript(int(args.manuscript))
    else:
        manuscript = service.get_manuscript_by_name(args.manuscript)

    if not manuscript:
        print(f"Error: Manuscript '{args.manuscript}' not found")
        sys.exit(1)

    result = service.check_citations(manuscript.id)

    print(f"\nCitation check for '{manuscript.name}':")
    print(f"  Total papers cited: {result.total_papers_cited}")
    print(f"  Papers with citation_key: {result.papers_with_citation_key}")
    print(f"  Papers without citation_key: {result.papers_without_citation_key}")
    print(f"  Orphan citations (no paper match): {len(result.orphan_citations)}")
    print(f"  Duplicate locations: {result.duplicate_locations}")

    if result.issues:
        print(f"\nIssues found:")
        for issue in result.issues:
            print(f"  - {issue}")
    else:
        print(f"\nNo issues found.")

    if result.orphan_citations and args.verbose:
        print(f"\nOrphan citation keys (not matched to any paper):")
        for key in sorted(result.orphan_citations):
            print(f"  - {key}")

    session.close()


def cmd_report(args):
    """Show citation summary for a manuscript."""
    session = get_session()
    service = CitationService(session)

    # Handle ID or name
    if args.manuscript.isdigit():
        manuscript = service.get_manuscript(int(args.manuscript))
    else:
        manuscript = service.get_manuscript_by_name(args.manuscript)

    if not manuscript:
        print(f"Error: Manuscript '{args.manuscript}' not found")
        sys.exit(1)

    locations = service.get_manuscript_citations(manuscript.id)

    # Group by citation key
    by_key = {}
    for loc in locations:
        if loc.citation_key not in by_key:
            by_key[loc.citation_key] = {
                'locations': [],
                'paper': loc.paper
            }
        by_key[loc.citation_key]['locations'].append(loc)

    print(f"\nCitation Report for '{manuscript.name}'")
    print(f"{'=' * 60}")
    print(f"Total unique citations: {len(by_key)}")
    print(f"Total citation instances: {len(locations)}")
    if manuscript.last_scanned:
        print(f"Last scanned: {manuscript.last_scanned.strftime('%Y-%m-%d %H:%M')}")
    print()

    # Sort by citation count
    sorted_keys = sorted(by_key.items(), key=lambda x: -len(x[1]['locations']))

    for key, data in sorted_keys:
        count = len(data['locations'])
        paper = data['paper']

        if paper:
            title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
            print(f"  {key} ({count}x) - {title}")
        else:
            print(f"  {key} ({count}x) - [NOT MATCHED]")

        if args.verbose:
            for loc in data['locations']:
                print(f"      {loc.file_path}:{loc.line_number} ({loc.section_inferred})")

    session.close()


def cmd_export(args):
    """Export citation registry."""
    session = get_session()
    service = CitationService(session)

    # Handle ID or name
    if args.manuscript.isdigit():
        manuscript = service.get_manuscript(int(args.manuscript))
    else:
        manuscript = service.get_manuscript_by_name(args.manuscript)

    if not manuscript:
        print(f"Error: Manuscript '{args.manuscript}' not found")
        sys.exit(1)

    try:
        output = service.export_registry(manuscript.id, format=args.format)

        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"Exported to {args.output}")
        else:
            print(output)

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_suggest(args):
    """Suggest citation keys for papers without one."""
    session = get_session()
    service = CitationService(session)

    suggestions = service.suggest_citation_keys()

    if not suggestions:
        print("All papers have citation keys assigned.")
        return

    print(f"\nSuggested citation keys ({len(suggestions)} papers):\n")

    for paper, suggested_key in suggestions:
        title = paper.title[:50] + "..." if len(paper.title) > 50 else paper.title
        print(f"  [{paper.id}] {suggested_key}")
        print(f"        {title}")
        print()

    if args.apply:
        confirm = input(f"Apply all {len(suggestions)} suggestions? [y/N]: ")
        if confirm.lower() == 'y':
            for paper, key in suggestions:
                service.set_citation_key(paper.id, key)
            print(f"Applied {len(suggestions)} citation keys.")

    session.close()


def cmd_set_key(args):
    """Set citation key for a paper."""
    session = get_session()
    service = CitationService(session)

    try:
        if service.set_citation_key(args.paper_id, args.key):
            paper = session.query(Paper).filter_by(id=args.paper_id).first()
            print(f"Set citation key for paper {args.paper_id}: {args.key}")
            print(f"  Title: {paper.title}")
        else:
            print(f"Error: Paper {args.paper_id} not found")
            sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


# ========== BibTeX Commands ==========

def get_manuscript_and_bib(args, session):
    """Helper to get manuscript and resolve bib path."""
    service = CitationService(session)

    # Handle ID or name
    if args.manuscript.isdigit():
        manuscript = service.get_manuscript(int(args.manuscript))
    else:
        manuscript = service.get_manuscript_by_name(args.manuscript)

    if not manuscript:
        print(f"Error: Manuscript '{args.manuscript}' not found")
        sys.exit(1)

    # Resolve bib path
    if hasattr(args, 'bib') and args.bib:
        bib_path = args.bib
        if not Path(bib_path).is_absolute():
            bib_path = Path(manuscript.project_path) / bib_path
    elif manuscript.bib_file:
        bib_path = Path(manuscript.project_path) / manuscript.bib_file
    else:
        print("Error: No .bib file specified. Use --bib or set bib_file in manuscript.")
        sys.exit(1)

    return manuscript, str(bib_path)


def cmd_bib_analyze(args):
    """Analyze a .bib file for issues."""
    session = get_session()
    manuscript, bib_path = get_manuscript_and_bib(args, session)
    service = BibtexService(session)

    print(f"Analyzing: {bib_path}")
    print(f"Manuscript: {manuscript.name}")
    print()

    try:
        result = service.analyze_bib_file(bib_path, manuscript.id)

        print(f"{'='*60}")
        print(f"BibTeX Analysis Results")
        print(f"{'='*60}")
        print()

        # Summary
        print(f"Total entries:        {result.total_entries}")
        print(f"Unique keys:          {result.unique_keys}")
        print(f"Entries with DOI:     {result.entries_with_doi}")
        print(f"Entries without DOI:  {result.entries_without_doi}")
        print(f"Matched to database:  {result.matched_to_database}")
        print(f"Unmatched entries:    {len(result.unmatched_entries)}")
        print()

        # Issues
        if result.duplicate_keys:
            print(f"DUPLICATE KEYS ({len(result.duplicate_keys)}):")
            for key in result.duplicate_keys:
                print(f"  - {key}")
            print()

        if result.inconsistent_keys:
            print(f"INCONSISTENT KEYS ({len(result.inconsistent_keys)}):")
            for old_key, new_key, reason in result.inconsistent_keys:
                print(f"  - {old_key} -> {new_key}")
                print(f"    ({reason})")
            print()

        if result.missing_required_fields:
            print(f"MISSING REQUIRED FIELDS ({len(result.missing_required_fields)}):")
            for key, fields in result.missing_required_fields:
                print(f"  - {key}: missing {', '.join(fields)}")
            print()

        if result.potential_duplicates:
            print(f"POTENTIAL DUPLICATES ({len(result.potential_duplicates)}):")
            for key1, key2, score in result.potential_duplicates:
                print(f"  - {key1} <-> {key2} ({score:.1%} similar)")
            print()

        if result.unmatched_entries and args.verbose:
            print(f"UNMATCHED ENTRIES ({len(result.unmatched_entries)}):")
            for key in sorted(result.unmatched_entries):
                print(f"  - {key}")
            print()

        # Summary
        issues_count = (len(result.duplicate_keys) + len(result.inconsistent_keys) +
                       len(result.missing_required_fields) + len(result.potential_duplicates))
        if issues_count == 0:
            print("No issues found!")
        else:
            print(f"Total issues found: {issues_count}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_bib_generate(args):
    """Generate .bib from database papers."""
    session = get_session()
    service = BibtexService(session)

    manuscript = None
    manuscript_id = None

    if args.manuscript:
        citation_service = CitationService(session)
        if args.manuscript.isdigit():
            manuscript = citation_service.get_manuscript(int(args.manuscript))
        else:
            manuscript = citation_service.get_manuscript_by_name(args.manuscript)

        if manuscript:
            manuscript_id = manuscript.id
            print(f"Generating .bib for manuscript: {manuscript.name}")
        else:
            print(f"Warning: Manuscript '{args.manuscript}' not found, generating for all papers with citation keys")

    try:
        output = service.generate_bib_file(
            manuscript_id=manuscript_id,
            include_uncited=args.include_uncited
        )

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"Generated: {args.output}")
            # Count entries
            count = output.count('@')
            print(f"Total entries: {count}")
        else:
            print(output)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_bib_fix(args):
    """Fix and standardize a .bib file."""
    session = get_session()
    manuscript, bib_path = get_manuscript_and_bib(args, session)
    service = BibtexService(session)

    print(f"Fixing: {bib_path}")
    print(f"Manuscript: {manuscript.name}")
    print(f"Dry run: {args.dry_run}")
    print()

    try:
        output, result, key_mapping = service.fix_bib_file(
            bib_path=bib_path,
            output_path=args.output,
            standardize_keys=not args.no_standardize,
            remove_duplicates=not args.keep_duplicates,
            add_missing_from_db=args.add_missing,
            manuscript_id=manuscript.id,
            dry_run=args.dry_run
        )

        print(f"{'='*60}")
        print(f"BibTeX Fix Results")
        print(f"{'='*60}")
        print()

        print(f"Entries processed:    {result.entries_processed}")
        print(f"Keys standardized:    {result.keys_standardized}")
        print(f"Duplicates removed:   {result.duplicates_removed}")
        print(f"Entries added from DB: {result.entries_added_from_db}")
        print()

        if key_mapping:
            print(f"KEY CHANGES ({len(key_mapping)}):")
            for old_key, new_key in sorted(key_mapping.items()):
                print(f"  {old_key} -> {new_key}")
            print()

        if result.warnings:
            print(f"WARNINGS ({len(result.warnings)}):")
            for warning in result.warnings:
                print(f"  - {warning}")
            print()

        if args.dry_run:
            print("Dry run complete. No files modified.")
            print("Run without --dry-run to apply changes.")
        else:
            out_path = args.output or bib_path
            print(f"Output written to: {out_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_bib_missing(args):
    """Show citations missing from .bib file."""
    session = get_session()
    manuscript, bib_path = get_manuscript_and_bib(args, session)
    service = BibtexService(session)

    print(f"Checking: {bib_path}")
    print(f"Manuscript: {manuscript.name}")
    print()

    try:
        missing = service.get_missing_bib_entries(manuscript.id, bib_path)

        if not missing:
            print("No missing entries! All citations have .bib entries.")
            return

        print(f"MISSING BIB ENTRIES ({len(missing)}):")
        print(f"{'='*60}")
        print()

        can_generate = 0
        cannot_generate = 0

        for key, paper in sorted(missing, key=lambda x: x[0]):
            if paper:
                can_generate += 1
                print(f"  {key}")
                print(f"    -> Can generate from DB: Paper #{paper.id}")
                print(f"       {paper.title[:60]}...")
                if args.verbose:
                    bib_entry = service.generate_bib_entry(paper)
                    print()
                    for line in bib_entry.split('\n'):
                        print(f"       {line}")
                print()
            else:
                cannot_generate += 1
                print(f"  {key}")
                print(f"    -> NOT IN DATABASE - need to add manually")
                print()

        print(f"Summary:")
        print(f"  Can generate from DB:  {can_generate}")
        print(f"  Not in database:       {cannot_generate}")

        if can_generate > 0 and args.generate:
            print()
            confirm = input(f"Generate {can_generate} missing entries to {args.generate}? [y/N]: ")
            if confirm.lower() == 'y':
                entries = []
                for key, paper in missing:
                    if paper:
                        entries.append(service.generate_bib_entry(paper))

                with open(args.generate, 'w', encoding='utf-8') as f:
                    f.write(f"% Missing entries generated by literature-database\n\n")
                    f.write('\n\n'.join(entries))
                print(f"Generated {can_generate} entries to {args.generate}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def cmd_bib_unused(args):
    """Show .bib entries not cited in manuscript."""
    session = get_session()
    manuscript, bib_path = get_manuscript_and_bib(args, session)
    service = BibtexService(session)

    print(f"Checking: {bib_path}")
    print(f"Manuscript: {manuscript.name}")
    print()

    try:
        unused = service.get_unused_bib_entries(manuscript.id, bib_path)

        if not unused:
            print("No unused entries! All .bib entries are cited.")
            return

        print(f"UNUSED BIB ENTRIES ({len(unused)}):")
        print(f"{'='*60}")
        print()

        for entry in sorted(unused, key=lambda e: e.citation_key):
            title = entry.title[:50] + "..." if entry.title and len(entry.title) > 50 else entry.title
            print(f"  {entry.citation_key}")
            if title:
                print(f"    {title}")
            print()

        print(f"Total unused: {len(unused)}")
        print()
        print("These entries are in your .bib file but not cited in the manuscript.")
        print("You may want to remove them or add citations.")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description='Citation mapping CLI for literature-database',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Register command
    reg_parser = subparsers.add_parser('register', help='Register a new manuscript')
    reg_parser.add_argument('name', help='Unique name for the manuscript')
    reg_parser.add_argument('--path', required=True, help='Project root path')
    reg_parser.add_argument('--tex', default='paper/tex', help='TeX directory (relative)')
    reg_parser.add_argument('--bib', help='BibTeX file path (relative)')
    reg_parser.add_argument('--description', help='Description of the manuscript')

    # List command
    list_parser = subparsers.add_parser('list', help='List registered manuscripts')

    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan manuscript for citations')
    scan_parser.add_argument('manuscript', help='Manuscript ID or name')
    scan_parser.add_argument('--append', action='store_true',
                            help='Append to existing (do not clear)')
    scan_parser.add_argument('-v', '--verbose', action='store_true',
                            help='Show detailed output')

    # Check command
    check_parser = subparsers.add_parser('check', help='Check citation consistency')
    check_parser.add_argument('manuscript', help='Manuscript ID or name')
    check_parser.add_argument('-v', '--verbose', action='store_true',
                             help='Show detailed output')

    # Report command
    report_parser = subparsers.add_parser('report', help='Show citation summary')
    report_parser.add_argument('manuscript', help='Manuscript ID or name')
    report_parser.add_argument('-v', '--verbose', action='store_true',
                              help='Show file locations')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export citation registry')
    export_parser.add_argument('manuscript', help='Manuscript ID or name')
    export_parser.add_argument('--format', choices=['json', 'csv'], default='json',
                              help='Export format')
    export_parser.add_argument('-o', '--output', help='Output file (stdout if not set)')

    # Suggest command
    suggest_parser = subparsers.add_parser('suggest', help='Suggest citation keys')
    suggest_parser.add_argument('--apply', action='store_true',
                               help='Apply all suggestions')

    # Set-key command
    setkey_parser = subparsers.add_parser('set-key', help='Set citation key for a paper')
    setkey_parser.add_argument('paper_id', type=int, help='Paper ID')
    setkey_parser.add_argument('key', help='Citation key to set')

    # ========== BibTeX Commands ==========

    # bib-analyze command
    bib_analyze_parser = subparsers.add_parser('bib-analyze', help='Analyze .bib file for issues')
    bib_analyze_parser.add_argument('manuscript', help='Manuscript ID or name')
    bib_analyze_parser.add_argument('--bib', help='Path to .bib file (relative to project)')
    bib_analyze_parser.add_argument('-v', '--verbose', action='store_true',
                                    help='Show unmatched entries')

    # bib-generate command
    bib_generate_parser = subparsers.add_parser('bib-generate', help='Generate .bib from database')
    bib_generate_parser.add_argument('manuscript', nargs='?', help='Manuscript ID or name (optional)')
    bib_generate_parser.add_argument('-o', '--output', help='Output file path')
    bib_generate_parser.add_argument('--include-uncited', action='store_true',
                                     help='Include papers not cited in manuscript')

    # bib-fix command
    bib_fix_parser = subparsers.add_parser('bib-fix', help='Fix and standardize .bib file')
    bib_fix_parser.add_argument('manuscript', help='Manuscript ID or name')
    bib_fix_parser.add_argument('--bib', help='Path to .bib file (relative to project)')
    bib_fix_parser.add_argument('-o', '--output', help='Output file path (default: overwrite input)')
    bib_fix_parser.add_argument('--dry-run', action='store_true',
                                help='Show changes without writing')
    bib_fix_parser.add_argument('--no-standardize', action='store_true',
                                help='Do not standardize citation keys')
    bib_fix_parser.add_argument('--keep-duplicates', action='store_true',
                                help='Do not remove duplicates')
    bib_fix_parser.add_argument('--add-missing', action='store_true',
                                help='Add missing entries from database')

    # bib-missing command
    bib_missing_parser = subparsers.add_parser('bib-missing', help='Show citations missing from .bib')
    bib_missing_parser.add_argument('manuscript', help='Manuscript ID or name')
    bib_missing_parser.add_argument('--bib', help='Path to .bib file (relative to project)')
    bib_missing_parser.add_argument('-v', '--verbose', action='store_true',
                                    help='Show generated bib entries')
    bib_missing_parser.add_argument('--generate', metavar='FILE',
                                    help='Generate missing entries to file')

    # bib-unused command
    bib_unused_parser = subparsers.add_parser('bib-unused', help='Show .bib entries not cited')
    bib_unused_parser.add_argument('manuscript', help='Manuscript ID or name')
    bib_unused_parser.add_argument('--bib', help='Path to .bib file (relative to project)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to command handler
    commands = {
        'register': cmd_register,
        'list': cmd_list,
        'scan': cmd_scan,
        'check': cmd_check,
        'report': cmd_report,
        'export': cmd_export,
        'suggest': cmd_suggest,
        'set-key': cmd_set_key,
        # BibTeX commands
        'bib-analyze': cmd_bib_analyze,
        'bib-generate': cmd_bib_generate,
        'bib-fix': cmd_bib_fix,
        'bib-missing': cmd_bib_missing,
        'bib-unused': cmd_bib_unused,
    }

    commands[args.command](args)


if __name__ == '__main__':
    main()
