"""User-owned workspaces. Local writes and GitHub commits use revision checks."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from urllib.parse import quote

from toolchain.project_source import read_project, validate_files, file_bytes, BINARY_SUFFIXES, LIMIT, project_path


class Conflict(ValueError):
    pass


def revision(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def project_files(files):
    validate_files(files)
    if 'main.cvc' not in files:
        raise ValueError('Il progetto deve contenere main.cvc.')
    if any(any(part.startswith('.') for part in Path(name).parts) for name in files):
        raise ValueError('I file nascosti non fanno parte del progetto.')
    return files


def github_api(endpoint, payload=None, method=None):
    command = ['gh', 'api', '--hostname', 'github.com', endpoint]
    if payload is not None:
        command += ['--method', method or 'POST', '--input', '-']
    try:
        result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                                capture_output=True, text=True, timeout=45,
                                env={**os.environ, 'GH_PROMPT_DISABLED': '1'})
    except FileNotFoundError as exc:
        raise ValueError('Installa GitHub CLI e collega il tuo account con gh auth login.') from exc
    if result.returncode:
        # Never return CLI diagnostics that might contain credentials or private responses.
        raise ValueError('GitHub non ha completato la richiesta. Controlla gh auth login, rete, permessi e protezione del branch.')
    return json.loads(result.stdout)


class WorkspaceStore:
    def __init__(self):
        self.workspaces = {}
        self.lock = threading.RLock()

    def register(self, descriptor, files, version):
        key = 'workspace-' + hashlib.sha256(json.dumps(descriptor, sort_keys=True).encode()).hexdigest()[:20]
        record = dict(descriptor=descriptor, files=files, revision=version)
        self.workspaces[key] = record
        return dict(id=key, label=descriptor.get('label', descriptor.get('path', '').split('/')[-1]),
                    files=files, revision=version, storage=descriptor)

    def open_local(self, path):
        if not isinstance(path, str) or not Path(path).expanduser().is_absolute():
            raise ValueError('Scegli una cartella o indica un percorso assoluto.')
        root = Path(path).expanduser().resolve(strict=True)
        files = project_files(read_project(root))
        return self.register(dict(kind='local', path=str(root), label=root.name), files, revision(files))

    def create_local(self, path, files):
        project_files(files)
        target = Path(path).expanduser()
        if not target.is_absolute() or target.name in ('', '.', '..'):
            raise ValueError('Indica il percorso assoluto di una nuova cartella.')
        # A new directory only: Save As never overwrites an existing project.
        target.mkdir(parents=False, exist_ok=False)
        try:
            for name, value in files.items():
                dest = target / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(file_bytes(value))
        except Exception:
            # Preserve partial data on I/O failure for recovery; never recursively delete.
            raise
        return self.open_local(str(target))

    def save_local(self, key, expected, files):
        project_files(files)
        record = self.workspaces[key]
        if record['descriptor']['kind'] != 'local':
            raise ValueError('Questo progetto richiede un commit GitHub.')
        root = Path(record['descriptor']['path'])
        if root.resolve() != root: raise ValueError('La cartella originale è stata sostituita da un link simbolico.')
        actual = read_project(root)
        if revision(actual) != expected:
            raise Conflict('La cartella è cambiata fuori da CVCC. La tua bozza è al sicuro: scarica una copia o riapri la versione su disco prima di salvare.')
        if set(actual) - set(files):
            raise ValueError('La rimozione dei file non è supportata da questo salvataggio.')
        staged = []
        try:
            for name, value in files.items():
                if name in actual and file_bytes(actual[name]) == file_bytes(value):
                    continue
                dest = root / name
                if not dest.resolve().is_relative_to(root) or any(p.is_symlink() for p in [dest, *dest.parents] if p != root and p.is_relative_to(root)):
                    raise ValueError('Salvataggio attraverso link simbolici non consentito.')
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=dest.parent, prefix='.cvcc-save-', delete=False) as tmp:
                    tmp.write(file_bytes(value)); tmp.flush(); os.fsync(tmp.fileno())
                    staged.append((Path(tmp.name), dest))
                if dest.exists(): os.chmod(tmp.name, dest.stat().st_mode & 0o777)
            # Detect edits made while preparing the transaction.
            if revision(read_project(root)) != expected:
                raise Conflict('La cartella è cambiata durante il salvataggio. Nessun file sostituito.')
            for tmp, dest in staged:
                os.replace(tmp, dest)
        finally:
            for tmp, _ in staged:
                tmp.unlink(missing_ok=True)
        return self.open_local(str(root))

    def github_descriptor(self, repo, branch='', folder=''):
        if not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repo):
            raise ValueError('Repository nel formato proprietario/nome.')
        if not isinstance(branch, str) or (branch and (not re.fullmatch(r'[A-Za-z0-9_./-]+', branch) or '..' in branch or branch.startswith('-'))):
            raise ValueError('Nome branch non valido.')
        if not isinstance(folder, str) or (folder and (not re.fullmatch(r'[A-Za-z0-9_ ./-]+', folder) or any(p in ('', '.', '..') or p.startswith('.') for p in folder.split('/')))):
            raise ValueError('La cartella deve essere relativa al repository.')
        if not branch: branch = github_api(f'repos/{repo}')['default_branch']
        return dict(kind='github', repo=repo, branch=branch, folder=folder,
                    label=repo.split('/')[-1] + (('/' + folder) if folder else ''),
                    path=f'{repo} · {branch}' + (f' · {folder}' if folder else ''))

    def open_github(self, repo, branch='', folder=''):
        descriptor = self.github_descriptor(repo, branch, folder)
        branch = descriptor['branch']
        base = f'repos/{repo}/git'
        head = github_api(f'{base}/ref/heads/{quote(branch, safe="")}')['object']['sha']
        tree = github_api(f'{base}/trees/{head}?recursive=1')
        if tree.get('truncated'): raise ValueError('Repository troppo grande: elenco GitHub incompleto.')
        prefix = folder + '/' if folder else ''
        files = {}; total = 0
        for item in tree['tree']:
            if not item['path'].startswith(prefix): continue
            name = item['path'][len(prefix):]
            if any(p.startswith('.') for p in name.split('/')) or not project_path(name): continue
            if item['type'] != 'blob' or item['mode'] not in ('100644', '100755'):
                raise ValueError('Link simbolici e submodule non supportati nei file del progetto.')
            total += item.get('size', 0)
            if total > LIMIT or len(files) >= 128: raise ValueError('Progetto troppo grande: scegli una sottocartella (massimo 128 file e 1 MiB).')
            blob = github_api(f'{base}/blobs/{item["sha"]}')
            data = base64.b64decode(blob['content'])
            files[name] = {'base64': base64.b64encode(data).decode()} if Path(name).suffix in BINARY_SUFFIXES else data.decode('utf-8')
        project_files(files)
        return self.register(descriptor, files, head)

    def commit_github(self, key, expected, files, message):
        project_files(files)
        record = self.workspaces[key]; desc = record['descriptor']
        if desc['kind'] != 'github': raise ValueError('Apri un progetto GitHub per inviare un commit.')
        if not isinstance(message, str) or not message.strip() or len(message) > 1000:
            raise ValueError('Scrivi un messaggio di commit (massimo 1000 caratteri).')
        if expected != record['revision']: raise Conflict('La base della bozza è cambiata. Riapri il progetto prima di inviare.')
        if set(record['files']) - set(files): raise ValueError('La rimozione dei file non è supportata.')
        base = f'repos/{desc["repo"]}/git'; ref = 'heads/' + quote(desc['branch'], safe='')
        head = github_api(f'{base}/ref/{ref}')['object']['sha']
        if head != expected:
            raise Conflict('Il branch è cambiato su GitHub. Nessun commit inviato. Conserva la bozza ed esamina la versione remota prima di riprovare.')
        changed = [name for name in files if name not in record['files'] or file_bytes(files[name]) != file_bytes(record['files'][name])]
        if not changed: raise ValueError('Nessuna modifica da inviare.')
        old_commit = github_api(f'{base}/commits/{head}')
        tree_entries = []
        for name in changed:
            blob = github_api(f'{base}/blobs', dict(content=base64.b64encode(file_bytes(files[name])).decode(), encoding='base64'))
            tree_entries.append(dict(path=(desc['folder']+'/' if desc['folder'] else '')+name, mode='100644', type='blob', sha=blob['sha']))
        tree = github_api(f'{base}/trees', dict(base_tree=old_commit['tree']['sha'], tree=tree_entries))
        # GitHub attributes the commit to the authenticated user; no synthetic coauthors.
        commit = github_api(f'{base}/commits', dict(message=message.strip(), tree=tree['sha'], parents=[head]))
        # force=False also protects against a concurrent push after the initial check.
        github_api(f'{base}/refs/{ref}', dict(sha=commit['sha'], force=False), method='PATCH')
        result = self.register(desc, files, commit['sha'])
        result['commit_url'] = f'https://github.com/{desc["repo"]}/commit/{commit["sha"]}'
        return result

    def dispatch(self, action, payload):
        with self.lock:
            if action == 'open':
                if payload.get('kind') == 'github': return self.open_github(payload.get('repo'), payload.get('branch', ''), payload.get('folder', ''))
                return self.open_local(payload.get('path'))
            if action == 'create': return self.create_local(payload.get('path', ''), payload.get('files'))
            if action == 'save': return self.save_local(payload.get('id'), payload.get('revision'), payload.get('files'))
            if action == 'commit': return self.commit_github(payload.get('id'), payload.get('revision'), payload.get('files'), payload.get('message'))
            if action == 'repositories':
                repos = github_api('user/repos?sort=updated&per_page=100')
                return dict(repositories=[dict(name=r['full_name'], branch=r['default_branch']) for r in repos])
            if action == 'projects':
                desc = self.github_descriptor(payload.get('repo'), payload.get('branch', ''))
                tree = github_api(f'repos/{desc["repo"]}/git/trees/{quote(desc["branch"], safe="")}?recursive=1')
                if tree.get('truncated'): raise ValueError('Elenco incompleto: indica la cartella manualmente.')
                folders = sorted(item['path'][:-len('main.cvc')].rstrip('/') for item in tree['tree']
                                 if item['type'] == 'blob' and (item['path'] == 'main.cvc' or item['path'].endswith('/main.cvc'))
                                 and not any(p.startswith('.') for p in item['path'].split('/')))
                return dict(folders=folders)
            if action == 'account':
                user = github_api('user')
                return dict(login=user['login'])
            if action == 'pick':
                if sys.platform != 'darwin': raise ValueError('Inserisci il percorso della cartella nel campo sottostante.')
                result = subprocess.run(['osascript', '-e', 'POSIX path of (choose folder with prompt "Scegli la cartella del progetto CVCC")'], capture_output=True, text=True, timeout=120)
                if result.returncode: return dict(cancelled=True)
                return dict(path=result.stdout.strip())
            raise ValueError('Operazione workspace sconosciuta.')
