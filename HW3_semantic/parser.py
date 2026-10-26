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
    def __init__(self, line=0, col=0):
        self.line = line
        self.col = col
        self.inffered_type = None

    def to_dict(self):
        res = {"node_type": self.__class__.__name__, "line": self.line, "col": self.col}
        if hasattr(self, 'inffered_type') and self.inffered_type is not None:
            res["infered_type"] = str(self.inferred_type)
        for k, v in self.__dict__.items():
            if k in ("line", "col", "inferred_type"):
                continue
            if isinstance(v, ASTNode):
                res[k] = v.to_dict()
            elif isinstance(v, list):
                res[k] = [item.to_dict() if isinstance(item, ASTNode) else item for item in v]
            else:
                res[k] = v
        return res

class Program(ASTNode):
    def __init__(self, declarations, line=0, col=0):
        super().__init__(line, col)
        self.declarations = declarations
        self.functions = declarations

class FunctionDef(ASTNode):
    def __init__(self, name, params, return_type, requires, ensures, uses, body, line=0, col=0):
        super().__init__(line, col)
        self.name = name
        self.params = params
        self.return_type = return_type
        self.requires = requires
        self.ensures = ensures
        self.uses = uses
        self.body = body

class FormulaNode(ASTNode):
    def __init__(self, name, params, predicate, line=0, col=0):
        super().__init__(line, col)
        self.name = name
        self.params = params
        self.predicate = predicate

class Literal(ASTNode):
    def __init__(self, value, line=0, col=0):
        super().__init__(line, col)
        self.value = value

class Identifier(ASTNode):
    def __init__(self, name, line=0, col=0):
        super().__init__(line, col)
        self.name = name

class BinaryOp(ASTNode):
    def __init__(self, left, op, right, line=0, col=0):
        super().__init__(line, col)
        self.left = left
        self.op = op
        self.right = right

class UnaryOp(ASTNode):
    def __init__(self, op, operand, line=0, col=0):
        super().__init__(line, col)
        self.op = op
        self.operand = operand

class ArrayAccess(ASTNode):
    def __init__(self, array, index, line=0, col=0):
        super().__init__(line, col)
        self.array = array
        self.index = index

class CallExpr(ASTNode):
    def __init__(self, name, args, line=0, col=0):
        super().__init__(line, col)
        self.name = name
        self.args = args

class QuantifierNode(ASTNode):
    def __init__(self, quantifier_type, var_name, var_type, predicate, line=0, col=0):
        super().__init__(line, col)
        self.quantifier_type = quantifier_type
        self.var_name = var_name
        self.var_type = var_type
        self.predicate = predicate

class Block(ASTNode):
    def __init__(self, statements, line=0, col=0):
        super().__init__(line, col)
        self.statements = statements

class Assign(ASTNode):
    def __init__(self, name, index, value, line=0, col=0):
        super().__init__(line, col)
        self.name = name
        self.index = index
        self.value = value

class TupleAssign(ASTNode):
    def __init__(self, targets, call_expr, line=0, col=0):
        super().__init__(line, col)
        self.targets = targets
        self.call_expr = call_expr

class IfStatement(ASTNode):
    def __init__(self, condition, then_branch, else_branch, line=0, col=0):
        super().__init__(line, col)
        self.condition = condition
        self.then_branch = then_branch
        self.else_branch = else_branch

class WhileStatement(ASTNode):
    def __init__(self, condition, invariant, body, line=0, col=0):
        super().__init__(line, col)
        self.condition = condition
        self.invariant = invariant
        self.body = body

class AssertStatement(ASTNode):
    def __init__(self, condition, line=0, col=0):
        super().__init__(line, col)
        self.condition = condition

class AssumeStatement(ASTNode):
    def __init__(self, condition, line=0, col=0):
        super().__init__(line, col)
        self.condition = condition

