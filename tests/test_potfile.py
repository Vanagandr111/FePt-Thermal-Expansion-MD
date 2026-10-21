"""potfile: upload sanitizing/folder choice/streamed save (TDD)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'gui'))

import potfile  # noqa: E402


def test_safe_name_strips_traversal():
    assert potfile.safe_name('../../../evil.model') == 'evil.model'
    assert potfile.safe_name('C:\\Users\\x\\a.model') == 'a.model'
    assert potfile.safe_name('..\\..\\b.eam.alloy') == 'b.eam.alloy'


def test_safe_name_rejects_bad():
    assert potfile.safe_name('') is None
    assert potfile.safe_name(None) is None
    assert potfile.safe_name('.hidden') is None
    assert potfile.safe_name('...') is None
    assert potfile.safe_name('   ') is None


def test_safe_name_strips_reserved():
    assert potfile.safe_name('mo:del?.model') == 'model.model'


def test_target_dir_by_extension():
    g, c = '/gpu', '/cpu'
    assert potfile.target_dir('mace.model', g, c) == g
    assert potfile.target_dir('MACE.MPT.MODEL', g, c) == g
    assert potfile.target_dir('model.pt', g, c) == g
    assert potfile.target_dir('Zhou04.eam.alloy', g, c) == c
    assert potfile.target_dir('PtFe.meam', g, c) == c
    assert potfile.target_dir('Fe_mm.eam.fs', g, c) == c
    assert potfile.target_dir('notes.txt', g, c) is None


def test_save_upload_happy_path(tmp_path):
    gpu, cpu = str(tmp_path / 'gpu'), str(tmp_path / 'cpu')
    ok, dst = potfile.save_upload(gpu, cpu, 'x.model',
                                  [b'abc', b'', b'def'])
    assert ok is True
    assert os.path.basename(dst) == 'x.model'
    assert os.path.dirname(dst) == gpu
    with open(dst, 'rb') as f:
        assert f.read() == b'abcdef'
    # no leftover .part file
    assert not os.path.exists(dst + '.part')


def test_save_upload_cpu_folder(tmp_path):
    gpu, cpu = str(tmp_path / 'gpu'), str(tmp_path / 'cpu')
    ok, dst = potfile.save_upload(gpu, cpu, 'PtFe.meam', [b'pair'])
    assert ok is True
    assert os.path.dirname(dst) == cpu


def test_save_upload_rejects(tmp_path):
    gpu, cpu = str(tmp_path / 'gpu'), str(tmp_path / 'cpu')
    ok, err = potfile.save_upload(gpu, cpu, 'evil.exe', [b'x'])
    assert ok is False and 'extension' in err
    ok, err = potfile.save_upload(gpu, cpu, '', [b'x'])
    assert ok is False
    ok, err = potfile.save_upload(gpu, cpu, 'empty.model', [])
    assert ok is False and 'empty' in err
    # no file was written (the folder itself may exist)
    assert not os.path.exists(os.path.join(gpu, 'empty.model'))
    assert not os.path.exists(os.path.join(gpu, 'empty.model.part'))


def test_save_upload_too_large(tmp_path):
    gpu, cpu = str(tmp_path / 'gpu'), str(tmp_path / 'cpu')
    ok, err = potfile.save_upload(gpu, cpu, 'big.model', [b'x' * 10],
                                  max_bytes=5)
    assert ok is False and 'large' in err
    assert not os.path.exists(os.path.join(gpu, 'big.model'))
    assert not os.path.exists(os.path.join(gpu, 'big.model.part'))
