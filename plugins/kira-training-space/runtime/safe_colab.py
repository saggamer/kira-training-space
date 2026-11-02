"""Use installed Colab auth, suppress credential logs and background update writes."""
import logging
import sys

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    import requests
    original = requests.Session.request
    def request(session, *args, **kwargs):
        kwargs.setdefault("timeout", 25)
        try: return original(session, *args, **kwargs)
        except requests.RequestException:
            raise RuntimeError("Colab network request failed; URL details suppressed") from None
    requests.Session.request = request
    import colab_cli.cli as cli
    cli.setup_logging = lambda *a, **k: None
    # CLI checks write global settings even for read-only commands. Disable the check.
    if hasattr(cli, "auto_update"):
        cli.auto_update.run_background_check = lambda: None
    try: cli.app()
    except Exception:
        print("Colab command failed. Authenticate with the official CLI in a terminal and retry.", file=sys.stderr)
        sys.exit(1)
