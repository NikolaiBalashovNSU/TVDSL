import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from parser import (
    Program, FunctionDef, Block, Assign, IfStatement, WhileStatement, 
    ReturnStatement, Literal, Identifier, BinaryOp, UnaryOp, CallExpr
)
from semantic import analyze_source

class Operand: pass
class Const(Operand):
    def __init__(self, v): self.v = v
    def __str__(self): return str(self.v)
class Var(Operand):
    def __init__(self, n): self.n = n
    def __str__(self): return self.n
    def __eq__(self, other): return isinstance(other, Var) and self.n == other.n
    def __hash__(self): return hash(('Var', self.n))
class Temp(Operand):
    _id = 0
    def __init__(self): Temp._id += 1; self.n = f"t{Temp._id}"
    def __str__(self): return self.n
    def __eq__(self, other): return isinstance(other, Temp) and self.n == other.n
    def __hash__(self): return hash(('Temp', self.n))

class Instr: pass
class Label(Instr):
    def __init__(self, n): self.n = n
    def __str__(self): return f"{self.n}:"
class AssignOp(Instr):
    def __init__(self, dst, op, l, r): self.dst, self.op, self.l, self.r = dst, op, l, r
    def __str__(self): return f"{self.dst} = {self.l} {self.op} {self.r}"
class AssignVar(Instr):
    def __init__(self, dst, src): self.dst, self.src = dst, src
    def __str__(self): return f"{self.dst} = {self.src}"
class CondJump(Instr):
    def __init__(self, cond, target): self.cond, self.target = cond, target
    def __str__(self): return f"if {self.cond} goto {self.target}"
class Jump(Instr):
    def __init__(self, target): self.target = target
    def __str__(self): return f"goto {self.target}"
class Call(Instr):
    def __init__(self, dst, name, args): self.dst, self.name, self.args = dst, name, args
    def __str__(self): return f"{self.dst} = call {self.name}({', '.join(map(str, self.args))})"
class Return(Instr):
    def __init__(self, v): self.v = v
    def __str__(self): return f"return {self.v}" if self.v else "return"

class IRFunc:
    def __init__(self, name, params, return_vars=None):
        self.name, self.params, self.instrs = name, params, []
        self.return_vars = return_vars or []
    def add(self, i): self.instrs.append(i)

class IRGenerator:
    def __init__(self):
        self.current_func = None
        self.lbl_cnt = 0
    def new_lbl(self): self.lbl_cnt += 1; return f"L{self.lbl_cnt}"
    
    def generate(self, program: Program):
        funcs = {}
        for decl in program.declarations:
            if isinstance(decl, FunctionDef):
                return_vars = []
                if isinstance(decl.return_type, list):
                    return_vars = [r[0] for r in decl.return_type]
                
                f = IRFunc(decl.name, [p[0] for p in decl.params], return_vars)
                self.current_func = f
                self.gen_block(decl.body)
                
                if return_vars and len(return_vars) == 1:
                    if not f.instrs or not isinstance(f.instrs[-1], Return):
                        f.add(Return(Var(return_vars[0])))
                
                funcs[decl.name] = f
        return funcs

    def gen_block(self, block: Block):
        for stmt in block.statements: self.gen_stmt(stmt)

    def gen_stmt(self, stmt):
        if isinstance(stmt, Assign) and stmt.index is None:
            src = self.gen_expr(stmt.value)
            self.current_func.add(AssignVar(Var(stmt.name), src))
        elif isinstance(stmt, IfStatement):
            self.gen_if(stmt)
        elif isinstance(stmt, WhileStatement):
            self.gen_while(stmt)
        elif isinstance(stmt, ReturnStatement):
            self.current_func.add(Return(self.gen_expr(stmt.expr) if stmt.expr else None))
        elif isinstance(stmt, Block):
            self.gen_block(stmt)

    def gen_if(self, node: IfStatement):
        l_then, l_end = self.new_lbl(), self.new_lbl()
        self.current_func.add(CondJump(self.gen_expr(node.condition), l_then))
        if node.else_branch:
            l_else = self.new_lbl()
            self.current_func.add(Jump(l_else))
            self.current_func.add(Label(l_then))
            self.gen_block(node.then_branch)
            self.current_func.add(Jump(l_end))
            self.current_func.add(Label(l_else))
            self.gen_stmt(node.else_branch)
        else:
            self.current_func.add(Jump(l_end))
            self.current_func.add(Label(l_then))
            self.gen_block(node.then_branch)
        self.current_func.add(Label(l_end))

    def gen_while(self, node: WhileStatement):
        l_start, l_body, l_end = self.new_lbl(), self.new_lbl(), self.new_lbl()
        self.current_func.add(Label(l_start))
        self.current_func.add(CondJump(self.gen_expr(node.condition), l_body))
        self.current_func.add(Jump(l_end))
        self.current_func.add(Label(l_body))
        self.gen_block(node.body)
        self.current_func.add(Jump(l_start))
        self.current_func.add(Label(l_end))

    def gen_expr(self, node):
        if isinstance(node, Literal): return Const(node.value)
        if isinstance(node, Identifier): return Var(node.name)
        if isinstance(node, BinaryOp):
            l, r = self.gen_expr(node.left), self.gen_expr(node.right)
            dst = Temp()
            self.current_func.add(AssignOp(dst, node.op, l, r))
            return dst
        if isinstance(node, UnaryOp) and node.op == '-':
            dst = Temp()
            self.current_func.add(AssignOp(dst, '-', Const(0), self.gen_expr(node.operand)))
            return dst
        if isinstance(node, CallExpr):
            dst = Temp()
            self.current_func.add(Call(dst, node.name, [self.gen_expr(a) for a in node.args]))
            return dst
        return Var("_")

