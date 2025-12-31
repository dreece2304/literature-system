#!/usr/bin/env python
"""Test Zotero local API connection."""
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.extractors.zotero_local_api import ZoteroLocalAPI
from src.extractors.zotero_sync import ZoteroSync

console = Console()


def test_local_api():
    """Test the Zotero local API connection."""
    console.print(Panel.fit(
        "[bold blue]Testing Zotero Local API Connection[/bold blue]\n"
        "Make sure Zotero is running on Windows with API access enabled!",
        title="Test"
    ))
    
    # Test direct local API
    console.print("\n[yellow]Testing direct local API connection...[/yellow]")
    local_api = ZoteroLocalAPI()
    console.print(f"[cyan]Using API URL: {local_api.base_url}[/cyan]")
    
    if local_api.is_available():
        console.print("[green]✓ Local API is available![/green]")
        
        # Get library info
        library_info = local_api.get_library_info()
        if library_info:
            console.print(f"[green]✓ Library info retrieved[/green]")
            console.print(f"  Library type: {library_info.get('type', 'unknown')}")
        
        # Get some items
        items = local_api.get_items(limit=5)
        console.print(f"[green]✓ Retrieved {len(items)} items (showing first 5)[/green]")
        
        if items:
            table = Table(title="Sample Items from Zotero")
            table.add_column("Type", style="cyan")
            table.add_column("Title", style="green", width=40)
            table.add_column("Key", style="yellow")
            
            for item in items:
                data = item.get('data', {})
                title = data.get('title', 'No title')
                if len(title) > 40:
                    title = title[:37] + "..."
                table.add_row(
                    data.get('itemType', 'unknown'),
                    title,
                    data.get('key', 'no key')
                )
            
            console.print(table)
        
        # Get collections
        collections = local_api.get_collections()
        console.print(f"[green]✓ Retrieved {len(collections)} collections[/green]")
        
        if collections:
            console.print("\n[blue]Collections:[/blue]")
            for collection in collections[:5]:  # Show first 5
                name = collection.get('name', 'Unnamed')
                console.print(f"  • {name}")
        
    else:
        console.print("[red]✗ Local API not available[/red]")
        console.print("\n[yellow]Troubleshooting:[/yellow]")
        console.print("1. Make sure Zotero is running on Windows")
        console.print("2. Check that HTTP API access is enabled:")
        console.print("   • Zotero → Edit → Preferences → Advanced → Config Editor")
        console.print("   • Search for: extensions.zotero.httpServer.enabled")
        console.print("   • Set to: true")
        console.print("3. Restart Zotero")
        console.print("4. The API should be available at: http://localhost:23119/api/")
    
    # Test integrated sync
    console.print("\n[yellow]Testing integrated ZoteroSync...[/yellow]")
    zotero_sync = ZoteroSync()
    
    api_info = zotero_sync.get_api_info()
    console.print(f"Local API available: {api_info['local_api']}")
    console.print(f"Web API available: {api_info['web_api']}")
    console.print(f"Preferred API: {api_info['preferred']}")
    
    if zotero_sync.is_api_available():
        console.print("[green]✓ ZoteroSync is ready to use![/green]")
        
        try:
            collections = zotero_sync.get_collections()
            console.print(f"[green]✓ Can access collections via ZoteroSync ({len(collections)} found)[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Collection access failed: {e}[/yellow]")
    else:
        console.print("[red]✗ No Zotero API available[/red]")


if __name__ == '__main__':
    test_local_api()