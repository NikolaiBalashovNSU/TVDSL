import json
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from lexer_generator import run_lexer
except ImportError as e:
    raise ImportError(f"Не удалось импортировать run_lexer из lexer_generator: {e}")

def tokenize_with_hw1(code):
    table_path = os.path.join(current_dir, 'dfa_table.json')
    if not os.path.exists(table_path):
        raise FileNotFoundError(
            f"Файл {table_path} не найден! Сначала запусти генератор лексера: "
            "python3 HW2_parsing/lexer_generator.py"
        )
    
    with open(table_path, 'r', encoding='utf-8') as f:
        dfa_json = json.load(f)
        
    raw_tokens = run_lexer(dfa_json, code)

    tokens = []
    line, column, pos = 1, 1, 0
    for t_type, value in raw_tokens:
        if t_type == "ERROR":
            tokens.append((t_type, value, line, column))
            continue
            
        idx = code.find(value, pos)
        if idx != -1:
            for i in range(pos, idx):
                if code[i] == '\n':
                    line += 1
                    column = 1
                else:
                    column += 1
            pos = idx
        
        start_line, start_col = line, column
        for char in value:
            if char == '\n':
                line += 1
                column = 1
            else:
                column += 1
        pos += len(value)
        
        tokens.append((t_type, value, start_line, start_col))
    return tokens


class ASTNode:
    def to_dict(self):
        res = {"node_type": self.__class__.__name__}
        for k, v in self.__dict__.items():
            if isinstance(v, ASTNode):
                res[k] = v.to_dict()
            elif isinstance(v, list):
                res[k] = [item.to_dict() if isinstance(item, ASTNode) else item for item in v]
            else:
                res[k] = v
        return res

class Program(ASTNode):
    def __init__(self, declarations):
        self.declarations = declarations
        self.functions = declarations

class FunctionDef(ASTNode):
    def __init__(self, name, params, return_type, requires, ensures, uses, body):
        self.name = name
        self.params = params
        self.return_type = return_type
        self.requires = requires
        self.ensures = ensures
        self.uses = uses
        self.body = body

class FormulaNode(ASTNode):
    def __init__(self, name, params, predicate):
        self.name = name
        self.params = params
        self.predicate = predicate

class Literal(ASTNode):
    def __init__(self, value):
        self.value = value

class Identifier(ASTNode):
    def __init__(self, name):
        self.name = name

class BinaryOp(ASTNode):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

class UnaryOp(ASTNode):
    def __init__(self, op, operand):
        self.op = op
        self.operand = operand

class ArrayAccess(ASTNode):
    def __init__(self, array, index):
        self.array = array
        self.index = index

class CallExpr(ASTNode):
    def __init__(self, name, args):
        self.name = name
        self.args = args

class QuantifierNode(ASTNode):
    def __init__(self, quantifier_type, var_name, var_type, predicate):
        self.quantifier_type = quantifier_type
        self.var_name = var_name
        self.var_type = var_type
        self.predicate = predicate

class Block(ASTNode):
    def __init__(self, statements):
        self.statements = statements

class Assign(ASTNode):
    def __init__(self, name, index, value):
        self.name = name
        self.index = index
        self.value = value

class TupleAssign(ASTNode):
    def __init__(self, targets, call_expr):
        self.targets = targets
        self.call_expr = call_expr

class IfStatement(ASTNode):
    def __init__(self, condition, then_branch, else_branch):
        self.condition = condition
        self.then_branch = then_branch
        self.else_branch = else_branch

class WhileStatement(ASTNode):
    def __init__(self, condition, invariant, body):
        self.condition = condition
        self.invariant = invariant
        self.body = body

class AssertStatement(ASTNode):
    def __init__(self, condition):
        self.condition = condition

class AssumeStatement(ASTNode):
    def __init__(self, condition):
        self.condition = condition

class ReturnStatement(ASTNode):
    def __init__(self, expr):
        self.expr = expr

class ParserError(Exception):
    def __init__(self, message, line, column):
        super().__init__(f"Syntax Error at line {line}, col {column}: {message}")
        self.message = message
        self.line = line
        self.column = column

