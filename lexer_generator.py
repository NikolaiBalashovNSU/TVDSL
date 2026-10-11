import json
from collections import defaultdict

class RegexNode:
    pass

class CharSet(RegexNode):
    def __init__(self, chars):
        self.chars = set(chars)

    def __repr__(self):
        return f"CharSet({len(self.chars)} chars)"

class Concat(RegexNode):
    def __init__(self, left, right):
        self.left = left
        self.right = right

class Alt(RegexNode):
    def __init__(self, left, right):
        self.left = left
        self.right = right

class Star(RegexNode):
    def __init__(self, child):
        self.child = child

class Epsilon(RegexNode):
    pass


class RegexParser:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def peek(self):
        return self.text[self.pos] if self.pos < len(self.text) else None

    def match(self, expected):
        if self.peek() == expected:
            self.pos += 1
            return True
        return False

    def parse(self):
        ast = self.parse_expr()
        if self.peek() is not None:
            raise ValueError(f"Неожиданный символ на позиции {self.pos}: {self.peek()}")
        return ast

    def parse_expr(self):
        node = self.parse_concat()
        while self.match('|'):
            right = self.parse_concat()
            node = Alt(node, right)
        return node

    def parse_concat(self):
        node = self.parse_term()
        while self.peek() is not None and self.peek() not in '|)*+':
            right = self.parse_term()
            node = Concat(node, right)
        return node

    def parse_term(self):
        node = self.parse_factor()
        while True:
            if self.match('*'):
                node = Star(node)
            elif self.match('+'):
                node = Concat(node, Star(node))
            else:
                break
        return node

    def parse_factor(self):
        if self.match('('):
            node = self.parse_expr()
            if not self.match(')'):
                raise ValueError("Ожидалась закрывающая скобка ')'")
            return node
        elif self.match('['):
            return self.parse_char_class()
        else:
            return self.parse_symbol()

    def parse_char_class(self):
        chars = set()
        invert = False
        if self.match('^'):
            invert = True

        while self.peek() is not None and self.peek() != ']':
            char = self.text[self.pos]
            self.pos += 1

            if self.peek() == '-' and self.pos + 1 < len(self.text) and self.text[self.pos + 1] != ']':
                self.pos += 1
                end_char = self.text[self.pos]
                self.pos += 1
                for c in range(ord(char), ord(end_char) + 1):
                    chars.add(chr(c))
            else:
                if char == '\\':
                    char = self.text[self.pos]
                    self.pos += 1
                    if char == 'n': char = '\n'
                    elif char == 't': char = '\t'
                    elif char == 'r': char = '\r'
                chars.add(char)

        if not self.match(']'):
            raise ValueError("Ожидался закрывающий символ ']'")

        if invert:
            all_ascii = set(chr(i) for i in range(128))
            chars = all_ascii - chars

        return CharSet(chars)

    def parse_symbol(self):
        char = self.peek()
        if char is None or char in '|)*+':
            return Epsilon()

        self.pos += 1
        if char == '\\':
            char = self.peek()
            if char is None:
                raise ValueError("Неожиданный конец строки после '\\'")
            self.pos += 1
            if char == 'n': char = '\n'
            elif char == 't': char = '\t'
            elif char == 'r': char = '\r'

        if char == '.':
            all_ascii_except_nl = set(chr(i) for i in range(128) if chr(i) != '\n')
            return CharSet(all_ascii_except_nl)

        return CharSet([char])



class NFAState:
    _id_counter = 0

    def __init__(self):
        self.id = NFAState._id_counter
        NFAState._id_counter += 1
        self.epsilon_transitions = []
        self.transitions = defaultdict(list)
        self.token_name = None
        self.priority = -1

class NFA:
    def __init__(self, start_state, accept_state):
        self.start = start_state
        self.accept = accept_state

