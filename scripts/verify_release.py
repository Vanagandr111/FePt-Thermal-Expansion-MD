import zipfile, os, sys
from collections import Counter

path = sys.argv[1]
z = zipfile.ZipFile(path, 'r')
names = z.namelist()
print('  File: {}'.format(path))
print('  Size: {:.1f} MB'.format(os.path.getsize(path) / 1024 / 1024))
print('  Files: {}'.format(len(names)))

dirs = Counter()
for n in names:
    if '/' in n:
        d = n.split('/')[0]
        dirs[d] += 1
    else:
        dirs['(root)'] += 1

print()
print('  Contents:')
for d, c in sorted(dirs.items()):
    print('    {}/  \u2014 {} files'.format(d, c))

critical = ['run.bat', 'bootstrap.bat', 'scripts/run_mode.py',
            'scripts/lmp_helper.py', 'scripts/seed_manager.py',
            'bin/lmp.exe', 'scripts/gen_structure.py']
missing = [f for f in critical if f not in names]
print()
if missing:
    print('  WARNING: Missing critical files: {}'.format(missing))
else:
    print('  All critical files present!')
print()
print('  Archive verified: {}'.format(path))
z.close()
