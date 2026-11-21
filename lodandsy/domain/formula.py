"""Bounded expression interpreter. AST is inspected and interpreted, never executed."""

import ast
import math
import operator
from dataclasses import dataclass

LIMIT = 1_000_000_000
_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


class CalculationError(ValueError):
    def __init__(self, message, status="error"):
        super().__init__(message)
        self.status = status


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > LIMIT:
        raise CalculationError("Ожидается конечное число в техническом диапазоне")
    return value


@dataclass(frozen=True)
class Expression:
    source: str
    tree: object
    dependencies: frozenset


def parse_expression(source, names, functions, *, name_types=None, expected_type=None):
    if not isinstance(source, str) or len(source.encode("utf-8")) > 4096:
        raise ValueError("Формула превышает 4096 bytes")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, RecursionError, MemoryError) as error:
        raise ValueError("Синтаксис формулы: " + str(error)) from None
    nodes = list(ast.walk(tree))
    if len(nodes) > 256:
        raise ValueError("Формула превышает 256 узлов")
    dependencies = set()

    def validate(node, depth=0):
        if depth > 32:
            raise ValueError("Формула превышает глубину 32")
        match node:
            case ast.Expression(body=body):
                validate(body, depth + 1)
            case ast.Constant(value=value):
                if type(value) is not bool:
                    number(value)
            case ast.Name(id=key):
                if key not in names:
                    raise ValueError("Неизвестная переменная: " + key)
                dependencies.add(key)
            case ast.BinOp(left=left, op=op, right=right) if type(op) in _BINARY:
                if isinstance(op, ast.Div) and isinstance(right, ast.Constant) and right.value == 0:
                    raise ValueError("Деление на ноль")
                validate(left, depth + 1)
                validate(right, depth + 1)
            case ast.UnaryOp(op=op, operand=operand) if isinstance(
                op, (ast.UAdd, ast.USub, ast.Not)
            ):
                validate(operand, depth + 1)
            case ast.BoolOp(op=op, values=values) if isinstance(op, (ast.And, ast.Or)):
                for value in values:
                    validate(value, depth + 1)
            case ast.Compare(left=left, ops=ops, comparators=values) if all(
                type(op) in _COMPARE for op in ops
            ):
                validate(left, depth + 1)
                for value in values:
                    validate(value, depth + 1)
            case ast.IfExp(test=test, body=body, orelse=other):
                for value in (test, body, other):
                    validate(value, depth + 1)
            case ast.Call(func=ast.Name(id=key), args=args, keywords=[]) if key in functions:
                if not 1 <= len(args) <= 16:
                    raise ValueError("Недопустимое число аргументов")
                for value in args:
                    validate(value, depth + 1)
            case _:
                raise ValueError("Запрещённый синтаксис формулы: " + type(node).__name__)

    validate(tree)

    def infer(node):
        if isinstance(node, ast.Expression):
            return infer(node.body)
        if isinstance(node, ast.Constant):
            return "bool" if type(node.value) is bool else "number"
        if isinstance(node, ast.Name):
            return (name_types or {}).get(node.id, "unknown")
        if isinstance(node, ast.Call):
            function = functions[node.func.id]
            arguments = tuple(infer(value) for value in node.args)
            expected = getattr(function, "argument_types", None)
            if expected is not None:
                if len(arguments) != len(expected) or any(
                    actual not in {"unknown", wanted} for actual, wanted in zip(arguments, expected)
                ):
                    raise ValueError("Типы/число аргументов: " + node.func.id)
            elif any(value not in {"unknown", "number"} for value in arguments):
                raise ValueError("Функция принимает числа: " + node.func.id)
            return "number"
        if isinstance(node, ast.BinOp):
            if any(infer(value) not in {"unknown", "number"} for value in (node.left, node.right)):
                raise ValueError("Арифметика требует чисел")
            return "number"
        if isinstance(node, ast.UnaryOp):
            wanted = "bool" if isinstance(node.op, ast.Not) else "number"
            if infer(node.operand) not in {"unknown", wanted}:
                raise ValueError("Несовместимый тип унарной операции")
            return wanted
        if isinstance(node, ast.BoolOp):
            if any(infer(value) not in {"unknown", "bool"} for value in node.values):
                raise ValueError("Логическая операция требует bool")
            return "bool"
        if isinstance(node, ast.Compare):
            types = {infer(value) for value in (node.left, *node.comparators)} - {"unknown"}
            if len(types) > 1:
                raise ValueError("Несовместимые типы сравнения")
            return "bool"
        if isinstance(node, ast.IfExp):
            if infer(node.test) not in {"unknown", "bool"}:
                raise ValueError("Условие требует bool")
            branches = {infer(node.body), infer(node.orelse)} - {"unknown"}
            if len(branches) > 1:
                raise ValueError("Ветви условия имеют разные типы")
            return next(iter(branches), "unknown")
        return "unknown"

    result_type = infer(tree)
    if expected_type is not None and result_type not in {expected_type, "unknown"}:
        raise ValueError("Неверный тип результата формулы: " + result_type)
    return Expression(source, tree.body, frozenset(dependencies))


