import re as _re
from enum import IntEnum

class TypeClass(IntEnum):
    STRUCT = 0
    FB = 1
    PROGRAM = 2

def _parse_path(path_str):
    """Parse 'A.B[1].C[2][3]' into [('A',[]), ('B',[1]), ('C',[2,3])].
    Also handles SFC transition names with '->' (e.g. 'START->COUNT')."""
    result = []
    for seg in path_str.split('.'):
        m = _re.fullmatch(r'([\w>,-]+)((?:\[\d+\])*)', seg)
        if not m:
            raise ValueError('Invalid path segment: {!r}'.format(seg))
        name = m.group(1).upper()
        indices = [int(x) for x in _re.findall(r'\[(\d+)\]', m.group(2))]
        result.append((name, indices))
    return result

def _dims_to_strides(offset, dims):
    """Compute strides from total flat offset and dimension sizes."""
    if not dims:
        return ()
    strides = []
    remaining = offset
    for d in dims:
        remaining //= d
        strides.append(remaining)
    return tuple(strides)

def _make_flat(members, POUS):
    def flat(segments, cumulated):
        if not segments: return cumulated, None
        name, indices = segments[0]; rest = segments[1:]
        entry = members.get(name)
        # Try joining with next segment(s) for SFC names containing dots
        if entry is None and rest:
            joined = name
            for i, (next_name, _) in enumerate(rest):
                joined += '.' + next_name
                entry = members.get(joined)
                if entry is not None:
                    rest = rest[i + 1:]
                    break
        if entry is None: raise KeyError(repr(name))
        off, strides, base_type = entry
        cumulated += off
        if strides:
            cumulated += sum((indices[d] if len(indices) > d else 0) * s for d, s in enumerate(strides))
        sub = POUS.get(base_type)
        if sub and rest:
            return sub(rest, cumulated)
        return cumulated, base_type
    return flat

def _build_pous(pous_list):
    """Build _POUS dict from POUS list with (name, type_class, members) tuples."""
    pous = {}
    for type_name, _type_class, members in pous_list:
        member_dict = {}
        cumulated = 0
        for var_name, offset, dims, base_type in members:
            strides = _dims_to_strides(offset, dims)
            member_dict[var_name.upper()] = (cumulated, strides, base_type.upper())
            cumulated += offset
        pous[type_name.upper()] = _make_flat(member_dict, pous)
    return pous

def path_to_flat(path_str, POUS):
    """Convert a dotted IEC 61131-3 variable path to (flat_index, base_type)."""
    segments = _parse_path(path_str)
    if not segments:
        raise ValueError('Empty path')
    pou_name = segments[0][0]
    if pou_name not in POUS:
        raise KeyError('Unknown POU: {!r}'.format(pou_name))
    return POUS[pou_name](segments[1:], 0)


class POUSData:
    """Wraps POUS.py content for IDE-side path resolution and C code generation."""

    def __init__(self, pous_list, instances_list, ticktime):
        self.pous_list = pous_list
        self.instances = instances_list
        self.ticktime = ticktime
        self._pous = _build_pous(pous_list)
        # type_class lookup: type_name -> TypeClass
        self._type_classes = {name.upper(): tc for name, tc, _members in pous_list}
        self._build_instance_index()

    def _build_instance_index(self):
        self._inst_by_path = {}
        cumulated = 0
        for path, flat_count, dims, base_type in self.instances:
            self._inst_by_path[path.upper()] = (cumulated, flat_count, dims, base_type.upper())
            cumulated += flat_count
        self._total_flat_count = cumulated

    def type_class_of(self, type_name):
        """Return TypeClass for a type name, or None if not in POUS."""
        return self._type_classes.get(type_name)

    def resolve_path(self, iec_path):
        """Resolve IEC path to (global_flat_index, leaf_base_type) or (None, None)."""
        segments = _parse_path(iec_path)
        if not segments:
            return (None, None)
        # Find the longest matching instance prefix (by name, ignoring indices)
        for n in range(len(segments), 0, -1):
            prefix = '.'.join(name for name, _idx in segments[:n])
            inst = self._inst_by_path.get(prefix)
            if inst is not None:
                base_offset, flat_count, dims, base_type = inst
                # Apply array indices on the last matched segment if instance is an array
                _last_name, last_indices = segments[n - 1]
                if dims and last_indices:
                    strides = _dims_to_strides(flat_count, dims)
                    base_offset += sum(i * s for i, s in zip(last_indices, strides))
                    flat_count = strides[-1] if strides else 1
                    dims = ()
                rest = segments[n:]
                if not rest:
                    if flat_count == 1 and not dims:
                        return (base_offset, base_type)
                    return (None, None)
                pou_fn = self._pous.get(base_type)
                if pou_fn is None:
                    return (None, None)
                try:
                    local_idx, leaf_type = pou_fn(rest, 0)
                    return (base_offset + local_idx, leaf_type)
                except (KeyError, ValueError):
                    return (None, None)
        return (None, None)

    def iec_path_to_c_name(self, iec_path):
        """Derive C variable name from IEC instance path.

        'config.X' -> 'CONFIG__X'
        'config.resource.X' -> 'RESOURCE__X'
        """
        parts = iec_path.split('.')
        if len(parts) <= 2:
            return '__'.join(p.upper() for p in parts)
        else:
            return '__'.join(p.upper() for p in parts[1:])

    def c_type_and_recurse(self, base_type, dims):
        """Return (c_extern_type, c_recurse_fn, needs_value_deref) for an instance.

        c_extern_type: type string for extern declaration
        c_recurse_fn: name of __recurse function, or None for simple leaf
        needs_value_deref: True if ptr needs .value to access raw data
        """
        uc = base_type.upper()
        tc = self._type_classes.get(uc)

        if dims:
            array_name = '__ARRAY_OF_' + uc + '_' + '_'.join(str(d) for d in dims)
            return (
                '__IEC_' + array_name + '_t',
                array_name + '__recurse',
                True
            )

        if tc is not None:
            if tc == TypeClass.STRUCT:
                return (
                    '__IEC_' + uc + '_t',
                    uc + '__recurse',
                    True
                )
            else:
                return (
                    uc + '_data__',
                    uc + '_data____recurse',
                    False
                )

        return ('__IEC_' + uc + '_t', None, False)
