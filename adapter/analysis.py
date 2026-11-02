from __future__ import annotations

import csv
import math
import re

from astrophotoflow.contracts.bundles import (
    AnalysisResult,
)


def parse_cell(value):
    stripped = value.strip()
    if not stripped or stripped.lower() in {'nan', '-nan', '+nan', 'inf', '+inf', '-inf', 'n/a'}:
        return None
    if re.fullmatch(r'[+-]?\d+', stripped):
        number = int(stripped)
        # Catalogue identifiers can exceed JavaScript's exact integer range.
        return number if abs(number) <= 2**53 - 1 else stripped
    try:
        number = float(stripped)
    except ValueError:
        return stripped
    if not math.isfinite(number):
        return None
    return number


def parse_table(path, command):
    rows, columns, count = [], [], 0
    with path.open('r', encoding='utf-8', errors='replace', newline='') as stream:
        content = (line for line in stream if line.strip() and not line.lstrip().startswith('#'))
        records = csv.reader(content, delimiter='\t' if command == 'seqstat' else ',') if path.suffix.lower() == '.csv' else (line.split() for line in content)
        for record in records:
            values = [parse_cell(value) for value in record]
            if not columns:
                if path.suffix.lower() == '.lst' and record[0] == 'P':
                    columns = ['record', 'x', 'y', 'pixel_type']
                elif any(isinstance(value, str) for value in values):
                    columns = [str(value) if value is not None else 'unnamed' for value in values]
                    continue
                else:
                    columns = ['column_' + str(index + 1) for index in range(len(values))]
            count += 1
            if len(rows) < 200:
                rows.append(values + [None] * max(0, len(columns) - len(values)))
    return AnalysisResult(kind='table', title=path.name, source='Siril 1.4.4 ' + command, columns=columns,
                          rows=rows, values={'row_count': count, 'source_file': path.name},
                          sample=f'First {len(rows)} of {count} rows; empty/nonfinite values remain unavailable. Full data is retained in the file output. Units not stated in column headers remain unavailable.')


def parse_histogram(path):
    bins = [0] * 512
    count = 0
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            parts = line.split()
            if len(parts) != 2:
                raise ValueError('Siril histogram contains an invalid row.')
            code, frequency = map(int, parts)
            if code != count or not 0 <= code < 65536 or frequency < 0:
                raise ValueError('Siril histogram has missing bins or an invalid count.')
            bins[code // 128] += frequency
            count += 1
    if count != 65536:
        raise ValueError('Siril histogram is incomplete.')
    return AnalysisResult(kind='series', title=path.stem, source='Siril 1.4.4 histo',
                          unit='Siril 16-bit scaled code / pixel count', columns=['intensity', 'count'],
                          rows=[[index * 128 + 63.5, frequency] for index, frequency in enumerate(bins)],
                          values={'source_bins': 65536, 'display_bins': 512, 'aggregation': 'sum', 'source_file': path.name},
                          sample='Full selected image/channel; each displayed bin sums 128 original bins. The raw 65,536-bin file is retained.')


def log_blocks(log, command):
    blocks = []
    for match in re.finditer(r'(?m)^log: Running command: ' + re.escape(command) + r'\r?\n', log):
        end = re.search(r'(?m)^log: Running command: ', log[match.end():])
        block = log[match.end():match.end() + end.start()] if end else log[match.end():]
        block = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', block)
        block = re.sub(r'(?m)^\d+: running command[^\n]*\n?', '', block)
        blocks.append(block.strip())
    return blocks


def parse_metrics(command, block):
    values, unit = {}, None
    if command == 'bg':
        for channel, code, normalised in re.findall(r'Background value \(channel: #(\d+)\): (\d+) \(([^)]+)\)', block):
            values['channel_' + channel] = parse_cell(normalised)
            values['channel_' + channel + '_16bit_code'] = int(code)
        unit = 'normalised intensity; separate 16-bit scaled codes'
    elif command == 'entropy':
        match = re.search(r'Entropy:\s*([+-]?[\d.eE]+)', block)
        if match:
            values['entropy'] = parse_cell(match[1])
        unit = 'Siril entropy, summed over channels'
    elif command == 'cdg':
        match = re.search(r'Center of gravity coordinates are \(([^,]+), ([^)]+)\)', block)
        if match:
            values = {'x': parse_cell(match[1]), 'y': parse_cell(match[2])}
        unit = 'pixel; Siril image coordinates'
    elif command == 'stat':
        for channel, rest in re.findall(r'(B&W|Red|Green|Blue) layer:\s*([^\n]+)', block):
            for name, number in re.findall(r'([\w()]+):\s*([+-]?(?:[\d.eE]+|nan|inf))', rest):
                values[channel + '.' + name] = parse_cell(number)
        unit = 'Siril 16-bit scaled intensity'
    elif command == 'bgnoise':
        for channel, code, normalised in re.findall(r'Background noise value \(channel: #(\d+)\): ([\d.eE+-]+) \(([^)]+)\)', block):
            values['channel_' + channel] = parse_cell(normalised)
            values['channel_' + channel + '_16bit_code'] = parse_cell(code)
        unit = 'normalised noise intensity; separate 16-bit scaled values'
    elif command == 'psf':
        for name, number, unit_value in re.findall(r'\b(x0|y0|FWHMx|FWHMy|r|B|A|m|SNR|RMSE)=([+-]?[\d.eE]+)(px|arcsec|deg|dB|\x22)?', block):
            values[name] = parse_cell(number)
            if unit_value:
                values[name + '_unit'] = unit_value
        angle = re.search(r'Angle:\s*([+-]?[\d.eE]+)deg', block)
        magnitude = re.search(r'm=([+-]?[\d.eE]+)±([+-]?[\d.eE]+)', block)
        reference = re.search(r'Magnitude \(([^)]+)\)', block)
        if angle:
            values['angle_degrees'] = parse_cell(angle[1])
        if magnitude:
            values['magnitude_uncertainty'] = parse_cell(magnitude[2])
        if reference:
            values['magnitude_reference'] = reference[1]
        if 'FWHMx' not in values or 'FWHMy' not in values:
            return AnalysisResult(kind='metrics', title='PSF fit unavailable', source='Siril 1.4.4 psf',
                                  values={'available': False}, text=block[:12000], sample='No PSF fit was reported for the selected star rectangle; no missing measurement is replaced with zero.')
        unit = 'Centroid px; FWHM units per value; angle deg; magnitude mag; SNR dB; intensity/RMSE in Siril native units'
    elif command == 'getref':
        match = re.search(r'Image (\d+)(?::\s*\x27([^\x27]+)\x27)?', block)
        if match:
            values = {'zero_based_reference_index': int(match[1]), 'filename': match[2]}
        unit = 'zero-based sequence index'
    if command in {'bg', 'entropy', 'cdg', 'stat', 'bgnoise', 'getref', 'psf'}:
        if not values:
            raise ValueError('Siril did not report a complete ' + command + ' result.')
        return AnalysisResult(kind='metrics', title=command, source='Siril 1.4.4 ' + command, unit=unit,
                              values=values, text=block[:12000], sample='Actual selected image/sequence; unavailable numeric values remain null.')
    if not block:
        raise ValueError('Siril did not report the requested analysis result: ' + command)
    return AnalysisResult(kind='text', title=command, source='Siril 1.4.4 ' + command, text=block[:12000],
                          values={'log_characters': len(block), 'display_characters': min(len(block), 12000), 'truncated': len(block) > 12000},
                          sample='Command output excerpt, at most 12,000 characters. The complete log is retained in the file output and invocation log.')
