import re as _re
from enum import IntEnum

class TypeClass(IntEnum):
    STRUCT = 0
    FB = 1
    PROGRAM = 2
    ARRAY = 3
    ENUM = 4
    DERIVED = 5
    SIMPLE = 6
    LOCATED = 7
    LOCATED_ARRAY = 8
    LOCATED_STRUCT = 9

# Instance classes of located global variables, whose C storage is a __IEC_*_p
# pointing to their location instead of a __IEC_*_t holding their value.
LOCATED_CLASSES = (TypeClass.LOCATED, TypeClass.LOCATED_ARRAY, TypeClass.LOCATED_STRUCT)

def _parse_path(path_str):
    """Parse 'A.B[1].C[2][3]' into [('A',[]), ('B',[1]), ('C',[2,3])]."""
    result = []
    for seg in path_str.split('.'):
        m = _re.fullmatch(r'(\w+)((?:\[\d+\])*)', seg)
        if not m:
            return None
        name = m.group(1).upper()
        indices = [int(x) for x in _re.findall(r'\[(\d+)\]', m.group(2))]
        result.append((name, indices))
    return result

def _dims_to_strides(flat_count, dims):
    """Compute strides from total flat count and dimension sizes."""
    if not dims:
        return ()
    strides = []
    remaining = flat_count
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
        off, strides, base_type, elem_type = entry
        cumulated += off
        if strides:
            cumulated += sum((indices[d] if len(indices) > d else 0) * s for d, s in enumerate(strides))
            if indices and elem_type is not None:
                base_type = elem_type
        sub = POUS.get(base_type)
        if sub and rest:
            return sub(rest, cumulated)
        return cumulated, base_type
    return flat


def _build_type_info(pous_list):
    """Build type info dict from POUS list.

    Returns {TYPE_NAME: (flat_count, dims_or_none, element_type_or_none, type_class)}
    """
    info = {}
    for entry in pous_list:
        tc = entry[1]
        name = entry[0].upper()
        if tc in (TypeClass.STRUCT, TypeClass.FB, TypeClass.PROGRAM):
            info[name] = (entry[2], None, None, tc)
        elif tc == TypeClass.ARRAY:
            info[name] = (entry[3], entry[4], entry[2].upper(), tc)
        elif tc == TypeClass.ENUM:
            info[name] = (1, None, None, tc)
        elif tc == TypeClass.DERIVED:
            info[name] = (1, None, entry[2].upper(), tc)
    return info


def _resolve_base_type(type_name, type_info):
    """Follow DERIVED chain to reach the ultimate base type."""
    seen = set()
    while type_name in type_info:
        ti = type_info[type_name]
        if ti[3] == TypeClass.ENUM:
            type_name = "DINT"
            break
        if ti[3] != TypeClass.DERIVED:
            break
        if type_name in seen:
            break
        seen.add(type_name)
        type_name = ti[2]
    return type_name


def _build_pous(pous_list, type_info):
    """Build _POUS dict for path resolution.

    New POUS format: members are (var_name, type_name) pairs.
    Flat counts and dims are resolved from type_info.
    """
    pous = {}
    for entry in pous_list:
        tc = entry[1]
        if tc not in (TypeClass.STRUCT, TypeClass.FB, TypeClass.PROGRAM):
            continue

        type_name = entry[0].upper()
        members = entry[3]

        member_dict = {}
        cumulated = 0
        for var_name, var_type in members:
            var_type_upper = _resolve_base_type(var_type.upper(), type_info)
            ti = type_info.get(var_type_upper)
            if ti is not None:
                flat_count = ti[0]
                dims = ti[1]
                base_type = var_type_upper
            else:
                flat_count = 1
                dims = None
                base_type = var_type_upper

            strides = _dims_to_strides(flat_count, dims) if dims else ()
            elem_type = ti[2] if ti is not None and ti[3] == TypeClass.ARRAY else None
            member_dict[var_name.upper()] = (cumulated, strides, base_type, elem_type)
            cumulated += flat_count

        pous[type_name] = _make_flat(member_dict, pous)
    return pous


def _build_members_by_type(pous_list):
    """Build dict mapping TYPE_NAME -> [(var_name, var_type), ...] for FB/STRUCT/PROGRAM types."""
    result = {}
    for entry in pous_list:
        tc = entry[1]
        if tc in (TypeClass.STRUCT, TypeClass.FB, TypeClass.PROGRAM):
            result[entry[0].upper()] = entry[3]
    return result