def build_nfa(node):
    if isinstance(node, Epsilon):
        start, accept = NFAState(), NFAState()
        start.epsilon_transitions.append(accept)
        return NFA(start, accept)

    elif isinstance(node, CharSet):
        start, accept = NFAState(), NFAState()
        for char in node.chars:
            start.transitions[char].append(accept)
        return NFA(start, accept)

    elif isinstance(node, Concat):
        left_nfa = build_nfa(node.left)
        right_nfa = build_nfa(node.right)
        left_nfa.accept.epsilon_transitions.append(right_nfa.start)
        return NFA(left_nfa.start, right_nfa.accept)

    elif isinstance(node, Alt):
        left_nfa = build_nfa(node.left)
        right_nfa = build_nfa(node.right)
        start, accept = NFAState(), NFAState()
        start.epsilon_transitions.extend([left_nfa.start, right_nfa.start])
        left_nfa.accept.epsilon_transitions.append(accept)
        right_nfa.accept.epsilon_transitions.append(accept)
        return NFA(start, accept)

    elif isinstance(node, Star):
        child_nfa = build_nfa(node.child)
        start, accept = NFAState(), NFAState()
        start.epsilon_transitions.extend([accept, child_nfa.start])
        child_nfa.accept.epsilon_transitions.extend([child_nfa.start, accept])
        return NFA(start, accept)

def get_nfa_size(start_state):
    visited = set()
    stack = [start_state]
    total_transitions = 0

    while stack:
        state = stack.pop()
        if state in visited:
            continue
        visited.add(state)

        for next_st in state.epsilon_transitions:
            total_transitions += 1
            if next_st not in visited:
                stack.append(next_st)

        for char, next_states in state.transitions.items():
            for next_st in next_states:
                total_transitions += 1
                if next_st not in visited:
                    stack.append(next_st)

    return len(visited), total_transitions

def build_lexer_nfa(token_rules):
    super_start = NFAState()
    all_alphabet = set()

    for regex_str, token_name, priority in token_rules:
        parser = RegexParser(regex_str)
        ast = parser.parse()
        nfa = build_nfa(ast)
        
        nfa.accept.token_name = token_name
        nfa.accept.priority = priority
        super_start.epsilon_transitions.append(nfa.start)

        def collect_alphabet(state, visited):
            if state in visited: return
            visited.add(state)
            for ch in state.transitions:
                all_alphabet.add(ch)
            for nxt in state.epsilon_transitions:
                collect_alphabet(nxt, visited)
            for nxt_list in state.transitions.values():
                for nxt in nxt_list:
                    collect_alphabet(nxt, visited)

        collect_alphabet(nfa.start, set())

    return super_start, all_alphabet



class DFAState:
    _id_counter = 0

    def __init__(self, nfa_states):
        self.id = DFAState._id_counter
        DFAState._id_counter += 1
        self.nfa_states = frozenset(nfa_states)
        self.transitions = {}
        self.is_accepting = False
        self.token_name = None
        self.priority = -1
        for s in nfa_states:
            if s.token_name is not None:
                if s.priority > self.priority:
                    self.is_accepting = True
                    self.token_name = s.token_name
                    self.priority = s.priority

def epsilon_closure(states):
    stack = list(states)
    closure = set(states)
    while stack:
        s = stack.pop()
        for nxt in s.epsilon_transitions:
            if nxt not in closure:
                closure.add(nxt)
                stack.append(nxt)
    return closure

def nfa_to_dfa(super_start, alphabet):
    DFAState._id_counter = 0
    start_closure = epsilon_closure({super_start})
    start_dfa = DFAState(start_closure)

    dfa_map = {start_dfa.nfa_states: start_dfa}
    unmarked = [start_dfa]
    all_dfa_states = [start_dfa]

    while unmarked:
        current = unmarked.pop(0)

        for char in alphabet:
            move_set = set()
            for nfa_state in current.nfa_states:
                if char in nfa_state.transitions:
                    move_set.update(nfa_state.transitions[char])

            if not move_set:
                continue

            closure = epsilon_closure(move_set)
            frozen_closure = frozenset(closure)

            if frozen_closure not in dfa_map:
                next_dfa = DFAState(closure)
                dfa_map[frozen_closure] = next_dfa
                unmarked.append(next_dfa)
                all_dfa_states.append(next_dfa)

            current.transitions[char] = dfa_map[frozen_closure]

    return start_dfa, all_dfa_states



