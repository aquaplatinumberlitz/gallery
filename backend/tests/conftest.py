from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("ENABLE_METRICS", "0")
os.environ.setdefault("GALLERY_CATALOG_SERVICE_ENABLED", "0")

# Set process-wide safety paths before any backend module is imported. Tests
# that forget an isolation fixture must never fall back to the live cache.
_PYTEST_RUNTIME_DIR = Path(tempfile.mkdtemp(prefix="gallery-pytest-runtime-"))
os.environ["GALLERY_METADATA_DB"] = str(_PYTEST_RUNTIME_DIR / "gallery_metadata.db")
os.environ["GALLERY_THUMBNAIL_CACHE_DIR"] = str(_PYTEST_RUNTIME_DIR / "thumbnails")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_test_png(
    path: Path,
    size: tuple[int, int] = (64, 64),
    color: tuple[int, int, int] = (40, 120, 200),
    pnginfo: PngInfo | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(path, format="PNG", pnginfo=pnginfo)
    assert Image.open(path).format == "PNG", f"Expected PNG, got {Image.open(path).format}"


def create_test_jpeg(
    path: Path,
    size: tuple[int, int] = (64, 64),
    color: tuple[int, int, int] = (40, 120, 200),
    quality: int = 85,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(path, format="JPEG", quality=quality)
    opened = Image.open(path)
    assert opened.format == "JPEG", f"Expected JPEG, got {opened.format}"


def create_exif_rotated_jpeg(
    path: Path,
    size: tuple[int, int] = (1440, 1080),
    orientation: int = 6,
    quality: int = 85,
    color: tuple[int, int, int] = (40, 120, 200),
) -> None:
    """Create a JPEG with an EXIF orientation tag.

    Raw pixel buffer is landscape (e.g. 1440x1080), but EXIF Orientation=6
    (rotate 90 CW) tells compliant viewers to display it as portrait
    (1080x1440). This mimics iPhone photos.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    exif = img.getexif()
    exif[0x0112] = orientation
    img.save(path, format="JPEG", quality=quality, exif=exif.tobytes())
    opened = Image.open(path)
    assert opened.format == "JPEG", f"Expected JPEG, got {opened.format}"


def create_test_image(
    path: Path,
    size: tuple[int, int] = (64, 64),
    color: tuple[int, int, int] = (40, 120, 200),
) -> None:
    """Create an image file with the correct format based on file extension.

    Uses PIL JPEG encoder for .jpg/.jpeg files.
    Uses PIL PNG encoder for .png files.
    Falls back to PNG bytes for .webp files (Pillow has no WebP encoder).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()
    img = Image.new("RGB", size, color)
    if ext in (".jpg", ".jpeg"):
        img.save(path, format="JPEG", quality=85)
        assert Image.open(path).format == "JPEG", f"Expected JPEG, got {Image.open(path).format}"
    elif ext == ".png":
        img.save(path, format="PNG")
        assert Image.open(path).format == "PNG", f"Expected PNG, got {Image.open(path).format}"
    elif ext == ".webp":
        # Pillow 12.0.0 on this system has no WebP encoder.
        # Write PNG bytes as a fallback and document the limitation.
        img.save(path, format="PNG")
    else:
        img.save(path, format="PNG")


def create_test_png_with_metadata(
    path: Path,
    *,
    prompt: str = "",
    negative_prompt: str = "",
    model: str = "",
    sampler: str = "",
    seed: str = "",
    steps: int | None = None,
    cfg_scale: float | None = None,
    size: tuple[int, int] = (512, 512),
    extra_params: str = "",
) -> None:
    """Create a test PNG with A1111-style parameters embedded in a tEXt chunk."""
    parts = [prompt]
    if negative_prompt:
        parts.append(f"Negative prompt: {negative_prompt}")
    params = []
    if steps is not None:
        params.append(f"Steps: {steps}")
    if sampler:
        params.append(f"Sampler: {sampler}")
    if cfg_scale is not None:
        params.append(f"CFG scale: {cfg_scale}")
    if seed:
        params.append(f"Seed: {seed}")
    if model:
        params.append(f"Model: {model}")
    params.append(f"Size: {size[0]}x{size[1]}")
    if extra_params:
        params.append(extra_params)
    parts.append(", ".join(params))
    parameters_text = "\n".join(parts)

    pnginfo = PngInfo()
    pnginfo.add_text("parameters", parameters_text)

    create_test_png(path, size=size, pnginfo=pnginfo)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_gallery_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temporary PATH_SAFETY_ROOT that tests can freely populate and clean up."""
    root = tmp_path / "gallery_root"
    root.mkdir()

    monkeypatch.setenv("PATH_SAFETY_ROOT", str(root))
    import backend.config as config_module
    import backend.metadata_store as ms_module
    import backend.paths as paths_module

    resolved_root = root.resolve()
    monkeypatch.setattr(config_module, "PATH_SAFETY_ROOT", resolved_root)
    monkeypatch.setattr(paths_module, "PATH_SAFETY_ROOT", resolved_root)
    monkeypatch.setattr(ms_module, "PATH_SAFETY_ROOT", resolved_root)

    return root


@pytest.fixture
def isolated_metadata_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temporary GALLERY_METADATA_DB, isolated from any real cache."""
    db_path = tmp_path / "test_metadata.db"
    monkeypatch.setenv("GALLERY_METADATA_DB", str(db_path))

    import backend.config as cfg
    import backend.metadata_store as ms
    from backend.scan_worker import stop as stop_scan_worker

    stop_scan_worker()

    monkeypatch.setattr(ms, "GALLERY_METADATA_DB", db_path)
    monkeypatch.setattr(cfg, "GALLERY_METADATA_DB", db_path)
    # Force re-initialization for every test
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED", False)
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED_PATH", None)

    # Initialize the isolated schema deterministically at fixture time so
    # tests do not depend on order-dependent first-use initialisation.
    ms.initialize_database()

    return db_path


@pytest.fixture
def isolated_thumbnail_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temporary thumbnail cache directory."""
    cache_dir = tmp_path / "thumbnail_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GALLERY_THUMBNAIL_CACHE_DIR", str(cache_dir))

    import backend.config as config_module
    import backend.thumbnails as tn

    monkeypatch.setattr(config_module, "THUMBNAIL_CACHE_DIR", cache_dir)
    # Re-create disk cache and file dir under the isolated path
    from diskcache import Cache

    isolated_cache = Cache(str(cache_dir), size_limit=2 * 1024 * 1024 * 1024)
    isolated_file_dir = cache_dir / "files"
    isolated_file_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tn, "_thumbnail_disk_cache", isolated_cache)
    monkeypatch.setattr(tn, "_thumbnail_file_dir", isolated_file_dir)

    return cache_dir


@pytest.fixture
def disable_background_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable indexer, watcher, refresh, and warm listing for deterministic tests."""
    monkeypatch.setattr("backend.indexer.METADATA_INDEXER_ENABLED", False)
    monkeypatch.setattr("backend.config.METADATA_INDEXER_ENABLED", False)
    monkeypatch.setattr("backend.config.ENABLE_WARM_INDEXED_LISTING", False)
    monkeypatch.setattr("backend.config.ENABLE_SCHEDULED_REFRESH", False)
    monkeypatch.setattr("backend.config.ENABLE_FILE_WATCHER", False)
    monkeypatch.setattr("backend.app.GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED", False)
    monkeypatch.setattr("backend.app.GALLERY_SEARCH_INDEXER_ENABLED", False)

    # Suppress startup phase3 tasks
    def _noop(*args, **kwargs):  # noqa: ANN002, ANN003
        pass

    monkeypatch.setattr("backend.refresh.start_refresh", _noop)
    monkeypatch.setattr("backend.watcher.start_watcher", _noop)
    monkeypatch.setattr("backend.watcher.reconcile_watcher", _noop)
    monkeypatch.setattr("backend.app._start_refresh", _noop)
    monkeypatch.setattr("backend.app._start_watcher", _noop)
    monkeypatch.setattr("backend.scan_worker.start", _noop)
    monkeypatch.setattr("backend.scan_worker.queue_startup_scans", lambda: [])


@pytest.fixture
def isolated_app(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    isolated_thumbnail_cache: Path,
    disable_background_services: None,
):
    """Build a fresh FastAPI TestClient with all paths isolated."""
    from fastapi.testclient import TestClient

    from backend.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def temp_gallery(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    isolated_thumbnail_cache: Path,
    disable_background_services: None,
) -> Path:
    """Create a structured temporary gallery with test image files.

    Layout:
        album_a/001.png
        album_a/002.jpg
        album_a/010.png
        album_a/note.txt
        album_a/.hidden.png
        album_b/cover.webp
    """
    root = isolated_gallery_root

    album_a = root / "album_a"
    album_a.mkdir()
    album_b = root / "album_b"
    album_b.mkdir()

    create_test_png(album_a / "001.png", size=(800, 600))
    create_test_jpeg(album_a / "002.jpg", size=(1200, 900))
    create_test_png(album_a / "010.png", size=(640, 480))
    (album_a / "note.txt").write_text("not an image")
    (album_a / ".hidden.png").write_bytes(b"hidden")

    # WebP encoder not available in Pillow 12.0.0; PNG bytes as fallback
    create_test_png(album_b / "cover.webp", size=(1920, 1080))

    from backend.metadata_store import create_library, index_directory_tree

    create_library([root], name="Test gallery")
    index_directory_tree(root)

    return root


@pytest.fixture
def temp_gallery_with_metadata(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    isolated_thumbnail_cache: Path,
    disable_background_services: None,
) -> Path:
    """Create a gallery with PNGs that have embedded AI metadata for search/facets testing."""
    root = isolated_gallery_root

    album = root / "mika_album"
    album.mkdir()

    # Image with "mika" in prompt, seed=12345
    create_test_png_with_metadata(
        album / "mika_portrait.png",
        prompt="masterpiece, 1girl, mika, blue eyes, rain",
        negative_prompt="low quality, blurry",
        model="ponyDiffusionV6XL",
        sampler="Euler a",
        seed="12345",
        steps=30,
        cfg_scale=7.0,
        size=(1024, 1536),
        extra_params="Scheduler: karras",
    )

    # Another image with different model
    create_test_png_with_metadata(
        album / "landscape.png",
        prompt="landscape, mountain, snow",
        negative_prompt="watermark",
        model="SDXL",
        sampler="DPM++ 2M",
        seed="99999",
        steps=25,
        cfg_scale=7.5,
        size=(1536, 1024),
    )

    from backend.metadata_store import create_library, index_directory_tree

    create_library([root], name="Metadata gallery")
    index_directory_tree(root)

    return root
