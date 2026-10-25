import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from semantic import analyze_source

def run_tests():
    print("=== Запуск тестов семантического анализатора (HW3) ===")
    
    test_cases = [
        ("Позитивный #1: Базовая арифметика и возвраты", """
        function add(a: int, b: int) returns res: int {
            res = a + b;
        }
        """, 0),
        
        ("Позитивный #2: Вывод типов локальных переменных (бонус)", """
        function compute(n: int) returns out: int {
            temp = n * 2;
            out = temp + 1;
        }
        """, 0),

        ("Позитивный #3: Массивы и контракты", """
        function update_elem(a: int[], pos: int, val: int)
            requires pos >= 0 and pos < length(a)
            returns out: int[]
            ensures out[pos] == val
        {
            a[pos] = val;
            out = a;
        }
        """, 0),

        ("Негативный #1: Использование необъявленной переменной", """
        function unknown_var() returns res: int {
            res = x + 1;
        }
        """, 1),

        ("Негативный #2: Несоответствие типов в присваивании", """
        function type_mismatch() returns res: int {
            res = true;
        }
        """, 1),

        ("Негативный #3: Неверное число аргументов при вызове", """
        function f(a: int) returns res: int { res = a; }
        function caller() returns res: int {
            res = f(1, 2);
        }
        """, 1),

        ("Негативный #4: Повторное объявление функции", """
        function dup(a: int) returns res: int { res = a; }
        function dup(a: int) returns res: int { res = a; }
        """, 1),
    ]

    passed = 0
    failed = 0

    for idx, (title, code, expected_err_count) in enumerate(test_cases, 1):
        print(f"\n[+] Тест #{idx}: {title}")
        print(f"  --------------------------------------------------")
        print(f"  Входной код:\n{code.strip()}")
        print(f"  --------------------------------------------------")
        
        ast, errors = analyze_source(code)
        err_count = len(errors)
        
        is_ok = False
        if expected_err_count == 0 and err_count == 0:
            is_ok = True
        elif expected_err_count > 0 and err_count >= expected_err_count:
            is_ok = True

        status = "PASSED" if is_ok else "FAILED"
        print(f"  Статус: [{status}] (ожидалось ошибок >= {expected_err_count}, получено {err_count})")
        
        if errors:
            print("  Обнаруженные семантические ошибки:")
            for e in errors:
                print(f"    -> {e}")
        else:
            print("  Результат: Ошибок нет. Типы успешно проверены и выведены.")

        if is_ok:
            passed += 1
        else:
            failed += 1

    print(f"\n==================================================")
    print(f"  ИТОГ: пройдено {passed} из {passed + failed} тестов.")
    print(f"==================================================")

if __name__ == "__main__":
    run_tests()