def evaluate(expression, read, functions):
    budget = 4096

    def boolean(value):
        if type(value) is not bool:
            raise CalculationError("Ожидается логическое значение")
        return value

    def visit(node):
        nonlocal budget
        budget -= 1
        if budget < 0:
            raise CalculationError("Исчерпан бюджет вычисления")
        match node:
            case ast.Constant(value=value):
                return value
            case ast.Name(id=key):
                value = read(key)
                if value is None:
                    raise CalculationError("Не задано: " + key, "unknown")
                return value
            case ast.BinOp(left=left, op=op, right=right):
                return number(_BINARY[type(op)](number(visit(left)), number(visit(right))))
            case ast.UnaryOp(op=ast.Not(), operand=value):
                return not boolean(visit(value))
            case ast.UnaryOp(op=op, operand=value):
                result = number(visit(value))
                return result if isinstance(op, ast.UAdd) else -result
            case ast.BoolOp(op=op, values=values):
                for value in values:
                    result = boolean(visit(value))
                    if isinstance(op, ast.And) and not result:
                        return False
                    if isinstance(op, ast.Or) and result:
                        return True
                return result
            case ast.Compare(left=left, ops=ops, comparators=values):
                left = visit(left)
                for op, node in zip(ops, values):
                    right = visit(node)
                    if type(left) is bool or type(right) is bool:
                        if type(left) is not type(right):
                            raise CalculationError("Несовместимые типы сравнения")
                    elif type(left) in (int, float) and type(right) in (int, float):
                        number(left)
                        number(right)
                    elif type(left) is not type(right):
                        raise CalculationError("Несовместимые типы сравнения")
                    if not _COMPARE[type(op)](left, right):
                        return False
                    left = right
                return True
            case ast.IfExp(test=test, body=body, orelse=other):
                return visit(body if boolean(visit(test)) else other)
            case ast.Call(func=ast.Name(id=key), args=args):
                return functions[key](*(visit(value) for value in args))
        raise CalculationError("Неизвестный узел")

    try:
        result = visit(expression.tree)
        return result if type(result) is bool else number(result)
    except CalculationError:
        raise
    except (ArithmeticError, TypeError, ValueError) as error:
        raise CalculationError("Ошибка расчёта: " + str(error)) from None


def dependency_order(expressions):
    order, active, done = [], [], set()

    def visit(key):
        if key in active:
            raise ValueError("Цикл: " + " → ".join((*active[active.index(key) :], key)))
        if key in done:
            return
        active.append(key)
        for dependency in sorted(expressions[key].dependencies & expressions.keys()):
            visit(dependency)
        active.pop()
        done.add(key)
        order.append(key)

    for key in expressions:
        visit(key)
    return tuple(order)
