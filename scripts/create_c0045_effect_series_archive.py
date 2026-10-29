"""Create a deterministic archive for one retained C0045 effect series."""

from __future__ import annotations

import argparse
import gzip
import sys
import tarfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from runners.c0045_effect_series import SERIES_PATH, C0045EffectSeries, load_c0045_effect_series
from runners.c0045_series_run import verify_c0045_series_cell
from scripts.verify_c0045_effect_series_archive import verify_archive

STATIC_AUXILIARY_ROOTS = ("c0045-prospective", "c0045-control-series")


def _allowed_roots(series: C0045EffectSeries) -> tuple[str, ...]:
    return (series.receipt_root_name, *STATIC_AUXILIARY_ROOTS)


def _archive_name(
    path: Path, source_dir: Path, allowed_roots: tuple[str, ...]
) -> str:
    relative = path.relative_to(source_dir)
    name = PurePosixPath(*relative.parts).as_posix()
    if not name or name.split("/", 1)[0] not in allowed_roots:
        raise ValueError("C0045 evidence is outside the declared archive roots")
    if any(part.startswith("._") or part == ".DS_Store" for part in name.split("/")):
        raise ValueError("C0045 evidence contains macOS metadata")
    return name


def _regular_files(source_dir: Path, allowed_roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root_name in allowed_roots:
        root = source_dir / root_name
        if not root.exists():
            continue
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"C0045 archive root is not a directory: {root_name}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"C0045 evidence contains a symbolic link: {path}")
            if path.is_dir():
                continue
            if not path.is_file() or path.suffix != ".json":
                raise ValueError(f"C0045 evidence contains a non-JSON file: {path}")
            _archive_name(path, source_dir, allowed_roots)
            files.append(path)
    return files


def _tar_info(name: str, size: int, *, directory: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if directory:
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
    else:
        info.size = size
        info.mode = 0o644
    return info


def _verify_source_series(source_dir: Path, series_path: Path) -> C0045EffectSeries:
    series = load_c0045_effect_series(series_path)
    for cell_id in series.selected_cells:
        verify_c0045_series_cell(source_dir, cell_id, series_path)
    return series


def create_archive(
    source_dir: Path, output_path: Path, series_path: Path = SERIES_PATH
) -> None:
    """Validate the source receipts, then emit and replay a portable archive."""
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise ValueError("C0045 source directory is missing or linked")
    if output_path.exists():
        raise FileExistsError(output_path)
    series = _verify_source_series(source_dir, series_path)
    allowed_roots = _allowed_roots(series)
    files = _regular_files(source_dir, allowed_roots)
    if not any(
        _archive_name(path, source_dir, allowed_roots).startswith(
            f"{series.receipt_root_name}/"
        )
        for path in files
    ):
        raise ValueError("C0045 source directory has no series receipts")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as output, gzip.GzipFile(
        filename="", fileobj=output, mode="wb", mtime=0
    ) as compressed, tarfile.open(
        fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT
    ) as archive:
        for root_name in allowed_roots:
            if (source_dir / root_name).is_dir():
                archive.addfile(_tar_info(root_name, 0, directory=True))
        for path in files:
            name = _archive_name(path, source_dir, allowed_roots)
            with path.open("rb") as source:
                archive.addfile(_tar_info(name, path.stat().st_size), source)
    verify_archive(output_path, series_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--series-path", type=Path, default=SERIES_PATH)
    options = parser.parse_args()
    create_archive(options.source_dir, options.output, options.series_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
