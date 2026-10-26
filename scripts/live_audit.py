#!/usr/bin/env python3
"""Audit live public pages on lagale.in: HTTP, redirects, canonicals and sitemap."""
from __future__ import annotations
import argparse, csv, datetime as dt, html.parser, re, time
import urllib.error, urllib.parse, urllib.request, urllib.robotparser
from collections import deque
from pathlib import Path

UA = "Lagale-Live-URL-Audit/1.0 (+https://github.com/uhackman-cpu/Quiz-live-url-test)"
SKIP_EXT = {".jpg",".jpeg",".png",".gif",".webp",".svg",".ico",".pdf",".zip",".gz",".mp4",".mp3",".woff",".woff2",".ttf",".css",".js",".json"}

class PageParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]; self.title=""; self.h1=""; self.canonical=""; self.robots=""
        self.in_title=False; self.in_h1=False
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); tag=tag.lower()
        if tag=="a" and a.get("href"): self.links.append((a["href"], a.get("aria-label","")))
        if tag=="link" and "canonical" in a.get("rel","").lower(): self.canonical=a.get("href","")
        if tag=="meta" and a.get("name","").lower()=="robots": self.robots=a.get("content","")
        if tag=="title": self.in_title=True
        if tag=="h1": self.in_h1=True
    def handle_endtag(self, tag):
        if tag.lower()=="title": self.in_title=False
        if tag.lower()=="h1": self.in_h1=False
    def handle_data(self, data):
        if self.in_title: self.title+=data
        if self.in_h1: self.h1+=data+" "

def normalize(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme.lower() not in ("http","https"): return None
    return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),re.sub(r"/{2,}","/",p.path or "/"),p.query,""))

