"""Conservative daily internship monitor. Python 3.11. Public postings only."""
import csv, hashlib, json, os, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

HEADERS={"User-Agent":"InternshipScout/1.0 (personal research; contact via GitHub)"}
S=requests.Session(); S.headers.update(HEADERS)
GOOD=re.compile(r"intern(ship)?|summer associate|student placement|university recruiting",re.I)
DOMAIN=re.compile(r"marketing|brand|creative|strateg(y|ic)|advertis|account planning|consumer insight|social media|communications|campaign|content",re.I)
BAD=re.compile(r"software engineer|backend|frontend|data engineer|machine learning engineer|security engineer|hardware|finance intern|legal intern",re.I)
SUMMER=re.compile(r"summer|2027|june|july|august|may",re.I)
NO_SPONSOR=re.compile(r"(no|not|cannot|unable to|will not).{0,40}sponsor|sponsorship.{0,30}(not|unavailable)|f-1.{0,40}(ineligible|not eligible)",re.I)
EXCLUDE_LONG=re.compile(r"12.month|one.year|full.year|6.month|six.month|january.{0,15}(june|july)",re.I)
seen_file=Path("seen.json")
seen=json.loads(seen_file.read_text()) if seen_file.exists() else {}
new=[]; errors=[]; checked=0

def get(url):
    response=S.get(url,timeout=18)
    response.raise_for_status()
    return response

def extract(row):
    """Prefer official Greenhouse/Lever/Ashby API when configured; otherwise link discovery."""
    url=row["careers_url"].strip()
    ats=row.get("ats","").strip().lower()
    token=row.get("board_token","").strip()
    if ats=="greenhouse" and token:
        data=get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true").json()
        return [(j["title"],j["absolute_url"],BeautifulSoup(j.get("content",""),"html.parser").get_text(" ",strip=True)) for j in data.get("jobs",[])]
    if ats=="lever" and token:
        data=get(f"https://api.lever.co/v0/postings/{token}?mode=json").json()
        return [(j.get("text",""),j.get("hostedUrl",""),j.get("descriptionPlain","")) for j in data]
    if ats=="ashby" and token:
        data=get(f"https://api.ashbyhq.com/posting-api/job-board/{token}").json()
        return [(j.get("title",""),j.get("jobUrl",""),j.get("descriptionPlain","")) for j in data.get("jobs",[])]
    # Fallback: only jobs explicitly linked on the fetched HTML page.
    # JS-rendered job lists won't be visible; this is NOT complete monitoring.
    resp=get(url)
    soup=BeautifulSoup(resp.text,"html.parser")
    results=[]
    for a in soup.select("a[href]"):
        href=urljoin(resp.url,a.get("href",""))
        label=a.get_text(" ",strip=True)[:180]
        if (urlparse(href).scheme not in ("http","https")) or not label:continue
        if GOOD.search(label) and DOMAIN.search(label) and not BAD.search(label):
            results.append((label,href,label))
    return results

def ai_review(job):
    key=os.getenv("OPENAI_API_KEY")
    if not key:return None
    prompt=("Return ONLY JSON {\"relevant\":boolean,\"reason\":string,\"visa\":\"excluded|unknown|potentially eligible\","
            "\"summer\":\"confirmed|unknown|mismatch\"}. Evaluate a summer May-Aug 2027 student internship "
            "in marketing, creative strategy, brand, advertising, or consumer insights. "
            "Exclude US roles explicitly saying no sponsorship. Do not assume unknown work authorization "
            "or dates are confirmed. Job: "+json.dumps(job)[:9000])
    try:
        r=S.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":"Bearer "+key},
                 json={"model":"gpt-4.1-mini","temperature":0,"response_format":{"type":"json_object"},
                       "messages":[{"role":"user","content":prompt}]},timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print("AI unavailable; using rule-based screening:",str(e)[:120]);return None

with open("companies.csv",newline="",encoding="utf-8") as f:
    rows=list(csv.DictReader(f))
for row in rows:
    if row.get("monitor","yes").lower()!="yes":continue
    try:
        jobs=extract(row);checked+=1
        print(row["company"],"links/listings:",len(jobs))
        for title,url,description in jobs:
            blob=title+" "+description
            if not GOOD.search(title) or not DOMAIN.search(blob) or BAD.search(title):continue
            if NO_SPONSOR.search(blob) and ("US" in row["locations"] or "United States" in row["locations"]):
                # If the role is clearly in another country, review manually instead of excluding automatically.
                if not re.search(r"singapore|london|united kingdom|india",blob,re.I):continue
            key=hashlib.sha256((row["company"].lower()+"|"+url.split("?")[0]).encode()).hexdigest()
            if key in seen:continue
            review=ai_review({"company":row["company"],"title":title,"url":url,"description":description[:6000]})
            if review and not review.get("relevant",False):continue
            status="Summer dates unverified"
            if EXCLUDE_LONG.search(blob):status="Possible duration mismatch"
            elif SUMMER.search(blob):status="Summer clue found; verify dates"
            item={"company":row["company"],"title":title,"url":url,"location_targets":row["locations"],
                  "priority":row["priority"],"dates":status,"ai":review}
            new.append(item)
            seen[key]={"company":row["company"],"title":title,"url":url}
    except Exception as e:
        errors.append(f'{row["company"]}: {type(e).__name__}: {str(e)[:140]}')
    time.sleep(.25)

seen_file.write_text(json.dumps(seen,indent=2,ensure_ascii=False)+"\n")
print(f"Checked {checked}/{len(rows)} company sites; {len(new)} new candidates; {len(errors)} errors.")
for err in errors:print("WARNING",err)
if not new:sys.exit(0)
body="## New possible internship matches\n\n"
body+="**Verify summer 2027 dates, location, eligibility, and actual application status before applying.**\n\n"
for j in new[:30]:
    reason=(j["ai"] or {}).get("reason","Keyword match; requires human review")
    body+=f'- **{j["company"]} — {j["title"]}** ([job link]({j["url"]})) · {j["dates"]} · {reason}\n'
body+=f"\nScanned {checked}/{len(rows)} configured sites. {len(errors)} sites returned errors. "
body+="HTML fallback misses JavaScript-rendered vacancies. An alert does not establish eligibility.\n"
repo=os.getenv("GITHUB_REPOSITORY");token=os.getenv("GITHUB_TOKEN")
if repo and token:
    r=S.post(f"https://api.github.com/repos/{repo}/issues",
             headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json"},
             json={"title":f"Internship scout: {len(new)} new possible matches","body":body},timeout=20)
    r.raise_for_status()
    print("Created notification issue:",r.json().get("html_url"))
else:print(body)
