"""Portable SQLite + media archives with checksums and a restore verification."""
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4
from contextlib import closing

from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_sqlite(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise CommandError('Baza yaxlitlik tekshiruvidan o‘tmadi.')
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise CommandError('Bazada buzilgan bog‘lanishlar mavjud.')


def create_backup(output_dir=None):
    config = settings.DATABASES['default']
    if config['ENGINE'] != 'django.db.backends.sqlite3':
        raise CommandError('Bu buyruq SQLite uchun mo‘ljallangan.')
    source = Path(config['NAME']).resolve()
    if not source.is_file():
        raise CommandError('Baza fayli topilmadi.')
    directory = Path(output_dir or Path(settings.BASE_DIR) / 'backups').resolve()
    media = Path(settings.MEDIA_ROOT).resolve()
    if directory == media or media in directory.parents:
        raise CommandError('Zaxira papkasi media papkasidan tashqarida bo‘lsin.')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'backup-{timezone.localtime():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.zip'
    partial = target.with_suffix('.zip.partial')
    try:
        with TemporaryDirectory(dir=directory, prefix='backup-work-') as work:
            database = Path(work) / 'db.sqlite3'
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
                with closing(sqlite3.connect(database)) as dst:
                    src.backup(dst)
            verify_sqlite(database)
            files = {'db.sqlite3': database}
            if media.is_dir():
                for path in media.rglob('*'):
                    if path.is_symlink():
                        raise CommandError('Media ichidagi symlinkni zaxiralashdan oldin tekshiring.')
                    if path.is_file():
                        files['media/' + path.relative_to(media).as_posix()] = path
            manifest = {'version': 1, 'created_at': timezone.now().isoformat(), 'files': {}}
            with zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, path in files.items():
                    digest = hashlib.sha256()
                    with path.open('rb') as src, archive.open(name, 'w') as dst:
                        for block in iter(lambda: src.read(1024 * 1024), b''):
                            digest.update(block)
                            dst.write(block)
                    manifest['files'][name] = digest.hexdigest()
                archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
            verify_backup(partial)
            partial.replace(target)
        return target, len(files) - 1
    finally:
        if partial.exists():
            partial.unlink()


def verify_backup(archive_path, destination=None):
    """Extract allowlisted entries into a new location, never over live data."""
    with TemporaryDirectory(prefix='crm-verify-') as temporary:
        root = Path(temporary)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise CommandError('Arxivda takroriy fayl nomlari mavjud.')
                manifest = json.loads(archive.read('manifest.json'))
                if not isinstance(manifest, dict):
                    raise CommandError('Zaxira manifesti noto‘g‘ri.')
                files = manifest.get('files')
                if manifest.get('version') != 1 or not isinstance(files, dict) or 'db.sqlite3' not in files:
                    raise CommandError('Zaxira manifesti noto‘g‘ri.')
                if set(names) != set(files) | {'manifest.json'}:
                    raise CommandError('Arxiv tarkibi manifestga mos emas.')
                for name in files:
                    path = PurePosixPath(name)
                    if ('\\' in name or ':' in name or path.is_absolute() or '..' in path.parts
                            or name != 'db.sqlite3' and not name.startswith('media/')):
                        raise CommandError('Arxivda ruxsat etilmagan fayl yo‘li bor.')
                for name, expected in files.items():
                    path = PurePosixPath(name)
                    output = root.joinpath(*path.parts)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as src, output.open('wb') as dst:
                        for block in iter(lambda: src.read(1024 * 1024), b''):
                            dst.write(block)
                    if checksum(output) != expected:
                        raise CommandError('Fayl nazorat summasi mos emas: ' + name)
            verify_sqlite(root / 'db.sqlite3')
            if destination is not None:
                import shutil
                destination = Path(destination).resolve()
                if destination.exists():
                    raise CommandError('Tiklash uchun mavjud bo‘lmagan yangi papkani tanlang.')
                shutil.copytree(root, destination)
            return len(files) - 1
        except (zipfile.BadZipFile, KeyError, ValueError, TypeError, OSError, sqlite3.Error) as exc:
            raise CommandError('Zaxirani tekshirib bo‘lmadi: ' + type(exc).__name__) from exc
