"""Local API entry point with reload deliberately scoped to Python source only."""
from pathlib import Path
import uvicorn


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        # `data/` is a sibling of `app/`, not a child.  Limiting watchfiles to
        # app therefore excludes engagement data, package staging/snapshots, and
        # execution artifacts without Uvicorn's Windows-incompatible glob parser.
        reload_dirs=[str(root / "app")],
    )
