"""Fallbacks de roteamento."""


def with_fallbacks(primary: str, fallbacks: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for name in [primary, *fallbacks]:
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered
