"""
Problem generation for math exercise sheets.

Each operation accepts independent integer ranges for operand1 and operand2,
plus a problem count. Problems are returned as a list of tuples
(operand1, operator, operand2, answer) sorted from easiest to hardest.

Difficulty heuristic (simple but reasonable for grade 2–3):
    score = digits(operand1) + digits(operand2)
            + 1 if the columnar operation requires regrouping (carry/borrow)
            + small magnitude term as a tiebreaker
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Literal

Operator = Literal["+", "-", "×", "÷"]


@dataclass(frozen=True)
class Problem:
    operand1: int
    operator: Operator
    operand2: int
    answer: int

    @property
    def difficulty(self) -> float:
        d1 = len(str(self.operand1))
        d2 = len(str(self.operand2))
        score = d1 + d2
        if self.operator == "+" and _has_carry(self.operand1, self.operand2):
            score += 1
        elif self.operator == "-" and _has_borrow(self.operand1, self.operand2):
            score += 1
        elif self.operator == "×":
            # multiplication scales with answer magnitude
            score += len(str(max(1, self.answer))) * 0.5
        elif self.operator == "÷":
            score += len(str(max(1, self.answer))) * 0.5
        # magnitude tiebreaker (kept small so it doesn't dominate)
        score += (self.operand1 + self.operand2) / 1_000_000
        return score


@dataclass
class OperationConfig:
    enabled: bool = False
    count: int = 0
    min1: int = 0
    max1: int = 9
    min2: int = 0
    max2: int = 9
    # Digit-shape constraints. Currently only honoured by multiplication
    # — the UI exposes them on the multiplication card only. The fields
    # live on OperationConfig (not just multiplication) so other
    # generators can opt in later without a schema change.
    no_zero_digits: bool = False        # 300, 301 excluded; 317 allowed
    no_repeated_digits: bool = False    # 311 excluded; 317 allowed


@dataclass
class GenerationRequest:
    addition: OperationConfig
    subtraction: OperationConfig
    multiplication: OperationConfig
    division: OperationConfig
    title: str = "Math Practice"
    include_answer_key: bool = True
    seed: int | None = None


# ---------- helpers ----------

def _has_carry(a: int, b: int) -> bool:
    """True if computing a + b column-wise requires a carry."""
    carry = 0
    while a or b or carry:
        s = (a % 10) + (b % 10) + carry
        if s >= 10:
            return True
        carry = s // 10
        a //= 10
        b //= 10
    return False


def _has_borrow(a: int, b: int) -> bool:
    """True if computing a - b column-wise (a >= b) requires a borrow."""
    if b > a:
        a, b = b, a
    while a or b:
        if (a % 10) < (b % 10):
            return True
        a //= 10
        b //= 10
    return False


def _rng(seed: int | None) -> random.Random:
    return random.Random(seed) if seed is not None else random.Random()


def digits_ok(value: int, no_zero: bool, no_repeated: bool) -> bool:
    """Does `value` satisfy the optional digit-shape constraints?

    Single source of truth shared by the generator (to pick operands) and
    the HTTP layer (to give a friendly feasibility error before generation
    runs and produces an empty section).
    """
    if not no_zero and not no_repeated:
        return True
    s = str(value)
    if no_zero and "0" in s:
        return False
    if no_repeated and len(set(s)) != len(s):
        return False
    return True


def valid_values(lo: int, hi: int, no_zero: bool, no_repeated: bool) -> list[int]:
    """Every integer in [lo, hi] that satisfies the digit-shape constraints."""
    if not no_zero and not no_repeated:
        return list(range(lo, hi + 1))
    return [v for v in range(lo, hi + 1) if digits_ok(v, no_zero, no_repeated)]


# ---------- per-operation generators ----------

def _gen_addition(cfg: OperationConfig, rng: random.Random) -> list[Problem]:
    out: list[Problem] = []
    for _ in range(cfg.count):
        a = rng.randint(cfg.min1, cfg.max1)
        b = rng.randint(cfg.min2, cfg.max2)
        out.append(Problem(a, "+", b, a + b))
    return out


def _gen_subtraction(cfg: OperationConfig, rng: random.Random) -> list[Problem]:
    out: list[Problem] = []
    for _ in range(cfg.count):
        a = rng.randint(cfg.min1, cfg.max1)
        b = rng.randint(cfg.min2, cfg.max2)
        # keep result non-negative for grade 2–3
        if b > a:
            a, b = b, a
        out.append(Problem(a, "-", b, a - b))
    return out


def _gen_multiplication(cfg: OperationConfig, rng: random.Random) -> list[Problem]:
    """
    Pick operands from the precomputed pool of values that satisfy the
    optional digit-shape constraints. Building the pool up front (rather
    than rejection-sampling) keeps generation fast and stays correct even
    when the constraints make valid values sparse — e.g. "101–999, no
    zeros, no repeated digits" leaves only 504 of the 899 values.
    """
    pool1 = valid_values(cfg.min1, cfg.max1, cfg.no_zero_digits, cfg.no_repeated_digits)
    pool2 = valid_values(cfg.min2, cfg.max2, cfg.no_zero_digits, cfg.no_repeated_digits)
    if not pool1 or not pool2:
        # The HTTP layer validates feasibility up front; if generation is
        # reached with an empty pool, fail silently with no problems so the
        # rest of the worksheet still renders.
        return []
    out: list[Problem] = []
    for _ in range(cfg.count):
        a = rng.choice(pool1)
        b = rng.choice(pool2)
        out.append(Problem(a, "×", b, a * b))
    return out


def _gen_division(cfg: OperationConfig, rng: random.Random) -> list[Problem]:
    """
    Generate exact (no-remainder) division problems.

    Strategy: pick divisor b in [min2, max2] (avoid 0). Then pick quotient q
    such that dividend a = b * q lies in [min1, max1]. If the divisor range
    makes that impossible, skip that attempt and try again with a different
    divisor. Falls back to a best-effort problem after several failures so
    the count is honored.
    """
    out: list[Problem] = []
    min2 = max(1, cfg.min2)  # forbid division by zero
    max2 = max(min2, cfg.max2)
    for _ in range(cfg.count):
        attempts = 0
        problem: Problem | None = None
        while attempts < 30 and problem is None:
            attempts += 1
            b = rng.randint(min2, max2)
            q_lo = max(0, -(-cfg.min1 // b))   # ceil(min1 / b)
            q_hi = cfg.max1 // b              # floor(max1 / b)
            if q_hi < q_lo:
                continue
            q = rng.randint(q_lo, q_hi)
            a = b * q
            problem = Problem(a, "÷", b, q)
        if problem is None:
            # fallback: pick something valid even if outside requested range
            b = rng.randint(min2, max2)
            q = rng.randint(0, max(1, cfg.max1 // b))
            problem = Problem(b * q, "÷", b, q)
        out.append(problem)
    return out


# ---------- public API ----------

def generate(req: GenerationRequest) -> list[Problem]:
    rng = _rng(req.seed)
    problems: list[Problem] = []
    if req.addition.enabled and req.addition.count > 0:
        problems += _gen_addition(req.addition, rng)
    if req.subtraction.enabled and req.subtraction.count > 0:
        problems += _gen_subtraction(req.subtraction, rng)
    if req.multiplication.enabled and req.multiplication.count > 0:
        problems += _gen_multiplication(req.multiplication, rng)
    if req.division.enabled and req.division.count > 0:
        problems += _gen_division(req.division, rng)

    problems.sort(key=lambda p: p.difficulty)
    return problems


def max_digits(problems: Iterable[Problem]) -> int:
    """Maximum width (in digit columns) needed across all problems for layout.

    For multi-digit multiplication we also reserve room for a uniform-width
    partial-product row at every shift: the leftmost partial sits at shift
    (op2_digits - 1), so the worksheet needs at least
    max_partial_digits + (op2_digits - 1) columns to keep that partial out
    of the operator column.
    """
    n = 1
    for p in problems:
        n = max(n, len(str(p.operand1)), len(str(p.operand2)), len(str(p.answer)))
        if p.operator == "×":
            op2 = str(p.operand2)
            if len(op2) >= 2:
                max_partial = max(
                    (len(str(p.operand1 * int(d))) for d in op2 if int(d) > 0),
                    default=1,
                )
                n = max(n, max_partial + len(op2) - 1)
    return n


def max_partial_width(p: Problem) -> int:
    """Uniform width to draw every partial-product row for a multi-digit mul."""
    op2 = str(p.operand2)
    return max(
        (len(str(p.operand1 * int(d))) for d in op2 if int(d) > 0),
        default=1,
    )
