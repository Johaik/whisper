# Security Guide

This document covers security considerations for the Whisper deployment.

## Network Security

### Port Binding

All Docker container ports are bound to `127.0.0.1` (localhost only):

| Port | Service | Binding | Network Access |
|------|---------|---------|----------------|
| 5432 | PostgreSQL | `127.0.0.1:5432` | Localhost only |
| 6379 | Redis | `127.0.0.1:6379` | Localhost only |
| 8000 | API | `127.0.0.1:8000` | Localhost only |

**This means:**
- Services are NOT accessible from other machines on the network
- You must access the API from the Windows machine itself
- Database and Redis are protected from external access

### WinRM Access

WinRM (port 5985) remains open for Ansible management:
- Used for deployment automation
- Should be restricted to trusted networks
- Consider using HTTPS (port 5986) for production

### How Port Security is Applied

During deployment, the `docker-compose.yml` is modified:

```yaml
# Before (accessible from network)
ports:
  - "8000:8000"

# After (localhost only)
ports:
  - "127.0.0.1:8000:8000"
```

## Credential Security

### GitHub Token

The GitHub Personal Access Token is stored securely:

```
ansible/.ghcr_token  # Git-ignored file
```

**Best practices:**
- Never commit tokens to Git
- Use minimal required scopes (`read:packages`, `write:packages`)
- Rotate tokens periodically
- Use fine-grained tokens when possible

### Windows Credentials

Ansible credentials are stored in `ansible/inventory.ini`:

```ini
ansible_user=username
ansible_password=password  # Consider using ansible-vault
```

**For production, use Ansible Vault:**

```bash
# Encrypt the password
ansible-vault encrypt_string 'your_password' --name 'ansible_password'

# Use in inventory
ansible_password: !vault |
  $ANSIBLE_VAULT;1.1;AES256
  ...
```

### API Token

The API uses bearer token authentication:

```bash
# Set in .env
API_TOKEN=your-secure-random-token

# Use in requests
curl -H "Authorization: Bearer your-secure-random-token" ...
```

**Recommendations:**
- Use a long, random token (32+ characters)
- Different tokens for dev and production
- Rotate tokens if compromised

## Database Security

### PostgreSQL

- Password is set in `docker-compose.yml`
- Data persists in `C:\app\postgres-data`
- Not accessible from network (localhost only)

**Change default password:**

```yaml
# In docker-compose.yml
postgres:
  environment:
    POSTGRES_PASSWORD: your_secure_password
```

### Redis

- No password by default (internal network only)
- Data persists in `C:\app\redis-data`

**Add password protection:**

```yaml
# In docker-compose.yml
redis:
  command: redis-server --requirepass your_password
```

## File System Security

### Windows Permissions

Ensure proper permissions on:

```
C:\app\                    # Application root
C:\app\Calls\              # Audio files (sensitive)
C:\app\outputs\            # Transcripts (sensitive)
C:\app\postgres-data\      # Database files
```

**Recommended:**
- Restrict access to the service account
- Don't share the `Calls` folder unnecessarily
- Backup `postgres-data` securely

### Google Drive Integration

When using Google Drive:
- Files are copied (not moved) to `C:\app\Calls`
- Original files on Google Drive are not modified
- `processed-files.txt` tracks what's been copied

## Sensitive Data

### Audio Recordings

Audio files may contain sensitive conversations:
- Store in encrypted volumes if required
- Limit access to authorized personnel
- Implement retention policies

### Transcripts

Transcripts contain the text of conversations:
- Stored in PostgreSQL database
- Output JSON files in `C:\app\outputs`
- Consider encryption at rest

### Caller Information

Phone numbers and names are stored:
- In database recordings table
- Consider PII regulations (GDPR, etc.)

## Audit Logging

### Container Logs

View logs for security events:

```bash
# All containers
docker compose logs

# Specific container
docker logs whisper-api

# Follow logs
docker logs -f whisper-worker
```

### What's Logged

- API requests (without auth tokens)
- Processing steps
- Errors and exceptions
- File discovery events

## Security Checklist

### Initial Setup

- [ ] Change default API token
- [ ] Change default database password
- [ ] Store GitHub token securely
- [ ] Configure Windows firewall
- [ ] Restrict WinRM access

### Ongoing

- [ ] Rotate credentials periodically
- [ ] Monitor container logs
- [ ] Keep Docker images updated
- [ ] Backup database regularly
- [ ] Review access permissions

## Firewall Rules (Optional)

If you need additional network security on Windows:

```powershell
# Block Docker ports from external (defense in depth)
New-NetFirewallRule -DisplayName "Block External 5432" `
  -Direction Inbound -LocalPort 5432 -Protocol TCP -Action Block

New-NetFirewallRule -DisplayName "Block External 6379" `
  -Direction Inbound -LocalPort 6379 -Protocol TCP -Action Block

New-NetFirewallRule -DisplayName "Block External 8000" `
  -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Block
```

## Incident Response

### If Credentials Compromised

1. **GitHub Token:**
   - Revoke token at github.com/settings/tokens
   - Generate new token
   - Update `ansible/.ghcr_token`
   - Re-deploy: `make deploy`

2. **API Token:**
   - Update `API_TOKEN` in `.env`
   - Restart containers
   - Update all clients using the API

3. **Database Password:**
   - Stop containers
   - Update password in compose file
   - May need to recreate database
   - Restart containers

### If Data Breach Suspected

1. Stop all containers: `docker compose down`
2. Preserve logs for investigation
3. Check access logs
4. Notify affected parties if required
5. Reset all credentials
6. Review and update security measures
