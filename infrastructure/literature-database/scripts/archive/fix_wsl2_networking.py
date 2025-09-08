#!/usr/bin/env python
"""Fix WSL2 networking issues for Zotero API access."""
import os
import sys
import subprocess
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from rich.panel import Panel

console = Console()

def check_windows_version():
    """Check Windows version to determine available networking features."""
    try:
        # Try to get Windows version from WSL
        result = subprocess.run(['powershell.exe', '-Command', 
                               '(Get-WmiObject -Class Win32_OperatingSystem).Version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip()
            console.print(f"[cyan]Windows version detected: {version}[/cyan]")
            
            # Parse version to check for Windows 11 22H2+ (build 22621+)
            parts = version.split('.')
            if len(parts) >= 3:
                build = int(parts[2])
                if build >= 22621:
                    console.print("[green]✓ Windows 11 22H2+ detected - Mirrored networking available![/green]")
                    return True, build
                else:
                    console.print(f"[yellow]⚠ Windows build {build} - Mirrored networking requires 22621+[/yellow]")
                    return False, build
    except Exception as e:
        console.print(f"[red]Could not detect Windows version: {e}[/red]")
    
    return False, 0

def check_wslconfig():
    """Check current .wslconfig file."""
    windows_home = os.path.expanduser("~")
    # Try to get Windows home directory
    try:
        result = subprocess.run(['powershell.exe', '-Command', '$env:USERPROFILE'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            windows_home = result.stdout.strip()
            # Convert Windows path to WSL path
            if windows_home.startswith('C:'):
                windows_home = windows_home.replace('C:', '/mnt/c')
                windows_home = windows_home.replace('\\', '/')
    except Exception:
        pass
    
    wslconfig_path = Path(windows_home) / ".wslconfig"
    
    console.print(f"[cyan]Checking .wslconfig at: {wslconfig_path}[/cyan]")
    
    if wslconfig_path.exists():
        try:
            content = wslconfig_path.read_text()
            console.print("[green]✓ .wslconfig exists[/green]")
            console.print("Current content:")
            console.print(content)
            return True, content, wslconfig_path
        except Exception as e:
            console.print(f"[red]Could not read .wslconfig: {e}[/red]")
    else:
        console.print("[yellow]⚠ .wslconfig does not exist[/yellow]")
    
    return False, "", wslconfig_path

def create_or_update_wslconfig(supports_mirrored, wslconfig_path):
    """Create or update .wslconfig with networking fixes."""
    console.print("\n[bold blue]WSL2 Networking Configuration Options[/bold blue]")
    
    config_lines = []
    
    if supports_mirrored:
        console.print("[green]Option 1: Mirrored Networking (Recommended for Windows 11 22H2+)[/green]")
        if Confirm.ask("Enable mirrored networking mode?", default=True):
            config_lines.extend([
                "[wsl2]",
                "networkingMode=mirrored",
                "dnsTunneling=true",
                "autoProxy=true"
            ])
    
    if not config_lines:
        console.print("[yellow]Option 2: Enhanced compatibility settings[/yellow]")
        if Confirm.ask("Enable enhanced networking compatibility?", default=True):
            config_lines.extend([
                "[wsl2]",
                "dnsTunneling=true", 
                "autoProxy=true"
            ])
    
    if config_lines:
        try:
            # Ensure directory exists
            wslconfig_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write configuration
            content = "\n".join(config_lines) + "\n"
            wslconfig_path.write_text(content)
            
            console.print(f"[green]✓ .wslconfig updated at {wslconfig_path}[/green]")
            console.print("New configuration:")
            console.print(content)
            
            console.print("\n[bold yellow]⚠ WSL restart required![/bold yellow]")
            console.print("Run the following in Windows PowerShell (as Administrator):")
            console.print("[cyan]wsl --shutdown[/cyan]")
            console.print("Then restart your WSL2 instance")
            
            return True
        except Exception as e:
            console.print(f"[red]Failed to write .wslconfig: {e}[/red]")
    
    return False

def test_alternative_urls():
    """Test alternative connection methods."""
    console.print("\n[bold blue]Testing Alternative Connection Methods[/bold blue]")
    
    import requests
    
    # Get hostname for mDNS
    try:
        hostname = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()
        console.print(f"[cyan]WSL hostname: {hostname}[/cyan]")
    except:
        hostname = "localhost"
    
    test_urls = [
        "http://localhost:23119/api",
        f"http://{hostname}.local:23119/api",
        "http://127.0.0.1:23119/api"
    ]
    
    # Add Windows host IP
    try:
        result = subprocess.run(['ip', 'route', 'show', 'default'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            import re
            match = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                windows_ip = match.group(1)
                test_urls.insert(1, f"http://{windows_ip}:23119/api")
    except:
        pass
    
    working_urls = []
    
    for url in test_urls:
        console.print(f"[yellow]Testing: {url}[/yellow]")
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                console.print(f"[green]✓ Working: {url}[/green]")
                working_urls.append(url)
            else:
                console.print(f"[red]✗ Status {response.status_code}: {url}[/red]")
        except requests.exceptions.ConnectTimeout:
            console.print(f"[red]✗ Connection timeout: {url}[/red]")
        except requests.exceptions.ConnectionError:
            console.print(f"[red]✗ Connection refused: {url}[/red]")
        except Exception as e:
            console.print(f"[red]✗ Error: {url} - {e}[/red]")
    
    return working_urls

def suggest_windows_fixes():
    """Suggest Windows-side fixes."""
    console.print("\n[bold blue]Windows-side Fixes to Try[/bold blue]")
    
    console.print("\n[yellow]1. Hyper-V Firewall Rules (Windows 11 22H2+):[/yellow]")
    console.print("Run in PowerShell as Administrator:")
    console.print("[cyan]Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow[/cyan]")
    
    console.print("\n[yellow]2. Check Zotero Binding:[/yellow]")
    console.print("In Zotero preferences, ensure API server binds to all interfaces (0.0.0.0) not just localhost")
    
    console.print("\n[yellow]3. Port Forwarding with netsh:[/yellow]")
    console.print("Run in Windows Command Prompt as Administrator:")
    console.print("[cyan]netsh interface portproxy add v4tov4 listenport=23119 listenaddress=0.0.0.0 connectport=23119 connectaddress=127.0.0.1[/cyan]")
    
    console.print("\n[yellow]4. Check Windows Defender Firewall:[/yellow]")
    console.print("Allow 'IP Helper service' through firewall")
    console.print("Create inbound rule for TCP port 23119")
    
    console.print("\n[yellow]5. Alternative: Use Zotero Web API instead[/yellow]")
    console.print("Get API key from https://www.zotero.org/settings/keys")

def main():
    """Main WSL2 networking fix utility."""
    console.print(Panel.fit(
        "[bold green]WSL2-Windows Networking Fixer for Zotero[/bold green]\n"
        "This tool will help fix networking issues between WSL2 and Windows\n"
        "for accessing Zotero's local API server.",
        title="WSL2 Network Fix"
    ))
    
    # Check Windows version
    supports_mirrored, build = check_windows_version()
    
    # Check current WSL config
    has_config, current_config, wslconfig_path = check_wslconfig()
    
    # Update WSL config if needed
    if Confirm.ask("\nUpdate .wslconfig with networking fixes?", default=True):
        if create_or_update_wslconfig(supports_mirrored, wslconfig_path):
            console.print("\n[green]✓ Configuration updated![/green]")
            console.print("[yellow]Please restart WSL2 and test again[/yellow]")
        else:
            console.print("[red]Failed to update configuration[/red]")
    
    # Test alternative URLs
    if Confirm.ask("\nTest alternative connection methods now?", default=True):
        working_urls = test_alternative_urls()
        if working_urls:
            console.print(f"\n[green]✓ Found {len(working_urls)} working URLs![/green]")
            for url in working_urls:
                console.print(f"  • {url}")
        else:
            console.print("\n[red]No working URLs found[/red]")
            suggest_windows_fixes()

if __name__ == '__main__':
    main()