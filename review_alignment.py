"""Unique, reversible alignment; never fuzzy-match words or numbers."""
import re,difflib
QUOTES={'“':'"','”':'"','‘':"'",'’':"'"}
def canonical(text):
    out=[];spans=[];i=0
    while i<len(text):
        start=i;c=text[i]
        if c=='\\' and i+1<len(text) and text[i+1] in r'!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~':
            i+=1;c=text[i]
        if c.isspace():
            i+=1
            while i<len(text) and text[i].isspace():i+=1
            out.append(' ');spans.append((start,i));continue
        out.append(QUOTES.get(c,c));spans.append((start,i+1));i+=1
    return ''.join(out),spans

def align(original,item):
    if not isinstance(item,dict) or set(item)!={'before','after','reason'} or any(not isinstance(v,str) for v in item.values()):return item
    before=item['before'];after=item['after']
    if original.count(before)==1:return item
    key,_=canonical(before);whole,positions=canonical(original)
    if not key or len(key.strip())<8:return item
    starts=[m.start() for m in re.finditer('(?='+re.escape(key)+')',whole)]
    if len(starts)!=1:return item
    start=starts[0];a=positions[start][0];b=positions[start+len(key)-1][1];exact=original[a:b]
    target,_=canonical(after)
    # Preserve original typography for unchanged spans; apply only actual edits.
    _,local=canonical(exact);replacement=exact
    for tag,i,j,x,y in reversed(difflib.SequenceMatcher(None,key,target,autojunk=False).get_opcodes()):
        if tag=='equal':continue
        left=local[i][0] if i<len(local) else len(exact)
        right=local[j-1][1] if j>i else left
        replacement=replacement[:left]+target[x:y]+replacement[right:]
    return dict(before=exact,after=replacement,reason=item['reason']+' [Unique match after normalizing only quotes, whitespace and Markdown escapes]')

def risk(before,after):
    a,_=canonical(before);b,_=canonical(after)
    changed=''.join(a[i:j]+b[x:y] for tag,i,j,x,y in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes() if tag!='equal')
    return 'meaning_or_name_or_number' if any(c.isalnum() for c in changed) or any(c in changed for c in '-—―…') else 'punctuation_or_format'


def unsupported_length_change(before,after):
    """Conservatively defer character deletion and spelling-only insertions."""
    a,_=canonical(before);b,_=canonical(after)
    changes=[(tag,a[i:j],b[x:y]) for tag,i,j,x,y in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes() if tag!='equal']
    if any(tag=='delete' and any(c.isalnum() for c in old) for tag,old,new in changes):return True
    return bool(changes) and all(tag=='insert' and new.isalpha() for tag,old,new in changes)
