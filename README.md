# HL7Find

HL7Find is an HL7 v2 parsing library that uses typical HL7 location notation as a means of retrieving values.

This library is not for sending or receiving HL7.

It's distinguishing feature is that it uses common (with some extensions) notation to access and update HL7 v2 messages. For example, to access PID.3.1 simply use `my_message.find('PID.3.1')` instead of inventing syntax in the programming language.

## Installation

This library is written using only the standard library for python 3. You can install it like most python packages:

```bash
pip install hl7find
```

## Use

The library is primarly a single class which takes an HL7 string (`\r` or `\n` delimeters on the segments) as its first argument.

There is also no need to specify the delimerters, repeating operator, or esacape character. HL7 does that in the MSH segment.

```python
from hl7find import HL7Message

hl7_string = """
MSH|^~\&|SendingApp|SendingFac|ReceivingApp|ReceivingFac|20120411070545||ORU^R01|59689|P|2.3
PID|1|12345|12345^^^MIE&1.2.840.114398.1.100&ISO^MR||MOUSE^MINNIE^S||19240101|F|||123 MOUSEHOLE LN^^FORT WAYNE^IN^46808|||||||||||||||||||
OBX|1|NM|wbc^Wbc^Local^6690-2^Wbc^LN||7.0|/nl|3.8-11.0||||F|||20120410160227|lab|12^XYZ LAB|
OBX|2|NM|neutros^Neutros^Local^770-8^Neutros^LN||68|%|40-82||||F|||20120410160227|lab|12^XYZ LAB|
OBX|3|NM|lymphs^Lymphs^Local^736-9^Lymphs^LN||20|%|11-47||||F|||20120410160227|lab|12^XYZ LAB|
ZF1|TEST|REPEAT 1~REPEAT 2~REPEAT 3|This^Still^Works|deeper^repeat^1~deeper^repeat^2|other^deepest~repeating~field|z end
"""

msg = HL7Message(hl7_string)
```

### Find

With an `HL7Message` instance you can use the find function to retrieve parts of the message. Using the example HL7 message above, this includes simple descrete values:

```python
msg.find("PID.3.1") # -> 12345
msg.find("PID.3.4.1") # -> MEI
```

Repeating segments or values:

```python
msg.find("OBX*.3")   # -> A tuple of all obx segments at position 3
msg.find("ZF1.2")     # -> The repeating field at ZF1.2 as a tuple: ('REPEAT 1', 'REPEAT 2'...)
msg.find("ZF1.4*.3") # -> The third position of the repeating value at ZF1.4: ('1','2')
msg.find("OBX[3].1") # -> The third obx segment and its value at position 1: 3
```

If you want to count from the opposite direction you can use a negative position value:

```python
msg.find("MSH.-1") # -> The last position on the MSH segment: 2.3
```

MSH is numbered as in the HL7 spec: `MSH.1` is the field separator and `MSH.2` the encoding characters.

```python
msg.find("MSH.1")   # -> |
msg.find("MSH.2")   # -> ^~\&
msg.find("MSH.3")   # -> SendingApp
msg.find("MSH.9.1") # -> ORU
```

Subcomponents can be used without components, as HL7 allows (e.g. a name of `&Whitaker&Emily` is component 1 split into subcomponents):

```python
msg.find("OBR.32.1.2") # -> Whitaker for OBR|...|&Whitaker&Emily|...
```

A plain value is its own first component, so `PID.1.1` is the same as `PID.1` when PID.1 has no components.

If there is a repeating field or segment but your search string is ambiguous it will raise `HL7AmbiguousSegmentException`.

### Missing locations and strict mode

Searching for a location that isn't in the message (a missing segment, a position past the end of a field, etc.) returns `None`. With repeating segments each segment gets its own value (`msg.find("OBX*.99")` -> `[None, None, ...]`).

To raise instead, use strict mode. It raises `HL7LocationNotFoundException`, a subclass of `IndexError`:

```python
msg = HL7Message(hl7_string, strict=True)
msg.find("ZZZ.1") # -> raises HL7LocationNotFoundException
```

`raise_on_index=True` is still accepted as the older name for `strict=True`.

### Update

Components of the HL7 message can be changed using the same find syntax. The one exception is repeating fields. These need to be changed on the level they repeat.

To change a field value just reference it and provide the updated value:

```python
msg.update("MSH.4","New Facility")
msg.find("MSH.4") # -> "New Facility"

msg.update("PID.-1","last element")
msg.find("PID.-1") # -> "last element"
```

This works with specific segments when there are multiple.

```python
msg.update("OBX[1].1","Yay!")
msg.find("OBX[1].1") # -> "Yay!"
```

You can also update part of a segment that isn't there yet and the structure will be extended to accomidate the update.

```python
msg.update("MSH.100","added elements automatically")
msg.find("MSH.100") # -> "added elements automatically"

msg.update("PID.3.12","added elements")
msg.find("PID.3.12") # -> "added elements"
```

It's also possible to update an entire segment at once or another part of a segment but adding to the structure. The internal structure of `HL7Message` is a list of tuples(`segment name`, `segment structure`) and the segment structure is a list of lists. Repeating fields are represented as a tuple. You can access the internal structure via the `internal_structure` function.

When updating a segment or a more complex component of a segment all at once you can reflect this same internal structure and delimeters will be placed accordingly when outputting with `to_string`.

```python
msg.update("ZF1",['test','a','value',['a','sub','value'],('and','a','repeating','field')])
msg.find("ZF1.1") # -> 'test'
msg.find("ZF1.4.2") # -> 'sub'
msg.find("ZF1.5[3]") # -> 'repeating'
```

### Add Segment

It's also possible to add a segment that doesn't exist. Use the `add_segment` function providing the segment name followed by the initial values. You can also specify a third argument of where (1-N) in the list of segments it should be inserted. It will not override the existing segment of that position but instead move the trailing segments (including the one at the specified index) down one index. The function will not take index 0 as an option as this should already be an MSH segment which is how a message must start.

```python
msg.add_segment("ZBS",['new','segment',['with','initial','values']]) # -> adds the ZBS segment to the last position
msg.add_segment("ZCS",['another','segment','right','after','msh'], 1) # -> adds the ZCS segment as the second segment (right after msh)
```

### Emit or Copy

`HL7Message`s can be turned back into an HL7 string with the `to_string` function which takes an optional keyword parameter to set the newline/break character (`newline_char='\r'`)

Also, as updates cause mutation there a copy of an `HL7Message` object can be made using the `copy` function.

## Contributing

Contributions are welcome via pull request.

To report issues use github issues.

There is a `test.sh` file that sets the PYTHONPATH so that pytest runs successfully from the root of the project.
