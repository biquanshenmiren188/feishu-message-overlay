"""Create an allowlisted source-only archive. No user state or dependencies."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path(__file__).resolve().parent.parent
roots = [root / name for name in ('src', 'tests', 'scripts', 'bridge', '.github')]
allowed = {'.cs', '.csproj', '.xaml', '.manifest', '.ps1', '.py', '.mjs', '.json', '.yml', '.md'}
excluded = {'bin', 'obj', 'node_modules', '.npm-cache', '__pycache__'}
files = [root / name for name in ('Directory.Build.props', '.gitignore', 'README.md', 'SOURCE-VALIDATION.md')]
for directory in roots:
    for file in directory.rglob('*'):
        relative = file.relative_to(root)
        if file.is_file() and "wpftmp" not in file.name and not excluded.intersection(relative.parts) and file.suffix in allowed:
            if any(word in file.name.lower() for word in ('secret', 'credential.dpapi', 'appearance.json')):
                raise RuntimeError('Unexpected sensitive file in source selection')
            files.append(file)
files = sorted(set(files), key=lambda p: p.relative_to(root).as_posix())
output = root / 'artifacts' / 'feishu-message-overlay-source.zip'
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for file in files:
        archive.write(file, file.relative_to(root).as_posix())
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None
    assert not any(excluded.intersection(Path(name).parts) for name in archive.namelist())
receipt = {'file': output.name, 'files': len(files), 'size': output.stat().st_size,
           'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
(root / 'artifacts' / 'source-archive-receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
print(json.dumps(receipt))
