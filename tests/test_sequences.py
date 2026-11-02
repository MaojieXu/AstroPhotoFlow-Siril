
import pytest
from adapter import sequences
from adapter import siril as adapter

from .adapter_test_helpers import build, defaults, script


def test_single_static_frame_gets_an_explicit_one_member_sequence(tmp_path):
    source = tmp_path / 'single.fit'
    source.write_bytes(b'untouched source')
    folder = tmp_path / 'sequence'
    commands = []
    base = sequences.stage_sequence(commands, [source], [], folder)
    descriptor = sequences.read_sequence_descriptor(folder / (base + '.seq'))
    assert descriptor.frames == descriptor.selected == 1
    assert descriptor.members == [(1, 1)]
    assert len([command for command in commands if command.startswith('load ')]) == 1
    assert commands[-1] == 'getref "input_"'
    assert source.read_bytes() == b'untouched source'


def test_single_frame_result_is_collected_without_siril_directory_discovery(tmp_path):
    source = tmp_path / 'single.fit'
    source.write_bytes(b'untouched source')
    work = tmp_path / 'work'
    work.mkdir()
    plan = adapter.build_plan('seqsubsky', {'image': [source]}, defaults('seqsubsky'), work)
    script = (work / 'operation.ssf').read_text(encoding='utf-8')
    assert 'seqsubsky "input_"' in script
    assert 'getref "result_input_"' not in script
    sequence = work / 'sequence'
    (sequence / 'result_input_00001.fit').write_bytes(b'produced frame')
    (sequence / 'result_input_.seq').unlink(missing_ok=True)
    log = work / 'siril.log'
    log.write_text('Sequence processing succeeded.\nScript execution finished successfully.\n', encoding='utf-8')
    adapter.parse_result('seqsubsky', work, plan, log)
    output = sequences.read_sequence_descriptor(sequence / 'result_input_.seq')
    assert output.members == [(1, 1)]
    assert output.frames == 1
    assert source.read_bytes() == b'untouched source'


def test_sequence_metadata_is_copied_and_rebound_without_writable_original_links(tmp_path):
    prior = tmp_path / 'prior'; prior.mkdir()
    original = prior / 'input_00001.fit'; original.write_bytes(b'protected science')
    descriptor = prior / 'input_.seq'
    descriptor.write_text(f"S '{(prior / 'input_').as_posix()}' 1 1 1 5 -1 6 0 0 0\nL 1\nI 1 1\n", encoding='utf-8')
    build(tmp_path, 'sequpdate_key', sources={'image': [original]},
          values={'key': 'TESTKEY', 'value': '1'}, supporting_sources={'image': [descriptor]})
    local = tmp_path / 'work/sequence/input_00001.fit'
    local.write_bytes(b'updated FITS header')
    assert original.read_bytes() == b'protected science'
    assert "S 'input_'" in (tmp_path / 'work/sequence/input_.seq').read_text(encoding='utf-8')
    assert str(prior) not in (tmp_path / 'work/sequence/input_.seq').read_text(encoding='utf-8')


def test_missing_selected_sequence_frame_is_not_complete_success(tmp_path):
    plan = build(tmp_path, 'seqcrop')
    folder = tmp_path / 'work/sequence'
    (folder / 'result_input_.seq').write_text("S 'result_input_' 1 2 2 5 -1 6 0 0 0\nL 1\nI 1 1\nI 2 1\n", encoding='utf-8')
    (folder / 'result_input_00001.fit').write_bytes(b'one frame')
    log = tmp_path / 'work/process.log'; log.write_text('log: Script execution finished successfully.\n')
    with pytest.raises(ValueError, match='selected sequence output frame is missing'):
        adapter.parse_result('seqcrop', tmp_path / 'work', plan, log)


def test_packed_fits_sequence_is_copied_without_loading_only_its_first_frame(tmp_path):
    source = tmp_path / 'packed.fit'; source.write_bytes(b'complete multi-frame container')
    plan = build(tmp_path, 'seqstat', sources={'image': [source]}, source_metadata={'image': [
        {'reference_index': 0, 'selection': {'kind': 'whole_file'},
         'scientific_metadata': {'format': 'fits', 'frame_count': 3, 'hdu_count': 3, 'selected_hdu': 0}}
    ]})
    assert (tmp_path / 'work/sequence/input.fit').read_bytes() == source.read_bytes()
    assert 'input_00001.fit' not in script(plan)
    assert 'getref "input"' in script(plan)


def test_single_compressed_result_descriptor_tracks_actual_frame(tmp_path):
    source = tmp_path / 'single.fit'
    source.write_bytes(b'original')
    work = tmp_path / 'work'
    work.mkdir()
    plan = adapter.build_plan('seqsubsky', {'image': [source]}, defaults('seqsubsky'), work)
    sequence = work / 'sequence'
    (sequence / 'result_input_00001.fit.fz').write_bytes(b'compressed result')
    descriptor = sequence / 'result_input_.seq'
    assert descriptor.is_file()
    log = work / 'siril.log'
    log.write_text('Sequence processing succeeded.\nScript execution finished successfully.\n', encoding='utf-8')
    adapter.parse_result('seqsubsky', work, plan, log)
    assert descriptor.read_text().splitlines()[0].split()[-2] == '1'
    assert sequences.read_sequence_descriptor(descriptor).members == [(1, 1)]
    assert source.read_bytes() == b'original'