def minimize_dfa(start_dfa, dfa_states, alphabet):
    groups_map = defaultdict(list)
    for state in dfa_states:
        if not state.is_accepting:
            key = None
        else:
            key = (state.token_name, state.priority)
        groups_map[key].append(state)

    P = list(groups_map.values())
    W = list(P)

    while W:
        A = W.pop(0)
        for char in alphabet:
            X = set()
            for s in dfa_states:
                if char in s.transitions and s.transitions[char] in A:
                    X.add(s)

            if not X:
                continue

            new_P = []
            for Y in P:
                Y_set = set(Y)
                intersection = Y_set & X
                difference = Y_set - X

                if intersection and difference:
                    Y1 = list(intersection)
                    Y2 = list(difference)
                    new_P.extend([Y1, Y2])

                    if Y in W:
                        W.remove(Y)
                        W.extend([Y1, Y2])
                    else:
                        if len(Y1) <= len(Y2):
                            W.append(Y1)
                        else:
                            W.append(Y2)
                else:
                    new_P.append(Y)
            P = new_P

    state_to_group = {}
    new_states = []
    
    group_to_new_state = {}
    for idx, group in enumerate(P):
        rep = group[0]
        new_state = DFAState([])
        new_state.id = idx
        new_state.is_accepting = rep.is_accepting
        new_state.token_name = rep.token_name
        new_state.priority = rep.priority
        
        group_to_new_state[idx] = new_state
        new_states.append(new_state)
        for s in group:
            state_to_group[s] = idx

    for group_idx, group in group_to_new_state.items():
        rep = P[group_idx][0]
        for char, target_dfa in rep.transitions.items():
            target_group_idx = state_to_group[target_dfa]
            group.transitions[char] = group_to_new_state[target_group_idx]

    new_start_state = group_to_new_state[state_to_group[start_dfa]]
    return new_start_state, new_states



def serialize_dfa(start_state, all_states, alphabet):
    trap_id = "TRAP"
    json_data = {
        "start_state": start_state.id,
        "trap_state": trap_id,
        "alphabet": sorted(list(alphabet)),
        "states": {}
    }

    for state in all_states:
        transitions_dict = {}
        for char, target in state.transitions.items():
            transitions_dict[char] = target.id

        json_data["states"][str(state.id)] = {
            "is_accepting": state.is_accepting,
            "token": state.token_name,
            "transitions": transitions_dict
        }

    json_data["states"][trap_id] = {
        "is_accepting": False,
        "token": None,
        "transitions": {char: trap_id for char in alphabet}
    }

    return json_data

def run_lexer(dfa_json, text):
    pos = 0
    tokens = []
    length = len(text)
    start_state_id = str(dfa_json["start_state"])

    while pos < length:
        current_state_id = start_state_id
        last_accept_state = None
        last_accept_pos = -1
        current_pos = pos

        while current_pos < length:
            char = text[current_pos]
            state_info = dfa_json["states"][current_state_id]

            if char in state_info["transitions"]:
                current_state_id = str(state_info["transitions"][char])
            else:
                current_state_id = dfa_json["trap_state"]

            if current_state_id == dfa_json["trap_state"]:
                break

            current_pos += 1
            next_state_info = dfa_json["states"][current_state_id]
            if next_state_info["is_accepting"]:
                last_accept_state = next_state_info
                last_accept_pos = current_pos

        if last_accept_state is not None:
            token_type = last_accept_state["token"]
            matched_text = text[pos:last_accept_pos]
            if token_type not in ["WS", "COMMENT"]:
                tokens.append((token_type, matched_text))
            pos = last_accept_pos
        else:
            tokens.append(("ERROR", f"Неизвестный символ или ловушка '{text[pos]}' на позиции {pos}"))
            pos += 1

    return tokens

