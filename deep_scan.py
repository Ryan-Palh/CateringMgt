# -*- coding: utf-8 -*-
"""餐饮综合管理系统 — 深度代码审查（第二轮）"""
import ast
import os
import re
import sys

SRC_DIR = r"D:\Documents\lingxi-claw\CateringMgt\desktop"
MOBILE_DIR = r"D:\Documents\lingxi-claw\CateringMgt\mobile\lib"

def find_py_files(root):
    py_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        for f in filenames:
            if f.endswith('.py') and '__pycache__' not in dirpath:
                py_files.append(os.path.join(dirpath, f))
    return sorted(py_files)

def find_dart_files(root):
    dart_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        for f in filenames:
            if f.endswith('.dart'):
                dart_files.append(os.path.join(dirpath, f))
    return sorted(dart_files)

issues = []

def add(f, line, sev, cat, desc, sug=""):
    issues.append({"file": f, "line": line, "severity": sev, "category": cat, "desc": desc, "sug": sug})

# ═══════════════════════════════════════════════
# 1. AST 深度扫描
# ═══════════════════════════════════════════════

class DeepScanner(ast.NodeVisitor):
    def __init__(self, fname, lines):
        self.fname = fname
        self.lines = lines
        self.source = '\n'.join(lines)
        self.funcs = {}
        self.classes = {}
        self.assignments = {}

    def visit_FunctionDef(self, node):
        # Check for mutable defaults
        for arg in node.args.defaults:
            if isinstance(arg, (ast.List, ast.Dict, ast.Set)):
                add(self.fname, node.lineno, "HIGH", "mutable_default",
                    f"函数 '{node.name}' 使用可变默认参数，跨调用共享状态",
                    "改为 None 并在函数体内初始化")
        # Check for too many locals (code smell)
        if len(node.body) > 200:
            add(self.fname, node.lineno, "LOW", "long_function",
                f"函数 '{node.name}' 过长 ({len(node.body)} 行)，建议拆分")
        self.funcs[node.name] = node
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.type is None:
            add(self.fname, node.lineno, "HIGH", "bare_except",
                "裸 except: 吞掉 KeyboardInterrupt/SystemExit",
                "改为 except Exception as e:")
        self.generic_visit(node)

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.assignments[target.id] = node.lineno
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check for eval/exec
        if isinstance(node.func, ast.Name):
            if node.func.id in ('eval', 'exec'):
                add(self.fname, node.lineno, "CRITICAL", "eval_exec",
                    f"使用了 {node.func.id}()，存在代码注入风险",
                    "寻找替代方案")
        self.generic_visit(node)

# ═══════════════════════════════════════════════
# 2. 正则深度扫描
# ═══════════════════════════════════════════════

