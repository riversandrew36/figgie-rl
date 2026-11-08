"""Resume the reward pilots and save independent exploratory benchmarks."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/figgie_competitiveness_20261106_pilot'
ENV = dict(os.environ, PYTHONPATH=str(ROOT), OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', MPLCONFIGDIR='/tmp/figgie-mpl', XDG_CACHE_HOME='/tmp/figgie-cache')


def run(config):
    name=config.stem
    import yaml
    cfg=yaml.safe_load(config.read_text())
    model=ROOT/'artifacts'/cfg['run_name']/'best_model/best_model.zip'
    final=ROOT/'artifacts'/cfg['run_name']/'models/final_model.metadata.json'
    log=OUT/f'{name}.log'
    with log.open('a') as stream:
        if not final.exists():
            subprocess.run([sys.executable,'-m','figgie_rl.train.train_ppo','--config',str(config)],cwd=ROOT,env=ENV,stdout=stream,stderr=subprocess.STDOUT,check=True)
        target=OUT/f'{name}_exploratory.json'
        if not target.exists():
            subprocess.run([sys.executable,'-m','figgie_rl.train.evaluate','--config',str(config),'--model-path',str(model),'--episodes','100','--seed','1501000','--benchmark','--output',str(target)],cwd=ROOT,env=ENV,stdout=stream,stderr=subprocess.STDOUT,check=True)
    report=json.loads(target.read_text())
    print(name,[(r['policy'],round(r['mean_profit'],2)) for r in report['aggregates']],flush=True)


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run,sorted((OUT/'configs').glob('*.yaml'))))
