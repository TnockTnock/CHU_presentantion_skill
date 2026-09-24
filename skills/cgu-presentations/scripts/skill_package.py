#!/usr/bin/env python3
"""Package or install the same skill for different agents; no agent account access."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

SKILL=Path(__file__).resolve().parents[1]
PROFILES={'codex':'.agents/skills','claude':'.claude/skills','cursor':'.cursor/skills','copilot':'.github/skills','gemini':'.gemini/skills','generic':'.agents/skills'}
EXCLUDE={'local','__pycache__','node_modules','.git','.DS_Store','.venv'}
ROOT_FILES={'SKILL.md'}
ROOT_DIRS={'agents','assets','design-system','examples','references','scripts'}

def public_files(source=SKILL):
    source=Path(source);files=[]
    for path in sorted(source.rglob('*')):
        rel=path.relative_to(source)
        if any(p in EXCLUDE for p in rel.parts) or path.suffix in ('.pyc','.pyo'):continue
        if rel.parts[0] not in ROOT_FILES|ROOT_DIRS:continue
        if path.is_symlink():raise ValueError('Do not package symlink: '+str(rel))
        if path.is_file():files.append(path)
    if source/'SKILL.md' not in files:raise ValueError('SKILL.md is missing')
    return files

def package(destination,source=SKILL):
    destination=Path(destination);source=Path(source)
    if destination.exists():raise ValueError('Package destination already exists')
    files=public_files(source);destination.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(destination,'x',ZIP_DEFLATED) as z:
        for path in files:z.write(path,Path('cgu-presentations')/path.relative_to(source))
    return {'archive':str(destination.resolve()),'files':len(files),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}

def install(destination,source=SKILL,replace=False):
    destination=Path(destination).absolute();source=Path(source).resolve()
    if destination.is_symlink():raise ValueError('Destination must not be a symlink')
    if source==destination.resolve() or source in destination.resolve().parents:raise ValueError('Destination must be outside the source skill')
    files=public_files(source)
    if destination.exists() and not replace:raise ValueError('Skill exists. Use --replace to back it up and update; local/ is preserved.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    backup=None
    with tempfile.TemporaryDirectory(prefix='.cgu-install-',dir=destination.parent) as temp:
        stage=Path(temp)/'cgu-presentations';stage.mkdir()
        for path in files:
            target=stage/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        if destination.exists():
            if not destination.is_dir():raise ValueError('Destination is not a directory')
            local=destination/'local'
            if local.is_symlink():raise ValueError('local/ must not be a symlink')
            if local.is_dir():shutil.copytree(local,stage/'local',symlinks=True)
            # Keep backups outside the discovery tree so agents see one skill.
            backup_root=destination.parent.parent/'cgu-skill-backups';backup_root.mkdir(exist_ok=True)
            backup=backup_root/(destination.name+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            destination.rename(backup)
        try:stage.rename(destination)
        except OSError:
            if backup:backup.rename(destination)
            raise
    return {'installed':str(destination),'files':len(files),'backup':str(backup) if backup else None}

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    pkg=sub.add_parser('pack');pkg.add_argument('--out',required=True,type=Path)
    ins=sub.add_parser('install');ins.add_argument('--agent',choices=PROFILES,default='generic');target=ins.add_mutually_exclusive_group(required=True);target.add_argument('--project',type=Path);target.add_argument('--dest',type=Path);ins.add_argument('--replace',action='store_true')
    args=ap.parse_args()
    try:
        if args.command=='pack':result=package(args.out)
        else:result=install(args.dest or args.project/PROFILES[args.agent]/'cgu-presentations',replace=args.replace)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,OSError) as e:ap.exit(1,str(e)+'\n')
if __name__=='__main__':main()
