"""Substituição pontual de NUL, que o PostgreSQL não aceita em texto."""


def replace_nul(rows):
    """Troca NUL por U+FFFD, preservando os demais caracteres e o comprimento."""
    result = []
    replacements = 0
    for row in rows:
        changed = False
        values = []
        for value in row:
            if isinstance(value, str) and "\x00" in value:
                replacements += value.count("\x00")
                value = value.replace("\x00", "\ufffd")
                changed = True
            values.append(value)
        result.append(tuple(values) if changed else row)
    return result, replacements
