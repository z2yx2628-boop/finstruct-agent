"""Read legacy binary Office files (.doc, .xls) without third-party packages.

Both formats are OLE2 "compound files" (a small FAT file system inside one
file). This module implements just enough of it to pull out:

* .doc (Word 97-2003): the main document text via the piece table (CLX).
  Field instructions are dropped, field results kept; table cell marks become
  " | " and row ends become line breaks.
* .xls (Excel 97-2003, BIFF8): cell values per sheet from the shared string
  table and LABELSST / LABEL / NUMBER / RK / MULRK / FORMULA / BOOLERR records.
  Dates stay as Excel serial numbers (formats are not interpreted).

Older formats (Word 6/95, Excel 5/95) raise LegacyOfficeError.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
END_OF_CHAIN = 0xFFFFFFFE
FREE_SECTOR = 0xFFFFFFFF


class LegacyOfficeError(ValueError):
    pass


class CompoundFile:
    """Minimal OLE2 compound-file reader (read-only, named streams only)."""

    def __init__(self, data: bytes):
        if data[:8] != SIGNATURE:
            raise LegacyOfficeError("not an OLE2 compound file (legacy .doc/.xls)")
        self.data = data
        self.sector_size = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        self.mini_sector_size = 1 << struct.unpack_from("<H", data, 0x20)[0]
        (fat_count, dir_start, _, self.mini_cutoff, minifat_start, minifat_count,
         difat_start, difat_count) = struct.unpack_from("<IIIIIIII", data, 0x2C)
        fat_sectors = [s for s in struct.unpack_from("<109I", data, 0x4C) if s < 0xFFFFFFFA]
        sector = difat_start
        per_sector = self.sector_size // 4 - 1
        for _ in range(difat_count):
            if sector >= 0xFFFFFFFA:
                break
            values = struct.unpack_from(f"<{per_sector + 1}I", self._sector(sector))
            fat_sectors.extend(v for v in values[:per_sector] if v < 0xFFFFFFFA)
            sector = values[per_sector]
        fat_sectors = fat_sectors[:fat_count]
        self.fat: list[int] = []
        for s in fat_sectors:
            self.fat.extend(struct.unpack_from(f"<{self.sector_size // 4}I", self._sector(s)))
        self.minifat: list[int] = []
        if minifat_count and minifat_start < 0xFFFFFFFA:
            raw = self._chain(minifat_start)
            self.minifat = list(struct.unpack_from(f"<{len(raw) // 4}I", raw))
        self.entries = self._directory(self._chain(dir_start))
        root = self.entries[0]
        self.mini_stream = self._chain(root["start"])[: root["size"]] if root["size"] else b""

    def _sector(self, number: int) -> bytes:
        offset = (number + 1) * self.sector_size
        return self.data[offset: offset + self.sector_size]

    def _chain(self, start: int) -> bytes:
        parts, sector, seen = [], start, set()
        while sector not in (END_OF_CHAIN, FREE_SECTOR) and sector < len(self.fat):
            if sector in seen:
                raise LegacyOfficeError("corrupt sector chain")
            seen.add(sector)
            parts.append(self._sector(sector))
            sector = self.fat[sector]
        return b"".join(parts)

    def _mini_chain(self, start: int) -> bytes:
        parts, sector, seen = [], start, set()
        size = self.mini_sector_size
        while sector not in (END_OF_CHAIN, FREE_SECTOR) and sector < len(self.minifat):
            if sector in seen:
                raise LegacyOfficeError("corrupt mini sector chain")
            seen.add(sector)
            parts.append(self.mini_stream[sector * size: (sector + 1) * size])
            sector = self.minifat[sector]
        return b"".join(parts)

    @staticmethod
    def _directory(raw: bytes) -> list[dict]:
        entries = []
        for offset in range(0, len(raw) - 127, 128):
            name_length = struct.unpack_from("<H", raw, offset + 64)[0]
            name = raw[offset: offset + max(0, name_length - 2)].decode("utf-16-le", "ignore")
            entry_type = raw[offset + 66]
            start, size = struct.unpack_from("<II", raw, offset + 116)
            entries.append({"name": name, "type": entry_type, "start": start, "size": size})
        return entries

    def stream(self, name: str) -> bytes | None:
        for entry in self.entries[1:]:
            if entry["type"] == 2 and entry["name"].lower() == name.lower():
                if entry["size"] < self.mini_cutoff:
                    return self._mini_chain(entry["start"])[: entry["size"]]
                return self._chain(entry["start"])[: entry["size"]]
        return None


# ---------------------------------------------------------------- Word (.doc)

FIELD_PATTERN = re.compile(r"\x13[^\x13\x14\x15]*\x14([^\x13\x14\x15]*)\x15|\x13[^\x13\x14\x15]*\x15")


def doc_text(path: str | Path) -> str:
    """Main-document text of a Word 97-2003 file, one paragraph per line."""
    cf = CompoundFile(Path(path).read_bytes())
    word = cf.stream("WordDocument")
    if word is None:
        raise LegacyOfficeError("no WordDocument stream")
    ident, fib_version = struct.unpack_from("<HH", word, 0)
    if ident != 0xA5EC or fib_version < 0x00C1:
        raise LegacyOfficeError("Word 6/95 or older .doc is not supported; save as .docx")
    flags = struct.unpack_from("<H", word, 0x0A)[0]
    if flags & 0x0100:
        raise LegacyOfficeError("encrypted .doc is not supported")
    table = cf.stream("1Table" if flags & 0x0200 else "0Table")
    if table is None:
        raise LegacyOfficeError("no table stream")
    ccp_text = struct.unpack_from("<I", word, 0x4C)[0]
    fc_clx, lcb_clx = struct.unpack_from("<II", word, 0x01A2)
    clx = table[fc_clx: fc_clx + lcb_clx]

    position = 0
    while position < len(clx) and clx[position] == 0x01:  # Prc: skip property modifiers
        position += 3 + struct.unpack_from("<H", clx, position + 1)[0]
    if position >= len(clx) or clx[position] != 0x02:
        raise LegacyOfficeError("piece table not found")
    lcb = struct.unpack_from("<I", clx, position + 1)[0]
    plc = clx[position + 5: position + 5 + lcb]
    count = (lcb - 4) // 12
    cps = struct.unpack_from(f"<{count + 1}I", plc, 0)
    pieces = []
    for index in range(count):
        fc = struct.unpack_from("<I", plc, 4 * (count + 1) + 8 * index + 2)[0]
        length = cps[index + 1] - cps[index]
        if fc & 0x40000000:
            start = (fc & 0x3FFFFFFF) // 2
            pieces.append(word[start: start + length].decode("cp1252", "replace"))
        else:
            pieces.append(word[fc: fc + 2 * length].decode("utf-16-le", "replace"))
    text = "".join(pieces)[:ccp_text]

    previous = None
    while previous != text:  # nested fields resolve from the inside out
        previous = text
        text = FIELD_PATTERN.sub(lambda m: m.group(1) or "", text)
    text = text.replace("\x07\r", "\x07").replace("\x07\x07", "\n").replace("\x07", " | ")
    text = text.replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    text = re.sub(r"[\x00-\x08\x0e-\x1f]", "", text)
    lines = [re.sub(r"[ \t　]+", " ", line).strip(" |") for line in text.split("\n")]
    return "\n".join(line.strip() for line in lines if line.strip())


# -------------------------------------------------------------- Excel (.xls)

class _Segments:
    """Byte reader over a record and its CONTINUE records (for the SST)."""

    def __init__(self, segments: list[bytes]):
        self.segments, self.index, self.offset = segments, 0, 0

    def _ensure(self):
        while self.index < len(self.segments) and self.offset >= len(self.segments[self.index]):
            self.index += 1
            self.offset = 0

    def read(self, size: int) -> bytes:
        out = b""
        while size > 0:
            self._ensure()
            if self.index >= len(self.segments):
                raise LegacyOfficeError("truncated SST")
            chunk = self.segments[self.index][self.offset: self.offset + size]
            self.offset += len(chunk)
            size -= len(chunk)
            out += chunk
        return out

    def chars(self, count: int, high_byte: bool) -> str:
        parts = []
        while count > 0:
            if self.index < len(self.segments) and self.offset >= len(self.segments[self.index]):
                # A string split across CONTINUE records restarts with a flags byte.
                self.index += 1
                self.offset = 0
                if self.index >= len(self.segments):
                    raise LegacyOfficeError("truncated SST")
                high_byte = bool(self.segments[self.index][0] & 0x01)
                self.offset = 1
            available = len(self.segments[self.index]) - self.offset
            width = 2 if high_byte else 1
            take = min(count, available // width)
            raw = self.segments[self.index][self.offset: self.offset + take * width]
            self.offset += take * width
            parts.append(raw.decode("utf-16-le" if high_byte else "latin-1"))
            count -= take
            if take == 0 and count:
                self.offset = len(self.segments[self.index])
        return "".join(parts)


def _unicode_string(data: bytes, offset: int, length_bytes: int = 2) -> tuple[str, int]:
    count = data[offset] if length_bytes == 1 else struct.unpack_from("<H", data, offset)[0]
    offset += length_bytes
    flags = data[offset]
    offset += 1
    rich = ext = 0
    if flags & 0x08:
        rich = struct.unpack_from("<H", data, offset)[0]
        offset += 2
    if flags & 0x04:
        ext = struct.unpack_from("<I", data, offset)[0]
        offset += 4
    width = 2 if flags & 0x01 else 1
    raw = data[offset: offset + count * width]
    text = raw.decode("utf-16-le" if width == 2 else "latin-1")
    return text, offset + count * width + rich * 4 + ext


def _rk(value: int) -> float:
    if value & 0x02:
        number = float(value >> 2 if not value & 0x80000000 else (value >> 2) - (1 << 30))
    else:
        number = struct.unpack("<d", struct.pack("<Q", (value & 0xFFFFFFFC) << 32))[0]
    return number / 100 if value & 0x01 else number


def _records(stream: bytes, start: int = 0):
    offset = start
    while offset + 4 <= len(stream):
        record_type, length = struct.unpack_from("<HH", stream, offset)
        yield offset, record_type, stream[offset + 4: offset + 4 + length]
        offset += 4 + length


def xls_sheets(path: str | Path) -> list[tuple[str, list[list[object]]]]:
    """[(sheet name, rows)] with rows as lists of str / float / None."""
    cf = CompoundFile(Path(path).read_bytes())
    book = cf.stream("Workbook") or cf.stream("Book")
    if book is None:
        raise LegacyOfficeError("no Workbook stream")
    records = list(_records(book))
    if not records or records[0][1] != 0x0809 or struct.unpack_from("<H", records[0][2], 0)[0] != 0x0600:
        raise LegacyOfficeError("only Excel 97-2003 (BIFF8) .xls is supported; save as .xlsx")
    if any(r[1] == 0x002F for r in records[:40]):
        raise LegacyOfficeError("encrypted .xls is not supported")

    sheets_meta, strings = [], []
    for index, (_, record_type, data) in enumerate(records):
        if record_type == 0x0085:  # BOUNDSHEET
            position, _, sheet_type = struct.unpack_from("<IBB", data, 0)
            name, _ = _unicode_string(data, 6, length_bytes=1)
            if sheet_type == 0:  # worksheet
                sheets_meta.append((name, position))
        elif record_type == 0x00FC:  # SST (+ CONTINUE)
            segments = [data[8:]]
            for _, next_type, next_data in records[index + 1:]:
                if next_type != 0x003C:
                    break
                segments.append(next_data)
            unique = struct.unpack_from("<I", data, 4)[0]
            reader = _Segments(segments)
            for _ in range(unique):
                count = struct.unpack("<H", reader.read(2))[0]
                flags = reader.read(1)[0]
                rich = struct.unpack("<H", reader.read(2))[0] if flags & 0x08 else 0
                ext = struct.unpack("<I", reader.read(4))[0] if flags & 0x04 else 0
                strings.append(reader.chars(count, bool(flags & 0x01)))
                reader.read(rich * 4 + ext)
        elif record_type == 0x000A:  # EOF of the workbook globals
            break

    result = []
    for name, position in sheets_meta:
        cells: dict[tuple[int, int], object] = {}
        pending_string = None
        for _, record_type, data in _records(book, position):
            if record_type == 0x000A:
                break
            if record_type == 0x00FD:  # LABELSST
                row, col, _, index = struct.unpack_from("<HHHI", data)
                cells[(row, col)] = strings[index] if index < len(strings) else ""
            elif record_type == 0x0204:  # LABEL
                row, col = struct.unpack_from("<HH", data)
                cells[(row, col)] = _unicode_string(data, 6)[0]
            elif record_type == 0x0203:  # NUMBER
                row, col, _, value = struct.unpack_from("<HHHd", data)
                cells[(row, col)] = value
            elif record_type == 0x027E:  # RK
                row, col, _, value = struct.unpack_from("<HHHI", data)
                cells[(row, col)] = _rk(value)
            elif record_type == 0x00BD:  # MULRK
                row, first = struct.unpack_from("<HH", data)
                for i in range((len(data) - 6) // 6):
                    value = struct.unpack_from("<I", data, 4 + 6 * i + 2)[0]
                    cells[(row, first + i)] = _rk(value)
            elif record_type == 0x0205:  # BOOLERR
                row, col, _, value, is_error = struct.unpack_from("<HHHBB", data)
                cells[(row, col)] = ("#ERR" if is_error else ("TRUE" if value else "FALSE"))
            elif record_type == 0x0006:  # FORMULA (cached result)
                row, col = struct.unpack_from("<HH", data)
                result_bytes = data[6:14]
                if result_bytes[6:8] == b"\xff\xff":
                    kind = result_bytes[0]
                    if kind == 0:
                        pending_string = (row, col)
                    elif kind == 1:
                        cells[(row, col)] = "TRUE" if result_bytes[2] else "FALSE"
                else:
                    cells[(row, col)] = struct.unpack("<d", result_bytes)[0]
            elif record_type == 0x0207 and pending_string:  # STRING after FORMULA
                cells[pending_string] = _unicode_string(data, 0)[0]
                pending_string = None
        if cells:
            rows_count = max(r for r, _ in cells) + 1
            cols_count = max(c for _, c in cells) + 1
            rows = [[cells.get((r, c)) for c in range(cols_count)] for r in range(rows_count)]
        else:
            rows = []
        result.append((name, rows))
    return result
