"""Internship Scout v2: explicit coverage reporting, official ATS discovery, and alerts."""
import csv, hashlib, json, os, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

S = requests.Session()
S.headers.update({'User-Agent':'Mozilla/5.0 (compatible; PersonalInternshipScout/2.0)'})
GOOD = re.compile(r'\b(intern(ship)?|summer associate|placement|working student)\b',re.I)
DOMAIN = re.compile(r'marketing|brand|creative|strateg(y|ic)|advertis|account planning|consumer insight|social media|communications|campaign|content|growth marketing|product marketing',re.I)
BAD = re.compile(r'software engineer|backend|frontend|data engineer|machine learning engineer|security engineer|hardware engineer|finance intern|legal intern',re.I)
NO_SPONSOR = re.compile(r'(?:no|not|cannot|unable to|will not).{0,40}sponsor|sponsorship.{0,30}(?:not|unavailable)',re.I)
ATS = re.compile(r'(?:boards\.greenhouse\.io|job-boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com)/([\w-]+)',re.I)
SEEN=Path('seen.json'); seen=json.loads(SEEN.read_text()) if SEEN.exists() else {}
new=[]; statuses=[]

def get(url):
    r=S.get(url,timeout=16); r.raise_for_status(); return r

def feed(ats, token):
    if ats=='greenhouse':
        data=get(f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true').json()
        return [(j.get('title',''),j.get('absolute_url',''),BeautifulSoup(j.get('content',''),'html.parser').get_text(' ',strip=True)) for j in data.get('jobs',[])]
    if ats=='lever':
        data=get(f'https://api.lever.co/v0/postings/{token}?mode=json').json()
        return [(j.get('text',''),j.get('hostedUrl',''),j.get('descriptionPlain','')) for j in data]
    if ats=='ashby':
        data=get(f'https://api.ashbyhq.com/posting-api/job-board/{token}').json()
        return [(j.get('title',''),j.get('jobUrl',''),j.get('descriptionPlain','')) for j in data.get('jobs',[])]
    raise ValueError('Unsupported ATS: '+ats)

def discover(url):
    """Only follow ATS URLs actually present on company's own public careers page."""
    r=get(url); soup=BeautifulSoup(r.text,'html.parser')
    links=[]; ats_boards=[]
    for a in soup.select('a[href]'):
        href=urljoin(r.url,a.get('href','')); label=a.get_text(' ',strip=True)
        m=ATS.search(href)
        if m:
            host=urlparse(href).hostname or ''
            kind='greenhouse' if 'greenhouse' in host else 'lever' if 'lever' in host else 'ashby'
            pair=(kind,m.group(1))
            if pair not in ats_boards:ats_boards.append(pair)
        if GOOD.search(label) and DOMAIN.search(label) and urlparse(href).scheme in ('http','https'):
            links.append((label[:180],href,label))
    if ats_boards:
        for kind,token in ats_boards[:3]:
            try:return feed(kind,token),'verified linked '+kind
            except Exception as e: print('ATS linked but unavailable:',kind,token,type(e).__name__)
    return links,'HTML links only (incomplete; may omit JavaScript jobs)'

def assess(title,description,locations):
    if not GOOD.search(title) or BAD.search(title) or not DOMAIN.search(title+' '+description):return False,'unrelated'
    if NO_SPONSOR.search(description) and re.search(r'\bUS\b|United States',locations,re.I) and not re.search(r'Singapore|United Kingdom|India',description,re.I):
        return False,'US sponsorship restriction (verify actual job location)'
    return True,'dates and work authorization unverified'

with open('companies.csv',newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
for row in rows:
    if row.get('monitor','yes').lower()!='yes':continue
    company=row['company']; url=row.get('careers_url','').strip()
    if not url:
        statuses.append((company,'NOT CONFIGURED','missing careers URL',0));continue
    try:
        ats=row.get('ats','').strip().lower();token=row.get('board_token','').strip()
        if ats and token: jobs=feed(ats,token);method='configured '+ats
        else: jobs,method=discover(url)
        status='FEED CONNECTED' if 'greenhouse' in method or 'lever' in method or 'ashby' in method else 'PARTIAL COVERAGE'
        statuses.append((company,status,method,len(jobs)))
        print(f'{company}: {status} | {len(jobs)} postings | {method}')
        for title,link,desc in jobs:
            eligible,reason=assess(title,desc,row.get('locations',''))
            if not eligible or not link:continue
            key=hashlib.sha256((company.lower()+'|'+link.split('?')[0]).encode()).hexdigest()
            if key in seen:continue
            new.append({'company':company,'title':title,'url':link,'reason':reason})
            seen[key]={'company':company,'title':title,'url':link}
    except Exception as e:
        msg=f'{type(e).__name__}: {str(e)[:130]}'
        statuses.append((company,'FAILED',msg,0));print(f'{company}: FAILED | {msg}')
    time.sleep(.15)
SEEN.write_text(json.dumps(seen,indent=2,ensure_ascii=False)+'\n')
counts={s:sum(x[1]==s for x in statuses) for s in ['FEED CONNECTED','PARTIAL COVERAGE','FAILED','NOT CONFIGURED']}
print('\n=== COVERAGE REPORT ===')
print('Configured rows:',len(statuses),'|',', '.join(f'{k}: {v}' for k,v in counts.items()),'| new matches:',len(new))
print('IMPORTANT: PARTIAL COVERAGE does NOT mean no vacancies. It means HTML-only scanning.')
for name,status,detail,n in statuses:
    if status in ('FAILED','NOT CONFIGURED'):print('NEEDS ATTENTION:',name,'—',detail)

# Always publish a coverage report as a workflow artifact (via workflow YAML).
report=['# Internship Scout coverage report','',f'Company entries: {len(statuses)}',f'New potential matches: {len(new)}','',
        '| Company | Coverage | Postings visible | Method / issue |','|---|---|---:|---|']
for name,status,detail,n in statuses:
    report.append('| '+ ' | '.join([name.replace('|','/'),status,str(n),detail.replace('|','/').replace('\n',' ')])+' |')
Path('coverage_report.md').write_text('\n'.join(report)+'\n')

if new:
    body='## New possible internship matches\n\n**Verify the job dates, location and work authorization before applying.**\n\n'
    for j in new[:40]:body+=f'- **{j["company"]}: {j["title"]}** — {j["url"]} ({j["reason"]})\n'
    body+='\nCoverage: '+', '.join(f'{k}: {v}' for k,v in counts.items())+'\n'
    repo=os.getenv('GITHUB_REPOSITORY');token=os.getenv('GITHUB_TOKEN')
    if repo and token:
        r=S.post(f'https://api.github.com/repos/{repo}/issues',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},
                 json={'title':f'Internship Scout: {len(new)} new possible matches','body':body},timeout=20)
        r.raise_for_status();print('Notification issue:',r.json().get('html_url'))
    else:print(body)
