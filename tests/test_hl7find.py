#!/usr/bin/env python

import unittest, hl7find

class TestHL7Message(unittest.TestCase):

    def setUp(self):
        f = open('tests/sample-oru.hl7')
        hl7_s = f.read()
        f.close()
        self.hl7_string = hl7_s
        self.msg = hl7find.HL7Message(self.hl7_string)
        self.loud_msg = hl7find.HL7Message(self.hl7_string,raise_on_index=True)


    def test_parse(self):
        self.assertEqual(type(self.msg.internal_structure()),list)
        self.assertEqual(len(self.msg.internal_structure()),20)
        self.assertTrue('MSH' in map(lambda t: t[0], self.msg.internal_structure()))

    def test_shallow_simple_find(self):
        self.assertEqual(self.msg.find("MSH.3"),"SendingApp")
        self.assertEqual(self.msg.find("PID.3.4.3"),"ISO")

    def test_negative_index(self):
        self.assertEqual(self.msg.find("PID.3.-1"),"MR")

    def test_repeating_segment(self):
        self.assertEqual(len(self.msg.find("OBX*")),14)
        self.assertEqual(self.msg.find("OBX[1].1"), '1')
        with self.assertRaises(hl7find.HL7AmbiguousSegmentException):
            self.msg.find("OBX.1")
        self.assertEqual(self.msg.find("OBX*.1")[0],'1')
        self.assertEqual(self.msg.find("OBX*.3.1")[0],'wbc')
        self.assertEqual(self.msg.find("OBX*.3.1")[1],'neutros')

    def test_repeating_field(self):
        self.assertEqual(self.msg.find("ZF1.1"),'TEST')
        self.assertEqual(self.msg.find("ZF1.-2"),'z end')
        with self.assertRaises(hl7find.HL7AmbiguousSegmentException):
            self.msg.find("ZF1.2")
        self.assertEqual(self.msg.find("ZF1.2*"),('REPEAT 1','REPEAT 2','REPEAT 3'))
        self.assertEqual(self.msg.find("ZF1.2*.1"),('REPEAT 1','REPEAT 2','REPEAT 3'));
        self.assertEqual(self.msg.find("ZF1.2[2]"),('REPEAT 2'));

    def test_repeating_segment_and_field(self):
        self.assertEqual(self.msg.find("ZF1.4*.1"),('deeper','deeper'))
        self.assertEqual(self.msg.find("ZF1.4*.3"),('1','2'))

    def test_bad_syntax(self):
        self.assertFalse(self.msg._check_search_syntax("OBX^.2"))
        self.assertFalse(self.msg._check_search_syntax("1.2"))
        self.assertTrue(self.msg._check_search_syntax("OBX.2"))
        self.assertTrue(self.msg._check_search_syntax("OBX*"))
        self.assertTrue(self.msg._check_search_syntax("OBX*.2"))
        self.assertTrue(self.msg._check_search_syntax("PID.-1"))
        self.assertTrue(self.msg._check_search_syntax("ZF1.2*.3"))
        with self.assertRaises(hl7find.InvalidHL7FindSyntaxException):
            self.msg.find("badsyntax")

    def test_emit(self):
        self.assertEqual(self.hl7_string, self.msg.to_string())

    def test_copy(self):
        self.assertEqual(self.msg.copy().to_string(), self.msg.to_string())

    # These tests mutate msg, but it's setup fresh for each test function
    def test_segment_update(self):
        self.msg.update("ZF1",['test','a','value',['a','sub','value'],('and','a','repeating','field')])
        self.assertEqual(self.msg.find("ZF1.1"),'test')
        self.assertEqual(self.msg.find("ZF1.4.2"),'sub')
        self.assertEqual(self.msg.find("ZF1.5[3]"),'repeating')

        self.msg.update("PID.2",["567","John","Doe"])
        self.assertEqual(self.msg.find("PID.2.2"),"John")

    def test_basic_update(self):
        self.msg.update("MSH.4","New Sending Facility")
        self.assertEqual(self.msg.find("MSH.4"),"New Sending Facility")

        self.msg.update("PID.3.4.1","Pants")
        self.assertEqual(self.msg.find("PID.3.4.1"),"Pants")

        self.msg.update("MSH.-1","end")
        self.assertEqual(self.msg.find("MSH.-1"),"end")

        self.msg.update("MSH.100","added elements automatically")
        self.assertEqual(self.msg.find("MSH.100"),"added elements automatically")

        self.msg.update("PID.3.12","added elements")
        self.assertEqual(self.msg.find("PID.3.12"),"added elements")


    def test_indexed_segment_update(self):
        self.msg.update("OBX[2].1","100")
        self.assertEqual(self.msg.find("OBX[2].1"),"100")

    def test_exceptions_on_update(self):
        with self.assertRaises(hl7find.HL7UpdateAttemptTooDeep):
            self.msg.update("MSH.3.1","test")
        with self.assertRaises(hl7find.InvalidHL7FindSyntaxException):
            self.msg.update("OBX*.1","test")

    def test_add_segment(self):
        self.msg.add_segment("ZBS",['new','custom','segment'])
        self.assertEqual(self.msg.find('ZBS.1'),'new')

        self.msg.add_segment("ZCS",['other','custom','segment'],1)
        self.assertEqual(self.msg._find_segment("ZCS")[0],1)

    def test_hide_index_error(self):
        self.assertEqual(self.msg.find('MSH.100'),None)

    def test_raise_index_error(self):
        with self.assertRaises(IndexError):
            self.loud_msg.find('MSH.100')

    def test_missing_locations_are_none(self):
        self.assertEqual(self.msg.find('ZZZ.1'),None)
        self.assertEqual(self.msg.find('OBX[99].1'),None)
        self.assertEqual(self.msg.find('PID.99.1'),None)
        self.assertEqual(self.msg.find('PID.1.2'),None)
        self.assertEqual(self.msg.find('OBX*.99'),[None] * 14)
        self.assertEqual(self.msg.find('ZZZ*.1'),[])

    def test_strict_mode(self):
        strict_msg = hl7find.HL7Message(self.hl7_string,strict=True)
        for location in ['ZZZ.1','OBX[99].1','PID.99.1','PID.1.2','OBX*.99']:
            with self.assertRaises(hl7find.HL7LocationNotFoundException):
                strict_msg.find(location)
        with self.assertRaises(IndexError):
            strict_msg.find('ZZZ.1')

    def test_plain_value_is_its_own_first_component(self):
        self.assertEqual(self.msg.find('PID.1.1'),'1')
        self.assertEqual(self.msg.find('PID.1.-1'),'1')
        self.assertEqual(self.msg.find('PID.1*'),('1',))

    def test_msh_numbering(self):
        self.assertEqual(self.msg.find('MSH.1'),'|')
        self.assertEqual(self.msg.find('MSH.2'),'^~\\&')
        self.assertEqual(self.msg.find('MSH.3'),'SendingApp')
        self.assertEqual(self.msg.find('MSH.9.1'),'ORU')
        self.assertEqual(self.msg.find('MSH.-1'),'2.3')

    def test_subcomponents_without_components(self):
        hl7_string = "\r".join([
            "MSH|^~\\&|gene|org2|BUTTERFLY|BUTTERFLY|20261029144059||ORM^O01^ORM_O01|1|P|2.5.1",
            "OBR|1|o1|fo1|RAD002^Abdominal X-Ray|&Whitaker&Dr. Emily|a&b~c&d"])
        msg = hl7find.HL7Message(hl7_string)
        self.assertEqual(msg.find('OBR.5.1.2'),'Whitaker')
        self.assertEqual(msg.find('OBR.5.1.3'),'Dr. Emily')
        self.assertEqual(msg.find('OBR.5.2'),None)
        self.assertEqual(msg.find('OBR.6*.1.2'),('b','d'))
        self.assertEqual(msg.to_string(newline_char='\r'),hl7_string)

if __name__ == '__main__':
    unittest.main()
