# RFMP

RFMP is a small Python project that provides a daemon and a lightweight web UI for the RFMP (radio file/message protocol) stack.

This repository contains two main components:

- `rfmp-daemon` — the core daemon implementation, configuration, protocol parsers, storage, and network adapters.
- `rfmp-web` — a minimal web UI and static frontend for interacting with the daemon.

## Contents

- `rfmp-daemon/` — daemon package, example config, systemd service, and installation scripts.
- `rfmp-web/` — web UI server, static assets, and start script.

## Quickstart

1. Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies for the component you want to run:

```bash
# For the daemon
pip install -r rfmp-daemon/requirements.txt

# For the web UI
pip install -r rfmp-web/requirements.txt
```

3. Configure the daemon by copying the example config and editing:

```bash
cp rfmp-daemon/config.yaml.example rfmp-daemon/config.yaml
# Edit rfmp-daemon/config.yaml as needed
```

4. Run the daemon (development):

```bash
python -m rfmpd.main
```

Alternatively install and run the systemd unit provided: `rfmpd.service`.

5. Start the web UI (development):

```bash
./rfmp-web/start.sh
```

## Configuration

- The main daemon config is `rfmp-daemon/config.yaml`. Use the `config.yaml.example` as a starting point.
- Network adapters, storage backends, and protocol options are configured in that file.

## Development

- Code lives under `rfmp-daemon/rfmpd` (daemon) and `rfmp-web` (web UI).
- Run the daemon locally with `python -m rfmpd.main` from the project root or after installing the package.
- Use a virtualenv and the per-component `requirements.txt` files.

## Packaging & Installation

- `rfmp-daemon/setup.py` is provided for installing the daemon as a package.
- The repository includes a `rfmpd.service` systemd unit for running the daemon as a service.

## Useful files

- `rfmp-daemon/config.yaml.example` — example daemon configuration.
- `rfmp-daemon/rfmpd/` — daemon source package.
- `rfmp-web/start.sh` — simple script to start the web UI server.

## License & Contributing

See individual component files for contributor notes. Open issues or PRs with improvements.

---

If you'd like, I can: run the daemon locally, update the README with usage examples from `rfmpd/main.py`, or add a short CONTRIBUTING guide.
