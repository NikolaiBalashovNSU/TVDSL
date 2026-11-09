# HW4: Промежуточное представление и базовые оптимизации

## Формат IR (трёхадресный код)

### Операнды
- `Const(v)` — целочисленная константа
- `Var(n)` — именованная переменная из исходного кода
- `Temp()` — временная переменная компилятора (t1, t2, ...)

### Инструкции
| Инструкция | Синтаксис | Описание |
|---|---|---|
| AssignOp | `t1 = a + b` | Бинарная операция (+, -, *, /, <, >, ==, !=) |
| AssignVar | `res = t1` | Копирование значения |
| Label | `L1:` | Метка — цель перехода |
| CondJump | `if t1 goto L1` | Условный переход |
| Jump | `goto L2` | Безусловный переход |
| Call | `t1 = call f(x, y)` | Вызов функции |
| Return | `return res` | Возврат значения |

### Соответствие байт-коду JVM
- `AssignOp` → `ILOAD/ILOAD/IADD/ISTORE`
- `CondJump` → `IF_ICMPGT/IFEQ/...`
- `Jump` → `GOTO`
- `Call` → `INVOKESTATIC/INVOKEVIRTUAL`
- `Return` → `IRETURN`

## Флаги оптимизаций

| Флаг CLI | Что делает |
|---|---|
| `--no-const-prop` | Отключить constant propagation и folding |
| `--no-algebraic` | Отключить алгебраические упрощения |
| `--no-cse` | Отключить удаление общих подвыражений |
| `--no-dce` | Отключить удаление мёртвого кода |
| `--disable-all` | Отключить все оптимизации |

## Примеры запуска

```bash
# Все оптимизации включены (по умолчанию)
python3 ir_tets.py

# Только CSE и DCE
python3 ir_tets.py --no-const-prop --no-algebraic

# Без оптимизаций (эталонный IR)
python3 ir_tets.py --disable-all