#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build companion source/notice assets and recheck the immutable runtime.

No binary or installer is executed. This is packaging evidence, not MSI testing
or public publication. The user needs only the MSI to run the application.
"""
from pathlib import Path
import argparse
import importlib.util
import hashlib
import json
import tarfile
import zipfile

_spec = importlib.util.spec_from_file_location('cadence_retained2008_packaging_data', Path(__file__).with_name('prepare_retained_package.py'))
_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_data)
CI, EXE, TREE, ORIGINAL, ROOT = _data.CI, _data.EXE, _data.TREE, _data.ORIGINAL, _data.ROOT
inventory, plain, read_json, require, sha, source_identity = _data.inventory, _data.plain, _data.read_json, _data.require, _data.sha, _data.source_identity

BASE = 'CadenceStudio-4.7.6-cadence.2008'


def new_zip(destination, files):
    require(not destination.exists(), 'New companion archive required')
    seen = set()
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for name, path in sorted(files):
            require(name not in seen and not name.startswith('/') and '..' not in Path(name).parts,
                    'Duplicate/unsafe archive member')
            seen.add(name); archive.write(plain(path), name)
    with zipfile.ZipFile(destination) as archive:
        require(archive.testzip() is None and len(archive.infolist()) == len(seen), 'Companion ZIP CRC/member verification failed')


def main():
    parser = argparse.ArgumentParser()
    for name in ('validated', 'stage', 'application-source', 'corresponding-sources', 'recipe',
                 'source-delta', 'delivery', 'qualification', 'bindings', 'source-profile'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    validated = read_json(args.validated)
    require(validated.get('source_ci_commit') == CI and validated.get('source_tree') == TREE
            and validated.get('executable_sha256') == EXE and validated.get('application_recompiled') is False,
            'Actual successful immutable packaging preflight required')
    require(sha(args.bindings) == validated['bindings_sha256'] and sha(args.qualification) == validated['qualification_sha256'],
            'Actual package/qualification bindings changed')
    source_identity(args.application_source)
    require(inventory(args.stage) == validated['stage_files'], 'Runtime changed during MSI packaging')
    require(inventory(args.corresponding_sources) == validated['component_files'], 'Component sources changed during packaging')
    delivery = plain(args.delivery)
    msi, source = delivery / (BASE + '-x86_64.msi'), delivery / (BASE + '-source.tar.gz')
    require(msi.is_file() and msi.stat().st_size > 10 * 1024**2 and source.is_file(), 'Actual nonempty MSI and source archive required')
    with tarfile.open(source, 'r:gz') as archive:
        require(archive.pax_headers.get('comment') == CI, 'The source tar must come from git archive of original CI95')
        names = set(archive.getnames())
        require({'CMakeLists.txt', 'LICENSE.txt', 'version.cmake', 'scripts/windows/Build.ps1'}.issubset(names),
                'Application source archive lacks required build/license files')
    components = [(name, args.corresponding_sources / name) for name in validated['component_files']]
    zlib_companions = {}
    for name in ('Cadence-zlib-1.3.2-corresponding-source.zip', 'zlib-source-profile.lock.json'):
        row = validated['input_files'][name]
        path = plain(row['path'])
        require(sha(path) == row['sha256'] and path.stat().st_size == row['bytes'], 'Original zlib source companion changed')
        components.append((name, path))
        zlib_companions[name] = {'bytes': row['bytes'], 'sha256': row['sha256']}
    profile = read_json(validated['input_files']['zlib-source-profile.lock.json']['path'])
    require(profile.get('component') == 'zlib' and profile.get('version') == '1.3.2'
            and profile.get('ci', {}).get('run_id') == 43101767743
            and profile.get('ci', {}).get('artifact_id') == 13891238030, 'Exact original zlib source profile required')
    supplement = args.validated.parent / 'zlib-source-supplement.MEASURED.json'
    require(not supplement.exists(), 'New derived zlib companion receipt required')
    supplement.write_bytes((json.dumps({'schema_version': 1,
        'scope': 'NEW derived packaging measurement; not an original stage or component-producer metadata file',
        'component': 'zlib', 'version': '1.3.2', 'producer_run_id': profile['ci']['run_id'],
        'producer_artifact_id': profile['ci']['artifact_id'], 'source_commit': profile['source_commit'],
        'upstream_source_archive_sha256': profile['source_archive_sha256'],
        'original_stage_companions': zlib_companions,
        'archive_includes': 'Original complete prepared zlib package copied byte for byte from authenticated stage; no component rebuilt',
        'application_recompiled': False}, indent=2) + '\n').encode())
    components.append((supplement.name, supplement))
    zlib_companions[supplement.name] = {'bytes': supplement.stat().st_size, 'sha256': sha(supplement), 'derived_measurement': True}
    new_zip(delivery / (BASE + '-component-sources.zip'), components)
    qualification = read_json(args.qualification)
    notice_report = read_json(validated['qualification_files']['stage_notices']['path'])
    notices = [(row['stage_path'], args.stage / row['stage_path']) for row in notice_report['notices']]
    new_zip(delivery / (BASE + '-notices.zip'), notices)
    recipe_root = plain(args.recipe)
    recipe_rows = inventory(recipe_root)
    require(sum(row['bytes'] for row in recipe_rows.values()) <= 64 * 1024**2,
            'Select only the original build recipe; runtime/dependency archives do not belong in it')
    forbidden = {'.git', '.aws', '.ssh', '.codex', '.agents', '.env', 'node_modules', '__pycache__'}
    require(not any(set(Path(name).parts) & forbidden for name in recipe_rows), 'Unrelated private/development directory in selected recipe')
    recipe = [('original-selected-driver/' + name, recipe_root / name) for name in recipe_rows]
    # Only packaging source and the pinned MSI test helper, never checks/binaries.
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if not path.is_file() or set(relative.parts) & {'checks', '__pycache__'}:
            continue
        if path.suffix.lower() in {'.ps1', '.psm1', '.py', '.cmake', '.json', '.md', '.txt', '.yml', '.yaml'} or path.name == '.gitattributes':
            recipe.append(('retained-packaging/' + relative.as_posix(), path))
    recipe.extend([('original-profile/source.json', args.source_profile),
                   ('original-profile/package-bindings.json', args.bindings),
                   ('original-profile/qualification.json', args.qualification),
                   ('original-profile/from-upstream.patch', args.source_delta),
                   ('original-profile/validated-inputs.json', args.validated)])
    for name, row in qualification['gates'].items():
        path = plain(validated['qualification_files'][name]['path'])
        require(sha(path) == row['sha256'] and path.stat().st_size == row['bytes'], 'Actual gate report changed during bundling')
        recipe.append(('qualification/' + name + '/' + path.name, path))
    for name, row in validated.get('input_files', {}).items():
        require(sha(row['path']) == row['sha256'], 'Original provenance record changed during bundling')
        recipe.append(('original-evidence/' + name, Path(row['path'])))
    new_zip(delivery / (BASE + '-build-recipe.zip'), recipe)
    guide = delivery / ('LIRE-MOI-' + BASE + '-FR.txt')
    require(not guide.exists(), 'New French guide required')
    guide.write_text('''Cadence Studio — Windows 64 bits — préversion 4.7.6.2008

Pour écrire, modifier et écouter des partitions hors ligne, sans abonnement.
Téléchargez puis ouvrez CadenceStudio-4.7.6-cadence.2008-x86_64.msi.
Suivez l'assistant et lancez Cadence Studio. Aucun compilateur, SDK, compte ou
installation Qt séparée n'est nécessaire. Commencez avec des copies de fichiers.

Les banques de base sont incluses. Les collections supplémentaires sont
facultatives et ont leurs propres notices. Les fichiers sources et recettes
sont fournis séparément pour les développeurs et ne sont pas à installer.

Cette préversion réutilise exactement le binaire déjà compilé de Cadence2008.
Voir les rapports joints pour les essais réellement effectués. La création de
ce paquet ne prouve pas encore l'installation, une écoute ou Windows10/11 client.
L'installateur est non signé. SHA256SUMS.txt identifie les fichiers livrés ; ce
fichier n'est pas une signature Windows. Aucune URL publique n'est inventée.

Cadence est dérivé de MuseScore Studio4.7.6 sous GPLv3. Les licences du code,
des polices, des sons et des composants figurent dans l'application et dans
l'archive de notices. Les sources exactes de l'application, les sources des
composants et la recette sont les archives séparées portant la même version.
''', encoding='utf-8')
    source_identity(args.application_source)
    require(inventory(args.stage) == validated['stage_files'] and inventory(args.corresponding_sources) == validated['component_files'],
            'Immutable runtime/component inputs changed during delivery bundling')
    rows = []
    for path in sorted(delivery.iterdir()):
        if path.is_file() and path.name != 'SHA256SUMS.txt':
            rows.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path)})
    require(len(rows) == 6, 'Exactly six delivery assets plus their checksum file are required')
    (delivery / 'SHA256SUMS.txt').write_text(''.join(row['sha256'] + '  ' + row['name'] + '\n' for row in rows), encoding='ascii')
    result = {'schema_version': 1, 'status': 'packaged-sources-and-notices-verified; MSI-test-still-required',
              'source_original_commit': ORIGINAL, 'source_ci_commit': CI, 'source_tree': TREE,
              'executable_sha256': EXE, 'stage_unchanged': True, 'component_sources_unchanged': True,
              'source_archive_CI_comment_verified': True, 'assets': rows,
              'component_source_original_zlib_companions': zlib_companions,
              'installer_executed': False, 'application_executed': False, 'publicly_published': False}
    (args.validated.parent / 'delivery-bundle-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'stage_unchanged', 'component_sources_unchanged', 'installer_executed', 'publicly_published')}))


if __name__ == '__main__':
    main()
