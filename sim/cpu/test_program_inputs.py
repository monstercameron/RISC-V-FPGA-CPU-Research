"""Input boundary and result-oracle tests. Run with Python; no compiler needed.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import unittest
from program_inputs import defaults, validate_inputs, expected_output, render_source, SCHEMAS
from program_catalog import PROGRAMS
from run_c_demo import expected_results

ROOT=Path(__file__).resolve().parents[2]


class InputTests(unittest.TestCase):
    def test_defaults_preserve_firmware_source(self):
        for program,spec in PROGRAMS.items():
            with self.subTest(program=program):
                source=(ROOT/spec['source']).read_text(encoding='utf-8')
                self.assertEqual(render_source(program,source,defaults(program)),source)
        self.assertEqual(expected_output('demo'),expected_results())

    def test_known_answers(self):
        cases=[('add',{'left':7,'right':8},[15]),
               ('branch',{'numbers':[3,9]},[13,19]),
               ('loop',{'limit':0},[0,0]),('loop',{'limit':100},[5050,100]),
               ('array',{'numbers':[-4,-4,-4,-4,-4]},[(1<<64)-20,(1<<64)-4,(1<<64)-4]),
               ('calls',{'n':16},[136]),('sort',{'numbers':[4,4,0,9,1,1]},[0,1,1,4,4,9])]
        for program,inputs,answer in cases:
            self.assertEqual(expected_output(program,inputs),answer)
        inputs=defaults('demo');inputs.update(message='123456789',repeats=1,fibonacci=0)
        self.assertEqual(expected_output('demo',inputs)[5:7],[0,0xcbf43926])

    def test_bounds_and_types(self):
        for program,fields in SCHEMAS.items():
            for field in fields:
                if field['kind']=='text': continue
                for value in [True,1.5,'3',field['minimum']-1,field['maximum']+1]:
                    inputs=defaults(program)
                    inputs[field['key']]=[value]*field['count'] if field['kind']=='array' else value
                    with self.subTest(program=program,key=field['key'],value=value),self.assertRaises(ValueError):
                        validate_inputs(program,inputs)

    def test_shape_and_extra_fields(self):
        for value in [[],{}, {'left':1}, {'left':1,'right':1,'source':'evil'}, {'left':None,'right':1}]:
            with self.assertRaises(ValueError): validate_inputs('add',value)
        for value in [[1,2], '1,2,3,4,5', [1]*6]:
            with self.assertRaises(ValueError): validate_inputs('array',{'numbers':value})

    def test_message_encoding(self):
        inputs=defaults('demo')
        for value in ['x'*81,'\0','é','😀']:
            inputs['message']=value
            with self.assertRaises(ValueError): validate_inputs('demo',inputs)
        inputs['message']='A "quote"\\path\n</script>'
        source=render_source('demo',(ROOT/PROGRAMS['demo']['source']).read_text(encoding='utf-8'),inputs)
        self.assertIn('A \\"quote\\"\\\\path\\n</script>',source)
        self.assertNotIn('\n</script>',source)

    def test_changed_template_fails_closed(self):
        with self.assertRaises(ValueError): render_source('add','int main(void) {return 0;}',{'left':2,'right':3})


if __name__=='__main__': unittest.main()
