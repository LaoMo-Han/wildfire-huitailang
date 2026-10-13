"""Read-only resource inspection. Parses old marshalled code; never executes it."""
from pathlib import Path
import argparse, json, re, struct


class MarshalReader:
    def __init__(self, data, pos=0):
        self.data, self.pos, self.strings = data, pos, []

    def read(self, n):
        if not 0 <= n <= 200_000_000 or self.pos + n > len(self.data):
            raise ValueError('out of bounds')
        b = self.data[self.pos:self.pos+n]
        self.pos += n
        return b

    def integer(self):
        return struct.unpack('<i', self.read(4))[0]

    def value(self, depth=0):
        if depth > 100:
            raise ValueError('nesting limit')
        kind = self.read(1)
        if kind in (b'N', b'0'): return None
        if kind == b'T': return True
        if kind == b'F': return False
        if kind == b'i': return self.integer()
        if kind == b'I': return struct.unpack('<q', self.read(8))[0]
        if kind == b'g': return struct.unpack('<d', self.read(8))[0]
        if kind == b'f': return float(self.read(self.read(1)[0]))
        if kind == b'l':
            count = self.integer()
            if abs(count) > 10000: raise ValueError('long limit')
            parts = struct.unpack('<'+'H'*abs(count), self.read(2*abs(count)))
            return sum(part << (15*i) for i,part in enumerate(parts)) * (-1 if count < 0 else 1)
        if kind in (b's', b't', b'u'):
            val = self.read(self.integer())
            if kind == b't': self.strings.append(val)
            if kind == b'u': val = val.decode('utf-8')
            return val
        if kind == b'R':
            return self.strings[self.integer()]
        if kind in (b'(', b'['):
            count = self.integer()
            if not 0 <= count <= 1_000_000: raise ValueError('count limit')
            return tuple(self.value(depth+1) for _ in range(count))
        if kind == b'{':
            pairs = []
            while self.data[self.pos:self.pos+1] != b'0':
                if len(pairs) > 1_000_000: raise ValueError('dict limit')
                pairs.append((self.value(depth+1),self.value(depth+1)))
            self.pos += 1
            return {'dict': pairs}
        if kind == b'c':
            record = {'type': 'code'}
            for field in ('argcount','nlocals','stacksize','flags'):
                record[field] = self.integer()
            if not all(0 <= record[f] <= 100_000 for f in ('argcount','nlocals','stacksize')):
                raise ValueError('code sanity')
            for field in ('code','consts','names','varnames','freevars','cellvars','filename','name'):
                record[field] = self.value(depth+1)
            record['firstlineno'] = self.integer()
            record['lnotab'] = self.value(depth+1)
            if not isinstance(record['code'],bytes) or not isinstance(record['filename'],bytes):
                raise ValueError('code types')
            return record
        raise ValueError('unsupported kind '+repr(kind))


def text(b):
    if isinstance(b, bytes):
        try: return b.decode('utf-8')
        except UnicodeDecodeError: return b.decode('gb18030',errors='replace')
    return b


def flatten_codes(obj):
    if isinstance(obj,dict) and obj.get('type') == 'code':
        yield obj
        for child in obj['consts']:
            yield from flatten_codes(child)
    elif isinstance(obj,(list,tuple)):
        for child in obj: yield from flatten_codes(child)


def flat_strings(obj):
    if isinstance(obj,bytes):
        yield text(obj)
    elif isinstance(obj,(tuple,list)):
        for item in obj: yield from flat_strings(item)
    elif isinstance(obj,dict):
        for key,item in obj.items():
            if key not in ('code','lnotab'): yield from flat_strings(item)


def summary(code):
    return {
        'name':text(code['name']), 'filename':text(code['filename']),
        'line':code['firstlineno'],'args':[text(x) for x in code['varnames'][:code['argcount']]],
        'names':[text(x) for x in code['names']],
        'constants':list(flat_strings(code['consts'])),
        'bytecode':code['code'].hex(),
    }


def carve(source,out):
    data=source.read_bytes()
    modules=[]
    skipped_until=0
    for match in re.finditer(rb'c\x00\x00\x00\x00\x00\x00\x00\x00',data):
        offset=match.start()
        if offset < skipped_until: continue
        try:
            reader=MarshalReader(data,offset)
            code=reader.value()
            if code['name'] != b'<module>': continue
            entry={'offset':offset,'end':reader.pos,'filename':text(code['filename']),
                   'functions':[summary(c) for c in flatten_codes(code)]}
            modules.append(entry)
            skipped_until=reader.pos
        except (ValueError,IndexError,TypeError,KeyError,UnicodeDecodeError,struct.error):
            pass
    out.mkdir(parents=True,exist_ok=True)
    (out/'marshal_modules.json').write_text(json.dumps(modules,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'module_names.txt').write_text('\n'.join(m['filename'] for m in modules),encoding='utf-8')
    print(f'{source.name}: {len(modules)} modules, {sum(len(m["functions"]) for m in modules)} code objects')
    print('\n'.join(m['filename'] for m in modules if any(x in m['filename'].lower() for x in ('login','replay','personality','offline','gamemain','client.py','hall','main.o'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('out',type=Path)
    args=parser.parse_args()
    carve(args.source,args.out)
