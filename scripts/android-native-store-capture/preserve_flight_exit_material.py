"""Read-only exact Flight crash material with inode/nofollow and shared byte budget."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from datetime import datetime,timezone

MAX_FILES=256
MAX_BYTES=64*1024*1024
SOURCE=Path('/tmp/android-runner/emu-crash-37.2.12.db')

def identity(value):return value.st_dev,value.st_ino,value.st_mode
def stable(value):return identity(value)+(value.st_size,value.st_mtime_ns,value.st_ctime_ns)
def inventory(root):
 root_stat=os.lstat(root)
 if stat.S_ISLNK(root_stat.st_mode) or not (stat.S_ISDIR(root_stat.st_mode) or stat.S_ISREG(root_stat.st_mode)):
  raise RuntimeError('Exact crash root is symlink/nonregular')
 files=[root] if stat.S_ISREG(root_stat.st_mode) else list(root.rglob('*'))
 records={}
 for file in files:
  value=os.lstat(file)
  if stat.S_ISLNK(value.st_mode):raise RuntimeError('Crash material symlink rejected')
  if stat.S_ISDIR(value.st_mode):continue
  if not stat.S_ISREG(value.st_mode):raise RuntimeError('Crash material nonregular file rejected')
  records[file]=value
  if len(records)>MAX_FILES:raise RuntimeError('Crash material file count exceeds exact bound')
 if sum(x.st_size for x in records.values())>MAX_BYTES:raise RuntimeError('Crash material preflight bytes exceed bound')
 return root_stat,records

def secure_open(file,root,root_stat):
 flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0);directory_flags=flags|getattr(os,'O_DIRECTORY',0)
 if stat.S_ISDIR(root_stat.st_mode) and os.open in os.supports_dir_fd:
  directory=os.open(root,directory_flags)
  try:
   if identity(os.fstat(directory))!=identity(root_stat):raise RuntimeError('Crash root replaced before open')
   parts=file.relative_to(root).parts
   for part in parts[:-1]:
    next_directory=os.open(part,directory_flags,dir_fd=directory)
    os.close(directory);directory=next_directory
    if not stat.S_ISDIR(os.fstat(directory).st_mode):raise RuntimeError('Non-directory crash ancestor')
   return os.open(parts[-1],flags,dir_fd=directory)
  finally:os.close(directory)
 before=os.lstat(file)
 if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):raise RuntimeError('Source changed to symlink/nonregular')
 return os.open(file,flags)

def copy_bounded(file,target,root,root_stat,expected,budget):
 descriptor=secure_open(file,root,root_stat)
 try:
  opened=os.fstat(descriptor)
  if not stat.S_ISREG(opened.st_mode) or stable(opened)!=stable(expected):raise RuntimeError('Crash file changed/replaced before read')
  if expected.st_size>budget['remaining']:raise RuntimeError('Shared byte budget exceeded before copy')
  target.parent.mkdir(parents=True,exist_ok=True);copied=0;digest=hashlib.sha256()
  with target.open('xb') as output:
   while copied<expected.st_size:
    amount=min(65536,expected.st_size-copied,budget['remaining'])
    if amount<=0:raise RuntimeError('Shared byte budget exhausted; partial only')
    data=os.read(descriptor,amount)
    if not data:raise RuntimeError('Source truncated during bounded read; partial only')
    if len(data)>amount or len(data)>budget['remaining']:raise RuntimeError('Read exceeded remaining bound; partial only')
    output.write(data);digest.update(data);copied+=len(data);budget['remaining']-=len(data);budget['copied']+=len(data)
   output.flush();os.fsync(output.fileno())
  if stable(os.fstat(descriptor))!=stable(expected) or stable(os.lstat(file))!=stable(expected):
   raise RuntimeError('Crash source grew/changed/replaced during copy; partial only')
  if not stat.S_ISREG(os.lstat(target).st_mode) or target.stat().st_size!=copied:raise RuntimeError('Output invariant failed')
  return {'source':str(file),'file':target.name,'bytes':copied,'sha256':digest.hexdigest(),'binaryUnmodified':True,'complete':True}
 finally:os.close(descriptor)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--capture-output',required=True);args=parser.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='mars-tw/taiwan-train-math' or os.environ.get('PROJECT')!='island-flight-school':
  raise SystemExit('Only owned Flight CI may preserve this material')
 run=os.environ['GITHUB_RUN_ID'];expected_avd='NativeCapturePhone_'+run+'_island-flight-school'
 if not run.isdigit() or os.environ.get('NATIVE_AVD_NAME')!=expected_avd:raise SystemExit('Exact Flight AVD required')
 output=Path(args.capture_output).resolve();workspace=Path(os.environ['GITHUB_WORKSPACE']).resolve()
 if not output.is_relative_to(workspace):raise SystemExit('Output escapes own workspace')
 destination=output/'flight-exit-material';destination.mkdir(parents=True,exist_ok=True)
 report={'runId':run,'avd':expected_avd,'observedAtUtc':datetime.now(timezone.utc).isoformat(),'emulatorExitCode':None,'emulatorSignal':None,
  'exitCodeOrSignalNotInferred':True,'materialCopied':[],'missingOrUnsafe':[],'collectionComplete':False,'partialMaterial':False,
  'newSdkVersionOrAvdLaunched':False,'byteLimit':MAX_BYTES,'fileLimit':MAX_FILES}
 budget={'remaining':MAX_BYTES,'copied':0}
 try:
  root_stat,records=inventory(SOURCE)
  for file,value in records.items():
   relative=Path(SOURCE.name)/file.relative_to(SOURCE) if stat.S_ISDIR(root_stat.st_mode) else Path(SOURCE.name)
   receipt=copy_bounded(file,destination/relative,SOURCE,root_stat,value,budget);receipt['file']=relative.as_posix();report['materialCopied'].append(receipt)
  after_root,after_records=inventory(SOURCE)
  if identity(after_root)!=identity(root_stat) or {str(f):stable(v) for f,v in records.items()}!={str(f):stable(v) for f,v in after_records.items()}:
   raise RuntimeError('Crash directory/file inventory changed during collection')
  report['collectionComplete']=True;report['status']='READONLY_EXIT_MATERIAL_RETAINED_SIGNAL_UNASSESSED'
 except (OSError,RuntimeError,ValueError) as error:
  report.update(status='HOLD_PARTIAL_EXIT_MATERIAL_UNKNOWN',collectionComplete=False,partialMaterial=budget['copied']>0,
   missingOrUnsafe=[str(error)],incompleteMaterialMustNotBePromoted=True)
  for receipt in report['materialCopied']:receipt.update(complete=False,collectionIncomplete=True)
 report['actualCopiedBytes']=budget['copied'];report['remainingByteBudget']=budget['remaining']
 (destination/'exit-material-receipt.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':report['status'],'runId':run,'files':len(report['materialCopied']),'collectionComplete':report['collectionComplete'],'actualCopiedBytes':budget['copied']}))

if __name__=='__main__':main()