class POUSData:
    """Wraps POUS.py content for IDE-side path resolution and C code generation."""

    def __init__(self, pous_list, instances_list, ticktime, configname):
        self._pous_list_raw = pous_list
        self._instances_raw = instances_list
        self.ticktime = ticktime
        self.configname = configname
        self._type_info = _build_type_info(self._pous_list_raw)
        self._type_classes = {entry[0].upper(): entry[1] for entry in self._pous_list_raw}
        self._members_by_type = _build_members_by_type(self._pous_list_raw)
        self._pous = _build_pous(self._pous_list_raw, self._type_info)
        self._build_instance_index()

    def _instance_path(self, name, domain):
        """Construct instance path from name and domain."""
        if domain.upper() == self.configname.upper():
            return domain + '.' + name
        else:
            return self.configname + '.' + domain + '.' + name

    def _build_instance_index(self):
        """Build instance index from new-format instances."""
        self._inst_by_path = {}
        cumulated = 0
        for name, domain, base_type, type_class, flat_count in self._instances_raw:
            path = self._instance_path(name, domain).upper()
            # Resolve DERIVED aliases (e.g. a named array type BLUPS ->
            # __ARRAY_OF_CPLX_TYPE_32) to the concrete ARRAY/STRUCT/native type,
            # otherwise dims and element indexing look up the alias which has none.
            concrete = _resolve_base_type(base_type.upper(), self._type_info)
            dims = self._type_info.get(concrete, (None, None))[1] \
                if type_class in (TypeClass.ARRAY, TypeClass.LOCATED_ARRAY) else ()
            self._inst_by_path[path] = (cumulated, flat_count, dims, concrete)
            cumulated += flat_count
        self._total_flat_count = cumulated

    @property
    def instances_c(self):
        """Yield (path, flat_count, base_type, type_class, c_name, c_type, recurse_fn,
        needs_deref, is_config) for each instance.

        is_config tells configuration domain globals from resource scoped ones.
        _instance_path() concatenates the domain into the path, which loses that
        distinction, and generators need it: those globals are the ones stored in
        the IOs .so (see Generate_global_vars) and therefore shared by every logic
        .so through symbol interposition.
        """
        uc_configname = self.configname.upper()
        for name, domain, base_type, type_class, flat_count in self._instances_raw:
            path = self._instance_path(name, domain)
            # Resolve DERIVED aliases (named array/enum/simple types) to their
            # concrete type so the debugger generators see a real ARRAY/STRUCT/
            # native type: named arrays get a proper __recurse (not a bogus
            # <ALIAS>_ENUM scalar tag), and enums map to their storage type.
            concrete = _resolve_base_type(base_type.upper(), self._type_info)
            c_type, c_recurse, needs_deref = self.c_type_and_recurse(
                concrete, type_class in LOCATED_CLASSES)
            c_name = self.iec_path_to_c_name(path)
            yield (path, flat_count, concrete, type_class, c_name, c_type, c_recurse,
                   needs_deref, domain.upper() == uc_configname)

    def count_fb_instances(self, target_types):
        """Count total instances of given FB types, recursively through type tree."""
        target_set = {t.upper() for t in target_types}
        cache = {}

        def count_in_type(type_name):
            key = type_name.upper()
            if key in cache:
                return cache[key]
            cache[key] = 0  # guard against recursion
            count = 0
            members = self._members_by_type.get(key)
            if members:
                for _var_name, var_type in members:
                    var_type_upper = var_type.upper()
                    ti = self._type_info.get(var_type_upper)
                    multiplicity = 1
                    if ti and ti[1]:  # has dims (array)
                        for d in ti[1]:
                            multiplicity *= d
                    if var_type_upper in target_set:
                        count += multiplicity
                    else:
                        count += multiplicity * count_in_type(var_type)
            cache[key] = count
            return count

        total = 0
        for name, domain, base_type, _type_class, flat_count in self._instances_raw:
            ti = self._type_info.get(base_type.upper())
            multiplicity = 1
            if ti and ti[1]:  # array dims
                for d in ti[1]:
                    multiplicity *= d
            if base_type.upper() in target_set:
                total += multiplicity
            else:
                total += multiplicity * count_in_type(base_type)
        return total

    def resolve_path(self, iec_path):
        """Resolve IEC path to (global_flat_index, leaf_base_type) or (None, None)."""
        segments = _parse_path(iec_path)
        if not segments:
            return (None, None)
        for n in range(len(segments), 0, -1):
            prefix = '.'.join(name for name, _idx in segments[:n])
            inst = self._inst_by_path.get(prefix)
            if inst is not None:
                base_offset, flat_count, dims, base_type = inst
                _last_name, last_indices = segments[n - 1]
                if dims and last_indices:
                    strides = _dims_to_strides(flat_count, dims)
                    base_offset += sum(i * s for i, s in zip(last_indices, strides))
                    flat_count = strides[-1] if strides else 1
                    dims = ()
                    elem_ti = self._type_info.get(base_type)
                    if elem_ti is not None and elem_ti[3] == TypeClass.ARRAY:
                        base_type = elem_ti[2]
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
        """Derive C variable name from IEC instance path."""
        parts = iec_path.split('.')
        if len(parts) <= 2:
            return '__'.join(p.upper() for p in parts)
        else:
            return '__'.join(p.upper() for p in parts[1:])

    def c_type_and_recurse(self, base_type, located=False):
        """Return (c_extern_type, c_recurse_fn, needs_value_deref) for a type."""
        uc = base_type.upper()
        tc = self._type_classes.get(uc)
        wrapper = '__IEC_' + uc + ('_p' if located else '_t')

        if tc is not None:
            if tc in (TypeClass.STRUCT, TypeClass.ARRAY):
                return (
                    wrapper,
                    uc + '__recurse',
                    True
                )
            elif tc in (TypeClass.FB, TypeClass.PROGRAM):
                return (
                    uc + '_data__',
                    uc + '__recurse',
                    False
                )

        return (wrapper, None, False)
