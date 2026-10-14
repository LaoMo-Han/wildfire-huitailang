"""Local D1-compatible SQL adapter used only by Worker tests."""
import json, sqlite3, sys
from pathlib import Path

input_data=json.load(sys.stdin)
db=sqlite3.connect(input_data['database'])
db.row_factory=sqlite3.Row
db.execute('PRAGMA foreign_keys=ON')
def value(item):
    if isinstance(item,dict) and 'blob' in item:return bytes(item['blob'])
    return item
try:
    if input_data.get('schema'):db.executescript(Path(input_data['schema']).read_text())
    results=[]
    for command in input_data.get('commands',[]):
        cursor=db.execute(command['sql'],[value(v) for v in command.get('params',[])])
        rows=[]
        if cursor.description:
            for row in cursor.fetchall():rows.append({k:list(v) if isinstance(v,bytes) else v for k,v in dict(row).items()})
        results.append({'results':rows,'success':True})
    db.commit();print(json.dumps(results))
except Exception as error:
    db.rollback();print(json.dumps({'error':str(error)}))
finally:db.close()
