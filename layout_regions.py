"""Deterministic region ordering; no text reconstruction by a language model."""
def ordered(regions, rtl=False):
    if len(regions)<2: return regions
    # Cut only through a gutter intersecting no region. Full-width headings
    # prevent a vertical cut until separated by a horizontal gutter.
    for axis in (0,1):
        spans=sorted((r['box'][axis],r['box'][axis+2]) for r in regions)
        end=spans[0][1];gaps=[]
        for start,stop in spans[1:]:
            if start>end:gaps.append((start-end,(start+end)/2))
            end=max(end,stop)
        if not gaps:continue
        _,cut=max(gaps)
        a=[r for r in regions if r['box'][axis+2]<=cut]
        b=[r for r in regions if r['box'][axis]>=cut]
        if not a or not b or len(a)+len(b)!=len(regions):continue
        groups=(b,a) if axis==0 and rtl else (a,b)
        return [r for group in groups for r in ordered(group,rtl)]
    return sorted(regions,key=lambda r:r.get('order') or 0)

def assemble(regions):
    text='';out=[]
    for n,r in enumerate(regions):
        content=r['text'].strip()
        if not content:continue
        if text:text+='\n\n'
        start=len(text);text+=content
        out.append(dict(r,id=n,start=start,end=len(text)))
    return text,out