class ReturnStatement(ASTNode):
    def __init__(self, expr, line=0, col=0):
        super().__init__(line, col)
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
        f_token = self.consume('KW_FUNCTION')
        f_line, f_col = f_token[2], f_token[3]
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
        return FunctionDef(name_token[1], params, returns_defs or return_type, requires, ensures, uses, body, line=f_line, col=f_col)

    def parse_formula(self):
        name_token = self.consume('IDENT')
        f_line, f_col = name_token[2], name_token[3]
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
        return FormulaNode(name_token[1], params, predicate, line=f_line, col=f_col)

    def parse_block(self):
        token = self.peek()
        b_line, b_col = (token[2], token[3]) if token else (0, 0)
        self.consume('LBRACE')
        statements = []
        while self.peek() and self.peek()[0] != 'RBRACE':
            try:
                statements.append(self.parse_statement())
            except ParserError as e:
                self.errors.append(e)
                self.panic_synchronize(self.STMT_SYNC)
        self.consume('RBRACE')
        return Block(statements, line=b_line, col=b_col)

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
        token = self.consume('KW_IF')
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
        return IfStatement(condition, then_branch, else_branch, line=token[2], col=token[3])

    def parse_while(self):
        token = self.consume('KW_WHILE')
        self.consume('LPAREN')
        condition = self.parse_condition()
        self.consume('RPAREN')
        
        invariant = None
        if self.peek() and self.peek()[0] == 'KW_INVARIANT':
            self.consume('KW_INVARIANT')
            invariant = self.parse_condition()

        body = self.parse_block()
        return WhileStatement(condition, invariant, body, line=token[2], col=token[3])

    def parse_assert(self):
        token = self.consume('KW_ASSERT')
        expr = self.parse_condition()
        if self.peek() and self.peek()[0] == 'SEMICOLON':
            self.consume('SEMICOLON')
        else:
            t = self.peek()
            raise ParserError("Ожидалась ';'", t[2] if t else -1, t[3] if t else -1)
        return AssertStatement(expr, line=token[2], col=token[3])

    def parse_assume(self):
        token = self.consume('KW_ASSUME')
        expr = self.parse_condition()
        if self.peek() and self.peek()[0] == 'SEMICOLON':
            self.consume('SEMICOLON')
        else:
            t = self.peek()
            raise ParserError("Ожидалась ';'", t[2] if t else -1, t[3] if t else -1)
        return AssumeStatement(expr, line=token[2], col=token[3])

    def parse_return(self):
        token = self.consume('KW_RETURN')
        expr = None
        if self.peek() and self.peek()[0] not in ('SEMICOLON', 'RBRACE'):
            expr = self.parse_expr()
        if self.peek() and self.peek()[0] == 'SEMICOLON':
            self.consume('SEMICOLON')
        return ReturnStatement(expr, line=token[2], col=token[3])

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
                return TupleAssign(targets, call_expr, line=t_line, col=t_col)

            if self.peek() and self.peek()[0] == 'ASSIGN':
                self.consume('ASSIGN')
                value_expr = self.parse_expr()
                if self.peek() and self.peek()[0] == 'SEMICOLON':
                    self.consume('SEMICOLON')
                else:
                    t = self.peek()
                    raise ParserError("Ожидалась ';'", t[2] if t else t_line, t[3] if t else t_col)
                    
                if isinstance(expr, Identifier):
                    return Assign(name=expr.name, index=None, value=value_expr, line=t_line, col=t_col)
                elif isinstance(expr, ArrayAccess):
                    if isinstance(expr.array, Identifier):
                        functional_update = CallExpr(
                            name="__array_update__",
                            args=[expr.array, expr.index, value_expr],
                            line=t_line, col=t_col
                        )
                        return Assign(name=expr.array.name, index=None, value=functional_update, line=t_line, col=t_col)
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
            q_token = self.consume()
            self.consume('LPAREN')
            var_name, var_type = self.parse_variable_def()
            self.consume('PIPE')
            pred = self.parse_condition()
            self.consume('RPAREN')
            return QuantifierNode(q_token[1], var_name, var_type, pred, line=q_token[2], col=q_token[3])
        return self.parse_implication()

    def parse_implication(self):
        node = self.parse_or()
        if self.peek() and self.peek()[0] == 'OP_ARROW_SINGLE':
            op_token = self.consume()
            right = self.parse_implication()
            node = BinaryOp(node, op_token[1], right, line=node.line, col=node.col)
        return node

    def parse_or(self):
        node = self.parse_and()
        while self.peek() and self.peek()[0] == 'IDENT' and self.peek()[1] == 'or':
            op_token = self.consume()
            right = self.parse_and()
            node = BinaryOp(node, op_token[1], right, line=node.line, col=node.col)
        return node

    def parse_and(self):
        node = self.parse_not()
        while self.peek() and self.peek()[0] == 'IDENT' and self.peek()[1] == 'and':
            op_token = self.consume()
            right = self.parse_not()
            node = BinaryOp(node, op_token[1], right, line=node.line, col=node.col)
        return node

    def parse_not(self):
        if self.peek() and self.peek()[0] == 'IDENT' and self.peek()[1] == 'not':
            op_token = self.consume()
            operand = self.parse_not()
            return UnaryOp(op_token[1], operand, line=op_token[2], col=op_token[3])
        return self.parse_equality()

    def parse_expr(self):
        return self.parse_condition()

    def parse_equality(self):
        node = self.parse_additive()
        while self.peek() and self.peek()[0] in ('OP_EQ', 'OP_NEQ', 'OP_LT', 'OP_GT', 'OP_LE', 'OP_GE'):
            op_token = self.consume()
            right = self.parse_additive()
            node = BinaryOp(node, op_token[1], right, line=node.line, col=node.col)
        return node

    def parse_additive(self):
        node = self.parse_multiplicative()
        while self.peek() and self.peek()[0] in ('OP_ADD', 'OP_SUB'):
            op_token = self.consume()
            right = self.parse_multiplicative()
            node = BinaryOp(node, op_token[1], right, line=node.line, col=node.col)
        return node

    def parse_multiplicative(self):
        node = self.parse_unary()
        while self.peek() and self.peek()[0] in ('OP_MUL', 'OP_DIV'):
            op_token = self.consume()
            right = self.parse_unary()
            node = BinaryOp(node, op_token[1], right, line=node.line, col=node.col)
        return node

    def parse_unary(self):
        if self.peek() and self.peek()[0] in ('OP_SUB', 'PIPE'):
            op_token = self.consume()
            operand = self.parse_unary()
            return UnaryOp(op_token[1], operand, line=op_token[2], col=op_token[3])
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
                    node = CallExpr(node.name, args, line=node.line, col=node.col)
                else:
                    raise ParserError("Ожидалось имя функции для вызова", t_line, t_col)
            
            elif t_type == 'LBRACKET':
                self.consume('LBRACKET')
                index_expr = self.parse_condition()
                self.consume('RBRACKET')
                node = ArrayAccess(node, index_expr, line=node.line, col=node.col)
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
            return Literal(int(t_val), line=t_line, col=t_col)
        elif t_type == 'IDENT' or t_type == 'KW_LENGTH':
            self.consume()
            return Identifier(t_val, line=t_line, col=t_col)
        elif t_type == 'LPAREN':
            self.consume('LPAREN')
            expr = self.parse_condition()
            self.consume('RPAREN')
            return expr
        elif t_type == 'KW_TRUE':
            self.consume('KW_TRUE')
            return Literal(True, line=t_line, col=t_col)
        elif t_type == 'KW_FALSE':
            self.consume('KW_FALSE')
            return Literal(False, line=t_line, col=t_col)
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