class BasicBlock:
    def __init__(self, id, instrs): self.id, self.instrs, self.succs = id, instrs, []

def build_cfg(instrs):
    blocks, cur = [], []
    for i in instrs:
        cur.append(i)
        if isinstance(i, (Label, Jump, CondJump, Return)):
            blocks.append(BasicBlock(len(blocks), cur))
            cur = []
    if cur: blocks.append(BasicBlock(len(blocks), cur))
    
    for i, b in enumerate(blocks):
        last = b.instrs[-1]
        if isinstance(last, Return): pass
        elif isinstance(last, Jump):
            b.succs = [j for j, blk in enumerate(blocks) if blk.instrs and isinstance(blk.instrs[0], Label) and blk.instrs[0].n == last.target]
        elif isinstance(last, CondJump):
            b.succs = [i+1] if i+1 < len(blocks) else []
            b.succs += [j for j, blk in enumerate(blocks) if blk.instrs and isinstance(blk.instrs[0], Label) and blk.instrs[0].n == last.target]
        else:
            if i+1 < len(blocks): b.succs.append(i+1)
    return blocks

def cfg_to_dot(blocks, fname):
    lines = [f"digraph CFG_{fname} {{"]
    for b in blocks:
        txt = "\\n".join([str(i).replace('"', "'") for i in b.instrs])
        lines.append(f'  B{b.id} [label="B{b.id}\\n{txt}", shape=box];')
        for s in b.succs: lines.append(f"  B{b.id} -> B{s};")
    lines.append("}")
    return "\n".join(lines)

class OptFlags:
    """Флаги включения/отключения оптимизаций."""
    def __init__(self, const_prop=True, algebraic=True, cse=True, dce=True):
        self.const_prop = const_prop
        self.algebraic = algebraic
        self.cse = cse
        self.dce = dce
    
    def __str__(self):
        return (f"const_prop={self.const_prop}, algebraic={self.algebraic}, "
                f"cse={self.cse}, dce={self.dce}")

