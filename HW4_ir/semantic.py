import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from parser import (
    parse_source, Program, FunctionDef, FormulaNode, Literal, Identifier,
    BinaryOp, UnaryOp, ArrayAccess, CallExpr, QuantifierNode, Block,
    Assign, TupleAssign, IfStatement, WhileStatement, AssertStatement,
    AssumeStatement, ReturnStatement
)

class Type:
    def __eq__(self, other):
        raise NotImplementedError
    def __str__(self):
        raise NotImplementedError

class BasicType(Type):
    def __init__(self, name):
        self.name = name
    def __eq__(self, other):
        return isinstance(other, BasicType) and self.name == other.name
    def __str__(self):
        return self.name

class ArrayType(Type):
    def __init__(self, element_type):
        self.element_type = element_type
    def __eq__(self, other):
        return isinstance(other, ArrayType) and self.element_type == other.element_type
    def __str__(self):
        return f"{self.element_type}[]"

INT = BasicType("int")
BOOL = BasicType("bool")
VOID = BasicType("void")

def parse_type_str(type_str):
    if not type_str:
        return None
    if type_str == "int":
        return INT
    elif type_str == "bool":
        return BOOL
    elif type_str.endswith("[]"):
        base = type_str[:-2]
        return ArrayType(parse_type_str(base))
    else:
        return BasicType(type_str)

class SemanticError(Exception):
    def __init__(self, message, line=0, column=0):
        super().__init__(f"Semantic Error at line {line}, col {column}: {message}")
        self.message = message
        self.line = line
        self.column = column

class SymbolTable:
    def __init__(self, parent=None):
        self.symbols = {}
        self.parent = parent

    def define(self, name, symbol_type):
        if name in self.symbols:
            return False
        self.symbols[name] = symbol_type
        return True

    def lookup(self, name):
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

class FunctionSymbol:
    def __init__(self, name, params, return_types):
        self.name = name
        self.params = params
        self.return_types = return_types