FUNNY_RULES = [
    ("function", "KW_FUNCTION", 10),
    ("returns", "KW_RETURNS", 10),
    ("requires", "KW_REQUIRES", 10),
    ("ensures", "KW_ENSURES", 10),
    ("uses", "KW_USES", 10),
    ("if", "KW_IF", 10),
    ("else", "KW_ELSE", 10),
    ("while", "KW_WHILE", 10),
    ("invariant", "KW_INVARIANT", 10),
    ("assert", "KW_ASSERT", 10),
    ("assume", "KW_ASSUME", 10),
    ("length", "KW_LENGTH", 10),
    ("int", "KW_INT", 10),
    ("true", "KW_TRUE", 10),
    ("false", "KW_FALSE", 10),

    ("==", "OP_EQ", 5),
    ("!=", "OP_NEQ", 5),
    ("<=", "OP_LE", 5),
    (">=", "OP_GE", 5),
    ("=>", "OP_ARROW_DOUBLE", 5),
    ("->", "OP_ARROW_SINGLE", 5),

    ("\\(", "LPAREN", 4),
    ("\\)", "RPAREN", 4),
    ("\\[", "LBRACKET", 4),
    ("\\]", "RBRACKET", 4),
    ("\\{", "LBRACE", 4),
    ("\\}", "RBRACE", 4),
    (",", "COMMA", 4),
    (":", "COLON", 4),
    (";", "SEMICOLON", 4),
    ("=", "ASSIGN", 4),
    (">", "OP_GT", 4),
    ("<", "OP_LT", 4),
    ("\\+", "OP_ADD", 4),
    ("-", "OP_SUB", 4),
    ("\\*", "OP_MUL", 4),
    ("/", "OP_DIV", 4),
    ("\\|", "PIPE", 4),

    ("[a-zA-Z_][a-zA-Z0-9_]*", "IDENT", 1),

    ("0|[1-9][0-9]*", "INT", 2),

    ("[ \t\r\n]+", "WS", 1),
    ("//[^\n]*", "COMMENT", 1),
]

def main():
    super_start, alphabet = build_lexer_nfa(FUNNY_RULES)
    nfa_states_cnt, nfa_trans_cnt = get_nfa_size(super_start)
    print(f"Размер НКА: {nfa_states_cnt} состояний")
    start_dfa, dfa_states = nfa_to_dfa(super_start, alphabet)
    raw_dfa_size = len(dfa_states)
    print(f"Размер ДКА до минимизации: {raw_dfa_size} состояний")

    min_start_dfa, min_dfa_states = minimize_dfa(start_dfa, dfa_states, alphabet)
    min_dfa_size = len(min_dfa_states)
    print(f"Размер ДКА после минимизации: {min_dfa_size} состояний")

    dfa_json = serialize_dfa(min_start_dfa, min_dfa_states, alphabet)
    with open("dfa_table.json", "w", encoding="utf-8") as f:
        json.dump(dfa_json, f, indent=2, ensure_ascii=False)
    print("Таблица переходов сохранена в 'dfa_table.json'")

    test_cases = [
        ("", []),
        ("   \t\r\n", []),
        ("0", [("INT", "0")]),
        ("00", [("INT", "0"), ("INT", "0")]),
        ("01", [("INT", "0"), ("INT", "1")]),
        ("my_var_123 _test", [("IDENT", "my_var_123"), ("IDENT", "_test")]),
        ("function returns while if else assert assume invariant length", [
            ("KW_FUNCTION", "function"), ("KW_RETURNS", "returns"),
            ("KW_WHILE", "while"), ("KW_IF", "if"), ("KW_ELSE", "else"),
            ("KW_ASSERT", "assert"), ("KW_ASSUME", "assume"),
            ("KW_INVARIANT", "invariant"), ("KW_LENGTH", "length")
        ]),
        ("()[]{},; + - * / == != <= >= < > =", [
            ("LPAREN", "("), ("RPAREN", ")"), ("LBRACKET", "["), ("RBRACKET", "]"),
            ("LBRACE", "{"), ("RBRACE", "}"), ("COMMA", ","), ("SEMICOLON", ";"),
            ("OP_ADD", "+"), ("OP_SUB", "-"), ("OP_MUL", "*"), ("OP_DIV", "/"),
            ("OP_EQ", "=="), ("OP_NEQ", "!="), ("OP_LE", "<="), ("OP_GE", ">="),
            ("OP_LT", "<"), ("OP_GT", ">"), ("ASSIGN", "=")
        ]),
        ("//comment\nwhile", [("KW_WHILE", "while")]),
        ("1xy @ # $", [
            ("IDENT", "var_123"),
            ("ERROR", "Неизвестный символ или ловушка '@' на позиции 8"),
            ("ERROR", "Неизвестный символ или ловушка '#' на позиции 10"),
            ("ERROR", "Неизвестный символ или ловушка '$' на позиции 12")
        ]),
    ]

    for idx, (inp, expected) in enumerate(test_cases, 1):
        res = run_lexer(dfa_json, inp)
        status = "PASSED" if res == expected else "FAILED"
        print(f"\nТест #{idx}: {status}")
        print(f"  Вход:    '{inp}'")
        print(f"  Выход:   {res}")
        if status == "FAILED":
            print(f"  Ожидалось: {expected}")

if __name__ == "__main__":
    main()