#!/usr/bin/env python3
"""Run reference-only regression tests and record exact outcomes."""
import argparse,json,sys,time,unittest,platform
from pathlib import Path
root=Path(__file__).resolve().parents[1]
class Results(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.outcomes=[]
    def addSuccess(self,test):super().addSuccess(test);self.outcomes.append({'test':test.id(),'outcome':'pass'})
    def addFailure(self,test,err):super().addFailure(test,err);self.outcomes.append({'test':test.id(),'outcome':'fail'})
    def addError(self,test,err):super().addError(test,err);self.outcomes.append({'test':test.id(),'outcome':'error'})
    def addSkip(self,test,reason):super().addSkip(test,reason);self.outcomes.append({'test':test.id(),'outcome':'skip','reason':reason})
p=argparse.ArgumentParser();p.add_argument('--report',type=Path);args=p.parse_args()
suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_reference_*.py')
start=time.monotonic();result=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(suite)
report={'scope':'Python reference model/reader/renderer regressions; NOT proposed Go/host/storage/farm implementation tests','python':platform.python_version(),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful() and not result.skipped,'elapsed_seconds':round(time.monotonic()-start,3),'outcomes':result.outcomes}
if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
sys.exit(0 if report['passed'] else 1)