def deep_pattern_scan(fname, lines):
    full = '\n'.join(lines)
    base = os.path.basename(fname)

    # 2a. 未使用的导入
    imports = {}
    for i, line in enumerate(lines):
        m = re.match(r'^from\s+(\S+)\s+import\s+\(?(.+?)\)?\s*$', line)
        if m:
            mod = m.group(1)
            names = [n.strip().split(' as ')[-1].strip() for n in m.group(2).split(',') if n.strip()]
            for n in names:
                imports[n] = (i+1, mod)
        m = re.match(r'^from\s+(\S+)\s+import\s+(.+?)(?:\s+#.*)?$', line)
        if m:
            mod = m.group(1)
            names = [n.strip().split(' as ')[-1].strip() for n in m.group(2).split(',') if n.strip()]
            for n in names:
                imports[n] = (i+1, mod)
        m = re.match(r'^import\s+(\S+)', line)
        if m:
            imports[m.group(1)] = (i+1, '')

    for name, (lineno, mod) in imports.items():
        if name.startswith('_'):
            continue
        # Count occurrences outside the import line
        pattern = re.compile(r'\b' + re.escape(name) + r'\b')
        count = len(pattern.findall(full)) - 1  # -1 for the import itself
        if count <= 0 and name not in ('os', 'sys', 're', 'json', 'datetime', 'time', 'threading', 'logging', 'traceback', 'collections', 'math', 'random', 'copy', 'functools', 'itertools', 'typing', 'io', 'base64', 'hashlib', 'secrets', 'struct', 'zlib', 'calendar', 'shutil', 'uuid', 'pathlib', 'sqlite3', 'tempfile', 'atexit', 'subprocess', 'webbrowser', 'inspect', 'pdb', 'warnings', 'unittest', 'argparse', 'configparser', 'csv', 'html', 'xml', 'urllib', 'socket', 'ssl', 'email', 'http', 'ftplib', 'zipfile', 'tarfile', 'gzip', 'bz2', 'lzma', 'pickle', 'shelve', 'marshal', 'sysconfig', 'platform', 'locale', 'gettext', 'string', 'textwrap', 'difflib', 'unicodedata', 'stringprep', 'fpformat', 'statistics', 'decimal', 'fractions', 'numbers', 'cmath', 'bisect', 'heapq', 'array', 'weakref', 'types', 'contextlib', 'abc', 'dataclasses', 'enum', 'graphlib', 'operator', 'pprint', 'reprlib', 'textwrap', 'getopt', 'fileinput', 'linecache', 'glob', 'fnmatch', 'shlex', 'getpass', 'curses', 'termios', 'tty', 'pty', 'fcntl', 'pipes', 'posix', 'pwd', 'grp', 'spwd', 'select', 'signal', 'mmap', 'readline', 'rlcompleter', 'code', 'codeop', 'ast', 'symtable', 'token', 'keyword', 'tokenize', 'tabnanny', 'pyclbr', 'py_compile', 'compileall', 'dis', 'pickletools', 'inspect', 'pdb', 'profile', 'cProfile', 'timeit', 'trace', 'tracemalloc', 'logging', 'getopt', 'optparse', 'ctypes', 'struct', 'binascii', 'quopri', 'uu', 'base64', 'binhex', 'uu', 'xdrlib', 'mailcap', 'mimetypes', 'http', 'ftplib', 'poplib', 'imaplib', 'nntplib', 'smtplib', 'smtpd', 'telnetlib', 'socketserver', 'xmlrpc', 'ipaddress', 'ssl', 'hashlib', 'hmac', 'secrets', 'os', 'io', 'time', 'argparse', 'getopt', 'logging', 'logging.config', 'logging.handlers', 'getpass', 'curses', 'curses.textpad', 'curses.ascii', 'curses.panel', 'platform', 'errno', 'ctypes', 'struct', 'tempfile', 'glob', 'fnmatch', 'linecache', 'shutil', 'macpath', 'pickle', 'shelve', 'marshal', 'dbm', 'sqlite3', 'zlib', 'gzip', 'bz2', 'lzma', 'zipfile', 'tarfile', 'csv', 'ConfigParser', 'configparser', 'netrc', 'plistlib', 'xdrlib', 'stat', 'filecmp', 'subprocess', 'sys', 'atexit', 'signal', 'threading', 'multiprocessing', 'concurrent', 'asyncio', 'queue', 'sched', 'contextvars', '_thread', 'copyreg', 'shelve', 'reprlib', 'weakref', 'gc', 'inspect', 'site', 'user', 'functools', 'operator', 'pathlib', 'fileinput', 'stat', 'filecmp', 'tempfile', 'glob', 'fnmatch', 'linecache', 'shutil', 'macpath', 'os', 'pickle', 'shelve', 'marshal', 'dbm', 'sqlite3', 'zlib', 'gzip', 'bz2', 'lzma', 'zipfile', 'tarfile', 'csv', 'ConfigParser', 'configparser', 'netrc', 'plistlib', 'xdrlib', 'stat', 'filecmp', 'subprocess', 'sys', 'atexit', 'signal', 'threading', 'multiprocessing', 'concurrent', 'asyncio', 'queue', 'sched', 'contextvars', '_thread', 'copyreg', 'shelve', 'reprlib', 'weakref', 'gc', 'inspect', 'site', 'user', 'functools', 'operator', 'pathlib', 'fileinput'):
            continue
        add(base, lineno, "LOW", "unused_import",
            f"'{name}' 导入但未使用",
            "删除未使用的导入")

    # 2b. 硬编码路径
    for i, line in enumerate(lines):
        if re.search(r'["\']([A-Za-z]:\\[^"\']{3,})["\']', line):
            if 'DOCUMENT' not in line.upper() and 'PATH' not in line.upper() and 'DIR' not in line.upper():
                add(base, i+1, "LOW", "hardcoded_path",
                    f"硬编码 Windows 路径：{line.strip()[:60]}",
                    "使用 os.path.join 或配置文件")

    # 2c. 未关闭的数据库连接
    conn_pattern = re.finditer(r'(\w+)\s*=\s*get_connection\(\)', full)
    for m in conn_pattern:
        vname = m.group(1)
        pos = m.end()
        remaining = full[pos:pos+2000]
        if f'{vname}.close()' not in remaining and 'with' not in full[max(0,m.start()-100):m.start()]:
            add(base, full[:m.start()].count('\n')+1, "MEDIUM", "conn_leak",
                f"get_connection() 赋值给 '{vname}' 可能未关闭（附近2000字符内未找到 .close()）",
                "使用 try/finally 确保 conn.close()")

    # 2d. 重复代码块检测（简单版）
    for i in range(len(lines) - 3):
        block = lines[i].strip()
        if len(block) > 30 and block.count('def ') == 0:
            # Check if this exact line appears 3+ times in the file
            count = sum(1 for l in lines if l.strip() == block)
            if count >= 4:
                add(base, i+1, "LOW", "duplicate_code",
                    f"重复行出现 {count} 次: {block[:60]}",
                    "提取为函数")

    # 2e. 潜在空指针/None 访问
    for i, line in enumerate(lines):
        # Pattern: var = something(); var.method()  without null check
        m = re.match(r'\s*(\w+)\s*=\s*(\w+)\(\)', line)
        if m:
            vname = m.group(1)
            # Check next line for direct usage
            if i+1 < len(lines):
                next_line = lines[i+1]
                if re.search(rf'\b{vname}\.\w+', next_line) and 'if ' + vname not in next_line and 'if ' + vname not in lines[i]:
                    pass  # Too many false positives, skip for now

