"""Saving uploaded potential files into potentials/{gpu,cpu} (unit-tested).

The HTTP layer streams raw bytes in; this module owns name sanitizing,
folder choice by extension and the atomic (.part -> rename) write.
"""
import os

GPU_EXTS = ('.model', '.pt')
CPU_EXTS = ('.eam', '.alloy', '.fs', '.meam', '.setfl')


def safe_name(name):
    """Pure basename, no traversal, sane charset; None if unusable."""
    if not name or not isinstance(name, str):
        return None
    base = os.path.basename(name.replace('\\', '/')).strip()
    if not base or base.startswith('.'):
        return None
    for ch in '<>:"|?*':
        base = base.replace(ch, '')
    base = base.strip(' .')
    if not base:
        return None
    return base


def target_dir(name, gpu_dir, cpu_dir):
    """Folder for an upload by extension; None if unsupported."""
    low = (name or '').lower()
    if low.endswith(GPU_EXTS):
        return gpu_dir
    if low.endswith(CPU_EXTS):
        return cpu_dir
    return None


def save_upload(gpu_dir, cpu_dir, name, chunk_iter, max_bytes=2 << 30):
    """Stream chunk_iter into the right folder. Returns (ok, path|error)."""
    base = safe_name(name)
    if not base:
        return False, 'bad file name'
    dst_dir = target_dir(base, gpu_dir, cpu_dir)
    if dst_dir is None:
        return False, 'unsupported extension (want .model/.pt or EAM/MEAM)'
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, base)
    tmp = dst + '.part'
    total = 0
    try:
        with open(tmp, 'wb') as f:
            for chunk in chunk_iter:
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    return False, 'file too large (>{} bytes)'.format(
                        max_bytes)
                f.write(chunk)
        if total == 0:
            return False, 'empty file'
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return True, dst
