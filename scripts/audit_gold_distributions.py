"""Audit pinned public annotations, without images or model calls.
Run from the repository root: python3 scripts/audit_gold_distributions.py [--download]
Metadata cache: results/audit/gold_metadata; report/data: results/audit/gold-distributions.*
"""
import argparse, ast, collections, hashlib, json, pathlib, re, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
REV='1895f22252f9a702fed95334c8e3b60280b4c626'
REPO='depth2world/VLADBench'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(s): return s.strip(":[]()' .")
def normalize(r,scorer):
 s=str(r) if isinstance(r,(int,float)) else r
 if not isinstance(s,str):return None
 return (clean(s) if scorer=='Judge_criterion_QA' else s).lower()
def options(q):
 matches=re.findall(r'\[([^\]]+)\]',q.split(';',1)[-1])
 for m in reversed(matches):
  try:
   v=ast.literal_eval('['+m+']')
   if v and all(isinstance(i,str) for i in v):return sorted(set(i.lower() for i in v))
  except (ValueError,SyntaxError):pass
 return []
def main():
 download=argparse.ArgumentParser();download.add_argument('--download',action='store_true');args=download.parse_args()
 catalog=json.loads((ROOT/'all_task.json').read_text()); tree=ast.parse((ROOT/'evaluate_utils.py').read_text())
 mapping={k.value:v.id for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='func_mapping' for t in n.targets) for k,v in zip(n.value.keys,n.value.values,strict=True)}
 report={'schema_version':1,'dataset':REPO,'revision':REV,'code_sha256':{f:sha(ROOT/f) for f in ['all_task.json','evaluate_utils.py','evaluate_vlm.py']},'method':'Counts cover full source annotations, no historical one-question exclusion. Groups separate answer option sets; yes/no groups split by input selector. Repeated questions share samples and are not independent trials. No pooled categorical baseline across incompatible options.','tasks':[], 'scoring_notes': ['evaluate_utils.py:112 general scorer lowercases references but does not trim them; Judge_criterion_QA at354 additionally clean_string trims a limited punctuation set.', 'evaluate_utils.py:119 and analogous loops iterate prediction length, so absent predictions can reduce denominators.', 'evaluate_vlm.py:54 composite combines distinct metrics: not simply accuracy. Judge metrics include judgment accuracy, description accuracy, and a prompt-substring instruction score.', 'evaluate_utils.py:216 relation scoring awards partial credit per matched ID, with no deduplication of predicted IDs; repeated IDs can inflate scores.', 'evaluate_utils.py:147 grounding conversion depends on model name and sample dimension; validate coordinate conventions before comparing providers.', 'evaluate_utils.py:317 speed bounds score independently; relationship/lane improvement scores compare first and second question halves rather than independent examples.'], 'code_references': {n.name: {'file':'evaluate_utils.py','line':n.lineno} for n in tree.body if isinstance(n,ast.FunctionDef)}}
 for category,groups in catalog.items():
  for group,names in groups.items():
   for name in names:
    rel=f'{category}/{group}/{name}_E.json';p=ROOT/'results/audit/gold_metadata'/rel;url=f'https://huggingface.co/datasets/{REPO}/resolve/{REV}/{rel}'
    t={'name':name,'source':rel,'url':url,'scorer':mapping.get(name),'groups':[],'warnings':[]};report['tasks'].append(t)
    if args.download:
     try:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(urllib.request.urlopen(url,timeout=60).read())
     except Exception as e:t['download_error']=str(e)
    if not p.exists():t.update(status='annotation unavailable at catalog-derived path',samples=0,questions=0);continue
    samples=json.loads(p.read_text());scorer=t['scorer'];buckets={};issues=[];normalization=[];scene_keys=[]
    t.update(status='audited',sha256=sha(p),samples=len(samples),questions=sum(len(s['questions']) for s in samples))
    for si,s in enumerate(samples):
     scene=json.dumps([s.get('sequence'),s.get('image_path')],sort_keys=True);scene_keys.append(scene)
     if len(s.get('reference',[]))!=len(s['questions']):issues.append({'sample':si,'issue':'question/reference length mismatch'})
     for qi,q in enumerate(s['questions']):
      if qi>=len(s.get('reference',[])):issues.append({'sample':si,'question':qi,'issue':'missing reference'});continue
      r=s['reference'][qi];norm=normalize(r,scorer);opts=options(q);selector=q.split(';',1)[0]
      if r is None or r=='':issues.append({'sample':si,'question':qi,'issue':'empty reference'})
      if isinstance(r,str) and norm!=r:normalization.append({'sample':si,'question':qi,'raw':r,'normalized':norm})
      if scorer=='Grounding_criterion_QA' and 'located in the image?' in q.lower():kind='bounding_box';key=kind
      elif scorer=='Relation_criterion_QA':kind='scene_local_relation_ids';key=kind
      elif scorer=='RoadSpeed_criterion_QA':kind='speed_limit_pair';key=kind
      elif norm in ('yes','no'):kind='yes_no';key=kind+' '+selector if selector.startswith('[') else kind
      else:kind='categorical';key=kind+' '+json.dumps(opts) if opts else kind+' question '+q.split(';',1)[-1]
      b=buckets.setdefault(key,{'type':kind,'options':opts,'raw':collections.Counter(),'normalized':collections.Counter(),'samples':set(),'examples':[],'bad':[]})
      b['raw'][json.dumps(r,ensure_ascii=False)]+=1;b['normalized'][norm if norm is not None else json.dumps(r)]+=1;b['samples'].add(si)
      if len(b['examples'])<2:b['examples'].append({'sample':si,'question':qi,'prompt':q,'reference':r})
      if kind=='scene_local_relation_ids' and (not isinstance(r,str) or not re.fullmatch(r'-?\d+(?:/-?\d+)*',r)):
       b['bad'].append({'sample':si,'question':qi,'issue':'reference not slash-separated integer IDs'})
      if kind=='speed_limit_pair' and (not isinstance(r,str) or not re.search(r'\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]',r)):
       b['bad'].append({'sample':si,'question':qi,'issue':'reference cannot be parsed by official speed scorer'})
      if kind=='bounding_box':
       if not isinstance(r,list) or len(r)!=4 or not all(isinstance(v,(int,float)) for v in r):b['bad'].append({'sample':si,'question':qi,'issue':'invalid box reference'})
       if 'dimension' not in s:b['bad'].append({'sample':si,'question':qi,'issue':'missing dimension required by normalized-model scorer'})
      if kind=='categorical' and opts and norm not in opts:b['bad'].append({'sample':si,'question':qi,'issue':'normalized reference absent from parsed options','reference':r})
    t['unique_scene_input_keys']=len(set(scene_keys));t['issues']=issues;t['normalization_changes']=normalization
    for key,b in buckets.items():
     n=sum(b['raw'].values());label,count=b['normalized'].most_common(1)[0];valid=b['type']=='yes_no' or (b['type']=='categorical' and bool(b['options']) and not b['bad'])
     t['groups'].append({'key':key,'type':b['type'],'options':b['options'],'questions':n,'samples':len(b['samples']),'raw_distribution':dict(b['raw']),'scorer_normalized_distribution':dict(b['normalized']),'majority_exact_match_baseline':{'answer':label,'correct':count,'denominator':n,'accuracy':count/n} if valid else None,'baseline_note':'Descriptive in-sample constant baseline, not held-out performance or official composite.' if valid else 'No categorical baseline: structured/scene-local answer space, unparsed options, or label/options mismatch.','examples':b['examples'],'issues':b['bad']})
    if scorer=='Judge_criterion_QA':t['warnings'].append('Judgment-vs-description partition is determined by normalized gold label, not question text. Composite weights are separate from judgment accuracy.')
    if len(samples)<t['questions']:t['warnings'].append('Multiple correlated questions per sample; question count is not independent scene count.')
 report['summary']={'catalog_tasks':len(report['tasks']),'scored_tasks':len(mapping),'audited_tasks':sum(t['status']=='audited' for t in report['tasks']),'samples':sum(t['samples'] for t in report['tasks']),'questions':sum(t['questions'] for t in report['tasks'])}
 out=ROOT/'results/audit';out.mkdir(exist_ok=True);(out/'gold-distributions.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
 lines=['# VLADBench gold-label audit',f'Public annotation revision: `{REV}`. No images or inference.','',report['method'],'','|Task|Samples|Questions|Yes/no gold (all views)|','|---|---:|---:|---|']
 for t in report['tasks']:
  binary=collections.Counter()
  for b in t['groups']:
   if b['type']=='yes_no':binary.update(b['scorer_normalized_distribution'])
  lines.append(f"|{t['name']}|{t['samples']}|{t['questions']}|{dict(binary) if binary else '—'}|")
 lines += ['', '## Binary judgment baselines', '|Task / input|Questions|Source samples|Majority|Exact-match baseline|','|---|---:|---:|---|---:|']
 for t in report['tasks']:
  for g in t['groups']:
   if g['type']=='yes_no':
    b=g['majority_exact_match_baseline']; lines.append(f"|{t['name']} / {g['key']}|{g['questions']}|{g['samples']}|{b['answer']}|{100*b['accuracy']:.2f}%|")
 lines+=['','## Interpretation','The JSON contains per-task, per-answer-space distributions, exact source references and normalization differences. Majority baselines are descriptive label-frequency baselines, not composite scores. They do not by themselves invalidate model rankings.','Trajectory has no scorer mapping, is skipped explicitly in evaluate_vlm.py, and the catalog-derived English annotation URL returns404. No trajectory distribution is claimed.','Grounding uses IoU and model-name-dependent coordinate conversion; relationship IDs are local to images and award partial credit; speed limits award half credit per bound. These are not treated as categorical class frequencies.','The scorer iterates predictions, not all questions: missing predictions can shrink the evaluated denominator. Full-run completeness must be checked separately.','No image-based ground-truth correctness claim is made. Option-set groups are conservative partitions; human semantic review is still required.']
 lines += ['','## Scorer audit'] + ['- '+n for n in report['scoring_notes']]
 (out/'gold-distributions.md').write_text('\n'.join(lines)+'\n');print(json.dumps(report['summary']))
if __name__=='__main__':main()
