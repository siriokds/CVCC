"""Bounded project-local quoted includes; deliberately not a C macro preprocessor."""
from pathlib import Path, PurePosixPath
import re
import base64
import binascii

LIMIT = 1024 * 1024
BINARY_SUFFIXES = ('.bin', '.chr', '.pal', '.map', '.dat')

def file_bytes(value):
    if isinstance(value, str): return value.encode()
    if not isinstance(value, dict) or set(value) != {'base64'} or not isinstance(value['base64'], str):
        raise ValueError('Expected binary file encoded as {"base64": "..."}')
    try: return base64.b64decode(value['base64'], validate=True)
    except (ValueError, binascii.Error) as exc: raise ValueError('Invalid binary base64') from exc


def validate_files(files):
    if not isinstance(files, dict) or not files or len(files) > 128:
        raise ValueError('Expected 1..128 project files')
    if len({name.casefold() for name in files if isinstance(name,str)}) != len(files):
        raise ValueError('Project filenames must be unique ignoring case')
    total = 0
    for name, source in files.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_. /-]+', name) or '\\' in name:
            raise ValueError('Invalid project filename')
        path = PurePosixPath(name)
        if path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')) or path.suffix not in ('.cvc', '.h') + BINARY_SUFFIXES:
            raise ValueError('Project files must be relative source or binary paths without traversal')
        if path.suffix in BINARY_SUFFIXES:
            if isinstance(source, str): raise ValueError('Binary files require base64 encoding')
        elif not isinstance(source, str) or '\0' in source:
            raise ValueError('Expected source text without NUL bytes')
        total += len(file_bytes(source))
    if total > LIMIT:
        raise ValueError('Project exceeds 1 MiB')
    names={name.casefold() for name in files}
    if any(str(parent).casefold() in names for name in files for parent in PurePosixPath(name).parents):
        raise ValueError('Conflicting file and directory paths')
    return files


def read_project(directory):
    root = Path(directory).resolve()
    if not (root/'main.cvc').is_file():
        raise ValueError('Project requires main.cvc')
    files = {}
    for path in sorted(root.rglob('*')):
        if any(part.startswith('.') for part in path.relative_to(root).parts): continue
        if path.suffix in ('.cvc', '.h') + BINARY_SUFFIXES and path.is_file():
            if not path.resolve().is_relative_to(root):
                raise ValueError('Project symlink escapes project directory')
            if path.stat().st_size > LIMIT:
                raise ValueError('Project file exceeds 1 MiB')
            files[path.relative_to(root).as_posix()] = {'base64': base64.b64encode(path.read_bytes()).decode()} if path.suffix in BINARY_SUFFIXES else path.read_text()
            if sum(len(file_bytes(value)) for value in files.values())>LIMIT: raise ValueError('Project exceeds 1 MiB')
            if len(files)>128: raise ValueError('Too many project files')
    return validate_files(files)


def expand(entry):
    entry = Path(entry).resolve()
    if entry.is_dir(): entry = entry/'main.cvc'
    if entry.suffix != '.cvc': raise ValueError('Entry must be a .cvc file')
    root = entry.parent
    output, mapping, inputs, active, once = [], [], {}, [], set()
    total = 0

    def visit(path):
        nonlocal total
        path = path.resolve()
        if not path.is_relative_to(root): raise ValueError('Include escapes project directory')
        if path in once: return
        if path in active: raise ValueError('Include cycle: '+ ' -> '.join(p.name for p in active+[path]))
        if len(active)>=32: raise ValueError('Include nesting exceeds 32')
        if path.suffix not in ('.cvc','.h'): raise ValueError('Includes require .h or .cvc files')
        if path.stat().st_size>LIMIT: raise ValueError('Source exceeds 1 MiB')
        source = path.read_text()
        if '\0' in source: raise ValueError('Source contains NUL byte')
        inputs[path.relative_to(root).as_posix()] = source
        if len(inputs)>128: raise ValueError('Too many included files')
        active.append(path)
        in_comment = False
        for line_no, line in enumerate(source.splitlines(keepends=True), 1):
            # Remove comments only for directive recognition; leave source intact.
            clean=[]; i=0; quote=None
            while i<len(line):
                if in_comment:
                    if line[i:i+2]=='*/': in_comment=False;clean.extend('  ');i+=2
                    else: clean.append(' ');i+=1
                elif quote:
                    clean.append(line[i])
                    if line[i]=='\\' and i+1<len(line): clean.append(line[i+1]);i+=2;continue
                    if line[i]==quote: quote=None
                    i+=1
                elif line[i:i+2]=='/*': in_comment=True;clean.extend('  ');i+=2
                elif line[i:i+2]=='//': break
                else:
                    if line[i] in ('"', "'"): quote=line[i]
                    clean.append(line[i]);i+=1
            directive=''.join(clean).strip()
            if directive.startswith('#'):
                if directive=='#pragma once': once.add(path)
                else:
                    match=re.fullmatch(r'#\s*(include|incbin)\s*"([^"\n]+)"',directive)
                    if not match: raise ValueError(f'{path}:{line_no}:1: error: only quoted #include, #incbin and #pragma once are supported')
                    name=match[2]
                    if Path(name).is_absolute() or '\\' in name: raise ValueError(f'{path}:{line_no}:1: error: include must be project-relative')
                    try:
                        if match[1]=='include': visit(path.parent/name)
                        else:
                            binary=(path.parent/name).resolve()
                            if not binary.is_relative_to(root): raise ValueError('Binary escapes project directory')
                            if binary.suffix not in BINARY_SUFFIXES: raise ValueError('Unsupported binary extension')
                            if not 1 <= binary.stat().st_size <= 8192: raise ValueError('Binary must contain 1..8192 bytes')
                            data=binary.read_bytes()
                            inputs[binary.relative_to(root).as_posix()]={'base64':base64.b64encode(data).decode()}
                            if len(inputs)>128: raise ValueError('Too many included files')
                            for offset in range(0,len(data),16):
                                text=','.join(str(b) for b in data[offset:offset+16])+',\n'
                                total+=len(text.encode())
                                if total>LIMIT: raise ValueError('Expanded source exceeds 1 MiB')
                                output.append(text);mapping.append((str(path),line_no))
                    except (OSError,ValueError) as exc: raise ValueError(f'{path}:{line_no}:1: error: {exc}') from exc
                # Directives occupy one mapped blank line after included text.
                blank=re.sub(r'[^\n]', ' ', line)
                blank=blank if blank.endswith('\n') else blank+'\n'
                total+=len(blank.encode())
                if total>LIMIT: raise ValueError('Expanded source exceeds 1 MiB')
                output.append(blank);mapping.append((str(path),line_no))
            else:
                text=''.join(clean).rstrip('\r\n')+'\n'
                total+=len(text.encode())
                if total>LIMIT: raise ValueError('Expanded source exceeds 1 MiB')
                output.append(text);mapping.append((str(path),line_no))
        if in_comment: raise ValueError(f'{path}:{len(source.splitlines())}:1: error: unterminated block comment')
        active.pop()
    visit(entry)
    return ''.join(output), mapping, inputs


def remap(message, flattened, mapping):
    def replace(match):
        row=int(match[1]); col=match[2]
        if 1<=row<=len(mapping):
            path,line=mapping[row-1];return f'{path}:{line}:{col}:'
        return match[0]
    message=re.sub(re.escape(str(flattened))+r':(\d+):(\d+):',replace,message)
    return re.sub(r' \[through \d+:\d+\]', '', message)