def optimize(func: IRFunc, flags: OptFlags = None):
    if flags is None:
        flags = OptFlags()  # все включены по умолчанию
    
    # Разбиваем на блоки
    blocks, cur = [], []
    for i in func.instrs:
        cur.append(i)
        if isinstance(i, (Label, Jump, CondJump, Return)):
            blocks.append(cur); cur = []
    if cur: blocks.append(cur)

    new_blocks = []
    for block in blocks:
        const_map = {}
        opt_b = []
        
        # === ПРОХОД 1: Const Prop + Folding + Algebraic ===
        for instr in block:
            if isinstance(instr, AssignOp):
                # Constant Propagation
                if flags.const_prop:
                    if isinstance(instr.l, (Var, Temp)) and instr.l.n in const_map: 
                        instr.l = Const(const_map[instr.l.n])
                    if isinstance(instr.r, (Var, Temp)) and instr.r.n in const_map: 
                        instr.r = Const(const_map[instr.r.n])
                
                # Constant Folding
                if flags.const_prop and isinstance(instr.l, Const) and isinstance(instr.r, Const):
                    try: 
                        res = int(eval(f"{instr.l.v} {instr.op} {instr.r.v}"))
                        instr = AssignVar(instr.dst, Const(res))
                        const_map[instr.dst.n] = res
                    except: pass
                
                # Algebraic Simplification
                if flags.algebraic and isinstance(instr, AssignOp):
                    if instr.op == '+' and isinstance(instr.r, Const) and instr.r.v == 0: 
                        instr = AssignVar(instr.dst, instr.l)
                    elif instr.op == '*' and isinstance(instr.r, Const) and instr.r.v == 1: 
                        instr = AssignVar(instr.dst, instr.l)
                    elif instr.op == '*' and isinstance(instr.r, Const) and instr.r.v == 0: 
                        instr = AssignVar(instr.dst, Const(0))
                        if flags.const_prop:
                            const_map[instr.dst.n] = 0
            
            if flags.const_prop and isinstance(instr, AssignVar) and isinstance(instr.src, Const):
                const_map[instr.dst.n] = instr.src.v
                
            opt_b.append(instr)

        # === ПРОХОД 2: CSE ===
        cse_b = opt_b
        if flags.cse:
            available = {}
            cse_b = []
            for instr in opt_b:
                if isinstance(instr, (AssignVar, AssignOp)):
                    var_name = instr.dst.n
                    keys_to_delete = []
                    for key, temp in available.items():
                        op, l, r = key
                        if (isinstance(l, (Var, Temp)) and l.n == var_name) or \
                           (isinstance(r, (Var, Temp)) and r.n == var_name):
                            keys_to_delete.append(key)
                    for k in keys_to_delete:
                        del available[k]
                
                if isinstance(instr, AssignOp):
                    key = (instr.op, instr.l, instr.r)
                    if key in available:
                        instr = AssignVar(instr.dst, available[key])
                    else:
                        available[key] = instr.dst
                
                cse_b.append(instr)

        new_blocks.append(cse_b)

    # Пересчёт all_used
    all_used = set()
    for block in new_blocks:
        for instr in block:
            if isinstance(instr, AssignVar) and isinstance(instr.src, (Var, Temp)):
                all_used.add(instr.src.n)
            elif isinstance(instr, AssignOp):
                if isinstance(instr.l, (Var, Temp)): all_used.add(instr.l.n)
                if isinstance(instr.r, (Var, Temp)): all_used.add(instr.r.n)
            elif isinstance(instr, CondJump) and isinstance(instr.cond, (Var, Temp)):
                all_used.add(instr.cond.n)
            elif isinstance(instr, Return) and instr.v and isinstance(instr.v, (Var, Temp)):
                all_used.add(instr.v.n)
            elif isinstance(instr, Call):
                for arg in instr.args:
                    if isinstance(arg, (Var, Temp)): all_used.add(arg.n)

    # === ПРОХОД 3: DCE ===
    final_instrs = []
    for block in new_blocks:
        if flags.dce:
            used = set()
            final_b = []
            for instr in reversed(block):
                is_dead = False
                if isinstance(instr, (AssignVar, AssignOp)):
                    if instr.dst.n not in used and instr.dst.n not in func.return_vars and instr.dst.n not in all_used:
                        is_dead = True
                
                if not is_dead:
                    final_b.append(instr)
                    if isinstance(instr, AssignVar) and isinstance(instr.src, (Var, Temp)): 
                        used.add(instr.src.n)
                    elif isinstance(instr, AssignOp):
                        if isinstance(instr.l, (Var, Temp)): used.add(instr.l.n)
                        if isinstance(instr.r, (Var, Temp)): used.add(instr.r.n)
                    elif isinstance(instr, CondJump) and isinstance(instr.cond, (Var, Temp)):
                        used.add(instr.cond.n)
                    elif isinstance(instr, Return) and instr.v and isinstance(instr.v, (Var, Temp)):
                        used.add(instr.v.n)
            final_instrs.extend(reversed(final_b))
        else:
            final_instrs.extend(block)
    
    func.instrs = final_instrs

