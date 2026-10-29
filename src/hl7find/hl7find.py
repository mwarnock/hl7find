import re

class InvalidHL7FindSyntaxException(Exception):
    def __init__(self,extra_message):
        self.message = f"Invalid HL7 Find Syntax {extra_message}"
        super().__init__(self. message)

class HL7AmbiguousSegmentException(Exception):
    def __init__(self, message):
        super().__init__("Ambiguous segment selection: " + message)

class HL7PicketFenceException(Exception):
    "HL7 Index Notation starts at 1 given 0"
    pass

class HL7UpdateAttemptTooDeep(Exception):
    def __init__(self, search_string):
        super().__init__(f"Attempt to set value at too deep a position given: {search_string}")

# An IndexError so callers already catching IndexError (the old
# raise_on_index behaviour) keep working
class HL7LocationNotFoundException(IndexError):
    def __init__(self, location):
        super().__init__(f"Nothing found at location: {location}")

class HL7Message:
    def __init__(self,message_string, **kwargs):
        self._options = dict({'raise_on_ambiguous': True, 'strict': False, 'raise_on_index': False},**kwargs)
        # raise_on_index is the older name for strict
        self._strict = self._options.get('strict') or self._options.get('raise_on_index')
        self._parsing_elements = list(message_string[3:8])
        self._escape = self._parsing_elements[3]
        self._repeating = self._parsing_elements[2]
        self._delimeters = [self._parsing_elements[0],self._parsing_elements[1],self._parsing_elements[4]]
        self._segments = message_string.splitlines()
        self._internal_structure = list(map(lambda seg: (seg[:3], self._parse_segment(seg)), self._segments))
        # MSH.1 is the field separator itself and MSH.2 the encoding
        # characters, so neither can be parsed like the rest of the fields
        msh_fields = self._internal_structure[0][1]
        fixed_msh = [self._delimeters[0], ''.join(self._parsing_elements[1:5])] + msh_fields[1:]
        self._internal_structure[0] = (self._internal_structure[0][0], fixed_msh)


    # Segment splitting is handled above
    # These handle splitting based on the delimeters specified
    # in the MSH segment into lists and the grouping of repeating
    # fields into tuples.
    # Using tuples to distinguish repeating fields is vital for
    # the wildcare find syntax used below (e.g. ZF1.4*.1 which returns
    # the first sub element of the ZF1.4 repeating field)
    def _parse_segment(self,segment):
        return list(map(self._parse_field, segment.split(self._delimeters[0])[1:]))

    def _parse_field(self,field):
        repititions = field.split(self._repeating)
        if len(repititions) > 1:
            return tuple(map(self._parse_components, repititions))
        else:
            return self._parse_components(field)

    # A value only stays a plain string when it uses no deeper delimeter at
    # all. Subcomponents without components (e.g. "&Whitaker&Emily") are
    # valid HL7 and are component 1 split into subcomponents.
    def _parse_components(self,value):
        component, subcomponent = self._delimeters[1], self._delimeters[2]
        if component not in value and subcomponent not in value:
            return value
        else:
            return list(map(self._parse_subcomponents, value.split(component)))

    def _parse_subcomponents(self,value):
        subcomponent = self._delimeters[2]
        if subcomponent in value:
            return value.split(subcomponent)
        else:
            return value

    def segments(self):
        return self._segments

    def delimeters(self):
        return self._delimeters

    def internal_structure(self):
        return self._internal_structure

    def to_string(self, newline_char='\n'):
        def list_to_string(hl7list,delimeters):
            if type(hl7list) is tuple:
                return self._repeating.join(map(lambda repeating_item: list_to_string(repeating_item,delimeters.copy()), hl7list))
            elif type(hl7list) is list and len(delimeters) > 0:
                first_delimeter = delimeters[0]
                rest_delimeters = delimeters[1:]
                return first_delimeter.join(map(lambda item: item if type(item) not in [tuple,list] else list_to_string(item,rest_delimeters), hl7list))
            else:
                return hl7list

        # MSH.1 is the field separator that's emitted after the segment name anyway
        def segment_to_string(name, fields):
            fields = fields[1:] if name == 'MSH' else fields
            return f"{name}{self._delimeters[0]}{list_to_string(fields,self._delimeters)}"

        return newline_char.join(map(lambda seg_tuple: segment_to_string(*seg_tuple),
                                     self._internal_structure))

    def find(self,search_string):
        # Add a format/syntax check here
        if not self._check_search_syntax(search_string):
            raise InvalidHL7FindSyntaxException(f"given: {search_string}")

        # Preventing duplication of [1:] token traversal
        def token_search(position, tokenized_search):
            for token in tokenized_search:
                position = self._find_with_int(position,token)
            return position

        # A location that isn't there is None unless in strict mode
        def guarded(search, *args):
            try:
                return search(*args)
            except HL7LocationNotFoundException:
                if self._strict:
                    raise HL7LocationNotFoundException(search_string)
                return None

        # Handle segment selection differently because of the
        # (segment name, list) setup in self._internal_structure
        tokenized_search = search_string.split(".")
        segment_token = tokenized_search.pop(0)
        found = guarded(self._find_segment, segment_token)
        if found is None:
            return None
        (_,position) = found

        # special case repeat segment handling, each segment is guarded on
        # its own so one missing value doesn't hide the others
        if type(position) == tuple:
            return list(map(lambda seg: guarded(token_search, seg, tokenized_search), position))
        else:
            return guarded(token_search, position, tokenized_search)

    # The primary difference in these finds is segments is a tuple
    # and the search string is alphanumeric instead of a number
    # opportunities for refactoring abound
    def _find_segment(self,token):
        if token[-1] == '*':
            indexes = [i for i,seg in filter(lambda i_seg: i_seg[1][0] == token[:-1], enumerate(self._internal_structure))]
            return (indexes,tuple(map(lambda seg: seg[1], filter(lambda seg: seg[0] == token[:-1], self._internal_structure))))
        elif token[-1] == ']':
            match = re.match(r"^([A-Z]{3})\[(\d+)\]$",token)
            seg_value = match.groups()[0]
            index = self._hl7_index_to_index(int(match.groups()[1]))
            seg_index = self._index([i for i,seg in filter(lambda i_seg: i_seg[1][0] == seg_value, enumerate(self._internal_structure))], index, token)
            segment = self._internal_structure[seg_index][1]
            return (seg_index, segment)
        else:
            segments = list(filter(lambda seg: seg[0] == token, self._internal_structure))
            if len(segments) == 0:
                raise HL7LocationNotFoundException(token)
            elif len(segments) > 1 and self._options.get('raise_on_ambiguous'):
                raise HL7AmbiguousSegmentException(f"There is more than one {token} segment")
            else:
                index = [i for i,seg in filter(lambda i_seg: i_seg[1][0] == token, enumerate(self._internal_structure))]
                return (index[0],segments[0][1])

    def _find_with_int(self,position, token):
        if type(position) == tuple: # Return of a repeating set
            return tuple(map(lambda p: self._find_with_int(p,token), position))
        if token[-1] == ']':
            match = re.match(r"^(\d+)\[(\d+)\]$",token)
            seg_index = self._hl7_index_to_index(int(match.groups()[0]))
            repeating_index = self._hl7_index_to_index(int(match.groups()[1]))
            field = self._index(position, seg_index, token)
            # A field that doesn't repeat is its own first repetition
            repititions = field if type(field) is tuple else (field,)
            return self._index(repititions, repeating_index, token)
        elif token[-1] == '*':
            index = self._hl7_index_to_index(int(token[:-1]))
            seg = self._index(position, index, token)
            return seg if type(seg) is tuple else (seg,)
        else:
            index = self._hl7_index_to_index(int(token))
            seg = self._index(position, index, token)
            if type(seg) in [tuple] and self._options.get('raise_on_ambiguous') and token[-1] != '*':
                raise HL7AmbiguousSegmentException(f"There is more than one value for segment {token} in {position}")
            else:
                return seg

    # A plain string is a value with only one component (in HL7 "Smith"
    # is the same as "Smith^"), so its first (or last) position is itself
    # rather than a character of it
    def _index(self,position, index, token):
        if type(position) is str:
            if index in [0, -1]:
                return position
            raise HL7LocationNotFoundException(token)
        try:
            return position[index]
        except IndexError:
            raise HL7LocationNotFoundException(token)

    def _hl7_index_to_index(self,given_int):
        if given_int == 0:
            raise HL7PicketFenceException()
        elif given_int < 0:
            return given_int
        else:
            return given_int - 1

    def _check_search_syntax(self,search_string):
        def is_or_with_selector(is_test, tokens):
            return (is_test(tokens[0])
                    and (len(tokens) == 1
                         or
                         tokens[1] == ''
                         or
                         re.match(r"^\d+\]$",tokens[1]) != None))

        tokens = list(map(lambda t: re.split(r"\*|\[", t), search_string.split(".")))
        valid = True if is_or_with_selector(lambda t: re.match(r"^\w{3}$", t) != None, tokens[0]) else False
        for token in tokens[1:]:
            if not is_or_with_selector(lambda t: re.match(r"^-*\d+$", t), token):
                valid = False
                break
        return valid

    def copy(self):
        return HL7Message(self.to_string())

    def add_segment(self,seg,value,index=None):
        if index and type(index) is int: # also filters out 0 which would override MSH
            head = self._internal_structure[:index+1]
            tail = self._internal_structure[index:]
            head[index] = (seg, value)
            head.extend(tail)
            self._internal_structure = head
        else:
            self._internal_structure.append((seg,value))


    def update(self,search_string,value):
        if re.match(r"^\w{3}(\[-?\d+\])?(\.-?\d+){0,3}$", search_string) == None:
            raise InvalidHL7FindSyntaxException("update search string must refer to only one location")

        tokenized_search = search_string.split(".")
        segment_token = tokenized_search[0]
        if len(tokenized_search) == 1: # Just the segment being updated
            index, seg = self._find_segment(segment_token)
            intstruc = list(self._internal_structure)
            new_seg = list(intstruc[index])
            intstruc[index] = (new_seg[0],value)
            self._internal_structure = intstruc
        else: # Any other depth updated
            indexes = list(map(lambda s: self._hl7_index_to_index(int(s)), tokenized_search[1:]))
            rindexes = indexes.copy()
            rindexes.reverse() # the lack of functional paradigms kills me
            (_, position) = self._find_segment(segment_token)
            previous_position = None

            while len(rindexes) > 0:
                index = rindexes.pop()
                print(f"In the while with:\nindex: {index}\nindexes: {rindexes}")
                # Extend any list that's too short and
                # raise if the position given is not a list
                if type(position) is list and len(position) < (index + 1):
                    diff = (index + 1) - len(position)
                    position.extend(list(map(lambda x: [], range(diff))))
                    previous_position = position
                    position = position[index]
                elif type(position) is list:
                    previous_position = position
                    position = position[index]
                else:
                    raise HL7UpdateAttemptTooDeep(search_string)

            # Previous position is used in order to set the internal
            # structure correctly otherwise it's just changing the value
            # of the leaf which doesn't change the internal structure
            # we want mutation. A copy method is available for those that
            # want to keep the original message intact akin to other python
            # data structures.
            previous_position[indexes[-1]] = value
            return previous_position



if __name__ == '__main__':
    pass
