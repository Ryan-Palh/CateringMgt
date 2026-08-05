import re, os

files = [
    ('approval.py', 83, 'gui'),
    ('attendance.py', 179, 'gui'),
    ('authorization.py', 888, 'gui'),
    ('cost_calc.py', 450, 'gui'),
    ('cost_calc.py', 628, 'gui'),
    ('cost_calc.py', 717, 'gui'),
    ('dashboard.py', 428, 'gui'),
    ('data_io.py', 312, 'utils'),
    ('db_manager.py', 100, 'database'),
    ('purchase.py', 2999, 'gui'),
    ('revenue.py', 473, 'gui'),
    ('salary.py', 886, 'gui'),
    ('salary.py', 1016, 'gui'),
]

base = r'D:\Documents\lingxi-claw\CateringMgt\desktop'

for fname, lineno, subdir in files:
    fpath = os.path.join(base, subdir, fname)
    if not os.path.exists(fpath):
        continue

    with open(fpath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for i in range(max(0, lineno-5), min(len(lines), lineno+5)):
        if 'get_connection()' in lines[i] and '=' in lines[i]:
            m = re.match(r'\s*(\w+)\s*=', lines[i])
            if not m:
                continue
            vname = m.group(1)
            found = False
            for j in range(i+1, min(len(lines), i+100)):
                if f'{vname}.close()' in lines[j]:
                    found = True
                    print(f'OK  {fname}:{i+1}  {vname} -> close at {j+1}')
                    break
            if not found:
                # Check finally block
                for j in range(i+1, min(len(lines), i+150)):
                    if 'finally:' in lines[j]:
                        for k in range(j+1, min(len(lines), j+10)):
                            if f'{vname}.close()' in lines[k]:
                                found = True
                                print(f'OK  {fname}:{i+1}  {vname} -> finally close at {k+1}')
                                break
                        if found:
                            break
            if not found:
                print(f'LEAK {fname}:{i+1}  {vname} NOT CLOSED')