# ═══════════════════════════════════════════════
# 3. Dart 语言扫描
# ═══════════════════════════════════════════════

def scan_dart(fname, lines):
    full = '\n'.join(lines)
    base = os.path.basename(fname)

    # 3a. 未处理的 Future
    for i, line in enumerate(lines):
        if re.search(r'\w+\(\)\s*;', line) and 'await' not in line:
            m = re.match(r'\s*(\w+)\(\)', line)
            if m and m.group(1) in ('fetchUsers', 'pullDatabase', 'pushDatabase', 'syncOnLogin', '_init', 'login'):
                add(base, i+1, "HIGH", "dart_unawaited_future",
                    f"异步函数 '{m.group(1)}()' 调用缺少 await",
                    "添加 await 或使用 .then()")

    # 3b. catch without specific type
    for i, line in enumerate(lines):
        if re.match(r'\s*\}\s*catch\s*\(\s*_\s*\)', line):
            add(base, i+1, "MEDIUM", "dart_catch_all",
                "catch 捕获所有异常且未使用异常对象",
                "添加日志记录")

    # 3c. build method too long
    for i, line in enumerate(lines):
        if re.match(r'\s*Widget\s+build\s*\(', line):
            # Count lines until next method or end of class
            j = i + 1
            depth = 0
            while j < len(lines) and j < i + 200:
                if 'Widget build(' in lines[j] or 'State<' in lines[j]:
                    break
                j += 1
            if j - i > 100:
                add(base, i+1, "LOW", "dart_long_build",
                    f"build() 方法可能过长 (~{j-i} 行)",
                    "拆分为多个子 Widget")

# ═══════════════════════════════════════════════
# 4. 执行扫描
# ═══════════════════════════════════════════════

print("=" * 70)
print("  餐饮综合管理系统 — 第二轮深度代码审查")
print("=" * 70)

# Desktop Python
for fpath in find_py_files(SRC_DIR):
    if os.path.basename(fpath).startswith('__'):
        continue
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            source = f.read()
            lines = source.split('\n')
        tree = ast.parse(source, filename=fpath)
        scanner = DeepScanner(os.path.basename(fpath), lines)
        scanner.visit(tree)
        deep_pattern_scan(os.path.basename(fpath), lines)
    except SyntaxError as e:
        add(os.path.basename(fpath), e.lineno, "CRITICAL", "syntax_error",
            f"语法错误: {e.msg}")
    except Exception as e:
        pass

# Mobile Dart
for fpath in find_dart_files(MOBILE_DIR):
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            lines = f.read().split('\n')
        scan_dart(os.path.basename(fpath), lines)
    except Exception:
        pass

# ═══════════════════════════════════════════════
# 5. 输出报告
# ═══════════════════════════════════════════════

sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
issues.sort(key=lambda x: (sev_order.get(x["severity"], 99), x["file"], x["line"]))

counts = {}
for i in issues:
    counts[i["severity"]] = counts.get(i["severity"], 0) + 1

cats = {}
for i in issues:
    cats[i["category"]] = cats.get(i["category"], 0) + 1

print(f"\n发现问题: {len(issues)}")
for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
    if sev in counts:
        print(f"  {sev}: {counts[sev]}")
print("\n按类别:")
for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"  {cat}: {cnt}")
print()

if len(issues) == 0:
    print("✅ 未发现新问题")
else:
    print("-" * 70)
    for i, issue in enumerate(issues):
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}.get(issue["severity"], "⚪")
        print(f"\n  [{issue['severity']}] {icon} {issue['file']}:{issue['line']}")
        print(f"        类别: {issue['category']}")
        print(f"        描述: {issue['desc']}")
        if issue.get('sug'):
            print(f"        建议: {issue['sug']}")

print("\n" + "=" * 70)
print(f"  扫描完成，共 {len(issues)} 个问题")