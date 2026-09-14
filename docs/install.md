# Install

For a kiosk or a desktop that should just work, install from the latest release and let it keep itself updated:

```bash
curl -fsSL https://raw.githubusercontent.com/dkoch84/lp/master/deploy/install.sh | bash -s -- --music /path/to/music
```

## Updates

lp checks GitHub for a new release every 6 hours and switches to it once the album you are playing has finished. Nothing runs as root, and nobody has to ssh in.

In the web UI, tap the release name at the top. It shows what you have, and when a new release is out: **Install now** or **Install after this album**.

To check less often, or to only install by hand, set this in `config.yml`:

```yaml
updates:
  auto: true
  check_hours: 6
```

The kiosk service, audio, where files live and how releases are made: [deploy/DEPLOYMENT.md](../deploy/DEPLOYMENT.md).
