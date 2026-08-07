import struct
import re
import json
import sys
import os

class PEFile:
    def __init__(self, data):
        self.data = data
        self.dos_header = struct.unpack_from('<H', data, 0)
        pe_offset = struct.unpack_from('<I', data, 0x3C)[0]
        self.sections = []
        self.image_base = struct.unpack_from('<Q', data, pe_offset + 0x18)[0]
        num_sections = struct.unpack_from('<H', data, pe_offset + 0x06)[0]
        opt_size = struct.unpack_from('<H', data, pe_offset + 0x14)[0]
        section_offset = pe_offset + 0x18 + opt_size
        for i in range(num_sections):
            s = section_offset + i * 40
            name = data[s:s+8].rstrip(b'\x00').decode('ascii', errors='ignore')
            vsize = struct.unpack_from('<I', data, s + 8)[0]
            vaddr = struct.unpack_from('<I', data, s + 12)[0]
            raw_size = struct.unpack_from('<I', data, s + 16)[0]
            raw_ptr = struct.unpack_from('<I', data, s + 20)[0]
            self.sections.append((name, vaddr, vsize, raw_ptr, raw_size))

    def rva_to_offset(self, rva):
        for name, vaddr, vsize, raw_ptr, raw_size in self.sections:
            if vaddr <= rva < vaddr + vsize:
                return raw_ptr + (rva - vaddr)
        return None

    def find_section(self, name):
        for s in self.sections:
            if s[0] == name:
                return s
        return None

    def read_rva(self, rva, size=8):
        off = self.rva_to_offset(rva)
        if off is None or off + size > len(self.data):
            return None
        return self.data[off:off+size]


def find_string_refs(pe, string_bytes):
    results = []
    rdata = pe.find_section('.rdata')
    if not rdata:
        return results
    name, vaddr, vsize, raw_ptr, raw_size = rdata
    offset = 0
    while True:
        idx = pe.data.find(string_bytes, raw_ptr + offset)
        if idx == -1 or idx >= raw_ptr + raw_size:
            break
        str_rva = vaddr + (idx - raw_ptr)
        text = pe.find_section('.text')
        if text:
            t_name, t_vaddr, t_vsize, t_raw_ptr, t_raw_size = text
            ref_pattern = struct.pack('<I', str_rva)
            t_offset = 0
            while True:
                ref_idx = pe.data.find(ref_pattern, t_raw_ptr + t_offset, t_raw_ptr + t_raw_size)
                if ref_idx == -1:
                    break
                inst_rva = t_vaddr + (ref_idx - t_raw_ptr)
                results.append({
                    'string_rva': str_rva,
                    'ref_rva': inst_rva,
                    'ref_offset': ref_idx
                })
                t_offset = ref_idx - t_raw_ptr + 1
        offset = idx - raw_ptr + 1
    return results


def find_pattern(pe, pattern_bytes, section_name='.text'):
    sec = pe.find_section(section_name)
    if not sec:
        return []
    name, vaddr, vsize, raw_ptr, raw_size = sec
    results = []
    offset = 0
    while True:
        idx = pe.data.find(pattern_bytes, raw_ptr + offset, raw_ptr + raw_size)
        if idx == -1:
            break
        rva = vaddr + (idx - raw_ptr)
        results.append({'rva': rva, 'offset': idx})
        offset = idx - raw_ptr + 1
    return results


def resolve_rip_relative(pe, instruction_rva, instruction_len=7):
    inst_data = pe.read_rva(instruction_rva, instruction_len)
    if not inst_data or len(inst_data) < 5:
        return None
    if inst_data[0] not in [0x48, 0x4C]:
        if inst_data[0] not in [0x8D, 0x8B, 0x89, 0x88]:
            return None
    if len(inst_data) < 7:
        return None
    rel32 = struct.unpack_from('<i', inst_data, 3)[0]
    target_rva = instruction_rva + instruction_len + rel32
    return target_rva


def find_datamodel_offset(pe):
    patterns = [
        b'DataModel',
        b'datamodel',
    ]
    for pat in patterns:
        refs = find_string_refs(pe, pat)
        if refs:
            for ref in refs:
                text = pe.find_section('.text')
                if not text:
                    continue
                t_name, t_vaddr, t_vsize, t_raw_ptr, t_rsize = text
                search_start = max(t_raw_ptr, ref['ref_offset'] - 0x200)
                search_end = min(t_raw_ptr + t_rsize, ref['ref_offset'] + 0x200)
                chunk = pe.data[search_start:search_end]
                for m in re.finditer(rb'\x48\x8b[\x05-\x0d]{1}\x00{4}', chunk):
                    inst_off = search_start + m.start()
                    inst_rva = t_vaddr + (inst_off - t_raw_ptr)
                    resolved = resolve_rip_relative(pe, inst_rva, 7)
                    if resolved is not None:
                        return resolved
    return None


def find_visualengine_offset(pe):
    patterns = [
        b'VisualEngine',
        b'visualengine',
        b'CGraphicSettings',
    ]
    for pat in patterns:
        refs = find_string_refs(pe, pat)
        if refs:
            for ref in refs:
                text = pe.find_section('.text')
                if not text:
                    continue
                t_name, t_vaddr, t_vsize, t_raw_ptr, t_rsize = text
                search_start = max(t_raw_ptr, ref['ref_offset'] - 0x200)
                search_end = min(t_raw_ptr + t_rsize, ref['ref_offset'] + 0x200)
                chunk = pe.data[search_start:search_end]
                for m in re.finditer(rb'\x48\x8b[\x05-\x0d]{1}\x00{4}', chunk):
                    inst_off = search_start + m.start()
                    inst_rva = t_vaddr + (inst_off - t_raw_ptr)
                    resolved = resolve_rip_relative(pe, inst_rva, 7)
                    if resolved is not None:
                        return resolved
    return None


def find_scheduler_offset(pe):
    patterns = [
        b'TaskScheduler',
        b'taskscheduler',
        b'Scheduler',
    ]
    for pat in patterns:
        refs = find_string_refs(pe, pat)
        if refs:
            for ref in refs:
                text = pe.find_section('.text')
                if not text:
                    continue
                t_name, t_vaddr, t_vsize, t_raw_ptr, t_rsize = text
                search_start = max(t_raw_ptr, ref['ref_offset'] - 0x200)
                search_end = min(t_raw_ptr + t_rsize, ref['ref_offset'] + 0x200)
                chunk = pe.data[search_start:search_end]
                for m in re.finditer(rb'\x48\x8b[\x05-\x0d]{1}\x00{4}', chunk):
                    inst_off = search_start + m.start()
                    inst_rva = t_vaddr + (inst_off - t_raw_ptr)
                    resolved = resolve_rip_relative(pe, inst_rva, 7)
                    if resolved is not None:
                        return resolved
    return None


def find_module_offsets(pe):
    dm = find_datamodel_offset(pe)
    ve = find_visualengine_offset(pe)
    sc = find_scheduler_offset(pe)
    return {
        'datamodel': dm,
        'visualengine': ve,
        'scheduler': sc
    }


def analyze_binary(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    pe = PEFile(data)
    module_offsets = find_module_offsets(pe)
    result = {
        'module': module_offsets,
        'found': sum(1 for v in module_offsets.values() if v is not None)
    }
    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python offset_finder.py <RobloxPlayerBeta.exe>")
        sys.exit(1)
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)
    result = analyze_binary(filepath)
    print(json.dumps(result, indent=2))
    if result['found'] > 0:
        print(f"\nFound {result['found']}/3 module offsets")
    else:
        print("\nNo module offsets found - patterns may need updating")
