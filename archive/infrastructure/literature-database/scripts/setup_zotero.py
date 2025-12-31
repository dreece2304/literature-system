#!/usr/bin/env python
"""Interactive Zotero setup and configuration."""
import sys
from pathlib import Path
import yaml
import requests
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.extractors.zotero_sync import ZoteroSync
from src.utils.logging import setup_logging

console = Console()


def find_user_id_from_url():
    """Help user find their Zotero user ID."""
    console.print("\n[bold blue]Finding Your Zotero User ID:[/bold blue]")
    console.print("1. Go to https://www.zotero.org/")
    console.print("2. Sign in to your account")
    console.print("3. Look at the URL - it should show something like:")
    console.print("   [cyan]https://www.zotero.org/dreec23/library[/cyan]")
    console.print("4. The part after 'zotero.org/' is your username")
    console.print("5. Or go to https://www.zotero.org/settings/keys")
    console.print("   Your User ID is shown at the top")
    
    return Prompt.ask("\nWhat is your Zotero User ID or username?")


def get_api_key():
    """Guide user through API key creation."""
    console.print("\n[bold blue]Creating Zotero API Key:[/bold blue]")
    console.print("1. Go to: [link]https://www.zotero.org/settings/keys[/link]")
    console.print("2. Click 'Create new private key'")
    console.print("3. Enter a description like 'Literature Database'")
    console.print("4. Under 'Personal Library', check:")
    console.print("   ✓ Allow library access")
    console.print("   ✓ Allow write access")
    console.print("5. Under 'Default Group Permissions' (optional):")
    console.print("   ✓ Allow library access (if you use groups)")
    console.print("6. Click 'Save Key'")
    console.print("7. Copy the generated key (it won't be shown again!)")
    
    api_key = Prompt.ask("\nPaste your API key here", password=True)
    return api_key


def test_api_connection(user_id: str, api_key: str) -> bool:
    """Test the Zotero API connection."""
    console.print("\n[blue]Testing API connection...[/blue]")
    
    try:
        # Test API endpoint
        url = f"https://api.zotero.org/users/{user_id}/items"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Zotero-API-Version': '3'
        }
        params = {'limit': 1}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            console.print(f"[green]✓ API connection successful![/green]")
            console.print(f"[green]✓ Found {response.headers.get('Total-Results', '?')} items in your library[/green]")
            return True
        elif response.status_code == 403:
            console.print("[red]✗ API key invalid or insufficient permissions[/red]")
            return False
        else:
            console.print(f"[red]✗ API error: {response.status_code}[/red]")
            return False
            
    except requests.RequestException as e:
        console.print(f"[red]✗ Connection failed: {e}[/red]")
        return False


def find_zotero_directory():
    """Help user find their Zotero data directory."""
    console.print("\n[bold blue]Finding Zotero Data Directory:[/bold blue]")
    console.print("1. Open Zotero on your Windows computer")
    console.print("2. Go to: Edit → Preferences → Advanced → Files and Folders")
    console.print("3. Note the 'Data Directory Location'")
    console.print("4. It's usually something like:")
    console.print("   [cyan]C:\\Users\\YourName\\Zotero[/cyan]")
    console.print("\nSince you're using WSL, convert the path:")
    console.print("   Windows: [cyan]C:\\Users\\YourName\\Zotero[/cyan]")
    console.print("   WSL:     [cyan]/mnt/c/Users/YourName/Zotero[/cyan]")
    
    while True:
        zotero_path = Prompt.ask("\nEnter your Zotero data directory path (WSL format)")
        path_obj = Path(zotero_path)
        
        if path_obj.exists():
            # Check if it looks like a Zotero directory
            if (path_obj / "zotero.sqlite").exists():
                console.print("[green]✓ Valid Zotero directory found![/green]")
                return str(path_obj)
            else:
                console.print("[yellow]⚠ Directory exists but doesn't contain zotero.sqlite[/yellow]")
                if Confirm.ask("Use this path anyway?"):
                    return str(path_obj)
        else:
            console.print("[red]✗ Directory not found[/red]")
            if not Confirm.ask("Try again?"):
                return zotero_path


