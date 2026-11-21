"""Typed lesson inputs, independent answers, and bounded C literal substitution.
SPDX-License-Identifier: MIT
"""
import copy
import json
import zlib

MASK = (1 << 64) - 1
DEMO_NUMBERS = [-17, 42, 0, 99, -5, 42, 7, 1, 1024, -300, 18, 9, -1, 256, 3, 64]
DEMO_MESSAGE = 'Custom RV64 core: C -> ELF -> BRAM -> RTL.\n'


def integer(key, label, default, minimum=0, maximum=1000000):
    return dict(key=key, label=label, kind='integer', default=default, minimum=minimum, maximum=maximum)


def array(key, label, default, minimum=-1000000, maximum=1000000):
    return dict(key=key, label=label, kind='array', default=default, count=len(default), minimum=minimum, maximum=maximum)


SCHEMAS = {
    'add': [integer('left', 'Left number', 1), integer('right', 'Right number', 1)],
    'branch': [array('numbers', 'Two test numbers', [-7, 4])],
    'loop': [integer('limit', 'Count from 1 through', 10, maximum=100)],
    'array': [array('numbers', 'Five array elements', [8, -3, 12, 5, -2])],
    'calls': [integer('n', 'Triangular number input', 5, maximum=16)],
    'sort': [array('numbers', 'Six numbers to sort', [9, 3, 7, 1, 5, 2], minimum=0)],
    'demo': [array('numbers', 'Sixteen numbers to sort', DEMO_NUMBERS),
             integer('fibonacci', 'Fibonacci iterations', 40, maximum=50),
             dict(key='message', label='Message for CRC32', kind='text', default=DEMO_MESSAGE, maxLength=80),
             integer('repeats', 'Message repetitions', 8, minimum=1, maximum=8)],
}


def defaults(program):
    return {field['key']: copy.deepcopy(field['default']) for field in SCHEMAS[program]}


def validate_inputs(program, raw=None):
    if program not in SCHEMAS:
        raise ValueError('Unknown program.')
    if raw is None:
        return defaults(program)
    if not isinstance(raw, dict) or set(raw) != {f['key'] for f in SCHEMAS[program]}:
        raise ValueError('Provide exactly the input fields for this program.')
    result = {}
    for field in SCHEMAS[program]:
        value = raw[field['key']]
        if field['kind'] == 'text':
            if not isinstance(value, str) or len(value) > field['maxLength'] or any(
                    not (32 <= ord(c) <= 126 or c in '\n\r\t') for c in value):
                raise ValueError(f"{field['label']}: use at most {field['maxLength']} ASCII characters, including tabs or line breaks.")
        else:
            values = value if field['kind'] == 'array' else [value]
            if field['kind'] == 'array' and (not isinstance(value, list) or len(value) != field['count']):
                raise ValueError(f"{field['label']}: enter exactly {field['count']} integers.")
            if any(type(v) is not int or not field['minimum'] <= v <= field['maximum'] for v in values):
                raise ValueError(f"{field['label']}: integers must be between {field['minimum']} and {field['maximum']}.")
        result[field['key']] = copy.deepcopy(value)
    return result


def expected_output(program, inputs=None):
    x = validate_inputs(program, inputs)
    if program == 'add': values = [x['left'] + x['right']]
    elif program == 'branch': values = [-n if n < 0 else n + 10 for n in x['numbers']]
    elif program == 'loop': values = [sum(range(1, x['limit'] + 1)), x['limit']]
    elif program == 'array': values = [sum(x['numbers']), min(x['numbers']), max(x['numbers'])]
    elif program == 'calls': values = [sum(range(1, x['n'] + 1))]
    elif program == 'sort': values = sorted(x['numbers'])
    else:
        numbers = sorted(x['numbers'])
        fingerprint = 0
        for n in numbers:
            fingerprint = (((fingerprint << 7) | (fingerprint >> 57)) ^ (n & MASK)) & MASK
        a, b = 0, 1
        for _ in range(x['fibonacci']): a, b = b, a + b
        values = [0x43505544454d4f31, 0, sum(numbers), numbers[0], numbers[-1], a,
                  zlib.crc32(x['message'].encode('ascii') * x['repeats']), fingerprint]
    return [n & MASK for n in values]


