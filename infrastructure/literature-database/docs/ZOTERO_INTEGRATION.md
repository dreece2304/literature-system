# Zotero Integration Guide

Zotero integration for the literature-database service in the research monorepo.

**Service Context**: literature-database service | Port 8001

## 🎯 Integration Overview

The Literature Database supports multiple Zotero integration methods:

1. **WSL Proxy Server** (Recommended for WSL2) - Uses Zotero-WSL-ProxyServer for reliable connectivity
2. **Web API** - Cloud-based sync through Zotero's servers
3. **File-based** - Direct import from Zotero's file storage

**Note**: The Zotero connector API (port 23119) is designed for browser extensions to SAVE items to Zotero. For reading/syncing items, we use the Web API (pyzotero). The local connector is only used for detecting if Zotero is running.

## 🔌 Method 1: WSL Proxy Server (Recommended for WSL2)

### Why Use the Proxy Server?

WSL2 cannot directly access Windows `localhost:23119` because:
- WSL2 runs in a separate virtual network (NAT or mirrored mode)
- Zotero's connector API has strict HTTP header validation
- Direct port forwarding attempts are rejected by Zotero

The [Zotero-WSL-ProxyServer](https://github.com/XFY9326/Zotero-WSL-ProxyServer) solves this by:
- Running on Windows and binding to the WSL-visible IP
- Forwarding requests to Zotero's localhost connector
- Modifying HTTP headers to pass Zotero's validation

### Setup Steps

#### 1. Enable Zotero HTTP Server (in Zotero)
```
Zotero → Edit → Preferences → Advanced → Config Editor
Search: extensions.zotero.httpServer.enabled
Set to: true
Restart Zotero
```

#### 2. Download Zotero-WSL-ProxyServer

Download from: https://github.com/XFY9326/Zotero-WSL-ProxyServer/releases

```powershell
# PowerShell - Download to a convenient location
Invoke-WebRequest -Uri "https://github.com/XFY9326/Zotero-WSL-ProxyServer/releases/download/0.1.0.3/Zotero-WSL-ProxyServer_0.1.0.3.exe" -OutFile "$env:USERPROFILE\Zotero-WSL-ProxyServer.exe"
```

Or manually download and save to `C:\Users\<username>\Zotero-WSL-ProxyServer.exe`

#### 3. Run the Proxy Server

1. **Start Zotero** (must be running first)
2. **Run the proxy server** by double-clicking the exe or from PowerShell:
   ```powershell
   & "$env:USERPROFILE\Zotero-WSL-ProxyServer.exe"
   ```

The proxy will display output like:
```
Windows host IP in WSL: 172.24.208.1
Zotero status: Running
Serving on 172.24.208.1:23119
Zotero WSL url: http://DESKTOP-ABC123.local:23119
```

**Note the URL** - you'll need it for the next step!

#### 4. Configure the Proxy URL

Edit `config/settings.yml`:
```yaml
zotero:
  windows_path: "/mnt/c/Users/dreec/Zotero"
  library_id: "13344138"
  library_type: "user"

  # Use the URL shown by Zotero-WSL-ProxyServer
  proxy_url: "http://DESKTOP-ABC123.local:23119"
  # Or use the IP directly: "http://172.24.208.1:23119"
```

#### 5. Test the Connection

```bash
# From WSL, test connectivity
curl -I http://DESKTOP-ABC123.local:23119/connector/ping

# Run the test script
cd infrastructure/literature-database
python scripts/test_zotero_local.py
```

Expected output:
```
✓ Local API is available!
✓ Zotero proxy at: http://DESKTOP-ABC123.local:23119
```

### Auto-Start the Proxy (Optional)

To start the proxy automatically when Zotero starts, create a Windows Task Scheduler task or add it to your startup folder.

### Cleaning Up Firewall Rules

If you previously added firewall rules for direct WSL2 access, you can remove them:

```cmd
# Run as Administrator in Windows Command Prompt

# Remove the WSL2 Zotero rule (if added)
netsh advfirewall firewall delete rule name="Zotero API WSL"

# Remove any other Zotero-related rules
netsh advfirewall firewall delete rule name="Zotero API"

# List remaining rules to verify
netsh advfirewall firewall show rule name=all dir=in | findstr /i "zotero"
```

**Revert Hyper-V Firewall Changes** (if you made them):
```powershell
# Run as Administrator in PowerShell
# Reset to default (block inbound)
Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Block
```

**Note**: The proxy server handles connectivity, so firewall rules for port 23119 are NOT needed when using the proxy.

### Usage

```bash
# Sync from Zotero (automatically uses local API)
python -m src.cli sync

# Check API status
python -c "
from src.extractors.zotero_sync import ZoteroSync
sync = ZoteroSync()
print(f'API Info: {sync.get_api_info()}')
"
```

### Troubleshooting Proxy Server

#### Proxy Not Starting
1. **Ensure Zotero is running first** - The proxy checks for Zotero
2. **Check if port 23119 is already in use** (another instance?)
3. **Run from command line** to see error messages

#### WSL Cannot Reach Proxy
```bash
# Test the hostname resolution
ping DESKTOP-ABC123.local

# Try the IP address directly
curl http://172.24.208.1:23119/connector/ping

# Update config to use IP instead of hostname
```

#### "Zotero status: Not Running"
1. **Start Zotero on Windows**
2. **Verify HTTP server is enabled** in Zotero preferences
3. **Restart Zotero** after enabling

## 🌐 Method 2: Web API Integration  

### Advantages
- ✅ **Always available** - Works from anywhere with internet
- ✅ **No networking issues** - Bypasses WSL2 complications
- ✅ **Cloud sync** - Access to your library from multiple devices
- ✅ **Official support** - Zotero's primary API method

### Setup Steps

#### 1. Get API Key
1. **Visit**: https://www.zotero.org/settings/keys
2. **Create new private key** with description "Literature Database"
3. **Enable permissions**:
   - ✅ Allow library access
   - ✅ Allow write access
   - ✅ Allow group library access (if using groups)

#### 2. Find User ID
**Method A: From Zotero URL**
- Visit your Zotero library: https://www.zotero.org/[username]/library
- Your username/ID is in the URL

**Method B: From API**
- Use the key to query: https://api.zotero.org/users/[USER-ID]/items?limit=1

#### 3. Configure Credentials

Update `config/credentials.yml`:
```yaml
zotero:
  api_key: "your-actual-api-key-here"
```

Update `config/settings.yml`:
```yaml
zotero:
  library_id: "your-user-id-or-username"
  library_type: "user"  # or "group" for group libraries
```

#### 4. Test Web API
```bash
# Run interactive setup wizard
python scripts/setup_zotero.py

# Manual test
python -c "
from src.extractors.zotero_sync import ZoteroSync
sync = ZoteroSync()
if sync.client:
    items = sync.client.items(limit=5)
    print(f'Found {len(items)} items via web API')
"
```

### Usage

```bash
# Sync from Zotero web API
python -m src.cli sync

# Check sync status
python -m src.cli stats
```

### Web API Rate Limits

- **120 requests per minute** for authenticated requests
- **12 requests per minute** for unauthenticated requests
- **Automatic backoff** implemented in the client

## 📁 Method 3: File-based Import

### When to Use
- Local/Web APIs aren't working
- One-time import from Zotero
- Working with exported Zotero libraries
- Offline scenarios

### Zotero Export Formats

#### BibTeX Export
```bash
# Export from Zotero: File → Export Library → BibTeX
# Import to Literature Database
python scripts/import_bibtex.py "/path/to/library.bib"
```

#### RIS Export  
```bash
# Export from Zotero: File → Export Library → RIS
# Import to Literature Database
python scripts/import_ris.py "/path/to/library.ris"
```

#### PDF Collection Import
```bash
# Import PDFs from Zotero storage directory
python scripts/migrate_pdfs.py "/mnt/c/Users/[username]/Zotero/storage" --copy --organize
```

### Zotero Storage Structure

Zotero stores files in a specific structure:
```
Zotero/storage/
├── ABCD1234/          # Item key directory
│   ├── paper.pdf      # PDF attachment
│   └── .zotero-ft-cache  # Full-text cache
├── EFGH5678/
│   └── document.pdf
└── ...
```

## 🔄 Synchronization Behavior

### Connection Priority

The system tries connection methods in this order:

1. **Configured Proxy URL** (from `config/settings.yml` → `zotero.proxy_url`)
2. **Localhost** (`http://localhost:23119`) - works in mirrored networking mode
3. **Windows Host IP** (`http://172.x.x.x:23119`) - auto-detected in NAT mode
4. **Web API** (if configured with API key) - for actual sync operations

**Important**: The local connector (port 23119) is only used to detect if Zotero is running. For syncing items, the Web API (pyzotero) is always used.

### Sync Operations

#### Full Sync
```bash
# Sync all items and collections
python -m src.cli sync
```

#### Incremental Sync
The system tracks versions and only syncs changed items.

#### Conflict Resolution
- **Zotero is master** - Local changes are overwritten
- **Version tracking** - Prevents unnecessary updates
- **Error logging** - Failed items are logged for review

### Data Mapping

| Zotero Field | Literature DB Field | Notes |
|--------------|-------------------|-------|
| `title` | `title` | Direct mapping |
| `abstractNote` | `abstract` | Direct mapping |
| `date` | `year` | Extracted year from date |
| `DOI` | `doi` | Direct mapping |
| `publicationTitle` | `journal` | Journal/conference name |
| `creators` | `authors` | Mapped to Author entities |
| `tags` | `tags` | Mapped to Tag entities |
| `collections` | `collections` | Mapped to Collection entities |
| `key` | `zotero_key` | Zotero item identifier |
| `version` | `zotero_version` | For incremental sync |

## 📊 Monitoring and Maintenance

### Sync Statistics
```bash
# View sync statistics
python -m src.cli stats

# Show last sync information
python -c "
from src.database import get_session
from src.models import Paper
session = next(get_session())
zotero_papers = session.query(Paper).filter(Paper.zotero_key.isnot(None)).count()
print(f'Papers synced from Zotero: {zotero_papers}')
session.close()
"
```

### Sync Logs
```bash
# View sync logs
tail -f logs/litdb.log | grep -i zotero

# Search for sync errors
grep -i "error\|failed" logs/litdb.log | grep -i zotero
```

### Regular Maintenance

#### Daily Sync (Automated)
```bash
# Add to cron job (Linux) or Task Scheduler (Windows)
0 9 * * * cd /path/to/literature-database && python -m src.cli sync
```

#### Weekly Cleanup
```bash
# Cleanup temporary files and optimize database
python scripts/maintenance.py --cleanup --optimize
```

## 🔧 Advanced Configuration

### Custom Sync Intervals
```yaml
# config/settings.yml
zotero:
  sync_interval: 3600  # seconds between automatic syncs
  batch_size: 100      # items per batch
  timeout: 30          # API timeout in seconds
```

### Group Libraries
```yaml
# config/settings.yml  
zotero:
  library_type: "group"
  library_id: "12345"   # Group ID
```

### Selective Sync
```python
# Custom sync filters
def should_sync_item(item):
    # Only sync items with PDFs
    return item.get('data', {}).get('itemType') == 'journalArticle'
```

### API Client Customization
```python
# Custom API client settings
from pyzotero import zotero

client = zotero.Zotero(
    library_id='your-id',
    library_type='user',
    api_key='your-key',
    preserve_json_order=True,
    backoff=30  # seconds to wait on rate limit
)
```

## 🚨 Common Issues and Solutions

### Issue: API Key Invalid
**Symptoms:** 403 Forbidden errors
**Solution:** 
1. Verify API key is correct
2. Check key permissions include library access
3. Ensure library ID is correct

### Issue: Rate Limited
**Symptoms:** 429 Too Many Requests
**Solution:**
1. Reduce sync frequency
2. Use smaller batch sizes  
3. Implement exponential backoff

### Issue: Network Timeout
**Symptoms:** Connection timeout errors
**Solution:**
1. Increase timeout values
2. Check internet connection
3. Use the WSL Proxy Server (see Method 1)

### Issue: WSL2 Cannot Connect to Zotero
**Symptoms:** Connection refused, timeout when accessing localhost:23119 from WSL
**Solution:**
1. **Use Zotero-WSL-ProxyServer** (recommended) - See Method 1 above
2. Configure `proxy_url` in `config/settings.yml`
3. Remove any firewall rules that were added (the proxy handles connectivity)

### Issue: Duplicate Items
**Symptoms:** Same paper appears multiple times
**Solution:**
1. Check Zotero for duplicates
2. Use DOI-based deduplication
3. Run duplicate detection script

### Issue: Missing Attachments
**Symptoms:** Papers sync without PDFs
**Solution:**
1. Ensure PDF files exist in Zotero
2. Check file permissions
3. Use file-based import for PDFs

## 🎯 Best Practices

### Security
- **Keep API keys secure** - Never commit to version control
- **Use environment variables** for sensitive data
- **Regularly rotate API keys**
- **Monitor API usage** in Zotero settings

### Performance  
- **Sync during off-peak hours** to avoid rate limits
- **Use incremental sync** rather than full sync
- **Monitor sync duration** and optimize batch sizes
- **Regular database maintenance** for optimal performance

### Data Management
- **Regular backups** of both Zotero and Literature Database
- **Version control** for configuration changes
- **Monitor sync logs** for errors and issues
- **Periodic cleanup** of orphaned records

### Integration Workflow
1. **Primary work in Zotero** - Add papers, organize collections
2. **Regular sync** to Literature Database
3. **Enhanced search** and analysis in Literature Database
4. **Bidirectional updates** for tags and notes (if supported)

---

With proper Zotero integration, your Literature Database becomes a powerful extension of your Zotero workflow, providing advanced search, organization, and analysis capabilities while maintaining synchronization with your primary reference manager. 🎓