"""Load the 50 seed listings + mock comps into the configured database (idempotent)."""
from app.logging_config import setup_logging
from app.main import bootstrap

if __name__ == "__main__":
    setup_logging("INFO")
    bootstrap(load_seed=True)
    print("seeded")