class Parser:
    STMT_SYNC = {'SEMICOLON', 'RBRACE', 'KW_IF', 'KW_WHILE', 'KW_ASSERT', 'KW_ASSUME', 'KW_FUNCTION'}
    DECL_SYNC = {'KW_FUNCTION', 'IDENT'}

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.errors = []

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected_type=None, expected_val=None):
        token = self.peek()
        if token is None:
            raise ParserError("Неожиданный конец файла (EOF)", -1, -1)
        
        t_type, t_val, t_line, t_col = token[0], token[1], token[2], token[3]

        if expected_type and t_type != expected_type:
            if expected_type == 'RPAREN':
                msg = "Ожидалась ')'"
            elif expected_type == 'SEMICOLON':
                msg = "Ожидалась ';'"
            else:
                msg = f"Ожидался токен {expected_type}, но получен {t_type} ('{t_val}')"
            raise ParserError(msg, t_line, t_col)

        if expected_val and t_val != expected_val:
            raise ParserError(f"Ожидалось '{expected_val}', но получено '{t_val}'", t_line, t_col)

        self.pos += 1
        return token

    def parse_program_with_recovery(self):
        declarations = []
        token = self.peek()
        if not token:
            return Program([]), [ParserError("Исходный код пуст", 1, 1)]

        while self.peek() is not None:
            t = self.peek()
            if t[0] == 'ERROR':
                self.errors.append(ParserError(t[1], t[2], t[3]))
                self.pos += 1
                continue

            try:
                if t[0] == 'KW_FUNCTION':
                    declarations.append(self.parse_function())
                elif t[0] == 'IDENT':
                    if self.is_formula_ahead():
                        declarations.append(self.parse_formula())
                    else:
                        raise ParserError(f"Неожиданный токен на верхнем уровне: {t[1]}", t[2], t[3])
                else:
                    raise ParserError(f"Неожиданный токен на верхнем уровне: {t[1]}", t[2], t[3])
            except ParserError as e:
                self.errors.append(e)
                self.panic_synchronize(self.DECL_SYNC)
        return Program(declarations), self.errors

    def is_formula_ahead(self):
        saved = self.pos
        try:
            if self.peek() and self.peek()[0] == 'IDENT':
                self.pos += 1
                if self.peek() and self.peek()[0] == 'LPAREN':
                    depth = 1
                    self.pos += 1
                    while self.pos < len(self.tokens) and depth > 0:
                        if self.tokens[self.pos][0] == 'LPAREN':
                            depth += 1
                        elif self.tokens[self.pos][0] == 'RPAREN':
                            depth -= 1
                        self.pos += 1
                    if self.peek() and self.peek()[0] == 'OP_ARROW_DOUBLE':
                        self.pos = saved
                        return True
        except Exception:
            pass
        self.pos = saved
        return False

    def panic_synchronize(self, sync_set):
        self.pos += 1
        while self.peek() is not None:
            t = self.peek()
            if t[0] in sync_set or t[1] in sync_set:
                if t[0] == 'SEMICOLON':
                    self.pos += 1
                return
            self.pos += 1

    def parse_variable_type(self):
        t = self.consume()
        type_str = t[1]
        if self.peek() and self.peek()[0] == 'LBRACKET':
            self.consume('LBRACKET')
            self.consume('RBRACKET')
            type_str += "[]"
        return type_str

    def parse_variable_def(self):
        v_name = self.consume('IDENT')[1]
        v_type = None
        if self.peek() and self.peek()[0] == 'COLON':
            self.consume('COLON')
            v_type = self.parse_variable_type()
        return (v_name, v_type)

    def parse_function(self):
        self.consume('KW_FUNCTION')
        name_token = self.consume('IDENT')
        
        self.consume('LPAREN')
        params = []
        if self.peek() and self.peek()[0] != 'RPAREN':
            while True:
                params.append(self.parse_variable_def())
                if self.peek() and self.peek()[0] == 'COMMA':
                    self.consume('COMMA')
                else:
                    break
        self.consume('RPAREN')
        
        requires = None
        if self.peek() and self.peek()[0] == 'KW_REQUIRES':
            self.consume('KW_REQUIRES')
            requires = self.parse_condition()

        return_type = None
        returns_defs = []
        if self.peek() and self.peek()[0] == 'KW_RETURNS':
            self.consume('KW_RETURNS')
            while True:
                returns_defs.append(self.parse_variable_def())
                if self.peek() and self.peek()[0] == 'COMMA':
                    self.consume('COMMA')
                else:
                    break

        ensures = None
        if self.peek() and self.peek()[0] == 'KW_ENSURES':
            self.consume('KW_ENSURES')
            ensures = self.parse_condition()

        uses = []
        if self.peek() and self.peek()[0] == 'KW_USES':
            self.consume('KW_USES')
            while True:
                uses.append(self.parse_variable_def())
                if self.peek() and self.peek()[0] == 'COMMA':
                    self.consume('COMMA')
                else:
                    break

        body = self.parse_block()
        return FunctionDef(name_token[1], params, returns_defs or return_type, requires, ensures, uses, body)

    def parse_formula(self):
        name = self.consume('IDENT')[1]
        self.consume('LPAREN')
        params = []
        if self.peek() and self.peek()[0] != 'RPAREN':
            while True:
                params.append(self.parse_variable_def())
                if self.peek() and self.peek()[0] == 'COMMA':
                    self.consume('COMMA')
                else:
                    break
        self.consume('RPAREN')
        self.consume('OP_ARROW_DOUBLE')
        predicate = self.parse_condition()
        if self.peek() and self.peek()[0] == 'SEMICOLON':
            self.consume('SEMICOLON')
        return FormulaNode(name, params, predicate)

    def parse_block(self):
        self.consume('LBRACE')
        statements = []
        while self.peek() and self.peek()[0] != 'RBRACE':
            try:
                statements.append(self.parse_statement())
            except ParserError as e:
                self.errors.append(e)
                self.panic_synchronize(self.STMT_SYNC)
        self.consume('RBRACE')
        return Block(statements)

    def parse_statement(self):
        token = self.peek()
        if not token:
            raise ParserError("Ожидалась инструкция", -1, -1)

        t_type = token[0]
        if t_type == 'KW_IF':
            return self.parse_if()
        elif t_type == 'KW_WHILE':
            return self.parse_while()
        elif t_type == 'KW_ASSERT':
            return self.parse_assert()
        elif t_type == 'KW_ASSUME':
            return self.parse_assume()
        elif t_type == 'KW_RETURN':
            return self.parse_return()
        else:
            return self.parse_assign_or_expr()

    def parse_if(self):
        self.consume('KW_IF')
        self.consume('LPAREN')
        condition = self.parse_condition()
        self.consume('RPAREN')
        then_branch = self.parse_block()
        
        else_branch = None
        if self.peek() and self.peek()[0] == 'KW_ELSE':
            self.consume('KW_ELSE')
            if self.peek() and self.peek()[0] == 'KW_IF':
                else_branch = self.parse_if()
            else:
                else_branch = self.parse_block()
        return IfStatement(condition, then_branch, else_branch)

    def parse_while(self):
        self.consume('KW_WHILE')
        self.consume('LPAREN')
        condition = self.parse_condition()
        self.consume('RPAREN')
        
        invariant = None
        if self.peek() and self.peek()[0] == 'KW_INVARIANT':
            self.consume('KW_INVARIANT')
            invariant = self.parse_condition()

        body = self.parse_block()
        return WhileStatement(condition, invariant, body)

    def parse_assert(self):
        self.consume('KW_ASSERT')
        expr = self.parse_condition()
        if self.peek() and self.peek()[0] == 'SEMICOLON':
            self.consume('SEMICOLON')
        else:
            t = self.peek()
            raise ParserError("Ожидалась ';'", t[2] if t else -1, t[3] if t else -1)
        return AssertStatement(expr)

    def parse_assume(self):
        self.consume('KW_ASSUME')
        expr = self.parse_condition()
        if self.peek() and self.peek()[0] == 'SEMICOLON':
            self.consume('SEMICOLON')
        else:
            t = self.peek()
            raise ParserError("Ожидалась ';'", t[2] if t else -1, t[3] if t else -1)
        return AssumeStatement(expr)

    def parse_return(self):
        self.consume('KW_RETURN')
        expr = None
        if self.peek() and self.peek()[0] not in ('SEMICOLON', 'RBRACE'):
            expr = self.parse_expr()
        if self.peek() and self.peek()[0] == 'SEMICOLON':
            self.consume('SEMICOLON')
        return ReturnStatement(expr)

    def parse_assign_or_expr(self):
        saved_pos = self.pos
        token = self.peek()
        t_line, t_col = token[2], token[3]

        try:
            expr = self.parse_expr()
            
            if isinstance(expr, Identifier) and self.peek() and self.peek()[0] == 'COMMA':
                targets = [expr.name]
                while self.peek() and self.peek()[0] == 'COMMA':
                    self.consume('COMMA')
                    targets.append(self.consume('IDENT')[1])
                self.consume('ASSIGN')
                call_expr = self.parse_expr()
                if self.peek() and self.peek()[0] == 'SEMICOLON':
                    self.consume('SEMICOLON')
                return TupleAssign(targets, call_expr)

            if self.peek() and self.peek()[0] == 'ASSIGN':
                self.consume('ASSIGN')
                value_expr = self.parse_expr()
                if self.peek() and self.peek()[0] == 'SEMICOLON':
                    self.consume('SEMICOLON')
                else:
                    t = self.peek()
                    raise ParserError("Ожидалась ';'", t[2] if t else t_line, t[3] if t else t_col)
                    
                if isinstance(expr, Identifier):
                    return Assign(name=expr.name, index=None, value=value_expr)
                elif isinstance(expr, ArrayAccess):
                    if isinstance(expr.array, Identifier):
                        functional_update = CallExpr(
                            name="__array_update__",
                            args=[expr.array, expr.index, value_expr]
                        )
                        return Assign(name=expr.array.name, index=None, value=functional_update)
                    else:
                        raise ParserError("Слева от '=' должен быть идентификатор или элемент массива", t_line, t_col)
                else:
                    raise ParserError("Недопустимая левая часть для присваивания", t_line, t_col)
            else:
                if self.peek() and self.peek()[0] == 'SEMICOLON':
                    self.consume('SEMICOLON')
                return expr
        except ParserError:
            self.pos = saved_pos
            raise

    def parse_condition(self):
        token = self.peek()
        if token and token[0] == 'IDENT' and token[1] in ('forall', 'exists'):
            q_type = self.consume()[1]
            self.consume('LPAREN')
            var_name, var_type = self.parse_variable_def()
            self.consume('PIPE')
            pred = self.parse_condition()
            self.consume('RPAREN')
            return QuantifierNode(q_type, var_name, var_type, pred)
        return self.parse_implication()

    def parse_implication(self):
        node = self.parse_or()
        if self.peek() and self.peek()[0] == 'OP_ARROW_SINGLE':
            op_token = self.consume()
            right = self.parse_implication()
            node = BinaryOp(node, op_token[1], right)
        return node

    def parse_or(self):
        node = self.parse_and()
        while self.peek() and self.peek()[0] == 'IDENT' and self.peek()[1] == 'or':
            op_token = self.consume()
            right = self.parse_and()
            node = BinaryOp(node, op_token[1], right)
        return node

    def parse_and(self):
        node = self.parse_not()
        while self.peek() and self.peek()[0] == 'IDENT' and self.peek()[1] == 'and':
            op_token = self.consume()
            right = self.parse_not()
            node = BinaryOp(node, op_token[1], right)
        return node

    def parse_not(self):
        if self.peek() and self.peek()[0] == 'IDENT' and self.peek()[1] == 'not':
            op_token = self.consume()
            operand = self.parse_not()
            return UnaryOp(op_token[1], operand)
        return self.parse_equality()

    def parse_expr(self):
        return self.parse_condition()

    def parse_equality(self):
        node = self.parse_additive()
        while self.peek() and self.peek()[0] in ('OP_EQ', 'OP_NEQ', 'OP_LT', 'OP_GT', 'OP_LE', 'OP_GE'):
            op_token = self.consume()
            right = self.parse_additive()
            node = BinaryOp(node, op_token[1], right)
        return node

    def parse_additive(self):
        node = self.parse_multiplicative()
        while self.peek() and self.peek()[0] in ('OP_ADD', 'OP_SUB'):
            op_token = self.consume()
            right = self.parse_multiplicative()
            node = BinaryOp(node, op_token[1], right)
        return node

    def parse_multiplicative(self):
        node = self.parse_unary()
        while self.peek() and self.peek()[0] in ('OP_MUL', 'OP_DIV'):
            op_token = self.consume()
            right = self.parse_unary()
            node = BinaryOp(node, op_token[1], right)
        return node

    def parse_unary(self):
        if self.peek() and self.peek()[0] in ('OP_SUB', 'PIPE'):
            op_token = self.consume()
            operand = self.parse_unary()
            return UnaryOp(op_token[1], operand)
        return self.parse_postfix()

    def parse_postfix(self):
        node = self.parse_primary()
        while True:
            token = self.peek()
            if not token:
                break
            
            t_type, t_line, t_col = token[0], token[2], token[3]

            if t_type == 'LPAREN':
                self.consume('LPAREN')
                args = []
                if self.peek() and self.peek()[0] != 'RPAREN':
                    args.append(self.parse_condition())
                    while self.peek() and self.peek()[0] == 'COMMA':
                        self.consume('COMMA')
                        args.append(self.parse_condition())
                self.consume('RPAREN')
                
                if isinstance(node, Identifier):
                    node = CallExpr(node.name, args)
                else:
                    raise ParserError("Ожидалось имя функции для вызова", t_line, t_col)
            
            elif t_type == 'LBRACKET':
                self.consume('LBRACKET')
                index_expr = self.parse_condition()
                self.consume('RBRACKET')
                node = ArrayAccess(node, index_expr)
            else:
                break
        return node

    def parse_primary(self):
        token = self.peek()
        if not token:
            raise ParserError("Неожиданный конец файла при разборе выражения", -1, -1)
        
        t_type, t_val, t_line, t_col = token[0], token[1], token[2], token[3]

        if t_type == 'INT':
            self.consume('INT')
            return Literal(int(t_val))
        elif t_type == 'IDENT' or t_type == 'KW_LENGTH':
            self.consume()
            return Identifier(t_val)
        elif t_type == 'LPAREN':
            self.consume('LPAREN')
            expr = self.parse_condition()
            self.consume('RPAREN')
            return expr
        elif t_type == 'KW_TRUE':
            self.consume('KW_TRUE')
            return Literal(True)
        elif t_type == 'KW_FALSE':
            self.consume('KW_FALSE')
            return Literal(False)
        else:
            raise ParserError(f"Неожиданный токен в выражении: {t_type} ('{t_val}')", t_line, t_col)


