"""Persistence checks: real disk I/O; GitHub writes only against a fake API."""
import base64
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from workspace_store import WorkspaceStore, Conflict

FILES = {'main.cvc': 'void setup() {}\nvoid loop() {waitFrame();}\n',
         'data/image.bin': {'base64': base64.b64encode(bytes(range(256))).decode()},
         'logic/game.h': '#pragma once\n'}


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'game'; self.store = WorkspaceStore()
        self.project = self.store.create_local(str(self.path), FILES)

    def test_save_nested_and_binary_preserves_other_files(self):
        (self.path/'notes.txt').write_text('untouched')
        edited = copy.deepcopy(FILES); edited['logic/game.h'] += '// edited\n'
        result = self.store.save_local(self.project['id'], self.project['revision'], edited)
        self.assertEqual(result['files'], edited)
        self.assertEqual((self.path/'data/image.bin').read_bytes(), bytes(range(256)))
        self.assertEqual((self.path/'notes.txt').read_text(), 'untouched')
        self.assertNotEqual(result['revision'], self.project['revision'])

    def test_external_edit_and_second_tab_conflict(self):
        edited = dict(FILES, **{'main.cvc': '// from first tab'})
        self.store.save_local(self.project['id'], self.project['revision'], edited)
        with self.assertRaises(Conflict):
            self.store.save_local(self.project['id'], self.project['revision'], FILES)
        self.assertEqual((self.path/'main.cvc').read_text(), '// from first tab')

    def test_missing_file_conflicts_without_recreating_it(self):
        (self.path/'logic/game.h').unlink()
        with self.assertRaises(Conflict):
            self.store.save_local(self.project['id'], self.project['revision'], FILES)
        self.assertFalse((self.path/'logic/game.h').exists())

    def test_save_as_never_overwrites_and_traversal_rejected(self):
        with self.assertRaises(FileExistsError): self.store.create_local(str(self.path), FILES)
        with self.assertRaises(ValueError): self.store.save_local(self.project['id'], self.project['revision'], {**FILES, '../escape.h': ''})
        with self.assertRaises(ValueError): self.store.save_local(self.project['id'], self.project['revision'], {**FILES, '.git/config.h': ''})

    def test_symlink_write_rejected(self):
        outside = Path(self.tmp.name)/'outside.h'; outside.write_text('#pragma once\n')
        (self.path/'logic/game.h').unlink(); (self.path/'logic/game.h').symlink_to(outside)
        with self.assertRaises(ValueError):
            self.store.save_local(self.project['id'], self.project['revision'], FILES)
        self.assertEqual(outside.read_text(), '#pragma once\n')

    def test_hidden_metadata_excluded(self):
        (self.path/'.metadata').mkdir(); (self.path/'.metadata/extra.h').write_text('not a source')
        self.assertEqual(self.store.open_local(str(self.path))['files'], FILES)


class GithubTests(unittest.TestCase):
    def setUp(self):
        self.store=WorkspaceStore();self.calls=[];self.head='a'*40
        self.patch=patch('workspace_store.github_api', side_effect=self.api);self.patch.start();self.addCleanup(self.patch.stop)

    def api(self, endpoint, payload=None, method=None):
        self.calls.append((endpoint,payload,method))
        if endpoint=='repos/person/game': return {'default_branch':'main'}
        if '/ref/heads/' in endpoint: return {'object':{'sha':self.head}}
        if '/trees/' in endpoint:
            return {'tree':[{'path':'project/'+name,'type':'blob','mode':'100644','size':len(json.dumps(value)),'sha':str(i)} for i,(name,value) in enumerate(FILES.items())]}
        if '/blobs/' in endpoint:
            value=list(FILES.values())[int(endpoint.rsplit('/',1)[-1])]
            return {'content':base64.b64encode(value.encode()).decode() if isinstance(value,str) else value['base64']}
        if '/commits/' in endpoint: return {'tree':{'sha':'original-tree'}}
        if endpoint.endswith('/blobs'): return {'sha':'new-blob'}
        if endpoint.endswith('/trees'): return {'sha':'new-tree'}
        if endpoint.endswith('/commits'): return {'sha':'b'*40}
        if '/refs/heads/' in endpoint:
            self.assertFalse(payload['force']); self.assertEqual(method,'PATCH'); self.head=payload['sha'];return {}
        self.fail(endpoint)

    def test_open_and_atomic_commit_preserve_repository(self):
        project=self.store.open_github('person/game',folder='project')
        self.assertEqual(project['files'],FILES)
        edited={**FILES,'logic/game.h':'// changed'}
        result=self.store.commit_github(project['id'],project['revision'],edited,'Change game')
        tree=next(payload for url,payload,_ in self.calls if url.endswith('/trees'))
        self.assertEqual(tree['base_tree'],'original-tree')
        self.assertEqual([e['path'] for e in tree['tree']],['project/logic/game.h'])
        commit=next(payload for url,payload,_ in self.calls if url.endswith('/commits'))
        self.assertEqual(commit['parents'],['a'*40]);self.assertNotIn('author',commit)
        self.assertEqual(result['revision'],'b'*40)

    def test_remote_change_stops_before_writes(self):
        project=self.store.open_github('person/game',folder='project');self.head='c'*40
        with self.assertRaises(Conflict):
            self.store.commit_github(project['id'],project['revision'],{**FILES,'main.cvc':'// edit'},'Change')
        self.assertFalse(any(payload for _,payload,_ in self.calls))

    def test_invalid_repository_and_folder_never_reach_api(self):
        for args in [('https://evil.test/repo','',''),('person/game','','../private'),('person/game','--bad','')]:
            with self.assertRaises(ValueError): self.store.open_github(*args)
        self.assertFalse(self.calls)

    def test_push_race_is_not_forced_or_reported_as_success(self):
        project=self.store.open_github('person/game',folder='project')
        real_api=self.api
        def race(endpoint,payload=None,method=None):
            if '/refs/heads/' in endpoint:
                self.assertFalse(payload['force']);raise ValueError('Non-fast-forward')
            return real_api(endpoint,payload,method)
        with patch('workspace_store.github_api',side_effect=race):
            with self.assertRaises(ValueError): self.store.commit_github(project['id'],project['revision'],{**FILES,'main.cvc':'// edit'},'Change')
        self.assertEqual(self.store.workspaces[project['id']]['revision'],'a'*40)

if __name__=='__main__': unittest.main(verbosity=2)
