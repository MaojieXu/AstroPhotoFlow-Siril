import json

import pytest
from adapter import analysis
from adapter import siril as adapter

from .adapter_test_helpers import build


def test_histogram_aggregation_preserves_counts_and_rejects_truncated_bins(tmp_path):
    path = tmp_path / 'histogram.dat'
    path.write_text(''.join(f'{index} {2 if index == 0 else 3 if index == 127 else 0}\n' for index in range(65536)), encoding='utf-8')
    result = analysis.parse_histogram(path)
    assert result.kind == 'series' and len(result.rows) == 512
    assert result.rows[0][1] == 5 and sum(row[1] for row in result.rows) == 5
    path.write_text('0 5\n', encoding='utf-8')
    with pytest.raises(ValueError, match='incomplete'):
        analysis.parse_histogram(path)


def test_bad_pixel_table_retains_first_record_and_zero_coordinates(tmp_path):
    path = tmp_path / 'pixels.lst'; path.write_text('P 0 0 H\nP 1 2 C\n', encoding='utf-8')
    result = analysis.parse_table(path, 'find_hot')
    assert result.rows == [['P', 0, 0, 'H'], ['P', 1, 2, 'C']]
    assert result.values['row_count'] == 2


def test_catalogue_identifiers_keep_all_digits_in_web_analysis(tmp_path):
    path = tmp_path / 'catalogue.csv'
    path.write_text('source_id,flux,flag\n9007199254740993,0.5,0\n-9007199254740993,1.25,1\n', encoding='utf-8')
    result = analysis.parse_table(path, 'conesearch')
    assert result.rows == [['9007199254740993', .5, 0], ['-9007199254740993', 1.25, 1]]


def test_getref_ignores_unrelated_supporting_star_tables(tmp_path):
    plan = build(tmp_path, 'getref')
    folder = tmp_path / 'work/sequence'
    (folder / 'input_.seq').write_text("S 'input_' 1 1 1 5 -1 6 0 0 0\nL 1\nI 1 1\n", encoding='utf-8')
    (folder / 'input_00001.fit').write_bytes(b'plan parser fixture')
    (folder / 'old-stars.lst').write_text('X Y\n99 99\n', encoding='utf-8')
    log = tmp_path / 'work/process.log'
    log.write_text("log: Running command: getref\nlog: Image 0: 'input_00001.fit'\n", encoding='utf-8')
    adapter.parse_result('getref', tmp_path / 'work', plan, log)
    result = json.loads((folder / 'analysis.json').read_text(encoding='utf-8'))
    assert result[0]['kind'] == 'metrics'
    assert result[0]['values']['zero_based_reference_index'] == 0


def test_sequence_statistics_tsv_preserves_columns_zero_and_unavailable(tmp_path):
    path = tmp_path/'statistics.csv'
    path.write_text('image\tchannel\tmean\tnoise\n1\t0\t0.25\tnan\n', encoding='utf-8')
    result = analysis.parse_table(path, 'seqstat')
    assert result.columns == ['image', 'channel', 'mean', 'noise']
    assert result.rows == [[1, 0, 0.25, None]]