def fetch(url, timeout):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            data=r.read(3000000); ctype=r.headers.get("Content-Type","")
            text=data.decode(r.headers.get_content_charset() or "utf-8",errors="replace") if ("html" in ctype.lower() or "xml" in ctype.lower() or not ctype) else ""
            return r.status,r.geturl(),ctype,text,""
    except urllib.error.HTTPError as e:
        return e.code,e.geturl(),e.headers.get("Content-Type",""),"",str(e)
    except Exception as e: return 0,url,"","",str(e)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--base",default="https://lagale.in/")
    ap.add_argument("--max-pages",type=int,default=1600)
    ap.add_argument("--delay",type=float,default=.25)
    ap.add_argument("--timeout",type=int,default=18)
    ap.add_argument("--out",default="reports")
    args=ap.parse_args(); base=normalize(args.base)
    if not base: raise SystemExit("Invalid --base URL")
    host=urllib.parse.urlsplit(base).netloc; scheme=urllib.parse.urlsplit(base).scheme
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    started=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    robots_url=f"{scheme}://{host}/robots.txt"
    robots_status,_,_,robots_text,robots_error=fetch(robots_url,args.timeout)
    rp=urllib.robotparser.RobotFileParser()
    if robots_status and robots_status<400 and robots_text: rp.parse(robots_text.splitlines())
    else: rp=None

    sitemap_url=f"{scheme}://{host}/sitemap.xml"
    sitemap_status,_,_,sitemap_text,sitemap_error=fetch(sitemap_url,args.timeout)
    raw_locs=re.findall(r"<loc>\s*(.*?)\s*</loc>",sitemap_text,re.I|re.S) if sitemap_status and sitemap_status<400 else []
    sitemap_urls={normalize(urllib.parse.urljoin(sitemap_url,re.sub("&amp;","&",v.strip()))) for v in raw_locs}
    sitemap_urls={u for u in sitemap_urls if u}
    queue=deque([base]); queued={base}; visited=set(); rows=[]; link_rows=[]; disallowed=0

    while queue and len(visited)<args.max_pages:
        url=normalize(queue.popleft())
        if not url or url in visited or urllib.parse.urlsplit(url).netloc!=host: continue
        if rp and not rp.can_fetch(UA,url):
            disallowed+=1; continue
        visited.add(url)
        status,final_url,ctype,body,error=fetch(url,args.timeout)
        row={"url":url,"http_status":status,"final_url":final_url,
             "redirected":bool(normalize(final_url) and normalize(final_url)!=url),
             "content_type":ctype,"title":"","h1":"","canonical":"",
             "canonical_matches_final":"","robots_meta":"","internal_links":0,
             "in_sitemap":url in sitemap_urls,"error":error}
        if body and "html" in ctype.lower():
            parser=PageParser()
            try: parser.feed(body)
            except Exception: pass
            row["title"]=" ".join(parser.title.split())
            row["h1"]=" ".join(parser.h1.split())
            row["canonical"]=urllib.parse.urljoin(final_url,parser.canonical) if parser.canonical else ""
            row["canonical_matches_final"]=bool(row["canonical"] and normalize(row["canonical"])==normalize(final_url))
            row["robots_meta"]=parser.robots
            for href,label in parser.links:
                target=normalize(urllib.parse.urljoin(final_url,href.strip()))
                if not target or urllib.parse.urlsplit(target).netloc!=host: continue
                if Path(urllib.parse.urlsplit(target).path).suffix.lower() in SKIP_EXT: continue
                row["internal_links"]+=1
                link_rows.append({"source":url,"target":target,"anchor_label":label})
                if target not in queued and target not in visited:
                    queue.append(target); queued.add(target)
        rows.append(row)
        if args.delay>0: time.sleep(args.delay)

    successful_missing=[r for r in rows if 0<r["http_status"]<400 and r["url"] not in sitemap_urls]
    sitemap_not_crawled=sorted(sitemap_urls-visited)
    errors=[r for r in rows if r["http_status"]>=400 or r["http_status"]==0]
    redirects=[r for r in rows if r["redirected"]]
    html_rows=[r for r in rows if 0<r["http_status"]<400 and "html" in r["content_type"].lower()]
    canonical_mismatch=[r for r in html_rows if r["canonical"] and not r["canonical_matches_final"]]
    no_canonical=[r for r in html_rows if not r["canonical"]]
    no_title=[r for r in html_rows if not r["title"]]
    no_h1=[r for r in html_rows if not r["h1"]]

    def write_csv(filename, fields, items):
        with (out/filename).open("w",newline="",encoding="utf-8-sig") as f:
            writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(items)
    fields=list(rows[0].keys()) if rows else ["url","http_status","final_url","redirected","content_type","title","h1","canonical","canonical_matches_final","robots_meta","internal_links","in_sitemap","error"]
    write_csv("live-url-audit.csv",fields,rows)
    write_csv("internal-links.csv",["source","target","anchor_label"],link_rows)
    write_csv("sitemap-not-crawled.csv",["url"],[{"url":u} for u in sitemap_not_crawled])

    report=out/"LIVE-AUDIT-REPORT.md"
    with report.open("w",encoding="utf-8") as f:
        f.write(f"# Lagale Live URL Audit\n\n- Started: {started}\n- Base URL: {base}\n- robots.txt HTTP status: {robots_status} ({robots_error})\n- sitemap.xml HTTP status: {sitemap_status} ({sitemap_error})\n- Sitemap URLs parsed: {len(sitemap_urls)}\n- URLs crawled: {len(rows)} (configured cap: {args.max_pages})\n- Successful HTML pages: {len(html_rows)}\n- Internal links recorded: {len(link_rows)}\n- robots-disallowed candidates skipped: {disallowed}\n\n## Summary\n\n| Check | Count |\n|---|---:|\n| HTTP errors or request failures | {len(errors)} |\n| Redirecting URLs | {len(redirects)} |\n| Canonical review candidates | {len(canonical_mismatch)} |\n| HTML pages without canonical | {len(no_canonical)} |\n| HTML pages without title | {len(no_title)} |\n| HTML pages without H1 | {len(no_h1)} |\n| Successful crawled URLs absent from sitemap | {len(successful_missing)} |\n| Sitemap URLs not reached in crawl | {len(sitemap_not_crawled)} |\n\n")
        def section(title,items,keys):
            f.write(f"## {title}\n\n")
            if not items: f.write("No findings.\n\n"); return
            f.write("| "+" | ".join(keys)+" |\n|"+"|".join(["---"]*len(keys))+"|\n")
            for item in items[:200]:
                f.write("| "+" | ".join(str(item.get(k,"")).replace("|","\\|").replace("\n"," ")[:240] for k in keys)+" |\n")
            if len(items)>200: f.write(f"\n_First 200 of {len(items)}; full detail is in CSV._\n")
            f.write("\n")
        section("HTTP errors / request failures",errors,["http_status","url","final_url","error"])
        section("Redirects",redirects,["url","http_status","final_url"])
        section("Canonical review candidates",canonical_mismatch,["url","canonical","final_url"])
        section("Successful URLs absent from sitemap",successful_missing,["http_status","url"])
        section("Sitemap URLs not reached during crawl",[{"url":u} for u in sitemap_not_crawled],["url"])
        f.write("\n## Interpretation notes\n\n- Point-in-time crawl; rate limiting, bot restrictions, redirects, or transient network errors may affect results.\n- Sitemap URLs not reached are not automatically broken: they may lack internal links, be disallowed by robots.txt, or fall beyond the crawl cap.\n- Canonical differences are review candidates, not automatic defects.\n- Google indexing state must be verified in Search Console.\n")
    print(f"CRAWLED={len(rows)} SITEMAP={len(sitemap_urls)} HTML={len(html_rows)} ERRORS={len(errors)} REDIRECTS={len(redirects)}")
    print(f"REPORT={report} CSV={out/'live-url-audit.csv'}")

if __name__=="__main__": main()