def parse_source(code):
    if not code or not code.strip():
        return Program([]), [ParserError("Исходный код пуст", 1, 1)]
    try:
        tokens = tokenize_with_hw1(code)
    except Exception as e:
        return Program([]), [ParserError(str(e), 1, 1)]
    
    parser = Parser(tokens)
    return parser.parse_program_with_recovery()

if __name__ == "__main__":
    print("\n[+] Тест 0: Проверка десахаризации обновления массива (функциональное копирование)")
    code_arr = """
    function test_arr(a: int[]) returns out: int[] {
        a[0] = 42;
        out = a;
    }
    """
    ast, errs = parse_source(code_arr)
    assert len(errs) == 0, f"Ошибки не ожидались: {errs}"
    
    stmt = ast.declarations[0].body.statements[0]
    print(f"Тип узла присваивания: {type(stmt).__name__}")
    print(f"Имя переменной: {stmt.name}")
    print(f"Правая часть (вызов): {stmt.value.name}({[arg.value if isinstance(arg, Literal) else arg.name for arg in stmt.value.args]})")
    print("[OK] Обновление массива успешно десахаризовано в чистую функциональную форму!")
    print("\n[+] Тест 1: Позитивный (цикл с инвариантом)")
    code1 = """
    function sum_to_n(n: int) returns total: int
    uses i: int
    {
        total = 0;
        i = 0;
        while (i < n) invariant i >= 0 and total >= 0 {
            total = total + i;
            i = i + 1;
        }
        assert total >= 0;
    }
    """
    try:
        ast, errs = parse_source(code1)
        assert len(errs) == 0, f"Ошибки не ожидались: {errs}"
        print("[OK] Разбор цикла с инвариантом прошел успешно!")
        print("Пример AST в JSON:", json.dumps(ast.to_dict(), indent=2, ensure_ascii=False)[:300], "...")
    except Exception as e:
        print(f"[-] Ошибка: {e}")

    print("\n[+] Тест 2: Позитивный (массивы и контракты)")
    code2 = """
    function update_array(a: int[], pos: int, val: int)
        requires pos >= 0 and pos < length(a)
        returns out: int[]
        ensures out[pos] == val
    {
        a[pos] = val;
        out = a;
    }
    """
    try:
        ast, errs = parse_source(code2)
        assert len(errs) == 0, f"Ошибки не ожидались: {errs}"
        print("[OK] Разбор массивов и контрактов прошел успешно!")
    except Exception as e:
        print(f"[-] Ошибка: {e}")

    print("\n[+] Тест 3: Позитивный (формулы и кванторы)")
    code3 = """
    is_valid(n: int) => n >= 0;

    function verify_elements(data: int[]) returns result: int {
        assert exists(k: int | k >= 0 and data[k] == 0);
        result = 1;
    }
    """
    try:
        ast, errs = parse_source(code3)
        assert len(errs) == 0, f"Ошибки не ожидались: {errs}"
        print("[OK] Разбор формул и кванторов прошел успешно!")
    except Exception as e:
        print(f"[-] Ошибка: {e}")

    print("\n[+] Тест 4: Негативный (незакрытая скобка)")
    code4 = "function compute_val(a: int returns res: int { res = a; }"
    try:
        ast, errs = parse_source(code4)
        assert len(errs) > 0, "Ожидалась синтаксическая ошибка"
        print(f"[OK] Ошибка успешно перехвачена: {errs[0].message}")
    except Exception as e:
        print(f"[-] Ошибка: {e}")

    print("\n[+] Тест 5: Негативный (пропущенная точка с запятой)")
    code5 = """
    function get_val() returns v: int {
        v = 100
        assert v == 100;
    }
    """
    try:
        ast, errs = parse_source(code5)
        assert len(errs) > 0, "Ожидалась ошибка отсутствия точки с запятой"
        print(f"[OK] Ошибка успешно перехвачена: {errs[0].message}")
    except Exception as e:
        print(f"[-] Ошибка: {e}")

    print("\n[+] Тест 6: Негативный (пустой ввод)")
    code6 = "   "
    try:
        ast, errs = parse_source(code6)
        assert len(errs) == 1
        print(f"[OK] Ошибка пустого ввода перехвачена: {errs[0].message}")
    except Exception as e:
        print(f"[-] Ошибка: {e}")

    print("\n[+] Тест 7: Режим паники (восстановление после ошибки)")
    code7 = """
    function broken_func(val: int) returns out: int {
        out = #;
        out = 42;
    }
    function correct_func(flag: int) returns status: int {
        if flag > 0 { status = 1; } else { status = 0; }
    }
    """
    try:
        ast, errs = parse_source(code7)
        assert len(errs) >= 1, f"Ожидались ошибки, получено {len(errs)}"
        f_names = [d.name for d in ast.declarations if hasattr(d, "name")]
        assert "correct_func" in f_names, "Парсер должен был восстановиться"
        print(f"[OK] Паника обработана, получено ошибок: {len(errs)}, функции: {f_names}")
    except Exception as e:
        print(f"[-] Ошибка: {e}")