def update_configuration(user_id: str, api_key: str, data_path: str):
    """Update configuration files with Zotero settings."""
    console.print("\n[blue]Updating configuration files...[/blue]")
    
    # Update settings.yml
    settings_path = Path("config/settings.yml")
    try:
        with open(settings_path, 'r') as f:
            settings = yaml.safe_load(f)
        
        settings['zotero']['library_id'] = user_id
        settings['zotero']['windows_path'] = data_path
        
        with open(settings_path, 'w') as f:
            yaml.dump(settings, f, default_flow_style=False, indent=2)
        
        console.print(f"[green]✓ Updated {settings_path}[/green]")
        
    except Exception as e:
        console.print(f"[red]✗ Failed to update settings.yml: {e}[/red]")
        return False
    
    # Update credentials.yml
    credentials_path = Path("config/credentials.yml")
    try:
        try:
            with open(credentials_path, 'r') as f:
                credentials = yaml.safe_load(f) or {}
        except FileNotFoundError:
            credentials = {}
        
        if 'zotero' not in credentials:
            credentials['zotero'] = {}
        
        credentials['zotero']['api_key'] = api_key
        
        with open(credentials_path, 'w') as f:
            f.write("# DO NOT COMMIT THIS FILE - CONTAINS API KEYS\n")
            yaml.dump(credentials, f, default_flow_style=False, indent=2)
        
        console.print(f"[green]✓ Updated {credentials_path}[/green]")
        
    except Exception as e:
        console.print(f"[red]✗ Failed to update credentials.yml: {e}[/red]")
        return False
    
    return True


def test_integration():
    """Test the complete Zotero integration."""
    console.print("\n[blue]Testing literature database integration...[/blue]")
    
    try:
        zotero_sync = ZoteroSync()
        
        if zotero_sync.is_api_available():
            console.print("[green]✓ Zotero API integration working![/green]")
            
            # Try to get collections
            collections = zotero_sync.get_collections()
            if collections:
                console.print(f"[green]✓ Found {len(collections)} collections[/green]")
                
                # Show first few collections
                table = Table(title="Your Zotero Collections")
                table.add_column("Name", style="cyan")
                table.add_column("Key", style="yellow")
                
                for collection in collections[:5]:  # Show first 5
                    table.add_row(
                        collection.get('data', {}).get('name', 'Unnamed'),
                        collection.get('key', 'No key')
                    )
                
                console.print(table)
            else:
                console.print("[yellow]⚠ No collections found (this is okay)[/yellow]")
            
            return True
        else:
            console.print("[red]✗ API integration not working[/red]")
            return False
            
    except Exception as e:
        console.print(f"[red]✗ Integration test failed: {e}[/red]")
        return False


def main():
    """Interactive Zotero setup."""
    setup_logging()
    
    console.print(Panel.fit(
        "[bold green]Zotero Integration Setup[/bold green]\n"
        "This will help you connect your Zotero library to the Literature Database",
        title="Setup Wizard"
    ))
    
    try:
        # Step 1: Get User ID
        user_id = find_user_id_from_url()
        
        # Step 2: Get API Key
        api_key = get_api_key()
        
        # Step 3: Test API Connection
        if not test_api_connection(user_id, api_key):
            console.print("[red]API connection failed. Please check your credentials.[/red]")
            return
        
        # Step 4: Find Zotero Directory
        data_path = find_zotero_directory()
        
        # Step 5: Update Configuration
        if not update_configuration(user_id, api_key, data_path):
            console.print("[red]Failed to update configuration files.[/red]")
            return
        
        # Step 6: Test Integration
        if test_integration():
            console.print(Panel.fit(
                "[bold green]✓ Zotero integration setup complete![/bold green]\n\n"
                "You can now:\n"
                "• Sync papers: [cyan]python -m src.cli sync[/cyan]\n"
                "• Start API server: [cyan]python -m src.cli serve[/cyan]\n"
                "• View stats: [cyan]python -m src.cli stats[/cyan]",
                title="Success!"
            ))
        else:
            console.print("[yellow]Configuration saved but integration test failed.[/yellow]")
            console.print("Check your settings and try running: [cyan]python -m src.cli sync[/cyan]")
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Setup cancelled by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Setup failed: {e}[/red]")


if __name__ == '__main__':
    main()