class SemanticAnalyzer:
    def __init__(self):
        self.globals = {}
        self.errors = []
        self.current_func_returns = None

    def error(self, msg, line=0, col=0):
        self.errors.append(SemanticError(msg, line, col))

    def analyze(self, program: Program):
        for decl in program.declarations:
            if isinstance(decl, FunctionDef):
                params_types = []
                for p_name, p_type_str in decl.params:
                    t = parse_type_str(p_type_str)
                    if t is None:
                        self.error(f"Параметр '{p_name}' не имеет указанного типа", decl.line, decl.col)
                        t = INT
                    params_types.append(t)
                
                return_types = []
                if isinstance(decl.return_type, list):
                    for r_name, r_type_str in decl.return_type:
                        t = parse_type_str(r_type_str)
                        if t is None:
                            self.error(f"Возвращаемое значение '{r_name}' не имеет типа", decl.line, decl.col)
                            t = INT
                        return_types.append(t)
                elif decl.return_type:
                    t = parse_type_str(decl.return_type)
                    if t:
                        return_types.append(t)

                if decl.name in self.globals:
                    self.error(f"Повторное объявление функции '{decl.name}'", decl.line, decl.col)
                else:
                    self.globals[decl.name] = FunctionSymbol(decl.name, params_types, return_types)

            elif isinstance(decl, FormulaNode):
                params_types = []
                for p_name, p_type_str in decl.params:
                    t = parse_type_str(p_type_str) or INT
                    params_types.append(t)
                if decl.name in self.globals:
                    self.error(f"Повторное объявление формулы '{decl.name}'", decl.line, decl.col)
                else:
                    self.globals[decl.name] = FunctionSymbol(decl.name, params_types, [BOOL])

        for decl in program.declarations:
            if isinstance(decl, FunctionDef):
                self.analyze_function(decl)
            elif isinstance(decl, FormulaNode):
                self.analyze_formula(decl)

        return program, self.errors

    def analyze_function(self, func: FunctionDef):
        scope = SymbolTable()
        for p_name, p_type_str in func.params:
            t = parse_type_str(p_type_str) or INT
            if not scope.define(p_name, t):
                self.error(f"Повторное объявление параметра '{p_name}' в функции '{func.name}'", func.line, func.col)

        for u_name, u_type_str in func.uses:
            t = parse_type_str(u_type_str)
            if t is None:
                self.error(f"Переменная в uses '{u_name}' не имеет типа", func.line, func.col)
                t = INT
            if not scope.define(u_name, t):
                self.error(f"Повторное объявление переменной '{u_name}' в uses", func.line, func.col)

        ret_types = []
        if isinstance(func.return_type, list):
            for r_name, r_type_str in func.return_type:
                t = parse_type_str(r_type_str) or INT
                ret_types.append(t)
                if not scope.define(r_name, t):
                    self.error(f"Повторное объявление возвращаемой переменной '{r_name}'", func.line, func.col)
        elif func.return_type:
            t = parse_type_str(func.return_type)
            if t:
                ret_types.append(t)

        self.current_func_returns = ret_types

        if func.requires:
            req_t = self.analyze_expr(func.requires, scope)
            if req_t != BOOL:
                self.error(f"Предусловие (requires) должно иметь тип bool, получен {req_t}", func.requires.line, func.requires.col)

        if func.ensures:
            ens_t = self.analyze_expr(func.ensures, scope)
            if ens_t != BOOL:
                self.error(f"Постусловие (ensures) должно иметь тип bool, получен {ens_t}", func.ensures.line, func.ensures.col)

        self.analyze_block(func.body, scope)

    def analyze_formula(self, formula: FormulaNode):
        scope = SymbolTable()
        for p_name, p_type_str in formula.params:
            t = parse_type_str(p_type_str) or INT
            if not scope.define(p_name, t):
                self.error(f"Повторное объявление параметра '{p_name}' в формуле '{formula.name}'", formula.line, formula.col)
        
        pred_t = self.analyze_expr(formula.predicate, scope)
        if pred_t != BOOL:
            self.error(f"Предикат формулы '{formula.name}' должен иметь тип bool, получен {pred_t}", formula.predicate.line, formula.predicate.col)

    def analyze_block(self, block: Block, parent_scope: SymbolTable):
        scope = SymbolTable(parent_scope)
        for stmt in block.statements:
            self.analyze_statement(stmt, scope)

    def analyze_statement(self, stmt, scope: SymbolTable):
        if isinstance(stmt, IfStatement):
            cond_t = self.analyze_expr(stmt.condition, scope)
            if cond_t != BOOL:
                self.error(f"Условие if должно иметь тип bool, получено {cond_t}", stmt.condition.line, stmt.condition.col)
            self.analyze_block(stmt.then_branch, scope)
            if stmt.else_branch:
                if isinstance(stmt.else_branch, IfStatement):
                    self.analyze_statement(stmt.else_branch, scope)
                elif isinstance(stmt.else_branch, Block):
                    self.analyze_block(stmt.else_branch, scope)

        elif isinstance(stmt, WhileStatement):
            cond_t = self.analyze_expr(stmt.condition, scope)
            if cond_t != BOOL:
                self.error(f"Условие while должно иметь тип bool, получено {cond_t}", stmt.condition.line, stmt.condition.col)
            if stmt.invariant:
                inv_t = self.analyze_expr(stmt.invariant, scope)
                if inv_t != BOOL:
                    self.error(f"Инвариант while должен иметь тип bool, получен {inv_t}", stmt.invariant.line, stmt.invariant.col)
            self.analyze_block(stmt.body, scope)

        elif isinstance(stmt, AssertStatement):
            cond_t = self.analyze_expr(stmt.condition, scope)
            if cond_t != BOOL:
                self.error(f"Утверждение assert должно иметь тип bool, получено {cond_t}", stmt.condition.line, stmt.condition.col)

        elif isinstance(stmt, AssumeStatement):
            cond_t = self.analyze_expr(stmt.condition, scope)
            if cond_t != BOOL:
                self.error(f"Предположение assume должно иметь тип bool, получено {cond_t}", stmt.condition.line, stmt.condition.col)

        elif isinstance(stmt, ReturnStatement):
            if stmt.expr:
                expr_t = self.analyze_expr(stmt.expr, scope)
                if self.current_func_returns and len(self.current_func_returns) == 1:
                    expected = self.current_func_returns[0]
                    if expr_t != expected:
                        self.error(f"Несоответствие типа в return: ожидался {expected}, получен {expr_t}", stmt.line, stmt.col)
            else:
                if self.current_func_returns and len(self.current_func_returns) > 0:
                    self.error("Функция должна возвращать значение", stmt.line, stmt.col)

        elif isinstance(stmt, Assign):
            val_t = self.analyze_expr(stmt.value, scope)
            if val_t == VOID:
                self.error(f"Нельзя присвоить результат функции без возвращаемого значения переменной '{stmt.name}'", stmt.line, stmt.col)
                val_t = INT

            existing_t = scope.lookup(stmt.name)
            if existing_t is not None:
                if val_t != existing_t:
                    self.error(f"Несоответствие типов при присваивании переменной '{stmt.name}': объявлен {existing_t}, присваивается {val_t}", stmt.line, stmt.col)
            else:
                scope.define(stmt.name, val_t)
            stmt.inferred_type = val_t

        elif isinstance(stmt, TupleAssign):
            val_t = self.analyze_expr(stmt.call_expr, scope)
            for target in stmt.targets:
                if scope.lookup(target) is None:
                    scope.define(target, INT)
            stmt.inferred_type = val_t

        else:
            self.analyze_expr(stmt, scope)

    def analyze_expr(self, expr, scope: SymbolTable):
        if isinstance(expr, Literal):
            if isinstance(expr.value, bool):
                expr.inferred_type = BOOL
            else:
                expr.inferred_type = INT
            return expr.inferred_type

        elif isinstance(expr, Identifier):
            t = scope.lookup(expr.name)
            if t is None:
                self.error(f"Использование необъявленной переменной '{expr.name}'", expr.line, expr.col)
                t = INT
            expr.inferred_type = t
            return t

        elif isinstance(expr, BinaryOp):
            left_t = self.analyze_expr(expr.left, scope)
            right_t = self.analyze_expr(expr.right, scope)
            op = expr.op
            if op in ('+', '-', '*', '/'):
                if left_t != INT or right_t != INT:
                    self.error(f"Операция '{op}' применима только к int, получены {left_t} и {right_t}", expr.line, expr.col)
                expr.inferred_type = INT
                return INT
            elif op in ('==', '!='):
                if left_t != right_t:
                    self.error(f"Сравнение '{op}' требует одинаковых типов, получены {left_t} и {right_t}", expr.line, expr.col)
                expr.inferred_type = BOOL
                return BOOL
            elif op in ('<', '>', '<=', '>='):
                if left_t != INT or right_t != INT:
                    self.error(f"Сравнение '{op}' применимо только к int, получены {left_t} и {right_t}", expr.line, expr.col)
                expr.inferred_type = BOOL
                return BOOL
            elif op in ('and', 'or', '->', '=>'):
                if left_t != BOOL or right_t != BOOL:
                    self.error(f"Логическая операция '{op}' требует bool, получены {left_t} и {right_t}", expr.line, expr.col)
                expr.inferred_type = BOOL
                return BOOL
            else:
                expr.inferred_type = INT
                return INT

        elif isinstance(expr, UnaryOp):
            operand_t = self.analyze_expr(expr.operand, scope)
            op = expr.op
            if op == '-':
                if operand_t != INT:
                    self.error(f"Унарный минус требует int, получен {operand_t}", expr.line, expr.col)
                expr.inferred_type = INT
                return INT
            elif op == 'not':
                if operand_t != BOOL:
                    self.error(f"Оператор 'not' требует bool, получен {operand_t}", expr.line, expr.col)
                expr.inferred_type = BOOL
                return BOOL
            elif op == '|':
                expr.inferred_type = INT
                return INT
            else:
                expr.inferred_type = operand_t
                return operand_t

        elif isinstance(expr, ArrayAccess):
            arr_t = self.analyze_expr(expr.array, scope)
            idx_t = self.analyze_expr(expr.index, scope)
            if idx_t != INT:
                self.error(f"Индекс массива должен быть int, получен {idx_t}", expr.line, expr.col)
            if isinstance(arr_t, ArrayType):
                expr.inferred_type = arr_t.element_type
                return arr_t.element_type
            else:
                self.error(f"Попытка индексации не-массива (тип {arr_t})", expr.line, expr.col)
                expr.inferred_type = INT
                return INT

        elif isinstance(expr, CallExpr):
            if expr.name == "__array_update__":
                if len(expr.args) != 3:
                    self.error("Внутренняя ошибка: __array_update__ требует 3 аргумента", expr.line, expr.col)
                    expr.inferred_type = VOID
                    return VOID
                arr_t = self.analyze_expr(expr.args[0], scope)
                idx_t = self.analyze_expr(expr.args[1], scope)
                val_t = self.analyze_expr(expr.args[2], scope)
                if idx_t != INT:
                    self.error(f"Индекс массива должен быть int, получен {idx_t}", expr.line, expr.col)
                if isinstance(arr_t, ArrayType):
                    if val_t != arr_t.element_type:
                        self.error(f"Несоответствие типа при записи в массив: ожидался {arr_t.element_type}, получен {val_t}", expr.line, expr.col)
                else:
                    self.error(f"Обновление по индексу применимо только к массиву, получен {arr_t}", expr.line, expr.col)
                expr.inferred_type = arr_t
                return arr_t

            if expr.name == "length":
                if len(expr.args) != 1:
                    self.error("Функция length требует ровно 1 аргумент", expr.line, expr.col)
                else:
                    arg_t = self.analyze_expr(expr.args[0], scope)
                    if not isinstance(arg_t, ArrayType):
                        self.error(f"Функция length применима только к массиву, получен {arg_t}", expr.line, expr.col)
                expr.inferred_type = INT
                return INT

            func_sym = self.globals.get(expr.name)
            if not func_sym:
                self.error(f"Вызов необъявленной функции '{expr.name}'", expr.line, expr.col)
                expr.inferred_type = INT
                return INT

            if len(expr.args) != len(func_sym.params):
                self.error(f"Функция '{expr.name}' ожидает {len(func_sym.params)} аргументов, передано {len(expr.args)}", expr.line, expr.col)

            for i, arg in enumerate(expr.args):
                arg_t = self.analyze_expr(arg, scope)
                if i < len(func_sym.params):
                    expected_t = func_sym.params[i]
                    if arg_t != expected_t:
                        self.error(f"Несоответствие типа аргумента #{i+1} функции '{expr.name}': ожидался {expected_t}, получен {arg_t}", arg.line, arg.col)

            if len(func_sym.return_types) == 1:
                res_t = func_sym.return_types[0]
                expr.inferred_type = res_t
                return res_t
            elif len(func_sym.return_types) > 1:
                expr.inferred_type = func_sym.return_types
                return func_sym.return_types[0]
            else:
                expr.inferred_type = VOID
                return VOID

        elif isinstance(expr, QuantifierNode):
            q_scope = SymbolTable(scope)
            var_t = parse_type_str(expr.var_type) if expr.var_type else INT
            q_scope.define(expr.var_name, var_t)
            pred_t = self.analyze_expr(expr.predicate, q_scope)
            if pred_t != BOOL:
                self.error(f"Тело квантора '{expr.quantifier_type}' должно иметь тип bool, получено {pred_t}", expr.line, expr.col)
            expr.inferred_type = BOOL
            return BOOL

        return INT

def analyze_source(code):
    program, parse_errors = parse_source(code)
    if parse_errors:
        return program, parse_errors
    analyzer = SemanticAnalyzer()
    return analyzer.analyze(program)