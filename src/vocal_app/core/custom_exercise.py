"""User supplied, two-line scores, kept separate from the original catalog."""
from pathlib import Path
import re

from .catalog import Exercise
from .notes import note_to_midi, midi_to_note


def parse_custom_exercise(text: str, name: str = "Personalizado") -> Exercise:
    lines = text.lstrip("\ufeff").strip().splitlines()
    if len(lines) != 2 or not all(line.strip() for line in lines):
        raise ValueError("Use duas linhas: notas na primeira e tempos em milissegundos na segunda.")
    tokens, times = lines[0].split(), lines[1].split()
    if len(tokens) != len(times):
        raise ValueError(f"Há {len(tokens)} notas e {len(times)} tempos. Informe um tempo por nota.")
    if len(tokens) > 256:
        raise ValueError("Use no máximo 256 notas por exercício.")
    notes = []
    for token in tokens:
        midi = note_to_midi(token)
        # Leave room for the application's full ±8 semitone transposition.
        if not 8 <= midi <= 119:
            raise ValueError(f"Nota fora da faixa instrumental suportada: {token}.")
        notes.append(midi_to_note(midi))
    if any(not re.fullmatch(r"[0-9]{1,5}", value) for value in times):
        raise ValueError("Os tempos devem ser números inteiros positivos em milissegundos, como 500.")
    durations = tuple(int(value) for value in times)
    if any(not 1 <= value <= 60000 for value in durations):
        raise ValueError("Cada tempo deve estar entre 1 e 60000 milissegundos.")
    if sum(durations) > 600000:
        raise ValueError("O exercício deve durar no máximo 10 minutos.")
    return Exercise(40, name, "Personalizado", "Tempos definidos no arquivo TXT", " ".join(notes),
                    "", "", None, 120, 1, tuple(notes), tuple(notes), durations_ms=durations)


def load_custom_exercise(path: str | Path) -> Exercise:
    path = Path(path)
    if path.suffix.lower() != ".txt":
        raise ValueError("Selecione um arquivo .txt.")
    with path.open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("O arquivo deve ter no máximo 64 KB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Salve o arquivo de texto na codificação UTF-8.") from exc
    return parse_custom_exercise(text, path.stem)
