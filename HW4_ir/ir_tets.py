import os
import sys
import argparse

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from semantic import analyze_source
from ir import (
    IRGenerator, build_cfg, cfg_to_dot, optimize, analyze_and_color, 
    interpret, OptFlags
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="HW4: тесты генерации IR и оптимизаций"
    )
    parser.add_argument(
        "--no-const-prop", action="store_true",
        help="Отключить constant propagation и folding"
    )
    parser.add_argument(
        "--no-algebraic", action="store_true",
        help="Отключить алгебраические упрощения"
    )
    parser.add_argument(
        "--no-cse", action="store_true",
        help="Отключить удаление общих подвыражений (CSE)"
    )
    parser.add_argument(
        "--no-dce", action="store_true",
        help="Отключить удаление мёртвого кода (DCE)"
    )
    parser.add_argument(
        "--disable-all", action="store_true",
        help="Отключить все оптимизации"
    )
    return parser.parse_args()


def run_tests(flags: OptFlags):
    print("=== Запуск тестов генерации IR и оптимизаций (HW4) ===")
    print(f"Флаги оптимизаций: {flags}")
    print()
    

    cfg_dir = os.path.join(current_dir, "cfg")
    os.makedirs(cfg_dir, exist_ok=True)
    coloring_dir = os.path.join(current_dir, "coloring")
    os.makedirs(coloring_dir, exist_ok=True)
    interference_dir = os.path.join(current_dir, "interference")
    os.makedirs(interference_dir, exist_ok=True)
    
    test_cases = [
        ("Позитивный #1: Базовая генерация IR (арифметика и возврат)", """
        function add(a: int, b: int) returns res: int {
            res = a + b;
        }
        """, {'a': 3, 'b': 4}, 7),
        
        ("Позитивный #2: Constant Folding (свертка констант)", """
        function compute() returns res: int {
            res = 10 + 5 * 2;
        }
        """, {}, 20),

        ("Позитивный #3: Algebraic Simplification (алгебраические упрощения)", """
        function simplify(x: int) returns res: int {
            a = x + 0;
            b = x * 1;
            c = x * 0;
            res = a + b + c;
        }
        """, {'x': 5}, 10),

        ("Позитивный #4: Dead Code Elimination (удаление мертвого кода)", """
        function dce_test(n: int) returns res: int {
            dead1 = 999;
            dead2 = 888;
            res = n + 1;
        }
        """, {'n': 10}, 11),

        ("Позитивный #5: Ветвление (if/else)", """
        function branch(n: int) returns res: int {
            if (n > 0) {
                res = 10;
            } else {
                res = 20;
            }
        }
        """, {'n': 5}, 10),

        ("Позитивный #6: Цикл (while)", """
        function loop(n: int) returns res: int {
            sum = 0;
            i = 0;
            while (i < n) {
                sum = sum + i;
                i = i + 1;
            }
            res = sum;
        }
        """, {'n': 5}, 10),

        ("Позитивный #7: Вызовы функций", """
        function helper(x: int) returns res: int {
            res = x * 2;
        }
        function caller(n: int) returns res: int {
            res = helper(n);
        }
        """, {'n': 7}, 14),

        ("Позитивный #8: Комбинированная оптимизация (const + algebraic + dce)", """
        function complex(x: int) returns res: int {
            a = 10 + 5;
            b = a * 1;
            c = x * 0;
            dead = 999;
            res = b + c;
        }
        """, {'x': 3}, 15),

        ("Позитивный #9: CSE (удаление общих подвыражений)", """
        function cse_test(x: int, y: int) returns res: int {
            a = x + y;
            b = x + y;
            c = x + y;
            res = a + b + c;
        }
        """, {'x': 2, 'y': 3}, 15),
    ]

    passed = 0
    failed = 0

    for idx, (title, code, args, expected_result) in enumerate(test_cases, 1):
        print(f"[+] Тест #{idx}: {title}")
        print(f"  --------------------------------------------------")
        print(f"  Входной код:\n{code.strip()}")
        print(f"  Аргументы: {args}")
        print(f"  --------------------------------------------------")
        
        ast, errors = analyze_source(code)
        if errors:
            print(f"  Ошибки семантического анализа: {errors}")
            failed += 1
            continue
        
        gen = IRGenerator()
        funcs = gen.generate(ast)
        
        func_name = list(funcs.keys())[-1]
        func = funcs[func_name]
        
        print(f"  Функция: {func_name}")
        print(f"  IR ДО оптимизаций:")
        for instr in func.instrs:
            print(f"    {instr}")
        
        instr_before = len(func.instrs)
        temps_before = sum(1 for i in func.instrs if hasattr(i, 'dst') and str(i.dst).startswith('t'))
        
        res_before = interpret(func, dict(args), funcs)
        print(f"  Результат ДО оптимизаций: {res_before}")
        
        optimize(func, flags)
        
        print(f"  IR ПОСЛЕ оптимизаций:")
        for instr in func.instrs:
            print(f"    {instr}")
        
        instr_after = len(func.instrs)
        temps_after = sum(1 for i in func.instrs if hasattr(i, 'dst') and str(i.dst).startswith('t'))
        
        res_after = interpret(func, dict(args), funcs)
        print(f"  Результат ПОСЛЕ оптимизаций: {res_after}")
        
        colors, graph = analyze_and_color(func)
        max_color = max(colors.values()) + 1 if colors else 0
        
        print(f"  Метрики:")
        print(f"    Инструкций: {instr_before} -> {instr_after} (экономия: {instr_before - instr_after})")
        print(f"    Временных переменных: {temps_before} -> {temps_after}")
        print(f"    Регистров (цветов): {max_color}")
        if colors:
            print(f"    Раскраска: {', '.join([f'{t}=R{c}' for t, c in sorted(colors.items())])}")
        
        coloring_filename = os.path.join(coloring_dir, f"coloring_test{idx}_{func_name}.txt")
        with open(coloring_filename, "w", encoding="utf-8") as f:
            f.write(f"Функция: {func_name}\n")
            f.write(f"Тест: {title}\n")
            f.write(f"Флаги: {flags}\n")
            f.write(f"Число регистров (цветов): {max_color}\n")
            f.write(f"{'='*40}\n")
            f.write("Раскраска временных переменных:\n")
            for t, c in sorted(colors.items()):
                f.write(f"  {t} -> R{c}\n")
            f.write(f"{'='*40}\n")
            f.write("Граф конфликтов (смежные вершины):\n")
            for t in sorted(graph.keys()):
                neighbors = sorted(graph[t])
                f.write(f"  {t} -- {{{', '.join(neighbors) if neighbors else '-'}}}\n")
        print(f"  Раскраска сохранена в {coloring_filename}")
        
        ig_filename = os.path.join(interference_dir, f"interference_graph_test{idx}_{func_name}.dot")
        with open(ig_filename, "w", encoding="utf-8") as f:
            f.write(f"graph InterferenceGraph_{func_name} {{\n")
            f.write(f'  label="Interference Graph for {func_name}\\nColors used: {max_color}";\n')
            f.write("  node [shape=circle];\n")
            for t in sorted(colors.keys()):
                color_hex = ["red", "blue", "green", "orange", "purple", "cyan", "yellow", "magenta"][colors[t] % 8]
                f.write(f'  {t} [style=filled, fillcolor={color_hex}, label="{t}\\nR{colors[t]}"];\n')
            drawn_edges = set()
            for t in sorted(graph.keys()):
                for nb in sorted(graph[t]):
                    edge = tuple(sorted([t, nb]))
                    if edge not in drawn_edges:
                        f.write(f"  {edge[0]} -- {edge[1]};\n")
                        drawn_edges.add(edge)
            f.write("}\n")
        print(f"  Граф конфликтов сохранен в {ig_filename}")
        
        blocks = build_cfg(func.instrs)
        cfg_filename = os.path.join(cfg_dir, f"cfg_test{idx}_{func_name}.dot")
        with open(cfg_filename, "w", encoding="utf-8") as f:
            f.write(cfg_to_dot(blocks, func_name))
        print(f"  CFG сохранен в {cfg_filename}")
        
        is_correct = (res_before == res_after)
        is_expected = (res_after == expected_result)
        
        is_ok = is_correct and is_expected
        
        status = "PASSED" if is_ok else "FAILED"
        print(f"  --------------------------------------------------")
        print(f"  Статус: [{status}]")
        
        if not is_correct:
            print(f"    Ошибка: Нарушена корректность (ДО={res_before}, ПОСЛЕ={res_after})")
        if not is_expected:
            print(f"    Ошибка: Ожидался результат {expected_result}, получен {res_after}")
        
        if is_ok:
            passed += 1
        else:
            failed += 1

    print(f"\n==================================================")
    print(f"  ИТОГ: пройдено {passed} из {passed + failed} тестов.")
    print(f"==================================================")


if __name__ == "__main__":
    cli_args = parse_args()
    
    if cli_args.disable_all:
        flags = OptFlags(const_prop=False, algebraic=False, cse=False, dce=False)
    else:
        flags = OptFlags(
            const_prop=not cli_args.no_const_prop,
            algebraic=not cli_args.no_algebraic,
            cse=not cli_args.no_cse,
            dce=not cli_args.no_dce
        )
    
    run_tests(flags)