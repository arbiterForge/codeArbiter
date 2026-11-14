"""Shared closed native manifest shape; declarations do not authenticate evidence.

Binary file/digest/magic and trusted qualification verification stay with their
owning consumers. A valid optional context record is a declaration, not a receipt.
"""
import json
import re

# BEGIN GENERATED MANIFEST CONTRACT
_CONTRACT_JSON = '{"binary_fields":["file","sha256","native_tested"],"context_fields":["source_commit","workflow","run_id","binary_sha256","observation_sha256","module_sha256","native_cases"],"contract":"codearbiter.native-manifest-contract/1","format":"codearbiter.artifact-release/0.1.0","native_cases":["TestContextBoundedRender","TestContextDocumentContract","TestContextMarkdownPreservation","TestContextMutationAdmission","TestContextRecoveryAndPaths","TestContextRepresentationBoundary"],"optional":["context_qualification"],"platforms":["linux/amd64","linux/arm64","darwin/amd64","darwin/arm64","windows/amd64","windows/arm64"],"protocol":"codearbiter.artifact-api/0.1.0","required":["format","version","protocol","schema_version","binaries"],"schema_version":"0.3.2","workflow":".github/workflows/ci.yml"}'
# END GENERATED MANIFEST CONTRACT
CONTRACT = json.loads(_CONTRACT_JSON)


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate native manifest key')
        out[key] = value
    return out


def parse_release_manifest(raw):
    if not isinstance(raw, (str, bytes)) or len(raw.encode('utf-8') if isinstance(raw, str) else raw) > 65536:
        raise ValueError('native manifest exceeds bounded input')
    return validate_release_manifest(json.loads(raw, object_pairs_hook=_pairs))


def validate_release_manifest(value):
    required = set(CONTRACT['required'])
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - set(CONTRACT['optional']):
        raise ValueError('unexpected native release manifest shape')
    if any(value[key] != CONTRACT[key] for key in ('format','protocol','schema_version')):
        raise ValueError('unsupported native release manifest identity')
    if not isinstance(value['version'], str) or not value['version'].strip():
        raise ValueError('native release version must be a nonempty string; not a supported artifact version')
    binaries = value['binaries']
    if not isinstance(binaries, dict) or not binaries or set(binaries) - set(CONTRACT['platforms']):
        raise ValueError('invalid native release platform map')
    for platform, entry in binaries.items():
        filename = 'ca-artifact-' + platform.replace('/','-') + ('.exe' if platform.startswith('windows/') else '')
        if (not isinstance(entry, dict) or set(entry) != set(CONTRACT['binary_fields'])
                or entry['file'] != filename or type(entry['native_tested']) is not bool
                or not isinstance(entry['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', entry['sha256']) is None):
            raise ValueError('invalid native release binary entry')
    if 'context_qualification' not in value:
        return value
    context = value['context_qualification']
    if not isinstance(context, dict) or set(context) - set(binaries):
        raise ValueError('invalid context qualification platform map')
    for platform, entry in context.items():
        if not isinstance(entry, dict) or set(entry) != set(CONTRACT['context_fields']):
            raise ValueError('invalid context qualification shape')
        if (not isinstance(entry['source_commit'], str) or re.fullmatch(r'[0-9a-f]{40}', entry['source_commit']) is None
                or entry['workflow'] != CONTRACT['workflow'] or not isinstance(entry['run_id'], str)
                or re.fullmatch(r'[1-9][0-9]*', entry['run_id']) is None
                or any(not isinstance(entry[key], str) or re.fullmatch(r'[0-9a-f]{64}', entry[key]) is None
                       for key in ('binary_sha256','observation_sha256','module_sha256'))
                or entry['binary_sha256'] != binaries[platform]['sha256']
                or binaries[platform]['native_tested'] is not True or entry['native_cases'] != CONTRACT['native_cases']):
            raise ValueError('invalid context qualification binding')
    return value