def analyze_and_color(func: IRFunc):
    n = len(func.instrs)
    use, defs = [set() for _ in range(n)], [set() for _ in range(n)]
    
    for i, instr in enumerate(func.instrs):
        if isinstance(instr, (AssignVar, AssignOp)): defs[i].add(instr.dst.n)
        if isinstance(instr, AssignVar) and isinstance(instr.src, (Var, Temp)): use[i].add(instr.src.n)
        if isinstance(instr, AssignOp):
            if isinstance(instr.l, (Var, Temp)): use[i].add(instr.l.n)
            if isinstance(instr.r, (Var, Temp)): use[i].add(instr.r.n)
        if isinstance(instr, CondJump) and isinstance(instr.cond, (Var, Temp)): use[i].add(instr.cond.n)
        if isinstance(instr, Return) and instr.v and isinstance(instr.v, (Var, Temp)): use[i].add(instr.v.n)

    def get_succs(i):
        succs = []
        instr = func.instrs[i]
        if not isinstance(instr, (Jump, CondJump, Return)) and i+1 < n: succs.append(i+1)
        if isinstance(instr, (Jump, CondJump)):
            succs += [j for j, blk in enumerate(func.instrs) if isinstance(blk, Label) and blk.n == instr.target]
        return succs

    live_in, live_out = [set() for _ in range(n)], [set() for _ in range(n)]
    changed = True
    while changed:
        changed = False
        for i in range(n-1, -1, -1):
            new_out = set().union(*(live_in[s] for s in get_succs(i)))
            new_in = use[i].union(new_out - defs[i])
            if new_in != live_in[i] or new_out != live_out[i]:
                live_in[i], live_out[i] = new_in, new_out
                changed = True

    temps = {item for i in range(n) for item in live_out[i] if item.startswith('t')}
    graph = {t: set() for t in temps}
    for i in range(n):
        lst = list(live_out[i])
        for j in range(len(lst)):
            for k in range(j+1, len(lst)):
                if lst[j] in graph and lst[k] in graph:
                    graph[lst[j]].add(lst[k]); graph[lst[k]].add(lst[j])

    colors = {}
    for t in sorted(temps, key=lambda x: len(graph[x]), reverse=True):
        neighbor_colors = {colors[nb] for nb in graph[t] if nb in colors}
        c = 0
        while c in neighbor_colors: c += 1
        colors[t] = c
    return colors, graph

def interpret(func: IRFunc, env: dict, all_funcs: dict = None):
    if all_funcs is None:
        all_funcs = {func.name: func}
    
    pc = 0
    while pc < len(func.instrs):
        instr = func.instrs[pc]
        if isinstance(instr, AssignVar):
            env[instr.dst.n] = instr.src.v if isinstance(instr.src, Const) else env.get(instr.src.n, 0)
            pc += 1
        elif isinstance(instr, AssignOp):
            l = instr.l.v if isinstance(instr.l, Const) else env.get(instr.l.n, 0)
            r = instr.r.v if isinstance(instr.r, Const) else env.get(instr.r.n, 0)
            env[instr.dst.n] = int(eval(f"{l} {instr.op} {r}"))
            pc += 1
        elif isinstance(instr, Label): 
            pc += 1
        elif isinstance(instr, Jump):
            pc = next(j for j, i in enumerate(func.instrs) if isinstance(i, Label) and i.n == instr.target)
        elif isinstance(instr, CondJump):
            cond = instr.cond.v if isinstance(instr.cond, Const) else env.get(instr.cond.n, 0)
            pc = next(j for j, i in enumerate(func.instrs) if isinstance(i, Label) and i.n == instr.target) if cond else pc + 1
        elif isinstance(instr, Call):
            called_func = all_funcs.get(instr.name)
            if called_func:
                call_env = {}
                for i, param in enumerate(called_func.params):
                    arg_val = instr.args[i].v if isinstance(instr.args[i], Const) else env.get(instr.args[i].n, 0)
                    call_env[param] = arg_val
                result = interpret(called_func, call_env, all_funcs)
                env[instr.dst.n] = result if result is not None else 0
            else:
                env[instr.dst.n] = 0
            pc += 1
        elif isinstance(instr, Return):
            return instr.v.v if instr.v and isinstance(instr.v, Const) else env.get(instr.v.n, 0) if instr.v else None
        else: 
            pc += 1
    
    if func.return_vars and len(func.return_vars) == 1:
        return env.get(func.return_vars[0], None)
    return None