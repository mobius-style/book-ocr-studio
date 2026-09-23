"""Display legacy app messages in English without rewriting stored job records.

Only known application messages are translated. Book text and model responses
are not passed through this module.
"""
import json,re
from pathlib import Path
_MESSAGES=json.loads(Path(__file__).with_name('legacy_messages.json').read_text())
_TEMPLATES=[]
for old,new in _MESSAGES.items():
    fields=list(re.finditer(r'\{[^{}]+\}',old))
    if not fields:continue
    chunks=[];end=0
    for field in fields:
        chunks.append(re.escape(old[end:field.start()]));chunks.append('(.+?)');end=field.end()
    chunks.append(re.escape(old[end:]))
    _TEMPLATES.append((re.compile(''.join(chunks)),[f.group() for f in fields],new))

def english_message(value):
    if not isinstance(value,str):return value
    for pattern,fields,replacement in _TEMPLATES:
        def replace(match):
            result=replacement
            for field,content in zip(fields,match.groups()):result=result.replace(field,content)
            return result
        value=pattern.sub(replace,value)
    for old,new in sorted(_MESSAGES.items(),key=lambda p:-len(p[0])):
        if '{' not in old:value=value.replace(old,new)
    return value

def diagnostic_display(value):
    if isinstance(value,dict):
        return {k:english_message(v) if k in {'reason','message','error'} else diagnostic_display(v) for k,v in value.items()}
    if isinstance(value,list):return [diagnostic_display(v) for v in value]
    return value
