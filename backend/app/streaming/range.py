import re
from dataclasses import dataclass

@dataclass
class ByteRange:
    start: int
    end: int

class RangeError(Exception): pass

def parse_range(value: str | None, total: int) -> ByteRange | None:
    if not value: return None
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not m: raise RangeError("Invalid Range header")
    a, b = m.groups()
    if not a and not b: raise RangeError("Invalid Range header")
    if not a:
        length = int(b)
        if length <= 0: raise RangeError("Invalid Range header")
        return ByteRange(max(0, total-length), total-1)
    start = int(a)
    end = int(b) if b else total-1
    if start >= total or start < 0 or end < start: raise RangeError("Range not satisfiable")
    return ByteRange(start, min(end, total-1))
