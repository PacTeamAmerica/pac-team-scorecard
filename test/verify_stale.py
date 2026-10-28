import re,sys,json
f=sys.argv[1]; meta=json.load(open(sys.argv[2]))
s=open(f,encoding='utf8').read()
fails=[]
def chk(name,got,exp):
    ok = got==exp
    print(('  ok  ' if ok else '  FAIL')+'  '+name.ljust(40)+str(got).rjust(14)+'  vs  '+str(exp))
    if not ok: fails.append(name)

M=re.search(r'MONTHLY_2026\s*=\s*\[([^\]]*)\]',s).group(1)
msum=sum(int(x) for x in M.split(','))
chk('MONTHLY_2026 sum', msum, meta['net'])
chk('invMeta.net == MONTHLY sum', int(re.search(r'net:\s*(\d+)',s).group(1)), msum)
chk('activeCount seed == clientTrailing', int(re.search(r"setActiveCount\] = useState\('(\d+)'\)",s).group(1)), meta['clientTrailing'])
chk('cnt-note trailing', int(re.search(r"'Pre-loaded: (\d+) \(billing-entity",s).group(1)), meta['clientTrailing'])
chk('cnt-note FY YTD', int(re.search(r'FY2026 YTD: (\d+) unique',s).group(1)), meta['clientFY'])
chk('NS totalOrders', int(re.search(r'"totalOrders":(\d+)',s).group(1)), meta['totalO'])
chk('QUOTE_SEED liveQuotes', int(re.search(r'"liveQuotes":(\d+)',s).group(1)), meta['liveQuotes'])
chk('QUOTE_SEED winRate', int(re.search(r'"winRate":(\d+)',s).group(1)), meta['winRate'])

# stale-label scan: any prior-cycle date string anywhere outside the embedded JSON data rows
CYCLE=sys.argv[3] if len(sys.argv)>3 else meta['cycle']  # e.g. 10/25; falls back to build_meta
print('\n  STALE LABEL SCAN (expect cycle '+CYCLE+')')
# Scan only NON-COMMENT lines: comments carry legitimate historical provenance
# dates (memo dates, decision dates, FY2025 pull dates). A stale label that
# reaches the CEO is always in a rendered string or a seed default.
lines=s.split('\n'); keep=[]; off=0; spans=[]
for ln in lines:
    st=ln.lstrip()
    if not st.startswith('//'): spans.append((off,ln))
    off+=len(ln)+1
s_scan='\n'.join(ln for _,ln in spans)
offmap=[]
for st,ln in spans:
    for i in range(len(ln)+1): offmap.append(st+i)
s=s_scan
bad=[]
for m in re.finditer(r'\b(\d{1,2})/(\d{1,2})/2026\b', s):
    if m.group(0)!=CYCLE+'/2026': bad.append((m.start(),m.group(0)))
for m in re.finditer(r'(?<![-\d])(\d{1,2})/(\d{1,2})(?![/\d])', s):
    tok=m.group(0)
    if tok in ('10/25','25/31'): continue
    ctx=s[max(0,m.start()-60):m.start()]
    if 'Oct' in ctx or 'as of' in ctx or 'refreshed' in ctx or 'export' in ctx: bad.append((m.start(),tok))
mn=int(CYCLE.split('/')[0]); dy=int(CYCLE.split('/')[1])
for m in re.finditer(r'\bOct(?:ober)? (\d{1,2})(?:,)? 2026\b', s):
    if int(m.group(1))!=dy: bad.append((m.start(),m.group(0)))
if bad:
    for off,t in bad[:25]: print('  FAIL  stale label at %d: %r  ...%s...'%(off,t,s[max(0,off-70):off+40].replace('\n',' ')))
    fails.append('stale labels (%d)'%len(bad))
else: print('  ok    no stale date labels found')
print('\n'+('STALE CHECKS PASSED' if not fails else 'FAILURES: '+', '.join(fails)))
sys.exit(1 if fails else 0)
