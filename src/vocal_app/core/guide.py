"""Deterministic practice levels; masks change guidance, never the vocal targets."""
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")
GUIDE_LEVELS = (
    ("integral", "1 · Integral", "Todas as notas têm referência e correção visual."),
    ("final", "2 · Final", "Último quarto das notas sem referência nem correção ao vivo."),
    ("meio", "3 · Meio", "De uma a três notas centrais ficam fantasmas."),
    ("guias", "4 · Apenas guias", "Primeira nota e uma referência central; a partir de 9 notas, duas referências centrais."),
    ("total", "5 · Total", "Somente a primeira nota tem referência e correção ao vivo."),
)


def guide_mask(length: int, level: str = "integral") -> tuple[bool, ...]:
    if length < 0:
        raise ValueError("O comprimento não pode ser negativo.")
    if level not in {item[0] for item in GUIDE_LEVELS}:
        raise ValueError(f"Nível de guia desconhecido: {level}")
    audible = set(range(length))
    if length > 1 and level == "final":
        count = min(length - 1, (length + 3) // 4)
        audible.difference_update(range(length - count, length))
    elif length > 2 and level == "meio":
        count = min(3, max(1, length // 4), length - 2)
        start = max(1, (length - count) // 2)
        audible.difference_update(range(start, start + count))
    elif level == "guias":
        audible = {0} if length else set()
        if length >= 9:
            audible.update((length // 3, 2 * length // 3))
        elif length >= 3:
            audible.add(length // 2)
    elif level == "total":
        audible = {0} if length else set()
    return tuple(index in audible for index in range(length))


def apply_guide_level(notes: Sequence[T | None], level: str = "integral", rest_positions=()) -> list[T | None]:
    rests = set(rest_positions)
    mask = iter(guide_mask(len(notes) - len(rests), level))
    return [None if i in rests else note if next(mask) else None for i, note in enumerate(notes)]
