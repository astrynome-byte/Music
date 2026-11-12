# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic report guard tests on Linux; no Cadence process or PCM is used."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('corpus_comparison', HERE / 'compare_corpus_reports.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
checks = []
for fixture in ('piano', 'voice', 'guitar', 'percussion', 'ensemble'):
    for stage in sorted(module.STABLE):
        output = {'path': 'C:/synthetic/' + fixture + '/export.' + stage[7:],
                  'sha256': hashlib.sha256((fixture + stage).encode()).hexdigest()}
        if stage == 'export-wav':
            output['audio'] = {'passed': True}
        checks.append({'fixture': fixture, 'stage': stage, 'passed': True, 'outputs': [output]})
for number in range(22):
    checks.append({'fixture': 'ensemble', 'stage': 'synthetic-nonstable-' + str(number), 'passed': True})
valid = {'executable_sha256': module.EXE, 'version_exit_code': 0, 'checks': checks}
results = []


def check(name, edit, accepted=False):
    candidate = copy.deepcopy(valid)
    edit(candidate)
    with tempfile.TemporaryDirectory(prefix='cadence-icu-synthetic-') as directory:
        base, test = Path(directory) / 'baseline.json', Path(directory) / 'candidate.json'
        base.write_text(json.dumps(valid), encoding='utf-8')
        test.write_text(json.dumps(candidate), encoding='utf-8')
        try:
            result = module.compare_reports(base, test)
        except (ValueError, KeyError, TypeError, AttributeError):
            assert not accepted, name
        else:
            assert accepted and result['stable_hashes_identical'] == 35, name
        results.append({'case': name, 'passed': True})


check('57 checks and 35 identical exports accepted', lambda x: None, True)
check('56 checks refused', lambda x: x['checks'].pop())
check('extra check refused', lambda x: x['checks'].append(copy.deepcopy(x['checks'][0])))
check('failed check refused', lambda x: x['checks'][0].update(passed=False))
check('string PASS refused', lambda x: x['checks'][0].update(passed='true'))
check('numeric PASS refused', lambda x: x['checks'][0].update(passed=1))
check('wrong executable refused', lambda x: x.update(executable_sha256='0' * 64))
check('nonzero version exit refused', lambda x: x.update(version_exit_code=1))
check('boolean version exit refused', lambda x: x.update(version_exit_code=False))
check('changed stable hash refused', lambda x: x['checks'][0]['outputs'][0].update(sha256='0' * 64))
check('malformed stable hash refused', lambda x: x['checks'][0]['outputs'][0].update(sha256='G' * 64))
check('missing stable output refused', lambda x: x['checks'][0]['outputs'].clear())
check('duplicate stable identity refused', lambda x: x['checks'][0]['outputs'].append(copy.deepcopy(x['checks'][0]['outputs'][0])))
wav_index = next(i for i, row in enumerate(checks) if row['stage'] == 'export-wav')
check('failed WAV numeric gate refused', lambda x: x['checks'][wav_index]['outputs'][0]['audio'].update(passed=False))
check('string WAV gate refused', lambda x: x['checks'][wav_index]['outputs'][0]['audio'].update(passed='true'))
check('missing WAV numeric gate refused', lambda x: x['checks'][wav_index]['outputs'][0].pop('audio'))
check('Windows output root may differ', lambda x: [o.update(path=o['path'].replace('C:/synthetic/', 'D:/copy/')) for c in x['checks'] for o in c.get('outputs', [])], True)
report = {'schema_version': 1, 'scope': 'Synthetic JSON reports only; no Windows, application or audio executed',
          'cases_passed': len(results), 'results': results}
(HERE / 'synthetic-comparison-results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
