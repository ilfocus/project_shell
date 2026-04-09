# Tencent Lighthouse IP Sync

This tool keeps selected Tencent Lighthouse firewall rules aligned with your current public IP.

## Files

- `tencent_lighthouse_ip_sync.py`: one-shot sync script.
- `tencent_lighthouse_ip_sync.example.json`: config template.
- `run_tencent_lighthouse_ip_sync.sh`: run once manually.
- `com.qiwang.tencent-lighthouse-ip-sync.plist`: `launchd` job definition.
- `install_tencent_lighthouse_ip_sync_launchd.sh`: install and start the `launchd` job.
- `uninstall_tencent_lighthouse_ip_sync_launchd.sh`: stop and remove the `launchd` job.

## Setup

1. Copy the config template:

   ```bash
   cp project_shell/tencent_lighthouse_ip_sync.example.json project_shell/tencent_lighthouse_ip_sync.json
   ```

2. Edit `project_shell/tencent_lighthouse_ip_sync.json`:
   - `secret_id` / `secret_key`: Tencent Cloud API key.
   - `region`: Lighthouse region, for example `ap-guangzhou`.
   - `instance_id`: Lighthouse instance ID like `lhins-xxxx`.
   - `managed_rules`: the ports you want this script to manage dynamically.

3. Make the shell helpers executable:

   ```bash
   chmod +x project_shell/*.sh
   ```

## Run Once

Preview changes without writing:

```bash
./project_shell/run_tencent_lighthouse_ip_sync.sh --dry-run
```

Apply immediately:

```bash
./project_shell/run_tencent_lighthouse_ip_sync.sh
```

Force an update even if the cached IP is unchanged:

```bash
./project_shell/run_tencent_lighthouse_ip_sync.sh --force
```

## Manage With launchd

Install and start:

```bash
./project_shell/install_tencent_lighthouse_ip_sync_launchd.sh
```

Check status:

```bash
launchctl print gui/$(id -u)/com.qiwang.tencent-lighthouse-ip-sync
```

Stop and remove:

```bash
./project_shell/uninstall_tencent_lighthouse_ip_sync_launchd.sh
```

Restart after a config change:

```bash
./project_shell/uninstall_tencent_lighthouse_ip_sync_launchd.sh
./project_shell/install_tencent_lighthouse_ip_sync_launchd.sh
```

## Logs

- Script log: `project_shell/tencent_lighthouse_ip_sync.log`
- launchd stdout: `project_shell/tencent_lighthouse_ip_sync.launchd.out.log`
- launchd stderr: `project_shell/tencent_lighthouse_ip_sync.launchd.err.log`

## Important Behavior

- The script fetches all current Lighthouse firewall rules first.
- It removes existing rules that match the same `protocol + port + action` as your `managed_rules`.
- It then adds those managed rules back with your current public IP in `/32` format.
- Other firewall rules, such as SSH or Ping, are preserved.

Before enabling automation, remove old manually maintained rules for the same ports if they are no longer needed.
