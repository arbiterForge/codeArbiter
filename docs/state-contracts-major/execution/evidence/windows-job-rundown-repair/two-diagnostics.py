from pathlib import Path
import sys,os,json,time,ctypes,subprocess
from ctypes import wintypes
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here/'immutable0830/core/pysrc'))
import _artifactauthoritylib as owner
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
k.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];k.GetExitCodeProcess.restype=wintypes.BOOL
k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.WaitForSingleObject.restype=wintypes.DWORD
k.CloseHandle.argtypes=[wintypes.HANDLE];k.CloseHandle.restype=wintypes.BOOL
legacy=ctypes.WinDLL('kernel32',use_last_error=True)
# Match only the test's unspecialized exit-code call for passive comparison.
legacy.CloseHandle.argtypes=[ctypes.c_void_p]
rows=[]
for label,redirect in [('inherited-pipes',False),('devnull-grandchild-output',True)]:
 cwd=here/('owned-cwd-'+label);cwd.mkdir()
 script="import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']" + (",stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL" if redirect else "") + "); print(p.pid,flush=True)"
 t=time.perf_counter_ns();completed=owner._run_contained([sys.executable,'-c',script],cwd=str(cwd),env=dict(os.environ),timeout_seconds=5);returned=time.perf_counter_ns();pid=int(completed.stdout.strip());ctypes.set_last_error(0);handle=k.OpenProcess(0x00101000,False,pid);open_error=ctypes.get_last_error();row={'variant':label,'parent_returncode':completed.returncode,'returned_after_ms':(returned-t)/1e6,'owned_descendant_pid':pid,'OpenProcess_BOOL':bool(handle),'OpenProcess_last_error':open_error,'at_return_observation_delay_ms':(time.perf_counter_ns()-returned)/1e6}
 try:
  if handle:
   code=wintypes.DWORD();ctypes.set_last_error(0);ok=k.GetExitCodeProcess(handle,ctypes.byref(code));row.update(typed_GetExitCodeProcess_BOOL=bool(ok),typed_last_error=ctypes.get_last_error(),typed_exit_code=code.value,typed_WaitForSingleObject_zero_ms=int(k.WaitForSingleObject(handle,0)))
   old_code=ctypes.c_ulong();ctypes.set_last_error(0)
   try:
    oldok=legacy.GetExitCodeProcess(handle,ctypes.byref(old_code));row.update(original_style_GetExitCodeProcess_BOOL=bool(oldok),original_style_last_error=ctypes.get_last_error(),original_style_exit_code=old_code.value)
   except (ValueError,ctypes.ArgumentError) as error:row['original_style_probe_error']=type(error).__name__
  row['first_cwd_probe_delay_ms']=(time.perf_counter_ns()-returned)/1e6
  try:os.rmdir(cwd);row['first_cwd_rmdir']='SUCCEEDED'
  except OSError as error:row.update(first_cwd_rmdir='FAILED',first_cwd_winerror=getattr(error,'winerror',None),first_cwd_errno=error.errno)
  # This wait is diagnostic cleanup after recording the initial state, never the acceptance observation.
  if handle:
   row['cleanup_wait_ms']=int(k.WaitForSingleObject(handle,10000))
   if row['cleanup_wait_ms']==0 and cwd.exists():
    try:os.rmdir(cwd);row['after_observed_termination_cleanup']='SUCCEEDED'
    except OSError as error:row.update(after_observed_termination_cleanup='FAILED',cleanup_winerror=getattr(error,'winerror',None))
  row['owned_cwd_remains']=cwd.exists()
 finally:
  if handle:row['CloseHandle_BOOL']=bool(k.CloseHandle(handle))
 rows.append(row)
 (here/'two-diagnostic-results.json').write_text(json.dumps({'actual_source':'immutable0830 exact6module copy','runtime':sys.version,'observations':rows,'scope':'Exactly one inherited-pipe and oneDEVNULL-output inert grandchild; initial facts retained independently of later process-handle wait and owned cleanup. No product/test changes, no stress or test population replay.'},indent=2)+'\n',encoding='utf-8')
print(json.dumps(rows,indent=2))