def render_source(program, template, inputs):
    """Only validated literals are substituted; input strings are C-escaped."""
    x = validate_inputs(program, inputs)
    if x == defaults(program): return template
    expected = expected_output(program, x)
    replacements = []
    numbers = lambda values: ', '.join(map(str, values))
    signed = lambda n: n - (1 << 64) if n >= 1 << 63 else n
    if program == 'add':
        replacements = [('load both ones', 'load both input values'),
                        ('left = 1;', f"left = {x['left']};"), ('right = 1;', f"right = {x['right']};"),
                        ('sum == 2', f'sum == {expected[0]}')]
    elif program == 'branch':
        replacements = [('inputs[2] = {-7, 4}', 'inputs[2] = {' + numbers(x['numbers']) + '}'),
                        ('output[0] == 7 && output[1] == 14', f'output[0] == {expected[0]} && output[1] == {expected[1]}')]
    elif program == 'loop':
        replacements = [('limit = 10;', f"limit = {x['limit']};"),
                        ('sum == 55 && count == 10', f'sum == {expected[0]} && count == {expected[1]}')]
    elif program == 'array':
        replacements = [('numbers[5] = {8, -3, 12, 5, -2}', 'numbers[5] = {' + numbers(x['numbers']) + '}'),
                        ('sum == 20 && minimum == -3 && maximum == 12',
                         f'sum == {signed(expected[0])} && minimum == {signed(expected[1])} && maximum == {signed(expected[2])}')]
    elif program == 'calls':
        replacements = [('input = 5;', f"input = {x['n']};"), ('result == 15', f'result == {expected[0]}')]
    elif program == 'sort':
        replacements = [('numbers[6] = {9, 3, 7, 1, 5, 2}', 'numbers[6] = {' + numbers(x['numbers']) + '}')]
        for i, old in enumerate([1, 2, 3, 5, 7, 9]):
            replacements.append((f'output[{i}] == {old}', f'output[{i}] == {expected[i]}'))
    else:
        replacements = [(numbers(DEMO_NUMBERS), numbers(x['numbers'])),
                        (json.dumps(DEMO_MESSAGE), json.dumps(x['message']).replace('?', r'\?')),
                        ('fibonacci_iterations = 40;', f"fibonacci_iterations = {x['fibonacci']};"),
                        ('message repeated 8x', f"message repeated {x['repeats']}x"),
                        ('repeat < 8;', f"repeat < {x['repeats']};"),
                        ('sum != 1242 || sorted[0] != -300 || sorted[15] != 1024',
                         f'sum != {signed(expected[2])} || sorted[0] != {signed(expected[3])} || sorted[15] != {signed(expected[4])}'),
                        ('a != 102334155ull || crc != 0x97f65c54u || fingerprint != 0x87101f1288184441ull',
                         f'a != {expected[5]}ull || crc != 0x{expected[6]:x}u || fingerprint != 0x{expected[7]:x}ull')]
    for old, new in replacements:
        if template.count(old) != 1:
            raise ValueError('Input substitution no longer matches the C template: ' + old)
        template = template.replace(old, new, 1)
    return template


def display_details(program, inputs, original):
    x = validate_inputs(program, inputs)
    lesson = copy.deepcopy(original)
    if program == 'add':
        lesson.update(title=f"{x['left']} + {x['right']}", summary=f"Load {x['left']} and {x['right']}, add them, and store the answer.",
                      question='Why does the answer reach a register before the output?',
                      answer='ADD writes a register. A later store copies that value into the RAM output mailbox.')
        lesson['outputs'] = [(f"{x['left']} + {x['right']}", 'signed')]
    elif program == 'branch':
        lesson.update(summary=f"Test {x['numbers']}. Negate a negative input; otherwise add 10.",
                      question='Do these inputs exercise both paths of the decision?',
                      answer='One negative and one nonnegative input exercise both paths. Same-sign inputs can leave a path unvisited.')
        lesson['outputs'] = [(f'Input {i+1}: {n}', 'signed') for i,n in enumerate(x['numbers'])]
    elif program == 'loop':
        lesson.update(summary=f"Add the integers from 1 through {x['limit']}. A limit of zero skips the loop.",
                      question='What tells the CPU to repeat the loop or stop?',
                      answer='The loop comparison controls a branch. The next address either repeats the body or continues after the loop.')
        lesson['outputs'] = [(f"Sum: 1 through {x['limit']}", 'signed'), ('Iterations', 'signed')]
    elif program == 'array': lesson['summary'] = f"Scan {x['numbers']} and find its sum, minimum, and maximum."
    elif program == 'calls':
        lesson['summary'] = f"Compute T({x['n']}) by recursively adding the integers down to zero."
        lesson['outputs'] = [(f"Triangular number: T({x['n']})", 'signed')]
    elif program == 'sort': lesson['summary'] = f"Sort {x['numbers']} into ascending order."
    else:
        lesson['summary'] = f"Sort 16 numbers, compute Fibonacci({x['fibonacci']}), and checksum {len(x['message']) * x['repeats']} message bytes."
        lesson['outputs'][5] = (f"Fibonacci({x['fibonacci']})", 'signed')
        lesson['outputs'][6] = (f"CRC32 · {len(x['message']) * x['repeats']} bytes", 'hex')
    return lesson
