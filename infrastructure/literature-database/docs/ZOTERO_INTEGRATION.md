# Zotero Integration Guide

Comprehensive guide for integrating the Literature Database with Zotero on Windows 11 through WSL2.

## 🎯 Integration Overview

The Literature Database supports multiple Zotero integration methods with automatic fallback:

1. **Local API** (Recommended) - Direct communication with running Zotero instance
2. **Web API** - Cloud-based sync through Zotero's servers
3. **File-based** - Direct import from Zotero's file storage

## 🔌 Method 1: Local API Integration

### Advantages
- ✅ **No API key required** - Direct access to running Zotero
- ✅ **Real-time sync** - Immediate access to current library state
- ✅ **Full access** - Read/write without web API limitations  
- ✅ **Faster & more reliable** - Local network vs internet requests
- ✅ **No rate limits** - Unrestricted access to your data

### Setup Steps

#### 1. Enable Zotero HTTP Server
```
Zotero → Edit → Preferences → Advanced → Config Editor
Search: extensions.zotero.httpServer.enabled
Set to: true
Restart Zotero
```

#### 2. Test Basic Connectivity
```bash
# From Windows Command Prompt
curl http://localhost:23119/api

# Should return Zotero API information
```

#### 3. WSL2 Network Configuration

**Option A: Mirrored Networking (Windows 11 22H2+)**

Create/edit `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
autoProxy=true
```

Restart WSL:
```powershell
wsl --shutdown
# Wait 10 seconds, restart WSL terminal
```

**Option B: Firewall Rules**
```cmd
# Run as Administrator in Windows Command Prompt
netsh advfirewall firewall add rule name="Zotero API WSL" dir=in action=allow protocol=TCP localport=23119
```

**Option C: Hyper-V Firewall (Windows 11 22H2+)**
```powershell
# Run as Administrator in PowerShell
Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow
```

#### 4. Test WSL2 Connection
```bash
# Test connection from WSL2
python scripts/test_zotero_local.py
```

Expected output:
```
✓ Local API is available!
✓ Library info retrieved
✓ Retrieved X items
✓ Retrieved X collections
```

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

### Troubleshooting Local API

#### Connection Timeout
```bash
# Run comprehensive network diagnostic
python scripts/fix_wsl2_networking.py

# Test alternative URLs
curl http://localhost:23119/api
curl http://$(hostname).local:23119/api
curl http://$(ip route show default | awk '/default/ {print $3}'):23119/api
```

#### Windows Firewall Blocking
1. **Check Windows Defender Firewall settings**
2. **Allow IP Helper service through firewall**
3. **Create specific rule for port 23119**

#### Zotero Not Binding to Network Interface
- **Check Zotero preferences for API server settings**
- **Restart Zotero after enabling HTTP server**
- **Ensure no other applications are using port 23119**

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

### Automatic Fallback Chain

The system tries connection methods in this order:

1. **Local API** (`http://localhost:23119/api`)
2. **mDNS Local** (`http://hostname.local:23119/api`)  
3. **Windows Host IP** (`http://172.x.x.x:23119/api`)
4. **Web API** (if configured)
5. **Error** if none available

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
3. Try local API instead

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